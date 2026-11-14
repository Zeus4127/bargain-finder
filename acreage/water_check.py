#!/usr/bin/env python3
"""Mapped creeks and rivers near each block (state government water maps), so a block isn't marked down
just because its listing forgot to mention the creek.

QLD: watercourses of stream order 3+ (a real creek, not a gully). NSW: named watercourses.
TAS: major and intermediate rivers, streams and creeks. Looks within 400 m of the listing's map point.
Saved in water-cache.json; scan_acreage/growth read it.

  python3 -I water_check.py
"""
import json, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)
LAYERS = {
    "QLD": ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/InlandWaters/WaterCoursesAndBodies/MapServer/37", "stream_order>=3", "name,stream_order"),
    "NSW": ("https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Hydrography/MapServer/5", "1=1", "*"),
    "TAS": ("https://services.thelist.tas.gov.au/arcgis/rest/services/Public/TopographyAndRelief/MapServer/16", "1=1", "NAME"),
}


def look(r):
    url, where, fields = LAYERS[r["s"]]
    q = urllib.parse.urlencode({"geometry": "%s,%s" % (r["lng"], r["lat"]), "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "distance": 400, "units": "esriSRUnit_Meter", "spatialRel": "esriSpatialRelIntersects",
                                "where": where, "outFields": fields, "returnGeometry": "false", "f": "json"})
    for i in range(3):
        try:
            j = json.load(urllib.request.urlopen(url + "/query?" + q, timeout=60))
            if "error" in j: raise RuntimeError(j["error"])
            names = sorted({(a.get("name") or a.get("NAME") or a.get("hydroname") or "").strip() for a in (f["attributes"] for f in j.get("features", []))} - {""})
            return {"n": len(j.get("features", [])), "names": names[:3]}
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def main():
    d = json.loads(open(P("acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    try: cache = json.load(open(P("water-cache.json")))
    except Exception: cache = {}
    todo = [r for r in d["listings"] if r["s"] in LAYERS and r.get("lat") and not r.get("approx") and str(r["id"]) not in cache]
    print("blocks to check:", len(todo), flush=True)
    with ThreadPoolExecutor(3) as ex:
        for i, (r, got) in enumerate(zip(todo, ex.map(look, todo)), 1):
            if got is not None: cache[str(r["id"])] = got
            if i % 100 == 0:
                json.dump(cache, open(P("water-cache.json"), "w"), separators=(",", ":")); print("  %d/%d" % (i, len(todo)), flush=True)
    json.dump(cache, open(P("water-cache.json"), "w"), separators=(",", ":"))
    print("Wrote water-cache.json:", len(cache), "| with a creek or river:", sum(1 for v in cache.values() if v["n"]), flush=True)


if __name__ == "__main__":
    main()
