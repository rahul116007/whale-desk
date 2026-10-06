#!/usr/bin/env python3
"""
Coin Desk
---------
Sits on top of whale_scanner.py. Keeps a focus list of ~20 coins, pulls market data,
news, Reddit chatter, community sentiment and the whale flows the scanner has
recorded for each, then renders one dashboard (dashboard.html).

  python3 coin_desk.py refresh              # update everything + rebuild dashboard.html
  python3 coin_desk.py research PEPE        # deep-dive one coin (any coin), research/PEPE.html
  python3 coin_desk.py focus                # show the focus list
  python3 coin_desk.py focus add LINK       # add / remove coins from the focus list
  python3 coin_desk.py focus remove SHIB
  python3 coin_desk.py watch --every 15     # whale scan + refresh every 15 min

Sources (no keys): CoinGecko, Google News RSS, Reddit RSS, DexScreener.
Optional: X API v2 bearer token in config.json ("x_bearer_token") enables live X search.
"""
import argparse, csv, json, os, re, sys, time, html, datetime as dt
import xml.etree.ElementTree as ET
import threading
REDDIT_LOCK = threading.Lock()
REDDIT_STATE = {"down": False}
from collections import defaultdict
import requests
import exchanges

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
TRADES_CSV = os.path.join(HERE, "trades.csv")
HOLDINGS_CSV = os.path.join(HERE, "holdings.csv")
ALERTS_LOG = os.path.join(HERE, "alerts.log")
DESK_JSON = os.path.join(HERE, "desk.json")
DASHBOARD = os.path.join(HERE, "dashboard.html")
RESEARCH_DIR = os.path.join(HERE, "research")
CG_CACHE = os.path.join(HERE, "cg_cache.json")
SOCIAL_CACHE = os.path.join(HERE, "social_cache.json")

CG = "https://api.coingecko.com/api/v3"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) coin-desk/1.0"}
try:
    with open(CONFIG_PATH) as _f: _k = json.load(_f).get("coingecko_api_key", "")
except Exception: _k = ""
_k = os.environ.get("COINGECKO_API_KEY") or _k
if _k: UA["x-cg-demo-api-key"] = _k        # free demo key from coingecko.com/en/api lifts the rate limit to 30/min
STABLE_IDS = {"tether", "usd-coin", "dai", "usds", "ethena-usde", "first-digital-usd", "usd1-wlfi", "paypal-usd",
              "true-usd", "binance-bridged-usdt-bnb-smart-chain", "usdt0", "ethena-staked-usde", "blackrock-usd-institutional-digital-liquidity-fund", "figure-heloc"}
WRAPPED_HINTS = ("wrapped", "staked", "bridged", "liquid", "restaked", "wsteth", "weeth", "cbbtc", "wbtc", "steth", "weth")

# ----------------------------------------------------------------------------- utils

def load_json(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def save_json(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f, indent=1)
    os.replace(tmp, p)

def now_ts(): return int(time.time())

def get(url, params=None, headers=None, retries=4, timeout=30, as_text=False, backoff=8):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=timeout)
            if r.status_code == 429:
                time.sleep(backoff * (i + 1)); continue
            if r.status_code >= 400:
                return None
            return r.text if as_text else r.json()
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def fmt_usd(v):
    try: v = float(v)
    except (TypeError, ValueError): return "-"
    if abs(v) >= 1e12: return f"${v/1e12:,.2f}T"
    if abs(v) >= 1e9: return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.1f}k"
    if abs(v) >= 1: return f"${v:,.2f}"
    return f"${v:.6g}"

def read_csv(p):
    if not os.path.exists(p): return []
    with open(p) as f: return list(csv.DictReader(f))

def parse_date(s):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            d = dt.datetime.strptime(s.strip(), fmt)
            if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
            return int(d.timestamp())
        except Exception: pass
    try: return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception: return 0

# ----------------------------------------------------------------------------- config / focus list

def load_config():
    cfg = load_json(CONFIG_PATH, {})
    cfg.setdefault("focus_coins", [])
    cfg.setdefault("focus_size", 20)
    cfg.setdefault("focus_mode", "erc20")
    cfg.setdefault("x_bearer_token", "")
    cfg.setdefault("news_days", 7)
    cfg.setdefault("anthropic_api_key", "")
    cfg.setdefault("coingecko_api_key", "")
    cfg.setdefault("x_cache_hours", 24)
    cfg.setdefault("x_posts_per_coin", 10)
    # keys can come from the environment (GitHub Actions secrets) instead of config.json
    for k, env in (("anthropic_api_key", "ANTHROPIC_API_KEY"), ("coingecko_api_key", "COINGECKO_API_KEY"),
                   ("x_bearer_token", "X_BEARER_TOKEN"), ("etherscan_api_key", "ETHERSCAN_API_KEY")):
        if os.environ.get(env): cfg[k] = os.environ[env]
    return cfg

def save_config(cfg):
    # keep the file human-readable: wallets one per line
    body = {k: v for k, v in cfg.items() if k != "wallets"}
    s = json.dumps(body, indent=2)[:-2] + ',\n  "wallets": [\n' + ",\n".join("    " + json.dumps(w) for w in cfg.get("wallets", [])) + "\n  ]\n}\n"
    with open(CONFIG_PATH, "w") as f: f.write(s)

