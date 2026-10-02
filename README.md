# Whale Desk (cloud)

Runs entirely on GitHub: a scheduled Action refreshes every 3 hours and GitHub Pages serves the dashboard.

* Dashboard: `https://<your-github-user>.github.io/<repo>/` (enable Pages: Settings → Pages → Source "Deploy from a branch", branch `main`, folder `/docs`)
* Manual run or a coin deep-dive: Actions → "Whale Desk refresh" → Run workflow (optionally type a coin, e.g. PEPE; the page lands at `/research/PEPE.html`)
* Keys (all optional) go in Settings → Secrets and variables → Actions: `COINGECKO_API_KEY` (free, makes it much faster), `ANTHROPIC_API_KEY` (written Claude desk note per coin), `X_BEARER_TOKEN` (X search, paid tier), `ETHERSCAN_API_KEY`
* Edit `config.json` to change the whale watchlist (`wallets`), the focus coins (`focus_coins`) or pin Hyperliquid traders from Nansen (`hl_traders`: `[{"address": "0x…", "label": "…"}]`). Commit, and the next run picks it up.
* The Action commits its own state back (trades, holdings, recommendations, model weights), so the learning loop persists.

The scripts also run unchanged on a laptop: `python3 whale_scanner.py scan`, `python3 coin_desk.py refresh`, open `dashboard.html`.

---

# Whale Wallet Scanner

Two parts: `whale_scanner.py` tracks a watchlist of Ethereum wallets (what they hold, when they buy or sell on DEXs) and
`coin_desk.py` turns that plus news, Reddit and market data into a dashboard for a focus list of ~20 coins.
No API keys needed: data comes from Blockscout (transfers, holdings, tx details) and DexScreener (prices, liquidity).

## Setup

    cd ~/Documents/whale-scanner
    python3 -m pip install requests        # already installed on this Mac

## Run

    python3 whale_scanner.py scan                 # new buys/sells/transfers since last run (first run: last 48h)
    python3 whale_scanner.py holdings             # every token each wallet holds right now, priced
    python3 whale_scanner.py report               # report.html: alerts, "most-held tokens", holdings, event feed
    python3 whale_scanner.py watch --every 10     # scan + report every 10 min until you Ctrl-C

Open `report.html` in a browser. The "tokens held by the most tracked wallets" table is the quickest read: it drops
stables, ETH wrappers and airdrops (identical balances everywhere) and shows what several wallets chose to hold. Everything else lands beside the script: `trades.csv`, `holdings.csv`, `alerts.log`.

The first `scan` is slow (a few minutes for 40 wallets; Blockscout takes several seconds per page). After that
it only reads what is new, so runs take well under a minute unless a market maker has gone wild.

## The watchlist (config.json)

41 wallets, every one with a source URL in the config so you can check the attribution yourself. Roughly:

* Individual traders whose DEX buys are the signal: PEPE early buyer, christian2022.eth, sifu.eth, Cobie, GCR, Arthur Hayes
  (3 wallets, `Arthur Hayes main` is the active one), Andrew Kang (rewkang.eth), Machi Big Brother, Humpy, Justin Sun.
* vitalik.eth is a sell signal: he dumps whatever gets airdropped to him.
* Liquid funds that do swap on-chain: DeFiance, Spartan, Arca, Abraxas (2), 7 Siblings, Trend Research (2).
* VCs, mostly holders whose outbound moves matter more than inbound: a16z, paradigm.eth, Multicoin, Dragonfly, Framework, Pantera, Animoca.
* Market makers and OTC desks (Wintermute, Cumberland, Galaxy OTC, Jump, DWF, Amber, GSR, Auros): huge flow, mostly inventory
  and listing support, useful for "token about to get distributed / listed" rather than conviction trades. If they clutter
  the feed, delete them from config.json.
* BitMine treasury: an ETH accumulator, included for completeness.

Add your own:

    python3 whale_scanner.py add 0x1234...abcd "Label"

Good hunting grounds for new addresses: any token page on Etherscan → Holders tab (skip exchanges and contracts),
Arkham entity pages, DeBank whale rankings, Nansen smart money, and Lookonchain / Onchain Lens / Spot On Chain posts,
which nearly always quote the full address. When a DexScreener chart shows an early big buy, click the txn, open the
buyer on Etherscan, add them.

