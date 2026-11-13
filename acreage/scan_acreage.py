#!/usr/bin/env python3
"""Acreage Finder scanner.

Pulls every rural listing of 100+ acres (up to a price cap) from farmbuy.com for each
state, opens the detail page of the cheaper ones to read features, prices each block
against similar blocks, and writes acreage-data.js for acreage.html.

Run:  python3 scan_acreage.py            (full scan, ~10-20 min, polite 1.1s between requests)
      python3 scan_acreage.py --no-details   (faster, skips detail pages)
Optional deal alerts: set the ACREAGE_NTFY_TOPIC environment variable to an ntfy topic (never put it in a file).
"""
import json, re, sys, time, html, os, math, statistics, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (AcreageFinder personal scanner)"
DELAY = 1.1          # farmbuy robots.txt asks for 1s between requests
MIN_ACRES = int(os.environ.get("ACREAGE_MIN_ACRES", "10"))   # smallest block to collect
MAX_PRICE = 3_000_000  # pricier listings are kept only as comparisons
DETAIL_MAX = 3_000_000  # open detail pages for every priced block (features + bush/farm/house)
STATES = {"QLD": "Queensland", "NSW": "New South Wales", "VIC": "Victoria", "SA": "South Australia",
          "WA": "Western Australia", "TAS": "Tasmania", "NT": "Northern Territory"}

_last = [0.0]
def get(url):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                _last[0] = time.time()
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            _last[0] = time.time()
            if attempt == 2: print("  failed:", url, e, file=sys.stderr); return ""
            time.sleep(3 * (attempt + 1))

CARD = re.compile(r'<script type="application/json">\s*(\{"address".*?\})\s*</script>', re.S)

def search_state(code):
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"ac": "state:" + STATES[code], "radius": 0, "max": MAX_PRICE,
                                    "landarea": MIN_ACRES, "searchtype": 1, "orderby": "priceasc", "page": page})
        s = get("https://farmbuy.com/find-rural-property?" + q)
        cards = []
        for m in CARD.finditer(s):
            try: cards.append(json.loads(m.group(1)))
            except ValueError: pass
        if not cards: break
        new = [c for c in cards if c.get("id") not in {o.get("id") for o in out}]
        if not new: break
        out += new
        print(f"  {code} page {page}: {len(cards)} cards")
        page += 1
        if page > 60: break
    return out

NUM = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|mil|million)?\b"
def parse_price(t):
    """Lowest sensible dollar figure in a price string, or None."""
    if not t: return None
    t = html.unescape(t).lower().replace("–", "-")
    if re.search(r"\b(priced from|from \$|lots? from|per lot|each|per block|lots? \d+\s*(?:&|and|,)\s*\d+|\blot\s*\d+[a-z]?\s*[:\-–]?\s*\$)", t): return None
    if re.search(r"\bper\s*(acre|ac|ha|hectare)\b|/\s*(ac|acre|ha)\b|per week|/wk|p\.?w\b", t): return None
    vals = []
    for m in re.finditer(NUM, t):
        raw = m.group(1); n = float(raw.replace(",", "")); u = m.group(2)
        parts = raw.split(".")[0].split(",")
        if len(parts) > 1 and len(parts[-1]) < 3: n *= 10 ** (3 - len(parts[-1]))   # "$2,100,00" typo
        if u == "k": n *= 1e3
        elif u: n *= 1e6
        if 20_000 <= n <= 60_000_000: vals.append(n)
    return min(vals) if vals else None

def acres_of(c):
    m = re.match(r"([\d.,]+)\s*(ac|ha)", (c.get("landArea") or "").replace(",", ""))
    if not m: return None
    v = float(m.group(1)); return v * 2.471 if m.group(2) == "ha" else v

# ---- detail page features -------------------------------------------------
FEATURES = [  # key, label, regex, quality points
    ("house",   "House or cabin", r"\b(\d\s*bed(room)?s?|homestead|dwelling|residence|cottage|cabin|farmhouse|home\b|house\b|shack|hut\b)", 14),
    ("dam",     "Dam(s)",        r"\bdams?\b", 6),
    ("bore",    "Bore",          r"\bbores?\b|\bwell\b", 6),
    ("creek",   "Creek or river", r"\bcreek|river frontage|\briver\b|spring[- ]fed|permanent water|waterhole", 7),
    ("power",   "Power",         r"\bpower (is )?(connected|on site|available|to (the )?boundary)|mains power|grid power|power to|electricity (connected|available)", 7),
    ("solar",   "Solar",         r"\bsolar\b", 3),
    ("shed",    "Shed",          r"\bshed\b|machinery shed|workshop", 4),
    ("fenced",  "Fenced",        r"\b(fully|boundary|well|stock)[- ]fenced|\bfencing\b", 3),
    ("bitumen", "Sealed road",   r"\bbitumen|sealed road|highway frontage|all[- ]weather (road|access)", 4),
    ("rain",    "Good rainfall", r"\b(7|8|9|1[0-9])\d\d ?mm\b", 3),
    ("bush",    "Bush block",    r"bush ?block|bushland|\bscrub\b|timbered|uncleared|native (bush|vegetation|forest)|\bmallee\b|untouched|wilderness", 0),
    ("titles",  "More than one title", r"\b(two|three|four|five|six|2|3|4|5|6|multiple|several|separate|individual) (separate |freehold |individual )?titles\b|\btitles? (can be|could be) sold separately|sold (as|on) (separate|individual) titles", 0),
    ("subdiv",  "Subdivision potential", r"subdivision (potential|approv|opportunit|possible)|potential (to|for) subdivi|approved (for )?subdivision|da approved|development approval|subdivide|rezon", 0),
    ("vendor",  "Vendor finance", r"vendor finance|terms available|deposit and|owner finance", 0),
]
FLAGS = [  # key, label, regex, quality penalty
    ("covenant", "Covenant / conservation agreement", r"covenant|heritage agreement|conservation agreement|trust for nature|biodiversity (stewardship|conservation)|land for wildlife agreement", 15),
    ("nobuild",  "No house allowed / no building entitlement", r"no (dwelling|building|house) (entitlement|rights|permit)|not (eligible|permitted) for a dwelling|cannot build|no ability to build", 20),
    ("lease",    "Leasehold, not freehold", r"leasehold|western lands lease|pastoral lease|perpetual lease|term lease|mining tenement|mining lease", 12),
    ("access",   "Access needs checking", r"no legal access|access via neighbou?r|via (a )?neighbou?r|unformed road|paper road|4wd only|four wheel drive only|right of way", 10),
    ("flood",    "Flood-prone", r"flood[- ]prone|subject to flood|floods? (regularly|occasionally)|flood ?plain", 6),
    ("remote",   "Very remote / off-grid", r"off[- ]grid|no services|no power|no electricity", 4),
    ("gas",      "Gas wells / CSG", r"gas well|csg|coal seam|petroleum lease", 4),
]

