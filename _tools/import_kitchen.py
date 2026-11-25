#!/usr/bin/env python3
"""Turn safe fields from a POS product export into catalogue entries.

Reads a JSON list of rows holding only ProductId, SupplierSKU, ShortDescription, Size,
Colour, Season (material), Brand and ProductType. Prices, costs, stock and custom notes
are never read. Writes {added: [...], held: [...]} for review; apply with --apply.
"""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from english_words import get_english_words_set
    WORDS = get_english_words_set(['web2'], lower=False)
except Exception:
    WORDS = set()

PROPER = {w.lower(): w for w in '''Avanti Bakemaster BergHOFF Brabantia Benriner Bohemia Brinix Capri ChefTech Cuisinart Cuisson
Fibrox Geotalics Glasslock Gokart Hackit Henrik HydroQuench Inox Joie Karlstert Kilner Lara Livingston Malmo Melrose Nexgen Oben Oko OXO
Perfekt Pyrocast Pyrochef Pyrolux Pyrosteel Pyrostone Retracto Saluti Scanpan Serroni Sorensen Speedycut Spiretti Stirling Swibo Varden
Victorinox Wenger Wilkie YumYum Zippo Paw BBQ XL DAWG Balmoral Aussie Xmas Ceylon Eden Susan WeCare Monch Sharkie Carnivale Manico Rigato
Emory Droid Eggies Typhoon Chasseur Prepara Gefu Swissmar Mundial Global Trenton Stanley Cuisipro Veneto Zyliss Peer Swiss Deco USB LED
DW PP PS PC QT Christmas French Turkish Irish American Vin Bouquet Ignite
Chinese Japanese Italian Dreaming Highlands'''.split()}
FIX = {'advanti': 'Avanti', 'advant': 'Avanti', 'bakemast': 'Bakemaster', 'edgemaster': 'Edge Master', 'fibx': 'Fibrox', 'gocup': 'Go Cup',
       'pryocast': 'Pyrocast', 'pryrocast': 'Pyrocast', 'vic': 'Victorinox', 'vict': 'Victorinox', 'victroinox': 'Victorinox', 'cuissn': 'Cuisson',
       'blk': 'black', 'nyl': 'nylon', 'sgl': 'single', 'hndle': 'handle', 'hdle': 'handle', 'knf': 'knife', 'ktchn': 'kitchen', 'rnd': 'round',
       'sq': 'square', 'sqr': 'square', 'str': 'straight', 'strt': 'straight', 'ss': 'stainless steel', 'lb': 'loose base', 'repl': 'replacement',
       'pce': 'piece', 'pcs': 'piece', 'peice': 'piece', 'gr': 'g', 'ano': 'anodised', 'bakware': 'bakeware', 'delux': 'deluxe', 'difuser': 'diffuser',
       'lisfestyle': 'lifestyle', 'melmine': 'melamine', 'ornamnt': 'ornament', 'pairing': 'paring', 'parsely': 'parsley', 'pestal': 'pestle',
       'plung': 'plunger', 'quich': 'quiche', 'shapener': 'sharpener', 'sharpner': 'sharpener', 'spekled': 'speckled', 'teir': 'tier', 'wisk': 'whisk',
       'hobnall': 'hobnail', 'vege': 'vegetable', 'veg': 'vegetable', 'silicon': 'silicone', 'aust': 'Australian', 'tom': 'tomato', 'blubber': 'bubble',
       'replacment': 'replacement', 'trolly': 'trolley', 'porer': 'pourer', 'strait': 'straight', 'frypan': 'frypan', 'ltr': 'L', 'ltrs': 'L', 'lt': 'L',
       'litre': 'L', 'kg': 'kg', 'ml': 'ml', 'cm': 'cm', 'mm': 'mm', 'oz': 'oz', 'pk': 'pack', 'dishrack': 'dish rack', 'multi': 'multi', 'mini': 'mini'}
