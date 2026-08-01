#!/usr/bin/env bash
# 每 5 分钟一轮: git pull -> signal_bot -> paper_bot -> paper_bot_short -> resume_watch -> 推送状态
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
# 2026-08-01: 影子模式恢复条件检查 (只读 shadow_trades.csv + 推送提醒, 不影响交易结果本身,
# 单独 || true 处理: 就算它失败也不该拖垮整轮的 ok 状态)
python3 resume_watch.py || echo "[warn] resume_watch failed (non-fatal)"

# 备份状态回 GitHub: 每轮都做(与 bot 成败解耦); 逐个 add, 缺失文件自动跳过
# 2026-08-01: 新增 trading_control.json(总开关) + shadow_account*.json/shadow_trades.csv
# (影子模拟状态) + resume_alert_state.json(恢复提醒去重), 否则 GitHub Actions 里跑的
# weekly_review.py 看不到最新的影子交易记录。
for f in bot_state.json paper_account.json paper_account_short.json review_history.json \
         review_history_short.json trading_control.json shadow_account.json \
         shadow_account_short.json shadow_trades.csv resume_alert_state.json; do
  git add "$f" 2>/dev/null
done
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "vps state update" --quiet && git push --quiet \
    || echo "[warn] git push failed, 状态仅保存在本地"
fi

# 失败计数 / 告警
if [ $ok -eq 1 ]; then
  prev=$(cat "$FAILFILE" 2>/dev/null || echo 0)
  echo 0 > "$FAILFILE"
  if [ "$prev" -ge 3 ]; then
    curl -s -m 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d chat_id="${TELEGRAM_CHAT_ID}" \
      -d text="✅ VPS bot 已恢复正常运行" > /dev/null || true
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
