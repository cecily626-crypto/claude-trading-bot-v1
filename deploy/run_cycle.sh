#!/usr/bin/env bash
# 每 5 分钟一轮: git pull -> signal_bot -> paper_bot -> paper_bot_short -> 推送状态
# 连续 3 次失败时发 Telegram 告警(只发一次, 恢复后自动复位)
set -u
BASE=/opt/trading-bot
REPO=$BASE/repo
FAILFILE=$BASE/failcount
LOCK=$BASE/cycle.lock

# 防止上一轮还没跑完就叠加
exec 9> "$LOCK"
flock -n 9 || { echo "previous cycle still running, skip"; exit 0; }

cd "$REPO"
git pull --rebase --autostash --quiet || echo "[warn] git pull failed, continue with local copy"

ok=1
python3 signal_bot.py  || { echo "[error] signal_bot failed"; ok=0; }
python3 paper_bot.py   || { echo "[error] paper_bot failed";  ok=0; }
python3 paper_bot_short.py || { echo "[error] paper_bot_short failed"; ok=0; }

if [ $ok -eq 1 ]; then
  # 成功: 复位失败计数, 推送状态文件回 GitHub (供 daily/weekly review 读取)
  prev=$(cat "$FAILFILE" 2>/dev/null || echo 0)
  echo 0 > "$FAILFILE"
  if [ "$prev" -ge 3 ]; then
    curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d chat_id="${TELEGRAM_CHAT_ID}" \
      -d text="✅ VPS bot 已恢复正常运行" > /dev/null || true
  fi
  git add bot_state.json paper_account.json review_history.json paper_account_short.json review_history_short.json 2>/dev/null || true
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "vps state update" --quiet && git push --quiet \
      || echo "[warn] git push failed (检查 deploy key), 状态仅保存在本地"
  fi
else
  n=$(( $(cat "$FAILFILE" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$FAILFILE"
  if [ "$n" -eq 3 ]; then
    curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d chat_id="${TELEGRAM_CHAT_ID}" \
      -d text="⚠️ VPS bot 连续 ${n} 次运行失败! 登录服务器检查: journalctl -u trading-bot.service -n 100" > /dev/null || true
  fi
fi
