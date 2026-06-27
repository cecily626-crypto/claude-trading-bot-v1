"""
Daily paper-account review -> Telegram. Runs once a day at 00:00 UTC (= 08:00 Beijing).

Summarizes YESTERDAY's virtual trades from paper_account.json:
opens, closes, realized P&L, win/loss, best/worst, and the current account equity.
Read-only (does not modify the account).

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_account.json")
DIRTXT = {1: "多", -1: "空"}


def send(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def equity(st):
    return st["cash"] + sum(p["units"] * p["last_px"] for p in st.get("positions", {}).values())


def build(st, yday):
    log = [e for e in st.get("log", []) if e.get("ts", "")[:10] == yday]
    opens = [e for e in log if e["ev"] == "open"]
    closes = [e for e in log if e["ev"] == "close"]
    eq = equity(st)
    pnl_pct = eq / st["start"] - 1
    L = [f"📄 *模拟盘 · 昨日复盘*（{yday} UTC，约北京时间昨 08:00–今 08:00）", ""]

    if closes:
        tot = sum(c["pnl"] for c in closes)
        wins = [c for c in closes if c["pnl"] > 0]
        best = max(closes, key=lambda c: c["pnl"]); worst = min(closes, key=lambda c: c["pnl"])
        L.append(f"*平仓 {len(closes)} 笔*  合计盈亏 `{tot:+.2f}`  胜 {len(wins)}/负 {len(closes)-len(wins)}")
        L.append(f"  最好 {best['sym'].upper()} `{best['pnl']:+.2f}`（{best['ret']*100:+.1f}%）· "
                 f"最差 {worst['sym'].upper()} `{worst['pnl']:+.2f}`（{worst['ret']*100:+.1f}%）")
        for c in closes:
            L.append(f"  🔵 平{DIRTXT[c['dir']]} {c['sym'].upper()} @ `{c['px']:.6g}`  `{c['pnl']:+.2f}` ({c['ret']*100:+.1f}%)")
    else:
        L.append("*平仓* 0 笔")

    if opens:
        L.append(f"\n*开仓 {len(opens)} 笔*")
        for o in opens:
            side = "开多" if o["dir"] > 0 else "开空"
            L.append(f"  {'🟢' if o['dir']>0 else '🔴'} {side} {o['sym'].upper()} @ `{o['px']:.6g}`  仓位 `${o['notional']:.0f}`")
    else:
        L.append("\n*开仓* 0 笔")

    rets = [c["ret"] for c in st.get("closed", [])]
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    cum_win = (100 * len(wins) / len(rets)) if rets else float("nan")
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99 if wins else float("nan"))
    L.append(f"\n*账户* 净值 `${eq:.2f}` ({pnl_pct*100:+.1f}%) · 持仓 {len(st.get('positions',{}))} 个 · "
             f"累计已实现 `${st.get('realized',0):+.2f}`")
    if rets:
        L.append(f"  累计 {len(rets)} 笔 · 胜率 {cum_win:.0f}% · 盈亏比 {pf:.2f}")
    L.append("\n_虚拟账户 · 非投资建议_")
    return "\n".join(L)


def main(dry=False):
    if not os.path.exists(STATE_FILE):
        msg = "📄 模拟盘昨日复盘：账户尚未初始化（还没跑过纸面账户）。"
    else:
        st = json.load(open(STATE_FILE))
        yday = (datetime.datetime.utcnow().date() - datetime.timedelta(days=1)).isoformat()
        msg = build(st, yday)
    if dry:
        print(msg)
    else:
        print("sent:", send(msg).get("ok"))


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
