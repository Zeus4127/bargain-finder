#!/usr/bin/env bash
# Quick hourly refresh (6 am to 9 pm): new listings and price changes from Farmbuy and Farm Property,
# details and checks for new blocks only, re-price, rebuild the page. The heavy jobs stay in run_daily.sh.
set -e
cd "$(dirname "$0")"
python3 -I -u scan_fp_sale.py || echo "Farm Property for-sale step failed; carrying on"
python3 -I -u build_listed.py || echo "Listed dates step failed; carrying on"
python3 -I -u scan_acreage.py
python3 -I -u scan_catches.py && python3 -I -u scan_acreage.py --rescore || echo "Catch checks failed; carrying on"
python3 -I -u growth.py || echo "Growth score step failed; carrying on"
python3 -I -u pulse.py || echo "Market pulse step failed; carrying on"
python3 -I -u alerts.py || echo "Alerts step failed; carrying on"
python3 -I build_page.py "${1:-acreage-finder.html}"