def detail(url):
    s = get(url)
    if not s: return None
    t = re.search(r"<title>(.*?)</title>", s, re.S)
    title = html.unescape(t.group(1)) if t else ""
    sold = bool(re.search(r"\bSold\b", title.split("|")[0]))
    uo = bool(re.search(r"under (offer|contract)", title, re.I)) or 'class="propertyPage-banner underoffer' in s
    i = s.find("propertyPage-title"); j = s.find("propertyPage-contact", i)
    seg = s[i:j if j > i else i + 80000] if i > 0 else ""
    seg = re.sub(r"<script.*?</script>|<style.*?</style>", " ", seg, flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", seg))).strip()
    low = text.lower()
    feats = [k for k, _, rx, _ in FEATURES if re.search(rx, low)]
    flags = [k for k, _, rx, _ in FLAGS if re.search(rx, low)]
    if "power" in feats and re.search(r"no power|no electricity", low): feats.remove("power")
    if "house" in feats and re.search(r"house site|building site|build your|no house|vacant", low) and not re.search(r"\d\s*bed|homestead|cottage|cabin|dwelling (on|with)|existing (home|house|dwelling)", low):
        feats.remove("house")
    m = re.search(r"user-content[^>]*>(.*?)</div>", s, re.S)
    desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip() if m else ""
    la = re.search(r'data-lat="(-?[\d.]+)"', s); lo = re.search(r'data-lng="(-?[\d.]+)"', s)
    rg = re.search(r'"property":\{"address":\{[^}]*"region":(null|"[^"]*")', s)
    region = json.loads(rg.group(1)) if rg else None
    return {"feats": feats, "flags": flags, "desc": desc[:320], "sold": sold, "uo2": uo, "v": 2,
            "lat": float(la.group(1)) if la else None, "lng": float(lo.group(1)) if lo else None, "region": region}

# ---- NSW planning: zoning and minimum lot size --------------------------------
NSW_PLAN = "https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/ePlanning/Planning_Portal_Principal_Planning/MapServer"
def nsw_planning(lat, lng):
    out = {}
    q = urllib.parse.urlencode({"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false", "f": "json"})
    for layer, kind in ((19, "zone"), (22, "lot")):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{NSW_PLAN}/{layer}/query?{q}", headers={"User-Agent": UA}), timeout=30) as r:
                feats = json.loads(r.read().decode()).get("features") or []
        except Exception:
            continue
        if not feats: continue
        a = feats[0]["attributes"]
        if kind == "zone":
            out.update(zone=a.get("SYM_CODE") or a.get("LABEL"), zone_name=a.get("LAY_CLASS"), lga=(a.get("LGA_NAME") or "").title())
        elif a.get("LOT_SIZE"):
            v = float(a["LOT_SIZE"]); u = (a.get("UNITS") or "").lower()
            out["minlot_ha"] = round(v / 10000 if "m" in u and "ha" not in u else v, 3)
        time.sleep(0.3)
    return out

# ---- VIC planning: zone from VicPlan; minimum lot = the state default for that zone ----
VIC_PLAN = "https://plan-gis.mapshare.vic.gov.au/arcgis/rest/services/Planning/Vicplan_PlanningSchemeZones/MapServer/0/query"
VIC_DEFAULT_HA = {"FZ": 40, "RCZ": 40, "GWZ": 40, "GWAZ": 8, "RAZ": 40, "RLZ": 8, "LDRZ": 0.4}
def vic_planning(lat, lng):
    q = urllib.parse.urlencode({"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": "ZONE_CODE,ZONE_DESCRIPTION,LGA",
                                "returnGeometry": "false", "f": "json"})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{VIC_PLAN}?{q}", headers={"User-Agent": UA}), timeout=30) as r:
            feats = json.loads(r.read().decode()).get("features") or []
    except Exception:
        return {}
    time.sleep(0.3)
    if not feats: return {}
    a = feats[0]["attributes"]; code = a.get("ZONE_CODE") or ""
    out = {"zone": code, "zone_name": (a.get("ZONE_DESCRIPTION") or "").title(), "lga": (a.get("LGA") or "").title()}
    base = re.match(r"[A-Z]+", code)
    if base and base.group(0) in VIC_DEFAULT_HA:
        out["minlot_ha"] = VIC_DEFAULT_HA[base.group(0)]; out["minsrc"] = "vicdefault"
    return out

def _arc_point(url, lat, lng, fields):
    q = urllib.parse.urlencode({"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "false", "f": "json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{url}/query?{q}", headers={"User-Agent": UA}), timeout=30) as r:
                d = json.loads(r.read().decode())
            if "error" in d: raise ValueError(d["error"])
            feats = d.get("features") or []
            time.sleep(0.3)
            return feats[0]["attributes"] if feats else None
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None

# ---- TAS: Tasmanian Planning Scheme zone; lot size from the State Planning Provisions ----
TAS_PLAN = "https://services.thelist.tas.gov.au/arcgis/rest/services/Public/PlanningOnline/MapServer/13"
def tas_planning(lat, lng):
    a = _arc_point(TAS_PLAN, lat, lng, "LPS,ZONE,ZONESUBGRP")
    if not a: return {}
    z = (a.get("ZONE") or "").strip()
    out = {"zone": z, "zone_name": z, "lga": re.sub(r"\s*Local Provisions? Schedule", "", a.get("LPS") or "").strip()}
    rl = re.match(r"Rural Living\s*(?:Zone)?\s*([ABCD])", z + " " + (a.get("ZONESUBGRP") or ""), re.I)
    if rl: out.update(minlot_ha={"A": 1, "B": 2, "C": 5, "D": 10}[rl.group(1).upper()], minsrc="tasdefault")
    elif re.match(r"Rural\b", z): out.update(minlot_ha=40, minsrc="tasdefault")
    elif z.startswith("Landscape Conservation"): out.update(minlot_ha=50, minsrc="tasdefault")
    elif z.startswith("Agricultur"): out["nosplit"] = "Agriculture zone: Tasmania only allows subdivision here in special cases."
    return out

# ---- WA: local planning scheme zone; WA policy is against splitting farmland ----
WA_PLAN = "https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Property_and_Planning/MapServer/112"
def wa_planning(lat, lng):
    a = _arc_point(WA_PLAN, lat, lng, "zone,lga,scheme_nam")
    if not a: return {}
    z = (a.get("zone") or "").strip()
    out = {"zone": z, "zone_name": z, "lga": (a.get("lga") or "").strip()}
    zl = z.lower()
    if "smallholding" in zl: out.update(minlot_ha=4, minsrc="waguide")
    elif "rural residential" in zl or "rural living" in zl: out.update(minlot_ha=1, minsrc="waguide")
    elif re.search(r"rural|farm|agricult|general farming", zl):
        out["nosplit"] = "WA planning policy is against splitting rural and farming land into smaller lots."
    return out

# ---- fair-price model --------------------------------------------------------
ASK_TO_SALE = float(os.environ.get("ACREAGE_ASK_TO_SALE", "0.82"))
STATION_ACRES = 20_000   # bigger holdings are mostly pastoral stations: priced as their own market

def solve(XtX, Xty):
    n = len(Xty); M = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        d = M[i][i] or 1e-9
        for j in range(i, n + 1): M[i][j] /= d
        for r in range(n):
            if r != i and M[r][i]:
                f = M[r][i]
                for j in range(i, n + 1): M[r][j] -= f * M[i][j]
    return [M[i][n] for i in range(n)]

def fit(rows):
    """Size and house effects estimated WITHIN districts (3-digit postcode), so location
    doesn't distort them: log(price) ~ b*log(acres) + h*house after removing each district's mean."""
    rows = [r for r in rows if r["a"] < STATION_ACRES]
    g = {}
    for r in rows: g.setdefault(r["pc"][:3], []).append(r)
    sxx = sxh = shh = sxy = shy = 0.0
    for rs in g.values():
        if len(rs) < 2: continue
        mx = statistics.fmean(math.log(r["a"]) for r in rs); mh = statistics.fmean(1.0 if r["house"] else 0.0 for r in rs)
        my = statistics.fmean(math.log(r["p"]) for r in rs)
        for r in rs:
            x = math.log(r["a"]) - mx; h = (1.0 if r["house"] else 0.0) - mh; y = math.log(r["p"]) - my
            sxx += x * x; sxh += x * h; shh += h * h; sxy += x * y; shy += h * y
    det = sxx * shh - sxh * sxh or 1e-9
    bb = (sxy * shh - shy * sxh) / det; hh = (shy * sxx - sxy * sxh) / det
    return {"b": max(0.3, min(0.95, bb)), "h": max(0.1, min(1.2, hh))}

FARM_TYPES = ("Cropping", "Livestock", "Mixed Farming", "Dairy", "Horticulture", "Viticulture", "Specialist")
def kind(r):
    """house = has a home; bush = bare bush/scrub; farm = working farmland; life = other bare lifestyle land."""
    if r.get("house") is True: return "house"
    farm = any(t in (r.get("type") or "") for t in FARM_TYPES)
    if "bush" in (r.get("feats") or []) and not farm: return "bush"
    return "farm" if farm else "life"

def km(a, b):
    """Distance in km between two blocks with coordinates, else None."""
    if not (a.get("lat") and b.get("lat")): return None
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))

def comps_for(subj, pool, model, k=12):
    """Most similar priced blocks: nearest first (by distance when both have map points,
    else by postcode district), then wider rings, then the state."""
    a = subj["a"]
    def ring(d_max, pc_len):
        def test(c):
            d = km(subj, c)
            if d is not None: return d <= d_max
            return pc_len and c["pc"][:pc_len] == subj["pc"][:pc_len]
        return test
    if subj.get("lat"):
        levels = [("near50", ring(50, 0), 1 / 3, 3), ("near120", ring(120, 3), 1 / 3, 3),
                  ("near250", ring(250, 2), 1 / 4, 4), ("state", lambda c: c["s"] == subj["s"], 1 / 4, 4)]
    else:
        levels = [("district", lambda c: c["pc"][:3] == subj["pc"][:3], 1 / 3, 3),
                  ("area", lambda c: c["pc"][:2] == subj["pc"][:2], 1 / 4, 4),
                  ("state", lambda c: c["s"] == subj["s"], 1 / 4, 4)]
    sk = kind(subj)
    for name, test, lo, hi in levels:
        cs = [c for c in pool if c["id"] != subj["id"] and lo <= c["a"] / a <= hi and test(c)]
        same = [c for c in cs if kind(c) == sk]
        use = same if len(same) >= 4 else cs
        if len(use) >= 4 or name == "state":
            def key(c):  # nearest in size and distance, same house status and kind, sales count more
                d = km(subj, c)
                far = (d / 150) if d is not None else (0 if c["pc"][:3] == subj["pc"][:3] else 0.3)
                return abs(math.log(c["a"] / a)) + (0 if c["house"] == subj.get("house") else 0.4) + min(far, 1) + \
                       (0 if kind(c) == sk else 0.5) - (0.15 if c.get("is_sold") else 0)
            # the same block listed twice (two agents) is not a comparison
            use = [c for c in use if not (c["p"] == subj.get("p") and abs(c["a"] - a) < 0.5 and c["pc"] == subj["pc"])]
            return sorted(use, key=key)[:k], name
    return [], "state"

def pctl(v, q):
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)

