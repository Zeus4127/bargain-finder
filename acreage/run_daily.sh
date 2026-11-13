#!/usr/bin/env bash
# Daily refresh: new sold listings (Farmbuy, Farm Property), then all 10+ acre listings (Farmbuy and Farm Property), then the one-file page.
set -e
cd "$(dirname "$0")"
python3 -I -u scan_sold.py
python3 -I -u scan_fp_sold.py || echo "Farm Property sold step failed; carrying on"
python3 -I -u scan_fp_sale.py || echo "Farm Property for-sale step failed; carrying on"
if [ "$(date +%u)" = 1 ] || [ ! -f nsw-sales.json ]; then  # Mondays, or when missing: refresh NSW government sales (about 45 minutes)
  rm -f nsw-vg/rural-sales.json nsw-vg/semi-rural-sales.json
  python3 -I -u fetch_nsw_map.py && python3 -I -u fetch_nsw_map.py semi && python3 -I -u import_nsw_vg.py || echo "NSW sales step failed; carrying on"
fi
python3 -I -u scan_acreage.py
python3 -I build_page.py "${1:-acreage-finder.html}"