BRANDFIX = {'Wilkie Bro': 'Wilkie Brothers', 'Chefs Choice': "Chef's Choice", 'Bakers Secret': "Baker's Secret", 'Bohmeia': 'Bohemia', 'SWIBO': 'Swibo'}
BRANDS_IN_NAME = ['Avanti', 'Victorinox', 'Scanpan', 'Chasseur', 'Glasslock', 'Mundial', 'Pyrolux', 'Bakemaster', 'Kilner', 'Cuisipro', 'Zippo', 'Karlstert',
                  'Brabantia', 'Benriner', 'Swissmar', 'Gefu', 'Edge Master', 'Bohemia', 'Serroni', 'Swibo', 'True Utility', 'Paw', 'Typhoon', 'Joie',
                  'Capri', 'BergHOFF', 'Cuisinart', 'OXO', 'Wilkie', 'Wenger', 'Hackit']

def flag(n):
    n = n.strip()
    if re.match(r'^DISC\w*\b', n, re.I): return 'discontinued'
    if re.match(r'^NULL\b', n, re.I): return 'null'
    if re.match(r'^SO\b', n, re.I): return 'SO'
    if re.match(r'^DC\b', n): return 'DC'
    return ''

def word(w, first):
    lw = w.lower()
    if lw in FIX: out = FIX[lw]
    elif lw in PROPER: out = PROPER[lw]
    elif lw in WORDS or not WORDS: out = lw
    elif w.capitalize() in WORDS and w[0].isupper(): out = w.capitalize()      # only known as a proper noun
    else: out = lw
    return out[0].upper() + out[1:] if first and out else out