def price_one(r, model, pool):
    if r["a"] >= STATION_ACRES: return None, [], ""
    cs, level = comps_for(r, pool, model)
    if len(cs) < 3: return None, [], level
    hs = 1.0 if r.get("house") else 0.0
    # asking prices sit above what blocks sell for; scale them down (tuned with backtest.py)
    implied = [c["p"] * (1.0 if c.get("is_sold") else ASK_TO_SALE) * (r["a"] / c["a"]) ** model["b"] * math.exp(model["h"] * (hs - float(c["house"]))) for c in cs]
    fair = statistics.median(implied)
    r["_lo"], r["_hi"] = pctl(implied, 0.25), pctl(implied, 0.75)
    f = set(r.get("feats", [])); g = set(r.get("flags", []))
    mult = 1.0
    if "creek" in f: mult *= 1.05
    if "power" in f: mult *= 1.04
    if "covenant" in g: mult *= 0.75
    if "nobuild" in g: mult *= 0.70
    if "lease" in g: mult *= 0.80
    if "access" in g: mult *= 0.85
    if "flood" in g: mult *= 0.93
    r["_lo"] *= mult; r["_hi"] *= mult
    return fair * mult, cs, level

def load_sold():
    """Recent sales from sold-cache.json (scan_sold.py), shaped like listings so they can be comparisons."""
    try: cache = json.load(open(os.path.join(HERE, "sold-cache.json")))
    except Exception: return []
    out = []
    for x in cache.values():
        if x.get("bad") or not x.get("p") or not x.get("a") or not x.get("s"): continue
        tags = " ".join(x.get("tags") or []).lower()
        out.append({"id": "s" + str(x["id"]), "s": x["s"], "pc": x.get("pc") or "000", "sub": x.get("sub"), "region": x.get("region"),
                    "a": x["a"], "p": x["p"], "house": (x.get("bed") or 0) > 0, "bush": "bush" in tags,
                    "feats": ["bush"] if "bush" in tags and not (x.get("bed") or 0) else [], "type": x.get("type") or "",
                    "sold": x.get("sold"), "is_sold": True, "u": x.get("u"), "lat": x.get("lat"), "lng": x.get("lng")})
    # Farm Property sales (scan_fp_sold.py); skip ones already seen on Farmbuy (same postcode, size and price)
    try: fp = json.load(open(os.path.join(HERE, "fp-sold-cache.json")))
    except Exception: fp = {}
    seen = {(o["pc"], round(o["a"]), round(o["p"], -4)) for o in out}
    for x in fp.values():
        if not x.get("price") or not x.get("acres") or not x.get("state"): continue
        key = (x.get("postcode") or "000", round(x["acres"]), round(x["price"], -4))
        if key in seen: continue
        seen.add(key)
        ty = (x.get("type") or "").strip()
        ty = {"Grazing": "Livestock", "Mixed": "Mixed Farming", "Irrigation": "Cropping", "Specialty": "Specialist"}.get(ty, ty)
        out.append({"id": "f" + x["id"], "s": x["state"], "pc": x.get("postcode") or "000",
                    "sub": re.sub(r"^.*?\b(?:road|rd|lane|ln|highway|hwy|street|st|drive|dr|track|way)\b\s*", "", x.get("address") or "", flags=re.I).strip() or x.get("address"),
                    "region": None, "a": x["acres"], "p": x["price"], "house": (x.get("bed") or 0) > 0, "bush": False,
                    "feats": [], "type": ty, "sold": x.get("date"), "is_sold": True, "u": x["url"], "src": "fp",
                    "lat": x.get("lat"), "lng": x.get("lng")})
    # NSW government sales (fetch_nsw_map.py + import_nsw_vg.py): the last two years only
    try: nsw = json.load(open(os.path.join(HERE, "nsw-sales.json")))
    except Exception: nsw = []
    cut = (datetime.now(timezone.utc).date() - timedelta(days=730)).isoformat()
    seen = {(o["pc"], round(o["a"]), round(o["p"], -4)) for o in out}
    for x in nsw:
        if x["date"] < cut or not x.get("lat"): continue
        key = (x["pc"], round(x["a"]), round(x["p"], -4))
        if key in seen: continue
        seen.add(key)
        out.append({"id": "n" + x["pid"], "s": "NSW", "pc": x["pc"], "sub": x["sub"], "region": x.get("region"), "lga": x.get("lga"),
                    "a": x["a"], "p": x["p"], "house": 0.5, "bush": False, "feats": [], "type": "", "sold": x["date"], "is_sold": True,
                    "u": "", "src": "nsw", "addr": x.get("addr"), "lat": x["lat"], "lng": x["lng"]})
    return out

