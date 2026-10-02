# Whale Desk backtest  2026-10-02 17:19Z

20 refresh snapshots over 25.0 days; 648 coin-days in the daily panel.

## Which factors predicted forward returns (rank correlation; +0.10 is a usable edge, below 0.05 is noise)

Daily panel (whale from trades.csv, momentum from prices, news where covered):
- momentum: 1d -0.02 (n=630), 3d -0.05 (n=594), 5d -0.10 (n=558)
- news: 1d -0.07 (n=522), 3d -0.25 (n=486), 5d -0.47 (n=450)
- whale: 1d +0.03 (n=252), 3d -0.02 (n=232), 5d +0.00 (n=212)

Refresh snapshots (all six factors + the combined score, short history):
- whale: 1d n/a (n=217), 3d n/a (n=163), 5d n/a (n=19)
- smart: 1d -0.01 (n=217), 3d -0.11 (n=163), 5d +0.16 (n=19)
- news: 1d +0.13 (n=217), 3d -0.10 (n=163), 5d -0.17 (n=19)
- sentiment: 1d -0.25 (n=217), 3d -0.33 (n=163), 5d -0.09 (n=19)
- momentum: 1d -0.31 (n=217), 3d -0.22 (n=163), 5d -0.56 (n=19)
- liquidity: 1d +0.20 (n=217), 3d +0.16 (n=163), 5d +0.43 (n=19)
- score: 1d -0.19 (n=217), 3d -0.33 (n=163), 5d -0.31 (n=19)

## Entry / exit settings by category (daily simulation on whale + momentum + news only; informational, not applied)

### major  (BTC, ETH)
- current settings: thr 0.3 gate 0.15 target 5.0 stop 4.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=13 hit 53.8% avg 0.37%

### alt  (AAVE, ARB, BTW, ENA, ICP, LINK, LIT, MNT, MORPHO, ONDO, SKY, UNI, WLD, WLFI)
- current settings: thr 0.35 gate 0.15 target 8.0 stop 6.0 days 7 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=112 hit 55.4% avg 1.74%
- grid: thr 0.2 gate 0.0 target 15 stop 3 days 3 -> n=24 hit 45.8% avg +2.22% exits {'target': 4, 'stop': 12, 'time': 8}
- grid: thr 0.2 gate 0.0 target 10 stop 3 days 5 -> n=24 hit 50.0% avg +2.10% exits {'target': 6, 'stop': 12, 'time': 6}
- grid: thr 0.2 gate 0.0 target 15 stop 3 days 7 -> n=20 hit 40.0% avg +2.17% exits {'target': 5, 'stop': 12, 'time': 3}

### meme  (PEPE, SHIB)
- current settings: thr 0.4 gate 0.2 target 15.0 stop 10.0 days 5 -> n=0 hit None% avg None% exits None
- buy everything, same exits: n=14 hit 57.1% avg 0.14%

## Changes applied
- major.weights.news 0.40->0.30 (daily IC -0.25)
- alt.weights.news 0.61->0.46 (daily IC -0.25)
- meme.weights.news 0.90->0.68 (daily IC -0.25)
- major.weights.sentiment 0.30->0.24 (snapshot IC -0.25)
- alt.weights.sentiment 0.59->0.47 (snapshot IC -0.25)
- meme.weights.sentiment 0.20->0.16 (snapshot IC -0.25)
- major.weights.liquidity 0.10->0.12 (snapshot IC +0.16)
- alt.weights.liquidity 0.45->0.55 (snapshot IC +0.16)
- meme.weights.liquidity 0.60->0.72 (snapshot IC +0.16)
- major.weights.momentum 0.90->0.72 (snapshot IC -0.22)
- alt.weights.momentum 0.78->0.63 (snapshot IC -0.22)
- meme.weights.momentum 1.00->0.80 (snapshot IC -0.22)
