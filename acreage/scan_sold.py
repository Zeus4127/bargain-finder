#!/usr/bin/env python3
"""Collect sold rural listings from Farmbuy's sold sitemap (its most recent ~3,000 sales).

Each sold page keeps the price (usually the sale price when the agent discloses it, otherwise the
last asking price), land size, postcode, region and map coordinates. The sitemap's lastmod is used as
the approximate sale date. Results accumulate in sold-cache.json, so running it daily builds a
growing sales history beyond the rolling 3,000. Writes sold-data.js for acreage.html.
"""
import json, re, os, sys, html, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_acreage import get, parse_price, HERE

CACHE = os.path.join(HERE, "sold-cache.json")
MIN_ACRES_KEEP = 10

def parse_page(s):
    m = re.search(r'dataLayer\.push\((\{"content":\{[^}]*"type":"property-listing-page".*?\})\);</script>', s, re.S)
    if not m: return None
    try: d = json.loads(m.group(1))["property"]
    except Exception: return None
    la = re.search(r'data-lat="(-?[\d.]+)"', s); lo = re.search(r'data-lng="(-?[\d.]+)"', s)
    a = re.match(r"([\d.,]+)\s*(ac|ha)", (d.get("landArea") or "").replace(",", ""))
    acres = (float(a.group(1)) * (2.471 if a.group(2) == "ha" else 1)) if a else None
    ad = d.get("address") or {}
    return {"id": d.get("id"), "addr": html.unescape(ad.get("full") or "").replace("&comma;", ","),
            "sub": html.unescape(ad.get("suburb") or "").title(), "s": ad.get("state"), "pc": ad.get("postcode") or "000",
            "region": ad.get("region"), "type": ", ".join(d.get("types") or []), "a": round(acres, 1) if acres else None,
            "pt": d.get("priceText") or "", "p": parse_price(d.get("priceText")), "ct": d.get("contractText"),
            "bed": int(float((d.get("meta") or {}).get("bed") or 0)), "tags": (d.get("meta") or {}).get("tags") or [],
            "lat": float(la.group(1)) if la else None, "lng": float(lo.group(1)) if lo else None, "u": d.get("url")}

def main():
    try: cache = json.load(open(CACHE))
    except Exception: cache = {}
    xml = get("https://farmbuy.com/dyn/sitemap/sold")
    urls = re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml)
    if not urls: urls = [(u, "") for u in re.findall(r"<loc>([^<]+)</loc>", xml)]
    todo = [(u, lm) for u, lm in urls if u.rsplit("-", 1)[-1] not in cache]
    print(len(urls), "sold in sitemap,", len(todo), "new", flush=True)
    for i, (u, lm) in enumerate(todo, 1):
        pid = u.rsplit("-", 1)[-1]
        r = parse_page(get(u) or "")
        cache[pid] = (r or {"id": pid, "u": u, "bad": True}) | {"sold": lm[:10]}
        if i % 50 == 0:
            json.dump(cache, open(CACHE, "w")); print(f"  {i}/{len(todo)}", flush=True)
    json.dump(cache, open(CACHE, "w"))
    keep = [r for r in cache.values() if not r.get("bad") and r.get("a") and r["a"] >= MIN_ACRES_KEEP and r.get("p")]
    keep.sort(key=lambda r: r.get("sold") or "", reverse=True)
    out = [{k: r.get(k) for k in ("id", "sub", "s", "pc", "region", "type", "a", "p", "pt", "bed", "sold", "u", "lat", "lng")} for r in keep]
    open(os.path.join(HERE, "sold-data.js"), "w").write("window.SOLD_DATA=" + json.dumps(out, separators=(",", ":")) + ";\n")
    print("Wrote sold-data.js with", len(out), "priced sales of", MIN_ACRES_KEEP, "+ acres")

if __name__ == "__main__":
    main()