# Farmbuy region -> Bendigo Bank farmland report region, used when a block has no council growth figure
FB_TO_BR = {
    "NSW": {"Hunter": "Hunter", "Riverina": "Riverina Murray", "South West Slopes": "Riverina Murray",
            "Central Tablelands": "Central West", "Central West Slopes & Plains": "Central West",
            "Mid North Coast": "North Coast", "Northern Rivers": "North Coast", "Southern Tablelands": "South East",
            "South Coast": "South East", "Snowy Mountains": "South East", "Upper Western": "Far West", "Lower Western": "Far West"},
    "VIC": {"Central": "Central", "East Gippsland": "East Gippsland", "Mallee": "Mallee", "South West": "South West",
            "Wimmera": "Wimmera", "North East": "Ovens Murray", "Northern Country": "Goulburn"},
    "SA": {"Eastern Eyre Peninsula": "Eyre Peninsula", "Lower Eyre Peninsula": "Eyre Peninsula", "West Coast": "Eyre Peninsula",
           "Kangaroo Island": "Kangaroo Island", "Lower South East": "Lower South East", "Murraylands": "Murray & Mallee",
           "Riverland": "Murray & Mallee", "Mid North": "Yorke & Mid-North", "Yorke Peninsula": "Yorke & Mid-North",
           "Mount Lofty Ranges": "Adelaide & Fleurieu", "Flinders": "North", "North East Pastoral": "North"},
    "WA": {"Great Southern": "Great Southern", "South West": "South West", "Lower West": "South West"},
    "TAS": {"North West Coast": "North West", "Western": "North West", "Central North": "Northern", "North East": "Northern",
            "Midlands": "Northern", "South East": "South", "Upper Derwent Valley": "South"},
}
LGA_SUFFIX = re.compile(r"\s+(Regional|City|Shire|Aboriginal Shire|Town|Council)$", re.I)

