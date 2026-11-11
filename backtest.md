# Whale Desk backtest  2026-11-11 07:01Z

189 refresh snapshots over 64.0 days; 644 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.20 (n=626), 3d +0.08 (n=590), 5d +0.05 (n=554)
- news: 1d -0.04 (n=554), 3d -0.03 (n=518), 5d +0.02 (n=482)
- whale: 1d -0.07 (n=455), 3d -0.11 (n=427), 5d -0.13 (n=399)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.04 (n=3309), 3d -0.06 (n=3225), 5d -0.10 (n=3085)
- smart: 1d -0.09 (n=3309), 3d -0.11 (n=3225), 5d -0.09 (n=3085)
- news: 1d +0.06 (n=3309), 3d +0.15 (n=3225), 5d +0.21 (n=3085)
- sentiment: 1d -0.02 (n=3309), 3d -0.03 (n=3225), 5d -0.00 (n=3085)
- momentum: 1d -0.17 (n=3309), 3d -0.18 (n=3225), 5d -0.15 (n=3085)
- liquidity: 1d +0.03 (n=3309), 3d +0.00 (n=3225), 5d -0.01 (n=3085)
- score: 1d -0.11 (n=3309), 3d -0.10 (n=3225), 5d -0.03 (n=3085)
- lighter: 1d -0.13 (n=1036), 3d -0.21 (n=998), 5d -0.06 (n=943)
- vaults: 1d -0.00 (n=864), 3d +0.07 (n=831), 5d +0.17 (n=793)
- cextop: 1d -0.02 (n=2696), 3d -0.01 (n=2594), 5d +0.01 (n=2454)
- funding: 1d +0.05 (n=2618), 3d +0.12 (n=2516), 5d +0.11 (n=2376)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 35.2 days of history, consistent IC -0.06
- vaults: watching, 35.2 days of history, no consistent edge yet
- cextop: watching, 35.2 days of history, no consistent edge yet
- funding: live, 35.2 days of history, no consistent edge yet

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=12 hit 8.3% avg -2.5%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=112 hit 27.7% avg -2.17%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=13 hit 38.5% avg 0.39%

## Changes applied
- major.weights.whale 0.16->0.12 (daily IC -0.11)
- alt.weights.whale 0.45->0.34 (daily IC -0.11)
- meme.weights.whale 0.38->0.28 (daily IC -0.11)
- major.weights.smart 0.48->0.39 (snapshot IC -0.09)
- alt.weights.smart 0.29->0.23 (snapshot IC -0.09)
- meme.weights.smart 0.41->0.33 (snapshot IC -0.09)
- major.weights.momentum 0.58->0.46 (snapshot IC -0.17)
- alt.weights.momentum 0.24->0.19 (snapshot IC -0.17)
- meme.weights.momentum 0.64->0.51 (snapshot IC -0.17)
