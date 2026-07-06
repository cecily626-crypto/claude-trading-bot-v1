#!/usr/bin/env bash
# 每日心跳: 报告存活状态 + 模拟盘净值摘要
set -u
BASE=/opt/trading-bot
REPO=$BASE/repo

eq=$(python3 - << 'EOF' 2>/dev/null || echo "N/A"
import json
d = json.load(open("/opt/trading-bot/repo/paper_account.json"))
eq = d["cash"] + sum(p["units"] * p["last_px"] for p in d["positions"].values())
print(f"${eq:.2f} ({(eq/d['start']-1)*100:+.1f}%) | 持仓{len(d['positions'])}个 | 已平仓{len(d['closed'])}笔")
EOF
)
last_run=$(systemctl show trading-bot.service -p ExecMainExitTimestamp --value 2>/dev/null || echo unknown)
fails=$(cat "$BASE/failcount" 2>/dev/null || echo 0)

curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d text="💓 VPS 心跳 | 模拟盘净值 ${eq} | 最近失败计数 ${fails} | 上次运行 ${last_run}" > /dev/null
