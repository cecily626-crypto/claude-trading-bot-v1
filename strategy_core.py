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


def breakout_ls(df, breakout=20, regime=100, atr_period=14, stop_mult=2.5, mom=20, short_gap=0.03,
                use_filters=True, rsi_max=75.0, surge_max=0.25, ext_atr=1.5, vol_mult=1.2):
    """Memecoins: long on new-high breakout in up-regime; short on new-low
    breakdown in a CONFIRMED downtrend (price >= short_gap below EMA(regime)).

    PATCH (anti-chase, default ON): a breakout LONG is skipped if it is just a
    blow-off spike — any of:
      F1 single-bar surge (close/open-1) > surge_max   (vertical pump)
      F2 price extended > ext_atr * ATR above the breakout line   (chased too far)
      F3 RSI(14) > rsi_max at the breakout   (overbought / late)

    PATCH 2 (2026-07-05, week-1 paper review): volume confirmation, default ON —
      F4 the breakout/breakdown bar must print volume > vol_mult * 20-bar average
         volume. Low-volume breakouts (the USELESS -9.9%/-9.1% and GORK -12.0%
         week-1 whipsaws) are skipped. Applies to BOTH longs and shorts.
    """
    c = df["close"]
    er = ema(c, regime)
    a = atr(df, atr_period)
    dh, dl = donchian_high(df["high"], breakout), donchian_low(df["low"], breakout)
    m = c.pct_change(mom)
    r = rsi(c, 14)
    surge = c / df["open"] - 1
    ext = (c - dh) / a
    vol_ok = df["volume"] > vol_mult * df["volume"].rolling(20).mean()
    long_ok = (c > dh) & (c > er) & (m > 0)
    short_ok = (c < dl) & (c < er * (1 - short_gap)) & (m < 0)
    if use_filters:
        long_ok = long_ok & (r < rsi_max) & (surge < surge_max) & (ext < ext_atr) & vol_ok
        short_ok = short_ok & vol_ok
    raw = pd.Series(np.where(long_ok, 1, np.where(short_ok, -1, np.nan)), index=c.index)
    raw[(c < er) & raw.isna() & (raw.ffill() == 1)] = 0
    raw[(c > er) & raw.isna() & (raw.ffill() == -1)] = 0
    target = raw.ffill().fillna(0).to_numpy()
    return {"target": target.astype(int), "atr": a.to_numpy(), "stop_mult": stop_mult,
            "atr_pct": (a / c).to_numpy(), "aux": {"ema_regime": er}}


def blowoff_short(df, surge=0.40, rsi_min=85.0, vol_mult=3.0, ext_atr=3.0,
                  atr_period=14, tp=0.15, stop_atr=1.0, max_hold=6):
    """EXPERIMENTAL mean-reversion SHORT that fades an exhaustion blow-off:
       single-bar surge > `surge` AND RSI > rsi_min AND volume > vol_mult*avg
       AND price extended > ext_atr*ATR above EMA20.
    Returns per-bar short-entry signals + the fast TP / tight-stop / max-hold params
    (this is NOT a trailing-trend exit — it's a quick fade)."""
    c = df["close"]; e20 = ema(c, 20); a = atr(df, atr_period); r = rsi(c, 14)
    avgv = df["volume"].rolling(20).mean()
    surge_now = c / df["open"] - 1
    ext = (c - e20) / a
    entry = ((surge_now > surge) & (r > rsi_min) & (df["volume"] > vol_mult * avgv)
             & (ext > ext_atr)).fillna(False)
    return {"entry": np.where(entry, -1, 0).astype(int), "atr": a.to_numpy(),
            "tp": tp, "stop_atr": stop_atr, "max_hold": max_hold}
