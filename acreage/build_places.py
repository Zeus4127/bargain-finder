#!/usr/bin/env python3
"""Reference places for distances: towns (ABS Urban Centres and Localities 2021: urban centres of 1,000+
people, and major urban areas of 100,000+) and electricity substations (Geoscience Australia National
Electricity Infrastructure). Writes ref/places.json."""
import io, json, os, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, "ref"), exist_ok=True)
U = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/UCL/FeatureServer/0/query"
towns, off = [], 0
while True:
    q = urllib.parse.urlencode({"where": "sos_name_2021 IN ('Major Urban','Other Urban')", "outFields": "ucl_name_2021,sos_name_2021,state_name_2021",
                                "returnGeometry": "false", "returnCentroid": "true", "outSR": 4326, "resultOffset": off, "resultRecordCount": 1000, "f": "json"})
    fs = json.load(urllib.request.urlopen(U + "?" + q, timeout=120)).get("features", [])
    if not fs: break
    for f in fs:
        c = f.get("centroid") or {}
        if "x" in c:
            a = f["attributes"]
            towns.append([round(c["y"], 4), round(c["x"], 4), a["ucl_name_2021"], 1 if a["sos_name_2021"] == "Major Urban" else 0])
    off += len(fs)
subs = []
try:
    import openpyxl
    data = urllib.request.urlopen("https://d28rz98at9flks.cloudfront.net/150022/150022_04_1.xlsx", timeout=180).read()
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True)["Transmission_Substations"]
    rows = ws.iter_rows(values_only=True); head = next(rows)
    ix = {h: i for i, h in enumerate(head)}
    for r in rows:
        if r[ix["OPERATIONALSTATUS"]] == "Operational" and r[ix["X_COORDINATE"]]:
            subs.append([round(r[ix["Y_COORDINATE"]], 4), round(r[ix["X_COORDINATE"]], 4), r[ix["NAME"]], r[ix["VOLTAGEKV"]] or 0])
except Exception as e:
    print("substations failed:", e)
json.dump({"town": towns, "sub": subs}, open(os.path.join(HERE, "ref", "places.json"), "w"), separators=(",", ":"))
print("Wrote ref/places.json:", len(towns), "towns,", sum(t[3] for t in towns), "cities,", len(subs), "substations")