def clean_name(raw, brand):
    n = raw.strip()
    notes = []
    n = re.sub(r'\s*RRP\s*\$?\s*[\d.,]+', '', n, flags=re.I)                     # never carry prices
    n = re.sub(r'\(\s*[\d.]+\s*old code\s*\)', '', n, flags=re.I)
    if re.search(r'-?\s*SOLD CTN ONLY', n, re.I):
        n = re.sub(r'\s*-?\s*SOLD CTN ONLY', '', n, flags=re.I); notes.append('sold by the carton')
    model = ''
    m = re.search(r'(?<![\d.])(\d\.\d{4}(?:\.\d{1,3}[A-Z]*\d*)?)(?![\d])', n)       # Victorinox model numbers
    if m: model = m.group(1); n = (n[:m.start()] + n[m.end():])
    n = re.sub(r'\bS/S\b', 'stainless steel', n, flags=re.I)
    n = re.sub(r'\bS/ANO\b', 'silver anodised', n, flags=re.I)
    n = re.sub(r'\bL/B(ase)?\b', 'loose base', n, flags=re.I)
    n = re.sub(r'\bW/(?=\w)', 'with ', n, flags=re.I)
    n = re.sub(r'\bS/Part\b', 'spare part', n, flags=re.I)
    n = re.sub(r'\bEx/Broad\b', 'extra broad', n, flags=re.I)
    n = re.sub(r'\bFib\.', 'Fibrox', n)
    n = re.sub(r'\bAust\.', 'Australian', n)
    n = re.sub(r'(\d)\s*[xX]\s*(?=\d)', r'\1 x ', n)                               # 35x28 -> 35 x 28
    n = re.sub(r'(\d)\s*(?:cm|mm)\s*x\s*(?=\d)', r'\1 x ', n, flags=re.I)
    n = re.sub(r'([a-z]{3,})(\d)', r'\1 \2', n)
    n = re.sub(r'\bnon sick\b', 'non stick', n, flags=re.I)
    n = re.sub(r'\s+ea$', '', n, flags=re.I)
    n = re.sub(r'\bpk\s*(\d+)\b', r'pack of \1', n, flags=re.I)                    # pk20
    n = re.sub(r'(\d+)\s*pk\b', r'\1 pack', n, flags=re.I)                         # 3pk
    n = re.sub(r'(\d+)\s*(pce|pcs|pc|peice|piece)s?\b', r'\1 piece', n, flags=re.I)
    n = re.sub(r'(\d(?:\.\d+)?)\s*(ltrs?|lt|litres?|l)\b', r'\1 L', n, flags=re.I)
    n = re.sub(r'(\d(?:\.\d+)?)\s*(cm|mm|ml|kg|oz|qt)\b', lambda m: m.group(1) + ' ' + (m.group(2).upper() if m.group(2).lower() == 'qt' else m.group(2).lower()), n, flags=re.I)
    n = re.sub(r'(\d)\s*gr?\b', r'\1 g', n)
    n = re.sub(r'(\d)\s*cup\b', r'\1 cup', n, flags=re.I)
    n = re.sub(r'\bset\s+of\b', 'set of', n, flags=re.I)
    m = re.search(r'\bCTN\s*(\d+)\b', n, re.I)
    if m: notes.append('PACK:Carton of ' + m.group(1)); n = n[:m.start()] + n[m.end():]
    n = re.sub(r'\beach\b', '', n, flags=re.I)
    n = re.sub(r'-(?=\d)', ' ', n)
    n = re.sub(r'\s*/\s*', ' / ', n)
    n = re.sub(r'(\d) / (\d)', r'\1/\2', n)
    n = re.sub(r'\s+-\s*$|^\s*-\s*', '', n)
    n = re.sub(r'\s*-\s*(?=[A-Za-z])', ' - ', n) if ' -' in n or '- ' in n else n
    n = n.replace(' #', '').replace('  ', ' ')
    # brand: take it out of the name wherever it sits, then lead with it
    b = BRANDFIX.get(brand or '', brand or '')
    for cand in BRANDS_IN_NAME + ['Advanti', 'Advant', 'Bakemast', 'Vic', 'Vict', 'Victroinox', 'Edgemaster', 'Wilkie Bro']:
        pat = r'(?<![A-Za-z])' + re.escape(cand) + r'(?![A-Za-z])'
        if re.search(pat, n, re.I):
            canon = FIX.get(cand.lower(), cand)
            if not b: b = canon
            if canon.lower() in b.lower() or cand in ('Vic', 'Vict', 'Victroinox', 'Advanti', 'Advant', 'Bakemast', 'Edgemaster'):
                n = re.sub(pat, ' ', n, flags=re.I)
    n = re.sub(r'\bINT BAKEWARE\b', '', n)
    n = re.sub(r'\s+', ' ', n).strip(' -,/')
    toks = re.split(r'(\s+|[/,()&\-])', n)
    out = []; first = True
    for t in toks:
        if re.fullmatch(r"[A-Za-z][A-Za-z'+]*", t or ''):
            out.append(word(t, first and not b)); first = False
        else:
            out.append(t)
            if t and t.strip() and not re.fullmatch(r'[\s/,()&\-]+', t): first = False
    n = ''.join(out)
    n = re.sub(r'\s+', ' ', n).strip(' -,/')
    n = re.sub(r'\s+,', ',', n)
    n = re.sub(r'\bgo cup\b', 'Go Cup', n, flags=re.I)
    n = re.sub(r'\bcafe press\b', 'Cafe Press', n, flags=re.I)
    n = re.sub(r'\bswiss classic\b', 'Swiss Classic', n, flags=re.I)
    n = re.sub(r'\bswiss army\b', 'Swiss Army', n, flags=re.I)
    n = re.sub(r'\btrue utility\b', 'True Utility', n, flags=re.I)
    n = re.sub(r'\bedge master\b', 'Edge Master', n, flags=re.I)
    n = re.sub(r'\bart deco\b', 'Art Deco', n, flags=re.I)
    n = re.sub(r'\bl[ae] cuisson\b', 'Le Cuisson', n, flags=re.I)
    n = re.sub(r'(\d) l\b', r'\1 L', n)
    n = re.sub(r'\bsize ([smlx]{1,3})\b', lambda m: 'size ' + m.group(1).upper(), n)
    n = re.sub(r' ([sml])$', lambda m: ' ' + m.group(1).upper(), n)
    n = re.sub(r'\be-z grip\b', 'E-Z Grip', n, flags=re.I)
    n = re.sub(r'\bha\+', 'HA+', n, flags=re.I)
    n = re.sub(r'\blazy susan\b', 'lazy Susan', n, flags=re.I)
    if b and not n.lower().startswith(b.lower()):
        n = b + ' ' + n
    elif n: n = n[0].upper() + n[1:]
    return n, b, model, notes

def pack(size):
    s = (size or '').strip()
    if not s or s.lower() == 'each': return 'Each'
    m = re.fullmatch(r'(\d+)\s*pk', s, re.I)
    if m: return 'Pack of ' + m.group(1)
    m = re.fullmatch(r'ctn\s*(\d+)', s, re.I)
    if m: return 'Carton of ' + m.group(1)
    m = re.fullmatch(r'slv\s*(\d+)', s, re.I)
    if m: return 'Sleeve of ' + m.group(1)
    m = re.fullmatch(r'([\d.]+)\s*lt', s, re.I)
    if m: return m.group(1) + ' L'
    return {'sm': 'Small', 'medium': 'Medium', 'large': 'Large'}.get(s.lower(), s)

