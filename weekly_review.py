"""
Weekly strategy review.  Runs once a week (GitHub Actions), re-backtests the live
strategies on a fresh rolling window of LBank 4h data, compares win rate / profit
factor / return to LAST week, and pushes a Telegram retrospective. If the win rate
clearly drops it escalates with a "需要复盘" flag and concrete optimisation ideas to
discuss; otherwise it says "保持不变".

State is kept in review_history.json (committed back by the workflow).

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (same secrets as the signal bot)
Run: python weekly_review.py            (live)
     python weekly_review.py --dry-run  (print, don't send)
"""
import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import numpy as np
import pandas as pd

from exchange_data import fetch_klines, MEMECOINS, TREND_COINS
from strategy_core import trend_ls, breakout_ls

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
BARS_PER_YEAR = {"hour4": 365 * 6, "hour1": 365 * 24, "day1": 365}.get(KTYPE, 365 * 6)
HIST_FILE = os.path.join(os.path.dirname(__file__), "review_history.json")
FEE, SLIP = 0.0002, 0.0005          # LBank taker 0.02% + slippage buffer

# how big a win-rate drop counts as "需要复盘"
DROP_PP = 5.0            # percentage points vs last week
FLOOR = 35.0             # absolute floor (%)


# --------------------------- mini long/short backtest -----------------------
def simulate(df, sig, target_vol, cap):
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    n = len(df); target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    atr_pct = sig["atr_pct"]; cost = FEE + SLIP
    cash, units, dir_ = 10000.0, 0.0, 0
    entry = stop = extreme = 0.0; locked = 0; pending = None
    eq = np.empty(n); trades = []

    def trade(cash, units, delta, price):
        cash -= delta * price + abs(delta) * price * cost
        return cash, units + delta

    for i in range(n):
        if pending is not None and pending != dir_:
            if dir_ != 0:
                cash, units = trade(cash, units, -units, o[i])
                trades[-1]["ret"] = (o[i] / entry - 1) * trades[-1]["dir"]
                dir_ = 0
            if pending != 0:
                w = float(np.clip(target_vol / ((atr_pct[i - 1] if i and atr_pct[i-1] > 0 else 0.02)
                                                * np.sqrt(BARS_PER_YEAR)), 0.05, cap))
                u = pending * (cash * w) / o[i]
                cash, units = trade(cash, units, u, o[i])
                dir_ = pending; entry = o[i]
                extreme = h[i] if dir_ > 0 else l[i]
                stop = entry - mult * atr_a[i] if dir_ > 0 else entry + mult * atr_a[i]
                trades.append({"dir": dir_, "entry": entry})
            pending = None
        if dir_ > 0:
            if l[i] <= stop:
                cash, units = trade(cash, units, -units, min(o[i], stop))
                trades[-1]["ret"] = (min(o[i], stop) / entry - 1); dir_ = 0; locked = 1
            else:
                extreme = max(extreme, h[i]); stop = max(stop, extreme - mult * atr_a[i])
        elif dir_ < 0:
            if h[i] >= stop:
                cash, units = trade(cash, units, -units, max(o[i], stop))
                trades[-1]["ret"] = (entry / max(o[i], stop) - 1); dir_ = 0; locked = -1
            else:
                extreme = min(extreme, l[i]); stop = min(stop, extreme + mult * atr_a[i])
        des = target[i]
        if locked != 0:
            des = 0 if des == locked else (locked := 0) or des
        if des != dir_:
            pending = des
        eq[i] = cash + units * c[i]
    closed = [t for t in trades if "ret" in t]
    eqs = pd.Series(eq, index=df.index)
    dd = float((eqs / eqs.cummax() - 1).min())
    total = float(eqs.iloc[-1] / eqs.iloc[0] - 1)
    return closed, total, dd


def pooled(group_trades, totals):
    rets = [t["ret"] for t in group_trades]
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    win = 100 * len(wins) / len(rets) if rets else float("nan")
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    return {"win": round(win, 1), "trades": len(rets),
            "pf": round(pf, 2) if pf != float("inf") else 99.0,
            "avg_total": round(100 * np.mean(totals), 1) if totals else 0.0}


