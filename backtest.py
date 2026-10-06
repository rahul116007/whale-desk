#!/usr/bin/env python3
"""Whale Desk backtest: replays the desk's own history and asks two questions.

  1. Which factors actually predicted forward returns?  (information coefficient = rank correlation between a
     factor's value and the return over the next 1 / 3 / 5 days, pooled over coin-days)
  2. Would different entry / exit settings have done better?  (grid search of threshold, whale gate, target,
     stop and holding window on a daily simulation, per category)

Data sources, all already in the repo:
  - every committed desk.json (one per refresh) -> all six factors + spot price at that moment  (short history)
  - trades.csv (tracked-whale DEX flow since early September) -> daily whale factor         (longer history)
  - the 90-day price chart in desk.json -> daily closes, momentum factor, forward returns
  - buzz_daily stitched across snapshots -> daily news factor where covered

    python backtest.py            # report only -> backtest.md / backtest.json
    python backtest.py --apply    # also move model.json toward what the evidence supports (bounded, logged)

Honesty note: a few weeks of one market regime over ~18 coins is a small sample. Only consistent, sizeable
effects are acted on, and only part of the way.
"""
import json, os, sys, subprocess, time, math, datetime as dt, csv, itertools
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import recommend, exchanges
from recommend import clamp, score, CATEGORY_PRIORS

DAY = 86400
HORIZONS = (1, 3, 5)

def sh(cmd):
    return subprocess.run(cmd, cwd=HERE, shell=True, capture_output=True, text=True).stdout

