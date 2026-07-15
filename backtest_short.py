"""
v2.0-Short strategy selection backtest.

Compares SHORT-ONLY candidates on 2000 x 4h LBank bars (~11 months):
  S1  breakdown_short  (trend-following breakdown, ATR trailing stop)
  S2  blowoff fade     (mean-reversion short on exhaustion pumps, fast TP)
  TS  trend_short      (BTC/ETH only)
  S3  best-S1 + best-S2 combined

Execution model identical to v1 backtests: signal on CLOSED bar -> fill next
open; trailing stop / TP checked intra-bar (stop takes priority = worst case);
fees+slippage 0.07% per side. Per-trade equal weight, pooled stats.
Robustness: first half vs second half of the window (min PF rule), quarters,
per-coin and exit attribution for the winners.

Outputs: full report -> stdout + backtest_short_report.md (committed by the
workflow) + Telegram summary.

Run: python backtest_short.py            (GitHub Actions: backtest-short.yml)
"""
import os
import json
import time
import datetime
import urllib.request
import urllib.parse

import numpy as np

from exchange_data import fetch_klines, MEMECOINS, TREND_COINS
from strategy_short import breakdown_short, trend_short
from strategy_core import blowoff_short, ema

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
BARS = int(os.environ.get("BACKTEST_BARS", "2000"))
FEE, SLIP = 0.0002, 0.0005
RT_COST = 2 * (FEE + SLIP)
REPORT = os.path.join(os.path.dirname(__file__), "backtest_short_report.md")
RESULTS = os.path.join(os.path.dirname(__file__), "backtest_short_results.json")

# 2026-07-14 A/B: confirm=回踩确认(opt#2), __regime__=BTC大盘闸门(opt#1).
# NOTE breakdown_short 默认 confirm=True, 所以"现行baseline"必须显式 confirm=False.
S1_VARIANTS = [
    # ---- 现行实盘基线 (opt#2 关) ----
    ("S1b bo55 现行(confirm off)", {"breakout": 55, "confirm": False}, True),
    # ---- opt#2 回踩确认 ----
    ("S1b+回踩确认 (opt#2)", {"breakout": 55, "confirm": True}, True),
    # ---- opt#2 + opt#1 大盘闸门 ----
    ("S1b+回踩+大盘闸门 (opt#2+#1)", {"breakout": 55, "confirm": True, "__regime__": True}, True),
    # ---- opt#1 单独 (仅大盘闸门, 回踩关) ----
    ("S1b+仅大盘闸门 (opt#1 only)", {"breakout": 55, "confirm": False, "__regime__": True}, True),
    # ---- 参考: 老 baseline (confirm off) ----
    ("S1a bo20 (confirm off)", {"confirm": False}, False),
    ("S1b bo55 无仅止损 (confirm off)", {"breakout": 55, "confirm": False}, False),
    ("S1c reg200/gap5 (confirm off)", {"regime": 200, "gap": 0.05, "confirm": False}, False),
]
S2_VARIANTS = [
    ("S2a surge40/rsi85/vol3/ext3 tp15/h6", {}),
    ("S2b surge25/rsi80/vol2/ext2 tp15/h6",
     {"surge": 0.25, "rsi_min": 80.0, "vol_mult": 2.0, "ext_atr": 2.0}),
    ("S2c =a, tp10/hold12", {"tp": 0.10, "max_hold": 12}),
    ("S2d =b, tp10/hold12",
     {"surge": 0.25, "rsi_min": 80.0, "vol_mult": 2.0, "ext_atr": 2.0,
      "tp": 0.10, "max_hold": 12}),
]


