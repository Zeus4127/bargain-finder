#!/usr/bin/env python3
"""Download NSW rural property sales (2001 onwards) from the NSW government's public valuation map
service into nsw-vg/ (rural, or semi-rural with the argument "semi").
Each property appears once, at its latest sale. Pages of 1,000, about one request a second, resumes if stopped."""
import json, os, sys, time, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
LAYER = {"rural": 3, "semi": 2}[sys.argv[1] if len(sys.argv) > 1 else "rural"]
B = "https://maps.six.nsw.gov.au/arcgis/rest/services/public/Valuation/MapServer/%d/query" % LAYER
OUT = os.path.join(HERE, "nsw-vg", {3: "rural-sales.json", 2: "semi-rural-sales.json"}[LAYER])
FIELDS = "OBJECTID,propid,house_no,street,suburb,postcode,price,sale_date,area,strata,last_sale,Validity_d,deal_props,dealing"

def get(params):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(B + "?" + urllib.parse.urlencode(params), timeout=90))
        except Exception as e:
            print("retry", e, flush=True); time.sleep(5 * (i + 1))
    raise SystemExit("gave up")

rows = json.load(open(OUT)) if os.path.exists(OUT) else []
off = len(rows)
while True:
    j = get({"where": "1=1" if LAYER == 3 else "area>=40000", "resultOffset": off, "outFields": FIELDS, "returnGeometry": "true", "outSR": 4326,
             "orderByFields": "OBJECTID", "resultRecordCount": 1000, "f": "json"})
    fs = j.get("features", [])
    if not fs: break
    for f in fs:
        a = f["attributes"]; g = f.get("geometry") or {}
        if "x" in g: a["lng"], a["lat"] = round(g["x"], 5), round(g["y"], 5)
        elif g.get("rings"): 
            pts = g["rings"][0]; a["lng"] = round(sum(p[0] for p in pts) / len(pts), 5); a["lat"] = round(sum(p[1] for p in pts) / len(pts), 5)
        rows.append(a)
    off += len(fs)
    if off % 10000 < len(fs):
        json.dump(rows, open(OUT, "w"), separators=(",", ":")); print(len(rows), flush=True)
    time.sleep(1)
json.dump(rows, open(OUT, "w"), separators=(",", ":"))
print("done", len(rows), flush=True)
