#!/usr/bin/env python3
"""
Whale Wallet Scanner
--------------------
Tracks a watchlist of Ethereum wallets, pulls their ERC-20 movements, works out
which ones are DEX buys / sells versus plain transfers, prices everything via
DexScreener and flags new positions, exits and "several whales bought the same
token" clusters.

Commands
  python3 whale_scanner.py scan                 # new activity since last run (lookback_hours on first run)
  python3 whale_scanner.py holdings             # full on-chain holdings of each wallet, priced
  python3 whale_scanner.py report               # build report.html from trades.csv + holdings.csv
  python3 whale_scanner.py watch --every 10     # scan + report every 10 minutes, forever
  python3 whale_scanner.py add 0xabc... "Label" # add a wallet to config.json

Data sources (no API keys needed)
  * Blockscout (eth.blockscout.com)  - transfers, tx details, holdings, spam reputation
  * DexScreener                       - live DEX price, liquidity, pair links
  * Etherscan V2 (optional key)       - alternative transfer source, deeper paging
"""
import argparse, csv, json, os, sys, time, datetime as dt
from collections import defaultdict
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "state.json")
TRADES_CSV = os.path.join(HERE, "trades.csv")
HOLDINGS_CSV = os.path.join(HERE, "holdings.csv")
ALERTS_LOG = os.path.join(HERE, "alerts.log")
REPORT_HTML = os.path.join(HERE, "report.html")
TX_CACHE = os.path.join(HERE, "tx_cache.json")

BLOCKSCOUT = "https://eth.blockscout.com/api/v2"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
STABLES = {"usdt", "usdc", "dai", "usde", "fdusd", "tusd", "usds", "pyusd", "frax", "lusd", "gusd", "usdp", "usd1", "crvusd", "gho",
           # ETH / BTC wrappers and liquid-staking receipts: swapping between these is a rotation, not a trade
           "weth", "steth", "wsteth", "weeth", "eeth", "reth", "rseth", "cbeth", "ezeth", "wbtc", "cbbtc", "tbtc", "lbtc", "fbtc"}

# Well known routers / aggregators. Used to label the venue; the tx-shape heuristic works without them.
KNOWN_ROUTERS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 R2",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal",
    "0x66a9893cc07d91d95644aedd05d03f95e1dba8af": "Uniswap Universal v2",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch v5",
    "0x111111125421ca6dc452d289314280a0f8842a65": "1inch v6",
    "0x111111125434b319222cdbf8c261674adb56f3ae": "1inch v4",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x",
    "0x6a000f20005980200259b80c5102003040001068": "Paraswap v6",
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41": "CoW Protocol",
    "0x881d40237659c251811cec9c364ef91dc08d300c": "Metamask Swap",
    "0x1231deb6f5749ef6ce6943a275a1d3e7486f4eae": "LI.FI",
    "0x6131b5fae19ea4f9d964eac0408e4408b66337b5": "KyberSwap",
    "0x00000000009726632680fb29d3f7a9734e3010e2": "Rainbow Router",
}

# ----------------------------------------------------------------------------- utils

def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def fmt_usd(v):
    try: v = float(v)
    except (TypeError, ValueError): return "-"
    if abs(v) >= 1e9: return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:,.1f}k"
    return f"${v:,.2f}"

def fmt_amt(v):
    try: v = float(v)
    except (TypeError, ValueError): return "-"
    if abs(v) >= 1e6: return f"{v:,.0f}"
    if abs(v) >= 1: return f"{v:,.2f}"
    return f"{v:.6f}"

def short(addr):
    return addr[:6] + "…" + addr[-4:] if addr else "?"

def log_alert(line):
    print("  !! " + line)
    with open(ALERTS_LOG, "a") as f:
        f.write(f"{now_iso()}  {line}\n")

def parse_ts(s):
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())

# ----------------------------------------------------------------------------- config

