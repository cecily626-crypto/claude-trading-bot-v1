"""
Paper-trading (虚拟账户) forward-test.  Runs on the SAME schedule as the signal bot.

It does NOT touch any exchange or real money. It mirrors the live strategy's
current position per symbol (from evaluate()), "fills" virtual orders at the latest
LBank price, applies LBank taker fee + slippage, tracks an account that starts at
START_EQUITY USDT, and reports fills + a once-a-day equity snapshot to Telegram.

State persists in paper_account.json (committed back by the workflow).

2026-07-05 (week-1 review): added HARD STOP + loss circuit breaker — the stored
stop is now enforced on every run, and any position whose unrealized loss exceeds
MAX_POS_LOSS of its entry notional is force-closed. Before this, stops were only
implied by the 4h state machine and a UDOGE short ran to -116% unchecked.

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, optional PAPER_START (default 2000).
Run: python paper_bot.py --dry-run   (prints, sends nothing)
     python paper_bot.py
"""
import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import numpy as np

from exchange_data import fetch_klines, MEMECOINS, TREND_COINS
from signal_bot import evaluate  # reuse the exact long/short state machine

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
ANN = {"hour4": 365 * 6, "hour1": 365 * 24, "day1": 365}.get(KTYPE, 365 * 6)
START = float(os.environ.get("PAPER_START", "2000"))
STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_account.json")
FEE, SLIP = 0.0002, 0.0005                       # LBank taker 0.02% + slippage
TARGET_VOL = {"trend": 0.6, "breakout": 0.5}
MAX_FRAC = {"trend": 0.40, "breakout": 0.12}     # cap per position (% of equity)
MIN_TICKET = 20.0                                # don't bother below $20
MAX_POS_LOSS = 0.15                              # circuit breaker: force-close at -15% of entry notional
DIRTXT = {1: "多", -1: "空"}


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"cash": START, "start": START, "positions": {}, "realized": 0.0,
            "closed": [], "log": [], "last_report": "", "inited": False}


def _logev(state, **kw):
    kw["ts"] = datetime.datetime.utcnow().isoformat()
    state.setdefault("log", []).append(kw)
    state["log"] = state["log"][-800:]      # keep it bounded


def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), indent=2)


def weight(kind, atr_pct):
    av = (atr_pct if atr_pct > 0 else 0.02) * np.sqrt(ANN)
    return float(np.clip(TARGET_VOL[kind] / av, 0.05, MAX_FRAC[kind]))


def equity_of(state):
    eq = state["cash"]
    for p in state["positions"].values():
        eq += p["units"] * p["last_px"]
    return eq


