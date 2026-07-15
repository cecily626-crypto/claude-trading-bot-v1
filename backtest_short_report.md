# v2.0-Short 策略回测报告
_2026-07-15T04:49:15.261311Z · LBank hour4 · 2000 bars_
```
数据: memecoin 34 个 + trend 2 个, 窗口 2026-01-31->2026-07-15
大盘闸门: BTC 空头占比 44% of window

== S1 破位趋势做空 (memecoins) · FULL | H1 | H2 ==
S1b bo55 现行(confirm off)           n= 402  win= 44.0%  PF= 1.88  tot=  +974.9%  avg= +2.43%  hold= 11 | H1 PF= 3.17 tot=+1155.6% | H2 PF= 0.69 tot= -180.7%
S1b+回踩确认 (opt#2)                   n= 392  win= 40.3%  PF= 0.95  tot=   -55.2%  avg= -0.14%  hold= 12 | H1 PF= 1.18 tot= +113.2% | H2 PF= 0.68 tot= -168.4%
S1b+回踩+大盘闸门 (opt#2+#1)             n= 356  win= 40.7%  PF= 0.77  tot=  -259.8%  avg= -0.73%  hold= 11 | H1 PF= 0.84 tot= -103.0% | H2 PF= 0.67 tot= -156.8%
S1a bo20 (confirm off)             n= 628  win= 37.4%  PF= 1.19  tot=  +381.1%  avg= +0.61%  hold= 10 | H1 PF= 1.91 tot= +896.2% | H2 PF= 0.51 tot= -515.1%
S1b bo55 无仅止损 (confirm off)        n= 408  win= 43.4%  PF= 1.82  tot=  +930.1%  avg= +2.28%  hold= 11 | H1 PF= 2.96 tot=+1105.4% | H2 PF= 0.69 tot= -175.2%
S1c reg200/gap5 (confirm off)      n= 359  win= 37.6%  PF= 1.25  tot=  +306.7%  avg= +0.85%  hold= 12 | H1 PF= 1.69 tot= +487.5% | H2 PF= 0.65 tot= -180.7%

== S2 泡沫反转做空 (memecoins) · FULL | H1 | H2 ==
S2a surge40/rsi85/vol3/ext3 tp15/h6 n=   3  win=  0.0%  PF= 0.00  tot=   -20.1%  avg= -6.71%  hold=  0 | H1 PF= 0.00 tot=   -7.8% | H2 PF= 0.00 tot=  -12.3%
S2b surge25/rsi80/vol2/ext2 tp15/h6 n=  21  win= 23.8%  PF= 0.85  tot=   -16.0%  avg= -0.76%  hold=  0 | H1 PF= 1.60 tot=  +13.2% | H2 PF= 0.64 tot=  -29.2%
S2c =a, tp10/hold12                n=   3  win=  0.0%  PF= 0.00  tot=   -20.1%  avg= -6.71%  hold=  0 | H1 PF= 0.00 tot=   -7.8% | H2 PF= 0.00 tot=  -12.3%
S2d =b, tp10/hold12                n=  21  win= 33.3%  PF= 0.85  tot=   -13.5%  avg= -0.64%  hold=  0 | H1 PF= 1.01 tot=   +0.1% | H2 PF= 0.80 tot=  -13.6%

== TS 趋势做空 (BTC/ETH) ==
TS btc/eth                         n=  91  win= 19.8%  PF= 1.34  tot=   +37.5%  avg= +0.41%  hold=  3 | H1 PF= 0.70 | H2 PF= 2.81

== 优胜者 (按 min(H1,H2) PF): S1 -> S1b bo55 无仅止损 (confirm off) · S2 -> S2d =b, tp10/hold12 ==

-- S1b bo55 无仅止损 (confirm off) · 明细 --
  Q1                               n= 109  win= 56.0%  PF= 4.92  tot= +1052.1%  avg= +9.65%  hold=  9
  Q2                               n= 100  win= 46.0%  PF= 1.18  tot=   +53.3%  avg= +0.53%  hold= 10
  Q3                               n=  84  win= 27.4%  PF= 0.73  tot=   -68.6%  avg= -0.82%  hold=  9
  Q4                               n= 115  win= 40.9%  PF= 0.66  tot=  -106.6%  avg= -0.93%  hold= 12
  exit=flip/regime                 n=  11  win=  0.0%  PF= 0.00  tot=   -65.6%  avg= -5.97%  hold=  2
  exit=trail_stop                  n= 397  win= 44.6%  PF= 1.93  tot=  +995.8%  avg= +2.51%  hold= 11
  best mog                         n=  15  win= 46.7%  PF= 3.92  tot=   +85.6%  avg= +5.70%  hold= 11
  best baby                        n=  13  win= 53.8%  PF= 6.10  tot=   +81.4%  avg= +6.26%  hold= 15
  best pepe                        n=   8  win= 75.0%  PF=35.32  tot=   +74.4%  avg= +9.30%  hold= 26
  best brett                       n=  10  win= 70.0%  PF=13.37  tot=   +72.7%  avg= +7.27%  hold= 16
  best pengu                       n=  12  win= 66.7%  PF= 4.65  tot=   +69.5%  avg= +5.79%  hold= 11
  worst mubarak                    n=  12  win= 25.0%  PF= 0.60  tot=   -21.1%  avg= -1.76%  hold=  7
  worst ban                        n=  12  win= 16.7%  PF= 0.56  tot=   -24.1%  avg= -2.01%  hold=  5
  worst labubu                     n=  14  win= 28.6%  PF= 0.45  tot=   -31.4%  avg= -2.24%  hold= 11
  最大亏损 gork       ret= -18.3% hold=  2 why=trail_stop
  最大亏损 labubu     ret= -17.6% hold=  3 why=trail_stop
  最大亏损 troll      ret= -16.9% hold=  5 why=trail_stop
  最大亏损 useless    ret= -15.2% hold=  4 why=trail_stop
  最大亏损 gork       ret= -14.8% hold=  9 why=trail_stop

-- S2d =b, tp10/hold12 · 明细 --
  Q1                               n=   1  win=  0.0%  PF= 0.00  tot=    -7.8%  avg= -7.80%  hold=  0
  Q2                               n=   4  win= 50.0%  PF= 1.56  tot=    +7.9%  avg= +1.98%  hold=  0
  Q3                               n=   6  win= 16.7%  PF= 0.41  tot=   -15.6%  avg= -2.60%  hold=  0
  Q4                               n=  10  win= 40.0%  PF= 1.05  tot=    +2.0%  avg= +0.20%  hold=  0
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
S3 组合                              n= 520  win= 38.8%  PF= 1.72  tot=  +954.1%  avg= +1.83%  hold=  8 | H1 PF= 2.63 tot=+1082.0% | H2 PF= 0.81 tot= -127.8%
```