DEFAULT_CONFIG = {
    "etherscan_api_key": "",
    "lookback_hours": 48,
    "min_usd": 2000,
    "cluster_window_hours": 24,
    "cluster_min_wallets": 2,
    "hide_unpriced_transfers": True,
    "max_pages_per_wallet": 40,
    "max_tx_lookups_per_wallet": 150,  # busy market makers: beyond this, plain in/out transfers stay unresolved
    "min_usd_show": 1,                 # hide priced dust below this (address-poisoning pennies)
    "big_transfer_usd": 250000,        # alert on plain transfers of non-stable tokens above this
    "ignore_tokens": [],
    "wallets": []
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    if not os.path.exists(CONFIG_PATH):
        save_json(CONFIG_PATH, cfg)
    cfg["wallets"] = [
        {"address": w["address"].lower(), "label": w.get("label") or short(w["address"]), "type": w.get("type", "")}
        for w in cfg["wallets"]
    ]
    cfg["ignore_tokens"] = {t.lower() for t in cfg.get("ignore_tokens", [])}
    if os.environ.get("ETHERSCAN_API_KEY"): cfg["etherscan_api_key"] = os.environ["ETHERSCAN_API_KEY"]
    return cfg

# ----------------------------------------------------------------------------- HTTP

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "whale-scanner/1.0"

def get_json(url, params=None, retries=4, pause=0.15):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=40)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1)); continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(pause)
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))

# ----------------------------------------------------------------------------- Blockscout

class Blockscout:
    def __init__(self):
        self.tx_cache = load_json(TX_CACHE, {})

    def transfers(self, wallet, min_block, min_ts, max_pages):
        """ERC-20 transfers newest-first, stopping once we pass min_block or min_ts."""
        rows, params, pages = [], {"type": "ERC-20"}, 0
        while True:
            j = get_json(f"{BLOCKSCOUT}/addresses/{wallet}/token-transfers", params)
            if not j:
                break
            stop = False
            for it in j.get("items", []):
                blk = it.get("block_number") or 0
                if blk < min_block or parse_ts(it["timestamp"]) < min_ts:
                    stop = True; break
                tok = it.get("token") or {}
                try:
                    dec = int(tok.get("decimals") or it["total"].get("decimals") or 18)
                    amount = int(it["total"]["value"]) / (10 ** dec)
                except Exception:
                    continue
                rows.append({
                    "hash": it["transaction_hash"], "block": blk, "ts": parse_ts(it["timestamp"]),
                    "token": (tok.get("address_hash") or tok.get("address") or "").lower(),
                    "symbol": (tok.get("symbol") or "?")[:20], "decimals": dec,
                    "from": (it["from"]["hash"]).lower(), "to": (it["to"]["hash"]).lower(),
                    "amount": amount, "reputation": tok.get("reputation") or "",
                    "bs_price": float(tok["exchange_rate"]) if tok.get("exchange_rate") else 0.0,
                })
            pages += 1
            nxt = j.get("next_page_params")
            if stop or not nxt or pages >= max_pages:
                if pages >= max_pages and nxt and not stop:
                    print(f"    (capped at {max_pages} pages, wallet is very active; raise max_pages_per_wallet to go deeper)")
                break
            params = {"type": "ERC-20", **nxt}
        rows.sort(key=lambda r: (r["block"], r["hash"]))
        return rows

    def tx(self, h):
        if h in self.tx_cache:
            return self.tx_cache[h]
        j = get_json(f"{BLOCKSCOUT}/transactions/{h}") or {}
        info = {
            "from": ((j.get("from") or {}).get("hash") or "").lower(),
            "to": ((j.get("to") or {}).get("hash") or "").lower(),
            "to_name": (j.get("to") or {}).get("name") or "",
            "value": int(j.get("value") or 0) / 1e18,
            "method": j.get("method") or "",
        }
        self.tx_cache[h] = info
        return info

    def holdings(self, wallet):
        out, params = [], {"type": "ERC-20"}
        for _ in range(20):
            j = get_json(f"{BLOCKSCOUT}/addresses/{wallet}/tokens", params)
            if not j: break
            for it in j.get("items", []):
                tok = it.get("token") or {}
                try:
                    dec = int(tok.get("decimals") or 18)
                    bal = int(it.get("value") or 0) / (10 ** dec)
                except Exception:
                    continue
                out.append({"token": (tok.get("address_hash") or tok.get("address") or "").lower(),
                            "symbol": (tok.get("symbol") or "?")[:20], "name": tok.get("name") or "",
                            "balance": bal, "bs_price": float(tok["exchange_rate"]) if tok.get("exchange_rate") else 0.0,
                            "reputation": tok.get("reputation") or "", "holders": tok.get("holders_count")})
            nxt = j.get("next_page_params")
            if not nxt: break
            params = {"type": "ERC-20", **nxt}
        return out

    def eth(self, wallet):
        j = get_json(f"{BLOCKSCOUT}/addresses/{wallet}") or {}
        return int(j.get("coin_balance") or 0) / 1e18, float(j.get("exchange_rate") or 0)

    def save(self):
        if len(self.tx_cache) > 20000:
            self.tx_cache = dict(list(self.tx_cache.items())[-10000:])
        save_json(TX_CACHE, self.tx_cache)

