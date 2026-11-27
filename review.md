# Whale Desk review  2026-11-27 23:48Z

Open calls: 1   Closed: 23

## Health
- OK last refresh 0.0h ago
- OK Hyperliquid top-trader data read 0.0h ago
- OK second opinion 'lighter' read 0.0h ago, 40 coins
- OK second opinion 'vaults' read 0.0h ago, 40 coins
- OK second opinion 'cextop' read 0.0h ago, 18 coins
- OK second opinion 'funding' read 0.0h ago, 18 coins
- NOTE no BUY calls on the board: thresholds may have drifted too high
- NOTE 6 of 23 closed calls were opened before 5 Oct on a frozen Hyperliquid feed: listed below, left out of tuning

## By category
- **alt** n=13 (9 on the live feed) hit 38.5% avg -1.30% (median -6.00%) exits {'stop': 8, 'target': 5} peak +4.5% trough -7.2% | target 8.0 stop 6.0 days 7 bar 0.33
- **major** n=10 (8 on the live feed) hit 60.0% avg +1.20% (median +3.27%) exits {'time': 2, 'stop': 3, 'target': 5} peak +3.9% trough -1.9% | target 5.0 stop 4.0 days 7 bar 0.22

## By entry gate
- smart: n=9 hit 33.3% avg -1.72%
- whale: n=14 hit 57.1% avg +0.75%

## Factor edge (mean in wins - mean in losses)
- vaults: +0.28 (wins +0.05, losses -0.23)
- momentum: +0.24 (wins -0.53, losses -0.77)
- news: +0.15 (wins +0.33, losses +0.18)
- funding: +0.06 (wins +0.18, losses +0.12)
- cextop: +0.05 (wins +0.01, losses -0.04)
- lighter: +0.04 (wins -0.13, losses -0.17)
- liquidity: +0.02 (wins +0.12, losses +0.10)
- smart: -0.06 (wins -0.48, losses -0.42)
- whale: -0.07 (wins -0.20, losses -0.13)
- sentiment: -0.18 (wins -0.72, losses -0.53)

## Suggestions
- alt.stop_pct: 6.0 -> 7.5  (5/9 stopped out although avg peak was +4.5%)
- *.weights.sentiment: None -> x0.7  (sentiment averaged -0.53 in losses vs -0.72 in wins: it is a contrary signal here)

## Applied this run
- alt.stop_pct 6.0->7.5
- major.weights.sentiment 0.50->0.35
- alt.weights.sentiment 0.33->0.23
- meme.weights.sentiment 0.13->0.10
