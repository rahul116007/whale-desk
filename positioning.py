"""
Second opinions on positioning
------------------------------
The Hyperliquid leaderboard (hl_smart.py) is one cohort on one venue. This module reads four more public,
key-less sources so every coin gets a second opinion, and so the weekly backtest can find out which of them
actually predicts anything:

  lighter   Lighter (perp DEX) 30-day PnL leaderboard -> what its top traders hold right now
  vaults    Hyperliquid's profitable user vaults (professionally run pooled accounts) -> their open positions
  cextop    exchange "top trader" long/short ratio by position size (OKX + Gate), measured against each coin's
            own two-week norm, so a structurally long-biased book does not read as a signal
  funding   perp funding rate (Hyperliquid + OKX), annualised; high funding = crowded longs = a headwind

    python3 positioning.py            # refresh positioning.json for the focus coins and print a summary

Design rules:
  * every source is independent and fails soft: one exchange being down never breaks a refresh
  * a failed source may reuse its last good read for at most 12 hours, then it drops out (no silent stale data)
  * nothing here changes a recommendation by itself. recommend.py records these as extra factors with no weight
    ("watch-only"); backtest.py --apply gives a factor weight once it has two weeks of history and a consistent
    positive rank correlation with forward returns, and takes it away again if that reverses.

Binance and Bybit publish the same kind of ratio but refuse connections from US-hosted servers (HTTP 451 / 403),
which is where GitHub Actions runs, so they are deliberately not used.
"""
import json, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "positioning.json")
CONFIG_PATH = os.path.join(HERE, "config.json")
H = {"User-Agent": "Mozilla/5.0 whale-desk/1.0", "Accept": "application/json"}
MAX_AGE = 12 * 3600                 # a source older than this is never used
SOURCES = ("lighter", "vaults", "cextop", "funding")
LABELS = {"lighter": "Lighter top traders", "vaults": "Hyperliquid vaults", "cextop": "exchange top traders (OKX, Gate)", "funding": "funding rates"}

LIGHTER = "https://mainnet.zklighter.elliot.ai/api/v1"
HL_VAULTS = "https://stats-data.hyperliquid.xyz/Mainnet/vaults"
OKX = "https://www.okx.com/api/v5"
GATE = "https://api.gateio.ws/api/v4"

DEFAULTS = {"pos_sources": list(SOURCES),
            "pos_lighter_top_n": 40, "pos_lighter_min_account": 250_000, "pos_lighter_min_roi_pct": 5.0, "pos_lighter_max_turnover_30d": 400,
            "pos_vaults_top_n": 25, "pos_vault_min_tvl": 1_000_000}

def load_json(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def save_json(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, p)

def fnum(x):
    try: return float(x)
    except Exception: return 0.0

def clamp(v, lo=-1.0, hi=1.0): return max(lo, min(hi, v))

def norm(sym):
    """Venue tickers -> desk symbols: 1000PEPE / kPEPE / 1000000MOG -> PEPE / PEPE / MOG."""
    s = (sym or "").strip()
    if s.startswith("k") and s[1:].isupper(): s = s[1:]
    return re.sub(r"^1(?:000)+", "", s.upper()) or s.upper()

def get(url, params=None, timeout=25, retries=2, must=False):
    """GET -> parsed JSON, or None. must=True raises with the reason instead (used for the first call of a source)."""
    err = "no answer"
    for i in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=H, timeout=timeout)
            if r.status_code == 429:
                err = "rate limited (HTTP 429)"; time.sleep(3 * (i + 1)); continue
            if r.status_code != 200:
                err = f"HTTP {r.status_code}"; break
            return r.json()
        except Exception as e:
            err = type(e).__name__; time.sleep(1 + i)
    if must: raise RuntimeError(f"{url.split('/')[2]} {err}")
    return None

# ----------------------------------------------------------------------------- cohorts (who holds what)

def _flow(hist, coin, net, now):
    """Change in the cohort's net notional versus the read closest to 48h ago (30-66h window). None without history."""
    best = None
    for ts, v in hist.get(coin, []):
        age = (now - ts) / 3600
        if 30 <= age <= 66 and (best is None or abs(age - 48) < abs(best[0] - 48)): best = (age, v)
    return None if best is None else net - best[1]

