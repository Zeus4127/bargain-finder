#!/usr/bin/env python3
"""Market pulse and track record: is the land market turning, and were our picks right?

Runs after the scan (no extra web requests). Writes:
  market-pulse.json  one snapshot per day (asking $/acre by size, price cuts, time on market, supply,
                     sold vs asking), plus NSW government sales month by month for the long run
  picks.json         every block first called a good or great deal, and what it later sold for
and adds a short summary to acreage-data.js ("pulse" and "picks") for the page.

  python3 -I pulse.py
"""
import json, os, statistics
from collections import defaultdict
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)


def load(f, default):
    try: return json.load(open(P(f)))
    except Exception: return default


def band(a): return "10-50" if a < 50 else "50-200" if a < 200 else "200+"


def med(v): return round(statistics.median(v)) if v else None


def main():
    raw = open(P("acreage-data.js")).read()
    d = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    L = [r for r in d["listings"] if r.get("a", 0) < 20000]
    today = d["scanned"][:10]

    # ---- today's snapshot
    snap = {"date": today, "n": len(L)}
    for b in ("10-50", "50-200", "200+"):
        snap["ppa_" + b] = med([r["p"] / r["a"] for r in L if r.get("p") and band(r["a"]) == b])
    priced = [r for r in L if r.get("p")]
    snap["cut_share"] = round(sum(1 for r in priced if r.get("cuts")) / max(1, len(priced)), 3)
    snap["dom_median"] = med([r["dom"] for r in L if r.get("dom") is not None])
    snap["new_7d"] = sum(1 for r in L if r.get("dom") is not None and r["dom"] <= 7)
    areas = list((d.get("areas") or {}).values())
    sold90 = sum(a.get("sold90", 0) for a in areas)
    snap["supply_months"] = round(len(L) / (sold90 / 3), 1) if sold90 else None
    sva = [a["sold_vs_ask"] for a in areas if a.get("sold_vs_ask")]
    snap["sold_vs_ask"] = round(statistics.median(sva), 3) if sva else None

    pulse = load("market-pulse.json", {"days": [], "nsw_months": []})
    pulse["days"] = [x for x in pulse["days"] if x["date"] != today] + [snap]
    pulse["days"].sort(key=lambda x: x["date"])

    # ---- long run: NSW government sales, 3-month rolling median $/acre for 10-200 acre blocks
    by = defaultdict(list)
    for x in load("nsw-sales.json", []):
        if 10 <= x["a"] < 200: by[x["date"][:7]].append(x["p"] / x["a"])
    months = sorted(by)[-30:]
    nm = []
    for i, m in enumerate(months):
        pool = [v for mm in months[max(0, i - 2):i + 1] for v in by[mm]]
        if len(by[m]) >= 100 and len(pool) >= 150: nm.append({"month": m, "ppa": med(pool), "sales": len(by[m])})
    if nm: pulse["nsw_months"] = nm
    # sales are recorded a month or two after they happen, so the newest two months are left out of the trend
    nmt = nm[:-2] if len(nm) > 8 else nm

    # ---- signals: compare with about 30 and 60 days ago
    days = pulse["days"]
    def ago(n):
        t = datetime.fromisoformat(today)
        old = [x for x in days if (t - datetime.fromisoformat(x["date"])).days >= n]
        return old[-1] if old else None
    sig, notes = 0, []
    a30 = ago(28)
    if a30:
        for b in ("10-50", "50-200"):
            if a30.get("ppa_" + b) and snap.get("ppa_" + b):
                ch = snap["ppa_" + b] / a30["ppa_" + b] - 1
                if ch <= -0.04: sig += 1; notes.append(f"asking prices for {b} acre blocks are down {round(-ch * 100)}% in a month")
                elif ch >= 0.04: sig -= 1; notes.append(f"asking prices for {b} acre blocks are up {round(ch * 100)}% in a month")
        if snap["cut_share"] - a30["cut_share"] >= 0.03: sig += 1; notes.append("more sellers are cutting prices")
        if snap.get("supply_months") and a30.get("supply_months") and snap["supply_months"] > a30["supply_months"] * 1.15:
            sig += 1; notes.append("more blocks for sale per sale (buyers have more choice)")
        if snap.get("sold_vs_ask") and a30.get("sold_vs_ask") and snap["sold_vs_ask"] < a30["sold_vs_ask"] - 0.03:
            sig += 1; notes.append("sales are landing further under asking prices")
    if len(nmt) >= 7:
        ch = nmt[-1]["ppa"] / nmt[-7]["ppa"] - 1
        if ch <= -0.05: sig += 1; notes.append(f"NSW sale prices per acre are down {round(-ch * 100)}% over 6 months")
        elif ch >= 0.05: sig -= 1; notes.append(f"NSW sale prices per acre are up {round(ch * 100)}% over 6 months")
    have = len(days)
    if not a30:
        verdict = (f"Learning: {have} day{'s' if have != 1 else ''} of daily data so far; the daily signals switch on after about a month. "
                   + ("The long-run NSW sales trend already shows: " + notes[-1] + "." if notes else "The long-run NSW sales trend is steady."))
    elif sig >= 3: verdict = "Falling: several signs prices are dropping. Good time to hunt, and to offer low."
    elif sig >= 1: verdict = "Softening: some signs prices are easing. Watch your matches and be ready."
    elif sig <= -2: verdict = "Rising: prices are going up. Don't wait too long on a good block."
    else: verdict = "Steady: no clear move yet."
    pulse["latest"] = {"date": today, "signals": sig, "verdict": verdict, "notes": notes, "days": have}
    json.dump(pulse, open(P("market-pulse.json"), "w"), separators=(",", ":"))

    # ---- track record: remember picks, then see what they sold for
    picks = load("picks.json", {})
    hist = load("listings-history.json", {})
    for r in L:
        sid = str(r["id"])
        if r.get("v") in ("great", "good") and r.get("p") and sid not in picks:
            picks[sid] = {"d": today, "v": r["v"], "p": r["p"], "fair": r.get("fair"), "s": r["s"], "sub": r.get("sub"), "a": r["a"], "u": r.get("u")}
    for sid, k in picks.items():
        h = hist.get(sid) or {}
        if h.get("sold_price") and "sold" not in k: k.update(sold=h["sold_price"], sold_d=h.get("sold_date"))
        if h.get("gone") and "gone" not in k: k["gone"] = h["gone"]
    json.dump(picks, open(P("picks.json"), "w"), separators=(",", ":"))
    done = [k for k in picks.values() if k.get("sold") and k.get("p")]
    summary = {"picks": len(picks), "sold": len(done), "gone": sum(1 for k in picks.values() if k.get("gone")),
               "sold_vs_ask": round(statistics.median(k["sold"] / k["p"] for k in done), 3) if done else None,
               "sold_vs_fair": round(statistics.median(k["sold"] / k["fair"] for k in done if k.get("fair")), 3) if any(k.get("fair") for k in done) else None,
               "recent": sorted(done, key=lambda k: k.get("sold_d") or "")[-8:]}

    # ---- add to the page data
    d["pulse"] = {"latest": pulse["latest"], "days": days[-120:], "nsw_months": pulse.get("nsw_months", [])}
    d["picks"] = summary
    open(P("acreage-data.js"), "w").write("window.ACREAGE_DATA=" + json.dumps(d, separators=(",", ":")) + ";\n")
    print("Pulse:", pulse["latest"]["verdict"], "| picks tracked:", len(picks), "| sold so far:", len(done))


if __name__ == "__main__":
    main()