RULES = [
 ('Lunch boxes', r'yumyum|bento|lunch ?box|lunch bag|sandwich box|snack box'),
 ('Drink bottles and cups', r'go ?cup|hydroquench|drink bottle|water bottle|flask|tumbler|travel mug|smoothie|fluid bottle|insulated bottle|straw'),
 ('Pocket knives and tools', r'pocket knife|swiss army|true utility|zippo|multi ?tool|carabiner|wenger|swisscard|nail clip'),
 ('Sharpening', r'sharpen|whetstone|sharpening steel|^steel (diamond|sharpening|oval|round|\d)|edge ?master|honing'),
 ('Butcher supplies', r'glove cut|cut resistan|larding|tying needle|twine|meat hook|bone saw'),
 ('Kitchen tools', r'mixing bowl|ice cream|thermometer|kitchen scale|timer|peeler|grater|garlic press|can opener|colander|strainer|whisk|spatula|ladle|tongs?\b|masher|mortar'),
 ('Tableware and serving', r'egg tray|table (fork|spoon|knife|set)|dessert ?spoon|tea ?spoon|soup spoon|cutlery|steak knife set|table forks|table spoons'),
 ('Knives', r'knife|knives|cleaver|santoku|mezzaluna|shears|scissor|cimeter|boning|slicer knife|knife block|knife guard|blade guard|carving (fork|knife|set)|paring|fillet|slicing (knife|point)'),
 ('Tea and coffee', r'teapot|tea pot|\btea\b|coffee|plunger|espresso|infuser|kettle|frother|knock box|cafe press|caffe|\blatte|milk jug|tamper'),
 ('Cookware', r'fry ?pan|saucepan|casserole|french oven|\bwok\b|stock ?pot|roaster|roasting|grill pan|skillet|pressure cooker|steamer|camp oven|chef pan|saute|paella|tagine|hotpot|cookware|poach|omelette|milk pan|splatter|crepe|pyrocast|pyrostone|pyrochef|griddle|dutch oven|egg ring|food warmer'),
 ('Bakeware', r'cake|baking|bakeware|muffin|loaf|\btart|quiche|\bpie\b|flan|cookie|biscuit|piping|\bicing|fondant|pastry|rolling pin|cooling rack|savarin|springform|bundt|mould|brownie|pizza|cannoli|cream horn|ramekin|macaroon|madeleine|dough|sifter|pudding|patty|cupcake|bread (tin|pan)|proving|sugar craft|decorat|oven thermometer|pie weights|baguette|lamington|slice pan|friand|donut|doughnut'),
 ('Glassware and bar', r'wine|cocktail|shaker|decanter|jigger|corkscrew|bottle opener|bottle carrier|wine purse|\bice (cube|bucket|ball|tong|block|brick|mould|tray|pick|crush)|beer|brandy|muddler|drink dispenser|drinks dispenser|water jug|carafe|champagne|stopper|whisky|tumbler|highball|pourer|\bbar\b|bohemia'),
 ('Tableware and serving', r'plate|dinner set|platter|placemat|napkin|salt|pepper|cruet|butter dish|oil can|gravy|lazy susan|trivet|coaster|table ?cloth|food cover|serving|server|salad bowl|egg cup|cake stand|cheese|oyster|chopstick|toast rack|mug|sugar bowl|jug'),
 ('Storage', r'canister|container|storage|bread bin|\bjar\b|glasslock|bag clip|compost|\bbin\b|caddy|dish ?rack|sink|organis|draining|spice rack|fridge|produce bag|food saver|avocado saver|wrap|cover'),
]
BRAND_TYPE = {'Bakemaster': 'Bakeware', 'Pyrolux': 'Cookware', 'Chasseur': 'Cookware', 'Scanpan': 'Cookware', 'Glasslock': 'Storage', 'Edge Master': 'Sharpening', 'True Utility': 'Pocket knives and tools'}

