# v2.0-Short 策略回测报告
_2026-07-07T05:28:44.739359Z · LBank hour4 · 2000 bars_
```
数据: memecoin 34 个 + trend 2 个, 窗口 2026-01-31->2026-07-07

== S1 破位趋势做空 (memecoins) · FULL | H1 | H2 ==
S1a bo20/reg100/gap3/stop2.5       n= 611  win= 37.3%  PF= 1.16  tot=  +325.4%  avg= +0.53%  hold= 10 | H1 PF= 1.71 tot= +753.3% | H2 PF= 0.58 tot= -427.9%
S1b bo55                           n= 405  win= 43.2%  PF= 1.82  tot=  +926.5%  avg= +2.29%  hold= 11 | H1 PF= 2.64 tot= +989.1% | H2 PF= 0.88 tot=  -62.6%
S1c reg200/gap5                    n= 347  win= 38.3%  PF= 1.26  tot=  +315.8%  avg= +0.91%  hold= 12 | H1 PF= 1.66 tot= +467.2% | H2 PF= 0.71 tot= -151.4%
S1d stop2.0                        n= 611  win= 34.4%  PF= 1.04  tot=   +68.9%  avg= +0.11%  hold=  7 | H1 PF= 1.47 tot= +467.5% | H2 PF= 0.53 tot= -398.7%
S1e stop3.0                        n= 611  win= 38.8%  PF= 1.29  tot=  +643.2%  avg= +1.05%  hold= 15 | H1 PF= 1.85 tot= +941.8% | H2 PF= 0.74 tot= -298.6%
S1f 无过滤器                           n= 623  win= 38.2%  PF= 1.17  tot=  +365.2%  avg= +0.59%  hold= 10 | H1 PF= 1.75 tot= +817.4% | H2 PF= 0.55 tot= -452.1%
S1a+仅止损出场                          n= 594  win= 38.9%  PF= 1.18  tot=  +369.8%  avg= +0.62%  hold= 12 | H1 PF= 1.73 tot= +775.8% | H2 PF= 0.60 tot= -406.0%
S1b+仅止损出场                          n= 400  win= 43.8%  PF= 1.87  tot=  +964.5%  avg= +2.41%  hold= 11 | H1 PF= 2.78 tot=+1026.9% | H2 PF= 0.88 tot=  -62.4%
S1c+仅止损出场                          n= 343  win= 39.1%  PF= 1.27  tot=  +334.7%  avg= +0.98%  hold= 12 | H1 PF= 1.74 tot= +501.9% | H2 PF= 0.69 tot= -167.2%

== S2 泡沫反转做空 (memecoins) · FULL | H1 | H2 ==
S2a surge40/rsi85/vol3/ext3 tp15/h6 n=   3  win=  0.0%  PF= 0.00  tot=   -20.1%  avg= -6.71%  hold=  0 | H1 PF= 0.00 tot=   -7.8% | H2 PF= 0.00 tot=  -12.3%
S2b surge25/rsi80/vol2/ext2 tp15/h6 n=  21  win= 23.8%  PF= 0.85  tot=   -16.0%  avg= -0.76%  hold=  0 | H1 PF= 1.60 tot=  +13.2% | H2 PF= 0.64 tot=  -29.2%
S2c =a, tp10/hold12                n=   3  win=  0.0%  PF= 0.00  tot=   -20.1%  avg= -6.71%  hold=  0 | H1 PF= 0.00 tot=   -7.8% | H2 PF= 0.00 tot=  -12.3%
S2d =b, tp10/hold12                n=  21  win= 33.3%  PF= 0.85  tot=   -13.5%  avg= -0.64%  hold=  0 | H1 PF= 1.01 tot=   +0.1% | H2 PF= 0.80 tot=  -13.6%

== TS 趋势做空 (BTC/ETH) ==
TS btc/eth                         n=  84  win= 21.4%  PF= 1.49  tot=   +49.0%  avg= +0.58%  hold=  4 | H1 PF= 0.80 | H2 PF= 2.77

== 优胜者 (按 min(H1,H2) PF): S1 -> S1b+仅止损出场 · S2 -> S2d =b, tp10/hold12 ==

-- S1b+仅止损出场 · 明细 --
  Q1                               n= 108  win= 51.9%  PF= 4.89  tot= +1000.9%  avg= +9.27%  hold= 11
  Q2                               n= 102  win= 45.1%  PF= 1.08  tot=   +26.1%  avg= +0.26%  hold= 11
  Q3                               n=  93  win= 31.2%  PF= 1.03  tot=    +7.9%  avg= +0.08%  hold=  9
  Q4                               n=  97  win= 45.4%  PF= 0.74  tot=   -70.3%  avg= -0.73%  hold= 13
  exit=trail_stop                  n= 400  win= 43.8%  PF= 1.87  tot=  +964.5%  avg= +2.41%  hold= 11
  best mog                         n=  13  win= 53.8%  PF= 5.31  tot=   +89.8%  avg= +6.91%  hold= 22
  best baby                        n=  12  win= 66.7%  PF= 6.56  tot=   +85.5%  avg= +7.13%  hold= 15
  best brett                       n=  10  win= 70.0%  PF=16.57  tot=   +73.8%  avg= +7.38%  hold= 18
  best pepe                        n=   9  win= 66.7%  PF=15.57  tot=   +71.6%  avg= +7.96%  hold= 25
  best giga                        n=  12  win= 75.0%  PF= 3.97  tot=   +63.1%  avg= +5.26%  hold= 13
  worst ban                        n=  11  win= 18.2%  PF= 0.60  tot=   -20.7%  avg= -1.88%  hold=  7
  worst mubarak                    n=  13  win= 23.1%  PF= 0.55  tot=   -26.4%  avg= -2.03%  hold=  5
  worst labubu                     n=  13  win= 30.8%  PF= 0.46  tot=   -30.4%  avg= -2.34%  hold= 10
  最大亏损 gork       ret= -18.3% hold=  2 why=trail_stop
  最大亏损 labubu     ret= -17.6% hold=  3 why=trail_stop
  最大亏损 troll      ret= -16.9% hold=  5 why=trail_stop
  最大亏损 useless    ret= -15.2% hold=  4 why=trail_stop
  最大亏损 gork       ret= -14.8% hold=  9 why=trail_stop

-- S2d =b, tp10/hold12 · 明细 --
  Q1                               n=   0  win=  nan%  PF=  nan  tot=    +0.0%  avg= +0.00%  hold=  0
  Q2                               n=   5  win= 40.0%  PF= 1.01  tot=    +0.1%  avg= +0.02%  hold=  0
  Q3                               n=   4  win=  0.0%  PF= 0.00  tot=   -19.9%  avg= -4.98%  hold=  0
  Q4                               n=  12  win= 41.7%  PF= 1.13  tot=    +6.3%  avg= +0.52%  hold=  0
  exit=stop                        n=  14  win=  0.0%  PF= 0.00  tot=   -90.3%  avg= -6.45%  hold=  0
  exit=tp                          n=   7  win=100.0%  PF=99.00  tot=   +76.8%  avg=+10.97%  hold=  0
  best pnut                        n=   1  win=100.0%  PF=99.00  tot=   +11.0%  avg=+10.97%  hold=  0
  best turbo                       n=   2  win= 50.0%  PF= 2.90  tot=    +7.2%  avg= +3.59%  hold=  0
  best baby                        n=   2  win= 50.0%  PF= 2.19  tot=    +6.0%  avg= +2.98%  hold=  0
  best gork                        n=   2  win= 50.0%  PF= 1.51  tot=    +3.7%  avg= +1.86%  hold=  0
  best hippo                       n=   2  win= 50.0%  PF= 1.41  tot=    +3.2%  avg= +1.58%  hold=  0
  worst giga                       n=   1  win=  0.0%  PF= 0.00  tot=    -7.6%  avg= -7.62%  hold=  1
  worst moodeng                    n=   1  win=  0.0%  PF= 0.00  tot=   -10.2%  avg=-10.25%  hold=  0
  worst dogs                       n=   3  win=  0.0%  PF= 0.00  tot=   -18.0%  avg= -5.99%  hold=  0
  最大亏损 moodeng    ret= -10.2% hold=  0 why=stop
  最大亏损 dogs       ret=  -9.2% hold=  0 why=stop
  最大亏损 troll      ret=  -8.0% hold=  0 why=stop
  最大亏损 hippo      ret=  -7.8% hold=  0 why=stop
  最大亏损 giga       ret=  -7.6% hold=  1 why=stop

== S3 组合 (best-S1 + best-S2 + TS) ==
S3 组合                              n= 505  win= 39.6%  PF= 1.77  tot= +1000.0%  avg= +1.98%  hold= 10 | H1 PF= 2.53 tot=+1014.2% | H2 PF= 0.98 tot=  -14.2%
```