def _remember(hist, coin, net, now):
    rows = [r for r in hist.get(coin, []) if now - r[0] < 7 * 86400]
    if not rows or now - rows[-1][0] >= 2.5 * 3600: rows.append([now, round(net, 2)])
    hist[coin] = rows

def aggregate(holdings, hist, now, keep=40):
    """holdings: [(who, coin, signed_notional)], one row per trader per coin -> {coin: record with a factor in [-1, 1]}.
    Same recipe as the Hyperliquid factor: 55% head-count crowding + 45% fresh flow; while there is no 48h history
    yet the flow part is replaced by the notional skew at a lower weight."""
    per = {}
    for who, coin, ntl in holdings:
        if not coin or not ntl: continue
        c = per.setdefault(coin, {"coin": coin, "longs": 0, "shorts": 0, "long_ntl": 0.0, "short_ntl": 0.0, "holders": []})
        if ntl > 0: c["longs"] += 1; c["long_ntl"] += ntl
        else: c["shorts"] += 1; c["short_ntl"] += -ntl
        c["holders"].append({"who": who, "side": "long" if ntl > 0 else "short", "notional": round(abs(ntl), 2)})
    for coin in set(hist) - set(per):                                       # a coin everyone left still needs its zero recorded
        _remember(hist, coin, 0.0, now)
        if not any(v for _, v in hist[coin]): del hist[coin]
    out = {}
    for coin, c in per.items():
        n = c["longs"] + c["shorts"]; gross = c["long_ntl"] + c["short_ntl"]
        c["net_ntl"] = c["long_ntl"] - c["short_ntl"]
        crowd = (c["longs"] - c["shorts"]) / n if n else 0.0
        fl = _flow(hist, coin, c["net_ntl"], now)
        if fl is None:
            c["flow48"] = None
            c["factor"] = round(clamp(0.7 * crowd + 0.3 * (c["net_ntl"] / gross if gross else 0.0)), 3)
        else:
            c["flow48"] = round(fl, 2)
            c["factor"] = round(clamp(0.55 * crowd + 0.45 * clamp(fl / max(2e6, 0.25 * gross))), 3)
        _remember(hist, coin, c["net_ntl"], now)
        c["holders"].sort(key=lambda h: -h["notional"]); c["holders"] = c["holders"][:6]
        for k in ("long_ntl", "short_ntl", "net_ntl"): c[k] = round(c[k], 2)
        out[coin] = c
    top = sorted(out.values(), key=lambda c: -(c["long_ntl"] + c["short_ntl"]))[:keep]
    return {c["coin"]: c for c in top}

