"""
Recommendation engine + performance tracker for coin_desk.py

Every refresh:
  1. score each focus coin on five factors (whale flow, news buzz, crowd sentiment, momentum, liquidity)
     using the current factor weights in model.json
  2. turn the score into BUY / WATCH / SELL with entry, target, stop and a written thesis
  3. open a tracked recommendation when BUY or SELL fires (one per coin at a time, with a cooldown)
  4. mark open recommendations to market; close them on target, stop or after max_days
  5. when one closes, nudge the factor weights toward whatever was present in winners and away from
     whatever was present in losers, and adapt the BUY threshold to the recent hit rate

Everything is written to recs.json (history) and model.json (weights + stats) next to the scripts.
This is a mechanical system for a discretionary trader to argue with, not advice.
"""
import json, os, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
RECS = os.path.join(HERE, "recs.json")
MODEL = os.path.join(HERE, "model.json")

STABLE_SYMS = {"USDT", "USDC", "DAI", "USDS", "USDE", "FDUSD", "TUSD", "PYUSD", "FRAX", "LUSD", "GUSD", "USDP", "USD1", "CRVUSD", "GHO", "USYC", "SUSDS", "USDG", "USD0", "RLUSD", "XAUT", "PAXG"}

def category(coin):
    """stable (never recommended) / major / meme / alt. Memes come from CoinGecko's own category tags."""
    sym = (coin.get("symbol") or "").upper()
    cats = [c.lower() for c in (coin.get("info", {}).get("categories") or [])]
    is_stable = any((("stablecoin" in c or "stablecoins" in c) and not any(x in c for x in ("protocol", "ecosystem", "issuer", "governance"))) or "tokenized gold" in c for c in cats)
    if sym in STABLE_SYMS or is_stable: return "stable"
    if any("meme" in c for c in cats): return "meme"
    if (coin.get("market", {}).get("market_cap") or 0) > 50e9: return "major"
    return "alt"

# Different priors per bucket. Memes: smart money, buzz and momentum drive the move, crowd sentiment is noise,
# and targets/stops are wider because they move 15% before lunch. Majors: whale flow on DEXs barely registers
# against ETF and CEX flow, so Hyperliquid positioning and trend carry more, and targets are tight.
CATEGORY_PRIORS = {
    "major": {"weights": {"whale": 0.5, "smart": 1.1, "news": 0.4, "sentiment": 0.3, "momentum": 0.9, "liquidity": 0.1},
              "buy_threshold": 0.30, "sell_threshold": -0.28, "whale_gate": 0.15, "target_pct": 5.0, "stop_pct": 4.0, "max_days": 7},
    "alt":   {"weights": {"whale": 1.0, "smart": 0.9, "news": 0.6, "sentiment": 0.5, "momentum": 0.8, "liquidity": 0.4},
              "buy_threshold": 0.35, "sell_threshold": -0.30, "whale_gate": 0.15, "target_pct": 8.0, "stop_pct": 6.0, "max_days": 7},
    "meme":  {"weights": {"whale": 1.2, "smart": 1.0, "news": 0.9, "sentiment": 0.2, "momentum": 1.0, "liquidity": 0.6},
              "buy_threshold": 0.40, "sell_threshold": -0.25, "whale_gate": 0.20, "target_pct": 15.0, "stop_pct": 10.0, "max_days": 5},
}

DEFAULT_MODEL = {
    "weights": {"whale": 1.0, "smart": 0.9, "news": 0.6, "sentiment": 0.5, "momentum": 0.8, "liquidity": 0.4},
    "buy_threshold": 0.35, "sell_threshold": -0.30, "whale_gate": 0.15, "target_pct": 8.0, "stop_pct": 6.0, "max_days": 7,
    "cooldown_days": 2, "learning_rate": 0.15, "by_category": {},
    "stats": {"closed": 0, "wins": 0, "losses": 0, "sum_return": 0.0, "best": 0.0, "worst": 0.0},
    "log": [],
}