# ----------------------------------------------------------------------------- Etherscan (optional)

def fetch_transfers_etherscan(cfg, wallet, start_block):
    out, page = [], 1
    while True:
        params = {"chainid": 1, "module": "account", "action": "tokentx", "address": wallet,
                  "startblock": start_block, "endblock": 99999999, "page": page, "offset": 1000,
                  "sort": "asc", "apikey": cfg["etherscan_api_key"]}
        r = get_json("https://api.etherscan.io/v2/api", params, pause=0.25)
        if r.get("status") != "1":
            if "No transactions" in str(r.get("message", "")):
                break
            raise RuntimeError(f"Etherscan: {r.get('message')} {r.get('result')}")
        for t in r["result"]:
            dec = int(t.get("tokenDecimal") or 18)
            out.append({"hash": t["hash"], "block": int(t["blockNumber"]), "ts": int(t["timeStamp"]),
                        "token": t["contractAddress"].lower(), "symbol": (t.get("tokenSymbol") or "?")[:20],
                        "decimals": dec, "from": t["from"].lower(), "to": t["to"].lower(),
                        "amount": int(t["value"]) / (10 ** dec), "reputation": "", "bs_price": 0.0})
        if len(r["result"]) < 1000: break
        page += 1
    return out

# ----------------------------------------------------------------------------- noise filter

ACCOUNTING_PREFIXES = ("variabledebt", "stabledebt", "aeth", "aethv", "aeth", "aethweth", "spweth", "cusdc", "ceth")
DEFI_VERBS = {"borrow", "repay", "supply", "deposit", "withdraw", "stake", "unstake", "claim", "redeem",
              "mint", "burn", "bridge", "delegate", "lock", "unlock", "harvest", "compound", "wrap", "unwrap",
              "repaywithpermit", "supplywithpermit", "depositfor", "withdrawto", "claimrewards", "getreward", "exit"}

def is_noise(r, p):
    """Airdrop spam, lookalike fakes (ÚЅDС), and lending-protocol accounting tokens."""
    sym = r["symbol"].lower()
    if r["reputation"] == "scam":
        return True
    if sym.startswith(ACCOUNTING_PREFIXES) or sym.startswith(("a", "sp", "c")) and sym.endswith(("usdc", "usdt", "weth", "dai")) and len(sym) <= 8:
        return True
    if not sym.isascii():                     # unicode lookalike tickers are always poisoning attempts
        return True
    if p["liq"] < 1000 and not r["bs_price"] and r["reputation"] != "ok":
        return True
    return False

# ----------------------------------------------------------------------------- classification

