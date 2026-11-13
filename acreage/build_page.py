#!/usr/bin/env python3
"""Build a single-file acreage-finder.html with the data inlined (for publishing as one page)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "acreage-finder.html")
s = open(os.path.join(HERE, "acreage.html")).read()
for f in ("acreage-data.js", "history-data.js"):
    s = s.replace(f'<script src="{f}"></script>', "<script>" + open(os.path.join(HERE, f)).read().replace("</", "<\\/") + "</script>")
open(out, "w").write(s)
print("Wrote", out, os.path.getsize(out), "bytes")
