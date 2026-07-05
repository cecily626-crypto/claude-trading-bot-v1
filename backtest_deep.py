"""
Deep backtest (2026-07-05):
  A) Long window: 2000 x 4h bars (~11 months, LBank single-call cap), quarterly split.
  B) Loss attribution on the CURRENT live parameters: by direction, exit reason,
     coin, holding time, biggest losers.
  C) One-factor-at-a-time parameter sensitivity, each validated on first half vs
     second half of the window (guards against overfitting a single regime).

Universe: btc/eth (trend_ls) + doge sol pepe bonk eigen wif shib floki popcat
(breakout_ls). ZEC is not listed on LBank (pair nonsupport) and is excluded.

Execution model per trade: signal on closed bar -> fill next open; ATR trailing
stop checked intra-bar; fees+slippage 0.07% per side. Per-trade equal weight.

Run: python backtest_deep.py     (GitHub Actions: backtest_deep.yml, manual)
"""
import os
import json
import time
import urllib.request
import urllib.parse

import numpy as np

from exchange_data import fetch_klines
from strategy_core import trend_ls, breakout_ls

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
BARS = int(os.environ.get("BACKTEST_BARS", "2000"))
FEE, SLIP = 0.0002, 0.0005
RT_COST = 2 * (FEE + SLIP)

TREND_SET = ["btc", "eth"]
ALT_SET = ["doge", "sol", "pepe", "bonk", "eigen", "wif", "shib", "floki", "popcat"]

BASE = {"regime": 100, "breakout": 20, "stop": 2.5, "stop_trend": 3.0,
        "vol": 1.2, "rsi": 75.0, "long_only": False}

VARIANTS = [
    ("baseline(当前参数)", {}),
    ("regime=144", {"regime": 144}),
    ("regime=200", {"regime": 200}),
    ("breakout=30", {"breakout": 30}),
    ("breakout=55", {"breakout": 55}),
    ("stop=2.0", {"stop": 2.0, "stop_trend": 2.5}),
    ("stop=3.0", {"stop": 3.0, "stop_trend": 3.5}),
    ("stop=3.5", {"stop": 3.5, "stop_trend": 4.0}),
    ("vol=off(关闭量能)", {"vol": 0.0}),
    ("vol=1.5", {"vol": 1.5}),
    ("vol=2.0", {"vol": 2.0}),
    ("rsi_max=65", {"rsi": 65.0}),
    ("只多不空", {"long_only": True}),
    ("只多+regime=200", {"long_only": True, "regime": 200}),
    ("只多+breakout=55", {"long_only": True, "breakout": 55}),
]


def simulate(df, kind, p):
    """Walk the live state machine; return list of trade dicts."""
    if kind == "trend":
        sig = trend_ls(df, regime=p["regime"], stop_mult=p["stop_trend"])
    else:
        sig = breakout_ls(df, breakout=p["breakout"], regime=p["regime"],
                          stop_mult=p["stop"], rsi_max=p["rsi"], vol_mult=p["vol"])
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    if p["long_only"]:
        target = np.where(target < 0, 0, target)
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
            pending = des
    return trades


def stats(trades):
    rets = [t["ret"] for t in trades]
    if not rets:
        return {"n": 0, "win": float("nan"), "pf": float("nan"), "tot": 0.0, "avg": 0.0}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 99.0
    return {"n": len(rets), "win": 100 * len(wins) / len(rets), "pf": pf,
            "tot": 100 * sum(rets), "avg": 100 * np.mean(rets)}


def fmt(name, s):
    return (f"{name:22s} n={s['n']:4d}  win={s['win']:5.1f}%  PF={s['pf']:5.2f}  "
            f"tot={s['tot']:+8.1f}%  avg={s['avg']:+6.2f}%")


