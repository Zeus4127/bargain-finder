# Acreage Finder

Bargain Finder for land: every rural block over 100 acres for sale in Australia (from Farmbuy.com),
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

Deal alerts: put an ntfy topic name in `ACREAGE_NTFY_TOPIC.txt` next to the script. After each scan,
any new great or good deal under $350k that isn't under offer is sent to that topic, the same way the
caravan scanner does it.

## How a block is priced

1. Find up to 12 of the most similar blocks for sale: same postcode district first (then the wider
   area, then the state), similar size, and the same kind of land (bare bush, working farm, bare
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

Next: 20-acre and 10-acre blocks (set `MIN_ACRES` in the scanner), and real sale-by-sale growth from
the free NSW Valuer General sales files.
