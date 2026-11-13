#!/usr/bin/env bash
# Daily refresh: new sold listings, then all 100+ acre listings, then the one-file page.
set -e
cd "$(dirname "$0")"
python3 -I -u scan_sold.py
python3 -I -u scan_acreage.py
python3 -I build_page.py "${1:-acreage-finder.html}"