Funds that custody through Coinbase Prime (Haun, Electric, Blockchain Capital, Brevan Howard, YZi Labs) have no public
trading wallet, so they are not in the list.


## Coin Desk (dashboard.html)

The whale scanner is the engine; `coin_desk.py` is the screen you actually look at. It keeps a focus list of
about 20 coins and, for each, pulls price + 90-day history (CoinGecko), news (Google News), Reddit chatter,
community sentiment, DEX pools (DexScreener) and the whale flows the scanner recorded, then renders
`dashboard.html`: a ticker tape, coin cards sorted by a signal score, and a slide-in panel per coin with charts,
an AI take, news, Reddit, whale moves, tracked holders and pools. Tabs along the top for the whale feed, alerts,
research pages and CoinGecko trending.

    python3 coin_desk.py refresh                # rebuild dashboard.html (first run ~5 min, then ~1 min: data is cached)
    python3 coin_desk.py research PEPE          # deep-dive any coin: prints a desk summary, writes research/PEPE.html, adds a card to the Research tab
    python3 coin_desk.py focus                  # show the focus list
    python3 coin_desk.py focus add pendle       # add / remove (CoinGecko id or ticker)
    python3 coin_desk.py focus remove leo-token
    python3 coin_desk.py focus reset            # rebuild from the top of the market (stables and wrapped coins skipped)
    python3 coin_desk.py watch --every 15       # whale scan + refresh in a loop; holdings every 6th cycle

The AI take on each coin is rule-based out of the box (momentum, whale net flow, chatter, sentiment, ATH distance,
pool depth). Put an Anthropic API key in `config.json` under `anthropic_api_key` and every coin also gets a written
desk note from Claude (stance, bull case, bear case, what would change its mind, sizing risk). Either way it is a
read of the data in front of it, not advice.

### X / Twitter

There is no free way in any more: Nitter mirrors are dead and X's search API is a paid tier (Basic, about $100 a month).
The desk has the hook ready: put a bearer token in `x_bearer_token` and the X tab on every coin fills with recent
posts ranked by likes and author reach, and X counts feed the buzz score. Without it you still get X indirectly:
news outlets quoting posts, CoinGecko's community sentiment vote, and a one-click link to the live $TICKER search on X.

### Optional keys (all free unless noted)

    coingecko_api_key   free demo key from coingecko.com/en/api: lifts the rate limit so refresh takes ~1 min instead of ~5
    anthropic_api_key   written Claude desk note per coin (paid per use, pennies per refresh)
    x_bearer_token      X API v2, paid tier
    etherscan_api_key   alternative transfer source for the whale scanner


## Recommendations (Recommend tab)

Each focus coin is scored on five factors, every one in the range -1 to +1: whale flow (net tracked-wallet DEX buys
scaled to the coin's market cap, plus clusters of buyers or sellers and big outbound transfers), news buzz (relative to
what is normal for a coin that size), crowd sentiment (CoinGecko vote, centred where it really sits), momentum (7d and 30d,
with a penalty for chasing a one-day spike) and DEX liquidity. The weighted sum is the score. Whale flow is the gate:
no tracked-wallet buying means no BUY, however loud the news; heavy tracked selling is a SELL on its own.

BUY and SELL calls are tracked from the moment they fire: entry price, +8% target, -6% stop, 7-day time limit, one open
call per coin with a 2-day cooldown. Every refresh marks them to market; when one closes, the factor weights move toward
whatever was present in a winner and away from whatever was present in a loser, and the BUY threshold rises when the
last-10 hit rate is under 45% and falls when it is over 60%. Weights, thresholds and the learning log live in
`model.json`; the call history in `recs.json`. The tab shows open calls with live P&L, closed calls, hit rate and
what the model has learned. Reset the learning with `rm model.json recs.json`.

    python3 coin_desk.py rescore    # re-run recommendations + IPO feed from the last data without refetching

Expect mostly WATCH at the start: the whale factor needs the scanner to have caught actual DEX buys of these tokens,
and that history builds up over days of `scan` runs.

## IPOs & Launches tab