def auto_focus(size, mode="erc20"):
    """Focus list. 'erc20' (default): the biggest Ethereum-ecosystem tokens, which is what the tracked whales
    actually trade on DEXs, plus BTC and ETH for context. 'top': plain top-of-market by market cap."""
    skip = lambda c: c["id"] in STABLE_IDS or any(h in (c["name"] + " " + c["id"]).lower() for h in WRAPPED_HINTS)
    out = []
    if mode == "erc20":
        out = ["bitcoin", "ethereum"]
        mk = get(f"{CG}/coins/markets", {"vs_currency": "usd", "category": "ethereum-ecosystem", "order": "market_cap_desc", "per_page": 80, "page": 1}) or []
        for c in mk:
            if skip(c) or c["id"] in out or c["id"] in ("ethereum", "bitcoin"): continue
            if c["symbol"].lower() in ("weth", "steth", "wbtc", "cbbtc", "leo", "wbt", "okb", "kcs", "gt", "cro", "bgb", "usdt", "usdc", "bnb", "ton"): continue
            low = (c["name"] + " " + c["symbol"] + " " + c["id"]).lower()
            if any(x in low for x in ("usd", "usyc", "stable", "dollar", "eur", "yield", "treasury", "paxg", "pax gold", "htx", "open-network")): continue   # yield-stables and dollar tokens
            out.append(c["id"])
            if len(out) >= size: break
    else:
        mk = get(f"{CG}/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 60, "page": 1}) or []
        for c in mk:
            if skip(c): continue
            out.append(c["id"])
            if len(out) >= size: break
    return out

# ----------------------------------------------------------------------------- CoinGecko

def cg_markets(ids):
    out = []
    for i in range(0, len(ids), 50):
        mk = get(f"{CG}/coins/markets", {"vs_currency": "usd", "ids": ",".join(ids[i:i+50]), "sparkline": "true",
                                          "price_change_percentage": "1h,24h,7d,30d", "per_page": 50}) or []
        out += mk
    return {c["id"]: c for c in out}

def cg_coin(cid, cache, max_age=6 * 3600):
    """Community + sentiment + links; cached because the free tier is ~30 calls/min."""
    hit = cache.get(cid)
    if hit and now_ts() - hit.get("_ts", 0) < max_age:
        return hit
    j = get(f"{CG}/coins/{cid}", {"localization": "false", "tickers": "false", "market_data": "true",
                                  "community_data": "true", "developer_data": "false", "sparkline": "false"})
    time.sleep(1.6)
    if not j: return hit or {}
    md, cd, links = j.get("market_data") or {}, j.get("community_data") or {}, j.get("links") or {}
    info = {
        "_ts": now_ts(), "id": cid, "symbol": (j.get("symbol") or "").upper(), "name": j.get("name"),
        "eth_address": ((j.get("platforms") or {}).get("ethereum") or "").lower(),
        "platforms": {k: v for k, v in (j.get("platforms") or {}).items() if v},
        "twitter": links.get("twitter_screen_name") or "", "subreddit": (links.get("subreddit_url") or ""),
        "homepage": next((u for u in links.get("homepage", []) if u), ""),
        "twitter_followers": cd.get("twitter_followers"), "reddit_subs": cd.get("reddit_subscribers"),
        "reddit_active_48h": cd.get("reddit_accounts_active_48h"),
        "sentiment_up": j.get("sentiment_votes_up_percentage"), "watchlist_users": j.get("watchlist_portfolio_users"),
        "ath": (md.get("ath") or {}).get("usd"), "ath_change": (md.get("ath_change_percentage") or {}).get("usd"),
        "ath_date": ((md.get("ath_date") or {}).get("usd") or "")[:10],
        "atl": (md.get("atl") or {}).get("usd"), "fdv": (md.get("fully_diluted_valuation") or {}).get("usd"),
        "circ": md.get("circulating_supply"), "total": md.get("total_supply"), "max": md.get("max_supply"),
        "description": re.sub(r"<[^>]+>", "", ((j.get("description") or {}).get("en") or "")).split("\n")[0][:600],
        "categories": [c for c in (j.get("categories") or []) if c][:6],
        "rank": j.get("market_cap_rank"),
    }
    cache[cid] = info
    return info

def cg_search(q):
    j = get(f"{CG}/search", {"query": q}) or {}
    coins = j.get("coins") or []
    q = q.lower()
    exact = [c for c in coins if c.get("symbol", "").lower() == q or c.get("id") == q or c.get("name", "").lower() == q]
    pick = (exact or coins)
    pick.sort(key=lambda c: (c.get("market_cap_rank") or 10**6))
    return pick[0] if pick else None

def cg_trending():
    j = get(f"{CG}/search/trending") or {}
    return [{"id": c["item"]["id"], "symbol": c["item"]["symbol"], "name": c["item"]["name"], "rank": c["item"].get("market_cap_rank"),
             "chg24": ((c["item"].get("data") or {}).get("price_change_percentage_24h") or {}).get("usd")}
            for c in (j.get("coins") or [])[:12]]

# ----------------------------------------------------------------------------- news / social

def google_news(query, days):
    xml = get("https://news.google.com/rss/search", {"q": f"{query} when:{days}d", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}, as_text=True)
    items = []
    if not xml: return items
    try:
        root = ET.fromstring(xml)
    except Exception:
        return items
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        src = it.find("source")
        items.append({"title": html.unescape(title), "link": it.findtext("link") or "", "ts": parse_date(it.findtext("pubDate") or ""),
                      "source": (src.text if src is not None else "") or ""})
    items.sort(key=lambda x: -x["ts"])
    return items[:100]

def reddit_search(query, subreddit=None):
    url = f"https://www.reddit.com/r/{subreddit}/search.rss" if subreddit else "https://www.reddit.com/search.rss"
    params = {"q": query, "sort": "new", "t": "week", "restrict_sr": 1 if subreddit else 0}
    with REDDIT_LOCK:                       # reddit throttles parallel callers hard: one at a time, gently
        if REDDIT_STATE["down"]: return []  # once it starts refusing, stop hammering it for this run
        xml = get(url, params, headers={"User-Agent": "python:coindesk:v1.0 (by /u/coindesk)"}, as_text=True, retries=1, backoff=3)
        if xml is None:
            REDDIT_STATE["down"] = True; print("  reddit is rate-limiting us, skipping reddit for the rest of this run")
        time.sleep(1.2)
    out = []
    if not xml: return out
    try: root = ET.fromstring(xml)
    except Exception: return out
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in root.findall("a:entry", ns):
        title = e.findtext("a:title", default="", namespaces=ns)
        link = e.find("a:link", ns)
        cat = e.find("a:category", ns)
        out.append({"title": html.unescape(title), "link": link.get("href") if link is not None else "",
                    "ts": parse_date(e.findtext("a:updated", default="", namespaces=ns)),
                    "sub": (cat.get("label") if cat is not None else (subreddit or "")).replace("r/", "")})
    out.sort(key=lambda x: -x["ts"])
    return out[:20]

def x_search(query, token, max_results=25):
    """X API v2 recent search. Needs a paid Basic tier bearer token; returns [] without one."""
    if not token: return []
    j = get("https://api.x.com/2/tweets/search/recent",
            {"query": f"({query}) -is:retweet lang:en", "max_results": max_results, "tweet.fields": "created_at,public_metrics,author_id",
             "expansions": "author_id", "user.fields": "username,public_metrics"},
            headers={"Authorization": f"Bearer {token}"})
    if not j: return []
    users = {u["id"]: u for u in (j.get("includes") or {}).get("users", [])}
    out = []
    for t in j.get("data", []):
        u = users.get(t.get("author_id"), {})
        m = t.get("public_metrics") or {}
        out.append({"title": t["text"][:280], "link": f"https://x.com/{u.get('username','i')}/status/{t['id']}",
                    "ts": parse_date(t.get("created_at", "")), "source": "@" + u.get("username", "?"),
                    "likes": m.get("like_count", 0), "followers": (u.get("public_metrics") or {}).get("followers_count", 0)})
    out.sort(key=lambda x: -(x["likes"] + x["followers"] / 1000))
    return out

def dex_pairs(symbol, eth_address=""):
    j = get("https://api.dexscreener.com/latest/dex/search", {"q": eth_address or symbol}) or {}
    pairs = j.get("pairs") or []
    if eth_address:
        pairs = [p for p in pairs if (p.get("baseToken") or {}).get("address", "").lower() == eth_address]
    else:
        pairs = [p for p in pairs if (p.get("baseToken") or {}).get("symbol", "").upper() == symbol.upper()]
    pairs.sort(key=lambda p: -((p.get("liquidity") or {}).get("usd") or 0))
    return [{"chain": p.get("chainId"), "dex": p.get("dexId"), "liq": (p.get("liquidity") or {}).get("usd") or 0,
             "vol24": (p.get("volume") or {}).get("h24") or 0, "url": p.get("url"), "price": float(p.get("priceUsd") or 0),
             "buys24": ((p.get("txns") or {}).get("h24") or {}).get("buys", 0), "sells24": ((p.get("txns") or {}).get("h24") or {}).get("sells", 0)}
            for p in pairs[:5]]

# ----------------------------------------------------------------------------- whale flows (from the scanner's csvs)

_WTYPES = None
def wallet_types():
    """{wallet label: type} from config.json (individual / fund / vc / market_maker / treasury)."""
    global _WTYPES
    if _WTYPES is None:
        try: _WTYPES = {w["label"]: w.get("type", "") for w in load_config().get("wallets", [])}
        except Exception: _WTYPES = {}
    return _WTYPES

def whale_flows(symbol, eth_address, days=7):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    ev = []
    for t in read_csv(TRADES_CSV):
        if not (t["symbol"].upper() == symbol.upper() or (eth_address and t["token"] == eth_address)): continue
        try: ts = dt.datetime.strptime(t["time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        except Exception: continue
        if ts < cutoff: continue
        ev.append({"time": t["time_utc"], "wallet": t["wallet_label"], "kind": t["kind"], "amount": float(t["amount"] or 0),
                   "usd": float(t["usd_now"] or 0), "note": t["note"], "tx": t["tx"]})
    buys = sum(e["usd"] for e in ev if e["kind"] == "buy"); sells = sum(e["usd"] for e in ev if e["kind"] == "sell")
    tin = sum(e["usd"] for e in ev if e["kind"] == "transfer_in"); tout = sum(e["usd"] for e in ev if e["kind"] == "transfer_out")
    # exchange flows: withdrawals from a CEX into a tracked wallet = accumulation, deposits to a CEX = distribution.
    # Market makers are the exception: their exchange legs are inventory management (backtest: mildly contrarian), so
    # only their non-exchange transfers count, at quarter weight like everyone else's.
    wtype = wallet_types()
    for e in ev:
        e["exchange"] = exchanges.in_note(e["note"]) if e["kind"] in ("transfer_in", "transfer_out") else None
        if e["exchange"] and wtype.get(e["wallet"], "").startswith("market_maker"): e["exchange"] = None
    ex_in = sum(e["usd"] for e in ev if e["kind"] == "transfer_in" and e["exchange"]); ex_out = sum(e["usd"] for e in ev if e["kind"] == "transfer_out" and e["exchange"])
    flow = (buys - sells) + (ex_in - ex_out) + 0.25 * ((tin - ex_in) - (tout - ex_out))
    accum = sorted({e["wallet"] for e in ev if e["kind"] == "buy" or (e["kind"] == "transfer_in" and e["exchange"] and e["usd"] >= 25_000)})
    distrib = sorted({e["wallet"] for e in ev if e["kind"] == "sell" or (e["kind"] == "transfer_out" and e["exchange"] and e["usd"] >= 25_000)})
    holders = []
    for h in read_csv(HOLDINGS_CSV):
        if h["symbol"].upper() == symbol.upper() or (eth_address and h["token"] == eth_address):
            if float(h["usd"] or 0) >= 1000:
                holders.append({"wallet": h["wallet_label"], "balance": float(h["balance"]), "usd": float(h["usd"])})
    holders.sort(key=lambda x: -x["usd"])
    ev.sort(key=lambda e: e["time"], reverse=True)
    return {"events": ev[:40], "buys": buys, "sells": sells, "net": buys - sells, "transfer_in": tin, "transfer_out": tout,
            "ex_in": ex_in, "ex_out": ex_out, "flow": flow, "buyers": accum, "sellers": distrib,
            "holders": holders, "held_usd": sum(h["usd"] for h in holders)}

# ----------------------------------------------------------------------------- scoring

def buzz(news, reddit, xposts):
    cut48 = now_ts() - 48 * 3600
    n48 = sum(1 for n in news if n["ts"] >= cut48); r48 = sum(1 for r in reddit if r["ts"] >= cut48); x48 = len(xposts)
    return {"news48": n48, "reddit48": r48, "x": x48, "score": min(100, n48 * 4 + r48 * 3 + x48 * 2)}

def signal(coin):
    """A blunt 0-100 'worth a look' number. Not advice, just a sort key."""
    s = 50
    w = coin["whales"]
    fl = w.get("flow", w["net"])
    if fl > 0: s += min(20, fl / 50000)
    if fl < 0: s -= min(20, -fl / 50000)
    s += min(15, coin["buzz"]["score"] / 5)
    su = coin["info"].get("sentiment_up")
    if su: s += (su - 50) / 5
    c24 = coin["market"].get("price_change_percentage_24h") or 0
    s += max(-10, min(10, c24 / 2))
    return int(max(0, min(100, s)))


# ----------------------------------------------------------------------------- charts + AI take

def cg_chart(cid, cache, days=90, max_age=3 * 3600):
    key = f"chart:{cid}"
    hit = cache.get(key)
    if hit and now_ts() - hit.get("_ts", 0) < max_age:
        return hit
    j = get(f"{CG}/coins/{cid}/market_chart", {"vs_currency": "usd", "days": days, "interval": "daily"})
    time.sleep(1.6)
    if not j: return hit or {"_ts": 0, "prices": [], "volumes": []}
    out = {"_ts": now_ts(), "prices": [[int(t / 1000), p] for t, p in (j.get("prices") or [])][-days:],
           "volumes": [[int(t / 1000), v] for t, v in (j.get("total_volumes") or [])][-days:]}
    cache[key] = out
    return out

def daily_series(items, key="ts", days=14):
    """Count of items per UTC day for the last N days -> [[day_ts, n], ...]"""
    today = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = {int((today - dt.timedelta(days=d)).timestamp()): 0 for d in range(days - 1, -1, -1)}
    for it in items:
        d = int(dt.datetime.fromtimestamp(it[key], dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        if d in buckets: buckets[d] += 1
    return sorted(buckets.items())

def whale_daily(events, days=14):
    today = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    b = {int((today - dt.timedelta(days=d)).timestamp()): [0.0, 0.0] for d in range(days - 1, -1, -1)}
    for e in events:
        try: d = int(dt.datetime.strptime(e["time"][:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
        except Exception: continue
        if d in b:
            if e["kind"] == "buy": b[d][0] += e["usd"]
            elif e["kind"] == "sell": b[d][1] += e["usd"]
    return [[k, v[0], v[1]] for k, v in sorted(b.items())]

def rules_take(coin):
    m, i, w, b, pairs = coin["market"], coin["info"], coin["whales"], coin["buzz"], coin["pairs"]
    c1, c24, c7, c30 = (m.get("price_change_percentage_1h_in_currency") or 0, m.get("price_change_percentage_24h") or 0,
                        m.get("price_change_percentage_7d_in_currency") or 0, m.get("price_change_percentage_30d_in_currency") or 0)
    bull, bear, watch = [], [], []
    if c7 > 8 and c30 > 0: bull.append(f"momentum is with it: {c7:+.1f}% on the week, {c30:+.1f}% on the month")
    elif c7 < -8: bear.append(f"price is bleeding, {c7:+.1f}% on the week")
    if abs(c24) > 12: watch.append(f"a {c24:+.0f}% day is unusual; check whether it was news or a single large trade")
    fl = w.get("flow", w["net"])
    if fl > 25000: bull.append(f"tracked whales are net accumulating over the window ({fmt_usd(fl)}, incl. {fmt_usd(w.get('ex_in', 0))} withdrawn from exchanges), led by {', '.join(w['buyers'][:3])}")
    elif fl < -25000: bear.append(f"tracked whales are net distributing ({fmt_usd(-fl)}, incl. {fmt_usd(w.get('ex_out', 0))} sent to exchanges), including {', '.join(w['sellers'][:3])}")
    if w["transfer_out"] > 5 * max(w["transfer_in"], 1) and w["transfer_out"] > 250000:
        bear.append(f"{fmt_usd(w['transfer_out'])} moved out of tracked wallets, often the step before a sale on an exchange")
    if w["holders"]: bull.append(f"{len(w['holders'])} tracked wallets hold it ({fmt_usd(w['held_usd'])} between them)")
    sm = coin.get("smart")
    if sm and sm["longs"] + sm["shorts"] >= 2:
        if sm["factor"] > 0.3: bull.append(f"Hyperliquid top traders lean long: {sm['longs']} long vs {sm['shorts']} short, net {fmt_usd(sm['net_ntl'])}, 48h flow {fmt_usd(sm['flow48'])}")
        elif sm["factor"] < -0.3: bear.append(f"Hyperliquid top traders lean short: {sm['longs']} long vs {sm['shorts']} short, net {fmt_usd(sm['net_ntl'])}")
    su = i.get("sentiment_up")
    if su and su >= 75: bull.append(f"crowd sentiment is {su:.0f}% bullish on CoinGecko")
    elif su and su <= 45: bear.append(f"crowd sentiment is weak ({su:.0f}% bullish)")
    if b["score"] >= 40: watch.append(f"attention is high ({b['news48']} stories and {b['reddit48']} Reddit posts in 48h); crowded trades reverse fast")
    elif b["score"] <= 6: watch.append("very little coverage or chatter, so a move here would come from on-chain flow rather than hype")
    ath = i.get("ath_change")
    if ath is not None and ath < -80: watch.append(f"still {ath:.0f}% below its all-time high; a lot of trapped holders sit above the price")
    elif ath is not None and ath > -10: watch.append("within 10% of its all-time high, so there is no overhead resistance but plenty of profit-taking")
    if pairs and pairs[0]["liq"] < 200000: bear.append(f"thin DEX liquidity ({fmt_usd(pairs[0]['liq'])}) means slippage and easy manipulation")
    if pairs and pairs[0]["buys24"] > 1.5 * max(pairs[0]["sells24"], 1): bull.append(f"DEX order flow skews to buys ({pairs[0]['buys24']} buys vs {pairs[0]['sells24']} sells in 24h)")
    s = coin["signal"]
    stance = "constructive" if s >= 65 else "neutral, wait for a trigger" if s >= 45 else "cautious"
    text = f"Desk view: {stance} (score {s}/100).\n"
    if bull: text += "For it: " + "; ".join(bull) + ".\n"
    if bear: text += "Against it: " + "; ".join(bear) + ".\n"
    if watch: text += "Watch: " + "; ".join(watch) + ".\n"
    text += "This is a mechanical read of price, whale flow, chatter and liquidity, not financial advice."
    return {"source": "rules", "text": text, "bull": bull, "bear": bear, "watch": watch, "stance": stance}

def claude_take(coin, cfg):
    key = cfg.get("anthropic_api_key")
    if not key: return None
    slim = {"symbol": coin["symbol"], "name": coin["name"], "market": {k: v for k, v in coin["market"].items() if k not in ("sparkline", "image")},
            "info": {k: v for k, v in coin["info"].items() if k in ("rank", "fdv", "ath", "ath_change", "ath_date", "sentiment_up", "twitter_followers", "reddit_subs", "categories", "description")},
            "whales": {k: v for k, v in coin["whales"].items() if k != "events"}, "whale_events": coin["whales"]["events"][:15],
            "news": [n["title"] + " (" + n["source"] + ")" for n in coin["news"][:15]], "reddit": [r["title"] for r in coin["reddit"][:10]],
            "x": [x["title"] for x in coin["x"][:10]], "pools": coin["pairs"][:3], "buzz": coin["buzz"], "rules_take": coin["ai"]["text"]}
    prompt = ("You are a crypto trading desk analyst writing a short internal note for a discretionary trader who follows whale wallets. "
              "Using ONLY the data below, write about 180 words: one line stance (constructive / neutral / cautious) with the main reason, "
              "then 'Bull case', 'Bear case' and 'What would change my mind' as short paragraphs, then one line on position sizing risk. "
              "Be concrete, cite the numbers, name the whale wallets. No hype, no disclaimers beyond one closing sentence that this is not financial advice.\n\n"
              + json.dumps(slim, default=str)[:12000])
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": cfg.get("anthropic_model", "claude-sonnet-4-5"), "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}, timeout=60)
        if r.status_code != 200:
            print(f"  claude take failed: {r.status_code} {r.text[:120]}"); return None
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        return {"source": "claude", "text": text}
    except Exception as e:
        print("  claude take failed:", e); return None

# ----------------------------------------------------------------------------- build one coin record

X_CACHE = os.path.join(HERE, "x_cache.json")
def x_cached(sym, name, cfg):
    """X Basic tier caps reads at 10k posts/month, so posts are cached per coin for x_cache_hours (default 24)."""
    token = cfg.get("x_bearer_token", "")
    if not token: return []
    xc = load_json(X_CACHE, {})
    hit = xc.get(sym)
    if hit and now_ts() - hit.get("_ts", 0) < cfg.get("x_cache_hours", 24) * 3600:
        return hit["posts"]
    posts = x_search(f'${sym} OR "{name}"', token, max_results=cfg.get("x_posts_per_coin", 10))
    xc[sym] = {"_ts": now_ts(), "posts": posts}; save_json(X_CACHE, xc)
    return posts

def social_for(info, cfg, deep=False):
    """News, Reddit, X and DEX pools for one coin. Safe to run in a thread (no CoinGecko calls)."""
    sym, name = info["symbol"], info["name"]
    days = cfg["news_days"] * (3 if deep else 1)
    news = google_news(f'"{name}" crypto OR "{sym} coin" OR "{sym} token"', days)
    subs = ["CryptoCurrency"] + (["CryptoMarkets", "ethtrader"] if deep else [])
    own = (info.get("subreddit") or "").rstrip("/").split("/")[-1]
    if own and own.lower() not in {x.lower() for x in subs}: subs.append(own)
    reddit = []
    for sub in subs:
        reddit += reddit_search(f"{name} OR {sym}", sub)
    seen, rd = set(), []
    for r in reddit:
        if r["link"] not in seen: seen.add(r["link"]); rd.append(r)
    xposts = x_cached(sym, name, cfg)
    pairs = dex_pairs(sym, info.get("eth_address", "")) if (deep or info.get("eth_address")) else []
    return {"news": news, "reddit": rd, "x": xposts, "pairs": pairs}

def build_coin(cid, market, cache, cfg, deep=False, social=None):
    info = cg_coin(cid, cache)
    sym = info.get("symbol") or (market.get("symbol") or "").upper()
    name = info.get("name") or market.get("name") or cid
    info.setdefault("symbol", sym); info.setdefault("name", name)
    soc = social or social_for(info, cfg, deep)
    news, rd, xposts, pairs = soc["news"], soc["reddit"], soc["x"], soc["pairs"]
    w = whale_flows(sym, info.get("eth_address", ""), days=14 if deep else 7)
    m = {k: market.get(k) for k in ("current_price", "market_cap", "market_cap_rank", "total_volume", "high_24h", "low_24h",
                                    "price_change_percentage_1h_in_currency", "price_change_percentage_24h",
                                    "price_change_percentage_7d_in_currency", "price_change_percentage_30d_in_currency", "image")}
    m["image"] = inline_logo(m.get("image"), cache)
    m["sparkline"] = (market.get("sparkline_in_7d") or {}).get("price") or []
    if len(m["sparkline"]) > 60:
        step = len(m["sparkline"]) / 60; m["sparkline"] = [m["sparkline"][int(i * step)] for i in range(60)]
    coin = {"id": cid, "symbol": sym, "name": name, "market": m, "info": info, "news": news[:12 if not deep else 25],
            "reddit": rd[:10 if not deep else 25], "x": xposts, "pairs": pairs, "whales": w, "buzz": buzz(news, rd, xposts),
            "updated": now_ts()}
    coin["signal"] = signal(coin)
    ch = cg_chart(cid, cache)
    coin["chart"] = {"prices": ch["prices"], "volumes": ch["volumes"]}
    coin["buzz_daily"] = daily_series(news + rd, days=14)
    coin["whale_daily"] = whale_daily(w["events"], days=14)
    coin["ai"] = rules_take(coin)
    ct = claude_take(coin, cfg)
    if ct: coin["ai"] = {**ct, "rules": coin["ai"]["text"]}
    return coin


# ----------------------------------------------------------------------------- IPOs, listings, new launches

def ipo_block():
    ipo = google_news('"crypto IPO" OR "crypto exchange IPO" OR "bitcoin miner IPO" OR "stablecoin IPO" OR "crypto firm" IPO OR "crypto" "files for IPO" OR "crypto" "S-1 filing" OR "crypto" "goes public" OR "Kraken IPO" OR "Consensys IPO" OR "Ledger IPO" OR "Grayscale IPO" OR "Anchorage IPO" OR "BitGo IPO"', 14)
    crypto_words = ("crypto", "bitcoin", "blockchain", "stablecoin", "token", "coin", "kraken", "circle", "gemini", "bullish", "bithumb", "consensys",
                    "ledger", "anchorage", "grayscale", "bitgo", "digital asset", "web3", "defi", "exchange", "miner", "ethereum", "solana", "ripple", "tether")
    ipo_words = ("ipo", "goes public", "go public", "s-1", "listing on nasdaq", "nyse", "nasdaq", "public offering", "spac", "direct listing")
    ipo = [n for n in ipo if any(w in n["title"].lower() for w in crypto_words) and any(w in n["title"].lower() for w in ipo_words)]
    listings = google_news('"lists" OR "listing" OR "to list" (Binance OR Coinbase OR Upbit OR Kraken OR Bybit OR OKX) token', 3)
    tge = google_news('"token launch" OR TGE OR "token generation event" OR airdrop claim', 3)
    seen, out = set(), {"ipo": [], "listings": [], "tge": []}
    for key, items in (("ipo", ipo), ("listings", listings), ("tge", tge)):
        for n in items:
            k = n["title"][:60].lower()
            if k in seen: continue
            seen.add(k); out[key].append(n)
        out[key] = out[key][:20]
    # fresh DEX launches: DexScreener's latest profiles + top boosts, checked for real liquidity
    cands, seen_t = [], set()
    for url in ("https://api.dexscreener.com/token-boosts/top/v1", "https://api.dexscreener.com/token-profiles/latest/v1"):
        for t in (get(url) or [])[:40]:
            key = (t.get("chainId"), (t.get("tokenAddress") or "").lower())
            if key in seen_t or t.get("chainId") not in ("ethereum", "solana", "base", "bsc"): continue
            seen_t.add(key); cands.append(t)
    launches = []
    by_chain = defaultdict(list)
    for t in cands[:45]: by_chain[t["chainId"]].append(t)
    for chain, ts in by_chain.items():
        for i in range(0, len(ts), 30):
            batch = ts[i:i+30]
            pairs = get(f"https://api.dexscreener.com/tokens/v1/{chain}/" + ",".join(t["tokenAddress"] for t in batch)) or []
            best = {}
            for p in pairs:
                a = (p.get("baseToken") or {}).get("address", "").lower()
                liq = (p.get("liquidity") or {}).get("usd") or 0
                if a not in best or liq > best[a]["liq"]:
                    best[a] = {"chain": chain, "symbol": (p.get("baseToken") or {}).get("symbol"), "name": (p.get("baseToken") or {}).get("name"),
                               "price": float(p.get("priceUsd") or 0), "liq": liq, "vol24": (p.get("volume") or {}).get("h24") or 0,
                               "chg24": (p.get("priceChange") or {}).get("h24"), "chg6h": (p.get("priceChange") or {}).get("h6"),
                               "buys24": ((p.get("txns") or {}).get("h24") or {}).get("buys", 0), "sells24": ((p.get("txns") or {}).get("h24") or {}).get("sells", 0),
                               "mcap": p.get("marketCap") or p.get("fdv"), "age_h": round((now_ts() * 1000 - (p.get("pairCreatedAt") or now_ts() * 1000)) / 3.6e6, 1),
                               "url": p.get("url"), "boosts": next((t.get("totalAmount") or t.get("amount") for t in batch if t["tokenAddress"].lower() == a), None)}
            launches += [v for v in best.values() if v["liq"] >= 50000]
    launches.sort(key=lambda x: -(x["vol24"] or 0))
    out["launches"] = launches[:25]
    return out

def inline_logo(url, cache):
    """Coin logo as a data URI so the hosted copy of the dashboard shows it (external images are blocked there)."""
    if not url: return ""
    key = "img:" + url
    if key in cache: return cache[key]
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code == 200 and len(r.content) < 200_000:
            import base64
            cache[key] = f"data:{r.headers.get('content-type','image/png')};base64," + base64.b64encode(r.content).decode()
            return cache[key]
    except Exception: pass
    return url

# ----------------------------------------------------------------------------- commands

HL_MAX_AGE = 12 * 3600

def fresh_hl(hl, why=""):
    """A saved Hyperliquid read may stand in for a failed fetch for 12 hours. Past that it is dropped, so stale
    positioning can never open a call (this is what went unnoticed from 14 Sep to 5 Oct 2026)."""
    age = now_ts() - (hl.get("updated") or 0)
    if hl.get("coins") and age > HL_MAX_AGE:
        print(f"  hl data is {age / 3600:.0f}h old: ignored until a fresh read succeeds")
        return {"coins": [], "traders": [], "n_traders": 0, "updated": hl.get("updated"), "params": hl.get("params", {}), "stale": True,
                "note": f"last good Hyperliquid read was {age / 3600:.0f}h ago and is being ignored" + (f" ({why[:120]})" if why else "")}
    if why: hl = {**hl, "note": f"fetch failed ({why[:120]}); showing the last good read"}
    return hl

def cmd_refresh(args):
    cfg = load_config()
    if not cfg["focus_coins"]:
        print("no focus list yet, building one from the top of the market…")
        cfg["focus_coins"] = auto_focus(cfg["focus_size"], cfg.get("focus_mode", "erc20")); save_config(cfg)
    ids = cfg["focus_coins"]
    cache = load_json(CG_CACHE, {})
    print(f"[{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}Z] refreshing {len(ids)} coins: {', '.join(ids)}")
    markets = cg_markets(ids)
    ids = [i for i in ids if i in markets] + [i for i in ids if i not in markets]
    # phase 1: CoinGecko coin info, serial (rate-limited), cached 6h so only the first run is slow
    infos = {}
    for cid in ids:
        if cid in markets:
            infos[cid] = cg_coin(cid, cache); infos[cid].setdefault("symbol", markets[cid]["symbol"].upper()); infos[cid].setdefault("name", markets[cid]["name"])
    save_json(CG_CACHE, cache)
    # phase 2: news / reddit / dex in parallel
    from concurrent.futures import ThreadPoolExecutor
    sc = load_json(SOCIAL_CACHE, {})
    fresh = [cid for cid in infos if now_ts() - sc.get(cid, {}).get("_ts", 0) < 30 * 60]
    todo = [cid for cid in infos if cid not in fresh]
    print(f"  social: {len(fresh)} cached, fetching {len(todo)} (news + reddit + dex)…")
    with ThreadPoolExecutor(max_workers=4) as ex:
        for cid, soc in zip(todo, ex.map(lambda cid: social_for(infos[cid], cfg), todo)):
            sc[cid] = {**soc, "_ts": now_ts()}
    save_json(SOCIAL_CACHE, sc)
    socials = {cid: sc[cid] for cid in infos}
    coins = []
    for cid in ids:
        mk = markets.get(cid)
        if not mk:
            print(f"  {cid}: not found on CoinGecko (check the id)"); continue
        c = build_coin(cid, mk, cache, cfg, social=socials.get(cid))
        coins.append(c)
        print(f"  {c['symbol']:<7} {fmt_usd(c['market']['current_price']):>12}  24h {c['market']['price_change_percentage_24h'] or 0:+.1f}%  "
              f"news48 {c['buzz']['news48']:>2}  reddit48 {c['buzz']['reddit48']:>2}  whale net 7d {fmt_usd(c['whales']['net'])}  signal {c['signal']}")
    save_json(CG_CACHE, cache)
    import hl_smart, recommend
    print("  Hyperliquid smart money…")
    try:
        hl = hl_smart.run(cfg, verbose=False)
    except Exception as e:
        print("  hl failed:", e); hl = fresh_hl(load_json(os.path.join(HERE, "hl.json"), {"coins": [], "traders": []}), str(e))
    by_sym = {c["coin"].upper(): c for c in hl.get("coins", [])}
    for c in coins:
        sm = by_sym.get(c["symbol"].upper())
        c["smart"] = {k: v for k, v in sm.items() if k != "holders"} if sm else None
    print("  second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)…")
    pos = {}
    try:
        import positioning
        pos = positioning.run([c["symbol"] for c in coins if recommend.category(c) != "stable"], cfg)
    except Exception as e:
        print("  positioning failed:", e)
    for c in coins: c["positioning"] = (pos.get("coins") or {}).get(c["symbol"].upper()) or None
    reco = recommend.run(coins)
    for r in reco["recs"]:
        print(f"  {r['action']:<5} {r['symbol']:<6} score {r['score']:+.2f} conf {r['confidence']}%  " + "; ".join(r["reasons"][:2]))
    for r in reco["closed_now"]:
        print(f"  closed {r['action']} {r['symbol']} {r['return']:+.1f}% ({r['why']})")
    print("  IPOs / listings / launches…")
    ipo = ipo_block()
    desk = load_json(DESK_JSON, {})
    desk.update({"coins": coins, "trending": cg_trending(), "updated": now_ts(), "x_enabled": bool(cfg.get("x_bearer_token")),
                 "reco": reco, "ipo": ipo, "hl": hl, "positioning": {k: v for k, v in pos.items() if k != "hist"},
                 "alerts": open(ALERTS_LOG).read().splitlines()[-60:][::-1] if os.path.exists(ALERTS_LOG) else [],
                 "feed": read_csv(TRADES_CSV)[-300:][::-1]})
    desk.setdefault("research", {})
    save_json(DESK_JSON, desk)
    render(desk, DASHBOARD)
    print(f"dashboard: {DASHBOARD}")
    weekly_tune()

def weekly_tune():
    """Run the self-review and the backtest once a week from inside the refresh. The workflow's own Monday 06:xx UTC
    step only fires when GitHub happens to start a run in that hour, and it often does not; this does not depend on it.
    Both scripts refuse to tune twice within six days, so the two triggers cannot double up."""
    import subprocess
    try:
        import backtest
        model = load_json(os.path.join(HERE, "model.json"), {})
        if not model: return
        due = [k for k in ("review", "backtest") if now_ts() - backtest.last_tuned(model, k) > 6.5 * 86400]
        for k in due:
            print(f"  weekly {k} is due, running it…")
            r = subprocess.run([sys.executable, "-u", os.path.join(HERE, f"{k}.py"), "--apply"], cwd=HERE, capture_output=True, text=True, timeout=900)
            print("    " + "\n    ".join((r.stdout or r.stderr or "").strip().splitlines()[-12:]))
    except Exception as e:
        print("  weekly tune skipped:", e)

def cmd_research(args):
    cfg = load_config(); cache = load_json(CG_CACHE, {})
    hit = cg_search(args.coin)
    if not hit:
        print(f"could not find '{args.coin}' on CoinGecko"); return
    cid = hit["id"]
    print(f"researching {hit['name']} ({hit['symbol'].upper()}), CoinGecko id '{cid}' …")
    mk = cg_markets([cid]).get(cid, {})
    coin = build_coin(cid, mk, cache, cfg, deep=True)
    save_json(CG_CACHE, cache)
    desk = load_json(DESK_JSON, {"coins": [], "research": {}})
    desk.setdefault("research", {})[coin["symbol"]] = coin
    save_json(DESK_JSON, desk)
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    out = os.path.join(RESEARCH_DIR, f"{coin['symbol']}.html")
    if os.path.isdir(os.path.join(HERE, "docs")): out = os.path.join(HERE, "docs", "research", f"{coin['symbol']}.html"); os.makedirs(os.path.dirname(out), exist_ok=True)
    render({"coins": [coin], "trending": [], "updated": now_ts(), "alerts": [], "feed": [], "research": {}, "single": True,
            "x_enabled": bool(cfg.get("x_bearer_token"))}, out)
    if desk.get("coins"):
        render(desk, DASHBOARD)
    m, i, w, b = coin["market"], coin["info"], coin["whales"], coin["buzz"]
    print(f"\n{coin['name']} ({coin['symbol']})  rank #{i.get('rank') or '-'}   {fmt_usd(m.get('current_price'))}   "
          f"1h {m.get('price_change_percentage_1h_in_currency') or 0:+.1f}%  24h {m.get('price_change_percentage_24h') or 0:+.1f}%  "
          f"7d {m.get('price_change_percentage_7d_in_currency') or 0:+.1f}%  30d {m.get('price_change_percentage_30d_in_currency') or 0:+.1f}%")
    print(f"  mcap {fmt_usd(m.get('market_cap'))}   FDV {fmt_usd(i.get('fdv'))}   vol24 {fmt_usd(m.get('total_volume'))}   "
          f"ATH {fmt_usd(i.get('ath'))} ({i.get('ath_change') or 0:+.0f}%, {i.get('ath_date')})")
    print(f"  community: X followers {i.get('twitter_followers') or '-'}  reddit subs {i.get('reddit_subs') or '-'}  "
          f"sentiment up {i.get('sentiment_up') or '-'}%   buzz: {b['news48']} news / {b['reddit48']} reddit posts in 48h" + (f" / {b['x']} X posts" if b["x"] else ""))
    print(f"  whales (14d): buys {fmt_usd(w['buys'])} sells {fmt_usd(w['sells'])} net {fmt_usd(w['net'])}; "
          f"held by {len(w['holders'])} tracked wallets worth {fmt_usd(w['held_usd'])}"
          + (f"  buyers: {', '.join(w['buyers'])}" if w["buyers"] else "") + (f"  sellers: {', '.join(w['sellers'])}" if w["sellers"] else ""))
    if coin["pairs"]:
        p = coin["pairs"][0]; print(f"  top DEX pool: {p['dex']} on {p['chain']}  liq {fmt_usd(p['liq'])}  vol24 {fmt_usd(p['vol24'])}  buys/sells 24h {p['buys24']}/{p['sells24']}")
    print("  latest news:")
    for n in coin["news"][:8]:
        print(f"    - {dt.datetime.fromtimestamp(n['ts'], dt.timezone.utc):%m-%d} {n['title'][:100]}  ({n['source']})")
    if coin["reddit"]:
        print("  reddit:")
        for r in coin["reddit"][:5]: print(f"    - r/{r['sub']}: {r['title'][:100]}")
    print("\n" + coin["ai"]["text"] + ("\n  (Claude desk note; add anthropic_api_key to config.json for this on every coin)" if coin["ai"]["source"] == "claude" else "\n  (rule-based take; add anthropic_api_key to config.json to get a written Claude note)"))
    print(f"\n  page: {out}")

def cmd_rescore(args):
    """Re-run recommendations + re-render from the last desk.json without refetching anything."""
    import recommend
    desk = load_json(DESK_JSON, {})
    if not desk.get("coins"): print("no desk.json yet, run refresh"); return
    hl = fresh_hl(load_json(os.path.join(HERE, "hl.json"), {"coins": [], "traders": []}))
    by_sym = {c["coin"].upper(): c for c in hl.get("coins", [])}
    for c in desk["coins"]:
        sm = by_sym.get(c["symbol"].upper()); c["smart"] = {k: v for k, v in sm.items() if k != "holders"} if sm else None
    desk["hl"] = hl
    try:
        import positioning
        pos = load_json(positioning.OUT, {})
        pz = positioning.per_coin(pos, [c["symbol"].upper() for c in desk["coins"]])
        desk["positioning"] = {**positioning.public(pos), "coins": pz}
    except Exception as e:
        print("  positioning skipped:", e); pz = {}
    for c in desk["coins"]: c["positioning"] = pz.get(c["symbol"].upper()) or None
    desk["reco"] = recommend.run(desk["coins"])
    desk["ipo"] = ipo_block()
    for r in desk["reco"]["recs"]:
        print(f"  {r['action']:<5} {r['symbol']:<6} score {r['score']:+.2f} whale {r['factors']['whale']:+.2f}  " + "; ".join(r["reasons"][:2]))
    save_json(DESK_JSON, desk); render(desk, DASHBOARD); print("dashboard re-rendered")

def cmd_focus(args):
    cfg = load_config()
    if args.action == "add" and args.coin:
        hit = cg_search(args.coin)
        if not hit: print("not found on CoinGecko"); return
        if hit["id"] not in cfg["focus_coins"]:
            cfg["focus_coins"].append(hit["id"]); save_config(cfg)
        print(f"added {hit['name']} ({hit['id']})")
    elif args.action == "remove" and args.coin:
        before = len(cfg["focus_coins"])
        cfg["focus_coins"] = [c for c in cfg["focus_coins"] if c != args.coin.lower() and not c.startswith(args.coin.lower())]
        save_config(cfg); print("removed" if len(cfg["focus_coins"]) < before else "not in the list (use the CoinGecko id, see `focus`)")
    elif args.action == "reset":
        cfg["focus_coins"] = auto_focus(cfg["focus_size"], cfg.get("focus_mode", "erc20")); save_config(cfg); print(f"focus list rebuilt ({cfg.get('focus_mode', 'erc20')} mode)")
    print(f"focus list ({len(cfg['focus_coins'])}): " + ", ".join(cfg["focus_coins"]))

def cmd_watch(args):
    import subprocess
    cycle = 0
    while True:
        try:
            subprocess.run([sys.executable, os.path.join(HERE, "whale_scanner.py"), "scan"], check=False)
            if cycle % 6 == 0:
                subprocess.run([sys.executable, os.path.join(HERE, "whale_scanner.py"), "holdings"], check=False)
            cmd_refresh(args)
        except KeyboardInterrupt:
            return
        except Exception as e:
            print("cycle error:", e)
        cycle += 1
        print(f"  next refresh in {args.every} min\n"); time.sleep(args.every * 60)

# ----------------------------------------------------------------------------- dashboard

def render(desk, path):
    tpl = open(os.path.join(HERE, "dashboard_template.html")).read()
    payload = json.dumps(desk).replace("</", "<\\/")
    out = tpl.replace("/*__DESK_DATA__*/null", payload)
    with open(path, "w") as f: f.write(out)
    if path == DASHBOARD:
        # hosted copy for the Claude artifact (it wraps the page itself, so no outer html/head/body tags)
        head = re.search(r"<head>(.*?)</head>", out, re.S).group(1)
        body = re.search(r"<body>(.*?)</body>", out, re.S).group(1)
        head = re.sub(r"<meta[^>]*>", "", head)
        with open(os.path.join(HERE, "dashboard_hosted.html"), "w") as f: f.write(head.strip() + "\n" + body.strip() + "\n")
        docs = os.path.join(HERE, "docs")
        if os.path.isdir(docs):                      # GitHub Pages copy
            with open(os.path.join(docs, "index.html"), "w") as f: f.write(out)

def main():
    ap = argparse.ArgumentParser(description="Coin desk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("refresh"); sub.add_parser("rescore")
    r = sub.add_parser("research"); r.add_argument("coin")
    f = sub.add_parser("focus"); f.add_argument("action", nargs="?", default="show", choices=["show", "add", "remove", "reset"]); f.add_argument("coin", nargs="?")
    w = sub.add_parser("watch"); w.add_argument("--every", type=int, default=15)
    a = ap.parse_args()
    {"refresh": cmd_refresh, "rescore": cmd_rescore, "research": cmd_research, "focus": cmd_focus, "watch": cmd_watch}[a.cmd](a)

if __name__ == "__main__":
    main()
