#!/usr/bin/env python3
"""Combine parsed Bendigo reports into history-data.js: price paths rebuilt from
compound growth rates, plus regions, councils and parcel-size bands."""
import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
cur = json.load(open(sys.argv[1]))   # 2026 report (2025 data)
prev = json.load(open(sys.argv[2]))  # 2025 report (2024 data)
NAMES = {"QLD": "Queensland", "NSW": "New South Wales", "VIC": "Victoria", "TAS": "Tasmania", "SA": "South Australia", "WA": "Western Australia", "NT": "Northern Territory"}

def path(rec, year):
    """Points implied by a median and its 5/10/20-year CAGRs."""
    pts = {year: rec["median"]}
    for k, n in (("cagr5", 5), ("cagr10", 10), ("cagr20", 20)):
        if rec.get(k) is not None: pts[year - n] = round(rec["median"] / (1 + rec[k] / 100) ** n)
    return pts

def key(r): return (r["state"], r["name"].upper())
pmap = {key(r): r for r in prev["regions"]}
regions = []
for r in cur["regions"]:
    pts = path(r, 2025)
    p = pmap.get(key(r))
    if p:
        for y, v in path(p, 2024).items(): pts.setdefault(y, v)
    regions.append({"state": r["state"], "name": NAMES[r["state"]] if r["is_state"] else r["name"].title().replace("&", "&"),
                    "is_state": r["is_state"], "median": r["median"], "yoy": r.get("yoy"), "cagr5": r.get("cagr5"),
                    "cagr10": r.get("cagr10"), "cagr20": r.get("cagr20"), "path": dict(sorted(pts.items()))})
# NT and national from report text (no table rows for these)
regions.append({"state": "NT", "name": "Northern Territory", "is_state": True, "median": 3662, "yoy": -1.2,
                "cagr5": None, "cagr10": None, "cagr20": 7.9, "path": {2005: round(3662 / 1.079 ** 20), 2025: 3662}})
national = {"median": 10516, "yoy": 2.8, "cagr20": 7.2, "path": {2005: round(10516 / 1.072 ** 20), 2024: round(10516 / 1.028), 2025: 10516}}
pl = {(g["state"], g["lga"].upper()): g for g in prev["lgas"]}
lgas = []
for g in cur["lgas"]:
    if not g["state"]: continue
    pts = path(g, 2025)
    p = pl.get((g["state"], g["lga"].upper()))
    if p:
        pts[2024] = p["median"]
        for y, v in path(p, 2024).items(): pts.setdefault(y, v)
    lgas.append({**g, "path": dict(sorted(pts.items())), "prev": p["median"] if p else None})
data = {"source": "Bendigo Bank Agribusiness, Australian Farmland Values 2026 and 2025 (sales over ~30 ha, median $/ha, total sale price incl. improvements)",
        "national": national, "regions": regions, "lgas": lgas, "bands": cur["bands"],
        "outlook": {"rabobank_2026": 2.0, "bendigo_2025_national": 2.8, "abares_10yr_broadacre": 9.8, "abares_10yr_hobby": 4.1}}
open(os.path.join(HERE, "..", "history-data.js"), "w").write("window.HISTORY_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n")
print(len(regions), "regions", len(lgas), "councils", len(cur["bands"]), "bands")
