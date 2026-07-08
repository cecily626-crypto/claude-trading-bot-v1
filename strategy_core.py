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
def trend_ls(df, fast=20, slow=50, regime=100, atr_period=14, stop_mult=3.0,
             short_gap=0.03, long_gap=0.005, rsi_max=70.0, rsi_min=30.0,
             use_filters=True, apply_short_filters=False):
    """BTC/ETH: symmetric trend, but short only on a CONFIRMED downtrend.

    PATCH (2026-07-08, after the 07-07 BTC false-long review):
      做多两道新过滤，专治“均线临界叉”假信号（那次 EMA50 只比 EMA100 高 0.03%）：
        - gap:  EMA50 必须比 EMA100 高出至少 `long_gap`（默认 0.5%），且 close 也高出
                EMA100 至少 long_gap —— 滤掉均线粘合/刚交叉就进的低质量多单。
        - rsi:  RSI(14) < `rsi_max`（默认 70），防追高。
      做空默认【不动】(apply_short_filters=False)：做空是 11 个月回测的利润引擎
      (PF 1.71 vs 做多 0.86)，且 58 天 4h 回测显示对做空加 gap/RSI 会在下跌行情里
      砍掉最赚钱的顺势空单（对称版 +6.4%→-2.4%，仅做多版 +6.4%→+9.3% / PF 2.25）。
      如需多空对称过滤，设 apply_short_filters=True。
    """
    c = df["close"]
    ef, es, er = ema(c, fast), ema(c, slow), ema(c, regime)
    a = atr(df, atr_period)
    r = rsi(c, 14)
    long_ok = (ef > es) & (es > er * (1 + long_gap)) & (c > er * (1 + long_gap))
    if apply_short_filters:
        short_ok = (ef < es) & (es < er * (1 - long_gap)) & (c < er * (1 - short_gap))
    else:
        short_ok = (ef < es) & (es < er) & (c < er * (1 - short_gap))
    if use_filters:
        long_ok = long_ok & (r < rsi_max)
        if apply_short_filters:
            short_ok = short_ok & (r > rsi_min)
    target = np.where(long_ok, 1, np.where(short_ok, -1, 0))
    return {"target": target.astype(int), "atr": a.to_numpy(), "stop_mult": stop_mult,
            "atr_pct": (a / c).to_numpy(), "aux": {"ema_regime": er, "rsi": r}}


def pullback_entry_1h(df1h, direction, ema_fast=20, lookback=6, rsi_dip=45.0):
    """多周期择时（PATCH 2026-07-08）：4h 决定方向 `direction`(+1 做多 / -1 做空)，
    用 1h 图等一次回调再进场，争取更好的价格，而不是在 4h 信号 K 线直接追。

      做多: 近 `lookback` 根 1h 内价格回踩过 1h EMA20（或 RSI<rsi_dip），
            且最新 1h 收盘重新站上 EMA20 且较上一根上翘 -> (True, 最新1h收盘价)。
      做空: 镜像 —— 反弹到 1h EMA20（或 RSI>100-rsi_dip）后，最新 1h 重新跌破 EMA20 且下拐。

    返回 (ok, price)。ok=False 表示方向虽成立但还没到好的进场点，应继续等待、不追。
    只对趋势币(BTC/ETH)建议启用；memecoin 突破策略仍用 4h 原逻辑。
    """
    c = df1h["close"]; e = ema(c, ema_fast); r = rsi(c, 14)
    lo = df1h["low"]; hi = df1h["high"]; i = len(df1h) - 1
    if i < lookback or direction == 0:
        return False, float(c.iloc[-1])
    if direction > 0:
        pulled = bool((lo.iloc[i - lookback:i + 1] <= e.iloc[i - lookback:i + 1]).any()
                      or (r.iloc[i - lookback:i + 1] < rsi_dip).any())
        resume = bool(c.iloc[i] > e.iloc[i] and c.iloc[i] > c.iloc[i - 1])
    else:
        pulled = bool((hi.iloc[i - lookback:i + 1] >= e.iloc[i - lookback:i + 1]).any()
                      or (r.iloc[i - lookback:i + 1] > 100 - rsi_dip).any())
        resume = bool(c.iloc[i] < e.iloc[i] and c.iloc[i] < c.iloc[i - 1])
    return (pulled and resume), float(c.iloc[i])


def breakout_ls(df, breakout=55, regime=100, atr_period=14, stop_mult=2.5, mom=20, short_gap=0.03,
                use_filters=True, rsi_max=65.0, surge_max=0.25, ext_atr=1.5, vol_mult=1.2):
    """Memecoins: long on new-high breakout in up-regime; short on new-low
    breakdown in a CONFIRMED downtrend (price >= short_gap below EMA(regime)).

    PATCH (anti-chase, default ON): a breakout LONG is skipped if it is just a
    blow-off spike — any of:
        F1  single-bar surge (close/open-1) > surge_max          (vertical pump)
        F2  price extended > ext_atr * ATR above the breakout line (chased too far)
        F3  RSI(14) > rsi_max at the breakout                     (overbought / late)

    PATCH 2 (2026-07-05, week-1 paper review): volume confirmation, default ON —
        F4  the breakout/breakdown bar must print volume > vol_mult * 20-bar average
            volume. Low-volume breakouts (the USELESS -9.9%/-9.1% and GORK -12.0%
            week-1 whipsaws) are skipped. Applies to BOTH longs and shorts.

    PATCH 3 (2026-07-05, 11-month deep backtest, backtest_deep.py run #2):
        breakout 20 -> 55 and rsi_max 75 -> 65. The combo was the ONLY config
        (of 18 tested) profitable in BOTH halves of the 11-month window:
        FULL PF 1.29 -> 1.65, recent-half PF 0.69 (-127%) -> 1.13 (+20%).
        It cuts the <=1-day "instant death" trades that attribution showed were
        the main leak (12.3% win rate, -187% contribution).
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
