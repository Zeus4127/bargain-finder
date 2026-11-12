#!/usr/bin/env python3
"""Parse Bendigo Bank Agribusiness 'Australian Farmland Values' report text (pdftotext -layout)
into regions, councils (LGAs) and parcel-size bands with median $/ha and growth rates."""
import re, sys, json

STATE_WORDS = {"QUEENSLAND": "QLD", "NEW SOUTH WALES": "NSW", "VICTORIA": "VIC", "TASMANIA": "TAS",
               "SOUTH AUSTRALIA": "SA", "WESTERN": "WA", "WESTERN AUSTRALIA": "WA", "NORTHERN TERRITORY": "NT"}
PCT = r"(-?[\d.]+%|n/?a|–|-)"
ROW = re.compile(r"((?:[A-Z][A-Za-z&’'\-/\.]*)(?: [A-Za-z&’'\-/\.]+)*|\d[\d,]*[–-]\d[\d,]*|\d[\d,]*\+|<\s?\d+)\s{2,}\$([\d,]+)\s+" + PCT + r"\s+" + PCT + r"(?:\s+" + PCT + r")?(?:\s+" + PCT + r")?(?=\s{2,}|\s*$)")

def pct(s):
    if s is None: return None
    s = s.strip()
    return float(s[:-1]) if s.endswith("%") else None

def parse(path, year):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    regions, lgas, bands = [], [], []
    state = None
    streams = {0: [], 1: []}
    for i, l in enumerate(lines):
        u = l.upper()
        for w, code in STATE_WORDS.items():
            if re.search(r"\b" + w + r"\b\s{2,}\$", u): state = code
        for m in ROW.finditer(l):
            name = re.split(r"\s{2,}", m.group(1))[-1].strip()
            med = int(m.group(2).replace(",", ""))
            vals = [pct(m.group(k)) for k in (3, 4, 5, 6)]
            n = sum(v is not None for v in vals)
            col = 0 if m.start() < len(l) / 2 else 1
            rec = {"name": name, "median": med, "line": i, "col": col}
            if re.match(r"^[\d<]", name) or name == "Overall":
                rec.update(yoy=vals[0], cagr10=vals[1]); streams[col].append(rec)
            elif m.group(5) is not None and m.group(6) is not None:
                rec.update(yoy=vals[0], cagr5=vals[1], cagr10=vals[2], cagr20=vals[3]); regions.append(rec)
            elif m.group(5) is not None:
                rec.update(cagr5=vals[0], cagr10=vals[1], cagr20=vals[2]); lgas.append(rec)
    # assign states to regions by the state summary row that follows them
    out_regions, pending = [], []
    for r in regions:
        code = STATE_WORDS.get(r["name"].upper())
        if code:
            for p in pending: p["state"] = code
            out_regions += pending + [dict(r, state=code, is_state=True)]
            pending = []
        else:
            pending.append(r)
    # parcel bands: group each column stream into runs ending at "Overall"; match Overall to a region by median
    by_med = {}
    for r in out_regions: by_med.setdefault(r["median"], r)
    for col in (0, 1):
        run = []
        for b in sorted(streams[col], key=lambda x: x["line"]):
            if b["name"] == "Overall":
                reg = by_med.get(b["median"])
                if reg and not reg.get("is_state"):
                    for x in run:
                        bands.append({"state": reg["state"], "region": reg["name"], "band_ha": x["name"].replace("–", "-"),
                                      "median": x["median"], "yoy": x["yoy"], "cagr10": x["cagr10"]})
                run = []
            else:
                run.append(b)
    # LGAs: dedupe; region name rows repeat in LGA tables (skip names equal to a region)
    regnames = {r["name"].upper() for r in out_regions}
    seen, out_lgas = set(), []
    # assign LGA state by nearest preceding region-table state
    state_lines = sorted((r["line"], r["state"]) for r in out_regions if r.get("is_state"))
    def state_at(line):
        st = None
        for ln, s in state_lines:
            if ln <= line: st = s
        nxt = [s for ln, s in state_lines if ln > line]
        return st if st else (nxt[0] if nxt else None)
    for g in lgas:
        if g["name"].upper() in regnames: continue
        st = state_at(g["line"])
        key = (st, g["name"])
        if key in seen: continue
        seen.add(key)
        out_lgas.append({"state": st, "lga": g["name"], "median": g["median"], "cagr5": g["cagr5"], "cagr10": g["cagr10"], "cagr20": g["cagr20"]})
    clean = lambda r: {k: r[k] for k in ("state", "name", "median", "yoy", "cagr5", "cagr10", "cagr20") if k in r} | {"is_state": bool(r.get("is_state"))}
    return {"year": year, "regions": [clean(r) for r in out_regions], "lgas": out_lgas, "bands": bands}

if __name__ == "__main__":
    print(json.dumps(parse(sys.argv[1], int(sys.argv[2])), indent=1))
