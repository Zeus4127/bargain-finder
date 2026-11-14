#!/usr/bin/env python3
"""Slope and height for each block, from the free Open-Meteo elevation service (Copernicus 90 m terrain).

Samples the block's map point and four points 400 m north, south, east and west, then keeps the height
and the steepest slope (%). Saved in elev-cache.json by rounded position.

  python3 -I elevation.py
"""
import json, math, os, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)
URL = "https://api.open-meteo.com/v1/elevation?"
STEP = 400.0


def main():
    d = json.loads(open(P("acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    try: cache = json.load(open(P("elev-cache.json")))
    except Exception: cache = {}
    keys = []
    for r in d["listings"]:
        if r.get("lat") and not r.get("approx"):
            k = "%.3f,%.3f" % (r["lat"], r["lng"])
            if k not in cache and k not in keys: keys.append(k)
    print("blocks to look up:", len(keys), flush=True)
    for i in range(0, len(keys), 20):        # 20 blocks x 5 points = 100 points a request
        batch = keys[i:i + 20]; lats, lngs = [], []
        for k in batch:
            la, lo = map(float, k.split(","))
            dla = STEP / 111320; dlo = STEP / (111320 * math.cos(math.radians(la)))
            for y, x in ((la, lo), (la + dla, lo), (la - dla, lo), (la, lo + dlo), (la, lo - dlo)):
                lats.append("%.5f" % y); lngs.append("%.5f" % x)
        for attempt in range(3):
            try:
                j = json.load(urllib.request.urlopen(URL + urllib.parse.urlencode({"latitude": ",".join(lats), "longitude": ",".join(lngs)}), timeout=60))
                e = j["elevation"]; break
            except Exception as ex:
                e = None; time.sleep(5 * (attempt + 1))
        if not e: continue
        for n, k in enumerate(batch):
            c, nn, s, ee, w = e[n * 5:n * 5 + 5]
            if c is None: continue
            slope = max(abs(c - v) for v in (nn, s, ee, w) if v is not None) / STEP * 100
            cache[k] = {"h": round(c), "slope": round(slope, 1), "range": round(max(c, nn, s, ee, w) - min(c, nn, s, ee, w))}
        time.sleep(0.5)
        if (i // 20) % 20 == 0:
            json.dump(cache, open(P("elev-cache.json"), "w"), separators=(",", ":")); print("  %d/%d" % (min(i + 20, len(keys)), len(keys)), flush=True)
    json.dump(cache, open(P("elev-cache.json"), "w"), separators=(",", ":"))
    print("Wrote elev-cache.json:", len(cache), flush=True)


if __name__ == "__main__":
    main()
