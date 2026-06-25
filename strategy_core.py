"""
Self-contained strategy logic for the live bot (no historical-data dependencies).
Indicators + the confirmed long/short TREND and BREAKOUT strategies, identical to
the backtested versions.
"""
import numpy as np
import pandas as pd


# ------------------------------- indicators ---------------------------------
def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def rsi(s, period=14):
    d = s.diff()
    up = d.clip(lower=0.0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-d.clip(upper=0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def donchian_high(s, n):
    return s.rolling(n).max().shift(1)


def donchian_low(s, n):
    return s.rolling(n).min().shift(1)


# --------------------------- long/short strategies --------------------------
def trend_ls(df, fast=20, slow=50, regime=100, atr_period=14, stop_mult=3.0, short_gap=0.03):
    """BTC/ETH: symmetric trend, but short only on a CONFIRMED downtrend
    (EMAs stacked bearish AND price >= short_gap below EMA(regime))."""
    c = df["close"]
    ef, es, er = ema(c, fast), ema(c, slow), ema(c, regime)
    a = atr(df, atr_period)
    long_ok = (ef > es) & (es > er) & (c > er)
    short_ok = (ef < es) & (es < er) & (c < er * (1 - short_gap))
    target = np.where(long_ok, 1, np.where(short_ok, -1, 0))
    return {"target": target.astype(int), "atr": a.to_numpy(), "stop_mult": stop_mult,
            "atr_pct": (a / c).to_numpy(), "aux": {"ema_regime": er}}


def breakout_ls(df, breakout=20, regime=100, atr_period=14, stop_mult=2.5, mom=20, short_gap=0.03):
    """Memecoins: long on new-high breakout in up-regime; short on new-low
    breakdown in a CONFIRMED downtrend (price >= short_gap below EMA(regime))."""
    c = df["close"]
    er = ema(c, regime)
    a = atr(df, atr_period)
    dh, dl = donchian_high(df["high"], breakout), donchian_low(df["low"], breakout)
    m = c.pct_change(mom)
    long_ok = (c > dh) & (c > er) & (m > 0)
    short_ok = (c < dl) & (c < er * (1 - short_gap)) & (m < 0)
    raw = pd.Series(np.where(long_ok, 1, np.where(short_ok, -1, np.nan)), index=c.index)
    raw[(c < er) & raw.isna() & (raw.ffill() == 1)] = 0
    raw[(c > er) & raw.isna() & (raw.ffill() == -1)] = 0
    target = raw.ffill().fillna(0).to_numpy()
    return {"target": target.astype(int), "atr": a.to_numpy(), "stop_mult": stop_mult,
            "atr_pct": (a / c).to_numpy(), "aux": {"ema_regime": er}}