def _load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return json.loads(json.dumps(d))

def _save(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f, indent=1)
    os.replace(tmp, p)

def clamp(v, lo, hi): return max(lo, min(hi, v))

# ----------------------------------------------------------------------------- factors

def factors(coin):
    """Each factor is in [-1, 1]. Positive = supportive of going long."""
    m, i, w, b, pairs = coin["market"], coin["info"], coin["whales"], coin["buzz"], coin.get("pairs") or []
    mcap = m.get("market_cap") or 0
    # whale: net DEX flow scaled by market cap (a $500k buy matters on a $1B coin, not on BTC), plus clusters
    scale = max(50_000.0, mcap * 0.0005)            # 0.05% of mcap counts as a full signal
    whale = clamp(w["net"] / scale, -1, 1)
    if len(w["buyers"]) >= 2: whale = clamp(whale + 0.3, -1, 1)
    if len(w["sellers"]) >= 2: whale = clamp(whale - 0.3, -1, 1)
    if w["transfer_out"] > 5 * max(w["transfer_in"], 1) and w["transfer_out"] > 250_000: whale = clamp(whale - 0.25, -1, 1)
    # news: buzz relative to what is normal for this coin's size; big caps always have coverage so we damp them
    base = 45 if mcap > 20e9 else 20 if mcap > 2e9 else 8
    news = clamp((b["news48"] + 1.5 * b["reddit48"] + 2 * b["x"] - base) / (base * 1.5), -1, 1)
    # sentiment: CoinGecko vote, centred on 78% (the vote skews bullish on almost everything)
    su = i.get("sentiment_up")
    sentiment = clamp((su - 78) / 18, -1, 1) if su else 0.0
    # momentum: 7d and 30d, with a penalty for a one-day spike (chasing)
    c24 = m.get("price_change_percentage_24h") or 0; c7 = m.get("price_change_percentage_7d_in_currency") or 0
    c30 = m.get("price_change_percentage_30d_in_currency") or 0
    momentum = clamp(c7 / 15 * 0.6 + c30 / 40 * 0.4, -1, 1)
    if c24 > 15: momentum -= 0.3
    momentum = clamp(momentum, -1, 1)
    # liquidity: depth of the top DEX pool vs a $1M reference; CEX-only majors get neutral
    liq = pairs[0]["liq"] if pairs else None
    liquidity = 0.0 if liq is None else clamp((liq - 1e6) / 5e6, -1, 0.5)
    if pairs and pairs[0]["buys24"] > 1.5 * max(pairs[0]["sells24"], 1): liquidity += 0.2
    # smart money: Hyperliquid top-trader positioning + 48h flow (hl_smart.py); 0 when none of them touch the coin
    sm = coin.get("smart") or {}
    smart = sm.get("factor", 0.0) if (sm.get("longs", 0) + sm.get("shorts", 0)) >= 2 else 0.0
    return {"whale": round(whale, 3), "smart": round(smart, 3), "news": round(news, 3), "sentiment": round(sentiment, 3),
            "momentum": round(momentum, 3), "liquidity": round(clamp(liquidity, -1, 1), 3)}

def score(f, weights):
    tot = sum(abs(v) for v in weights.values()) or 1
    return sum(weights[k] * f[k] for k in weights) / tot

# ----------------------------------------------------------------------------- recommendation

