"""
EMA-regime A/B backtest: breakout_ls with regime=55 vs regime=100.

Purpose (2026-07-05 week-1 paper review): decide with data — not by feel —
whether the memecoin breakout strategy should use a faster EMA55 trend filter
(earlier entries, more false signals) or keep the current EMA100.

Method: for every coin in the current MEMECOINS universe, pull the last 300
4h bars (~50 days) from LBank and replay the SAME bar-close state machine the
live bot uses (enter next open, ATR trailing stop, fees+slippage), once per
regime setting. Prints a comparison table; sends a Telegram summary when
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are set.

Run: python backtest_regime.py            (in GitHub Actions: backtest.yml)
NOTE: ~50 days is a short window — treat results as directional evidence,
re-run weekly and only switch after consistent outperformance.
"""
import os
import json
import time
import urllib.request
import urllib.parse

from exchange_data import fetch_klines, MEMECOINS
from strategy_core import breakout_ls

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
FEE, SLIP = 0.0002, 0.0005
REGIMES = (55, 100)


def simulate(df, regime):
    """Replay the live state machine over closed bars; return per-trade returns."""
    sig = breakout_ls(df, regime=regime)
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    o, h, l = (df[x].to_numpy() for x in ("open", "high", "low"))
    n = len(df)
    dir_ = 0
    entry = stop = extreme = 0.0
    locked = 0
    pending = None
    trades = []
    for i in range(n):
        if pending is not None and pending != dir_:
            if dir_ != 0:                                   # close at next open
                trades.append((o[i] / entry - 1) * dir_ - 2 * (FEE + SLIP))
            if pending != 0:
                entry = o[i]
                dir_ = pending
                extreme = h[i] if dir_ > 0 else l[i]
                stop = entry - mult * atr_a[i] if dir_ > 0 else entry + mult * atr_a[i]
            else:
                dir_ = 0
            pending = None
        if dir_ > 0:
            if l[i] <= stop:
                trades.append((stop / entry - 1) - 2 * (FEE + SLIP))
                dir_ = 0
                locked = 1
            else:
                extreme = max(extreme, h[i])
                stop = max(stop, extreme - mult * atr_a[i])
        elif dir_ < 0:
            if h[i] >= stop:
                trades.append((1 - stop / entry) - 2 * (FEE + SLIP))
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
    if not trades:
        return {"n": 0, "win": float("nan"), "pf": float("nan"), "tot": 0.0}
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 99.0
    return {"n": len(trades), "win": 100 * len(wins) / len(trades),
            "pf": pf, "tot": 100 * sum(trades)}


def send(text):
    if not TOKEN or not CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    all_trades = {r: [] for r in REGIMES}
    per_coin = {r: {} for r in REGIMES}
    for coin in MEMECOINS:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) < 120:
                continue
            for r in REGIMES:
                tr = simulate(df, r)
                all_trades[r].extend(tr)
                per_coin[r][coin] = stats(tr)
            time.sleep(0.25)
        except Exception as e:
            print(f"[warn] {coin}: {e}")

    lines = ["*EMA regime 回测*（LBank 4h · 最近300根 ≈ 50天 · 含手续费滑点）"]
    for r in REGIMES:
        s = stats(all_trades[r])
        line = (f"EMA{r}: {s['n']} 笔  胜率 {s['win']:.1f}%  PF {s['pf']:.2f}  "
                f"累计收益 {s['tot']:+.1f}%（单笔等权）")
        print(line)
        lines.append(line)
    print("\nper-coin (EMA55 | EMA100)  n/win%/PF:")
    for coin in sorted(per_coin[REGIMES[0]]):
        a, b = per_coin[REGIMES[0]][coin], per_coin[REGIMES[1]][coin]
        print(f"  {coin:10s} {a['n']:3d}/{a['win']:5.1f}/{a['pf']:5.2f} | "
              f"{b['n']:3d}/{b['win']:5.1f}/{b['pf']:5.2f}")
    lines.append("_窗口较短，仅作方向性证据；连续数周占优才切换参数_")
    ok = send("\n".join(lines))
    if ok is not None:
        print("telegram sent:", ok.get("ok"))


if __name__ == "__main__":
    main()
