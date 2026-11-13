#!/usr/bin/env python3
"""Turn NSW Valuer General bulk sales files into land growth by area and block size.

Download the yearly files (2001 onwards) in a browser from
valuation.property.nsw.gov.au/embed/propertySalesInformation, put the .zip files in acreage/nsw-vg/
(zips inside zips are fine), then run:

  python3 -I import_nsw_vg.py

Keeps every sale of 10+ acres (the file gives land area in hectares or square metres) and writes
nsw-sales.json (each sale) and nsw-growth.json (median $/acre each year by area and size band, with
5, 10 and 20-year growth). The data is free under CC BY-NC-ND: fine for personal use, not for sale.
"""
import io, json, math, os, re, statistics, sys, zipfile
from datetime import datetime
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "nsw-vg")
MIN_ACRES = float(os.environ.get("ACREAGE_MIN_ACRES", "10"))
HA = 2.471


def dat_lines(path):
    """Every line of every .DAT file, opening zips inside zips."""
    def walk(zf):
        for n in zf.namelist():
            data = zf.read(n)
            if n.lower().endswith(".zip"):
                yield from walk(zipfile.ZipFile(io.BytesIO(data)))
            elif n.lower().endswith(".dat"):
                yield from data.decode("latin-1").splitlines()
    if path.lower().endswith(".zip"):
        yield from walk(zipfile.ZipFile(path))
    elif path.lower().endswith(".dat"):
        yield from open(path, encoding="latin-1")


def parse_b(line):
    """A 2001-onwards sale record: B;district;property id;sale counter;download date;property name;unit;house no;
    street;locality;postcode;area;area type;contract date;settlement date;price;zoning;nature;purpose;strata lot;..."""
    f = line.rstrip("\n").split(";")
    if len(f) < 19 or f[0] != "B":
        return None
    try:
        area = float(f[11] or 0)
        price = float(f[15] or 0)
    except ValueError:
        return None
    acres = area * HA if f[12] == "H" else area / 4046.86 if f[12] == "M" else 0
    if acres < MIN_ACRES or price < 10000 or (f[19] if len(f) > 19 else "").strip():
        return None
    d = f[13] or f[14]
    if not re.match(r"\d{8}$", d):
        return None
    return {"pid": f[2], "dist": f[1], "sub": f[9].strip().title(), "pc": f[10].strip(), "a": round(acres, 1),
            "p": int(price), "date": "%s-%s-%s" % (d[:4], d[4:6], d[6:]), "zone": f[16].strip(),
            "nature": f[17].strip(), "purpose": f[18].strip().title(), "addr": " ".join(x for x in (f[7], f[8]) if x).strip().title()}


def map_sales():
    """Sales from fetch_nsw_map.py (the NSW government's public valuation map): each property's latest sale."""
    for fn in ("rural-sales.json", "semi-rural-sales.json"):
        p = os.path.join(SRC, fn)
        if not os.path.exists(p): continue
        for x in json.load(open(p)):
            if (x.get("deal_props") or 1) > 1 or x.get("strata") or not x.get("price") or not x.get("area"): continue
            acres = x["area"] / 4046.86
            if acres < MIN_ACRES or x["price"] < 10000: continue
            try: d = datetime.strptime(x["sale_date"], "%d %B %Y").date().isoformat()
            except Exception: continue
            yield {"pid": str(x.get("propid")), "dist": "", "sub": (x.get("suburb") or "").title(), "pc": str(x.get("postcode") or ""),
                   "a": round(acres, 1), "p": int(x["price"]), "date": d, "zone": "", "nature": "", "purpose": "",
                   "addr": " ".join(v for v in (x.get("house_no"), x.get("street")) if v).title(), "lat": x.get("lat"), "lng": x.get("lng"),
                   "src": "map"}


def band(a):
    return "10-50" if a < 50 else "50-100" if a < 100 else "100-500" if a < 500 else "500+"


def cagr(path, yrs):
    ys = sorted(path)
    if not ys: return None
    last = ys[-1]
    if last - yrs not in path: return None
    return round(((path[last] / path[last - yrs]) ** (1 / yrs) - 1) * 100, 1)