def prefetch_txs(bs, hashes, cap, workers=4):
    """Look up tx details in parallel; beyond `cap` we leave them unresolved."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [h for h in hashes if h not in bs.tx_cache][:cap]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda h: bs.tx(h), todo))

def classify(bs, wallet, rows, tx_cap=150):
    """Group transfers by tx and decide buy / sell / transfer_in / transfer_out."""
    by_tx = defaultdict(list)
    for r in rows:
        by_tx[r["hash"]].append(r)
    need = [h for h, trs in by_tx.items()
            if not (any(r["to"] == wallet for r in trs) and any(r["from"] == wallet for r in trs))]
    prefetch_txs(bs, need, tx_cap)
    events = []
    for h, trs in by_tx.items():
        inflow, outflow, sym, rep, bsp = defaultdict(float), defaultdict(float), {}, {}, {}
        for r in trs:
            sym[r["token"]] = r["symbol"]; rep[r["token"]] = r["reputation"]; bsp[r["token"]] = r["bs_price"]
            if r["to"] == wallet: inflow[r["token"]] += r["amount"]
            if r["from"] == wallet: outflow[r["token"]] += r["amount"]
        for t in list(inflow):                       # net tokens that went both ways in one tx
            if t in outflow:
                net = inflow[t] - outflow[t]
                del inflow[t]; del outflow[t]
                if net > 0: inflow[t] = net
                elif net < 0: outflow[t] = -net

        def is_money(t):
            return t == WETH or sym.get(t, "").lower() in STABLES

        ins = [t for t in inflow if not is_money(t)]; outs = [t for t in outflow if not is_money(t)]
        money_in = [t for t in inflow if is_money(t)]; money_out = [t for t in outflow if is_money(t)]
        needs_tx = not (inflow and outflow)           # swaps are self-evident, other shapes need tx context
        blank = {"from": "", "to": "", "to_name": "", "value": 0.0, "method": ""}
        tx = bs.tx_cache.get(h, blank) if needs_tx else blank   # only what prefetch resolved (cap)
        self_initiated = tx["from"] == wallet
        venue = KNOWN_ROUTERS.get(tx["to"]) or (tx["to_name"] if tx["to_name"] and tx["to"] not in sym else None)
        method = (tx["method"] or "").lower()
        defi = method in DEFI_VERBS or any(method.startswith(v) for v in ("borrow", "repay", "supply", "withdraw", "deposit", "stake", "unstake", "claim", "redeem"))
        ts, blk = trs[0]["ts"], trs[0]["block"]

        def emit(kind, token, amount, counter, note):
            events.append({"ts": ts, "block": blk, "hash": h, "wallet": wallet, "kind": kind,
                           "dir": "in" if token in inflow else "out", "bs_price": bsp.get(token, 0.0),
                           "money": is_money(token),
                           "token": token, "symbol": sym.get(token, "?"), "amount": amount,
                           "counter_symbol": sym.get(counter, "ETH") if counter else "ETH",
                           "via": venue or ("self" if self_initiated else "external"),
                           "reputation": rep.get(token, ""), "note": note})

        if inflow and outflow:
            for t in ins: emit("buy", t, inflow[t], (money_out or outs or [None])[0], "swap")
            for t in outs: emit("sell", t, outflow[t], (money_in or ins or [None])[0], "swap")
            if not ins and not outs:      # USDC <-> USDS <-> WETH shuffles: informational only
                for t in inflow: emit("rotate", t, inflow[t], (money_out or [None])[0], "stable/ETH rotation")
        elif inflow:
            for t, a in inflow.items():
                if defi and self_initiated:
                    emit("defi", t, a, None, f"{method} [{tx['to_name'] or short(tx['to'])}]")
                elif self_initiated and (tx["value"] > 0 or venue or tx["to"] not in (t, "")):
                    emit("buy", t, a, None, "bought with ETH" if tx["value"] > 0 else f"via {method or 'contract'}")
                else:
                    emit("transfer_in", t, a, None, "from " + short(tx["from"] or trs[0]["from"]))
        elif outflow:
            for t, a in outflow.items():
                if self_initiated and tx["to"] == t:
                    emit("transfer_out", t, a, None, "sent to " + short(trs[0]["to"]))
                elif defi and self_initiated:
                    emit("defi", t, a, None, f"{method} [{tx['to_name'] or short(tx['to'])}]")
                elif self_initiated:
                    emit("sell", t, a, None, "sold for ETH" if venue else f"via {method or short(tx['to'])}")
                elif tx["from"]:
                    emit("transfer_out", t, a, None, "pulled by " + short(tx["from"]))
                else:
                    emit("transfer_out", t, a, None, "to " + short(trs[0]["to"]) + " (unresolved)")
    events.sort(key=lambda e: (e["ts"], e["hash"]))
    return events

# ----------------------------------------------------------------------------- pricing

EMPTY_PRICE = {"price": 0.0, "liq": 0, "vol24": 0, "chg24": None, "dex": None, "url": None}

class Prices:
    def __init__(self):
        self.cache = {}

    def fetch(self, tokens):
        todo = [t for t in set(tokens) if t and t not in self.cache]
        for i in range(0, len(todo), 30):
            batch = todo[i:i + 30]
            try:
                pairs = get_json("https://api.dexscreener.com/tokens/v1/ethereum/" + ",".join(batch), pause=0.25) or []
            except Exception:
                pairs = []
            best = {}
            for p in pairs:
                t = (p.get("baseToken") or {}).get("address", "").lower()
                if t not in batch: continue
                liq = (p.get("liquidity") or {}).get("usd") or 0
                if t not in best or liq > best[t]["liq"]:
                    best[t] = {"price": float(p.get("priceUsd") or 0), "liq": liq,
                               "vol24": (p.get("volume") or {}).get("h24") or 0,
                               "chg24": (p.get("priceChange") or {}).get("h24"),
                               "dex": p.get("dexId"), "url": p.get("url")}
            for t in batch:
                self.cache[t] = best.get(t, dict(EMPTY_PRICE))

    def get(self, token):
        return self.cache.get((token or "").lower()) or dict(EMPTY_PRICE)

# ----------------------------------------------------------------------------- csv

TRADE_COLS = ["time_utc", "wallet_label", "wallet", "kind", "symbol", "token", "amount", "usd_now",
              "counter", "via", "note", "price_now", "liquidity_usd", "dex_url", "tx"]

def append_trades(rows):
    new = not os.path.exists(TRADES_CSV)
    with open(TRADES_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_COLS)
        if new: w.writeheader()
        for r in rows: w.writerow(r)

def read_csv(path):
    if not os.path.exists(path): return []
    with open(path) as f:
        return list(csv.DictReader(f))

# ----------------------------------------------------------------------------- scan

def cmd_scan(args):
    cfg = load_config()
    if not cfg["wallets"]:
        print("No wallets in config.json yet. Add one:  python3 whale_scanner.py add 0x... \"Label\""); return
    bs, prices = Blockscout(), Prices()
    state = load_json(STATE_PATH, {})
    state.setdefault("last_block", {}); state.setdefault("holdings", {}); state.setdefault("recent_buys", [])
    use_es = bool(cfg.get("etherscan_api_key"))
    # approximate current head from a fresh transfer would need a call; use timestamps instead
    cutoff_ts = int(time.time()) - cfg["lookback_hours"] * 3600
    print(f"[{now_iso()}] scanning {len(cfg['wallets'])} wallets via {'Etherscan' if use_es else 'Blockscout'}")

    all_events, highest = [], {}
    for w in cfg["wallets"]:
        addr, label = w["address"], w["label"]
        last = state["last_block"].get(addr, 0)
        try:
            if use_es:
                rows = fetch_transfers_etherscan(cfg, addr, last + 1)
                rows = [r for r in rows if r["ts"] >= cutoff_ts or last]
            else:
                rows = bs.transfers(addr, last + 1 if last else 0, 0 if last else cutoff_ts, cfg["max_pages_per_wallet"])
        except Exception as e:
            print(f"  {label}: fetch failed ({e})"); continue
        rows = [r for r in rows if r["token"] and r["token"] not in cfg["ignore_tokens"]]
        if cfg.get("hide_unpriced_transfers", True) and rows:
            # drop airdrop spam, address-poisoning fakes and DeFi accounting tokens before classification
            prices.fetch([r["token"] for r in rows])
            n = len(rows)
            rows = [r for r in rows if not is_noise(r, prices.get(r["token"]))]
            hidden = n - len(rows)
        else:
            hidden = 0
        events = classify(bs, addr, rows, cfg.get("max_tx_lookups_per_wallet", 150))
        for e in events: e["label"] = label
        all_events += events
        if rows:
            highest[addr] = max(r["block"] for r in rows)
        elif last:
            highest[addr] = last
        else:
            highest[addr] = 0
        print(f"  {label:<26} {len(rows):>4} transfers -> {len(events):>3} events" + (f"  ({hidden} spam hidden)" if hidden else ""))
    bs.save()
    # a wallet with no rows on the first run keeps last_block=0 but we still must not re-read history
    # forever, so remember the scan time and use it as the cutoff next time
    for addr, b in highest.items():
        if b: state["last_block"][addr] = b
    state["last_scan_ts"] = int(time.time())

    if not all_events:
        print("  nothing new."); save_json(STATE_PATH, state); return

    prices.fetch([e["token"] for e in all_events])
    out_rows, alerts = [], []
    holdings = state["holdings"]
    recent = [b for b in state["recent_buys"] if b["ts"] > time.time() - cfg["cluster_window_hours"] * 3600]

    print(f"\n  {'time (UTC)':<12} {'wallet':<22} {'kind':<12} {'amount':>16} {'token':<10} {'~USD now':>11}  detail")
    for e in all_events:
        p = prices.get(e["token"])
        price = e["bs_price"] if e["money"] and e["bs_price"] else (p["price"] or e["bs_price"])
        usd = e["amount"] * price if price else None
        t = dt.datetime.fromtimestamp(e["ts"], dt.timezone.utc).strftime("%m-%d %H:%M")
        if usd is not None and usd < cfg.get("min_usd_show", 1):
            continue
        big = usd is not None and usd >= cfg["min_usd"] and not e["money"]   # stables / WETH never alert
        flag = "*" if big else " "
        detail = e["note"] + (f" [{e['via']}]" if e["via"] not in ("self", "external") and e["kind"] != "defi" else "")
        print(f" {flag}{t:<12} {e['label'][:21]:<22} {e['kind']:<12} {fmt_amt(e['amount']):>16} {e['symbol'][:9]:<10} {fmt_usd(usd) if usd is not None else '-':>11}  {detail}")

        hw = holdings.setdefault(e["wallet"], {})
        prev = hw.get(e["token"], 0.0)
        if e["dir"] == "in":
            hw[e["token"]] = prev + e["amount"]
            if e["kind"] == "buy" and big:
                if prev == 0:
                    alerts.append(f"NEW POSITION  {e['label']} bought {fmt_amt(e['amount'])} {e['symbol']} (~{fmt_usd(usd)}) {p['url'] or ''}")
                recent.append({"ts": e["ts"], "wallet": e["wallet"], "label": e["label"], "token": e["token"], "symbol": e["symbol"]})
        else:
            hw[e["token"]] = max(0.0, prev - e["amount"])
            if e["kind"] == "sell" and prev > 0 and hw[e["token"]] <= prev * 0.02 and big:
                alerts.append(f"FULL EXIT     {e['label']} sold out of {e['symbol']} (~{fmt_usd(usd)})")
        if big and e["kind"] in ("buy", "sell"):
            alerts.append(f"{e['kind'].upper():<13} {e['label']} {fmt_amt(e['amount'])} {e['symbol']} ~{fmt_usd(usd)} via {e['via']}  https://etherscan.io/tx/{e['hash']}")
        if big and e["kind"] in ("transfer_in", "transfer_out") and usd >= cfg.get("big_transfer_usd", 250000):
            alerts.append(f"BIG TRANSFER  {e['label']} {e['kind'].replace('_', ' ')} {fmt_amt(e['amount'])} {e['symbol']} ~{fmt_usd(usd)} {e['note']}  https://etherscan.io/tx/{e['hash']}")
        if big and e["kind"] == "buy" and p["liq"] and p["liq"] < 50000 and not e["money"]:
            alerts.append(f"THIN POOL     {e['symbol']} liquidity only {fmt_usd(p['liq'])}: that buy is most of the move")

        out_rows.append({
            "time_utc": dt.datetime.fromtimestamp(e["ts"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "wallet_label": e["label"], "wallet": e["wallet"], "kind": e["kind"], "symbol": e["symbol"],
            "token": e["token"], "amount": f"{e['amount']:.8f}", "usd_now": f"{usd:.2f}" if usd is not None else "",
            "counter": e["counter_symbol"], "via": e["via"], "note": e["note"], "price_now": price,
            "liquidity_usd": p["liq"], "dex_url": p["url"] or "", "tx": e["hash"],
        })

    by_tok, sym_of = defaultdict(set), {}
    for b in recent:
        by_tok[b["token"]].add(b["label"]); sym_of[b["token"]] = b["symbol"]
    already = set(state.get("clusters_alerted", []))
    for tok, labels in by_tok.items():
        if len(labels) >= cfg["cluster_min_wallets"] and tok not in already:
            alerts.append(f"CLUSTER       {len(labels)} wallets bought {sym_of[tok]} within {cfg['cluster_window_hours']}h: {', '.join(sorted(labels))}  {prices.get(tok)['url'] or ''}")
            already.add(tok)
    state["clusters_alerted"] = list(already)[-500:]
    state["recent_buys"] = recent[-2000:]

    append_trades(out_rows)
    if alerts:
        print("\n  alerts:")
        for a in alerts: log_alert(a)
    save_json(STATE_PATH, state)
    print(f"\n  {len(out_rows)} events -> trades.csv, {len(alerts)} alerts -> alerts.log")

# ----------------------------------------------------------------------------- holdings

def cmd_holdings(args):
    cfg = load_config()
    bs, prices = Blockscout(), Prices()
    rows, totals = [], {}
    print(f"[{now_iso()}] fetching holdings for {len(cfg['wallets'])} wallets (4 in parallel)")
    from concurrent.futures import ThreadPoolExecutor
    def fetch(w):
        try:
            return w, bs.eth(w["address"]), bs.holdings(w["address"]), None
        except Exception as e:
            return w, (0, 0), [], e
    with ThreadPoolExecutor(max_workers=4) as ex:
        fetched = list(ex.map(fetch, cfg["wallets"]))
    for w, (eth, eth_price), toks, err in fetched:
        addr, label = w["address"], w["label"]
        if err:
            print(f"  {label}: failed ({err})"); continue
        toks = [t for t in toks if t["reputation"] != "scam" and t["token"] not in cfg["ignore_tokens"]]
        # DexScreener for the biggest positions (live price beats Blockscout's cached rate) plus anything unpriced
        toks.sort(key=lambda t: -(t["balance"] * t["bs_price"]))
        prices.fetch([t["token"] for t in toks[:60]] + [t["token"] for t in toks if not t["bs_price"]][:60])
        rows.append({"wallet_label": label, "wallet": addr, "symbol": "ETH", "token": "native", "balance": eth,
                     "price": eth_price, "usd": eth * eth_price, "chg24": "", "liquidity_usd": "", "dex_url": ""})
        for t in toks:
            p = prices.get(t["token"])
            price = p["price"] if (p["price"] and p["liq"] >= 100000) else (t["bs_price"] or p["price"])
            rows.append({"wallet_label": label, "wallet": addr, "symbol": t["symbol"], "token": t["token"],
                         "balance": t["balance"], "price": price, "usd": t["balance"] * price,
                         "chg24": p["chg24"] if p["chg24"] is not None else "", "liquidity_usd": p["liq"] or "",
                         "dex_url": p["url"] or f"https://dexscreener.com/ethereum/{t['token']}"})
        totals[label] = sum(r["usd"] for r in rows if r["wallet"] == addr)
        print(f"  {label:<26} {len(toks):>4} tokens   tracked value {fmt_usd(totals[label])}")
    if not rows:
        return
    rows.sort(key=lambda r: (-totals[r["wallet_label"]], -r["usd"]))
    with open(HOLDINGS_CSV, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader()
        for r in rows: wr.writerow(r)
    cur = None
    for r in rows:
        if r["usd"] < args.min_usd:
            continue
        if r["wallet_label"] != cur:
            cur = r["wallet_label"]
            print(f"\n{cur}  ({short(r['wallet'])})  ~{fmt_usd(totals[cur])}")
            print(f"  {'token':<10} {'balance':>18} {'price':>14} {'value':>12} {'24h%':>7}")
        chg = f"{float(r['chg24']):+.1f}" if r["chg24"] not in ("", None) else "-"
        print(f"  {r['symbol'][:9]:<10} {fmt_amt(r['balance']):>18} {('$%.6g' % r['price']) if r['price'] else '-':>14} {fmt_usd(r['usd']):>12} {chg:>7}")
    print(f"\n  full table in holdings.csv (unpriced tokens included there with value 0)")

# ----------------------------------------------------------------------------- report

def cmd_report(args):
    trades = read_csv(TRADES_CSV)[-500:][::-1]
    holdings = read_csv(HOLDINGS_CSV)
    alerts = open(ALERTS_LOG).read().splitlines()[-80:] if os.path.exists(ALERTS_LOG) else []

    def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;")
    tr_rows = "".join(
        f"<tr><td>{esc(t['time_utc'])}</td><td>{esc(t['wallet_label'])}</td>"
        f"<td><span class='k {esc(t['kind'])}'>{esc(t['kind'])}</span></td><td class='r'>{fmt_amt(t['amount'])}</td>"
        f"<td>{'<a href=%s target=_blank>%s</a>' % (esc(t['dex_url']), esc(t['symbol'])) if t['dex_url'] else esc(t['symbol'])}</td>"
        f"<td class='r'>{fmt_usd(t['usd_now']) if t['usd_now'] else '-'}</td><td>{esc(t['via'])}</td><td class='m'>{esc(t['note'])}</td>"
        f"<td><a href='https://etherscan.io/tx/{esc(t['tx'])}' target=_blank>tx</a></td></tr>" for t in trades)
    hd_rows = "".join(
        f"<tr><td>{esc(h['wallet_label'])}</td><td><a href='{esc(h['dex_url'])}' target=_blank>{esc(h['symbol'])}</a></td>"
        f"<td class='r'>{fmt_amt(h['balance'])}</td><td class='r'>{fmt_usd(h['usd'])}</td>"
        f"<td class='r'>{esc(h['chg24'] or '-')}</td></tr>"
        for h in holdings if float(h["usd"] or 0) >= 1000)
    # token concentration: which tokens are held by the most wallets
    by_tok = defaultdict(lambda: {"wallets": set(), "usd": 0.0, "bals": []})
    for h in holdings:
        if h["symbol"] == "ETH" or h["symbol"].lower() in STABLES or h["symbol"].lower() in ("weth", "wsteth", "weeth", "steth") \
                or float(h["usd"] or 0) < 1000: continue
        d = by_tok[h["symbol"]]
        d["wallets"].add(h["wallet_label"]); d["usd"] += float(h["usd"]); d["bals"].append(round(float(h["balance"]), 2))
    # identical balances across wallets = airdrop, not conviction
    conc = [(s_, v) for s_, v in by_tok.items() if not (len(v["bals"]) >= 3 and len(set(v["bals"])) == 1)]
    conc = sorted(conc, key=lambda kv: (-len(kv[1]["wallets"]), -kv[1]["usd"]))[:40]
    conc_rows = "".join(f"<tr><td>{esc(s)}</td><td class='r'>{len(v['wallets'])}</td><td class='r'>{fmt_usd(v['usd'])}</td>"
                        f"<td class='m'>{esc(', '.join(sorted(v['wallets'])))}</td></tr>" for s, v in conc)
    al_rows = "".join(f"<li>{esc(a)}</li>" for a in reversed(alerts))
    html = f"""<!doctype html><html><head><meta charset=utf-8><title>Whale Scanner</title>
