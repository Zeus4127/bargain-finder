#!/usr/bin/env bash
# Daily refresh: new sold listings (Farmbuy, Farm Property), then all 10+ acre listings (Farmbuy and Farm Property), then the one-file page.
set -e
cd "$(dirname "$0")"
python3 -I -u scan_sold.py
python3 -I -u scan_fp_sold.py || echo "Farm Property sold step failed; carrying on"
python3 -I -u scan_fp_sale.py || echo "Farm Property for-sale step failed; carrying on"
python3 -I -u scan_acreage.py
python3 -I build_page.py "${1:-acreage-finder.html}"