def lighter(symbols, cfg, hist, now):
    """Lighter's 30-day PnL leaderboard, filtered like the Hyperliquid one (sizeable, profitable, not a market maker)."""
    j = get(f"{LIGHTER}/pnlLeaderboard", {"time_window": "30d", "sort_by": "pnl", "sort_dir": "desc", "limit": 100, "offset": 0}, must=True)
    rows = (j or {}).get("entries") or []
    if not rows: raise RuntimeError("Lighter leaderboard came back empty")
    picked = []
    for r in rows:
        av, pnl, roi, vol = fnum(r.get("account_value")), fnum(r.get("pnl")), fnum(r.get("roi")), fnum(r.get("volume"))
        if av < cfg["pos_lighter_min_account"] or pnl <= 0 or roi < cfg["pos_lighter_min_roi_pct"]: continue
        if av and vol / av > cfg["pos_lighter_max_turnover_30d"]: continue
        picked.append({"addr": r.get("l1_address"), "value": av, "m_pnl": pnl, "m_roi": roi / 100.0, "m_vlm": vol, "score": pnl * min(roi / 100.0, 2.0) ** 0.5})
    picked.sort(key=lambda t: -t["score"]); top = picked[:cfg["pos_lighter_top_n"]]
    if not top: raise RuntimeError("no Lighter trader passed the filter")
    deadline = time.time() + 150; holdings = []; traders = []; unread = 0
    for t in top:
        if time.time() > deadline: unread += 1; continue
        a = get(f"{LIGHTER}/account", {"by": "l1_address", "value": t["addr"]}, retries=1)
        time.sleep(1.1)                                     # Lighter's public limit is about one request a second
        if a is None: unread += 1; continue
        who = t["addr"][:6] + "…" + t["addr"][-4:]; net = {}
        for acc in a.get("accounts") or []:
            for p in acc.get("positions") or []:
                if not fnum(p.get("position")): continue
                side = 1 if fnum(p.get("sign")) > 0 else -1
                net[norm(p.get("symbol"))] = net.get(norm(p.get("symbol")), 0.0) + side * abs(fnum(p.get("position_value")))
        for coin, ntl in net.items(): holdings.append((who, coin, ntl))
        t = dict(t); t["positions"] = [{"coin": c, "side": "long" if v > 0 else "short", "notional": round(abs(v), 2)} for c, v in sorted(net.items(), key=lambda kv: -abs(kv[1]))[:8]]
        traders.append(t)
    if len(traders) < max(3, len(top) // 2): raise RuntimeError(f"Lighter answered for only {len(traders)} of {len(top)} traders")
    return {"coins": aggregate(holdings, hist, now), "traders": traders, "n_traders": len(traders), "unread": unread}

def vaults(symbols, cfg, hist, now):
    """Hyperliquid user vaults that are open, sizeable and in profit over the month and all-time (HLP and its
    children are market makers and are skipped). Their managers trade pooled money in public."""
    import hl_smart
    r = requests.get(HL_VAULTS, headers=H, timeout=120)
    if r.status_code != 200: raise RuntimeError(f"vault list HTTP {r.status_code}")
    picked = []
    for v in r.json() or []:
        s = v.get("summary") or {}
        if s.get("isClosed") or (s.get("relationship") or {}).get("type") != "normal": continue
        tvl = fnum(s.get("tvl"))
        if tvl < cfg["pos_vault_min_tvl"]: continue
        pn = {}
        for row in v.get("pnls") or []:
            if isinstance(row, list) and len(row) == 2 and row[1]: pn[row[0]] = fnum(row[1][-1])
        if pn.get("month", 0) <= 0 or pn.get("allTime", 0) <= 0: continue
        picked.append({"addr": s.get("vaultAddress"), "name": s.get("name"), "value": tvl, "apr": fnum(v.get("apr")), "m_pnl": pn["month"]})
    picked.sort(key=lambda t: -t["value"]); top = picked[:cfg["pos_vaults_top_n"]]
    if not top: raise RuntimeError("no vault passed the filter")
    holdings = []; rows = []; unread = 0
    for t in top:
        pos, _ = hl_smart.positions(t["addr"])
        time.sleep(0.25)
        if pos is None: unread += 1; continue
        who = (t["name"] or t["addr"][:8])[:22]
        for p in pos: holdings.append((who, norm(p["coin"]), p["notional"] if p["side"] == "long" else -p["notional"]))
        t = dict(t); t["positions"] = [{"coin": norm(p["coin"]), "side": p["side"], "notional": round(p["notional"], 2)} for p in sorted(pos, key=lambda p: -p["notional"])[:8]]
        rows.append(t)
    if len(rows) < max(3, len(top) // 2): raise RuntimeError(f"Hyperliquid answered for only {len(rows)} of {len(top)} vaults")
    return {"coins": aggregate(holdings, hist, now), "traders": rows, "n_traders": len(rows), "unread": unread}

# ----------------------------------------------------------------------------- exchange top-trader ratio

def _share(ratio):
    """long/short ratio -> long share of the book (0..1)."""
    return ratio / (1.0 + ratio) if ratio and ratio > 0 else None

def _venue(series):
    """series: oldest-first long shares. -> (now, norm, factor) where 5 points of long share above the norm is a full signal."""
    xs = [x for x in series if x is not None]
    if len(xs) < 5: return None
    now_, base = xs[-1], sum(xs[:-1]) / (len(xs) - 1)
    return {"share": round(now_, 4), "base": round(base, 4), "factor": round(clamp((now_ - base) / 0.05), 3)}

def _okx_top(sym):
    j = get(f"{OKX}/rubik/stat/contracts/long-short-position-ratio-contract-top-trader", {"instId": f"{sym}-USDT-SWAP", "period": "1D", "limit": "15"}, retries=1)
    if not j or j.get("code") != "0" or not j.get("data"): return None
    rows = sorted((int(a[0]), fnum(a[1])) for a in j["data"] if len(a) >= 2)
    return _venue([_share(r) for _, r in rows])

def _gate_top(sym):
    j = get(f"{GATE}/futures/usdt/contract_stats", {"contract": f"{sym}_USDT", "interval": "1d", "limit": 15}, retries=1)
    if not isinstance(j, list) or len(j) < 5:
        j = get(f"{GATE}/futures/usdt/contract_stats", {"contract": f"{sym}_USDT", "interval": "4h", "limit": 84}, retries=0)
    if not isinstance(j, list) or not j: return None
    rows = sorted(j, key=lambda r: r.get("time", 0))
    v = _venue([_share(fnum(r.get("top_lsr_size"))) for r in rows])
    if v:
        crowd = _share(fnum(rows[-1].get("lsr_account")))
        if crowd is not None: v["crowd_share"] = round(crowd, 4)       # every account on the venue, not just the big ones
    return v

def cextop(symbols, cfg, hist, now):
    out = {}; seen = {"okx": 0, "gate": 0}
    deadline = time.time() + 120
    for sym in symbols:
        if time.time() > deadline: break
        venues = {}
        o = _okx_top(sym); time.sleep(0.45)                 # OKX statistics endpoints allow 5 requests per 2 seconds
        if o: venues["okx"] = o; seen["okx"] += 1
        g = _gate_top(sym)
        if g: venues["gate"] = g; seen["gate"] += 1
        if not venues: continue
        vs = list(venues.values())
        rec = {"venues": venues, "long_share": round(sum(v["share"] for v in vs) / len(vs), 4), "base": round(sum(v["base"] for v in vs) / len(vs), 4),
               "factor": round(sum(v["factor"] for v in vs) / len(vs), 3)}
        rec["delta_pts"] = round((rec["long_share"] - rec["base"]) * 100, 1)
        out[sym] = rec
    if not out: raise RuntimeError("neither OKX nor Gate returned a top-trader ratio for any focus coin")
    return {"coins": out, "venues_seen": seen}

# ----------------------------------------------------------------------------- funding

def _okx_apr(row):
    """One OKX funding row -> annualised %, using the contract's own interval (4h or 8h)."""
    rate = fnum(row.get("fundingRate")); ft, pt = fnum(row.get("fundingTime")), fnum(row.get("prevFundingTime"))
    hours = (ft - pt) / 3.6e6 if ft and pt and ft > pt else 8.0
    if not 0.5 <= hours <= 24: hours = 8.0
    return rate * (24 / hours) * 365 * 100

def funding(symbols, cfg, hist, now):
    import hl_smart
    per = {s: {} for s in symbols}
    j = hl_smart.info({"type": "metaAndAssetCtxs"})
    if isinstance(j, list) and len(j) == 2:
        for meta, ctx in zip(j[0].get("universe", []), j[1]):
            s = norm(meta.get("name"))
            if s in per and ctx.get("funding") is not None:
                per[s]["hl"] = round(fnum(ctx["funding"]) * 24 * 365 * 100, 2)             # Hyperliquid pays hourly
                per[s]["oi_usd"] = round(fnum(ctx.get("openInterest")) * fnum(ctx.get("markPx")), 0)
    allrows = get(f"{OKX}/public/funding-rate", {"instId": "ANY"}, retries=1) or {}
    by_inst = {r.get("instId"): r for r in (allrows.get("data") or [])} if allrows.get("code") == "0" else {}
    for s in symbols:
        row = by_inst.get(f"{s}-USDT-SWAP")
        if row is None and len(by_inst) < 50:               # the all-contracts call was refused or short: ask per coin
            one = get(f"{OKX}/public/funding-rate", {"instId": f"{s}-USDT-SWAP"}, retries=0); time.sleep(0.25)
            row = (one.get("data") or [None])[0] if one and one.get("code") == "0" else None
        if row: per[s]["okx"] = round(_okx_apr(row), 2)
    out = {}
    for s, v in per.items():
        aprs = [v[k] for k in ("hl", "okx") if k in v]
        if not aprs: continue
        apr = sum(aprs) / len(aprs)
        # 11% a year is the resting rate (0.01% per 8h). Well above it longs are paying up to stay in: crowded.
        out[s] = {**v, "apr": round(apr, 2), "factor": round(clamp((11.0 - apr) / 40.0), 3)}
    if not out: raise RuntimeError("no funding data from Hyperliquid or OKX")
    return {"coins": out}

# ----------------------------------------------------------------------------- run

FETCH = {"lighter": lighter, "vaults": vaults, "cextop": cextop, "funding": funding}

def cfg_get(cfg=None):
    c = dict(cfg) if cfg else load_json(CONFIG_PATH, {})
    for k, v in DEFAULTS.items(): c.setdefault(k, v)
    return c

def per_coin(pos, symbols, now=None):
    """{SYMBOL: {source: record}} using only sources read within the last 12 hours."""
    now = now or time.time(); out = {}
    for name, blk in (pos.get("blocks") or {}).items():
        if now - (blk.get("updated") or 0) > MAX_AGE: continue
        for s in symbols:
            rec = (blk.get("coins") or {}).get(s)
            if rec: out.setdefault(s, {})[name] = rec
    return out

def run(symbols, cfg=None, verbose=True):
    cfg = cfg_get(cfg); now = int(time.time())
    symbols = [s.upper() for s in symbols]
    prev = load_json(OUT, {}); hist = prev.get("hist") or {}
    out = {"updated": now, "blocks": {}, "hist": hist}
    for name in SOURCES:
        if name not in cfg["pos_sources"]: continue
        t0 = time.time()
        try:
            blk = FETCH[name](symbols, cfg, hist.setdefault(name, {}), now)
            blk.update({"ok": True, "updated": now, "secs": round(time.time() - t0, 1)})
        except Exception as e:
            note = str(e)[:160] or type(e).__name__
            old = (prev.get("blocks") or {}).get(name)
            if old and old.get("coins") and now - (old.get("updated") or 0) < MAX_AGE:
                blk = {**old, "ok": False, "note": note + "; using the last good read"}
            else:
                blk = {"ok": False, "updated": 0, "coins": {}, "note": note}
        out["blocks"][name] = blk
        if verbose:
            print(f"  [pos] {name:<8} " + (f"ok, {len(blk['coins'])} coins in {blk.get('secs')}s" if blk["ok"] else f"FAILED: {blk.get('note')}"))
    out["coins"] = per_coin(out, symbols, now)
    save_json(OUT, out)
    return out

def public(pos):
    """The part worth putting in desk.json / on the dashboard (no history arrays)."""
    return {k: v for k, v in pos.items() if k != "hist"}

if __name__ == "__main__":
    cfg = cfg_get()
    syms = sys.argv[1:]
    if not syms:
        desk = load_json(os.path.join(HERE, "desk.json"), {})
        syms = [c["symbol"] for c in desk.get("coins", [])] or ["BTC", "ETH"]
    res = run(syms, cfg)
    for s in syms:
        p = res["coins"].get(s.upper(), {})
        bits = []
        for k in ("lighter", "vaults"):
            if k in p: bits.append(f"{k} {p[k]['longs']}L/{p[k]['shorts']}S ({p[k]['factor']:+.2f})")
        if "cextop" in p: bits.append(f"top traders {p['cextop']['long_share']*100:.0f}% long ({p['cextop']['delta_pts']:+.1f} pts, {p['cextop']['factor']:+.2f})")
        if "funding" in p: bits.append(f"funding {p['funding']['apr']:+.0f}%/yr ({p['funding']['factor']:+.2f})")
        print(f"  {s.upper():<7} " + ("; ".join(bits) or "no cover"))