# ------------------------------ engines --------------------------------------
def sim_target(df, sig, stop_exit_only=False):
    """v1 state machine: target -1/0, next-open fills, ATR trailing stop."""
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    o, h, l = (df[x].to_numpy() for x in ("open", "high", "low"))
    n = len(df)
    dir_ = 0
    entry = stop = extreme = 0.0
    i0 = 0
    locked = 0
    pending = None
    trades = []

    def close(i, px, reason):
        trades.append({"i0": i0, "i1": i, "dir": dir_, "hold": i - i0,
                       "ret": (px / entry - 1) * dir_ - RT_COST, "why": reason})

    for i in range(n):
        if pending is not None and pending != dir_:
            if dir_ != 0:
                close(i, o[i], "flip/regime")
            if pending != 0:
                entry = o[i]
                dir_ = pending
                i0 = i
                extreme = h[i] if dir_ > 0 else l[i]
                stop = entry - mult * atr_a[i] if dir_ > 0 else entry + mult * atr_a[i]
            else:
                dir_ = 0
            pending = None
        if dir_ > 0:
            if l[i] <= stop:
                close(i, stop, "trail_stop")
                dir_ = 0
                locked = 1
            else:
                extreme = max(extreme, h[i])
                stop = max(stop, extreme - mult * atr_a[i])
        elif dir_ < 0:
            if h[i] >= stop:
                close(i, stop, "trail_stop")
                dir_ = 0
                locked = -1
            else:
                extreme = min(extreme, l[i])
                stop = min(stop, extreme + mult * atr_a[i])
        des = int(target[i])
        if locked != 0:
            if des == locked:
                des = 0
            else:
                locked = 0
        if des != dir_:
            if dir_ == 0 or not stop_exit_only:
                pending = des
    return trades


def sim_fade(df, sig):
    """Blow-off fade: enter short next open; exit = stop (entry + stop_atr*ATR,
    checked FIRST = worst case), TP (entry*(1-tp)), or time (max_hold bars)."""
    entry_sig, atr_a = sig["entry"], sig["atr"]
    tp, stop_atr, max_hold = sig["tp"], sig["stop_atr"], sig["max_hold"]
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    n = len(df)
    pos = False
    pending = False
    entry = stop = tp_px = 0.0
    i0 = 0
    trades = []
    for i in range(n):
        if pending and not pos:
            entry = o[i]
            i0 = i
            stop = entry + stop_atr * atr_a[i - 1]
            tp_px = entry * (1 - tp)
            pos = True
            pending = False
        if pos and i >= i0:
            exit_px, why = None, None
            if h[i] >= stop:
                exit_px, why = stop, "stop"
            elif l[i] <= tp_px:
                exit_px, why = tp_px, "tp"
            elif i - i0 >= max_hold:
                exit_px, why = c[i], "time"
            if exit_px is not None:
                trades.append({"i0": i0, "i1": i, "dir": -1, "hold": i - i0,
                               "ret": (entry / exit_px - 1) - RT_COST, "why": why})
                pos = False
        if not pos and i < n - 1 and entry_sig[i] == -1:
            pending = True
    return trades


# ------------------------------ stats ----------------------------------------
def stats(trades):
    rets = [t["ret"] for t in trades]
    if not rets:
        return {"n": 0, "win": float("nan"), "pf": float("nan"), "tot": 0.0,
                "avg": 0.0, "medhold": 0}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 99.0
    return {"n": len(rets), "win": 100 * len(wins) / len(rets), "pf": pf,
            "tot": 100 * sum(rets), "avg": 100 * float(np.mean(rets)),
            "medhold": int(np.median([t["hold"] for t in trades]))}


def fmt(name, s):
    return (f"{name:34s} n={s['n']:4d}  win={s['win']:5.1f}%  PF={s['pf']:5.2f}  "
            f"tot={s['tot']:+8.1f}%  avg={s['avg']:+6.2f}%  hold={s['medhold']:3d}")