def reasons(coin, f):
    w, b, i, m = coin["whales"], coin["buzz"], coin["info"], coin["market"]
    out = []
    if f["whale"] > 0.2: out.append(f"tracked whales net bought {_usd(w['net'])} over 7d" + (f" ({', '.join(w['buyers'][:3])})" if w["buyers"] else ""))
    if f["whale"] < -0.2: out.append(f"tracked whales net sold {_usd(-w['net'])} over 7d" + (f" ({', '.join(w['sellers'][:3])})" if w["sellers"] else ""))
    sm = coin.get("smart") or {}
    if f["smart"] > 0.25: out.append(f"Hyperliquid top traders: {sm.get('longs',0)} long / {sm.get('shorts',0)} short, net {_usd(sm.get('net_ntl',0))}, 48h flow {_usd(sm.get('flow48',0))}")
    if f["smart"] < -0.25: out.append(f"Hyperliquid top traders lean short: {sm.get('longs',0)} long / {sm.get('shorts',0)} short, net {_usd(sm.get('net_ntl',0))}")
    if w["transfer_out"] > 250_000 and w["transfer_out"] > 5 * max(w["transfer_in"], 1): out.append(f"{_usd(w['transfer_out'])} left tracked wallets, often an exchange deposit before a sale")
    if f["news"] > 0.3: out.append(f"coverage is running hot: {b['news48']} stories, {b['reddit48']} Reddit posts in 48h")
    if f["news"] < -0.3: out.append("coverage is unusually quiet for a coin this size")
    if f["sentiment"] > 0.4: out.append(f"crowd vote {i.get('sentiment_up'):.0f}% bullish")
    if f["sentiment"] < -0.3: out.append(f"crowd vote only {i.get('sentiment_up'):.0f}% bullish")
    c7 = m.get("price_change_percentage_7d_in_currency") or 0; c30 = m.get("price_change_percentage_30d_in_currency") or 0
    if f["momentum"] > 0.3: out.append(f"trend is up ({c7:+.1f}% 7d, {c30:+.1f}% 30d)")
    if f["momentum"] < -0.3: out.append(f"trend is down ({c7:+.1f}% 7d, {c30:+.1f}% 30d)")
    if (m.get("price_change_percentage_24h") or 0) > 15: out.append("already up >15% today; chasing risk")
    if f["liquidity"] < -0.5: out.append("thin DEX liquidity; slippage and manipulation risk")
    return out

def _usd(v):
    v = float(v or 0)
    if abs(v) >= 1e6: return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.1f}k"
    return f"${v:,.0f}"

def params_for(model, cat):
    """Per-category weights/thresholds, seeded from the priors and learned separately from then on."""
    bc = model.setdefault("by_category", {})
    if cat not in bc:
        bc[cat] = json.loads(json.dumps(CATEGORY_PRIORS.get(cat, CATEGORY_PRIORS["alt"])))
        bc[cat]["stats"] = {"closed": 0, "wins": 0, "losses": 0, "sum_return": 0.0}
    return bc[cat]

