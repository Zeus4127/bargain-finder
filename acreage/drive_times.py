#!/usr/bin/env python3
"""Real road drive times for each block (free OSRM public router, about one request a second).

For each block with a map point: minutes by road to the nearest town with the basics, the nearest town
of 10,000+ people, and the nearest city (the closest 3 of each by straight line are tried, the quickest
by road kept). Saved in drive-cache.json by rounded position, so later runs only route new blocks.

  python3 -I drive_times.py
"""
import json, math, os, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)
OSRM = "https://router.project-osrm.org/table/v1/driving/"
UA = "acreage-finder/1.0 (personal research; polite)"


def km(a, b, c, d):
    r = math.pi / 180
    h = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def nearest3(lat, lng, pts):
    return sorted(pts, key=lambda p: km(lat, lng, p[0], p[1]))[:3]


def main():
    d = json.loads(open(P("acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    pl = json.load(open(P("ref/places.json")))
    groups = {"town": pl["town"], "sua": pl["sua"], "city": [t for t in pl["town"] if t[3]]}
    try: cache = json.load(open(P("drive-cache.json")))
    except Exception: cache = {}
    todo = []
    for r in d["listings"]:
        if not r.get("lat"): continue
        k = "%.3f,%.3f" % (r["lat"], r["lng"])
        if k not in cache and k not in [t[0] for t in todo]: todo.append((k, r["lat"], r["lng"]))
    print("blocks to route:", len(todo), flush=True)
    last = 0.0
    for i, (k, la, lo) in enumerate(todo, 1):
        dest = {g: nearest3(la, lo, pts) for g, pts in groups.items()}
        flat = [p for g in ("town", "sua", "city") for p in dest[g]]
        coords = ";".join(["%.5f,%.5f" % (lo, la)] + ["%.5f,%.5f" % (p[1], p[0]) for p in flat])
        wait = 1.05 - (time.time() - last)
        if wait > 0: time.sleep(wait)
        last = time.time()
        res = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(OSRM + coords + "?sources=0&annotations=duration", headers={"User-Agent": UA})
                j = json.load(urllib.request.urlopen(req, timeout=40))
                if j.get("code") == "Ok": res = j["durations"][0][1:]; break
            except Exception as e:
                time.sleep(5 * (attempt + 1))
        if res is None: continue
        out, n = {}, 0
        for g in ("town", "sua", "city"):
            best = None
            for p in dest[g]:
                sec = res[n]; n += 1
                if sec is not None and (best is None or sec < best[0]): best = (sec, p[2])
            if best: out[g] = [best[1], round(best[0] / 60)]
        cache[k] = out
        if i % 100 == 0:
            json.dump(cache, open(P("drive-cache.json"), "w"), separators=(",", ":")); print("  %d/%d" % (i, len(todo)), flush=True)
    json.dump(cache, open(P("drive-cache.json"), "w"), separators=(",", ":"))
    print("Wrote drive-cache.json:", len(cache), flush=True)


if __name__ == "__main__":
    main()
