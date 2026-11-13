#!/usr/bin/env python3
"""Acreage Finder scanner.

Pulls every rural listing of 100+ acres (up to a price cap) from farmbuy.com for each
state, opens the detail page of the cheaper ones to read features, prices each block
against similar blocks, and writes acreage-data.js for acreage.html.

Run:  python3 scan_acreage.py            (full scan, ~10-20 min, polite 1.1s between requests)
      python3 scan_acreage.py --no-details   (faster, skips detail pages)
Optional deal alerts: put an ntfy topic name in ACREAGE_NTFY_TOPIC.txt next to this file.
"""
import json, re, sys, time, html, os, math, statistics, urllib.request, urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (AcreageFinder personal scanner)"
DELAY = 1.1          # farmbuy robots.txt asks for 1s between requests
MIN_ACRES = 100
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
    if re.search(r"\b(priced from|from \$|lots? from|per lot)", t): return None
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
    ("vendor",  "Vendor finance", r"vendor finance|terms available|deposit and|owner finance", 0),
]
FLAGS = [  # key, label, regex, quality penalty
    ("covenant", "Covenant / conservation agreement", r"covenant|heritage agreement|conservation agreement|trust for nature|biodiversity (stewardship|conservation)|land for wildlife agreement", 15),
    ("nobuild",  "No house allowed / no building entitlement", r"no (dwelling|building|house) (entitlement|rights|permit)|not (eligible|permitted) for a dwelling|cannot build|no ability to build", 20),
    ("lease",    "Leasehold, not freehold", r"leasehold|western lands lease|pastoral lease|perpetual lease|term lease", 12),
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
    return {"feats": feats, "flags": flags, "desc": desc[:320], "sold": sold, "uo2": uo}

# ---- fair-price model --------------------------------------------------------
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
    if r.get("house"): return "house"
    farm = any(t in (r.get("type") or "") for t in FARM_TYPES)
    if "bush" in (r.get("feats") or []) and not farm: return "bush"
    return "farm" if farm else "life"

def comps_for(subj, pool, model, k=12):
    """Most similar priced blocks: same district first, then wider area, then state."""
    a = subj["a"]
    def cands(test, lo, hi):
        return [c for c in pool if c["id"] != subj["id"] and test(c) and lo <= c["a"] / a <= hi]
    levels = [("district", lambda c: c["pc"][:3] == subj["pc"][:3], 1 / 3, 3),
              ("area", lambda c: c["pc"][:2] == subj["pc"][:2], 1 / 4, 4),
              ("state", lambda c: c["s"] == subj["s"], 1 / 4, 4)]
    picked, level = [], "state"
    for name, test, lo, hi in levels:
        cs = cands(test, lo, hi)
        sk = kind(subj)
        same = [c for c in cs if kind(c) == sk]
        use = same if len(same) >= 4 else cs
        if len(use) >= 4 or name == "state":
            def key(c):  # nearest in size, prefer same house status and same district
                return abs(math.log(c["a"] / a)) + (0 if c["house"] == subj.get("house") else 0.4) + (0 if c["pc"][:3] == subj["pc"][:3] else 0.3) + (0 if kind(c) == kind(subj) else 0.5)
            picked = sorted(use, key=key)[:k]; level = name
            break
    return picked, level

def pctl(v, q):
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)

def price_one(r, model, pool):
    if r["a"] >= STATION_ACRES: return None, [], ""
    cs, level = comps_for(r, pool, model)
    if len(cs) < 3: return None, [], level
    hs = 1.0 if r.get("house") else 0.0
    implied = [c["p"] * (r["a"] / c["a"]) ** model["b"] * math.exp(model["h"] * (hs - (1.0 if c["house"] else 0.0))) for c in cs]
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
            for k in ("fair", "ratio", "v", "offer", "walk", "comps", "cids", "lvl", "lo", "hi"): r.pop(k, None)
            r["flags"] = [f for f in r.get("flags") or [] if f != "station"]
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
            d = cache.get(r["id"]) or detail(r["u"])
            if d: cache[r["id"]] = d
            if d:
                r.update({k: v for k, v in d.items() if k not in ("uo2",)})
                if d.get("uo2"): r["uo"] = True
            if i % 25 == 0: print(f"  {i}/{len(todo)}", flush=True); json.dump(cache, open(cp, "w"))
        json.dump(cache, open(cp, "w"))
    return finish(rows, datetime.now(timezone.utc).isoformat(timespec="minutes"))

def finish(rows, scanned, keep_prev=True):
    for r in rows:
        r["house"] = r.get("bed", 0) > 0
        if r["house"] and "house" not in r.setdefault("feats", []): r["feats"].insert(0, "house")
        if not r["house"] and "house" in r.get("feats", []): r["feats"].remove("house")
        if r["a"] >= STATION_ACRES: r.setdefault("flags", []).append("station")
    priced = [r for r in rows if r["p"]]
    model = fit(priced)
    pool = [r for r in priced if r["a"] < STATION_ACRES and not r.get("sold")]
    for r in rows:
        fair, cs, level = price_one(r, model, pool)
        r["fair"] = round(fair, -3) if fair else None; r["comps"] = len(cs); r["lvl"] = level
        r["cids"] = [c["id"] for c in cs[:6]]; r["q"] = quality(r)
        if r["p"] and fair:
            ratio = r["p"] / fair
            r["ratio"] = round(ratio, 3); r["v"] = verdict(r["p"], r["_lo"], r["_hi"])
            r["lo"] = round(r["_lo"], -3); r["hi"] = round(r["_hi"], -3)
            if level == "state" and r["v"] == "great": r["v"] = "good"   # few nearby comparisons: soften
            r["offer"] = round(min(r["p"], fair) * 0.88, -3)
            r["walk"] = round(min(r["p"], fair * 1.05), -3)
        r["ppa"] = round(r["p"] / r["a"]) if r["p"] else None
        r.pop("_lo", None); r.pop("_hi", None)
    # state medians for the guide
    guide = {}
    for s in STATES:
        rs = [r for r in priced if r["s"] == s]
        if rs:
            guide[s] = {"n": len(rs), "med_ppa": round(statistics.median(r["p"] / r["a"] for r in rs)),
                        "med_price": round(statistics.median(r["p"] for r in rs), -3),
                        "under300": sum(1 for r in rs if r["p"] <= 300_000)}
    data = {"scanned": scanned, "source": "farmbuy.com",
            "min_acres": MIN_ACRES, "max_price": MAX_PRICE, "guide": guide,
            "model": {"b": round(model["b"], 4), "h": round(model["h"], 4)},
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
    tp = os.path.join(HERE, "ACREAGE_NTFY_TOPIC.txt")
    if keep_prev and prev_ids and os.path.exists(tp):
        topic = open(tp).read().strip()
        for r in rows:
            if r["id"] not in prev_ids and r.get("v") in ("great", "good") and r["p"] <= 350_000 and not r["uo"]:
                msg = f"{r['a']:.0f} ac {r['sub']} {r['s']} ${r['p']:,.0f} ({r['v']} deal)"
                try:
                    urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode(),
                                           headers={"Title": "New acreage bargain", "Click": r["u"]}), timeout=15)
                except Exception as e: print("alert failed", e)

if __name__ == "__main__":
    main()
