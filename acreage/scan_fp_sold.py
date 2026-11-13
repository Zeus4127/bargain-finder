#!/usr/bin/env python3
"""Collect sold farms from farmproperty.com.au into fp-sold-cache.json.

Step 1 reads every page of /sold (about 24 cards a page): address, state, postcode, acres,
farm type, bedrooms and the sold price when the agent shows it.
Step 2 opens the detail page of each priced sale of 10+ acres for the sale date and location.
Both steps save as they go, so a stopped run carries on where it left off.
One request about every 1.1 seconds.

  python3 scan_fp_sold.py            # both steps
  python3 scan_fp_sold.py --cards    # list pages only
  python3 scan_fp_sold.py --from 150 # carry on from list page 150
  python3 scan_fp_sold.py --all      # also open unpriced sales for their date
"""
import json, os, re, sys, time, html, urllib.request

BASE = "https://www.farmproperty.com.au"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "fp-sold-cache.json")
DELAY = 1.1
UA = "Mozilla/5.0 (acreage-finder; personal research; polite)"
_last = [0.0]


def get(url):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            _last[0] = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print("  retry", url, e, flush=True)
            time.sleep(5 * (attempt + 1))
    return ""


def text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


ADDR = re.compile(r"^(.*?)\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+(\d{4})\b")


def parse_cards(page):
    out = []
    parts = page.split('data-testid="property-card"')[1:]
    for p in parts:
        m = re.search(r'data-property-id="(\d+)"', p)
        if not m:
            continue
        pid = m.group(1)
        href = re.search(r'href="(/property/%s/[^"]+)"' % pid, p)
        addr = re.search(r"<address[^>]*>(.*?)</address>", p, re.S)
        t = text(p)
        r = {"id": pid, "url": BASE + href.group(1) if href else BASE + "/property/" + pid}
        a = text(addr.group(1)) if addr else ""
        am = ADDR.search(a) or ADDR.search(t)
        if am:
            r["address"], r["state"], r["postcode"] = am.group(1).strip(), am.group(2), am.group(3)
        pm = re.search(r"SOLD\s+\$?(\d[\d,]*(?:\.\d+)?)", t)
        if pm:
            v = float(pm.group(1).replace(",", ""))
            if v >= 10000:
                r["price"] = int(v)
        ac = re.search(r"Acres:\s*([\d,]+(?:\.\d+)?)", t)
        if ac:
            r["acres"] = float(ac.group(1).replace(",", ""))
        ft = re.search(r"Farm Type:\s*(?:<[^>]+>\s*)*([^<]+)", p)
        if ft:
            r["type"] = ft.group(1).strip()
        bed = re.search(r"mdi-bed\"></i><strong>\s*(\d+)", p)
        r["bed"] = int(bed.group(1)) if bed else 0
        out.append(r)
    return out


def parse_detail(page):
    d = {}
    t = text(page)
    m = re.search(r"Sold\s+(\d{1,2})/(\d{1,2})/(\d{4})\s*(\$[\d,]+)?", t)
    if m:
        d["date"] = "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
        if m.group(4):
            d["price"] = int(m.group(4)[1:].replace(",", ""))
    la = re.search(r'"latitude":\s*"(-?\d+\.\d+)"', page)
    lo = re.search(r'"longitude":\s*"(-?\d+\.\d+)"', page)
    if la and lo:
        d["lat"], d["lng"] = float(la.group(1)), float(lo.group(1))
    d["v"] = 1
    return d


def save(c):
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, separators=(",", ":"))
    os.replace(tmp, CACHE)


def main():
    c = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    first = get(BASE + "/sold?pagenumber=1&order=LastUpdateNewest")
    last = max([int(x) for x in re.findall(r"pagenumber=(\d+)", first)] or [1])
    print("sold pages:", last, flush=True)
    state_p = os.path.join(HERE, "fp-sold-state.json")
    full_done = os.path.exists(state_p)
    start = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 1
    stale = 0
    for n in range(start, last + 1):
        page = first if n == 1 else get(BASE + "/sold?pagenumber=%d&order=LastUpdateNewest" % n)
        cards = parse_cards(page)
        new = 0
        for r in cards:
            old = c.get(r["id"], {})
            if not old:
                new += 1
            old.update({k: v for k, v in r.items() if k != "price" or "date" not in old})
            c[r["id"]] = old
        if n % 10 == 0:
            save(c)
            print("  page %d/%d  %d sales" % (n, last, len(c)), flush=True)
        # on later runs, stop once a few pages in a row hold nothing new
        if full_done:
            stale = stale + 1 if new == 0 else 0
            if stale >= 5:
                print("  caught up at page", n, flush=True)
                break
    save(c)
    if n == last and not full_done:
        json.dump({"full_pass": time.strftime("%Y-%m-%d")}, open(state_p, "w"))
    print("cards done:", len(c), flush=True)
    if "--cards" in sys.argv:
        return
    # --all also opens unpriced sales, for the sale date (sales counts by year in every state)
    todo = [r for r in c.values() if (r.get("price") or "--all" in sys.argv) and r.get("acres", 0) >= 10 and "v" not in r]
    print("detail pages to open:", len(todo), flush=True)
    for i, r in enumerate(todo, 1):
        page = get(r["url"])
        if page:
            r.update(parse_detail(page))
        if i % 50 == 0:
            save(c)
            print("  detail %d/%d" % (i, len(todo)), flush=True)
    save(c)
    dated = sum(1 for r in c.values() if r.get("date"))
    print("Wrote fp-sold-cache.json: %d sales, %d with price, %d dated" %
          (len(c), sum(1 for r in c.values() if r.get("price")), dated), flush=True)


if __name__ == "__main__":
    main()