<style>body{{font:14px -apple-system,Segoe UI,sans-serif;margin:24px;color:#e8e8e8;background:#111}}h1,h2{{font-weight:600}}
table{{border-collapse:collapse;width:100%;margin-bottom:28px}}td,th{{padding:6px 8px;border-bottom:1px solid #2a2a2a;text-align:left;white-space:nowrap}}
th{{color:#999;font-weight:500}}td.r{{text-align:right;font-variant-numeric:tabular-nums}}td.m{{color:#999;white-space:normal}}
.k{{padding:2px 7px;border-radius:4px;font-size:12px}}.k.buy{{background:#14532d}}.k.sell{{background:#7f1d1d}}.k.transfer_in,.k.transfer_out{{background:#333}}.k.rotate,.k.defi{{background:#1e3a5f}}
a{{color:#7dd3fc;text-decoration:none}}ul{{line-height:1.7;font-family:ui-monospace,Menlo,monospace;font-size:12.5px}}small{{color:#888}}</style></head><body>
<h1>Whale Scanner <small>generated {now_iso()}</small></h1>
<h2>Alerts (newest first)</h2><ul>{al_rows or '<li>none yet</li>'}</ul>
<h2>Tokens held by the most tracked wallets (≥ $1k positions)</h2>
<table><tr><th>token</th><th>wallets</th><th>combined value</th><th>who</th></tr>{conc_rows or '<tr><td colspan=4>run holdings first</td></tr>'}</table>
<h2>Holdings (≥ $1k)</h2><table><tr><th>wallet</th><th>token</th><th>balance</th><th>value</th><th>24h %</th></tr>{hd_rows}</table>
<h2>Recent events (newest first, USD at current price)</h2>
<table><tr><th>time UTC</th><th>wallet</th><th>kind</th><th>amount</th><th>token</th><th>~USD</th><th>via</th><th>detail</th><th></th></tr>{tr_rows}</table>
</body></html>"""
    with open(REPORT_HTML, "w") as f: f.write(html)
    print(f"report written: {REPORT_HTML}")

# ----------------------------------------------------------------------------- watch / add

def cmd_watch(args):
    while True:
        try:
            cmd_scan(args); cmd_report(args)
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(f"scan error: {e}")
        print(f"  sleeping {args.every} min…\n")
        time.sleep(args.every * 60)

def cmd_add(args):
    cfg = load_json(CONFIG_PATH, dict(DEFAULT_CONFIG))
    addr = args.address.lower()
    if not (addr.startswith("0x") and len(addr) == 42):
        print("that does not look like an Ethereum address"); return
    if any(w["address"].lower() == addr for w in cfg["wallets"]):
        print("already in the watchlist"); return
    cfg["wallets"].append({"address": addr, "label": args.label or short(addr)})
    save_json(CONFIG_PATH, cfg)
    print(f"added {args.label or short(addr)} ({len(cfg['wallets'])} wallets tracked)")

def main():
    ap = argparse.ArgumentParser(description="Whale wallet scanner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    h = sub.add_parser("holdings"); h.add_argument("--min-usd", type=float, default=1000)
    sub.add_parser("report")
    w = sub.add_parser("watch"); w.add_argument("--every", type=int, default=10)
    a = sub.add_parser("add"); a.add_argument("address"); a.add_argument("label", nargs="?")
    args = ap.parse_args()
    {"scan": cmd_scan, "holdings": cmd_holdings, "report": cmd_report, "watch": cmd_watch, "add": cmd_add}[args.cmd](args)

if __name__ == "__main__":
    main()
