#!/usr/bin/env python3
"""Whale Desk reviewer: scores the tracked recommendations, checks that the online learning is behaving,
and (with --apply) makes evidence-based parameter changes that the per-trade learner cannot make itself.

    python review.py            # print the report, write review.md + review.json
    python review.py --apply    # also adjust model.json where the evidence is strong enough

The per-trade learner (recommend.learn) nudges factor weights and the BUY threshold after every closed call.
This reviewer looks at the whole sample: exit mix (target / stop / time), returns by category and by entry gate,
which factors actually separated wins from losses, and whether the pipeline itself is healthy.
"""
import json, os, sys, time, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RECS = os.path.join(HERE, "recs.json"); MODEL = os.path.join(HERE, "model.json"); DESK = os.path.join(HERE, "desk.json")
MIN_SAMPLE = 8          # closed calls in a category before any parameter is touched
FACTORS = ["whale", "smart", "news", "sentiment", "momentum", "liquidity", "lighter", "vaults", "cextop", "funding"]
FEED_MAX_AGE_H = 12     # positioning data older than this is ignored by the desk and flagged here

def load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def pct(a, b): return round(100.0 * a / b, 1) if b else None

def analyse(recs, model, desk):
    now = time.time(); out = {"ts": int(now), "health": [], "categories": {}, "gates": {}, "factors": {}, "suggestions": []}
    closed = recs.get("closed", []); opened = recs.get("open", [])

    # --- pipeline health ------------------------------------------------------------------------------------
    gen = desk.get("updated") or desk.get("generated_at") or 0
    if isinstance(gen, str):
        try: gen = time.mktime(time.strptime(gen[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception: gen = 0
    age_h = (now - gen) / 3600 if gen else None
    if age_h is None: out["health"].append("WARN desk.json has no updated timestamp; cannot tell when the last refresh ran")
    elif age_h > 7: out["health"].append(f"STALE last refresh {age_h:.1f}h ago (GitHub normally delivers one every 3 to 6 hours) - check the Actions tab")
    else: out["health"].append(f"OK last refresh {age_h:.1f}h ago")
    # the feeds behind the entry gate: a refresh can succeed while one of these has quietly stopped updating
    hl = desk.get("hl") or {}
    hl_age = (now - hl["updated"]) / 3600 if hl.get("updated") else None
    if hl_age is None: out["health"].append("WARN no Hyperliquid top-trader data at all: the smart-money gate cannot open")
    elif hl_age > FEED_MAX_AGE_H: out["health"].append(f"STALE Hyperliquid top-trader data is {hl_age:.0f}h old ({hl.get('note') or 'fetch failing'}): ignored by the desk until it recovers")
    else: out["health"].append(f"OK Hyperliquid top-trader data read {hl_age:.1f}h ago" + (f" (note: {hl['note']})" if hl.get("note") else ""))
    blocks = (desk.get("positioning") or {}).get("blocks") or {}
    for name, b in blocks.items():
        b_age = (now - b["updated"]) / 3600 if b.get("updated") else None
        if b.get("ok") and b_age is not None and b_age <= FEED_MAX_AGE_H: out["health"].append(f"OK second opinion '{name}' read {b_age:.1f}h ago, {len(b.get('coins') or {})} coins")
        else: out["health"].append(f"WARN second opinion '{name}' is not updating: {b.get('note') or 'no data'}")
    if not blocks: out["health"].append("NOTE second opinions (positioning.py) have not run yet")
    stale_open = [r for r in opened if (now - r["opened"]) / 86400 > 9]
    if stale_open: out["health"].append(f"WARN {len(stale_open)} open call(s) older than 9 days: tracking is not closing them ({', '.join(r['symbol'] for r in stale_open)})")
    ms = model.get("stats", {})
    if ms.get("closed", 0) != len(closed) and len(closed) < 300:
        out["health"].append(f"WARN model.stats.closed={ms.get('closed')} but recs.json has {len(closed)} closed calls")
    n_recs = len(desk.get("reco", {}).get("recs", [])) if isinstance(desk.get("reco"), dict) else None
    if n_recs is not None:
        buys = sum(1 for r in desk["reco"]["recs"] if r.get("action") == "BUY")
        if buys == 0 and len(closed) >= MIN_SAMPLE: out["health"].append("NOTE no BUY calls on the board: thresholds may have drifted too high")
        if buys >= 8: out["health"].append(f"NOTE {buys} BUY calls at once: threshold may be too loose for the coin universe")
    out["open"] = len(opened); out["closed"] = len(closed)

    # --- by category ------------------------------------------------------------------------------------------
    bycat = defaultdict(list)
    for r in closed: bycat[r.get("category", "alt")].append(r)
    for cat, rs in bycat.items():
        rets = [r["return"] for r in rs]; wins = [r for r in rs if r["return"] > 0]
        why = defaultdict(int)
        for r in rs: why[r.get("why", "?")] += 1
        peaks = [r.get("peak", 0) for r in rs]; troughs = [r.get("trough", 0) for r in rs]
        cp = model.get("by_category", {}).get(cat, {})
        c = {"n": len(rs), "hit_rate": pct(len(wins), len(rs)), "avg_return": round(st.mean(rets), 2), "median_return": round(st.median(rets), 2),
             "exits": dict(why), "avg_peak": round(st.mean(peaks), 2), "avg_trough": round(st.mean(troughs), 2),
             "target_pct": cp.get("target_pct"), "stop_pct": cp.get("stop_pct"), "max_days": cp.get("max_days"), "buy_threshold": cp.get("buy_threshold")}
        out["categories"][cat] = c
        if len(rs) < MIN_SAMPLE: continue
        n = len(rs)
        # target never reached but peaks are decent -> target too ambitious for the holding period
        if why.get("time", 0) / n > 0.6 and c["avg_peak"] > 0 and cp.get("target_pct") and c["avg_peak"] < cp["target_pct"] * 0.8:
            out["suggestions"].append({"cat": cat, "param": "target_pct", "from": cp["target_pct"], "to": round(max(cp["target_pct"] * 0.8, 3.0), 1),
                                       "why": f"{why['time']}/{n} closed on time with avg peak {c['avg_peak']:+.1f}% vs target {cp['target_pct']}%"})
        # stopped out most of the time while peaks were positive -> stop too tight for the volatility
        if why.get("stop", 0) / n > 0.55 and c["avg_peak"] > 1.0:
            out["suggestions"].append({"cat": cat, "param": "stop_pct", "from": cp["stop_pct"], "to": round(min(cp["stop_pct"] * 1.25, 20.0), 1),
                                       "why": f"{why['stop']}/{n} stopped out although avg peak was {c['avg_peak']:+.1f}%"})
        # losing category: raise the entry bar beyond what the learner does, and demand a stronger whale/smart gate
        if c["hit_rate"] < 40 and c["avg_return"] < 0:
            out["suggestions"].append({"cat": cat, "param": "whale_gate", "from": cp.get("whale_gate", 0.15), "to": round(min(cp.get("whale_gate", 0.15) + 0.05, 0.5), 2),
                                       "why": f"hit rate {c['hit_rate']}%, avg {c['avg_return']:+.1f}%: require stronger whale / top-trader entry"})
        # winning category with a lot of time exits: let it run a little longer
        if c["hit_rate"] >= 60 and why.get("time", 0) / n > 0.5 and cp.get("max_days", 7) < 10:
            out["suggestions"].append({"cat": cat, "param": "max_days", "from": cp.get("max_days"), "to": cp.get("max_days", 7) + 2,
                                       "why": f"hit rate {c['hit_rate']}% but {why['time']}/{n} closed on time: extend the holding window"})

    # --- by entry gate (which signal got us in) ------------------------------------------------------------------
    gate = defaultdict(list)
    for r in closed:
        f = r.get("factors", {}); g = "whale" if f.get("whale", 0) >= f.get("smart", 0) else "smart"
        gate[g].append(r["return"])
    for g, rets in gate.items():
        out["gates"][g] = {"n": len(rets), "hit_rate": pct(sum(1 for x in rets if x > 0), len(rets)), "avg_return": round(st.mean(rets), 2)}

    # --- factor separation: mean factor value in wins minus in losses ---------------------------------------------
    wins = [r for r in closed if r["return"] > 0]; losses = [r for r in closed if r["return"] <= 0]
    if len(wins) >= 4 and len(losses) >= 4:
        for k in FACTORS:
            mw = st.mean(r["factors"].get(k, 0) for r in wins); ml = st.mean(r["factors"].get(k, 0) for r in losses)
            out["factors"][k] = {"wins": round(mw, 2), "losses": round(ml, 2), "edge": round(mw - ml, 2)}
        weighted = {k for cp in model.get("by_category", {}).values() for k in cp.get("weights", {})} or set(FACTORS)
        worst = min(((k, v) for k, v in out["factors"].items() if k in weighted), key=lambda kv: kv[1]["edge"])   # watch-only factors have no weight to cut
        if worst[1]["edge"] < -0.15 and len(closed) >= 2 * MIN_SAMPLE:
            out["suggestions"].append({"cat": "*", "param": f"weights.{worst[0]}", "from": None, "to": "x0.7",
                                       "why": f"{worst[0]} averaged {worst[1]['losses']:+.2f} in losses vs {worst[1]['wins']:+.2f} in wins: it is a contrary signal here"})
    return out

def apply(out, model):
    """Apply suggestions to model.json (bounded, logged). Returns list of applied change strings."""
    applied = []
    bc = model.setdefault("by_category", {})
    for s in out["suggestions"]:
        if s["param"].startswith("weights."):
            k = s["param"].split(".", 1)[1]
            for cat, cp in bc.items():
                old = cp["weights"].get(k)
                if old is None: continue
                cp["weights"][k] = round(max(0.1, old * 0.7), 3); applied.append(f"{cat}.weights.{k} {old:.2f}->{cp['weights'][k]:.2f}")
            continue
        cp = bc.get(s["cat"])
        if not cp: continue
        cp[s["param"]] = s["to"]; applied.append(f"{s['cat']}.{s['param']} {s['from']}->{s['to']}")
    if applied:
        model.setdefault("log", []).append({"ts": int(time.time()), "symbol": "REVIEW", "action": "TUNE", "category": "*", "return": 0.0, "why": "weekly review",
                                            "changes": applied, "buy_threshold": None})
        model["log"] = model["log"][-100:]
    return applied

def report(out, applied):
    L = [f"# Whale Desk review  {time.strftime('%Y-%m-%d %H:%M', time.gmtime(out['ts']))}Z", "",
         f"Open calls: {out['open']}   Closed: {out['closed']}", "", "## Health"] + [f"- {h}" for h in out["health"]] + ["", "## By category"]
    for cat, c in sorted(out["categories"].items()):
        L.append(f"- **{cat}** n={c['n']} hit {c['hit_rate']}% avg {c['avg_return']:+.2f}% (median {c['median_return']:+.2f}%) exits {c['exits']} "
                 f"peak {c['avg_peak']:+.1f}% trough {c['avg_trough']:+.1f}% | target {c['target_pct']} stop {c['stop_pct']} days {c['max_days']} bar {c['buy_threshold']}")
    if not out["categories"]: L.append("- no closed calls yet")
    L += ["", "## By entry gate"] + [f"- {g}: n={v['n']} hit {v['hit_rate']}% avg {v['avg_return']:+.2f}%" for g, v in out["gates"].items()]
    if out["factors"]:
        L += ["", "## Factor edge (mean in wins - mean in losses)"] + [f"- {k}: {v['edge']:+.2f} (wins {v['wins']:+.2f}, losses {v['losses']:+.2f})" for k, v in sorted(out["factors"].items(), key=lambda kv: -kv[1]["edge"])]
    L += ["", "## Suggestions"] + ([f"- {s['cat']}.{s['param']}: {s['from']} -> {s['to']}  ({s['why']})" for s in out["suggestions"]] or ["- none: sample too small or parameters look right"])
    L += ["", "## Applied this run"] + ([f"- {a}" for a in applied] or ["- nothing"])
    return "\n".join(L) + "\n"

def main():
    recs = load(RECS, {"open": [], "closed": []}); model = load(MODEL, {}); desk = load(DESK, {})
    if model:   # make sure every category the sample uses has its parameter block (same seeding as the recommender)
        sys.path.insert(0, HERE); import recommend
        for cat in {r.get("category", "alt") for r in recs.get("closed", []) + recs.get("open", [])} | {"major", "alt", "meme"}:
            recommend.params_for(model, cat)
    want_apply = "--apply" in sys.argv and bool(model)
    if want_apply and "--force" not in sys.argv:
        import backtest
        since = time.time() - backtest.last_tuned(model, "review")
        if since < backtest.TUNE_EVERY:
            print(f"review already tuned the model {since / 86400:.1f} days ago; skipping (use --force to override)"); return
    out = analyse(recs, model, desk)
    applied = apply(out, model) if want_apply else []
    if want_apply:
        model.setdefault("tuned", {})["review"] = int(time.time())
        with open(MODEL, "w") as f: json.dump(model, f, indent=1)
    out["applied"] = applied
    txt = report(out, applied)
    with open(os.path.join(HERE, "review.md"), "w") as f: f.write(txt)
    with open(os.path.join(HERE, "review.json"), "w") as f: json.dump(out, f, indent=1)
    print(txt)

if __name__ == "__main__":
    main()
