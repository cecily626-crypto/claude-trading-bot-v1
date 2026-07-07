"""
v2.0-Short: dedicated SHORT-ONLY strategies, built on the v1 indicator stack.

Candidates (to be compared by backtest_short.py before any goes live):
  S1 breakdown_short : trend-following breakdown short — mirror of the v1
                       breakout long, with mirrored anti-chase filters.
  S2 blowoff fade    : mean-reversion short on exhaustion pumps
                       (strategy_core.blowoff_short, never traded live in v1).
  trend_short        : BTC/ETH short leg of the v1 trend strategy.
"""
import numpy as np
import pandas as pd

from strategy_core import ema, rsi, atr, donchian_low, trend_ls, blowoff_short  # noqa: F401


def breakdown_short(df, breakout=20, regime=100, atr_period=14, stop_mult=2.5,
                    mom=20, gap=0.03, use_filters=True, rsi_min=25.0,
                    crash_max=0.25, ext_atr=1.5):
    """Short on a new-low breakdown in a CONFIRMED downtrend
    (price >= `gap` below EMA(regime), momentum negative).

    Anti-chase filters (mirror of the v1 long-side blow-off filters):
      F1 skip if the bar already crashed > crash_max open->close (vertical dump,
         bounce risk after we fill at next open)
      F2 skip if price is extended > ext_atr * ATR below the breakdown line
      F3 skip if RSI(14) < rsi_min (capitulation lows tend to mean-revert)

    Exit to flat when price recovers above EMA(regime). ATR trailing stop is
    applied by the execution engine (same state machine as v1).
    """
    c = df["close"]
    er = ema(c, regime)
    a = atr(df, atr_period)
    dl = donchian_low(df["low"], breakout)
    m = c.pct_change(mom)
    r = rsi(c, 14)
    crash = 1 - c / df["open"]          # positive when the bar dumps
    ext = (dl - c) / a                  # distance below the breakdown line
    short_ok = (c < dl) & (c < er * (1 - gap)) & (m < 0)
    if use_filters:
        short_ok = short_ok & (r > rsi_min) & (crash < crash_max) & (ext < ext_atr)
    raw = pd.Series(np.where(short_ok, -1, np.nan), index=c.index)
    raw[(c > er) & raw.isna() & (raw.ffill() == -1)] = 0    # recovered -> flat
    target = raw.ffill().fillna(0).to_numpy()
    return {"target": target.astype(int), "atr": a.to_numpy(), "stop_mult": stop_mult,
            "atr_pct": (a / c).to_numpy(), "aux": {"ema_regime": er}}


def trend_short(df, fast=20, slow=50, regime=100, atr_period=14, stop_mult=3.0, gap=0.03):
    """BTC/ETH: the short leg of the v1 trend strategy only (longs dropped)."""
    sig = trend_ls(df, fast=fast, slow=slow, regime=regime, atr_period=atr_period,
                   stop_mult=stop_mult, short_gap=gap)
    sig["target"] = np.where(np.asarray(sig["target"]) < 0, -1, 0).astype(int)
    return sig