def run(dry_run=False):
    st = load_state()
    universe = [("trend", c) for c in TREND_COINS] + [("breakout", c) for c in MEMECOINS]
    fills = []
    # 1) refresh marks + reconcile each symbol against the strategy's current view
    for kind, coin in universe:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) < 120:
                continue
            ev = evaluate(df, kind)
            px = ev["price"]
            held = st["positions"].get(coin)
            held_dir = held["dir"] if held else 0
            desired = ev["dir"]
            if held:
                held["last_px"] = px                       # mark to market

            # --- HARD STOP + loss circuit breaker (2026-07-05 week-1 review) --
            # Enforce the stored stop against the live price on EVERY run instead
            # of waiting for the 4h state machine, and force-close any position
            # whose unrealized loss exceeds MAX_POS_LOSS of its entry notional
            # (UDOGE lesson: a microcap short ran -116% with no hard exit).
            # After a forced close we do NOT re-enter on the same run.
            if held:
                unreal = held["units"] * (px - held["entry"])
                entry_notional = abs(held["units"]) * held["entry"]
                stop_hit = (held_dir > 0 and px <= held["stop"]) or \
                           (held_dir < 0 and px >= held["stop"])
                fuse_hit = unreal <= -MAX_POS_LOSS * entry_notional
                if stop_hit or fuse_hit:
                    pnl = unreal
                    st["cash"] += held["units"] * px - abs(held["units"]) * px * (FEE + SLIP)
                    ret = (px / held["entry"] - 1) * held_dir
                    st["realized"] += pnl
                    st["closed"].append({"sym": coin, "dir": held_dir, "ret": ret, "pnl": pnl})
                    why = "硬止损" if stop_hit else f"熔断{MAX_POS_LOSS*100:.0f}%"
                    _logev(st, ev="close", sym=coin, dir=held_dir, px=px,
                           pnl=round(pnl, 2), ret=round(ret, 4), why=why)
                    fills.append(f"⛔ {why} 平{DIRTXT[held_dir]} *{coin.upper()}* @ `{px:.6g}`  "
                                 f"盈亏 `{pnl:+.2f}` ({ret*100:+.1f}%)")
                    st["positions"].pop(coin, None)
                    time.sleep(0.2)
                    continue

            eq = equity_of(st)

            if desired != held_dir:
                # close existing
                if held_dir != 0:
                    pnl = held["units"] * (px - held["entry"])
                    st["cash"] += held["units"] * px - abs(held["units"]) * px * (FEE + SLIP)
                    ret = (px / held["entry"] - 1) * held_dir
                    st["realized"] += pnl
                    st["closed"].append({"sym": coin, "dir": held_dir, "ret": ret, "pnl": pnl})
                    _logev(st, ev="close", sym=coin, dir=held_dir, px=px, pnl=round(pnl, 2), ret=round(ret, 4))
                    fills.append(f"🔵 平{DIRTXT[held_dir]} *{coin.upper()}* @ `{px:.6g}`  盈亏 `{pnl:+.2f}` ({ret*100:+.1f}%)")
                    st["positions"].pop(coin, None)
                # open new
                if desired != 0:
                    gross = sum(abs(p["units"]) * p["last_px"] for p in st["positions"].values())
                    notional = min(eq * weight(kind, ev["atr"] / px), max(eq - gross, 0))
                    if notional >= MIN_TICKET:
                        units = desired * notional / px
                        st["cash"] -= units * px + abs(units) * px * (FEE + SLIP)
                        st["positions"][coin] = {"dir": desired, "units": units, "entry": px,
                                                 "stop": ev["stop"], "last_px": px}
                        _logev(st, ev="open", sym=coin, dir=desired, px=px, notional=round(notional, 2))
                        side = "🟢 开多" if desired > 0 else "🔴 开空"
                        fills.append(f"{side} *{coin.upper()}* @ `{px:.6g}`  仓位 `${notional:.0f}` "
                                     f"({notional/eq*100:.0f}%)  止损 `{ev['stop']:.6g}`")
            elif held:                                      # same direction -> trail the stop
                held["stop"] = ev["stop"]
            time.sleep(0.2)
        except Exception as e:
            print(f"[warn] {coin}: {e}")

    # 2) compose message
    eq = equity_of(st)
    pnl_pct = eq / st["start"] - 1
    msgs = []
    if not st["inited"]:
        msgs.append(f"📄 *模拟盘已启动*  初始资金 `${st['start']:.0f}` USDT（LBank · 4h · 多空 · 虚拟下单，不碰真钱）")
        st["inited"] = True
    msgs += fills
    today = datetime.date.today().isoformat()
    if today != st.get("last_report"):                      # once-a-day snapshot
        rets = [c["ret"] for c in st["closed"]]
        wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
        win = 100 * len(wins) / len(rets) if rets else float("nan")
        pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99 if wins else float("nan"))
        msgs.append(
            f"📄 *模拟盘日报*\n  净值 `${eq:.2f}` ({pnl_pct*100:+.1f}%)  ·  持仓 {len(st['positions'])} 个\n"
            f"  累计已实现 `${st['realized']:+.2f}`  ·  已平仓 {len(rets)} 笔"
            + (f"  ·  胜率 {win:.0f}%  盈亏比 {pf:.2f}" if rets else ""))
        st["last_report"] = today

    if msgs:
        text = "\n\n".join(msgs) + "\n\n_虚拟账户·非投资建议_"
        if dry_run:
            print(text)
        else:
            print("sent:", send(text).get("ok"))
    else:
        print(f"no paper events (equity ${eq:.2f}, {len(st['positions'])} positions)")
    save_state(st)


def send(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