def day_of(ts): return int(ts // DAY) * DAY

# ----------------------------------------------------------------------------- data

def ensure_history():
    """GitHub Actions checks out only the latest commit, which leaves the backtest with a single snapshot and nothing
    to measure. Pull enough history to work with (about two months of refreshes) when the clone is shallow."""
    if sh("git rev-parse --is-shallow-repository").strip() == "true":
        print("shallow clone: fetching history for the backtest…")
        subprocess.run("git fetch --quiet --depth=400 origin", cwd=HERE, shell=True, timeout=600)

TUNE_EVERY = 6 * DAY      # --apply acts at most once per this period, however often it is invoked

def last_tuned(model, kind):
    """When model.json was last tuned by 'review' or 'backtest' (falls back to the model log for older files)."""
    t = (model.get("tuned") or {}).get(kind)
    if t: return t
    tag = "REVIEW" if kind == "review" else "BACKTEST"
    return max([l.get("ts", 0) for l in model.get("log", []) if l.get("symbol") == tag] or [0])

def snapshots():
    """[(ts, {symbol: {category, factors, score, action, price, mcap}})] from committed desk.json history."""
    out = []; seen_ts = set()
    for sha in sh("git log --format=%H -- desk.json").split():
        try: d = json.loads(sh(f"git show {sha}:desk.json"))
        except Exception: continue
        ts = d.get("updated")
        if not ts or ts in seen_ts: continue          # a commit that did not refresh carries the previous snapshot again
        seen_ts.add(ts)
        mc = {c["symbol"]: c["market"].get("market_cap") or 0 for c in d.get("coins", [])}
        px = {c["symbol"]: c["market"].get("current_price") for c in d.get("coins", [])}
        rows = {}
        for r in d.get("reco", {}).get("recs", []):
            rows[r["symbol"]] = {"category": r.get("category", "alt"), "factors": r["factors"], "score": r["score"], "action": r["action"],
                                 "price": px.get(r["symbol"]) or r.get("entry"), "mcap": mc.get(r["symbol"], 0)}
        out.append((ts, rows))
    out.sort(key=lambda x: x[0])
    return out

def price_series(desk, snaps):
    """{symbol: sorted [(ts, price)]}: daily chart closes plus every snapshot's spot price."""
    ps = defaultdict(dict)
    for c in desk.get("coins", []):
        for t, p in c.get("chart", {}).get("prices", []): ps[c["symbol"]][int(t)] = p
    for ts, rows in snaps:
        for s, r in rows.items():
            if r["price"]: ps[s][int(ts)] = r["price"]
    return {s: sorted(d.items()) for s, d in ps.items()}

def price_at(series, ts, tol=DAY * 0.75):
    """First price at or after ts (within tolerance), else None."""
    for t, p in series:
        if t >= ts:
            return p if t - ts <= tol else None
    return None

def fwd_return(series, ts, h):
    p0 = price_at(series, ts, tol=DAY * 0.5); p1 = price_at(series, ts + h * DAY)
    return (p1 / p0 - 1) * 100 if p0 and p1 else None

def whale_daily(desk):
    """{symbol: {day_ts: whale factor}} replicating recommend.factors' whale rule on a rolling 7-day window."""
    mc = {c["symbol"]: c["market"].get("market_cap") or 0 for c in desk.get("coins", [])}
    try: wtype = {w["label"]: w.get("type", "") for w in json.load(open(os.path.join(HERE, "config.json")))["wallets"]}
    except Exception: wtype = {}
    ev = defaultdict(list)
    with open(os.path.join(HERE, "trades.csv")) as f:
        for t in csv.DictReader(f):
            try: ts = dt.datetime.strptime(t["time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
            except Exception: continue
            ex = exchanges.in_note(t["note"]) if t["kind"] in ("transfer_in", "transfer_out") else None
            if ex and wtype.get(t["wallet_label"], "").startswith("market_maker"): ex = None   # same rule as coin_desk.whale_flows
            ev[t["symbol"].upper()].append((ts, t["kind"], float(t["usd_now"] or 0), t["wallet_label"], ex))
    out = {}
    for sym, es in ev.items():
        if sym not in mc: continue
        es.sort(); days = sorted({day_of(e[0]) for e in es})
        if not days: continue
        out[sym] = {}
        for d in range(days[0], day_of(time.time()) + DAY, DAY):
            w = [e for e in es if d - 7 * DAY <= e[0] < d + DAY]
            buys = sum(u for _, k, u, _, _ in w if k == "buy"); sells = sum(u for _, k, u, _, _ in w if k == "sell")
            tin = sum(u for _, k, u, _, _ in w if k == "transfer_in"); tout = sum(u for _, k, u, _, _ in w if k == "transfer_out")
            ex_in = sum(u for _, k, u, _, x in w if k == "transfer_in" and x); ex_out = sum(u for _, k, u, _, x in w if k == "transfer_out" and x)
            buyers = {l for _, k, u, l, x in w if k == "buy" or (k == "transfer_in" and x and u >= 25_000)}
            sellers = {l for _, k, u, l, x in w if k == "sell" or (k == "transfer_out" and x and u >= 25_000)}
            scale = max(50_000.0, mc[sym] * 0.0005)
            flow = (buys - sells) + (ex_in - ex_out) + 0.25 * ((tin - ex_in) - (tout - ex_out))
            wf = clamp(flow / scale, -1, 1)
            if len(buyers) >= 2: wf = clamp(wf + 0.3, -1, 1)
            if len(sellers) >= 2: wf = clamp(wf - 0.3, -1, 1)
            if tout > 5 * max(tin, 1) and tout > 250_000: wf = clamp(wf - 0.25, -1, 1)
            out[sym][d] = round(wf, 3)
    return out

def momentum_daily(series):
    """{day_ts: momentum factor} from daily closes (7d / 30d change, one-day spike penalty)."""
    daily = {}
    for t, p in series: daily[day_of(t)] = p
    days = sorted(daily); out = {}
    for i, d in enumerate(days):
        p = daily[d]; p7 = daily.get(d - 7 * DAY); p30 = daily.get(d - 30 * DAY); p1 = daily.get(d - DAY)
        if not p7 or not p30: continue
        c7 = (p / p7 - 1) * 100; c30 = (p / p30 - 1) * 100; c24 = (p / p1 - 1) * 100 if p1 else 0
        m = clamp(c7 / 15 * 0.6 + c30 / 40 * 0.4, -1, 1)
        if c24 > 15: m -= 0.3
        out[d] = round(clamp(m, -1, 1), 3)
    return out

def news_daily(snaps_raw, mcaps):
    """{symbol: {day_ts: news factor}} by stitching buzz_daily across snapshots (max count seen per day)."""
    cnt = defaultdict(dict)
    for d in snaps_raw:
        for c in d.get("coins", []):
            for day, n in c.get("buzz_daily", []):
                cnt[c["symbol"]][int(day)] = max(cnt[c["symbol"]].get(int(day), 0), n)
    out = {}
    for sym, dd in cnt.items():
        mcap = mcaps.get(sym, 0); base = 45 if mcap > 20e9 else 20 if mcap > 2e9 else 8
        out[sym] = {}
        for day in dd:
            n48 = dd.get(day, 0) + dd.get(day - DAY, 0)
            out[sym][day] = round(clamp((n48 - base) / (base * 1.5), -1, 1), 3)
    return out

# ----------------------------------------------------------------------------- statistics

def spearman(xs, ys):
    n = len(xs)
    if n < 8: return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i]); r = [0.0] * n; i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]: j += 1
            for k in range(i, j + 1): r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys); mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry)); vx = sum((a - mx) ** 2 for a in rx); vy = sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx and vy else 0.0