_GL = None
def growth_lga(state, name):
    """The council's name as the Bendigo Bank farmland report spells it, or None if the report doesn't list it."""
    global _GL
    if _GL is None:
        try:
            h = json.loads(open(os.path.join(HERE, "history-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
            _GL = {(l["state"], l["lga"].upper()): l["lga"] for l in h["lgas"]}
        except Exception: _GL = {}
    n = name.upper()
    for c in (n, re.sub(r"^GREATER\s+", "", n), n.replace("LATROBE", "LA TROBE"), n.replace("MID COAST", "MID-COAST")):
        if (state, c) in _GL: return _GL[(state, c)]
    return None

def band_of(a):
    return "10-50" if a < 50 else "50-200" if a < 200 else "200+"

def fill_areas(rows, sold, scanned):
    """Give each block its council and region, then work out how busy each area's market is."""
    # postcode -> Farmbuy region, from every block and sale that has one
    pc_reg = {}
    for x in list(rows) + list(sold):
        if x.get("region"): pc_reg.setdefault((x["s"], x["pc"]), {}).setdefault(x["region"], 0); pc_reg[(x["s"], x["pc"])][x["region"]] += 1
    pc_reg = {k: max(v, key=v.get) for k, v in pc_reg.items()}
    # suburb -> council, from blocks with a planning lookup, plus the QLD government locality list
    sub_lga = {}
    for r in rows:
        if r.get("lga"): sub_lga.setdefault((r["s"], (r.get("sub") or "").upper()), r["lga"])
    try: qld = json.load(open(os.path.join(HERE, "qld-localities.json")))
    except Exception: qld = {}
    for r in rows:
        if not r.get("region"): r["region"] = pc_reg.get((r["s"], r["pc"]))
        if not r.get("lga"):
            g = sub_lga.get((r["s"], (r.get("sub") or "").upper()))
            if not g and r["s"] == "QLD": g = qld.get((r.get("sub") or "").upper())
            if g: r["lga"] = g
        if r.get("lga"):
            r["lga"] = LGA_SUFFIX.sub("", re.sub(r"^(Shire|City|Town|Municipality) of\s+", "", r["lga"])).strip()
            g = growth_lga(r["s"], r["lga"])
            if g: r["lga_g"] = g
        br = FB_TO_BR.get(r["s"], {}).get(r.get("region") or "")
        if br: r["br"] = br
    # market numbers per region
    end = scanned[:10]
    def days(d):
        try: return (datetime.fromisoformat(end) - datetime.fromisoformat(d[:10])).days
        except Exception: return None
    fp = {}
    try: fp = json.load(open(os.path.join(HERE, "fp-sold-cache.json")))
    except Exception: pass
    sc = {}
    try: sc = json.load(open(os.path.join(HERE, "sold-cache.json")))
    except Exception: pass
    A = {}
    def area(s, reg):
        return A.setdefault(s + "|" + reg, {"s": s, "region": reg, "forsale": 0, "fs_band": {}, "sold90": 0, "s90_band": {},
                                             "months": {}, "years": {}, "fp_sold": 0, "cuts": 0, "_ask": {}, "_sold": {}})
    for r in rows:
        if not r.get("region"): continue
        a = area(r["s"], r["region"]); b = band_of(r["a"])
        a["forsale"] += 1; a["fs_band"][b] = a["fs_band"].get(b, 0) + 1
        if r.get("drop"): a["cuts"] += 1
        if r.get("p") and r["a"] < STATION_ACRES: a["_ask"].setdefault(b, []).append(r["p"] / r["a"])
    for x in sc.values():   # Farmbuy sales: every one has the date it was marked sold
        if not x.get("region") or not x.get("a") or x["a"] < MIN_ACRES or not x.get("sold"): continue
        a = area(x["s"], x["region"]); dd = days(x["sold"]); b = band_of(x["a"])
        a["months"][x["sold"][:7]] = a["months"].get(x["sold"][:7], 0) + 1
        if dd is not None and 0 <= dd <= 90: a["sold90"] += 1; a["s90_band"][b] = a["s90_band"].get(b, 0) + 1
        if x.get("p") and x["a"] < STATION_ACRES: a["_sold"].setdefault(b, []).append(x["p"] / x["a"])
    for x in fp.values():   # Farm Property: older sales, mostly without a date
        reg = pc_reg.get((x.get("state"), x.get("postcode")))
        if not reg or (x.get("acres") or 0) < MIN_ACRES: continue
        a = area(x["state"], reg); a["fp_sold"] += 1
        if x.get("date"): a["years"][x["date"][:4]] = a["years"].get(x["date"][:4], 0) + 1
        if x.get("price") and x["acres"] < STATION_ACRES: a["_sold"].setdefault(band_of(x["acres"]), []).append(x["price"] / x["acres"])
    for a in A.values():
        per_month = a["sold90"] / 3
        a["supply"] = round(a["forsale"] / per_month, 1) if a["sold90"] >= 3 else None
        a["pace"] = None if a["supply"] is None else "busy" if a["supply"] <= 6 else "normal" if a["supply"] <= 12 else "slow"
        gaps, w = 0.0, 0
        for b in a["_ask"]:
            if len(a["_ask"][b]) >= 5 and len(a["_sold"].get(b, [])) >= 5:
                n = min(len(a["_ask"][b]), len(a["_sold"][b]))
                gaps += n * statistics.median(a["_sold"][b]) / statistics.median(a["_ask"][b]); w += n
        a["sold_vs_ask"] = round(gaps / w, 2) if w else None
        a["months"] = dict(sorted(a["months"].items()))
        a["years"] = dict(sorted(a["years"].items()))
        del a["_ask"], a["_sold"]
    return A

def fp_listings(rows):
    """Farm Property listings (scan_fp_sale.py) that Farmbuy doesn't already have."""
    try: fp = json.load(open(os.path.join(HERE, "fp-sale-cache.json")))
    except Exception: return []
    have = {}
    for r in rows: have.setdefault(r["pc"], []).append(r["a"])
    out = []
    for x in fp.values():
        if not x.get("live") or not x.get("acres") or x["acres"] < MIN_ACRES or x.get("state") not in STATES: continue
        pc = x.get("postcode") or "000"
        if any(abs(a - x["acres"]) <= max(1.0, 0.03 * a) for a in have.get(pc, [])): continue
        desc = x.get("desc") or ""; low = desc.lower()
        feats = [k for k, _, rx, _ in FEATURES if re.search(rx, low)]
        flags = [k for k, _, rx, _ in FLAGS if re.search(rx, low)]
        if "power" in feats and re.search(r"no power|no electricity", low): feats.remove("power")
        ty = (x.get("type") or "").strip()
        ty = {"Grazing": "Livestock", "Mixed": "Mixed Farming", "Irrigation": "Cropping", "Specialty": "Specialist"}.get(ty, ty)
        addr = x.get("address") or ""
        sub = re.sub(r"^.*?\b(?:road|rd|lane|ln|highway|hwy|street|st|drive|dr|track|way|avenue|ave)\b\.?\s*", "", addr, flags=re.I).strip() or addr
        pt = x.get("pt") or ""
        status = (x.get("status") or "").lower()
        out.append({"id": "fp" + x["id"], "s": x["state"], "sub": sub.title() if sub.isupper() else sub, "addr": f"{addr} {x['state']} {pc}",
                    "pc": pc, "a": round(x["acres"], 1), "pt": pt, "p": parse_price(pt),
                    "uo": "under" in status or "under offer" in pt.lower() or "under contract" in pt.lower(),
                    "ct": x.get("status") or "", "type": ty, "u": x["url"], "ag": x.get("agent") or "", "bed": x.get("bed") or 0,
                    "feats": feats, "flags": flags, "desc": desc[:320] if desc else None, "sold": "sold" in status,
                    "lat": x.get("lat"), "lng": x.get("lng"), "src": "fp"})
        have.setdefault(pc, []).append(x["acres"])
    return out

def track_history(rows, scanned, sold_by_id):
    """Keep first-seen date, price changes and gone-from-market dates across daily scans."""
    hp = os.path.join(HERE, "listings-history.json")
    try: hist = json.load(open(hp))
    except Exception: hist = {}
    today = scanned[:10]; seen = set()
    for r in rows:
        h = hist.setdefault(r["id"], {"first": today, "prices": []})
        h["last"] = today; h.pop("gone", None); seen.add(r["id"])
        if r["p"] and (not h["prices"] or h["prices"][-1][1] != r["p"]): h["prices"].append([today, r["p"]])
        h.update(sub=r["sub"], s=r["s"], a=r["a"], u=r["u"])
        r["first"] = h["first"]
        if len(h["prices"]) > 1 and h["prices"][-1][1] < h["prices"][-2][1]:
            r["drop"] = [h["prices"][-2][1], h["prices"][-1][1], h["prices"][-1][0]]
    for pid, h in hist.items():
        if pid not in seen and "gone" not in h: h["gone"] = today
        sx = sold_by_id.get("s" + pid)
        if sx: h["sold_price"] = sx["p"]; h["sold_date"] = sx.get("sold")
    json.dump(hist, open(hp, "w"))

def quality(r):
    q = 50
    for k, _, _, pts in FEATURES:
        if k in r.get("feats", []): q += pts
    for k, _, _, pen in FLAGS:
        if k in r.get("flags", []): q -= pen
    if r["a"] >= 500: q += 3
    return max(5, min(100, q))

def verdict(p, lo, hi):
    """Judge the asking price against the normal range (middle half) of similar blocks."""
    if p < lo * 0.5: return "why"
    if p <= lo * 0.85: return "great"
    if p <= lo: return "good"
    if p <= hi: return "fair"
    if p <= hi * 1.2: return "high"
    return "over"

def main():
    details = "--no-details" not in sys.argv
    pth = os.path.join(HERE, "acreage-data.js")
    if "--rescore" in sys.argv:
        old = json.loads(open(pth).read().split("=", 1)[1].rstrip().rstrip(";"))
        rows = old["listings"]
        for r in rows:
            for k in ("fair", "ratio", "v", "offer", "walk", "comps", "cids", "lvl", "lo", "hi", "nsold", "drop"): r.pop(k, None)
            r["flags"] = [f for f in r.get("flags") or [] if f != "station"]
            if r.get("pt"): r["p"] = parse_price(r["pt"])
            low = ((r.get("desc") or "") + " " + (r.get("pt") or "")).lower()   # pick up flag rules added since the scan
            for k, _, rx, _ in FLAGS:
                if re.search(rx, low) and k not in r["flags"]: r["flags"].append(k)
        return finish(rows, old["scanned"], keep_prev=False)
    raw = []
    for code in STATES:
        print("Searching", code)
        for c in search_state(code):
            c["_s"] = code; raw.append(c)
    rows, seen = [], set()
    for c in raw:
        if c.get("id") in seen: continue
        seen.add(c.get("id"))
        a = acres_of(c)
        if not a or a < MIN_ACRES: continue
        ad = c.get("address", {})
        st = ad.get("state") or c["_s"]
        if st not in STATES: st = c["_s"]
        rows.append({
            "id": c.get("id"), "s": st, "sub": html.unescape(ad.get("suburb") or "").strip().title(),
            "addr": html.unescape(ad.get("full") or "").replace("&comma;", ","), "pc": ad.get("postcode") or "000",
            "a": round(a, 1), "pt": html.unescape(c.get("priceText") or "").strip(), "p": parse_price(c.get("priceText")),
            "uo": bool(c.get("underOffer")) or "under offer" in (c.get("priceText") or "").lower() or "under contract" in (c.get("contractText") or "").lower(),
            "ct": c.get("contractText") or "", "type": ", ".join(c.get("types") or []),
            "u": c.get("url"), "ag": c.get("realestate") or "",
            "bed": int(float((c.get("meta") or {}).get("bed") or 0)),
        })
    print(len(rows), "listings over", MIN_ACRES, "acres;", sum(1 for r in rows if r["p"]), "with a price")
    if details:
        cp = os.path.join(HERE, "details-cache.json")
        try: cache = json.load(open(cp))
        except Exception: cache = {}
        todo = [r for r in rows if r["p"] and r["p"] <= DETAIL_MAX]
        print("Reading", len(todo), "detail pages (", sum(1 for r in todo if r["id"] in cache), "cached )")
        for i, r in enumerate(todo, 1):
            d = cache.get(r["id"])
            if not d or d.get("v") != 2: d = detail(r["u"])
            if d: cache[r["id"]] = d
            if d:
                r.update({k: v for k, v in d.items() if k not in ("uo2", "v")})
                if d.get("uo2"): r["uo"] = True
            if i % 25 == 0: print(f"  {i}/{len(todo)}", flush=True); json.dump(cache, open(cp, "w"))
        json.dump(cache, open(cp, "w"))
        extra = fp_listings(rows)
        print("Farm Property listings not on Farmbuy:", len(extra), flush=True)
        rows += extra
        pp = os.path.join(HERE, "planning-cache.json")
        try: plan = json.load(open(pp))
        except Exception: plan = {}
        look = {"NSW": nsw_planning, "VIC": vic_planning, "TAS": tas_planning, "WA": wa_planning}
        todo_p = [r for r in rows if r["s"] in look and r.get("lat") and not r.get("approx")]
        print("Planning lookups (NSW, VIC, TAS, WA):", sum(1 for r in todo_p if not plan.get(r["id"])), "new", flush=True)
        for r in todo_p:
            if not plan.get(r["id"]):
                got = look[r["s"]](r["lat"], r["lng"])
                if got: plan[r["id"]] = got
            r.update(plan.get(r["id"]) or {})
        json.dump(plan, open(pp, "w"))
    return finish(rows, datetime.now(timezone.utc).isoformat(timespec="minutes"))

def match_rules(x, r):
    """Same rules as the page's "My rules" panel (alert-rules.json)."""
    f, c = x.get("feats") or [], x.get("chk") or {}
    if r.get("maxPrice") and not (x.get("p") and x["p"] <= r["maxPrice"]): return False
    if r.get("minAcres") and x["a"] < r["minAcres"]: return False
    if r.get("maxAcres") and x["a"] > r["maxAcres"]: return False
    if r.get("maxTownKm") and not (x.get("town") and x["town"][1] * 1.3 <= r["maxTownKm"]): return False
    if r.get("maxCityKm") and not (x.get("city") and x["city"][1] * 1.3 <= r["maxCityKm"]): return False
    if r.get("minRain") and not (x.get("rain") and x["rain"] >= r["minRain"]): return False
    if r.get("states") and x["s"] not in r["states"].split(): return False
    if r.get("house") == "yes" and not x.get("house"): return False
    if r.get("house") == "no" and x.get("house"): return False
    if r.get("deal") == "good" and x.get("v") not in ("good", "great"): return False
    if r.get("deal") == "great" and x.get("v") != "great": return False
    if r.get("water") and not any(k in f for k in ("creek", "river", "dam", "bore")): return False
    if r.get("noFlood") and (c.get("flood") or "flood" in (x.get("flags") or [])): return False
    if r.get("noVeg") and c.get("veg"): return False
    if r.get("noFire") and (c.get("fire") or c.get("burnt")): return False
    if r.get("stay") and not x.get("stay"): return False
    if r.get("split") and not (x.get("lots") or 0) >= 2: return False
    return True

def finish(rows, scanned, keep_prev=True):
    try: cent = json.load(open(os.path.join(HERE, "suburb-centroids.json")))
    except Exception: cent = {}
    try: catches = json.load(open(os.path.join(HERE, "catch-cache.json")))
    except Exception: catches = {}
    for r in rows:
        ck = catches.get(str(r["id"]))
        if ck: r["chk"] = {k: v for k, v in ck.items() if k != "v" and v}
    # roughly when each Farmbuy block was listed (build_listed.py), and how many times its price was cut
    try: curve = json.load(open(os.path.join(HERE, "listed-curve.json")))
    except Exception: curve = []
    try: hist = json.load(open(os.path.join(HERE, "listings-history.json")))
    except Exception: hist = {}
    try: fps = json.load(open(os.path.join(HERE, "fp-sale-cache.json")))
    except Exception: fps = {}
    import bisect
    cids = [c[0] for c in curve]
    today = scanned[:10]
    for r in rows:
        sid = str(r["id"]); listed = None
        if sid.isdigit() and cids:
            i = bisect.bisect_left(cids, int(sid))
            if i < len(curve): listed = curve[i][1]
        elif sid.startswith("fp"):
            listed = (fps.get(sid[2:]) or {}).get("first")
        h = hist.get(sid) or {}
        if h.get("first") and (not listed or h["first"] < listed): listed = h["first"]
        if listed:
            r["listed"] = listed
            try: r["dom"] = (datetime.fromisoformat(today) - datetime.fromisoformat(listed)).days
            except Exception: pass
        pr = [p for _, p in (h.get("prices") or [])]
        fpp = (fps.get(sid[2:]) or {}).get("prices") if sid.startswith("fp") else None
        r["cuts"] = sum(1 for a, b in zip(pr, pr[1:]) if b < a) + (len(fpp) if fpp else 0)
    for r in rows:   # no map point on the listing: use the suburb's centre, marked as approximate
        if not r.get("lat") or r.get("approx"):
            c = cent.get("%s|%s" % (r["s"], (r.get("sub") or "").upper()))
            if c: r["lat"], r["lng"], r["approx"] = c[0], c[1], 1
    # nearest town of 1,000+ people, nearest city of 100,000+, nearest power substation (straight line)
    try: places = json.load(open(os.path.join(HERE, "ref", "places.json")))
    except Exception: places = {}
    def nearest(r, pts):
        best = None
        for p in pts:
            if abs(p[0] - r["lat"]) > 3 or abs(p[1] - r["lng"]) > 3.5: continue
            d = km(r, {"lat": p[0], "lng": p[1]})
            if best is None or d < best[0]: best = (d, p)
        return best
    if places:
        cities = [t for t in places["town"] if t[3]]
        for r in rows:
            if not r.get("lat"): continue
            t = nearest(r, places["town"])
            if t: r["town"] = [t[1][2], round(t[0])]
            c = min(((km(r, {"lat": p[0], "lng": p[1]}), p) for p in cities), key=lambda x: x[0])
            r["city"] = [c[1][2], round(c[0])]
            sb = nearest(r, places.get("sub") or [])
            if sb: r["subst"] = [sb[1][2], round(sb[0], 1), sb[1][3]]
    # average yearly rainfall (Bureau of Meteorology 1991-2020 grid, ref/bom-rainfall-annual.zip)
    try:
        import zipfile
        z = zipfile.ZipFile(os.path.join(HERE, "ref", "bom-rainfall-annual.zip"))
        lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
        hd = {l.split()[0].lower(): float(l.split()[1]) for l in lines[:6]}
        grid = lines[6:]
        for r in rows:
            if not r.get("lat"): continue
            col = round((r["lng"] - hd["xllcenter"]) / hd["cellsize"]); row = int(hd["nrows"]) - 1 - round((r["lat"] - hd["yllcenter"]) / hd["cellsize"])
            if 0 <= row < len(grid):
                vals = grid[row].split()
                if 0 <= col < len(vals) and float(vals[col]) < hd["nodata_value"] - 1: r["rain"] = round(float(vals[col]))
    except Exception as e: print("rainfall grid:", e)
    # income evidence: short stays nearby (Inside Airbnb) and house rents by postcode (state bond data)
    try: bnb = json.load(open(os.path.join(HERE, "ref", "airbnb.json")))["rows"]
    except Exception: bnb = []
    try: rents = json.load(open(os.path.join(HERE, "ref", "rents.json")))["rents"]
    except Exception: rents = {}
    cells = {}
    for b in bnb: cells.setdefault((round(b[0]), round(b[1])), []).append(b)
    for r in rows:
        rt = rents.get("%s|%s" % (r["s"], r["pc"]))
        if rt: r["rent"] = rt
        if not r.get("lat") or not bnb: continue
        near = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for b in cells.get((round(r["lat"]) + dy, round(r["lng"]) + dx), []):
                    d = km(r, {"lat": b[0], "lng": b[1]})
                    if d <= 40: near.append((d, b))
        rural = [b for d, b in near if b[5]]
        use, kind = (rural, "cabins, cottages and farm stays") if len(rural) >= 5 else ([b for d, b in near if d <= 25], "whole homes")
        booked = [b for b in use if b[3] > 0]
        if len(use) >= 5 and len(booked) >= 3:
            r["stay"] = {"n": len(use), "kind": kind, "night": round(statistics.median(b[2] for b in use)),
                         "nights": round(statistics.median(b[3] for b in booked)), "rev": round(statistics.median(b[4] for b in booked), -2),
                         "top": round(pctl(sorted(b[4] for b in booked), 0.75), -2)}
    for r in rows:
        r["house"] = r.get("bed", 0) > 0
        if r["house"] and "house" not in r.setdefault("feats", []): r["feats"].insert(0, "house")
        if not r["house"] and "house" in r.get("feats", []): r["feats"].remove("house")
        if r["a"] >= STATION_ACRES: r.setdefault("flags", []).append("station")
        if r.get("minlot_ha"):
            lots = int((r["a"] / 2.471) // r["minlot_ha"])
            r["lots"] = lots if lots >= 2 else 0
    priced = [r for r in rows if r["p"]]
    model = fit(priced)
    sold = load_sold()
    pool = [r for r in priced if r["a"] < STATION_ACRES and not r.get("sold")] + \
           [x for x in sold if x["a"] >= MIN_ACRES * 0.5 and x["a"] < STATION_ACRES]
    for r in rows:
        fair, cs, level = price_one(r, model, pool)
        r["fair"] = round(fair, -3) if fair else None; r["comps"] = len(cs); r["lvl"] = level
        r["cids"] = [c["id"] for c in cs[:6]]; r["q"] = quality(r)
        r["nsold"] = sum(1 for c in cs if c.get("is_sold"))
        if r["p"] and fair:
            # fair = likely sale price. The verdict compares asking with what similar blocks usually ASK
            k = ASK_TO_SALE
            ratio = r["p"] * k / fair
            r["ratio"] = round(ratio, 3); r["v"] = verdict(r["p"] * k, r["_lo"], r["_hi"])
            r["lo"] = round(r["_lo"] / k, -3); r["hi"] = round(r["_hi"] / k, -3)
            if level == "state" and r["v"] == "great": r["v"] = "good"   # few nearby comparisons: soften
            r["offer"] = round(min(r["p"], fair) * 0.93, -3)
            r["walk"] = round(min(r["p"], fair * 1.08), -3)
        r["ppa"] = round(r["p"] / r["a"]) if r["p"] else None
        r.pop("_lo", None); r.pop("_hi", None)
    track_history(rows, scanned, {x["id"]: x for x in sold})
    areas = fill_areas(rows, [x for x in sold if x.get("src") != "nsw"], scanned)
    used = {c for r in rows for c in r.get("cids") or []}
    # state medians for the guide
    guide = {}
    for s in STATES:
        rs = [r for r in priced if r["s"] == s]
        if rs:
            guide[s] = {"n": len(rs), "med_ppa": round(statistics.median(r["p"] / r["a"] for r in rs)),
                        "med_price": round(statistics.median(r["p"] for r in rs), -3),
                        "under300": sum(1 for r in rs if r["p"] <= 300_000)}
    data = {"scanned": scanned, "source": "farmbuy.com",
            "min_acres": MIN_ACRES, "ask_to_sale": ASK_TO_SALE, "max_price": MAX_PRICE, "guide": guide,
            "model": {"b": round(model["b"], 4), "h": round(model["h"], 4)}, "areas": areas,
            "alert_rules": (json.load(open(os.path.join(HERE, "alert-rules.json"))) if os.path.exists(os.path.join(HERE, "alert-rules.json")) else {}),
            "latest": (json.load(open(os.path.join(HERE, "latest-values.json"))) if os.path.exists(os.path.join(HERE, "latest-values.json")) else {}),
            "nsw": (json.load(open(os.path.join(HERE, "nsw-growth.json"))) if os.path.exists(os.path.join(HERE, "nsw-growth.json")) else {}),
            "qbig": (json.load(open(os.path.join(HERE, "qld-big-sales.json")))["sales"] if os.path.exists(os.path.join(HERE, "qld-big-sales.json")) else []),
            "sold": [{k: x.get(k) for k in ("id", "sub", "s", "pc", "region", "a", "p", "house", "bush", "sold", "u", "lat", "lng", "src", "addr")} for x in sold
                     if x["a"] >= MIN_ACRES and (x.get("src") != "nsw" or x["id"] in used)],
            "listings": rows}
    prev_ids = set()
    pth = os.path.join(HERE, "acreage-data.js")
    if os.path.exists(pth):
        try: prev_ids = {l["id"] for l in json.loads(open(pth).read().split("=", 1)[1].rstrip().rstrip(";"))["listings"]}
        except Exception: pass
    with open(pth, "w") as f:
        f.write("window.ACREAGE_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n")
    print("Wrote", pth)
    # optional ntfy alerts for new great/good deals under $350k
    topic = os.environ.get("ACREAGE_NTFY_TOPIC", "").strip()
    try: rules = json.load(open(os.path.join(HERE, "alert-rules.json")))   # "My rules" from the page (no secrets)
    except Exception: rules = {}
    if keep_prev and prev_ids and topic:
        for r in rows:
            if r["id"] not in prev_ids and (match_rules(r, rules) if rules else (r.get("v") in ("great", "good") and r["p"] and r["p"] <= 350_000)) and not r["uo"]:
                msg = f"{r['a']:.0f} ac {r['sub']} {r['s']} ${r['p']:,.0f} ({r['v']} deal)"
                try:
                    urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode(),
                                           headers={"Title": "New acreage bargain", "Click": r["u"]}), timeout=15)
                except Exception as e: print("alert failed", e)

if __name__ == "__main__":
    main()
