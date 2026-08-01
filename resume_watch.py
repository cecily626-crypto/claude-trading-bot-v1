"""
resume_watch.py (added 2026-08-01) -- checks each paused strategy's shadow
rolling-90-day performance (from shadow_trades.csv, written by paper_bot.py /
paper_bot_short.py every cycle) against the pre-agreed resume bar:

    rolling 90-day PF > 1.2  AND  >= 30 shadow trades in that window

Both conditions must hold at once. This does NOT use ADX/EMA regime labels --
the 2026-07-31 backtest found 4h-vs-daily agreement on those labels is only
47-52%, too unstable to gate a resume decision on (see
docs/PAUSE_AND_SHADOW_MODE.md).

When the bar is met for a strategy that is still paused in trading_control.json,
this sends ONE Telegram alert (edge-triggered via resume_alert_state.json, so
it won't repeat every 5 minutes) and STOPS THERE -- it never flips the
*_trading_enabled flags itself. Resuming is always a manual edit + decision.

Run every cycle (added to run_cycle.sh, after paper_bot_short.py) so it always
sees the freshest shadow_trades.csv from the same cycle. Pure local CSV/JSON
analysis -- no network calls except the Telegram push itself.

ENV: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Run: python resume_watch.py [--dry-run]
"""
import os
import sys
import csv
import json
import datetime
import urllib.request
import urllib.parse

BASE = os.path.dirname(__file__)
CONTROL_FILE = os.path.join(BASE, "trading_control.json")
SHADOW_CSV = os.path.join(BASE, "shadow_trades.csv")
ALERT_STATE_FILE = os.path.join(BASE, "resume_alert_state.json")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PF_THRESHOLD = 1.2
MIN_TRADES = 30
WINDOW_DAYS = 90

STRATEGIES = {
    "S1_trend_breakout": {"control_key": "strategy1_trading_enabled", "tag": "《做多1.0策略》"},
    "S2_short": {"control_key": "strategy2_trading_enabled", "tag": "【2.0空】"},
}


def send(text):
    if not TOKEN or not CHAT_ID:
        print("[warn] no telegram creds, skip send")
        return {"ok": False}
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "parse_mode": "Markdown",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[warn] telegram send failed: {e}")
        return {"ok": False}


def load_shadow_rets(strategy, days):
    if not os.path.exists(SHADOW_CSV):
        return []
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    out = []
    with open(SHADOW_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("strategy") != strategy or r.get("event") != "close":
                continue
            try:
                ts = datetime.datetime.fromisoformat(r["ts_utc"])
            except Exception:
                continue
            if ts < cutoff:
                continue
            try:
                out.append(float(r["pnl_pct"]))
            except Exception:
                continue
    return out


def pf_of(rets):
    if not rets:
        return float("nan")
    wins = sum(r for r in rets if r > 0)
    losses = sum(r for r in rets if r <= 0)
    if losses == 0:
        return 99.0 if wins > 0 else float("nan")
    return wins / abs(losses)


def main(dry=False):
    if not os.path.exists(CONTROL_FILE):
        print("[resume_watch] no trading_control.json, nothing to check")
        return
    ctl = json.load(open(CONTROL_FILE))
    alert_state = json.load(open(ALERT_STATE_FILE)) if os.path.exists(ALERT_STATE_FILE) else {}

    for strat, meta in STRATEGIES.items():
        if ctl.get(meta["control_key"], True):
            # already live -- reset so a future pause+recovery cycle can alert again
            alert_state[strat] = {"alerted": False}
            print(f"[resume_watch] {strat}: live, skip")
            continue

        rets = load_shadow_rets(strat, WINDOW_DAYS)
        pf = pf_of(rets)
        n = len(rets)
        met = n >= MIN_TRADES and pf == pf and pf > PF_THRESHOLD
        prev = alert_state.get(strat, {"alerted": False})

        if met and not prev.get("alerted"):
            text = (f"{meta['tag']} 🔔 *恢复条件达成（仅提醒，不自动恢复）*\n"
                    f"  影子模拟滚动{WINDOW_DAYS}天：PF `{pf:.2f}` (阈值 >{PF_THRESHOLD}) · "
                    f"交易 {n} 笔 (阈值 ≥{MIN_TRADES})\n"
                    f"  是否恢复交易由你决定 -- 需要手动把 trading_control.json 里 "
                    f"`{meta['control_key']}` 改回 `true` 确认。")
            print("sent:" if not dry else "(dry) would send:", send(text).get("ok") if not dry else text)
            alert_state[strat] = {"alerted": True, "last_alert": datetime.datetime.utcnow().isoformat(),
                                  "pf": round(pf, 2), "n": n}
        elif not met and prev.get("alerted"):
            alert_state[strat] = {"alerted": False}   # condition lapsed -- allow re-alert if it recovers again
        else:
            alert_state[strat] = prev

        pf_str = f"{pf:.2f}" if pf == pf else "nan"
        print(f"[resume_watch] {strat}: n={n} pf={pf_str} met={met}")

    json.dump(alert_state, open(ALERT_STATE_FILE, "w"), indent=2)


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
