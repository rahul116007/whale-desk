# Whale Desk backtest  2026-11-24 14:10Z

232 refresh snapshots over 77.7 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.23 (n=630), 3d +0.19 (n=594), 5d +0.18 (n=558)
- news: 1d -0.04 (n=576), 3d -0.18 (n=540), 5d -0.30 (n=504)
- whale: 1d -0.02 (n=477), 3d -0.01 (n=449), 5d +0.01 (n=421)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.01 (n=4067), 3d -0.03 (n=3975), 5d -0.05 (n=3867)
- smart: 1d -0.04 (n=4067), 3d -0.02 (n=3975), 5d +0.04 (n=3867)
- news: 1d +0.04 (n=4067), 3d +0.13 (n=3975), 5d +0.20 (n=3867)
- sentiment: 1d -0.04 (n=4067), 3d -0.05 (n=3975), 5d -0.02 (n=3867)
- momentum: 1d -0.09 (n=4067), 3d -0.06 (n=3975), 5d +0.01 (n=3867)
- liquidity: 1d +0.02 (n=4067), 3d +0.01 (n=3975), 5d +0.03 (n=3867)
- score: 1d -0.10 (n=4067), 3d -0.08 (n=3975), 5d -0.00 (n=3867)
- lighter: 1d -0.08 (n=1312), 3d -0.12 (n=1272), 5d -0.01 (n=1233)
- vaults: 1d +0.04 (n=1052), 3d +0.16 (n=1040), 5d +0.29 (n=1026)
- cextop: 1d -0.02 (n=3454), 3d -0.03 (n=3344), 5d -0.03 (n=3236)
- funding: 1d +0.03 (n=3376), 3d +0.04 (n=3266), 5d -0.02 (n=3158)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 48.9 days of history, no consistent edge yet
- vaults: watching, 48.9 days of history, no consistent edge yet
- cextop: watching, 48.9 days of history, no consistent edge yet
- funding: live, 48.9 days of history, no consistent edge yet

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.24 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=16 hit 25.0% avg -1.89%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.33 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=110 hit 23.6% avg -2.88%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=15 hit 26.7% avg -2.94%

## Changes applied
- major.weights.momentum 0.93->1.17 (daily IC +0.18)
- alt.weights.momentum 0.15->0.18 (daily IC +0.18)
- meme.weights.momentum 0.64->0.80 (daily IC +0.18)
- major.weights.news 0.20->0.15 (daily IC -0.18)
- alt.weights.news 0.21->0.15 (daily IC -0.18)
- meme.weights.news 0.36->0.27 (daily IC -0.18)
