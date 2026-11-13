#!/usr/bin/env bash
# Daily refresh: new sold listings (Farmbuy, Farm Property), then all 100+ acre listings, then the one-file page.
set -e
cd "$(dirname "$0")"
python3 -I -u scan_sold.py
python3 -I -u scan_fp_sold.py || echo "Farm Property sold step failed; carrying on"
python3 -I -u scan_acreage.py
python3 -I build_page.py "${1:-acreage-finder.html}"