Crypto-company IPO news (Kraken, Circle, Bullish and whoever is next), exchange-listing news, token launches and
airdrop news, and fresh DEX pairs from DexScreener's promoted and latest lists filtered to pools of $50k or more,
with age, buys vs sells and liquidity so a pump is visible as a pump.

## Hosted link

`coin_desk.py refresh` also writes `dashboard_hosted.html`, a copy formatted for the Claude artifact that holds the
phone-friendly link. A scheduled task ("Whale Desk refresh", every 3 hours) runs scan + refresh on this Mac and
republishes it; it needs the Mac awake and the task approved for this computer in the Claude app.

## How events are classified

Each transaction is read as a whole:

* token in and token out in the same tx → swap (buy of what came in, sell of what went out)
* token in, wallet sent the tx, ETH attached or a router / aggregator called → buy with ETH
* token in, someone else sent the tx → transfer_in (exchange withdrawal, airdrop, OTC delivery)
* token out, wallet called the token contract directly → transfer_out (plain send, often to an exchange)
* token out, wallet called anything else → sell for ETH

Stablecoins and WETH count as money, so USDC → PEPE is a buy of PEPE. Airdrop spam (tokens flagged scam by Blockscout
or with under $1k of DEX liquidity) is dropped before it reaches the feed; switch `hide_unpriced_transfers` off to see it.

## Alerts (alerts.log and top of report.html)

* BUY / SELL above `min_usd` (default $2,000, at today's price) with the Etherscan tx link
* NEW POSITION: first buy of a token the wallet had none of during the scan history
* FULL EXIT: a sell that takes the balance to about zero
* CLUSTER: `cluster_min_wallets` different wallets bought the same token inside `cluster_window_hours`
* THIN POOL: a buy into a pool under $50k, where the whale's own buy is most of the price move
* BIG TRANSFER: a plain in/out move of a non-stable token above `big_transfer_usd` (default $250k), which is how OTC
  deliveries and exchange deposits show up

Stablecoins and WETH never raise alerts: the funds shuffle USDC/USDS/USDT between Aave, Sky and exchanges all day.
Those show in the feed as `rotate` (stable-for-stable) or `defi` (borrow / repay / supply / claim) so you can still see them.

## Things to know

* USD values are at the current price, not the price when the trade happened.
* Native ETH moves are not events (only ERC-20 logs are read), so ETH → USDC shows as a buy of USDC.
* `holdings` reads the full on-chain token list per wallet, independent of scans.
* Blockscout occasionally throttles; the scanner retries and saves progress per wallet, so just run again.
* Optional: put a free Etherscan key in `etherscan_api_key` to use Etherscan for transfers instead (faster paging).
* Ethereum mainnet only. Base/Arbitrum need `BLOCKSCOUT` and the DexScreener chain slug changed; Solana is a different stack.
* None of this is advice. Whales are wrong often, hedge on exchanges you cannot see, and get front-run by everyone copying them.

## Self-improvement loop

Two layers tune the recommender:

1. Per trade (`recommend.learn`): every closed call nudges that category's factor weights and BUY threshold. Runs inside every 3-hourly refresh.
2. Weekly review (`review.py --apply`): looks at the whole sample: exit mix (target / stop / time), returns by category and by entry gate (whale vs top-trader), and which factors actually separated wins from losses. With enough closed calls (8+ per category) it adjusts targets, stops, holding window, whale gate and down-weights contrary factors. Runs Mondays 06:xx UTC in the workflow, or manually via Run workflow with `review = true`. Output: `review.md` / `review.json` in the repo and a `REVIEW` entry in the model log on the Recommend tab.

Run `python review.py` anytime for a read-only report.

3. Backtest (`backtest.py --apply`): replays the desk's own history (every committed desk.json, trades.csv whale flow, the 90-day price chart) and measures which factors actually predicted 1/3/5-day forward returns (rank correlation). Factor weights move a bounded step (x0.75 / x1.25) only when the sign is consistent across horizons with a decent sample. Also runs Mondays with the review. `backtest.md` is the readable report; the grid-search section is informational only.

Whale factor (since Oct 2026): DEX buys/sells plus exchange withdrawals (accumulation) minus exchange deposits (distribution), other transfers at quarter weight. Known exchange hot wallets are in `exchanges.py`. Market-maker wallets' exchange legs are ignored (inventory moves, not conviction).
