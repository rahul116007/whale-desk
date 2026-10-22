# Whale Desk backtest  2026-10-22 14:07Z

116 refresh snapshots over 44.7 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.19 (n=630), 3d +0.14 (n=594), 5d +0.21 (n=558)
- news: 1d +0.04 (n=450), 3d +0.06 (n=414), 5d +0.05 (n=378)
- whale: 1d +0.00 (n=380), 3d -0.11 (n=354), 5d -0.21 (n=328)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.01 (n=1937), 3d -0.06 (n=1793), 5d -0.12 (n=1559)
- smart: 1d -0.18 (n=1937), 3d -0.23 (n=1793), 5d -0.10 (n=1559)
- news: 1d +0.02 (n=1937), 3d +0.13 (n=1793), 5d +0.20 (n=1559)
- sentiment: 1d -0.04 (n=1937), 3d -0.05 (n=1793), 5d -0.09 (n=1559)
- momentum: 1d -0.23 (n=1937), 3d -0.25 (n=1793), 5d -0.13 (n=1559)
- liquidity: 1d -0.01 (n=1937), 3d -0.07 (n=1793), 5d -0.10 (n=1559)
- score: 1d -0.20 (n=1937), 3d -0.21 (n=1793), 5d -0.11 (n=1559)
- lighter: 1d -0.34 (n=467), 3d -0.65 (n=400), 5d -0.31 (n=312)
- vaults: 1d -0.20 (n=423), 3d -0.12 (n=369), 5d +0.05 (n=306)
- cextop: 1d -0.01 (n=1324), 3d +0.07 (n=1162), 5d +0.10 (n=928)
- funding: 1d +0.12 (n=1250), 3d +0.25 (n=1097), 5d +0.13 (n=876)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 15.8 days of history, consistent IC -0.31
- vaults: watching, 15.8 days of history, no consistent edge yet
- cextop: watching, 15.8 days of history, no consistent edge yet
- funding: promoted, 15.8 days of history, consistent IC +0.12

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=12 hit 41.7% avg 0.39%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=116 hit 54.3% avg 1.51%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=14 hit 50.0% avg 0.74%

## Changes applied
- major.weights.whale 0.38->0.28 (daily IC -0.11)
- alt.weights.whale 0.72->0.54 (daily IC -0.11)
- meme.weights.whale 0.90->0.68 (daily IC -0.11)
- major.weights.momentum 0.72->0.90 (daily IC +0.14)
- alt.weights.momentum 0.26->0.33 (daily IC +0.14)
- meme.weights.momentum 0.80->1.00 (daily IC +0.14)
- major.weights.news 0.10->0.12 (daily IC +0.05)
- alt.weights.news 0.15->0.19 (daily IC +0.05)
- meme.weights.news 0.38->0.47 (daily IC +0.05)
- major.weights.smart 0.94->0.76 (snapshot IC -0.18)
- alt.weights.smart 0.56->0.45 (snapshot IC -0.18)
- meme.weights.smart 0.80->0.64 (snapshot IC -0.18)
- *.weights.funding promoted from watch-only to 0.30 (16 days of history, snapshot IC +0.12)
