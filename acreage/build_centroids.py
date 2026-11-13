#!/usr/bin/env python3
"""Suburb centre points, for blocks whose listing has no map point.

Averages every known point in the suburb: scanned blocks, Farmbuy and Farm Property sales, NSW
government sales (nsw-sales.json) and the Queensland government's locality boundaries. Writes
suburb-centroids.json as {"STATE|SUBURB": [lat, lng, number of points]}.
"""
import json, os, statistics, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
pts = {}

def add(s, sub, lat, lng):
    if s and sub and lat and lng:
        pts.setdefault("%s|%s" % (s, sub.strip().upper()), []).append((lat, lng))

def load(p):
    try: return json.load(open(os.path.join(HERE, p)))
    except Exception: return None

d = json.loads(open(os.path.join(HERE, "acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
for x in d["listings"] + d["sold"]: add(x["s"], x.get("sub"), x.get("lat"), x.get("lng"))
for x in (load("sold-cache.json") or {}).values(): add(x.get("s"), x.get("sub"), x.get("lat"), x.get("lng"))
for x in (load("nsw-sales.json") or []): add("NSW", x.get("sub"), x.get("lat"), x.get("lng"))
out = {k: [round(statistics.median(p[0] for p in v), 4), round(statistics.median(p[1] for p in v), 4), len(v)] for k, v in pts.items()}
# Queensland localities: centre of each locality's outline
B = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Boundaries/AdminBoundariesFramework/MapServer/26/query"
off, n = 0, 0
while True:
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "locality", "returnGeometry": "true", "outSR": 4326,
                                "maxAllowableOffset": 0.02, "resultOffset": off, "resultRecordCount": 500, "orderByFields": "objectid", "f": "json"})
    try: fs = json.load(urllib.request.urlopen(B + "?" + q, timeout=120)).get("features", [])
    except Exception as e: print("QLD localities failed:", e); break
    if not fs: break
    for f in fs:
        rings = (f.get("geometry") or {}).get("rings") or []
        xy = [p for r in rings for p in r]
        k = "QLD|" + (f["attributes"]["locality"] or "").upper()
        if xy and k not in out:
            out[k] = [round((min(p[1] for p in xy) + max(p[1] for p in xy)) / 2, 4), round((min(p[0] for p in xy) + max(p[0] for p in xy)) / 2, 4), 0]; n += 1
    off += len(fs)
json.dump(out, open(os.path.join(HERE, "suburb-centroids.json"), "w"), separators=(",", ":"))
print("Wrote suburb-centroids.json:", len(out), "suburbs (", n, "from QLD localities )")
