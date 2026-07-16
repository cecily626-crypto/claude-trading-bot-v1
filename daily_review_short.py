"""
v2.0-Short daily paper-account review -> Telegram. Runs with daily_review.py
at 00:00 UTC. Reads paper_account_short.json, read-only. Stdlib only.
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
STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_account_short.json")
TAG = "《做空2.0》"

# opt#4 滚动PF缩放参数 (镜像 paper_bot_short.py, 只读展示用)
PF_N, PF_LO, PF_HI, PF_MULT_LO, PF_WARM = 18, 0.9, 1.4, 0.25, 8


def _roll_pf(rets):
    wins = sum(r for r in rets if r > 0)
    losses = sum(r for r in rets if r <= 0)
    return (wins / abs(losses)) if losses != 0 else (9.0 if wins > 0 else 1.0)


def current_sizing(st):
    """当前 meme(S1) 仓位缩放系数与滚动PF; 热身中返回 (None, None)."""
    rets = [c["ret"] for c in st.get("closed", []) if c.get("why") == "s1"][-PF_N:]
    if len(rets) < PF_WARM:
        return None, None
    pf = _roll_pf(rets)
    mult = min(1.0, max(PF_MULT_LO, PF_MULT_LO + (pf - PF_LO) / (PF_HI - PF_LO) * (1.0 - PF_MULT_LO)))
    return mult, pf


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
    L = [f"{TAG}📄 *做空模拟盘 · 昨日复盘*（{yday} UTC）", ""]

    if closes:
        tot = sum(c["pnl"] for c in closes)
        wins = [c for c in closes if c["pnl"] > 0]
        best = max(closes, key=lambda c: c["pnl"]); worst = min(closes, key=lambda c: c["pnl"])
        L.append(f"*平空 {len(closes)} 笔*  合计盈亏 `{tot:+.2f}`  胜 {len(wins)}/负 {len(closes)-len(wins)}")
        L.append(f"  最好 {best['sym'].upper()} `{best['pnl']:+.2f}`（{best['ret']*100:+.1f}%）· "
                 f"最差 {worst['sym'].upper()} `{worst['pnl']:+.2f}`（{worst['ret']*100:+.1f}%）")
        for c in closes:
            L.append(f"  🔵 平空 {c['sym'].upper()} @ `{c['px']:.6g}`  `{c['pnl']:+.2f}` "
                     f"({c['ret']*100:+.1f}%) [{c.get('why','-')}]")
    else:
        L.append("*平空* 0 笔")

    if opens:
        L.append(f"\n*开空 {len(opens)} 笔*")
        for o in opens:
            sn = (f" ⚖️{o['smult']:.2f}×" if o.get("smult") is not None and o["smult"] < 0.999 else "")
            L.append(f"  🔴 开空 {o['sym'].upper()} @ `{o['px']:.6g}`  仓位 `${o['notional']:.0f}`{sn} "
                     f"[{o.get('why','-')}]")
    else:
        L.append("\n*开空* 0 笔")

    rets = [c["ret"] for c in st.get("closed", [])]
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    cum_win = (100 * len(wins) / len(rets)) if rets else float("nan")
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99 if wins else float("nan"))
    L.append(f"\n*账户* 净值 `${eq:.2f}` ({(eq/st['start']-1)*100:+.1f}%) · "
             f"持仓 {len(st.get('positions',{}))} 个 · 累计已实现 `${st.get('realized',0):+.2f}`")
    if rets:
        L.append(f"  累计 {len(rets)} 笔 · 胜率 {cum_win:.0f}% · 盈亏比 {pf:.2f}")
    smult, spf = current_sizing(st)
    if spf is None:
        L.append(f"  仓位缩放 满仓（热身中，需 {PF_WARM} 笔平仓；已 {len([c for c in st.get('closed',[]) if c.get('why')=='s1'])} 笔）")
    else:
        L.append(f"  仓位缩放 `{smult:.2f}×`（滚动PF {spf:.2f}，窗口{PF_N}｜冷{PF_LO}→{PF_MULT_LO}× 热{PF_HI}→满仓）")
    if st.get("fuse_until", "") > datetime.datetime.utcnow().isoformat():
        L.append(f"  ⛔ 熔断中，恢复时间 {st['fuse_until'][:16]} UTC")
    L.append("\n_虚拟账户 · 非投资建议_")
    return "\n".join(L)


def main(dry=False):
    if not os.path.exists(STATE_FILE):
        msg = f"{TAG}📄 做空模拟盘昨日复盘：账户尚未初始化。"
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
