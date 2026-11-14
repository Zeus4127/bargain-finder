# Acreage Finder

Bargain Finder for land: every rural block of 10+ acres for sale in Australia (from Farmbuy.com),
each with a fair price, an opening offer, a walk-away price and a verdict, plus farmland price growth
by state, region and council.

Open `acreage.html` in a browser. It reads `acreage-data.js` (listings) and `history-data.js` (growth).

## Refresh the listings

```
python3 scan_acreage.py              # full scan, about 45 minutes the first time, ~5 minutes after that
python3 scan_acreage.py --rescore    # re-price the saved listings without scanning again
```

The scanner waits about a second between requests, as Farmbuy's robots.txt asks. Detail pages are
saved in `details-cache.json`, so later scans only open new listings.

Deal alerts: set the environment variable `ACREAGE_NTFY_TOPIC` to an ntfy topic name before running
(never write it into a file). After each scan, any new great or good deal under $350k that isn't under
offer is sent to that topic, the same way the caravan scanner does it.

Daily: `./run_daily.sh` runs the sold collectors, the scan and the page build in order.

## Where the data comes from

| Source | What | Script |
|---|---|---|
| Farmbuy.com | Every block for sale over 100 acres, with detail pages and map points | `scan_acreage.py` |
| Farmbuy sold sitemap | Recent sales with price and date | `scan_sold.py` |
| FarmProperty.com.au /sold | About 9,300 sold farms; price on about 670, sale date and map point from the detail page | `scan_fp_sold.py` |
| NSW Planning Portal map | Zone and real minimum lot size, for "could be split into N lots" | `scan_acreage.py` |
| VicPlan map | Zone; minimum lot is the state default for the zone (council schedules can differ) | `scan_acreage.py` |
| Farm Property for sale | Blocks Farmbuy doesn't have | `scan_fp_sale.py` |
| NSW government valuation map (maps.six.nsw.gov.au) | Latest sale of every NSW rural and semi-rural property since 2001: price, date, land size, map point. Used for NSW growth by size and as recent sale comparisons | `fetch_nsw_map.py`, `import_nsw_vg.py` |
| VicPlan, TAS PlanningOnline, WA SLIP maps | Zone and default minimum lot | `scan_acreage.py` |
| QLD locality boundaries | Suburb to council, for council growth | `qld-localities.json` |
| QLD State Valuation Service maps | Big station sales 2023–25 (over 500 ha), positions read off the map | `qld-big-sales.json` |
| Bendigo Bank 2026 mid-year report, NSW and QLD Valuer-General | Newest changes by region and council | `latest-values.json` |
| Bendigo Bank farmland values | Growth by state, region, council and parcel size | `history/` |

Not used: Domain, realestate.com.au, Facebook and Gumtree (off-limits), REIWA (bot check), Elders (not
reachable). Paste their ads into "Check a listing" instead.

## How a block is priced

1. Find up to 12 of the most similar blocks for sale or recently sold: within 50 km first (then 120 km,
   250 km, then the state; blocks without a map point use the postcode district), similar size, and the same kind of land (bare bush, working farm, bare
   lifestyle block, or a block with a house).
2. Scale each one's price to this block's size, then take the middle value.
3. Adjust for the block's own details read from its listing: creek or river +5%, power +4%,
   covenant −25%, no right to build −30%, leasehold −20%, doubtful access −15%, flood-prone −7%.
4. Verdict against the usual range of the similar blocks (25th to 75th percentile): inside it is
   fair; up to 15% under the low end is good, more is great; under half the low end is flagged
   "unusually cheap: find out why"; up to 20% over the high end is a bit high, more is overpriced. Opening offer is 88% of the lower of asking and fair
   price. Walk away above fair price + 5%.

These are asking prices, not sale prices, so they're a guide, not a valuation.

## Growth data

`history/parse_bendigo.py` reads the Bendigo Bank Agribusiness *Australian Farmland Values* report
(pdftotext -layout) into regions, councils and parcel-size bands. `history/build_history.py`
combines two years of reports into `history-data.js`. Price paths are rebuilt from each area's
5, 10 and 20-year compound growth rates.

```
pdftotext -layout 2026-farmland-values-report.pdf b26.txt && python3 history/parse_bendigo.py b26.txt 2025 > history/b2025.json
pdftotext -layout 2025-farmland-values-report.pdf b25.txt && python3 history/parse_bendigo.py b25.txt 2024 > history/b2024.json
python3 history/build_history.py history/b2025.json history/b2024.json
```

## NSW sales

`fetch_nsw_map.py` (rural) and `fetch_nsw_map.py semi` (semi-rural, 10+ acres) download the NSW
government's public valuation map layers into `nsw-vg/` (not committed). `import_nsw_vg.py` turns them
into `nsw-sales.json` (not committed) and `nsw-growth.json`: median $/acre by year, and 5, 10 and
20-year growth from 3-year pooled medians, for NSW, each region and each council, by block size.
Each property appears once, at its latest sale. The daily run refreshes this on Mondays.

## When you're ready to buy

The free system runs on its own until then. When there's money to spend, in this order:

1. **Sales records for the other states (about $175–$280 a month).** Cotality (CoreLogic RP Data) or Pricefinder
   give every sale with land size for QLD, VIC, WA, SA and TAS. Export the last 3–5 years of sales of 10+ acres
   as CSV (address, suburb, postcode, date, price, land area, and latitude/longitude if offered) into `acreage/sales-import/`.
   The import would follow `import_nsw_vg.py`: one row per sale, the same `nsw-sales.json` shape (`sub, pc, a, p, date, lat, lng`),
   then `scan_acreage.py` uses the last two years as comparisons and `growth.py`/the growth tables get real growth per
   council for every state. One month is enough to pull the history; keep it only if you're actively buying.
2. **Re-test the prices** with `python3 -I backtest.py --tune` once those sales are in: accuracy should improve outside NSW.
3. **Pick from the ⭐ Standouts** (Today tab). Each has a dossier: comparisons, an offer plan, cabin and caravan rules
   for its state, and questions for the agent. Ring the agent, check the council, see it in person.
4. **Phone alerts:** built into the Acreage Finder app (1.5+), free. Each refresh writes `alerts-feed.json`
   (new Standouts and new matches for `alert-rules.json`); the app checks it in the background about every 3 hours,
   even when closed, and shows a notification that opens the listing. Allow notifications when the app asks.