def ic_table(obs):
    """obs: [(factor_name, value, {h: fwd})] -> {factor: {h: (ic, n)}}"""
    by = defaultdict(lambda: defaultdict(list))
    for name, v, fw in obs:
        for h, r in fw.items():
            if r is not None: by[name][h].append((v, r))
    out = {}
    for name, hs in by.items():
        out[name] = {}
        for h, pairs in hs.items():
            xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
            if len(set(xs)) < 3: out[name][h] = (None, len(pairs)); continue
            out[name][h] = (spearman(xs, ys), len(pairs))
    return out

# ----------------------------------------------------------------------------- simulation

def simulate(panel, weights, thr, gate, target, stop, max_days):
    """panel: {symbol: {day_ts: (factors_dict, close)}}. Daily entry when score>=thr and max(whale,smart)>=gate.
    Exit on target / stop / time using daily closes. One open position per coin. Returns list of trade returns."""
    trades = []
    for sym, days in panel.items():
        ds = sorted(days); i = 0
        while i < len(ds):
            f, p0 = days[ds[i]]
            s = score(f, weights)
            if s >= thr and max(f["whale"], f["smart"]) >= gate and p0:
                ret = None
                for j in range(i + 1, min(i + max_days, len(ds) - 1) + 1):
                    p = days[ds[j]][1]
                    if not p: continue
                    r = (p / p0 - 1) * 100
                    if r >= target: ret = (target, "target", j - i); break
                    if r <= -stop: ret = (-stop, "stop", j - i); break
                    ret = (r, "time", j - i)
                if ret is None: i += 1; continue
                trades.append({"symbol": sym, "day": ds[i], "ret": ret[0], "why": ret[1], "held": ret[2]})
                i += ret[2] + 1          # cooldown: re-enter only after the position is closed
            else:
                i += 1
    return trades

def summarize(trades):
    if not trades: return {"n": 0}
    rets = [t["ret"] for t in trades]
    return {"n": len(rets), "hit": round(100 * sum(1 for r in rets if r > 0) / len(rets), 1), "avg": round(sum(rets) / len(rets), 2),
            "total": round(sum(rets), 1), "exits": {k: sum(1 for t in trades if t["why"] == k) for k in ("target", "stop", "time")}}

GRID = {"thr": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5], "gate": [0.0, 0.1, 0.15, 0.2, 0.3],
        "target": [4, 5, 6, 8, 10, 15], "stop": [3, 4, 5, 6, 8, 10], "max_days": [3, 5, 7, 10]}

def grid_search(panel, weights, min_trades=8):
    res = []
    for thr, gate, tg, stp, md in itertools.product(GRID["thr"], GRID["gate"], GRID["target"], GRID["stop"], GRID["max_days"]):
        s = summarize(simulate(panel, weights, thr, gate, tg, stp, md))
        if s["n"] >= min_trades: res.append(({"thr": thr, "gate": gate, "target": tg, "stop": stp, "max_days": md}, s))
    # rank by average return per trade, tie-break on sample size; penalise tiny samples a little
    res.sort(key=lambda x: -(x[1]["avg"] * math.sqrt(min(x[1]["n"], 40))))
    return res

# ----------------------------------------------------------------------------- main

