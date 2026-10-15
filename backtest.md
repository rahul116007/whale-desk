# Whale Desk backtest  2026-10-15 22:34Z

81 refresh snapshots over 38.4 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.16 (n=630), 3d +0.14 (n=594), 5d +0.09 (n=558)
- news: 1d -0.15 (n=450), 3d -0.22 (n=414), 5d -0.33 (n=378)
- whale: 1d +0.01 (n=352), 3d -0.07 (n=326), 5d -0.11 (n=302)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d +0.02 (n=1294), 3d -0.05 (n=1168), 5d -0.07 (n=1006)
- smart: 1d -0.07 (n=1294), 3d -0.12 (n=1168), 5d -0.03 (n=1006)
- news: 1d +0.01 (n=1294), 3d +0.16 (n=1168), 5d +0.19 (n=1006)
- sentiment: 1d -0.06 (n=1294), 3d -0.12 (n=1168), 5d -0.12 (n=1006)
- momentum: 1d -0.13 (n=1294), 3d -0.14 (n=1168), 5d -0.14 (n=1006)
- liquidity: 1d -0.00 (n=1294), 3d -0.03 (n=1168), 5d -0.10 (n=1006)
- score: 1d -0.13 (n=1294), 3d -0.09 (n=1168), 5d -0.08 (n=1006)
- lighter: 1d -0.29 (n=242), 3d -0.69 (n=204), 5d -0.27 (n=145)
- vaults: 1d -0.01 (n=235), 3d -0.03 (n=189), 5d -0.12 (n=123)
- cextop: 1d +0.00 (n=681), 3d +0.03 (n=537), 5d -0.04 (n=375)
- funding: 1d +0.18 (n=643), 3d +0.34 (n=507), 5d +0.37 (n=354)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 9.5 days of history, no consistent edge yet
- vaults: watching, 9.5 days of history, no consistent edge yet
- cextop: watching, 9.5 days of history, no consistent edge yet
- funding: watching, 9.5 days of history, consistent IC +0.18

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=12 hit 33.3% avg 0.05%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=112 hit 56.2% avg 1.59%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=14 hit 35.7% avg 0.47%

## Changes applied
- major.weights.whale 0.50->0.38 (daily IC -0.07)
- alt.weights.whale 0.96->0.72 (daily IC -0.07)
- meme.weights.whale 1.20->0.90 (daily IC -0.07)
- major.weights.momentum 0.58->0.72 (daily IC +0.09)
- alt.weights.momentum 0.21->0.26 (daily IC +0.09)
- meme.weights.momentum 0.64->0.80 (daily IC +0.09)
- major.weights.news 0.10->0.10 (daily IC -0.22)
- alt.weights.news 0.20->0.15 (daily IC -0.22)
- meme.weights.news 0.51->0.38 (daily IC -0.22)
- major.weights.smart 1.13->0.91 (snapshot IC -0.07)
- alt.weights.smart 0.70->0.56 (snapshot IC -0.07)
- meme.weights.smart 1.00->0.80 (snapshot IC -0.07)
- major.weights.sentiment 0.12->0.10 (snapshot IC -0.06)
- alt.weights.sentiment 0.15->0.12 (snapshot IC -0.06)
- meme.weights.sentiment 0.16->0.13 (snapshot IC -0.06)
