"""
EMA-regime A/B backtest: regime EMA55 vs EMA100 as the entry trend filter.

Universe (2026-07-05, user-selected):
  TREND  (trend_ls):    btc, eth
  ALTS   (breakout_ls): doge, sol, zec, pepe, bonk, eigen, wif, shib, floki, popcat

Data: LBank 4h klines, 640 bars (~107 days; after ~100-bar indicator warmup this
is an effective ~3-month trade window). Same bar-close state machine as the live
bot (enter next open, ATR trailing stop, fees + slippage), run once per regime.

Prints a per-coin + aggregate comparison; sends a Telegram summary when
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are set.

Run: python backtest_regime.py            (in GitHub Actions: backtest.yml)
NOTE: single window, no walk-forward — treat results as directional evidence,
re-run weekly and only switch after consistent outperformance.
"""
import os
import json
import time
import urllib.request
import urllib.parse

from exchange_data import fetch_klines
from strategy_core import trend_ls, breakout_ls

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
BARS = int(os.environ.get("BACKTEST_BARS", "640"))
FEE, SLIP = 0.0002, 0.0005
REGIMES = (55, 100)

TREND_SET = ["btc", "eth"]
ALT_SET = ["doge", "sol", "zec", "pepe", "bonk", "eigen", "wif", "shib", "floki", "popcat"]


def simulate(df, kind, regime):
    """Replay the live state machine over closed bars; return per-trade returns."""
    sig = trend_ls(df, regime=regime) if kind == "trend" else breakout_ls(df, regime=regime)
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
    universe = [("trend", c) for c in TREND_SET] + [("breakout", c) for c in ALT_SET]
    all_trades = {r: [] for r in REGIMES}
    per_coin = {r: {} for r in REGIMES}
    for kind, coin in universe:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=BARS)
            got = len(df)
            if got < 150:
                print(f"[warn] {coin}: only {got} bars, skipped")
                continue
            for r in REGIMES:
                tr = simulate(df, kind, r)
                all_trades[r].extend(tr)
                per_coin[r][coin] = stats(tr)
            print(f"[ok] {coin}: {got} bars ({kind})")
            time.sleep(0.25)
        except Exception as e:
            print(f"[warn] {coin}: {e}")

    lines = [f"*EMA regime 回测*（LBank {KTYPE} · {BARS}根 ≈ 3个月+warmup · BTC/ETH trend + 10 alts breakout · 含手续费滑点）"]
    for r in REGIMES:
        s = stats(all_trades[r])
        line = (f"EMA{r}: {s['n']} 笔  胜率 {s['win']:.1f}%  PF {s['pf']:.2f}  "
                f"累计收益 {s['tot']:+.1f}%（单笔等权）")
        print(line)
        lines.append(line)
    print(f"\n{'coin':10s} {'EMA55 n/win%/PF/tot%':>26s} | {'EMA100 n/win%/PF/tot%':>26s}")
    for kind, coin in universe:
        if coin not in per_coin[REGIMES[0]]:
            continue
        a, b = per_coin[REGIMES[0]][coin], per_coin[REGIMES[1]][coin]
        print(f"{coin:10s} {a['n']:3d}/{a['win']:5.1f}/{a['pf']:5.2f}/{a['tot']:+7.1f} | "
              f"{b['n']:3d}/{b['win']:5.1f}/{b['pf']:5.2f}/{b['tot']:+7.1f}")
    lines.append("_单窗口回测，仅作方向性证据；连续数周占优才切换参数_")
    ok = send("\n".join(lines))
    if ok is not None:
        print("telegram sent:", ok.get("ok"))


if __name__ == "__main__":
    main()
