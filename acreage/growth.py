#!/usr/bin/env python3
"""Growth score: how likely a block is to grow in value and be a good place to own, out of 100.

Built for long-term buyers: location and things to do count most, then water and land, then the area's
momentum, then upside and price. Deal-breakers take points off. Adds to every block in acreage-data.js:
  gs   score 0-100            gx   the facts behind it (drive times, parks, wine, coast, growth...)
  gok  ticks the must-haves   gstar  a standout (ticks everything, high score, priced well)
Drive times are straight-line distance x 1.3 at 80 km/h: a guide, not a route.

  python3 -I growth.py
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)


def km(a, b, c, d):
    r = math.pi / 180
    h = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


class Grid:
    """Nearest point lookups without checking every point."""
    def __init__(self, pts, cell=1.0):
        self.cell, self.g = cell, {}
        for p in pts: self.g.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)

    def nearest(self, lat, lng, reach=3, fn=None):
        best = None
        cy, cx = int(lat // self.cell), int(lng // self.cell)
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                for p in self.g.get((cy + dy, cx + dx), []):
                    d = km(lat, lng, p[0], p[1])
                    if fn: d = fn(d, p)
                    if best is None or d < best[0]: best = (d, p)
        return best


def mins(k): return round(k * 1.3 / 80 * 60)   # rough drive minutes


def main():
    raw = open(P("acreage-data.js")).read()
    d = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    pl = json.load(open(P("ref/places.json")))
    life = json.load(open(P("ref/lifestyle.json")))
    pop = json.load(open(P("ref/lga-pop.json")))
    H = json.loads(open(P("history-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    lga_g = {(l["state"], l["lga"]): l for l in H["lgas"]}
    reg_g = {(r["state"], r["name"]): r for r in H["regions"] if not r["is_state"]}
    st_g = {r["state"]: r for r in H["regions"] if r["is_state"]}
    towns = Grid([t for t in pl["town"]]); sua = Grid(pl["sua"], 2.0)
    cities = Grid([t for t in pl["town"] if t[3]], 3.0); coast = Grid(pl["coast"], 1.0)
    parks = Grid(pl.get("parks", []), 1.0)
    wine = Grid([[w[1], w[2], w[0]] for w in life["wine"]], 2.0)
    hol = Grid([[h[1], h[2], h[0]] for h in life["holiday"]], 2.0)
    bnb = Grid([b for b in json.load(open(P("ref/airbnb.json")))["rows"] if b[5]], 1.0)
    park_edge = lambda dist, p: max(0.0, dist - math.sqrt(max(p[4], 1) / 100 / math.pi))   # centre to edge, area in ha
    for r in d["listings"]:
        for k in ("gs", "gx", "gok", "gstar"): r.pop(k, None)
        if not r.get("lat"): continue
        la, lo, x = r["lat"], r["lng"], {}
        t = towns.nearest(la, lo, 2); s = sua.nearest(la, lo, 2); c = cities.nearest(la, lo, 2)
        x["town"] = [t[1][2], mins(t[0])] if t else None
        x["sua"] = [s[1][2], mins(s[0])] if s else None
        x["city"] = [c[1][2], mins(c[0])] if c else None
        co = coast.nearest(la, lo, 2); x["coast"] = round(co[0]) if co else None
        pk = parks.nearest(la, lo, 1, park_edge); x["park"] = [pk[1][2], round(pk[0])] if pk else None
        w = wine.nearest(la, lo, 1); x["wine"] = [w[1][2], round(w[0])] if w and w[0] <= 80 else None
        h = hol.nearest(la, lo, 1); x["hol"] = [h[1][2], mins(h[0])] if h and h[0] <= 120 else None
        stays = 0
        if bnb.g:
            cy, cx = int(la), int(lo)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for b in bnb.g.get((cy + dy, cx + dx), []):
                        if km(la, lo, b[0], b[1]) <= 40: stays += 1
        x["stays"] = stays
        g = (lga_g.get((r["s"], r.get("lga_g") or "")) or reg_g.get((r["s"], r.get("br") or "")) or st_g.get(r["s"]) or {})
        x["land20"] = g.get("cagr20"); x["land10"] = g.get("cagr10")
        pp = pop.get(r["s"] + "|" + (r.get("lga") or "").upper())
        x["pop10"] = pp["g10"] if pp else None
        mk = (d.get("areas") or {}).get(r["s"] + "|" + (r.get("region") or "")) or {}
        x["pace"] = mk.get("pace")

        pts, why = 0, []
        def add(n, ok, txt):
            nonlocal pts
            pts += n if ok else 0
            why.append([1 if ok else 0, txt])
        # location and liveability (40)
        sm = x["sua"][1] if x["sua"] else 999
        add(12 if sm <= 20 else 9 if sm <= 40 else 5 if sm <= 60 else 2 if sm <= 90 else 0, sm <= 60,
            f"{x['sua'][0]} (10,000+ people) about {sm} min" if x["sua"] else "no town of 10,000+ near")
        tm = x["town"][1] if x["town"] else 999
        add(3, tm <= 15, f"town with the basics ({x['town'][0]}) about {tm} min" if x["town"] else "no town near")
        cm = x["city"][1] if x["city"] else 999
        add(8 if cm <= 90 else 5 if cm <= 150 else 2 if cm <= 240 else 0, cm <= 150, f"{x['city'][0]} about {cm} min" if x["city"] else "far from a city")
        hm = x["hol"][1] if x["hol"] else 999
        add(8 if hm <= 30 else 4 if hm <= 60 else 0, hm <= 60, f"holiday area: {x['hol'][0]} about {hm} min" if x["hol"] else "not near a known holiday area")
        cst = x["coast"] if x["coast"] is not None else 999
        add(6 if cst <= 20 else 3 if cst <= 60 else 0, cst <= 60, f"beach about {cst} km" if cst < 999 else "far from the coast")
        # things to do (15)
        pkd = x["park"][1] if x["park"] else 999
        add(6 if pkd <= 15 else 3 if pkd <= 35 else 0, pkd <= 35, f"{x['park'][0]} about {pkd} km" if x["park"] else "no park near")
        wd = x["wine"][1] if x["wine"] else 999
        add(6 if wd <= 25 else 3 if wd <= 50 else 0, wd <= 50, f"{x['wine'][0]} wine region about {wd} km" if x["wine"] else "no wine region near")
        add(3, stays >= 20, f"{stays} holiday cabins and farm stays within 40 km" if stays else "few holiday stays nearby (or no data)")
        # water and land (15)
        f = set(r.get("feats") or [])
        frontage = bool(f & {"creek", "river"}); stored = bool(f & {"dam", "bore", "tank"})
        add(7 if frontage else 0, frontage, "creek or river" if frontage else "no creek or river mentioned")
        add(3 if stored else 0, stored, "dam, bore or tanks" if stored else "no dam or bore mentioned")
        rn = r.get("rain") or 0
        add(4 if 550 <= rn <= 1300 else 2 if 450 <= rn <= 1800 else 0, 450 <= rn <= 1800, f"{rn} mm rain a year" if rn else "rainfall unknown")
        a = r["a"]
        add(3 if 20 <= a <= 2500 else 2 if 10 <= a <= 5000 else 0, 20 <= a <= 2500, f"{round(a)} acres")
        # momentum (20)
        l20 = x["land20"] or 0
        add(7 if l20 >= 8 else 5 if l20 >= 6 else 3 if l20 >= 4 else 0, l20 >= 6, f"area land values grew {l20}%/yr over 20 years" if x["land20"] else "no long-run growth figure")
        p10 = x["pop10"]
        add(6 if (p10 or 0) >= 1.5 else 4 if (p10 or 0) >= 0.8 else 2 if (p10 or 0) >= 0.3 else 0, (p10 or 0) >= 0.8,
            f"council population growing {p10}%/yr" if p10 is not None else "population growth unknown")
        add(4 if x["pace"] == "busy" else 2 if x["pace"] == "normal" else 0, x["pace"] in ("busy", "normal"), f"local market {x['pace'] or 'unknown'}")
        # upside and price (10)
        add(3, (r.get("lots") or 0) >= 2, f"could be split into {r.get('lots')} lots" if (r.get("lots") or 0) >= 2 else "no subdivision found")
        v = r.get("v")
        add({"great": 7, "good": 5, "fair": 3, "high": 1}.get(v, 0), v in ("great", "good", "fair"),
            {"great": "priced well under similar blocks", "good": "priced under similar blocks", "fair": "fairly priced", "high": "asking a bit high", "over": "overpriced", "why": "suspiciously cheap"}.get(v, "no price to judge"))
        # deal-breakers
        ck = r.get("chk") or {}; fl = set(r.get("flags") or [])
        bad = []
        if ck.get("flood") or "flood" in fl: pts -= 8; bad.append("flood area")
        if ck.get("veg"): pts -= 8; bad.append("protected vegetation")
        if "covenant" in fl: pts -= 10; bad.append("covenant")
        if "nobuild" in fl: pts -= 15; bad.append("may not be allowed to build")
        if "lease" in fl: pts -= 10; bad.append("leasehold")
        if "access" in fl: pts -= 10; bad.append("access doubtful")
        if v == "why": pts -= 5; bad.append("price so low there's likely a catch")
        if ck.get("fire") or ck.get("burnt"): pts -= 2; bad.append("bushfire prone")
        if a >= 20000: pts -= 10; bad.append("pastoral station")
        gs = max(0, min(100, round(pts)))
        # must-haves: a real town or a holiday town with the basics, water, things to do, no deal-breaker
        town_ok = sm <= 40 or (hm <= 30 and tm <= 20)
        fun_ok = pkd <= 30 or wd <= 40 or cst <= 30 or hm <= 30
        hard = [b for b in bad if b not in ("bushfire prone",)]
        r["gs"], r["gx"] = gs, dict(x, bad=bad)   # the page builds the tick list from these facts
        r["gok"] = 1 if (town_ok and fun_ok and (frontage or stored) and not hard) else 0
        r["gstar"] = 1 if (r["gok"] and gs >= 68 and v in ("great", "good")) else 0
    open(P("acreage-data.js"), "w").write("window.ACREAGE_DATA=" + json.dumps(d, separators=(",", ":")) + ";\n")
    L = [r for r in d["listings"] if "gs" in r]
    print("Growth score on", len(L), "blocks | tick all boxes:", sum(r["gok"] for r in L), "| standouts:", sum(r["gstar"] for r in L))


if __name__ == "__main__":
    main()