def recommend(coin, model):
    f = factors(coin)
    cat = category(coin)
    if cat == "stable":
        price = coin["market"].get("current_price") or 0
        return {"symbol": coin["symbol"], "id": coin["id"], "name": coin["name"], "action": "SKIP", "category": cat, "score": 0.0, "confidence": 0,
                "factors": f, "reasons": ["stablecoin / gold token: parked money, not a trade"], "invalidation": [], "entry": price, "target": None, "stop": None, "sizing": ""}
    model = {**model, **{k: v for k, v in params_for(model, cat).items() if k != "stats"}}   # category view of the model
    s = score(f, model["weights"])
    price = coin["market"].get("current_price") or 0
    # whale flow is the gate: no tracked-wallet buying, no BUY; heavy tracked selling is a SELL on its own
    entry = max(f["whale"], f["smart"])          # either on-chain whales buying or HL top traders long/adding
    exit_ = min(f["whale"], f["smart"])
    if s >= model["buy_threshold"] and entry >= model.get("whale_gate", 0.15):
        action = "BUY"
    elif (s <= model["sell_threshold"] and exit_ <= -0.1) or exit_ < -0.6:
        action = "SELL"
    else:
        action = "WATCH"
    conf = int(clamp(abs(s) * 140, 5, 95))
    rs = reasons(coin, f)
    invalid = []
    if action == "BUY":
        invalid = [f"stop at {price * (1 - model['stop_pct']/100):.6g} ({-model['stop_pct']:.0f}%)", "a tracked whale full-exit alert", "a cluster of sells on the whale feed"]
    elif action == "SELL":
        invalid = [f"price back above {price * (1 + model['stop_pct']/100):.6g} (+{model['stop_pct']:.0f}%)", "two or more tracked wallets buying"]
    else:
        gap = model["buy_threshold"] - s
        invalid = []
        if entry < model.get("whale_gate", 0.15): invalid.append("needs whale or top-trader entry (whale %+.2f, smart money %+.2f, gate %.2f)" % (f["whale"], f["smart"], model.get("whale_gate", 0.15)))
        if gap > 0: invalid.append(f"score {s:+.2f}, needs {gap:+.2f} more")
        if not invalid: invalid.append("close: one more supportive factor tips it")
    return {"symbol": coin["symbol"], "id": coin["id"], "name": coin["name"], "action": action, "category": cat, "score": round(s, 3),
            "confidence": conf, "factors": f, "reasons": rs or ["nothing stands out either way"], "invalidation": invalid,
            "entry": price, "target": price * (1 + model["target_pct"]/100) if action == "BUY" else price * (1 - model["target_pct"]/100) if action == "SELL" else None,
            "stop": price * (1 - model["stop_pct"]/100) if action == "BUY" else price * (1 + model["stop_pct"]/100) if action == "SELL" else None,
            "sizing": "small: high confidence still means a coin-flip with an edge" if conf < 50 else "normal: several factors agree" if conf < 75 else "normal, but crowded: take profit into strength"}

# ----------------------------------------------------------------------------- tracking + learning

def _ret(rec, price):
    if not rec["entry"] or not price: return 0.0
    r = (price / rec["entry"] - 1) * 100
    return r if rec["action"] == "BUY" else -r

def update_tracking(recs_by_symbol, prices, model):
    """recs_by_symbol: {symbol: recommendation}; prices: {symbol: current price}. Returns (recs_state, closed_now)."""
    state = _load(RECS, {"open": [], "closed": []})
    now = int(time.time()); closed_now = []
    # 1. mark to market / close
    still = []
    for r in state["open"]:
        p = prices.get(r["symbol"])
        if p:
            r["last"] = p; r["return"] = round(_ret(r, p), 2)
            r["peak"] = max(r.get("peak", 0.0), r["return"]); r["trough"] = min(r.get("trough", 0.0), r["return"])
        age = (now - r["opened"]) / 86400
        why = None
        cp = params_for(model, r.get("category", "alt"))
        if r["return"] >= cp["target_pct"]: why = "target"
        elif r["return"] <= -cp["stop_pct"]: why = "stop"
        elif age >= cp["max_days"]: why = "time"
        if why:
            r["closed"] = now; r["why"] = why; r["outcome"] = "win" if r["return"] > 0 else "loss"
            state["closed"].append(r); closed_now.append(r); learn(r, model)
        else:
            still.append(r)
    state["open"] = still
    # 2. open new ones
    open_syms = {r["symbol"] for r in state["open"]}
    recent_close = {r["symbol"]: r["closed"] for r in state["closed"]}
    for sym, rec in recs_by_symbol.items():
        if rec["action"] not in ("BUY", "SELL") or sym in open_syms: continue
        if now - recent_close.get(sym, 0) < model["cooldown_days"] * 86400: continue
        state["open"].append({"symbol": sym, "id": rec["id"], "name": rec["name"], "action": rec["action"], "category": rec.get("category", "alt"), "opened": now, "entry": rec["entry"],
                              "target": rec["target"], "stop": rec["stop"], "score": rec["score"], "confidence": rec["confidence"],
                              "factors": rec["factors"], "reasons": rec["reasons"], "last": rec["entry"], "return": 0.0, "peak": 0.0, "trough": 0.0})
    state["closed"] = state["closed"][-300:]
    _save(RECS, state)
    return state, closed_now

