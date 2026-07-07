"""
v2.0-Short weekly strategy review (runs with weekly_review.py, Monday 00:00 UTC).

1. Re-backtests the LIVE short config — S1 breakdown_short(bo55, 仅止损出场) on
   memecoins + trend_short on BTC/ETH — on a fresh rolling ~50-day window.
2. Compares win rate / PF to last week (review_history_short.json).
3. Summarizes the short paper account's week (trades, realized PnL, equity).
4. Escalates with "需要复盘" + concrete ideas if degraded, else "保持不变".

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Run: python weekly_review_short.py [--dry-run]
"""
import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse

from exchange_data import fetch_klines, MEMECOINS, TREND_COINS
from strategy_short import breakdown_short, trend_short

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
HIST_FILE = os.path.join(os.path.dirname(__file__), "review_history_short.json")
PAPER_FILE = os.path.join(os.path.dirname(__file__), "paper_account_short.json")
FEE, SLIP = 0.0002, 0.0005
RT_COST = 2 * (FEE + SLIP)
S1_KW = {"breakout": 55}
STOP_EXIT_ONLY = True
TAG = "【2.0空】"
DROP_PP, FLOOR = 5.0, 30.0


def sim(df, sig, stop_exit_only=True):
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    o, h, l = (df[x].to_numpy() for x in ("open", "high", "low"))
    dir_ = 0; entry = stop = extreme = 0.0; locked = 0; pending = None
    rets = []
    for i in range(len(df)):
        if pending is not None and pending != dir_:
            if dir_ != 0:
                rets.append((o[i] / entry - 1) * dir_ - RT_COST)
            if pending != 0:
                entry = o[i]; dir_ = pending; extreme = l[i]
                stop = entry + mult * atr_a[i]
            else:
                dir_ = 0
            pending = None
        if dir_ < 0:
            if h[i] >= stop:
                rets.append((stop / entry - 1) * dir_ - RT_COST)
                dir_ = 0; locked = -1
            else:
                extreme = min(extreme, l[i]); stop = min(stop, extreme + mult * atr_a[i])
        des = int(target[i])
        if locked != 0:
            des = 0 if des == locked else (locked := 0) or des
        if des != dir_:
            if dir_ == 0 or not stop_exit_only:
                pending = des
    return rets


def pooled(rets):
    if not rets:
        return {"win": float("nan"), "trades": 0, "pf": float("nan"), "avg": 0.0}
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else 99.0
    return {"win": round(100 * len(wins) / len(rets), 1), "trades": len(rets),
            "pf": round(pf, 2), "avg": round(100 * sum(rets) / len(rets), 2)}


def review():
    meme_rets, ts_rets = [], []
    for coin in MEMECOINS:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) >= 150:
                meme_rets += sim(df, breakdown_short(df, **S1_KW), STOP_EXIT_ONLY)
            time.sleep(0.2)
        except Exception as e:
            print(f"[warn] {coin}: {e}")
    for coin in TREND_COINS:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) >= 150:
                ts_rets += sim(df, trend_short(df), False)
            time.sleep(0.2)
        except Exception as e:
            print(f"[warn] {coin}: {e}")
    return {"date": datetime.date.today().isoformat(),
            "s1": pooled(meme_rets), "ts": pooled(ts_rets),
            "overall": pooled(meme_rets + ts_rets)}


def paper_week():
    if not os.path.exists(PAPER_FILE):
        return None
    st = json.load(open(PAPER_FILE))
    wk_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()
    log = [e for e in st.get("log", []) if e.get("ts", "") >= wk_ago]
    closes = [e for e in log if e["ev"] == "close"]
    opens = [e for e in log if e["ev"] == "open"]
    eq = st["cash"] + sum(p["units"] * p["last_px"] for p in st.get("positions", {}).values())
    return {"opens": len(opens), "closes": len(closes),
            "pnl": sum(c["pnl"] for c in closes), "eq": eq, "start": st["start"],
            "pos": len(st.get("positions", {}))}


def fmt_delta(now, prev):
    if prev is None or now != now:
        return ""
    d = now - prev
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    return f"（上周 {prev}% {arrow}{abs(round(d, 1))}）"


def build(cur, hist, pw_):
    prev = hist[-1] if hist else None
    ov = cur["overall"]
    degraded, reasons = False, []
    if prev and ov["win"] == ov["win"] and prev["overall"]["win"] == prev["overall"]["win"]:
        if ov["win"] - prev["overall"]["win"] <= -DROP_PP:
            degraded = True
            reasons.append(f"总体胜率较上周下滑 {round(prev['overall']['win'] - ov['win'], 1)} 个百分点")
    if ov["win"] == ov["win"] and ov["win"] < FLOOR:
        degraded = True; reasons.append(f"总体胜率 {ov['win']}% 低于 {FLOOR}% 警戒线")
    if ov["pf"] == ov["pf"] and ov["pf"] < 1.0:
        degraded = True; reasons.append(f"盈亏比 {ov['pf']} < 1")

    L = [f"{TAG}📊 *每周做空策略复盘*（LBank · 4h · 滚动~50天）", f"_{cur['date']}_", ""]
    L.append(f"*S1 破位空（meme）*  胜率 `{cur['s1']['win']}%` "
             f"{fmt_delta(cur['s1']['win'], prev['s1']['win'] if prev else None)} · "
             f"交易 {cur['s1']['trades']} · PF {cur['s1']['pf']} · 单笔均 {cur['s1']['avg']}%")
    L.append(f"*TS 趋势空（BTC/ETH）*  胜率 `{cur['ts']['win']}%` · 交易 {cur['ts']['trades']} · "
             f"PF {cur['ts']['pf']}")
    L.append(f"*总体*  胜率 `{ov['win']}%` "
             f"{fmt_delta(ov['win'], prev['overall']['win'] if prev else None)} · PF {ov['pf']}")
    if pw_:
        L.append(f"\n*纸账户本周*  开空 {pw_['opens']} / 平空 {pw_['closes']} 笔 · "
                 f"已实现 `{pw_['pnl']:+.2f}` · 净值 `${pw_['eq']:.2f}` "
                 f"({(pw_['eq']/pw_['start']-1)*100:+.1f}%) · 持仓 {pw_['pos']}")
    L.append("")
    if degraded:
        L.append("⚠️ *需要复盘* — " + "；".join(reasons) + "。")
        L.append("*可讨论的优化方向：*")
        L.append("  1) 加行情过滤：BTC 在 EMA200 上方时禁止 meme 开空（回测显示上行期做空亏损）")
        L.append("  2) breakout 55→更大（更少但更准的破位）或 ATR 止损倍数调整")
        L.append("  3) 收敛做空 universe，剔除近期与信号背离的币")
        L.append("  4) 暂停 meme 空、仅保留 BTC/ETH 趋势空，等下跌趋势确认再恢复")
        L.append("\n要不要按其中某个方向重新回测验证？")
    else:
        L.append("✅ *基本稳定，保持不变*。")
    L.append("\n_做空盈利靠下跌行情，震荡上行期回撤属预期内；盯 PF 与熔断次数比胜率更有效。非投资建议。_")
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
    hist = json.load(open(HIST_FILE)) if os.path.exists(HIST_FILE) else []
    cur = review()
    msg, degraded = build(cur, hist, paper_week())
    if dry:
        print(msg)
    else:
        print("sent:", send(msg).get("ok"), "| degraded:", degraded)
    hist.append(cur)
    json.dump(hist[-52:], open(HIST_FILE, "w"), indent=2)


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