def main():
    apply_ = "--apply" in sys.argv
    desk = json.load(open(os.path.join(HERE, "desk.json")))
    model = json.load(open(os.path.join(HERE, "model.json")))
    for cat in ("major", "alt", "meme"): recommend.params_for(model, cat)
    if apply_ and "--force" not in sys.argv and time.time() - last_tuned(model, "backtest") < TUNE_EVERY:
        print(f"backtest already tuned the model {(time.time() - last_tuned(model, 'backtest')) / DAY:.1f} days ago; skipping (use --force to override)"); return
    ensure_history()
    snaps = snapshots()
    if not snaps: print("no desk.json history to backtest yet"); return
    raw = []
    for sha in sh("git log --format=%H -- desk.json").split()[:60]:
        try: raw.append(json.loads(sh(f"git show {sha}:desk.json")))
        except Exception: pass
    series = price_series(desk, snaps)
    mcaps = {c["symbol"]: c["market"].get("market_cap") or 0 for c in desk["coins"]}
    cats = {c["symbol"]: recommend.category(c) for c in desk["coins"]}
    out = {"ts": int(time.time()), "snapshots": len(snaps), "span_days": round((snaps[-1][0] - snaps[0][0]) / DAY, 1) if len(snaps) > 1 else 0}

    # 1. snapshot IC: all six factors, short history
    obs = []
    for ts, rows in snaps:
        for sym, r in rows.items():
            if sym not in series: continue
            fw = {h: fwd_return(series[sym], ts, h) for h in HORIZONS}
            for k, v in r["factors"].items(): obs.append((k, v, fw))
            obs.append(("score", r["score"], fw))
    out["ic_snapshot"] = {k: {str(h): v for h, v in hs.items()} for k, hs in ic_table(obs).items()}

    # 2. long-history daily panel: whale + momentum (+ news where covered); smart / sentiment / liquidity = 0
    wd = whale_daily(desk); nd = news_daily(raw, mcaps)
    panel = defaultdict(dict); obs2 = []
    for sym, ser in series.items():
        if sym not in cats or cats[sym] == "stable": continue
        md = momentum_daily(ser); daily_close = {day_of(t): p for t, p in ser}
        for d in sorted(md):
            if d < day_of(time.time()) - 35 * DAY: continue
            w = wd.get(sym, {}).get(d); n = nd.get(sym, {}).get(d)
            f = {"whale": w if w is not None else 0.0, "smart": 0.0, "news": n if n is not None else 0.0, "sentiment": 0.0, "momentum": md[d], "liquidity": 0.0}
            panel[sym][d] = (f, daily_close.get(d))
            fw = {h: fwd_return(ser, d, h) for h in HORIZONS}
            obs2.append(("momentum", md[d], fw))
            if w is not None: obs2.append(("whale", w, fw))
            if n is not None: obs2.append(("news", n, fw))
    out["ic_daily"] = {k: {str(h): v for h, v in hs.items()} for k, hs in ic_table(obs2).items()}
    out["panel_days"] = sum(len(v) for v in panel.values())

    # 3. per-category grid search vs the current settings, on the partial-factor panel
    out["grid"] = {}
    for cat in ("major", "alt", "meme"):
        sub = {s: d for s, d in panel.items() if cats.get(s) == cat}
        if not sub: continue
        cp = model["by_category"][cat]; w = cp["weights"]
        base = summarize(simulate(sub, w, cp["buy_threshold"], cp["whale_gate"], cp["target_pct"], cp["stop_pct"], cp["max_days"]))
        uncond = summarize(simulate(sub, w, -9, -9, cp["target_pct"], cp["stop_pct"], cp["max_days"]))
        res = grid_search(sub, w)
        out["grid"][cat] = {"coins": sorted(sub), "current": {"thr": cp["buy_threshold"], "gate": cp["whale_gate"], "target": cp["target_pct"], "stop": cp["stop_pct"], "max_days": cp["max_days"], **base},
                            "unconditional": uncond, "best": [{**g, **s} for g, s in res[:5]]}

    # 4. decide what the evidence supports
    changes = []
    icd, ics = out["ic_daily"], out["ic_snapshot"]
    def consistent(tbl, k, min_n, horizons):
        vals = [(v[0], v[1]) for h, v in tbl.get(k, {}).items() if h in horizons and v[0] is not None and v[1] >= min_n]
        if len(vals) < 2: return 0.0
        if all(v[0] >= 0.05 for v in vals): return min(v[0] for v in vals)
        if all(v[0] <= -0.05 for v in vals): return max(v[0] for v in vals)
        return 0.0
    for k in ("whale", "momentum", "news"):
        e = consistent(icd, k, 150, ("3", "5"))
        if e:
            mult = 1.25 if e > 0 else 0.75
            for cat, cp in model["by_category"].items():
                old = cp["weights"][k]; cp["weights"][k] = round(clamp(old * mult, 0.1, 2.5), 3); changes.append(f"{cat}.weights.{k} {old:.2f}->{cp['weights'][k]:.2f} (daily IC {e:+.2f})")
    daily_done = {c.split()[0].split(".")[-1] for c in changes}
    for k in ("smart", "sentiment", "liquidity", "momentum"):
        e = consistent(ics, k, 100, ("1", "3"))
        if e and k not in daily_done:
            mult = 1.2 if e > 0 else 0.8
            for cat, cp in model["by_category"].items():
                old = cp["weights"][k]; cp["weights"][k] = round(clamp(old * mult, 0.1, 2.5), 3); changes.append(f"{cat}.weights.{k} {old:.2f}->{cp['weights'][k]:.2f} (snapshot IC {e:+.2f})")
    # second-opinion factors (positioning.py) start with no weight. One earns a starting weight once it has two weeks
    # of history and a consistent positive rank correlation; a live one that turns contrary is cut and then retired.
    seen = {}
    for ts, rows in snaps:
        for r in rows.values():
            for k in r["factors"]:
                if k in recommend.SHADOW: seen[k] = min(seen.get(k, ts), ts)
    out["second_opinions"] = {}
    for k in recommend.SHADOW:
        days = round((snaps[-1][0] - seen[k]) / DAY, 1) if k in seen and snaps else 0.0
        e = consistent(ics, k, 300, ("1", "3", "5"))
        live = any(k in cp["weights"] for cp in model["by_category"].values())
        verdict = "watching"
        if days >= 14 and e >= 0.10 and not live:
            for cat, cp in model["by_category"].items(): cp["weights"][k] = 0.3
            changes.append(f"*.weights.{k} promoted from watch-only to 0.30 ({days:.0f} days of history, snapshot IC {e:+.2f})"); verdict = "promoted"
        elif live and e:
            for cat, cp in model["by_category"].items():
                if k not in cp["weights"]: continue
                old = cp["weights"][k]; new = round(clamp(old * (1.2 if e > 0 else 0.8), 0.1, 2.5), 3)
                if e < 0 and new <= 0.15:
                    del cp["weights"][k]; changes.append(f"{cat}.weights.{k} {old:.2f}->retired to watch-only (snapshot IC {e:+.2f})")
                else:
                    cp["weights"][k] = new; changes.append(f"{cat}.weights.{k} {old:.2f}->{new:.2f} (snapshot IC {e:+.2f})")
            verdict = "live"
        elif live: verdict = "live"
        out["second_opinions"][k] = {"days": days, "ic": round(e, 3), "status": verdict}
    # the grid runs on a panel without smart / sentiment / liquidity history, so it is reported for reading, not applied
    out["changes"] = changes
    if apply_:
        if changes:
            model.setdefault("log", []).append({"ts": int(time.time()), "symbol": "BACKTEST", "action": "TUNE", "category": "*", "return": 0.0, "why": "backtest", "changes": changes, "buy_threshold": None})
            model["log"] = model["log"][-100:]
        model.setdefault("tuned", {})["backtest"] = int(time.time())
        with open(os.path.join(HERE, "model.json"), "w") as f: json.dump(model, f, indent=1)
    out["applied"] = bool(apply_ and changes)

    # 5. report
    L = [f"# Whale Desk backtest  {time.strftime('%Y-%m-%d %H:%M', time.gmtime(out['ts']))}Z", "",
         f"{out['snapshots']} refresh snapshots over {out['span_days']} days; {out['panel_days']} coin-days in the daily panel.", "",
         "## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)", "",
         "Daily panel (whale from trades.csv, momentum from prices, news where covered):"]
    for k, hs in icd.items(): L.append("- " + k + ": " + ", ".join(f"{h}d {('%+.2f' % v[0]) if v[0] is not None else 'n/a'} (n={v[1]})" for h, v in sorted(hs.items())))
    L += ["", "Refresh snapshots (every factor + the combined score, short history):"]
    for k, hs in ics.items(): L.append("- " + k + ": " + ", ".join(f"{h}d {('%+.2f' % v[0]) if v[0] is not None else 'n/a'} (n={v[1]})" for h, v in sorted(hs.items())))
    L += ["", "## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)", "",
          "Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better."]
    for k, v in out["second_opinions"].items():
        L.append(f"- {k}: {v['status']}, {v['days']} days of history" + (f", consistent IC {v['ic']:+.2f}" if v["ic"] else ", no consistent edge yet"))
    L += ["", "## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)"]
    for cat, g in out["grid"].items():
        c = g["current"]; u = g["unconditional"]
        L += ["", f"### {cat}  ({', '.join(g['coins'])})",
              f"- current settings: thr {c['thr']} gate {c['gate']} target {c['target']} stop {c['stop']} days {c['max_days']} -> n={c.get('n',0)} hit {c.get('hit')}% avg {c.get('avg')}% exits {c.get('exits')}",
              f"- buy everything, same exits: n={u.get('n',0)} hit {u.get('hit')}% avg {u.get('avg')}%"]
        for b in g["best"][:3]: L.append(f"- grid: thr {b['thr']} gate {b['gate']} target {b['target']} stop {b['stop']} days {b['max_days']} -> n={b['n']} hit {b['hit']}% avg {b['avg']:+.2f}% exits {b['exits']}")
    L += ["", "## Changes " + ("applied" if out["applied"] else "suggested (not applied)")] + ([f"- {c}" for c in changes] or ["- none: nothing consistent enough to act on"])
    txt = "\n".join(L) + "\n"
    with open(os.path.join(HERE, "backtest.md"), "w") as f: f.write(txt)
    with open(os.path.join(HERE, "backtest.json"), "w") as f: json.dump(out, f, indent=1)
    print(txt)

if __name__ == "__main__":
    main()
