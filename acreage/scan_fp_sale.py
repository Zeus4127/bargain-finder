#!/usr/bin/env python3
"""Collect blocks for sale from farmproperty.com.au into fp-sale-cache.json.

Reads every page of /buy (24 cards a page): address, state, postcode, acres, farm type, bedrooms
and the asking price text. Then opens each new listing's page once for its description,
status (under offer) and map point. scan_acreage.py adds the ones Farmbuy doesn't have.
One request about every 1.1 seconds; saves as it goes.

  python3 scan_fp_sale.py
"""
import json, os, re, sys, time, html
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_fp_sold import BASE, HERE, get, text, ADDR

CACHE = os.path.join(HERE, "fp-sale-cache.json")
MIN_ACRES = float(os.environ.get("ACREAGE_MIN_ACRES", "10"))


def parse_cards(page):
    out = []
    for p in page.split('data-testid="property-card"')[1:]:
        m = re.search(r'data-property-id="(\d+)"', p)
        if not m:
            continue
        pid = m.group(1)
        href = re.search(r'href="(/property/%s/[^"]+)"' % pid, p)
        addr = re.search(r"<address[^>]*>(.*?)</address>", p, re.S)
        pr = re.search(r'property-price[^"]*">(.*?)</div>', p, re.S)
        t = text(p)
        r = {"id": pid, "url": BASE + (href.group(1) if href else "/property/" + pid),
             "pt": text(pr.group(1)) if pr else ""}
        a = text(addr.group(1)) if addr else ""
        am = ADDR.search(a) or ADDR.search(t)
        if am:
            r["address"], r["state"], r["postcode"] = am.group(1).strip(), am.group(2), am.group(3)
        ac = re.search(r"Acres:\s*([\d,]+(?:\.\d+)?)", t)
        if ac:
            r["acres"] = float(ac.group(1).replace(",", ""))
        ft = re.search(r"Farm Type:\s*(?:<[^>]+>\s*)*([^<]+)", p)
        if ft:
            r["type"] = ft.group(1).strip()
        bed = re.search(r'mdi-bed"></i><strong>\s*(\d+)', p)
        r["bed"] = int(bed.group(1)) if bed else 0
        ag = re.search(r'card-title"[^>]*>([^<]+)</h6>', p)
        if ag:
            r["agent"] = html.unescape(ag.group(1)).strip()
        out.append(r)
    return out


def parse_detail(page):
    d = {"v": 1}
    for m in re.finditer(r'<script type="application/ld(?:\+|&#x2B;)json">(.*?)</script>', page, re.S):
        try:
            j = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        for x in (j if isinstance(j, list) else [j]):
            if isinstance(x, dict) and x.get("description") and "desc" not in d:
                d["desc"] = re.sub(r"\s+", " ", html.unescape(x["description"]))[:3000]
            g = x.get("geo") if isinstance(x, dict) else None
            if g and g.get("latitude"):
                try:
                    d["lat"], d["lng"] = float(g["latitude"]), float(g["longitude"])
                except (TypeError, ValueError):
                    pass
    full = re.search(r'id="more_desc"[^>]*>(.*?)</div>', page, re.S)
    if full:
        hd = re.search(r'<h3 class="card-title[^"]*">([^<]*)</h3>\s*<div class="property-description"', page)
        d["desc"] = ((html.unescape(hd.group(1)).strip() + ". ") if hd else "") + text(full.group(1))[:3000]
    st = re.search(r'<h5 class="for_sale">\s*<span>([^<]+)', page)
    d["status"] = st.group(1).strip() if st else ""
    return d


def save(c):
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, separators=(",", ":"))
    os.replace(tmp, CACHE)


def main():
    c = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    today = date.today().isoformat()
    first = get(BASE + "/buy?pagenumber=1&order=LastUpdateNewest")
    last = max([int(x) for x in re.findall(r"pagenumber=(\d+)", first)] or [1])
    print("for-sale pages:", last, flush=True)
    seen = set()
    for n in range(1, last + 1):
        page = first if n == 1 else get(BASE + "/buy?pagenumber=%d&order=LastUpdateNewest" % n)
        for r in parse_cards(page):
            old = c.get(r["id"], {})
            if old.get("pt") and old["pt"] != r["pt"]:
                old.setdefault("prices", []).append([today, r["pt"]])
            old.update(r)
            old.setdefault("first", today)
            old["last"] = today
            c[r["id"]] = old
            seen.add(r["id"])
        if n % 10 == 0:
            save(c)
            print("  page %d/%d  %d listings" % (n, last, len(seen)), flush=True)
    for pid, r in c.items():
        r["live"] = pid in seen
    save(c)
    todo = [r for r in c.values() if r["live"] and r.get("acres", 0) >= MIN_ACRES and "v" not in r]
    print("listings on sale:", len(seen), "| detail pages to open:", len(todo), flush=True)
    for i, r in enumerate(todo, 1):
        page = get(r["url"])
        if page:
            r.update(parse_detail(page))
        if i % 50 == 0:
            save(c)
            print("  detail %d/%d" % (i, len(todo)), flush=True)
    save(c)
    print("Wrote fp-sale-cache.json: %d live listings of %d+ acres" %
          (sum(1 for r in c.values() if r["live"] and r.get("acres", 0) >= MIN_ACRES), MIN_ACRES), flush=True)


if __name__ == "__main__":
    main()
