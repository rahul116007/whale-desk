# Whale Desk backtest  2026-10-09 09:33Z

52 refresh snapshots over 31.7 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.10 (n=630), 3d -0.02 (n=594), 5d -0.09 (n=558)
- news: 1d -0.19 (n=522), 3d -0.35 (n=486), 5d -0.49 (n=450)
- whale: 1d +0.02 (n=328), 3d -0.04 (n=304), 5d -0.09 (n=282)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d +0.03 (n=789), 3d -0.04 (n=641), 5d -0.17 (n=461)
- smart: 1d +0.07 (n=789), 3d +0.04 (n=641), 5d +0.05 (n=461)
- news: 1d +0.05 (n=789), 3d +0.17 (n=641), 5d +0.24 (n=461)
- sentiment: 1d -0.06 (n=789), 3d -0.03 (n=641), 5d -0.05 (n=461)
- momentum: 1d -0.12 (n=789), 3d -0.10 (n=641), 5d -0.12 (n=461)
- liquidity: 1d +0.03 (n=789), 3d -0.01 (n=641), 5d -0.05 (n=461)
- score: 1d -0.02 (n=789), 3d +0.05 (n=641), 5d +0.04 (n=461)
- lighter: 1d -0.36 (n=72), 3d n/a (n=7)
- vaults: 1d -0.23 (n=58), 3d n/a (n=4)
- cextop: 1d -0.01 (n=176), 3d -0.07 (n=14)
- funding: 1d +0.16 (n=167), 3d +0.08 (n=14)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 2.9 days of history, no consistent edge yet
- vaults: watching, 2.9 days of history, no consistent edge yet
- cextop: watching, 2.9 days of history, no consistent edge yet
- funding: watching, 2.9 days of history, no consistent edge yet

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=12 hit 41.7% avg -0.32%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=114 hit 50.0% avg 1.09%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=14 hit 35.7% avg 0.46%

## Changes applied
- major.weights.news 0.16->0.12 (daily IC -0.35)
- alt.weights.news 0.27->0.20 (daily IC -0.35)
- meme.weights.news 0.68->0.51 (daily IC -0.35)
- major.weights.momentum 0.68->0.54 (snapshot IC -0.10)
- alt.weights.momentum 0.26->0.21 (snapshot IC -0.10)
- meme.weights.momentum 0.80->0.64 (snapshot IC -0.10)
