#!/usr/bin/env bash
# ============================================================
# Phase 1 VPS 一键部署脚本 (Ubuntu 24.04/26.04 LTS)
# 用法: 以 root 执行
#   bash setup_vps.sh
# 完成后需要你手动做两件事(脚本最后会提示):
#   1. 编辑 /etc/trading-bot.env 填入 Telegram token/chat id
#   2. 把打印出来的 deploy key 公钥加到 GitHub 仓库(允许写入)
# ============================================================
set -e

REPO_HTTPS="https://github.com/cecily626-crypto/claude-trading-bot-v1.git"
REPO_SSH="git@github.com:cecily626-crypto/claude-trading-bot-v1.git"
BASE=/opt/trading-bot

echo "==== [1/7] 连通性自测 ===================================="
fail=0
for url in \
  "https://api.lbkex.com/v2/currencyPairs.do" \
  "https://api.binance.com/api/v3/ping" \
  "https://api.telegram.org" \
  "https://github.com" ; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "$url" || echo 000)
  if [ "$code" = "000" ]; then
    echo "  ❌ FAIL  $url (无法连接)"
    fail=1
  else
    echo "  ✅ OK    $url (HTTP $code)"
  fi
done
if [ $fail -eq 1 ]; then
  echo "!! 有端点不可达，这台 VPS 不合格，停止部署。"
  exit 1
fi
echo "连通性全部通过。"

echo "==== [2/7] 安装依赖 ======================================"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip git ufw curl > /dev/null
pip3 install --quiet --break-system-packages pandas numpy

echo "==== [3/7] 拉取代码 ======================================"
mkdir -p "$BASE"
if [ ! -d "$BASE/repo/.git" ]; then
  git clone --quiet "$REPO_HTTPS" "$BASE/repo"
fi
git config --global user.name "vps-bot"
git config --global user.email "vps-bot@local"

echo "==== [4/7] 生成 GitHub deploy key (用于推送状态) ==========="
if [ ! -f "$BASE/deploy_key" ]; then
  ssh-keygen -t ed25519 -N "" -f "$BASE/deploy_key" -C "vps-trading-bot" -q
fi
cd "$BASE/repo"
git remote set-url origin "$REPO_SSH"
git config core.sshCommand "ssh -i $BASE/deploy_key -o StrictHostKeyChecking=accept-new"

echo "==== [5/7] 配置环境变量文件 ==============================="
if [ ! -f /etc/trading-bot.env ]; then
  cat > /etc/trading-bot.env << 'EOF'
# 必填: 与 GitHub Secrets 里相同的两个值
TELEGRAM_BOT_TOKEN=在这里填入token
TELEGRAM_CHAT_ID=在这里填入chatid
SIGNAL_KTYPE=hour4
EOF
  chmod 600 /etc/trading-bot.env
fi

echo "==== [6/7] 安装 systemd 定时任务 =========================="
install -m 755 "$BASE/repo/deploy/run_cycle.sh" "$BASE/run_cycle.sh"
install -m 755 "$BASE/repo/deploy/heartbeat.sh" "$BASE/heartbeat.sh"

cat > /etc/systemd/system/trading-bot.service << 'EOF'
[Unit]
Description=signal+paper trading cycle
After=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/trading-bot.env
ExecStart=/opt/trading-bot/run_cycle.sh
EOF

cat > /etc/systemd/system/trading-bot.timer << 'EOF'
[Unit]
Description=run trading cycle every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/bot-heartbeat.service << 'EOF'
[Unit]
Description=daily heartbeat to telegram

[Service]
Type=oneshot
EnvironmentFile=/etc/trading-bot.env
ExecStart=/opt/trading-bot/heartbeat.sh
EOF

cat > /etc/systemd/system/bot-heartbeat.timer << 'EOF'
[Unit]
Description=daily heartbeat 09:00 SGT (01:00 UTC)

[Timer]
OnCalendar=*-*-* 01:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now trading-bot.timer bot-heartbeat.timer > /dev/null 2>&1

echo "==== [7/7] 基础安全加固 ==================================="
ufw allow OpenSSH > /dev/null
ufw --force enable > /dev/null
apt-get install -y -qq unattended-upgrades > /dev/null

echo ""
echo "============================================================"
echo "部署完成! 还差两步手动操作:"
echo ""
echo "① 编辑环境变量, 填入 Telegram token 和 chat id:"
echo "     nano /etc/trading-bot.env"
echo ""
echo "② 把下面这行公钥加到 GitHub:"
echo "   仓库 Settings -> Deploy keys -> Add deploy key"
echo "   勾选 'Allow write access'"
echo ""
cat "$BASE/deploy_key.pub"
echo ""
echo "都做完后, 手动跑一次验证:"
echo "     systemctl start trading-bot.service"
echo "     journalctl -u trading-bot.service -n 50 --no-pager"
echo "============================================================"