def main():
    if not os.path.isdir(SRC):
        sys.exit("Run fetch_nsw_map.py, or put the NSW yearly sales zips in %s, first." % SRC)
    sales, seen = [], set()
    for r in map_sales():
        k = (r["pid"], r["date"], r["p"])
        if k not in seen: seen.add(k); sales.append(r)
    print("map service:", len(sales), "sales of %g+ acres" % MIN_ACRES, flush=True)
    for fn in sorted(os.listdir(SRC)):
        if not fn.lower().endswith((".zip", ".dat")): continue
        n = 0
        for line in dat_lines(os.path.join(SRC, fn)):
            r = parse_b(line)
            if not r: continue
            k = (r["pid"], r["date"], r["p"])
            if k in seen: continue
            seen.add(k); sales.append(r); n += 1
        print(fn, n, "sales of %g+ acres" % MIN_ACRES, flush=True)
    # areas: Farmbuy region by postcode, council by suburb, from the main scan
    pc_reg, sub_lga = {}, {}
    try:
        d = json.loads(open(os.path.join(HERE, "acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
        for x in d["listings"] + d["sold"]:
            if x["s"] != "NSW": continue
            if x.get("region"): pc_reg.setdefault(x["pc"], x["region"])
            if x.get("lga"): sub_lga.setdefault((x.get("sub") or "").upper(), x["lga"])
    except Exception as e:
        print("no acreage-data.js to name areas:", e)
    # nearest scanned NSW block (within 20 km) names the council and region for sales with a map point
    grid = {}
    try:
        for x in d["listings"]:
            if x["s"] == "NSW" and x.get("lat") and (x.get("lga") or x.get("region")):
                grid.setdefault((round(x["lat"] * 5), round(x["lng"] * 5)), []).append(x)
    except Exception: pass
    def near(r):
        best, bd = None, 20.0
        ky, kx = round(r["lat"] * 5), round(r["lng"] * 5)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for x in grid.get((ky + dy, kx + dx), []):
                    dd = math.hypot((x["lat"] - r["lat"]) * 111, (x["lng"] - r["lng"]) * 111 * math.cos(math.radians(r["lat"])))
                    if dd < bd: best, bd = x, dd
        return best
    for r in sales:
        n = near(r) if r.get("lat") else None
        r["lga"] = sub_lga.get(r["sub"].upper()) or (n or {}).get("lga")
        r["region"] = pc_reg.get(r["pc"]) or (n or {}).get("region")
    json.dump(sales, open(os.path.join(HERE, "nsw-sales.json"), "w"), separators=(",", ":"))
    # growth: median $/acre per year by group (state, region, council) and size band, at least 5 sales a year
    groups = defaultdict(lambda: defaultdict(list))
    for r in sales:
        y = int(r["date"][:4]); v = r["p"] / r["a"]
        for g in [("NSW", "NSW")] + ([("region", r["region"])] if r["region"] else []) + ([("council", r["lga"])] if r["lga"] else []):
            for b in ("all", band(r["a"])):
                groups[(g[0], g[1], b)][y].append(v)
    out = []
    for (kind, name, b), years in groups.items():
        path = {y: round(statistics.median(v)) for y, v in years.items() if len(v) >= 5}
        if len(path) < 3: continue
        ys = sorted(path)
        # growth from 3-year pooled medians so one odd year doesn't swing it
        sm = {}
        for y in ys:
            pool = years.get(y - 1, []) + years[y] + years.get(y + 1, [])
            if len(pool) >= 8: sm[y] = statistics.median(pool)
        out.append({"kind": kind, "name": name, "band": b, "path": {y: path[y] for y in ys}, "sales": {y: len(years[y]) for y in ys},
                    "n": sum(len(v) for v in years.values()), "now": path[ys[-1]], "now_year": ys[-1],
                    "yoy": round((path[ys[-1]] / path[ys[-2]] - 1) * 100, 1) if ys[-1] - 1 == ys[-2] else None,
                    "cagr5": cagr(sm, 5), "cagr10": cagr(sm, 10), "cagr20": cagr(sm, 20)})
    json.dump({"source": "NSW Valuer General bulk property sales information (CC BY-NC-ND 4.0)", "min_acres": MIN_ACRES,
               "groups": out}, open(os.path.join(HERE, "nsw-growth.json"), "w"), separators=(",", ":"))
    print("Wrote nsw-sales.json (%d sales) and nsw-growth.json (%d groups)" % (len(sales), len(out)))


if __name__ == "__main__":
    main()