def classify(raw, brand, ptype):
    low = raw.lower()
    if brand == 'Kilner' or 'kilner' in low: return 'Jars, bottles & caps', 'Kilner jars and preserving'
    if brand == 'Paw' or 'napkin' in low and 'holder' not in low: return 'Catering & packaging', 'Napkins'
    if 'shopping trolley' in low: return 'Bags & paper', 'Shopping trolleys'
    if 'squeegee' in low: return 'Cleaning', 'Cleaning'
    for ty, pat in RULES:
        if re.search(pat, low): return 'Kitchen & knives', ty
    if ptype == 'Kids Lunchboxes': return 'Kitchen & knives', 'Lunch boxes'
    if ptype == 'Drink Bottles': return 'Kitchen & knives', 'Drink bottles and cups'
    if brand in BRAND_TYPE: return 'Kitchen & knives', BRAND_TYPE[brand]
    if ptype == 'Butcher': return 'Kitchen & knives', 'Butcher supplies'
    return 'Kitchen & knives', 'Kitchen tools'

def convert(rows, have):
    added, held = [], []
    for r in rows:
        raw = re.sub(r'\s+', ' ', str(r['ShortDescription'])).strip(); pid = int(r['ProductId'])
        f = flag(raw)
        if pid in have: continue
        if f: held.append({'pid': pid, 'flag': f, 'name': raw, 'brand': r.get('Brand') or ''}); continue
        name, brand, model, notes = clean_name(raw, r.get('Brand'))
        size = r.get('Size')
        if not brand and re.search(r'go ?cup', raw, re.I): brand = 'Avanti'; name = 'Avanti ' + name
        if not brand and re.search(r'\blara\b', raw, re.I): brand = 'Bohemia'; name = 'Bohemia ' + name[0].lower() + name[1:]
        for x in [x for x in notes if x.startswith('PACK:')]: size = x[5:]; notes.remove(x)
        if re.search(r'lunch napkin', raw, re.I):
            d = re.sub(r'\b(paw|lunch|napkins?|33\s*cm|pk\s*20|20\s*pk)\b', ' ', raw, flags=re.I)
            d = re.sub(r'\s+', ' ', d).strip(' -')
            d = ' '.join(w if w.lower() in ('on', 'and', 'of', 'the', '&', 'in') else w[0].upper() + w[1:].lower() for w in d.split()).replace('Wecare', 'WeCare').replace('Bbq', 'BBQ').replace('Ornamnt', 'Ornament')
            name, brand = 'Paw lunch napkins 33 cm, ' + d, 'Paw'; size = size or '20 Pk'
        cat, ty = classify(raw, brand, r.get('ProductType'))
        bits = [size if str(size).startswith('Carton') else pack(size)]
        mat = (r.get('Season') or '').strip().lower().replace('silicon', 'silicone').replace('siliconee', 'silicone')
        if mat and mat not in name.lower(): bits.append(mat)
        col = (r.get('Colour') or '').strip().lower()
        if col and col not in name.lower(): bits.append(col)
        if model: bits.append('model ' + model)
        bits += notes
        sku = ' '.join(dict.fromkeys(str(r.get('SupplierSKU') or '').split()))
        added.append({'sku': sku, 'name': name, 'desc': ', '.join(bits), 'brand': brand, 'cat': cat, 'type': ty, 'pid': pid, 'img': '', '_raw': raw})
    return added, held

if __name__ == '__main__':
    import batch
    rows = json.load(open(sys.argv[1])); s, i, j, P = batch.load()
    added, held = convert(rows, {p['pid'] for p in P})
    json.dump({'added': added, 'held': held}, open(sys.argv[2], 'w'), ensure_ascii=False, indent=0)
    print(len(added), 'to add,', len(held), 'held')
    if '--apply' in sys.argv:
        for a in added: a.pop('_raw', None)
        retype = {128522: 'Knives', 128042: 'Knives', 128480: 'Sharpening', 129785: 'Glassware and bar', 125537: 'Glassware and bar'}
        for p in P:
            if p['pid'] in retype: p['type'] = retype[p['pid']]
        P += added
        s = s[:i] + json.dumps(P, ensure_ascii=False, separators=(',', ':')) + s[j:]
        open(batch.IDX, 'w', encoding='utf-8').write(batch.stamp(s)); print('applied', len(P))
