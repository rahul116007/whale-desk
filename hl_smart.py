"""
Hyperliquid smart money
-----------------------
Pulls Hyperliquid's public leaderboard (the same data Nansen's Hyperliquid pages are built on),
picks the traders worth following, reads their open positions and last 7 days of fills, and
aggregates per coin: how many top traders are long vs short, net notional, and what they opened
or closed in the last 48 hours. No login, no key.

    python3 hl_smart.py            # refresh hl.json and print the summary
    python3 hl_smart.py add 0x... "label"   # pin a trader (e.g. from Nansen) so it is always followed

Used by coin_desk.py as the "smart money" factor and the Smart Money tab.
"""
import json, os, sys, time, datetime as dt
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
LB_CACHE = os.path.join(HERE, "hl_leaderboard.json")
HL_JSON = os.path.join(HERE, "hl.json")
INFO = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
H = {"User-Agent": "Mozilla/5.0 whale-desk/1.0", "Content-Type": "application/json"}

DEFAULTS = {"hl_top_n": 40, "hl_min_account": 250_000, "hl_min_month_roi": 0.05, "hl_max_turnover": 100, "hl_traders": []}

def load_json(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def save_json(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, p)

def cfg_get():
    c = load_json(CONFIG_PATH, {})
    for k, v in DEFAULTS.items(): c.setdefault(k, v)
    return c

def info(body, retries=3):
    for i in range(retries):
        try:
            r = requests.post(INFO, json=body, headers=H, timeout=40)
            if r.status_code == 429: time.sleep(5 * (i + 1)); continue
            if r.status_code == 200: return r.json()
            return None
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def fnum(x):
    try: return float(x)
    except Exception: return 0.0

# ----------------------------------------------------------------------------- leaderboard

def leaderboard(max_age=6 * 3600):
    c = load_json(LB_CACHE, {})
    if c and time.time() - c.get("_ts", 0) < max_age:
        return c["rows"]
    r = requests.get(LEADERBOARD, headers=H, timeout=120)
    rows = r.json().get("leaderboardRows", [])
    slim = []
    for x in rows:
        w = {k: v for k, v in x.get("windowPerformances", [])}
        slim.append({"addr": x["ethAddress"].lower(), "name": x.get("displayName"), "value": fnum(x.get("accountValue")),
                     "d_pnl": fnum(w.get("day", {}).get("pnl")), "w_pnl": fnum(w.get("week", {}).get("pnl")), "w_roi": fnum(w.get("week", {}).get("roi")),
                     "w_vlm": fnum(w.get("week", {}).get("vlm")), "m_pnl": fnum(w.get("month", {}).get("pnl")), "m_roi": fnum(w.get("month", {}).get("roi")),
                     "m_vlm": fnum(w.get("month", {}).get("vlm")), "a_pnl": fnum(w.get("allTime", {}).get("pnl")), "a_roi": fnum(w.get("allTime", {}).get("roi"))})
    save_json(LB_CACHE, {"_ts": int(time.time()), "rows": slim})
    return slim

def pick_traders(rows, cfg):
    """Consistent, sizeable, not market-making: positive week, month and all-time PnL, decent monthly ROI,
    weekly turnover under N x account value, then ranked by month PnL x ROI."""
    out = []
    for r in rows:
        if r["value"] < cfg["hl_min_account"]: continue
        if r["m_roi"] < cfg["hl_min_month_roi"] or r["w_pnl"] <= 0 or r["a_pnl"] <= 0: continue
        if r["value"] and r["w_vlm"] / r["value"] > cfg["hl_max_turnover"]: continue
        r["score"] = r["m_pnl"] * min(r["m_roi"], 2.0) ** 0.5
        out.append(r)
    out.sort(key=lambda r: -r["score"])
    top = out[:cfg["hl_top_n"]]
    have = {r["addr"] for r in top}
    for t in cfg.get("hl_traders", []):
        a = t["address"].lower()
        if a in have: continue
        row = next((r for r in rows if r["addr"] == a), None) or {"addr": a, "value": 0, "d_pnl": 0, "w_pnl": 0, "w_roi": 0, "w_vlm": 0, "m_pnl": 0, "m_roi": 0, "m_vlm": 0, "a_pnl": 0, "a_roi": 0}
        row = dict(row); row["name"] = t.get("label") or row.get("name"); row["pinned"] = True; row["score"] = 0
        top.append(row)
    return top

# ----------------------------------------------------------------------------- positions + fills

def positions(addr):
    j = info({"type": "clearinghouseState", "user": addr}) or {}
    out = []
    for ap in j.get("assetPositions", []):
        p = ap.get("position") or {}
        szi = fnum(p.get("szi"))
        if not szi: continue
        out.append({"coin": p.get("coin"), "side": "long" if szi > 0 else "short", "size": abs(szi), "notional": fnum(p.get("positionValue")),
                    "entry": fnum(p.get("entryPx")), "upnl": fnum(p.get("unrealizedPnl")), "lev": (p.get("leverage") or {}).get("value"),
                    "liq": fnum(p.get("liquidationPx")) if p.get("liquidationPx") else None})
    return out, fnum((j.get("marginSummary") or {}).get("accountValue"))

def fills(addr, days=7):
    start = int((time.time() - days * 86400) * 1000)
    j = info({"type": "userFillsByTime", "user": addr, "startTime": start}) or []
    out = []
    for f in j:
        d = f.get("dir") or ""
        out.append({"coin": f.get("coin"), "dir": d, "px": fnum(f.get("px")), "sz": fnum(f.get("sz")), "ts": int(f.get("time", 0) / 1000),
                    "pnl": fnum(f.get("closedPnl")), "notional": fnum(f.get("px")) * fnum(f.get("sz"))})
    return out

def norm_coin(c):
    """Hyperliquid names: kPEPE / kSHIB / kBONK are 1000x units; strip the k for matching."""
    if not c: return c
    return c[1:] if c.startswith("k") and c[1:].isupper() else c

# ----------------------------------------------------------------------------- aggregate

def run(cfg=None, verbose=True):
    cfg = cfg or cfg_get()
    rows = leaderboard()
    top = pick_traders(rows, cfg)
    if verbose: print(f"[hl] leaderboard {len(rows)} accounts, following {len(top)} traders")
    now = int(time.time()); cut48 = now - 48 * 3600
    per_coin = {}
    traders = []
    for i, t in enumerate(top):
        pos, value = positions(t["addr"])
        fl = fills(t["addr"])
        time.sleep(0.25)
        t = dict(t); t["value"] = value or t["value"]; t["positions"] = sorted(pos, key=lambda p: -p["notional"])[:8]
        t["fills48"] = sum(1 for f in fl if f["ts"] >= cut48); t["realized7d"] = round(sum(f["pnl"] for f in fl), 2)
        traders.append(t)
        for p in pos:
            c = per_coin.setdefault(norm_coin(p["coin"]), {"coin": norm_coin(p["coin"]), "hl_coin": p["coin"], "longs": 0, "shorts": 0, "long_ntl": 0.0, "short_ntl": 0.0,
                                                          "open_long_48h": 0.0, "open_short_48h": 0.0, "close_long_48h": 0.0, "close_short_48h": 0.0, "opens_7d": 0.0, "closes_7d": 0.0,
                                                          "entries": [], "exits": [], "holders": []})
            if p["side"] == "long": c["longs"] += 1; c["long_ntl"] += p["notional"]
            else: c["shorts"] += 1; c["short_ntl"] += p["notional"]
            c["holders"].append({"who": t.get("name") or t["addr"][:6] + "…" + t["addr"][-4:], "side": p["side"], "notional": p["notional"], "entry": p["entry"], "upnl": p["upnl"], "lev": p["lev"]})
        # fills: net flow per coin, signed toward long
        agg = {}
        for f in fl:
            c = per_coin.setdefault(norm_coin(f["coin"]), {"coin": norm_coin(f["coin"]), "hl_coin": f["coin"], "longs": 0, "shorts": 0, "long_ntl": 0.0, "short_ntl": 0.0,
                                                          "open_long_48h": 0.0, "open_short_48h": 0.0, "close_long_48h": 0.0, "close_short_48h": 0.0, "opens_7d": 0.0, "closes_7d": 0.0,
                                                          "entries": [], "exits": [], "holders": []})
            d = f["dir"]; n = f["notional"]
            if d.startswith("Open"): c["opens_7d"] += n if "Long" in d else -n
            elif d.startswith("Close"): c["closes_7d"] += n if "Long" in d else -n
            if f["ts"] >= cut48:
                if d == "Open Long": c["open_long_48h"] += n
                elif d == "Open Short": c["open_short_48h"] += n
                elif d == "Close Long": c["close_long_48h"] += n
                elif d == "Close Short": c["close_short_48h"] += n
                k = (f["coin"], d)
                a = agg.setdefault(k, {"who": t.get("name") or t["addr"][:6] + "…" + t["addr"][-4:], "coin": norm_coin(f["coin"]), "dir": d, "notional": 0.0, "ts": f["ts"], "px": f["px"], "pnl": 0.0})
                a["notional"] += n; a["pnl"] += f["pnl"]; a["ts"] = max(a["ts"], f["ts"])
        for (coin, d), a in agg.items():
            if a["notional"] < 25_000: continue
            c = per_coin[norm_coin(coin)]
            (c["entries"] if d.startswith("Open") else c["exits"]).append(a)
        if verbose and (i + 1) % 10 == 0: print(f"  … {i + 1}/{len(top)} traders read")
    coins = []
    for c in per_coin.values():
        c["net_ntl"] = c["long_ntl"] - c["short_ntl"]
        c["flow48"] = c["open_long_48h"] - c["open_short_48h"] - c["close_long_48h"] + c["close_short_48h"]   # signed toward long
        c["entries"].sort(key=lambda a: -a["notional"]); c["exits"].sort(key=lambda a: -a["notional"])
        c["entries"] = c["entries"][:12]; c["exits"] = c["exits"][:12]
        c["holders"].sort(key=lambda h: -h["notional"]); c["holders"] = c["holders"][:15]
        # smart-money factor in [-1, 1]: crowding (who is long vs short) + fresh 48h flow
        n = c["longs"] + c["shorts"]
        crowd = (c["longs"] - c["shorts"]) / n if n else 0.0
        flow = max(-1.0, min(1.0, c["flow48"] / max(2e6, 0.25 * (c["long_ntl"] + c["short_ntl"]) or 2e6)))
        c["factor"] = round(max(-1.0, min(1.0, 0.55 * crowd + 0.45 * flow)), 3)
        coins.append(c)
    coins.sort(key=lambda c: -(c["long_ntl"] + c["short_ntl"]))
    out = {"updated": now, "n_traders": len(traders), "traders": sorted(traders, key=lambda t: -t["m_pnl"]), "coins": coins,
           "params": {k: cfg[k] for k in ("hl_top_n", "hl_min_account", "hl_min_month_roi", "hl_max_turnover")}}
    save_json(HL_JSON, out)
    if verbose:
        print(f"[hl] {len(coins)} coins with top-trader exposure. Most crowded:")
        for c in coins[:12]:
            print(f"  {c['coin']:<8} long {c['longs']:>2} / short {c['shorts']:>2}   net ${c['net_ntl']/1e6:+.1f}M   48h flow ${c['flow48']/1e6:+.2f}M   factor {c['factor']:+.2f}")
    return out

def add_trader(addr, label):
    c = load_json(CONFIG_PATH, {})
    lst = c.setdefault("hl_traders", [])
    if any(t["address"].lower() == addr.lower() for t in lst): print("already pinned"); return
    lst.append({"address": addr, "label": label or addr[:10]})
    # keep config format (wallets one per line)
    body = {k: v for k, v in c.items() if k != "wallets"}
    s = json.dumps(body, indent=2)[:-2] + ',\n  "wallets": [\n' + ",\n".join("    " + json.dumps(w) for w in c.get("wallets", [])) + "\n  ]\n}\n"
    with open(CONFIG_PATH, "w") as f: f.write(s)
    print(f"pinned {label or addr} ({len(lst)} pinned traders)")

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        add_trader(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    else:
        run()
