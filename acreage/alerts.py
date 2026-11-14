#!/usr/bin/env python3
"""Phone alerts for new Standouts and new matches for "My rules" (alert-rules.json), sent with ntfy.

Only sends when the environment variable ACREAGE_NTFY_TOPIC is set (the topic is never stored in a file).
Remembers what it has already sent in alerted.json, so each block is only announced once.

  ACREAGE_NTFY_TOPIC=your-topic python3 -I alerts.py
"""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]]; sys.path.insert(0, HERE)
P = lambda f: os.path.join(HERE, f)


def main():
    import scan_acreage as S
    d = json.loads(open(P("acreage-data.js")).read().split("=", 1)[1].strip().rstrip(";"))
    try: rules = json.load(open(P("alert-rules.json")))
    except Exception: rules = {}
    try: sent = set(json.load(open(P("alerted.json"))))
    except Exception: sent = None          # first run: remember everything, send nothing
    first = sent is None; sent = sent or set()
    topic = os.environ.get("ACREAGE_NTFY_TOPIC", "").strip()
    new = []
    for r in d["listings"]:
        if r.get("uo"): continue
        why = "⭐ Standout" if r.get("gstar") else "Matches your rules" if rules and S.match_rules(r, rules) else None
        if not why: continue
        key = str(r["id"])
        if key in sent: continue
        sent.add(key)
        if not first: new.append((why, r))
    json.dump(sorted(sent), open(P("alerted.json"), "w"))
    if first: print("alerts: first run, remembered", len(sent), "blocks; nothing sent"); return
    print("alerts: new", len(new), "| sending" if topic else "| no ntfy topic set, not sending")
    for why, r in new[:10]:
        msg = f"{why}: {round(r['a'])} ac {r.get('sub')} {r['s']}, asking ${r['p']:,.0f}" + (f", Growth {r['gs']}/100" if r.get("gs") is not None else "") + (f", likely sale ${r['fair']:,.0f}" if r.get("fair") else "")
        if not topic: print("  ", msg); continue
        try:
            urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode(),
                                   headers={"Title": "Acreage Finder", "Click": r.get("u") or "", "Tags": "house"}), timeout=15)
        except Exception as e: print("  alert failed", e)


if __name__ == "__main__":
    main()