def halves(trades):
    h1 = [t for t in trades if t["i1"] < t["n"] // 2]
    h2 = [t for t in trades if t["i1"] >= t["n"] // 2]
    return stats(h1), stats(h2)


def robust_key(trades):
    s1, s2 = halves(trades)
    return min(s1["pf"] if s1["n"] else 0.0, s2["pf"] if s2["n"] else 0.0)


# ------------------- position sizing: rolling-PF circuit breaker --------------
import bisect


def _roll_pf(rets):
    wins = sum(r for r in rets if r > 0)
    losses = sum(r for r in rets if r <= 0)
    return (wins / abs(losses)) if losses != 0 else (9.0 if wins > 0 else 1.0)


def _equity_maxdd(seq):
    """Additive equity curve from time-ordered returns -> (total, maxDD<=0), same units."""
    eq = peak = mdd = 0.0
    for r in seq:
        eq += r
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return eq, mdd


def size_scale(trades, N=30, pf_lo=0.8, pf_hi=1.3, mult_lo=0.3, warm=10):
    """Sequential rolling-PF position scaling (no look-ahead). For each trade in
    ENTRY-time order, size = linear map of the PF over the last N trades that
    CLOSED strictly before this entry, clipped to [mult_lo, 1.0]. Cold strategy
    (low rolling PF) -> smaller size; hot -> full size."""
    by_entry = sorted(trades, key=lambda t: t["t0"])
    by_exit = sorted(trades, key=lambda t: t["t1"])
    exit_ts = [t["t1"] for t in by_exit]
    out = []
    for t in by_entry:
        k = bisect.bisect_left(exit_ts, t["t0"])          # count closed before entry
        window = by_exit[max(0, k - N):k]
        if len(window) >= warm:
            pf = _roll_pf([w["ret"] for w in window])
            mult = mult_lo + (pf - pf_lo) / (pf_hi - pf_lo) * (1.0 - mult_lo)
            mult = min(1.0, max(mult_lo, mult))
        else:
            mult = 1.0                                     # not enough history -> full
        out.append(dict(t, mult=mult, wret=t["ret"] * mult))
    return out


def size_report(name, sized):
    """size-weighted equity (ordered by exit) + max drawdown + H1/H2 + avg size."""
    seq = sorted(sized, key=lambda t: t["t1"])
    tot, mdd = _equity_maxdd([t["wret"] for t in seq])
    h1 = 100 * sum(t["wret"] for t in sized if t["i1"] < t["n"] // 2)
    h2 = 100 * sum(t["wret"] for t in sized if t["i1"] >= t["n"] // 2)
    avg = sum(t["mult"] for t in sized) / len(sized) if sized else 0
    rdd = tot / abs(mdd) if mdd != 0 else float("inf")
    return (f"{name:32s} tot={tot*100:+8.1f}%  maxDD={mdd*100:7.1f}%  "
            f"ret/DD={rdd:5.2f}  avg_size={avg:4.2f} | H1={h1:+7.1f}% H2={h2:+7.1f}%")


def send(text):
    if not TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


# ------------------------------ main ------------------------------------------
def main():
    L = []                                     # report lines

    def out(s=""):
        print(s)
        L.append(s)

    out(f"# v2.0-Short 策略回测报告")
    out(f"_{datetime.datetime.utcnow().isoformat()}Z · LBank {KTYPE} · {BARS} bars_")
    out("```")

    meme_data, trend_data = {}, {}
    for coin in MEMECOINS:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=BARS)
            if len(df) >= 400:
                meme_data[coin] = df
                print(f"[ok] {coin}: {len(df)} bars {df.index[0].date()} -> {df.index[-1].date()}")
            time.sleep(0.25)
        except Exception as e:
            print(f"[warn] {coin}: {e}")
    for coin in TREND_COINS:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=BARS)
            if len(df) >= 400:
                trend_data[coin] = df
            time.sleep(0.25)
        except Exception as e:
            print(f"[warn] {coin}: {e}")
    if not meme_data:
        raise SystemExit("no data")
    spans = [f"{df.index[0].date()}->{df.index[-1].date()}" for df in meme_data.values()]
    out(f"数据: memecoin {len(meme_data)} 个 + trend {len(trend_data)} 个, 窗口 {max(spans)}")

    # BTC 大盘闸门 mask (opt#1): BTC 4h 收盘<EMA100 且 20 根动量<0 才算确认下跌
    btc_df = trend_data.get("btc")
    if btc_df is not None:
        bc = btc_df["close"]
        btc_bear = (bc < ema(bc, 100)) & (bc.pct_change(20) < 0)
        out(f"大盘闸门: BTC 空头占比 {100*btc_bear.mean():.0f}% of window")
    else:
        btc_bear = None
        out("大盘闸门: BTC 数据缺失, __regime__ 变体退化为仅回踩确认")

    # ---------------- S1 scan (memecoins) ----------------
    out("\n== S1 破位趋势做空 (memecoins) · FULL | H1 | H2 ==")
    s1_res = {}
    for name, over, seo in S1_VARIANTS:
        vt = []
        over = dict(over)
        use_regime = over.pop("__regime__", False)
        for coin, df in meme_data.items():
            sig = breakdown_short(df, regime_mask=(btc_bear if use_regime else None), **over)
            for t in sim_target(df, sig, seo):
                t.update(coin=coin, n=len(df),
                         t0=df.index[t["i0"]], t1=df.index[t["i1"]])  # entry/exit时间戳
                vt.append(t)
        s1_res[name] = vt
        s, (sh1, sh2) = stats(vt), halves(vt)
        out(fmt(name, s) + f" | H1 PF={sh1['pf']:5.2f} tot={sh1['tot']:+7.1f}% | "
            f"H2 PF={sh2['pf']:5.2f} tot={sh2['tot']:+7.1f}%")

    # ---------------- S2 scan (memecoins) ----------------
    out("\n== S2 泡沫反转做空 (memecoins) · FULL | H1 | H2 ==")
    s2_res = {}
    for name, over in S2_VARIANTS:
        vt = []
        for coin, df in meme_data.items():
            sig = blowoff_short(df, **over)
            vt += [dict(t, coin=coin, n=len(df)) for t in sim_fade(df, sig)]
        s2_res[name] = vt
        s, (sh1, sh2) = stats(vt), halves(vt)
        out(fmt(name, s) + f" | H1 PF={sh1['pf']:5.2f} tot={sh1['tot']:+7.1f}% | "
            f"H2 PF={sh2['pf']:5.2f} tot={sh2['tot']:+7.1f}%")

    # ---------------- BTC/ETH trend short ----------------
    out("\n== TS 趋势做空 (BTC/ETH) ==")
    ts_trades = []
    for coin, df in trend_data.items():
        sig = trend_short(df)
        ts_trades += [dict(t, coin=coin, n=len(df)) for t in sim_target(df, sig)]
    s, (sh1, sh2) = stats(ts_trades), halves(ts_trades)
    out(fmt("TS btc/eth", s) + f" | H1 PF={sh1['pf']:5.2f} | H2 PF={sh2['pf']:5.2f}")

    # ---------------- winners & detail ----------------
    best_s1 = max(s1_res, key=lambda k: robust_key(s1_res[k]))
    best_s2 = max(s2_res, key=lambda k: robust_key(s2_res[k]))
    out(f"\n== 优胜者 (按 min(H1,H2) PF): S1 -> {best_s1} · S2 -> {best_s2} ==")

    for label, tr in ((best_s1, s1_res[best_s1]), (best_s2, s2_res[best_s2])):
        out(f"\n-- {label} · 明细 --")
        for q in range(4):
            qt = [t for t in tr if q * t["n"] // 4 <= t["i1"] < (q + 1) * t["n"] // 4]
            out(fmt(f"  Q{q+1}", stats(qt)))
        whys = sorted({t["why"] for t in tr})
        for why in whys:
            out(fmt(f"  exit={why}", stats([t for t in tr if t["why"] == why])))
        bycoin = {}
        for t in tr:
            bycoin.setdefault(t["coin"], []).append(t)
        ranked = sorted(bycoin.items(), key=lambda kv: -stats(kv[1])["tot"])
        for coin, ct in ranked[:5]:
            out(fmt(f"  best {coin}", stats(ct)))
        for coin, ct in ranked[-3:]:
            out(fmt(f"  worst {coin}", stats(ct)))
        worst = sorted(tr, key=lambda t: t["ret"])[:5]
        for t in worst:
            out(f"  最大亏损 {t['coin']:10s} ret={t['ret']*100:+6.1f}% hold={t['hold']:3d} why={t['why']}")

    # ---------------- S3 combined ----------------
    s3 = s1_res[best_s1] + s2_res[best_s2] + ts_trades
    out("\n== S3 组合 (best-S1 + best-S2 + TS) ==")
    s, (sh1, sh2) = stats(s3), halves(s3)
    out(fmt("S3 组合", s) + f" | H1 PF={sh1['pf']:5.2f} tot={sh1['tot']:+7.1f}% | "
        f"H2 PF={sh2['pf']:5.2f} tot={sh2['tot']:+7.1f}%")

    # ---------------- position sizing: rolling-PF adaptive scaling -----------
    base_name = "S1b bo55 现行(confirm off)"
    base = s1_res.get(base_name)
    if base:
        out(f"\n== 仓位管理: 滚动PF自适应缩放 (基于 {base_name}) ==")
        out(size_report("基线 满仓(mult=1)",
                        [dict(t, mult=1.0, wret=t["ret"]) for t in base]))
        for tag, kw in [("N30 f0.8/c1.3/min0.30", dict(N=30, pf_lo=0.8, pf_hi=1.3, mult_lo=0.30)),
                        ("N20 f0.9/c1.4/min0.25", dict(N=20, pf_lo=0.9, pf_hi=1.4, mult_lo=0.25)),
                        ("N40 f0.8/c1.5/min0.20", dict(N=40, pf_lo=0.8, pf_hi=1.5, mult_lo=0.20))]:
            out(size_report(tag, size_scale(base, **kw)))
        out("  注: tot/maxDD 为每单位敞口的可加净值; 缩放会降低总敞口, 看 ret/DD 与 H2 是否改善")
    out("```")

    # persist
    summary = {
        "date": datetime.date.today().isoformat(), "bars": BARS, "ktype": KTYPE,
        "universe": {"meme": sorted(meme_data), "trend": sorted(trend_data)},
        "best_s1": best_s1, "best_s2": best_s2,
        "tables": {
            "s1": {k: [stats(v)] + list(halves(v)) for k, v in s1_res.items()},
            "s2": {k: [stats(v)] + list(halves(v)) for k, v in s2_res.items()},
            "ts": [stats(ts_trades)] + list(halves(ts_trades)),
            "s3": [stats(s3)] + list(halves(s3)),
        },
    }
    json.dump(summary, open(RESULTS, "w"), indent=2, default=float)
    open(REPORT, "w").write("\n".join(L) + "\n")

    s_best1, s_best2, s_all = stats(s1_res[best_s1]), stats(s2_res[best_s2]), stats(s3)
    tg = ["v2.0-Short 回测完成 (LBank 4h · ~11个月 · 含费用)",
          f"S1 最稳: {best_s1} | n={s_best1['n']} win={s_best1['win']:.0f}% PF={s_best1['pf']:.2f} tot={s_best1['tot']:+.0f}%",
          f"S2 最稳: {best_s2} | n={s_best2['n']} win={s_best2['win']:.0f}% PF={s_best2['pf']:.2f} tot={s_best2['tot']:+.0f}%",
          f"S3 组合: n={s_all['n']} win={s_all['win']:.0f}% PF={s_all['pf']:.2f} tot={s_all['tot']:+.0f}%",
          "完整报告见仓库 backtest_short_report.md · 等待人工确认后才会上纸账户"]
    ok = send("\n".join(tg))
    if ok is not None:
        print("telegram sent:", ok.get("ok"))


if __name__ == "__main__":
    main()
