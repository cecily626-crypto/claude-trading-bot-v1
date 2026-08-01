"""
v2.0-Short weekly strategy review -- 影子模式版 (rewritten 2026-08-01).

Strategy 2 (2.0空) is PAUSED (trading_control.json: strategy2_trading_enabled=
false) after a regime-filter backtest found no out-of-sample edge -- see
docs/PAUSE_AND_SHADOW_MODE.md for the full writeup.

No longer re-backtests a fresh rolling window. Reports the shadow ledger's
ACTUAL rolling 60d/90d performance (shadow_trades.csv, written every 5 minutes
by paper_bot_short.py regardless of the pause), plus a short real-account
summary (the 2 positions open at pause time winding down naturally, no new
opens since).

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Run: python weekly_review_short.py [--dry-run]
"""
import os
import sys
import csv
import json
import datetime
import urllib.request
import urllib.parse

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
HIST_FILE = os.path.join(os.path.dirname(__file__), "review_history_short.json")
CONTROL_FILE = os.path.join(os.path.dirname(__file__), "trading_control.json")
PAPER_FILE = os.path.join(os.path.dirname(__file__), "paper_account_short.json")
SHADOW_CSV = os.path.join(os.path.dirname(__file__), "shadow_trades.csv")
STRATEGY_KEY = "S2_short"
TAG = "【2.0空】"

RESUME_PF, RESUME_N = 1.2, 30


def load_shadow_closes(days):
    if not os.path.exists(SHADOW_CSV):
        return []
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    out = []
    with open(SHADOW_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("strategy") != STRATEGY_KEY or r.get("event") != "close":
                continue
            try:
                ts = datetime.datetime.fromisoformat(r["ts_utc"])
            except Exception:
                continue
            if ts < cutoff:
                continue
            try:
                out.append({"ret": float(r["pnl_pct"]), "pnl": float(r["pnl_usd"])})
            except Exception:
                continue
    return out


def pooled(rows):
    if not rows:
        return {"win": float("nan"), "trades": 0, "pf": float("nan"), "cum_pnl": 0.0}
    rets = [r["ret"] for r in rows]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    win = 100 * len(wins) / len(rets)
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99.0 if wins else float("nan"))
    return {"win": round(win, 1), "trades": len(rets),
            "pf": round(pf, 2) if pf == pf else pf,
            "cum_pnl": round(sum(r["pnl"] for r in rows), 2)}


def is_paused():
    if not os.path.exists(CONTROL_FILE):
        return False
    return not json.load(open(CONTROL_FILE)).get("strategy2_trading_enabled", True)


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


def fmt_group(label, g):
    if g["trades"] == 0:
        return f"*{label}*  交易 0 笔  <-- 样本不足,不可据此下结论"
    flag = "  <-- 样本不足(n<5),不可据此下结论" if g["trades"] < 5 else ""
    return (f"*{label}*  交易 {g['trades']} 笔 · 胜率 `{g['win']}%` · PF `{g['pf']}` · "
            f"累计假设盈亏 `{g['cum_pnl']:+.2f}`{flag}")


def build_message():
    d60 = pooled(load_shadow_closes(60))
    d90 = pooled(load_shadow_closes(90))
    paused = is_paused()
    pw_ = paper_week()

    L = [f"{TAG}📊 *每周做空策略复盘*（LBank · 4h · 影子模拟）", f"_{datetime.date.today().isoformat()}_", ""]
    if paused:
        L.append("⏸️ *当前策略已暂停（不开新仓，已有持仓按原规则自然离场）。以下为影子模拟持续演算的表现：*")
    else:
        L.append("_策略当前为正常交易状态，以下同时展示影子模拟表现供对照：_")
    L.append("")
    L.append(fmt_group("滚动60天", d60))
    L.append(fmt_group("滚动90天", d90))

    if pw_:
        L.append(f"\n*真实账户本周*{'（已暂停开仓）' if paused else ''}  开空 {pw_['opens']} / 平空 {pw_['closes']} 笔 · "
                 f"已实现 `{pw_['pnl']:+.2f}` · 净值 `${pw_['eq']:.2f}` "
                 f"({(pw_['eq']/pw_['start']-1)*100:+.1f}%) · 持仓 {pw_['pos']}")

    if paused:
        met = d90["trades"] >= RESUME_N and d90["pf"] == d90["pf"] and d90["pf"] > RESUME_PF
        L.append("")
        L.append(f"*恢复条件*：滚动90天影子PF > {RESUME_PF} 且交易 ≥ {RESUME_N} 笔，两者同时满足 -> "
                 f"当前 {'已达成 ✅（另有独立提醒，见 resume_watch.py）' if met else '未达成'}")
        L.append("_不使用ADX/EMA体制标签判断是否恢复 -- 2026-07-31回测发现这类标签4h/日线一致率仅47-52%，不够稳定。_")

    L.append("\n_影子模拟基于实时行情持续演算的假设交易，不代表已发生的真实交易；非投资建议。_")
    return "\n".join(L)


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
    msg = build_message()
    if dry:
        print(msg)
    else:
        print("sent:", send(msg).get("ok"))
    hist.append({"date": datetime.date.today().isoformat(),
                 "d60": pooled(load_shadow_closes(60)),
                 "d90": pooled(load_shadow_closes(90)),
                 "paused": is_paused()})
    json.dump(hist[-52:], open(HIST_FILE, "w"), indent=2)


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