def learn(rec, model):
    """Nudge the category's weights toward factors present in a win, away from those present in a loss."""
    cat = rec.get("category", "alt"); cp = params_for(model, cat)
    lr = model["learning_rate"]; sign = 1 if rec["action"] == "BUY" else -1
    ret = clamp(rec["return"] / cp["target_pct"], -1.5, 1.5)   # normalised outcome
    changes = []
    for k, v in rec["factors"].items():
        if abs(v) < 0.15 or k not in cp["weights"]: continue
        delta = lr * (v * sign) * ret
        old = cp["weights"][k]; new = clamp(old + delta, 0.1, 2.5)
        if abs(new - old) > 1e-4:
            cp["weights"][k] = round(new, 3); changes.append(f"{cat}.{k} {old:.2f}→{new:.2f}")
    cs = cp["stats"]; cs["closed"] += 1; cs["sum_return"] += rec["return"]; cs["wins" if rec["return"] > 0 else "losses"] += 1
    st = model["stats"]; st["closed"] += 1; st["sum_return"] += rec["return"]
    st["wins" if rec["outcome"] == "win" else "losses"] += 1
    st["best"] = max(st["best"], rec["return"]); st["worst"] = min(st["worst"], rec["return"])
    # adaptive threshold: tighten when the hit rate is poor, loosen when it is good (only once there is a sample)
    recent = [r for r in _load(RECS, {"closed": []})["closed"][-30:] if r.get("category", "alt") == cat][-10:] + [rec]
    if len(recent) >= 5:
        hr = sum(1 for r in recent if r.get("outcome") == "win") / len(recent)
        if hr < 0.45: cp["buy_threshold"] = round(clamp(cp["buy_threshold"] + 0.04, 0.2, 0.7), 3)
        elif hr > 0.6: cp["buy_threshold"] = round(clamp(cp["buy_threshold"] - 0.02, 0.2, 0.7), 3)
    model["log"].append({"ts": int(time.time()), "symbol": rec["symbol"], "action": rec["action"], "category": cat, "return": rec["return"], "why": rec["why"],
                         "changes": changes, "buy_threshold": cp["buy_threshold"]})
    model["log"] = model["log"][-100:]

def run(coins):
    """Entry point used by coin_desk.refresh: returns the block the dashboard renders."""
    model = _load(MODEL, DEFAULT_MODEL)
    for k, v in DEFAULT_MODEL.items(): model.setdefault(k, v)
    for k, v in DEFAULT_MODEL["weights"].items(): model["weights"].setdefault(k, v)
    recs = {c["symbol"]: recommend(c, model) for c in coins}
    prices = {c["symbol"]: c["market"].get("current_price") or 0 for c in coins}
    state, closed_now = update_tracking(recs, prices, model)
    _save(MODEL, model)
    st = model["stats"]; n = st["closed"] or 1
    for c in coins:
        if category(c) != "stable": params_for(model, category(c))
    _save(MODEL, model)
    return {"recs": sorted([r for r in recs.values() if r["action"] != "SKIP"], key=lambda r: -r["score"]), "skipped": [r["symbol"] for r in recs.values() if r["action"] == "SKIP"],
            "open": state["open"], "closed": state["closed"][-40:][::-1],
            "closed_now": closed_now, "model": {"weights": model["weights"], "buy_threshold": model["buy_threshold"], "sell_threshold": model["sell_threshold"],
            "target_pct": model["target_pct"], "stop_pct": model["stop_pct"], "max_days": model["max_days"], "by_category": model["by_category"]},
            "stats": {**st, "hit_rate": round(st["wins"] / n * 100, 1) if st["closed"] else None, "avg_return": round(st["sum_return"] / n, 2) if st["closed"] else None,
                      "open_count": len(state["open"]), "open_return": round(sum(r["return"] for r in state["open"]) / max(1, len(state["open"])), 2)},
            "log": model["log"][-20:][::-1]}
