#!/usr/bin/env python3
"""Catch checks from free government maps, for blocks with a real map point.

NSW: bushfire prone land, flood planning area, biodiversity values (clearing limits).
VIC: planning overlays (bushfire, flood, vegetation, environment, landscape, erosion, salinity).
QLD: regulated vegetation category, strategic cropping land, floodplain assessment area.
WA:  bushfire prone area.
Saves catch-cache.json as it goes; scan_acreage.py adds the results to each block.
"""
import json, os, sys, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "catch-cache.json")
NSW = "https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/ePlanning/"
QLD = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Boundaries/AdminBoundariesFramework/MapServer/"
VIC = "https://plan-gis.mapshare.vic.gov.au/arcgis/rest/services/Planning/Vicplan_PlanningSchemeOverlays/MapServer/0"
WA = "https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Bush_Fire_Prone_Areas/MapServer/23"

def hits(url, lat, lng, fields="*"):
    q = urllib.parse.urlencode({"geometry": "%s,%s" % (lng, lat), "geometryType": "esriGeometryPoint", "inSR": 4326,
                                "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "false", "f": "json"})
    for i in range(3):
        try:
            j = json.load(urllib.request.urlopen(url + "/query?" + q, timeout=60))
            if "error" in j: raise RuntimeError(j["error"])
            return [f["attributes"] for f in j.get("features", [])]
        except Exception as e:
            if i == 2: print("  failed", url.split("/")[-3:], e, flush=True); return None
            time.sleep(3 * (i + 1))

def check(r):
    lat, lng, s, c = r["lat"], r["lng"], r["s"], {}
    if s == "NSW":
        f = hits(NSW + "Planning_Portal_Hazard/MapServer/229", lat, lng, "d_Category")
        if f is None: return None
        if f: c["fire"] = f[0].get("d_Category") or "yes"
        f = hits(NSW + "Planning_Portal_Hazard/MapServer/230", lat, lng, "LAY_CLASS")
        if f: c["flood"] = f[0].get("LAY_CLASS") or "yes"
        f = hits(NSW + "BiodiversityValuesMap/MapServer/1", lat, lng, "OBJECTID")
        if f: c["veg"] = "Biodiversity values map"
    elif s == "VIC":
        f = hits(VIC, lat, lng, "ZONE_CODE")
        if f is None: return None
        c["ov"] = sorted({a.get("ZONE_CODE") for a in f if a.get("ZONE_CODE")})
        codes = " ".join(c["ov"])
        if "BMO" in codes: c["fire"] = "Bushfire Management Overlay"
        if any(k in codes for k in ("LSIO", "FO", "RFO", "SBO")): c["flood"] = "Flood overlay"
        if "VPO" in codes: c["veg"] = "Vegetation Protection Overlay"
    elif s == "QLD":
        f = hits(QLD + "102", lat, lng, "rvm_cat")
        if f is None: return None
        cats = {a.get("rvm_cat") for a in f}
        if "B" in cats: c["veg"] = "Category B: remnant vegetation, clearing mostly not allowed"
        elif "C" in cats: c["veg"] = "Category C: high-value regrowth, clearing limited"
        elif "R" in cats: c["veg"] = "Category R: reef regrowth near watercourses, clearing limited"
        f = hits(QLD + "106", lat, lng, "zone")
        if f: c["scl"] = f[0].get("zone") or "yes"
        f = hits(QLD + "15", lat, lng, "objectid")
        if f: c["flood"] = "Floodplain assessment area"
    elif s == "WA":
        f = hits(WA, lat, lng, "designation")
        if f is None: return None
        if f: c["fire"] = "Bushfire prone area"
    c["v"] = 1
    return c

def main():
    c = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    d = json.loads(open(os.path.join(HERE, "acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    todo = [r for r in d["listings"] if r["s"] in ("NSW", "VIC", "QLD", "WA") and r.get("lat") and not r.get("approx") and str(r["id"]) not in c]
    print("catch checks to do:", len(todo), flush=True)
    for i, r in enumerate(todo, 1):
        got = check(r)
        if got: c[str(r["id"])] = got
        if i % 50 == 0:
            json.dump(c, open(CACHE, "w")); print("  %d/%d" % (i, len(todo)), flush=True)
    json.dump(c, open(CACHE, "w"))
    print("Wrote catch-cache.json:", len(c), flush=True)

if __name__ == "__main__":
    main()