def send(text):
    if not TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    universe = [("trend", c) for c in TREND_SET] + [("breakout", c) for c in ALT_SET]
    data = {}
    nmin = 10 ** 9
    for kind, coin in universe:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=BARS)
            if len(df) < 400:
                print(f"[warn] {coin}: only {len(df)} bars, skipped")
                continue
            data[coin] = (kind, df)
            nmin = min(nmin, len(df))
            print(f"[ok] {coin}: {len(df)} bars ({kind})  "
                  f"{df.index[0].date()} -> {df.index[-1].date()}")
            time.sleep(0.25)
        except Exception as e:
            print(f"[warn] {coin}: {e}")
    if not data:
        raise SystemExit("no data")

    # ---------------- A) baseline over full window + quarters ----------------
    print("\n================ A. 基线策略 · 全窗口与季度分段 ================")
    base_trades = {}
    for coin, (kind, df) in data.items():
        base_trades[coin] = [dict(t, coin=coin, kind=kind, n=len(df))
                             for t in simulate(df, kind, BASE)]
    allt = [t for ts in base_trades.values() for t in ts]
    print(fmt("FULL(~11mo)", stats(allt)))
    for q in range(4):
        qt = [t for t in allt if q * t["n"] // 4 <= t["i1"] < (q + 1) * t["n"] // 4]
        print(fmt(f"  Q{q+1}(按时段1/4切)", stats(qt)))
    print("\n-- per coin (baseline, full window) --")
    for coin in data:
        print(fmt(f"  {coin}", stats(base_trades[coin])))

    # ---------------- B) loss attribution on baseline -----------------------
    print("\n================ B. 亏损归因（基线参数） ================")
    for lab, sel in [("LONG", lambda t: t["dir"] > 0), ("SHORT", lambda t: t["dir"] < 0)]:
        print(fmt(lab, stats([t for t in allt if sel(t)])))
    for why in ("trail_stop", "flip/regime"):
        print(fmt(f"exit={why}", stats([t for t in allt if t["why"] == why])))
    for lab, sel in [("hold<=6bars(1天内)", lambda t: t["hold"] <= 6),
                     ("hold 7-18bars", lambda t: 6 < t["hold"] <= 18),
                     ("hold>18bars(3天+)", lambda t: t["hold"] > 18)]:
        print(fmt(lab, stats([t for t in allt if sel(t)])))
    worst = sorted(allt, key=lambda t: t["ret"])[:10]
    print("-- 10 笔最大亏损 --")
    for t in worst:
        print(f"  {t['coin']:8s} {'L' if t['dir']>0 else 'S'} ret={t['ret']*100:+6.1f}% "
              f"hold={t['hold']:3d}bars why={t['why']}")
    lr = sorted([t["ret"] for t in allt])
    tail = sum(r for r in lr[:max(1, len(lr)//10)])
    tot = sum(r for r in lr if r <= 0)
    if tot < 0:
        print(f"最差10%的交易贡献了全部亏损的 {100*tail/tot:.0f}%")

    # ---------------- C) one-factor sensitivity, half/half validation -------
    print("\n================ C. 参数敏感性（全窗口 | 前半 | 后半） ================")
    tg = []
    for name, over in VARIANTS:
        p = dict(BASE, **over)
        vt = []
        for coin, (kind, df) in data.items():
            vt.extend(dict(t, n=len(df)) for t in simulate(df, kind, p))
        h1 = [t for t in vt if t["i1"] < t["n"] // 2]
        h2 = [t for t in vt if t["i1"] >= t["n"] // 2]
        s, s1, s2 = stats(vt), stats(h1), stats(h2)
        line = (f"{name:22s} FULL n={s['n']:4d} PF={s['pf']:5.2f} tot={s['tot']:+8.1f}% | "
                f"H1 PF={s1['pf']:5.2f} tot={s1['tot']:+7.1f}% | "
                f"H2 PF={s2['pf']:5.2f} tot={s2['tot']:+7.1f}%")
        print(line)
        tg.append((name, s, s1, s2))

    best = sorted(tg, key=lambda x: min(x[2]["pf"] if x[2]["n"] else 0,
                                        x[3]["pf"] if x[3]["n"] else 0), reverse=True)[:4]
    lines = [f"*深度回测*（LBank {KTYPE}·{BARS}根≈11个月·11币对·含费用）",
             f"基线: {fmt('baseline', stats(allt))}",
             "前后半段最稳的 4 个变体（按 min(H1,H2) PF 排）:"]
    for name, s, s1, s2 in best:
        lines.append(f"{name}: FULL PF {s['pf']:.2f} tot {s['tot']:+.0f}% "
                     f"(H1 {s1['pf']:.2f}/H2 {s2['pf']:.2f})")
    lines.append("_单因子扫描，正式换参数前需再验证_")
    ok = send("\n".join(lines))
    if ok is not None:
        print("\ntelegram sent:", ok.get("ok"))


if __name__ == "__main__":
    main()
