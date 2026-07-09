"""
v2.0-Short paper-trading bot (虚拟做空账户).  Runs in the same VPS cycle as v1,
completely separate ledger: paper_account_short.json, starts at $2000.

Strategy: set by SHORT_MODE env (default filled in after backtest selection):
  "s1"   breakdown_short only
  "s2"   blowoff fade only
  "s1s2" both (independent signals; one position per symbol)
  "+ts"  suffix adds BTC/ETH trend-short (e.g. "s1s2+ts")

Execution mirror of v1 paper_bot: reconcile desired vs held per symbol at the
latest LBank price, taker fee + slippage, TG message for EVERY open/close with
【2.0空】 tag.  Delivery guaranteed: state saved BEFORE sending; failed sends go
to a pending queue and are re-sent next cycle with a (补发) prefix.

Risk: per-position cap 12% of equity (meme) / 40% (btc-eth), account fuse -3%
in a UTC day -> close all + pause 24h, daily snapshot report.

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, optional PAPER_START_SHORT,
     SHORT_MODE, SIGNAL_KTYPE.
Run: python paper_bot_short.py [--dry-run]
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
from strategy_short import breakdown_short, trend_short
from strategy_core import blowoff_short

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")
ANN = {"hour4": 365 * 6, "hour1": 365 * 24, "day1": 365}.get(KTYPE, 365 * 6)
START = float(os.environ.get("PAPER_START_SHORT", "2000"))
MODE = os.environ.get("SHORT_MODE", "s1+ts")   # backtest 2026-07-07: S1(bo55/仅止损) + BTC/ETH 趋势空
STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_account_short.json")
FEE, SLIP = 0.0002, 0.0005
TARGET_VOL = 0.5
MAX_FRAC = {"meme": 0.12, "trend": 0.40}
MIN_TICKET = 20.0
FUSE_DD = 0.03                       # -3% intraday -> fuse
TAG = "【2.0空】"

# Backtest winner (2026-07-07, LBank 4h, 34 meme + btc/eth):
#   S1b+仅止损出场: n=400 win=43.8% PF=1.87 avg=+2.41%  (H1 2.78 / H2 0.88)
S1_KW = {"breakout": 55}                 # regime=100, gap=0.03, stop_mult=2.5 defaults
S1_STOP_EXIT_ONLY = True                 # only the ATR trailing stop closes a position
S2_KW = {}                               # S2 blowoff fade: rejected (PF 0.85), not used


# ------------------------------- state --------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"cash": START, "start": START, "positions": {}, "realized": 0.0,
            "closed": [], "log": [], "pending_msgs": [], "last_report": "",
            "day_anchor": {}, "fuse_until": "", "inited": False}


def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), indent=2)


def _logev(state, **kw):
    kw["ts"] = datetime.datetime.utcnow().isoformat()
    state.setdefault("log", []).append(kw)
    state["log"] = state["log"][-800:]


# ------------------------------ telegram ------------------------------------
def _send_raw(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode()).get("ok", False)


def send_guaranteed(state, text, dry=False):
    """State is already saved by caller. Retry 3x; on failure queue for next cycle."""
    if dry:
        print(text)
        return True
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    for _ in range(3):
        try:
            if _send_raw(text):
                return True
        except Exception as e:
            print(f"[warn] tg send failed: {e}")
        time.sleep(2)
    state.setdefault("pending_msgs", []).append(text)
    state["pending_msgs"] = state["pending_msgs"][-20:]
    save_state(state)
    return False


# --------------------------- strategy evaluation ----------------------------
def eval_s1(df):
    """Walk the breakdown_short state machine over closed bars -> current view."""
    sig = breakdown_short(df, **S1_KW)
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    n = len(df)
    dir_ = 0; entry = stop = extreme = 0.0; locked = 0; pending = None
    for i in range(n):
        if pending is not None and pending != dir_:
            if pending != 0:
                entry = o[i]; dir_ = pending
                extreme = l[i]
                stop = entry + mult * atr_a[i]
            else:
                dir_ = 0
            pending = None
        if dir_ < 0:
            if h[i] >= stop:
                dir_ = 0; locked = -1
            else:
                extreme = min(extreme, l[i]); stop = min(stop, extreme + mult * atr_a[i])
        des = int(target[i])
        if locked != 0:
            des = 0 if des == locked else (locked := 0) or des
        if des != dir_:
            if dir_ == 0 or not S1_STOP_EXIT_ONLY:
                pending = des
    return {"dir": int(dir_), "why": "s1", "price": float(c[-1]),
            "stop": float(stop) if dir_ else None,
            "atr": float(atr_a[-1]), "atr_pct": float(sig["atr_pct"][-1])}


def eval_s2(df):
    """Walk blowoff-fade over closed bars -> open fade position (if any)."""
    sig = blowoff_short(df, **S2_KW)
    entry_sig, atr_a = sig["entry"], sig["atr"]
    tp, stop_atr, max_hold = sig["tp"], sig["stop_atr"], sig["max_hold"]
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    n = len(df)
    pos = False; pending = False
    entry = stop = tp_px = 0.0; i0 = 0
    for i in range(n):
        if pending and not pos:
            entry = o[i]; i0 = i
            stop = entry + stop_atr * atr_a[i - 1]
            tp_px = entry * (1 - tp)
            pos = True; pending = False
        if pos and i >= i0:
            if h[i] >= stop or l[i] <= tp_px or i - i0 >= max_hold:
                pos = False
        if not pos and i < n - 1 and entry_sig[i] == -1:
            pending = True
    return {"dir": -1 if pos else 0, "why": "s2", "price": float(c[-1]),
            "stop": float(stop) if pos else None, "tp": float(tp_px) if pos else None,
            "deadline": int(i0 + max_hold - (n - 1)) if pos else None,   # bars left
            "atr": float(atr_a[-1]), "atr_pct": float(atr_a[-1] / c[-1])}


def evaluate_short(df, kind):
    """Merge enabled strategies -> single desired view per symbol (short/flat)."""
    if kind == "trend":
        sig = trend_short(df)
        # reuse eval_s1's machinery by mimicking its structure
        target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
        o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
        dir_ = 0; stop = 0.0; extreme = 0.0; locked = 0; pending = None
        for i in range(len(df)):
            if pending is not None and pending != dir_:
                if pending != 0:
                    dir_ = pending; extreme = l[i]; stop = o[i] + mult * atr_a[i]
                else:
                    dir_ = 0
                pending = None
            if dir_ < 0:
                if h[i] >= stop:
                    dir_ = 0; locked = -1
                else:
                    extreme = min(extreme, l[i]); stop = min(stop, extreme + mult * atr_a[i])
            des = int(target[i])
            if locked != 0:
                des = 0 if des == locked else (locked := 0) or des
            if des != dir_:
                pending = des
        return {"dir": int(dir_), "why": "ts", "price": float(c[-1]),
                "stop": float(stop) if dir_ else None,
                "atr": float(atr_a[-1]), "atr_pct": float(sig["atr_pct"][-1])}
    views = []
    if "s1" in MODE:
        views.append(eval_s1(df))
    if "s2" in MODE:
        views.append(eval_s2(df))
    active = [v for v in views if v["dir"] != 0]
    return active[0] if active else views[0] if views else {"dir": 0, "why": "-",
                                                            "price": float(df['close'].iloc[-1]),
                                                            "stop": None, "atr": 0.0, "atr_pct": 0.02}


# ------------------------------- account ------------------------------------
def equity_of(state):
    eq = state["cash"]
    for p in state["positions"].values():
        eq += p["units"] * p["last_px"]
    return eq


def weight(kind, atr_pct):
    av = (atr_pct if atr_pct > 0 else 0.02) * np.sqrt(ANN)
    return float(np.clip(TARGET_VOL / av, 0.05, MAX_FRAC[kind]))


def close_pos(st, coin, px, why, fills):
    held = st["positions"].pop(coin)
    pnl = held["units"] * (px - held["entry"])
    st["cash"] += held["units"] * px - abs(held["units"]) * px * (FEE + SLIP)
    ret = (px / held["entry"] - 1) * held["dir"]
    st["realized"] += pnl
    st["closed"].append({"sym": coin, "dir": held["dir"], "ret": ret, "pnl": pnl, "why": why,
                         "entry": held["entry"], "exit": px,
                         "in": abs(held["units"]) * held["entry"], "out": abs(held["units"]) * px,
                         "ts": datetime.datetime.utcnow().isoformat()})
    _logev(st, ev="close", sym=coin, dir=held["dir"], px=px, pnl=round(pnl, 2),
           ret=round(ret, 4), why=why)
    fills.append(f"{TAG}🔵 平空 *{coin.upper()}* @ `{px:.6g}`  盈亏 `{pnl:+.2f}` "
                 f"({ret*100:+.1f}%) [{why}]")


def run(dry_run=False):
    st = load_state()
    now = datetime.datetime.utcnow()
    today = now.date().isoformat()

    # resend queue from previous failed cycles
    pending = st.get("pending_msgs", [])
    if pending and not dry_run:
        st["pending_msgs"] = []
        save_state(st)
        for m in pending:
            send_guaranteed(st, "(补发) " + m)

    universe = [("meme", c) for c in MEMECOINS]
    if "+ts" in MODE:
        universe += [("trend", c) for c in TREND_COINS]

    fused = st.get("fuse_until", "") and now.isoformat() < st["fuse_until"]
    fills = []
    for kind, coin in universe:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) < 220:
                continue
            ev = evaluate_short(df, kind)
            px = ev["price"]
            held = st["positions"].get(coin)
            if held:
                held["last_px"] = px
            desired = 0 if fused else ev["dir"]
            held_dir = held["dir"] if held else 0

            if desired != held_dir:
                if held_dir != 0:
                    close_pos(st, coin, px, "fuse" if fused else ev["why"], fills)
                if desired != 0:
                    eq = equity_of(st)
                    gross = sum(abs(p["units"]) * p["last_px"] for p in st["positions"].values())
                    notional = min(eq * weight(kind, ev["atr_pct"]), max(eq - gross, 0))
                    if notional >= MIN_TICKET:
                        units = desired * notional / px
                        st["cash"] -= units * px + abs(units) * px * (FEE + SLIP)
                        st["positions"][coin] = {"dir": desired, "units": units, "entry": px,
                                                 "stop": ev["stop"], "tp": ev.get("tp"),
                                                 "why": ev["why"], "last_px": px}
                        _logev(st, ev="open", sym=coin, dir=desired, px=px,
                               notional=round(notional, 2), why=ev["why"])
                        fills.append(f"{TAG}🔴 开空 *{coin.upper()}* @ `{px:.6g}`  "
                                     f"仓位 `${notional:.0f}` ({notional/eq*100:.0f}%)  "
                                     f"止损 `{ev['stop']:.6g}`"
                                     + (f"  止盈 `{ev['tp']:.6g}`" if ev.get("tp") else "")
                                     + f" [{ev['why']}]")
            elif held:
                held["stop"] = ev["stop"] if ev["stop"] else held["stop"]
            time.sleep(0.2)
        except Exception as e:
            print(f"[warn] {coin}: {e}")

    # ---- account fuse: -3% within the UTC day -> flat all + pause 24h ------
    eq = equity_of(st)
    anchor = st.setdefault("day_anchor", {})
    if anchor.get("date") != today:
        anchor.update({"date": today, "eq": eq})
    if not fused and anchor["eq"] > 0 and eq / anchor["eq"] - 1 <= -FUSE_DD:
        for coin in list(st["positions"]):
            close_pos(st, coin, st["positions"][coin]["last_px"], "fuse", fills)
        st["fuse_until"] = (now + datetime.timedelta(hours=24)).isoformat()
        fills.append(f"{TAG}⛔ *熔断*：单日回撤超 {FUSE_DD*100:.0f}%，已全部平仓，暂停开仓 24h")
        eq = equity_of(st)

    # ---- messages -----------------------------------------------------------
    msgs = []
    if not st["inited"]:
        msgs.append(f"{TAG}📄 *做空模拟盘已启动*  初始资金 `${st['start']:.0f}` USDT"
                    f"（LBank · 4h · 只做空 · 模式 {MODE} · 虚拟下单，不碰真钱）")
        st["inited"] = True
    msgs += fills
    if today != st.get("last_report"):
        rets = [c["ret"] for c in st["closed"]]
        wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
        win = 100 * len(wins) / len(rets) if rets else float("nan")
        pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99 if wins else float("nan"))
        rep = [f"{TAG}📄 *做空模拟盘日报*\n  净值 `${eq:.2f}` ({(eq/st['start']-1)*100:+.1f}%)"
               f"  ·  持仓 {len(st['positions'])} 个\n  累计已实现 `${st['realized']:+.2f}`"
               f"  ·  已平仓 {len(rets)} 笔"
               + (f"  ·  胜率 {win:.0f}%  盈亏比 {pf:.2f}" if rets else "")]
        day_closes = [c for c in st["closed"] if str(c.get("ts", ""))[:10] == today]
        if day_closes:
            tot = sum(c["pnl"] for c in day_closes)
            rep.append(f"  *今日平空 {len(day_closes)} 笔*  合计 `{tot:+.2f}`")
            for c in day_closes:
                rep.append(f"   平空 {c['sym'].upper()}  "
                           f"入`${c.get('in', 0):.0f}`→出`${c.get('out', 0):.0f}`  "
                           f"`{c['pnl']:+.2f}` ({c['ret']*100:+.1f}%)")
        if st["positions"]:
            upnl = 0.0; plines = []
            for sym, p in st["positions"].items():
                u = p["units"] * (p["last_px"] - p["entry"]); upnl += u
                innot = abs(p["units"]) * p["entry"]; curval = abs(p["units"]) * p["last_px"]
                r = (p["last_px"] / p["entry"] - 1) * p["dir"]
                plines.append(f"   空 {sym.upper()}  入`${innot:.0f}`现`${curval:.0f}`  `{u:+.2f}` ({r*100:+.1f}%)")
            rep.append(f"  *当前持仓 {len(st['positions'])} 个*  浮盈亏合计 `{upnl:+.2f}`")
            rep.extend(plines)
        msgs.append("\n".join(rep))
        st["last_report"] = today

    save_state(st)                      # state FIRST, messages second
    if msgs:
        send_guaranteed(st, "\n\n".join(msgs) + "\n\n_虚拟账户·非投资建议_", dry=dry_run)
    else:
        print(f"no short-paper events (equity ${eq:.2f}, {len(st['positions'])} positions)")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
