"""
Live market data from LBank (where you trade) + the memecoin universe.

LBank public kline API (no key needed):
  GET https://api.lbkex.com/v2/kline.do?symbol=doge_usdt&size=300&type=hour4&time=<start_sec>
  -> {"data": [[time, open, high, low, close, volume], ...]}  (ascending)
  NOTE: LBank row order is [time, OPEN, HIGH, LOW, CLOSE, vol]  (different from Coinbase!)
  Intraday candle types LBank supports: minute1/5/15/30, hour1, hour4, hour8, hour12, day1...
  (There is no 6h on LBank, so the live bot uses hour4 — the strategy logic is the
   same on any timeframe; only the bar size changes.)
"""
import time
import json
import urllib.request
import urllib.parse
import pandas as pd

LBANK_BASE = "https://api.lbkex.com/v2"
COLS = ["open", "high", "low", "close", "volume"]

# ---- memecoin universe -----------------------------------------------------
# A broad curated list of memecoin USDT pairs that exist on LBank. The breakout
# long/short strategy is applied to ALL of these (not just the backtested DOGE/PEPE).
# Add or remove freely — or set MEMECOINS = lbank_pairs(meme_only=True) to auto-pull.
#
# 2026-07-05 week-1 paper review: removed ultra-low-liquidity microcaps
# (udoge, shibdoge, caw, manyu, babyshark, kekius). UDOGE short alone lost
# -113.79 USDT (-116%) on a microcap squeeze. Re-adding any of them requires a
# separate liquidity check first.
MEMECOINS = [
    "doge", "shib", "pepe", "floki", "bonk", "wif", "mog", "brett", "popcat",
    "neiro", "pnut", "moodeng", "fartcoin", "mew", "dogs", "turbo", "memecoin",
    "baby", "elon", "wojak", "bobo", "snek", "troll", "gork", "useless",
    "spx", "giga", "ban", "chillguy", "apepe", "hippo", "goatseus",
    "pengu", "mubarak", "labubu",
]
# Large caps that use the TREND long/short strategy instead.
TREND_COINS = ["btc", "eth"]

# keywords that usually indicate a NON-memecoin (filter these out of auto-discovery)
_EXCLUDE = ("3l_", "3s_", "5l_", "5s_", "on_usdt", "x_usdt", "_usdc", "_usde",
            "_usd1", "_btc", "_eth", "_vusd", "usd_", "3l", "3s")


def _sym(coin: str, quote: str = "usdt") -> str:
    return coin.lower() if "_" in coin else f"{coin.lower()}_{quote}"


def fetch_klines(coin: str, ktype: str = "hour4", size: int = 300, quote: str = "usdt") -> pd.DataFrame:
    """Return an OHLCV DataFrame (UTC index, ascending) for a coin from LBank."""
    symbol = _sym(coin, quote)
    start = int(time.time()) - size * _seconds(ktype)
    q = urllib.parse.urlencode({"symbol": symbol, "size": size, "type": ktype, "time": start})
    url = f"{LBANK_BASE}/kline.do?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "lbank-signal-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.loads(r.read().decode())
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError(f"LBank returned no data for {symbol}: {payload.get('msg')}")
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("time").sort_values("time")
    df["date"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("date")[COLS].astype(float)


def _seconds(ktype: str) -> int:
    table = {"minute1": 60, "minute5": 300, "minute15": 900, "minute30": 1800,
             "hour1": 3600, "hour4": 14400, "hour8": 28800, "hour12": 43200, "day1": 86400}
    return table.get(ktype, 14400)


def lbank_pairs(meme_only: bool = False):
    """Fetch every trading pair on LBank. If meme_only, best-effort filter to *_usdt
    spot pairs excluding leveraged/stock/forex tokens (still curate the result)."""
    url = f"{LBANK_BASE}/currencyPairs.do"
    with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
        pairs = json.loads(r.read().decode()).get("data", [])
    if not meme_only:
        return pairs
    out = []
    for p in pairs:
        if not p.endswith("_usdt"):
            continue
        if any(x in p for x in _EXCLUDE):
            continue
        out.append(p)
    return out


if __name__ == "__main__":
    for c in ("btc", "doge", "pepe", "wif"):
        d = fetch_klines(c)
        print(c, len(d), "bars, last", d["close"].iloc[-1], "@", d.index[-1])
        time.sleep(0.3)