# ------------------------------ run review ----------------------------------
def review():
    groups = {"trend": {"coins": TREND_COINS, "fn": trend_ls, "tv": 0.6, "cap": 1.0},
              "meme": {"coins": MEMECOINS, "fn": breakout_ls, "tv": 0.5, "cap": 0.8}}
    out = {}
    all_trades, all_totals, all_dd = [], [], []
    for g, cfg in groups.items():
        gt, gtot = [], []
        for coin in cfg["coins"]:
            try:
                df = fetch_klines(coin, ktype=KTYPE, size=300)
                if len(df) < 150:
                    continue
                sig = cfg["fn"](df)
                trades, total, dd = simulate(df, sig, cfg["tv"], cfg["cap"])
                gt += trades; gtot.append(total); all_dd.append(dd)
                time.sleep(0.2)
            except Exception as e:
                print(f"[warn] {coin}: {e}")
        out[g] = pooled(gt, gtot)
        all_trades += gt; all_totals += gtot
    out["overall"] = pooled(all_trades, all_totals)
    out["overall"]["maxdd"] = round(100 * min(all_dd), 1) if all_dd else 0.0
    out["date"] = datetime.date.today().isoformat()
    return out


def load_hist():
    return json.load(open(HIST_FILE)) if os.path.exists(HIST_FILE) else []


def fmt_delta(now, prev):
    if prev is None:
        return ""
    d = now - prev
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    return f"（上周 {prev}% {arrow}{abs(round(d,1))}）"


def build_message(cur, hist):
    prev = hist[-1] if hist else None
    pw = lambda g: (prev[g]["win"] if prev else None)
    ov, tr, me = cur["overall"], cur["trend"], cur["meme"]
    degraded = False
    reasons = []
    if prev:
        if ov["win"] - prev["overall"]["win"] <= -DROP_PP:
            degraded = True; reasons.append(f"总体胜率较上周下滑 {round(prev['overall']['win']-ov['win'],1)} 个百分点")
    if ov["win"] < FLOOR:
        degraded = True; reasons.append(f"总体胜率 {ov['win']}% 低于 {FLOOR}% 警戒线")
    if ov["pf"] < 1.0:
        degraded = True; reasons.append(f"盈亏比 {ov['pf']} < 1（亏损单吃掉了盈利）")

    L = [f"📊 *每周策略复盘*（LBank · 4h · 多空 · 滚动~50天）", f"_{cur['date']}_", ""]
    L.append(f"*趋势组（BTC/ETH）*\n  胜率 `{tr['win']}%` {fmt_delta(tr['win'], pw('trend'))} · "
             f"交易 {tr['trades']} · 盈亏比 {tr['pf']} · 区间均收 {tr['avg_total']}%")
    L.append(f"*Memecoin 组（{me['trades']} 笔 / 全部币对）*\n  胜率 `{me['win']}%` {fmt_delta(me['win'], pw('meme'))} · "
             f"盈亏比 {me['pf']} · 区间均收 {me['avg_total']}%")
    L.append(f"*组合总体*\n  胜率 `{ov['win']}%` {fmt_delta(ov['win'], pw('overall'))} · "
             f"盈亏比 {ov['pf']} · 最大回撤 {ov.get('maxdd','-')}%")
    L.append("")
    if degraded:
        L.append("⚠️ *需要复盘* — " + "；".join(reasons) + "。")
        L.append("*可讨论的优化方向：*")
        L.append("  1) 做空门槛 `short_gap` 放宽/收紧（震荡多→放宽，避免乱空）")
        L.append("  2) ATR 止损倍数（频繁被扫→调大；亏损过大→调小）")
        L.append("  3) memecoin universe 收敛到流动性最好的一批，剔除噪音币")
        L.append("  4) 暂时只做多/降杠杆，等趋势更明确再恢复双向")
        L.append("\n要不要按其中某个方向，我帮你重新回测验证后再决定？")
    else:
        L.append("✅ *基本稳定，保持不变*。胜率/盈亏比无明显恶化，继续按现策略执行。")
    L.append("\n_注：趋势策略本就靠少数大赢单，胜率天然不高；盈亏比与回撤比单看胜率更可靠。非投资建议。_")
    return "\n".join(L), degraded


def send(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def main(dry=False):
    hist = load_hist()
    cur = review()
    msg, degraded = build_message(cur, hist)
    if dry:
        print(msg)
    else:
        print("sent:", send(msg).get("ok"), "| degraded:", degraded)
    hist.append(cur)
    json.dump(hist[-52:], open(HIST_FILE, "w"), indent=2)   # keep ~1 year


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
