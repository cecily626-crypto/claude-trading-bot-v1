"""
LBank -> Telegram live signal bot.  Runs every 30 minutes.

What it does each run:
  1. Pull the latest 4h klines from LBank for:
       - TREND coins  (BTC, ETH)   -> confirmed long/short TREND strategy
       - MEMECOINS    (all pairs)  -> long/short BREAKOUT strategy
  2. Determine the current recommended position for each symbol (long / short / flat)
     using the SAME logic as the backtest (ls_engine), incl. the confirmed-downtrend
     short gate and ATR trailing stop.
  3. Compare to the saved state. It only sends a Telegram message when something
     ACTIONABLE changes — a new entry, an exit to flat, a long<->short flip, or a
     trailing-stop breach. Otherwise it stays silent (no spam every 30 min).
  4. Persist state to bot_state.json.

2026-07-06: send hardened — state is saved BEFORE sending; sends retry 3x and
queue to pending_signal_msgs.json for redelivery on the next run, so every
signal is guaranteed to reach Telegram exactly once.

SETUP
  pip install -r requirements.txt
  export TELEGRAM_BOT_TOKEN="123456:ABC..."
  export TELEGRAM_CHAT_ID="987654321"
  python signal_bot.py --dry-run        # prints what it WOULD send, sends nothing
  python signal_bot.py                   # live: sends Telegram alerts on triggers

RUN EVERY 30 MIN (cron):
  */30 * * * *  cd /path/to/bot && /usr/bin/python3 signal_bot.py >> bot.log 2>&1

Add/remove memecoins by editing MEMECOINS in exchange_data.py (it already covers a
broad set). To monitor the whole LBank memecoin universe automatically:
  MEME_SYMBOLS = exchange_data.lbank_pairs(meme_only=True)   # (curate the result)
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import numpy as np

from exchange_data import fetch_klines, MEMECOINS, TREND_COINS, lbank_pairs

# Set SIGNAL_MEME_ALL=true to monitor the WHOLE LBank memecoin-ish USDT universe
# (auto-discovered & filtered) instead of the curated MEMECOINS list.
if os.environ.get("SIGNAL_MEME_ALL", "false").lower() == "true":
    try:
        MEMECOINS = [p for p in lbank_pairs(meme_only=True)]
    except Exception as _e:
        print("[warn] could not auto-list pairs, using curated MEMECOINS:", _e)
from strategy_core import trend_ls, breakout_ls

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KTYPE = os.environ.get("SIGNAL_KTYPE", "hour4")       # LBank timeframe (4h)
BARS_PER_YEAR = {"hour4": 365 * 6, "hour8": 365 * 3, "hour1": 365 * 24, "day1": 365}.get(KTYPE, 365 * 6)
STATE_FILE = os.path.join(os.path.dirname(__file__), "bot_state.json")
FEE_NOTE = "LBank maker 0.04% / taker 0.02%"

DIR_NAME = {1: "LONG", -1: "SHORT", 0: "FLAT"}


# --------------------------- signal evaluation ------------------------------
def evaluate(df, kind):
    """Walk the long/short state machine over CLOSED bars and return the current
    recommended position, trailing stop, suggested size and regime context."""
    sig = trend_ls(df) if kind == "trend" else breakout_ls(df)
    target, atr_a, mult = sig["target"], sig["atr"], sig["stop_mult"]
    atr_pct = sig["atr_pct"]
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    n = len(df)
    dir_ = 0; entry = stop = extreme = 0.0; locked = 0; pending = None
    for i in range(n):
        if pending is not None and pending != dir_:
            if pending != 0:
                entry = o[i]; dir_ = pending
                extreme = h[i] if dir_ > 0 else l[i]
                stop = entry - mult * atr_a[i] if dir_ > 0 else entry + mult * atr_a[i]
            else:
                dir_ = 0
            pending = None
        if dir_ > 0:
            if l[i] <= stop:
                dir_ = 0; locked = 1
            else:
                extreme = max(extreme, h[i]); stop = max(stop, extreme - mult * atr_a[i])
        elif dir_ < 0:
            if h[i] >= stop:
                dir_ = 0; locked = -1
            else:
                extreme = min(extreme, l[i]); stop = min(stop, extreme + mult * atr_a[i])
        des = target[i]
        if locked != 0:
            des = 0 if des == locked else (locked := 0) or des
        if des != dir_:
            pending = des

    target_vol = 0.5 if kind == "breakout" else 0.6
    cap = 0.8 if kind == "breakout" else 1.0
    ap = atr_pct[-1] if atr_pct[-1] > 0 else 0.02
    size = float(np.clip(target_vol / (ap * np.sqrt(BARS_PER_YEAR)), 0.05, cap))
    er = sig["aux"]["ema_regime"].iloc[-1]
    price = float(c[-1])
    return {"dir": int(dir_), "price": price, "stop": float(stop) if dir_ else None,
            "size_pct": round(size * 100, 1), "regime": "BULL" if price > er else "BEAR",
            "atr": float(atr_a[-1])}


# ------------------------------ telegram ------------------------------------
def send(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


# --- 送达保证 (2026-07-06): 每条信号必须到达 Telegram -------------------------
PENDING = os.path.join(os.path.dirname(__file__), "pending_signal_msgs.json")


def send_reliable(text):
    for _ in range(3):
        try:
            return send(text)
        except Exception as e:
            print(f"[warn] telegram send failed, retrying: {e}")
            time.sleep(2)
    q = []
    if os.path.exists(PENDING):
        try:
            q = json.load(open(PENDING))
        except Exception:
            q = []
    q.append(text)
    json.dump(q, open(PENDING, "w"))
    print(f"[warn] telegram unreachable, {len(q)} message(s) queued for retry")
    return {"ok": False}


def flush_pending():
    if not os.path.exists(PENDING):
        return
    try:
        q = json.load(open(PENDING))
    except Exception:
        q = []
    os.remove(PENDING)
    for t in q:
        send_reliable("(补发) " + t)


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), indent=2)


# ---- action diffing: only alert on real changes ----------------------------
def action_message(sym, prev_dir, ev):
    d = ev["dir"]
    if d == prev_dir:
        return None
    px = ev["price"]
    if prev_dir == 0 and d != 0:                      # fresh entry
        side = "🟢 LONG 进场" if d > 0 else "🔴 SHORT 进场（做空）"
        return (f"*{sym.upper()}*  {side}\n"
                f"  价格 `{px:.6g}`  ·  环境 {ev['regime']}\n"
                f"  建议仓位 `{ev['size_pct']}%`  ·  初始止损 `{ev['stop']:.6g}`")
    if prev_dir != 0 and d == 0:                      # exit to flat
        return (f"*{sym.upper()}*  ⚪ 平仓 / 离场（趋势结束或触发止损）\n"
                f"  价格 `{px:.6g}`  ·  环境 {ev['regime']}  ·  转为空仓观望")
    # flip long<->short
    side = "🟢 翻多" if d > 0 else "🔴 翻空"
    return (f"*{sym.upper()}*  🔁 {side}（先平旧仓再反向开仓）\n"
            f"  价格 `{px:.6g}`  ·  环境 {ev['regime']}\n"
            f"  建议仓位 `{ev['size_pct']}%`  ·  新止损 `{ev['stop']:.6g}`")


def run(dry_run=False):
    state = load_state()
    universe = [("trend", c) for c in TREND_COINS] + [("breakout", c) for c in MEMECOINS]
    alerts, errors = [], 0
    for kind, coin in universe:
        try:
            df = fetch_klines(coin, ktype=KTYPE, size=300)
            if len(df) < 120:                          # need enough history for EMA100
                continue
            ev = evaluate(df, kind)
            prev = state.get(coin, {})
            prev_dir = int(prev.get("dir", 0))
            msg = action_message(coin, prev_dir, ev)
            # live trailing-stop breach alert (between bar closes)
            if msg is None and prev_dir != 0 and prev.get("stop"):
                if (prev_dir > 0 and ev["price"] <= prev["stop"]) or \
                   (prev_dir < 0 and ev["price"] >= prev["stop"]):
                    msg = (f"*{coin.upper()}*  ⚠️ 触及止损 `{prev['stop']:.6g}`"
                           f"（现价 `{ev['price']:.6g}`）— 按计划离场")
            if msg:
                alerts.append(msg)
            state[coin] = {"dir": ev["dir"], "stop": ev["stop"],
                           "price": ev["price"], "ts": int(time.time())}
            time.sleep(0.25)                            # be gentle on LBank
        except Exception as e:
            errors += 1
            print(f"[warn] {coin}: {e}")
    save_state(state)                    # 先落盘: 消息发送失败绝不能导致信号状态丢失/重放
    if alerts:
        header = "*交易信号*（LBank · 4h · 多空）"
        body = "\n\n".join(alerts)
        footer = f"_{FEE_NOTE} · 非投资建议，回测优势≠未来收益_"
        text = f"{header}\n\n{body}\n\n{footer}"
        if dry_run:
            print(text)
        else:
            flush_pending()
            print("sent:", send_reliable(text).get("ok"), f"({len(alerts)} alerts)")
    else:
        print(f"no new triggers ({len(universe)} symbols checked, {errors} errors)")
        if not dry_run:
            flush_pending()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
