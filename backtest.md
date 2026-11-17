# Whale Desk backtest  2026-11-17 23:07Z

212 refresh snapshots over 71.2 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.24 (n=630), 3d +0.18 (n=594), 5d +0.10 (n=558)
- news: 1d +0.03 (n=558), 3d -0.04 (n=522), 5d -0.01 (n=486)
- whale: 1d -0.04 (n=470), 3d -0.05 (n=442), 5d -0.12 (n=414)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.03 (n=3709), 3d -0.06 (n=3583), 5d -0.10 (n=3457)
- smart: 1d -0.05 (n=3709), 3d -0.04 (n=3583), 5d +0.01 (n=3457)
- news: 1d +0.06 (n=3709), 3d +0.15 (n=3583), 5d +0.23 (n=3457)
- sentiment: 1d -0.02 (n=3709), 3d -0.03 (n=3583), 5d -0.01 (n=3457)
- momentum: 1d -0.11 (n=3709), 3d -0.09 (n=3583), 5d -0.08 (n=3457)
- liquidity: 1d +0.03 (n=3709), 3d +0.02 (n=3583), 5d +0.01 (n=3457)
- score: 1d -0.09 (n=3709), 3d -0.07 (n=3583), 5d -0.01 (n=3457)
- lighter: 1d -0.10 (n=1183), 3d -0.16 (n=1133), 5d -0.02 (n=1086)
- vaults: 1d +0.03 (n=988), 3d +0.14 (n=940), 5d +0.23 (n=902)
- cextop: 1d -0.01 (n=3096), 3d -0.01 (n=2952), 5d +0.02 (n=2826)
- funding: 1d +0.03 (n=3018), 3d +0.05 (n=2874), 5d +0.05 (n=2748)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 42.4 days of history, no consistent edge yet
- vaults: watching, 42.4 days of history, no consistent edge yet
- cextop: watching, 42.4 days of history, no consistent edge yet
- funding: live, 42.4 days of history, no consistent edge yet

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=15 hit 13.3% avg -2.23%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=115 hit 22.6% avg -2.98%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=15 hit 26.7% avg -1.88%

## Changes applied
- major.weights.whale 0.12->0.10 (daily IC -0.05)
- alt.weights.whale 0.32->0.24 (daily IC -0.05)
- meme.weights.whale 0.28->0.21 (daily IC -0.05)
- major.weights.momentum 0.65->0.82 (daily IC +0.10)
- alt.weights.momentum 0.25->0.31 (daily IC +0.10)
- meme.weights.momentum 0.51->0.64 (daily IC +0.10)
