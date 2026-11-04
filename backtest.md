# Whale Desk backtest  2026-11-04 18:57Z

170 refresh snapshots over 57.7 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d +0.22 (n=630), 3d +0.03 (n=594), 5d -0.04 (n=558)
- news: 1d -0.02 (n=486), 3d -0.11 (n=450), 5d -0.13 (n=414)
- whale: 1d -0.04 (n=432), 3d -0.09 (n=404), 5d -0.15 (n=378)

Refresh snapshots (every factor + the combined score, short history):
- whale: 1d -0.04 (n=2950), 3d -0.07 (n=2860), 5d -0.11 (n=2721)
- smart: 1d -0.10 (n=2950), 3d -0.13 (n=2860), 5d -0.10 (n=2721)
- news: 1d +0.05 (n=2950), 3d +0.13 (n=2860), 5d +0.20 (n=2721)
- sentiment: 1d -0.03 (n=2950), 3d -0.03 (n=2860), 5d -0.00 (n=2721)
- momentum: 1d -0.19 (n=2950), 3d -0.21 (n=2860), 5d -0.17 (n=2721)
- liquidity: 1d +0.02 (n=2950), 3d +0.00 (n=2860), 5d +0.00 (n=2721)
- score: 1d -0.13 (n=2950), 3d -0.12 (n=2860), 5d -0.05 (n=2721)
- lighter: 1d -0.14 (n=897), 3d -0.25 (n=853), 5d -0.06 (n=793)
- vaults: 1d -0.01 (n=755), 3d +0.01 (n=707), 5d +0.11 (n=662)
- cextop: 1d -0.04 (n=2337), 3d -0.02 (n=2229), 5d +0.04 (n=2090)
- funding: 1d +0.06 (n=2259), 3d +0.13 (n=2151), 5d +0.10 (n=2012)

## Second opinions (Lighter top traders, Hyperliquid vaults, exchange top traders, funding)

Recorded every refresh with no weight. One is promoted into the score after 14+ days of history with a consistent rank correlation of +0.10 or better.
- lighter: watching, 28.9 days of history, consistent IC -0.06
- vaults: watching, 28.9 days of history, no consistent edge yet
- cextop: watching, 28.9 days of history, no consistent edge yet
- funding: live, 28.9 days of history, consistent IC +0.06

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=10 hit 30.0% avg -0.44%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=109 hit 33.9% avg -1.44%

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=13 hit 53.8% avg 0.32%

## Changes applied
- major.weights.whale 0.21->0.16 (daily IC -0.09)
- alt.weights.whale 0.60->0.45 (daily IC -0.09)
- meme.weights.whale 0.51->0.38 (daily IC -0.09)
- major.weights.news 0.12->0.10 (daily IC -0.11)
- alt.weights.news 0.18->0.13 (daily IC -0.11)
- meme.weights.news 0.47->0.36 (daily IC -0.11)
- major.weights.smart 0.60->0.48 (snapshot IC -0.10)
- alt.weights.smart 0.37->0.29 (snapshot IC -0.10)
- meme.weights.smart 0.51->0.41 (snapshot IC -0.10)
- major.weights.momentum 0.72->0.58 (snapshot IC -0.19)
- alt.weights.momentum 0.30->0.24 (snapshot IC -0.19)
- meme.weights.momentum 0.80->0.64 (snapshot IC -0.19)
- major.weights.funding 0.36->0.43 (snapshot IC +0.06)
- alt.weights.funding 0.32->0.39 (snapshot IC +0.06)
- meme.weights.funding 0.36->0.43 (snapshot IC +0.06)
