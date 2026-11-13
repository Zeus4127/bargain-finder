#!/usr/bin/env python3
"""Roughly when was each Farmbuy block first listed? Farmbuy listing numbers go up over time, so the
earliest 'last changed' date among all listings with the same or a higher number is a good upper
bound. Reads Farmbuy's for-sale sitemap and the sold cache; writes listed-curve.json [[number, date]].
A relisted block gets a new number, so its real time on the market can be longer."""
import json, os, re, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (acreage-finder; personal research; polite)"
xml = urllib.request.urlopen(urllib.request.Request("https://farmbuy.com/dyn/sitemap/forsale", headers={"User-Agent": UA}), timeout=120).read().decode()
pairs = [(int(m.group(1)), m.group(2)[:10]) for m in re.finditer(r"-(\d+)</loc>\s*<lastmod>([^<]+)", xml)]
try: sold = json.load(open(os.path.join(HERE, "sold-cache.json")))
except Exception: sold = {}
pairs += [(int(k), v["sold"]) for k, v in sold.items() if k.isdigit() and v.get("sold")]
pairs.sort()
curve, m = [], "9999"
for i, d in reversed(pairs):
    if d < m: m = d; curve.append([i, d])
curve.reverse()
json.dump(curve, open(os.path.join(HERE, "listed-curve.json"), "w"), separators=(",", ":"))
print("Wrote listed-curve.json:", len(curve), "points from", len(pairs), "listings")
