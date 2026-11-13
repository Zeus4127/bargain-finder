#!/usr/bin/env python3
"""How good are the fair prices? Price each real sale as if it were for sale (leaving that sale out of
its own comparisons) and compare with what it actually sold for. Writes backtest.json.

  python3 -I backtest.py
"""
import json, os, random, statistics, sys
sys.argv = [sys.argv[0]]
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import scan_acreage as S

def band(a): return "10-50" if a < 50 else "50-200" if a < 200 else "200-1000" if a < 1000 else "1000+"

def main():
    d = json.loads(open(os.path.join(HERE, "acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    rows = d["listings"]; model = d["model"]
    sold = S.load_sold()
    asking = [r for r in rows if r.get("p") and r["a"] < S.STATION_ACRES]
    for r in asking: r["house"] = bool(r.get("house"))
    sales = [x for x in sold if x["a"] < S.STATION_ACRES]
    random.seed(7)
    nsw = [x for x in sales if x.get("src") == "nsw"]
    test = [x for x in sales if x.get("src") != "nsw"] + random.sample(nsw, min(800, len(nsw)))
    out = []
    for kind, pool_all in (("asking prices only", asking), ("asking + sales (what the app uses)", asking + sales)):
        res = []
        for t in test:
            pool = [c for c in pool_all if c["id"] != t["id"]]
            subj = dict(t); subj.pop("is_sold", None)
            fair, cs, lvl = S.price_one(subj, model, pool)
            if fair: res.append((t, fair / t["p"]))
        def summ(rs):
            r = [x[1] for x in rs]
            if len(r) < 10: return None
            return {"n": len(r), "median_ratio": round(statistics.median(r), 3),
                    "median_abs_err": round(statistics.median(abs(x - 1) for x in r), 3),
                    "within20": round(sum(1 for x in r if abs(x - 1) <= .2) / len(r), 3),
                    "within35": round(sum(1 for x in r if abs(x - 1) <= .35) / len(r), 3)}
        o = {"pool": kind, "all": summ(res),
             "by_state": {s: summ([x for x in res if x[0]["s"] == s]) for s in sorted({x[0]["s"] for x in res})},
             "by_size": {b: summ([x for x in res if band(x[0]["a"]) == b]) for b in ("10-50", "50-200", "200-1000", "1000+")},
             "by_source": {k: summ([x for x in res if (x[0].get("src") or "farmbuy") == k]) for k in ("farmbuy", "fp", "nsw")}}
        out.append(o)
        print(kind, json.dumps(o["all"]), flush=True)
        for k in ("by_state", "by_size", "by_source"): print("  ", k, {a: (b["median_ratio"], b["median_abs_err"], b["within20"], b["n"]) for a, b in o[k].items() if b})
    json.dump({"tests": out}, open(os.path.join(HERE, "backtest.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
