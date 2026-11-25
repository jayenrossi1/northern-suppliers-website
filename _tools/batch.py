#!/usr/bin/env python3
"""Attach product photos and rebuild the photos-needed list.

usage: python3 _tools/batch.py '<json>' [xlsx_out]
json:  [[source_image, [pid, ...], mode], ...]   mode: "white" (default), "cut" or "photo"
  white  photo already on a white background: trim and square it
  cut    remove the background first, then place on white
  photo  keep the photo as it is, centre-cropped square
The catalogue lives inside index.html (var PRODUCTS=[...]); this updates it in place.
"""
import sys, json, re, os, datetime
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, 'index.html')
CATS = ['Pool','Chemicals','Washroom & hygiene','Catering & packaging','Cleaning','Jars, bottles & caps','Bags & paper','Kitchen & knives','Food & beverage','Matting & storage']
_sess = None

def load():
    s = open(IDX, encoding='utf-8').read()
    i = s.find('var PRODUCTS=') + len('var PRODUCTS='); j = s.find('];', i) + 1
    return s, i, j, json.loads(s[i:j])

def cut(im):
    global _sess
    from rembg import remove, new_session
    if _sess is None: _sess = new_session('isnet-general-use')
    c = remove(im.convert('RGB'), session=_sess)
    bg = Image.new('RGBA', c.size, (255, 255, 255, 255)); bg.alpha_composite(c)
    return bg.convert('RGB')

def prep(path, mode='white'):
    im = Image.open(path)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA'); bg = Image.new('RGBA', im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg
    im = im.convert('RGB')
    if mode == 'photo':
        w, h = im.size; s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        return im.resize((800, 800), Image.LANCZOS)
    if mode == 'cut': im = cut(im)
    g = im.convert('L').point(lambda v: 255 if v < 244 else 0)
    box = g.getbbox()
    if box: im = im.crop(box)
    w, h = im.size; side = int(max(w, h) * 1.12)
    sq = Image.new('RGB', (side, side), (255, 255, 255)); sq.paste(im, ((side - w) // 2, (side - h) // 2))
    return sq.resize((800, 800), Image.LANCZOS)

def stamp(s):
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=10)
    t = 'Site updated ' + now.strftime('%-d %b %Y, %-I:%M %p').replace('AM', 'am').replace('PM', 'pm')
    return re.sub(r'Site updated[^<]*', t, s, count=1)

def needed(P):
    need = [p for p in P if not p.get('img')]
    def key(p):
        t = p['type']; g = 0 if t == 'Dolphin pool cleaners' else 1 if t == 'Dolphin parts and accessories' else 2
        return (g, CATS.index(p['cat']), p['name'].lower())
    return sorted(need, key=key)

def xlsx(P, out):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Photos needed'
    ws.append(['#', 'Category', 'Product', 'Pack / size', 'Product ID', 'Sent?'])
    for n, p in enumerate(needed(P), 1): ws.append([n, p['cat'], p['name'], p['desc'], p['pid'], None])
    for c in ws[1]: c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='0B2A5C')
    for col, w in zip('ABCDEF', [5, 22, 58, 44, 12, 8]): ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions; wb.save(out)

def main():
    jobs = json.loads(sys.argv[1]); out = sys.argv[2] if len(sys.argv) > 2 else None
    s, i, j, P = load(); by = {p['pid']: p for p in P}
    logp = os.path.join(ROOT, '_tools', 'received.json')
    log = json.load(open(logp)) if os.path.exists(logp) else {}
    for job in jobs:
        src, pids = job[0], job[1]; mode = job[2] if len(job) > 2 else 'white'
        im = prep(src, mode)
        for pid in pids:
            assert pid in by, pid
            im.save(os.path.join(ROOT, 'img', f'{pid}.webp'), quality=86, method=6)
            im.resize((400, 400), Image.LANCZOS).save(os.path.join(ROOT, 'img', 'm', f'{pid}.webp'), quality=82, method=6)
            im.resize((160, 160), Image.LANCZOS).save(os.path.join(ROOT, 'img', 't', f'{pid}.webp'), quality=80, method=6)
            by[pid]['img'] = f'img/t/{pid}.webp'; log[str(pid)] = os.path.basename(src)
            print('ok', pid, by[pid]['name'])
    s = s[:i] + json.dumps(P, ensure_ascii=False, separators=(',', ':')) + s[j:]
    open(IDX, 'w', encoding='utf-8').write(stamp(s))
    json.dump(log, open(logp, 'w'), indent=0, sort_keys=True)
    print(sum(1 for p in P if p.get('img')), 'of', len(P), 'have photos')
    if out: xlsx(P, out)

if __name__ == '__main__': main()
