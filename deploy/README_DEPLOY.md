# Phase 1 VPS 部署指南

目标：把 signal-bot 和 paper-account 的调度从 GitHub Actions（延迟 0.5~5 小时不定）迁到 VPS（每 5 分钟确定运行），并加上每日心跳和连续失败告警。daily-review / weekly-review / 回测暂时留在 GitHub Actions。

## 部署步骤（SSH 登录 VPS 后执行）

```bash
# 1. 下载并执行部署脚本（自动做连通性自测，不合格会中止）
curl -sO https://raw.githubusercontent.com/cecily626-crypto/claude-trading-bot-v1/main/deploy/setup_vps.sh
bash setup_vps.sh

# 2. 填入 Telegram 凭据（与 GitHub Secrets 里相同的两个值）
nano /etc/trading-bot.env

# 3. 把脚本最后打印的公钥添加到 GitHub：
#    仓库 Settings -> Deploy keys -> Add deploy key -> 勾选 Allow write access

# 4. 手动跑一次验证
systemctl start trading-bot.service
journalctl -u trading-bot.service -n 50 --no-pager
```

## 部署后架构

- `trading-bot.timer`：每 5 分钟 → git pull → signal_bot.py → paper_bot.py → 状态推回 GitHub
- `bot-heartbeat.timer`：每日 09:00 新加坡时间发 Telegram 心跳（净值摘要 + 失败计数）
- 连续 3 次运行失败 → Telegram 告警；恢复后自动发恢复通知
- 防叠加锁：上一轮未结束时跳过本轮
- 状态文件（bot_state/paper_account/review_history）持续推回 GitHub，daily/weekly review 无缝读取

## 切换（VPS 稳定运行 1-2 天后执行）

GitHub Actions 的 main.yml 和 paper.yml 中删除 `schedule:` 段（保留 workflow_dispatch 作手动备用），避免双跑导致重复消息和状态冲突。

## 常用命令

```bash
systemctl list-timers | grep -E "trading|heartbeat"   # 看定时器
journalctl -u trading-bot.service -f                   # 实时日志
systemctl start trading-bot.service                    # 手动跑一轮
cat /opt/trading-bot/failcount                         # 失败计数
```

## 安全边界

- 本阶段只跑信号和模拟盘，服务器上没有任何交易所 API key
- /etc/trading-bot.env 权限 600，只存 Telegram 凭据
- ufw 只开 SSH；unattended-upgrades 自动补安全补丁
- deploy key 只对这一个仓库有效
