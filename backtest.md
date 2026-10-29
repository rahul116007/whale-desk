# Whale Desk backtest  2026-10-29 06:20Z

148 refresh snapshots over 51.6 days; 644 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.23 (n=626), 3d +0.06 (n=590), 5d +0.03 (n=554)
- news: 1d -0.02 (n=446), 3d +0.05 (n=410), 5d +0.12 (n=374)
- whale: 1d -0.06 (n=405), 3d -0.15 (n=379), 5d -0.22 (n=353)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.04 (n=2535), 3d -0.09 (n=2409), 5d -0.15 (n=2193)
- smart: 1d -0.11 (n=2535), 3d -0.15 (n=2409), 5d -0.10 (n=2193)
- news: 1d +0.01 (n=2535), 3d +0.09 (n=2409), 5d +0.17 (n=2193)
- sentiment: 1d -0.05 (n=2535), 3d -0.05 (n=2409), 5d -0.01 (n=2193)
- momentum: 1d -0.21 (n=2535), 3d -0.25 (n=2409), 5d -0.19 (n=2193)
- liquidity: 1d +0.01 (n=2535), 3d -0.01 (n=2409), 5d -0.03 (n=2193)
- score: 1d -0.17 (n=2535), 3d -0.17 (n=2409), 5d -0.08 (n=2193)
- lighter: 1d -0.17 (n=722), 3d -0.33 (n=662), 5d -0.21 (n=566)
- vaults: 1d -0.08 (n=605), 3d -0.06 (n=552), 5d -0.00 (n=499)
- cextop: 1d -0.03 (n=1922), 3d -0.01 (n=1778), 5d +0.03 (n=1562)
- funding: 1d +0.05 (n=1844), 3d +0.15 (n=1700), 5d +0.12 (n=1484)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 22.7 days of history, consistent IC -0.17
- vaults: watching, 22.7 days of history, no consistent edge yet
- cextop: watching, 22.7 days of history, no consistent edge yet
- funding: live, 22.7 days of history, consistent IC +0.05

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=10 hit 30.0% avg -1.33%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=112 hit 41.1% avg -0.19%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=13 hit 53.8% avg 0.13%

## Changes applied
- major.weights.whale 0.28->0.21 (daily IC -0.15)
- alt.weights.whale 0.60->0.45 (daily IC -0.15)
- meme.weights.whale 0.68->0.51 (daily IC -0.15)
- major.weights.smart 0.76->0.60 (snapshot IC -0.11)
- alt.weights.smart 0.46->0.37 (snapshot IC -0.11)
- meme.weights.smart 0.64->0.51 (snapshot IC -0.11)
- major.weights.momentum 0.90->0.72 (snapshot IC -0.21)
- alt.weights.momentum 0.31->0.25 (snapshot IC -0.21)
- meme.weights.momentum 1.00->0.80 (snapshot IC -0.21)
- major.weights.funding 0.30->0.36 (snapshot IC +0.05)
- alt.weights.funding 0.30->0.36 (snapshot IC +0.05)
- meme.weights.funding 0.30->0.36 (snapshot IC +0.05)
