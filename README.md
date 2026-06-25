# 加密信号机器人 · 零基础上手指南

这份指南假设你**完全不会编程**。照着一步步点就行，全程在网页上操作，不需要在自己电脑上装任何东西。

机器人会：每 30 分钟看一次 LBank 行情，**只在出现买/卖/做空/平仓信号时**给你的 Telegram 发消息。平时安静，不刷屏。

全程大约 **20 分钟**。建议用电脑（不是手机）操作。

---

## 总览：你要做 4 件事

1. **建一个 Telegram 机器人**，拿到两串密码（Token 和 Chat ID）
2. **注册 GitHub**，把这个文件夹里的文件传上去
3. **把两串密码填进 GitHub 的保险箱（Secrets）**
4. **开启自动运行**，测试一次，确认手机能收到消息

---

# 第一步：建 Telegram 机器人，拿两串密码

### 1.1 拿到 Token（机器人的钥匙）

1. 打开 Telegram，搜索框输入 **`@BotFather`**，点开那个带蓝色对勾的官方账号。
2. 点 **Start**（开始）。
3. 发送：**`/newbot`**
4. 它问机器人名字，随便起一个，比如：`我的交易信号`
5. 它再问用户名，必须以 **bot** 结尾，比如：`my_signal_2025_bot`（如果重名就换一个）
6. 成功后它会给你一段话，里面有一行像这样的密码：

   ```
   123456789:AAE_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

   **把这一整行复制下来，存到记事本。这就是 Token。**

### 1.2 拿到 Chat ID（你的聊天地址）

1. 在 Telegram 搜索 **`@userinfobot`**，点开，点 **Start**。
2. 它会立刻回你一段信息，里面有一行 **`Id: 123456789`**。
3. **把那串数字复制下来（只要数字）。这就是 Chat ID。**

> 现在你手上应该有两样东西：
> - **Token**：`123456789:AAE_xxxx...`
> - **Chat ID**：`123456789`

### 1.3 让你的机器人能给你发消息（重要！）

在 Telegram 搜索你刚建的机器人（用你起的用户名，比如 `my_signal_2025_bot`），点开，点 **Start**，随便发一句 `hi`。
（不做这一步，机器人无权给你发消息。）

---

# 第二步：注册 GitHub 并上传文件

GitHub 是个免费的代码网站，我们用它来 24 小时帮你跑机器人，你电脑可以关机。

### 2.1 注册

1. 打开 https://github.com ，点右上角 **Sign up**，用邮箱注册，按提示完成验证。

### 2.2 新建一个仓库（repository）

1. 登录后，点右上角 **加号 ➕ → New repository**。
2. **Repository name**（仓库名）：随便填，比如 `signal-bot`。
3. 选 **Public（公开）** ✅
   —— 重要：选 Public，自动运行的额度才是**无限免费**的。
   （别担心隐私：你的两串密码不放在文件里，而是放在下一步的“保险箱”里，别人看不到。）
4. 其它都不用动，点最下面绿色 **Create repository**。

### 2.3 上传文件

你会看到一个几乎空白的页面，上面有一行链接 **uploading an existing file**，点它。
（或者点 **Add file → Upload files**。）

把本文件夹里的这 **5 个文件**拖进去上传：

- `signal_bot.py`
- `exchange_data.py`
- `strategy_core.py`
- `requirements.txt`
- `README.md`（就是本文件，可传可不传）

拖好后，点页面下方绿色 **Commit changes**（提交）。

### 2.4 单独创建“自动运行”的配置文件

这个文件在一个特殊的隐藏文件夹里，拖拽容易丢，所以我们手动建：

1. 在仓库主页点 **Add file → Create new file**。
2. 最上方“文件名”输入框里，**完整粘贴这一行**（中间的斜杠会自动变成文件夹）：

   ```
   .github/workflows/bot.yml
   ```

3. 下面的大空白框里，把本文件夹中 `bot.yml` 文件的**全部内容**复制粘贴进去。
   （`bot.yml` 在 `.github/workflows/` 子文件夹里；如果你看不到这个隐藏文件夹，直接用下面“附录”里的内容复制即可。）
4. 点右上角绿色 **Commit changes**。

---

# 第三步：把两串密码放进保险箱（Secrets）

1. 在仓库页面点上方 **Settings（设置）**。
2. 左侧菜单找到 **Secrets and variables → Actions**，点它。
3. 点右边绿色 **New repository secret**，建第一个：
   - **Name** 填：`TELEGRAM_BOT_TOKEN`
   - **Secret** 填：你的 Token（`123456789:AAE_xxxx...` 那一整行）
   - 点 **Add secret**
4. 再点一次 **New repository secret**，建第二个：
   - **Name** 填：`TELEGRAM_CHAT_ID`
   - **Secret** 填：你的 Chat ID（那串数字）
   - 点 **Add secret**

> 名字必须一字不差地写成 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`（全大写、用下划线）。

---

# 第四步：开启自动运行并测试

### 4.1 开启 Actions

1. 仓库上方点 **Actions**。
2. 如果出现绿色按钮 **I understand my workflows, enable them**，点一下。
3. 左侧会看到 **signal-bot**，点它。

### 4.2 手动跑一次测试

1. 右边出现 **Run workflow** 按钮（灰色下拉），点开它，再点绿色 **Run workflow**。
2. 等约 1 分钟，刷新页面，会出现一条运行记录。
3. 点进去看，如果步骤旁边都是**绿色对勾 ✅**，说明跑通了。

### 4.3 怎么算成功？

- 点开运行记录里的 **“运行机器人”** 这一步，能看到日志。
  - 如果显示 `sent: True (N alerts)` → 它给你发消息了，去 Telegram 查收。
  - 如果显示 `no new triggers` → **也是正常的！** 说明此刻没有任何币触发买卖条件，机器人按设计保持安静。等行情出现信号时，它会自动发。
- 之后它会**每 30 分钟自动跑一次**，你什么都不用管。

---

# 常见问题

**Q：手机一直没收到消息，是不是坏了？**
A：不一定。机器人**只在有买/卖信号时**才发。日志里若是 `no new triggers` 就属正常。想确认通道没问题，可以临时把监控的币改少、或等一次明显行情。也务必确认你做了 **1.3** 那一步（给机器人发过 `hi`）。

**Q：运行那步是红叉 ❌？**
A：点开看日志最后几行红字：
- 写着 `Set TELEGRAM_BOT_TOKEN...` → 第三步的 Secret 名字拼错了，回去检查。
- 写着某个币 `no data` → 个别币 LBank 没有，跳过即可，不影响其它币。

**Q：我想监控“全部 memecoin 币对”怎么办？**
A：打开仓库里的 `.github/workflows/bot.yml`（点文件 → 右上角铅笔图标编辑），把 `SIGNAL_MEME_ALL: "false"` 改成 `"true"`，提交。
（注意：币越多每次跑得越久。）

**Q：我想增减监控的币？**
A：编辑 `exchange_data.py`，里面有一行 `MEMECOINS = [ ... ]`，按格式加引号加逗号增删即可。

**Q：想暂停机器人？**
A：Actions 页面 → 右上 **`...` → Disable workflow**。想恢复就 Enable。

**Q：嫌 30 分钟太频繁？**
A：编辑 `bot.yml`，把 `*/30 * * * *` 改成 `0 * * * *`（每小时）。

---

# 一定要知道的几点

- 机器人**只发信号，不会自动下单、不碰你的钱**。买不买、买多少，都由你本人在 LBank 手动操作。
- 信号来自历史回测的策略，**过往表现不代表未来收益**。加密货币（尤其 memecoin）波动极大、可能归零，请只用你能承受全部损失的闲钱。
- GitHub 的定时偶尔会延迟几分钟，属正常现象。

---

## 附录：`bot.yml` 的内容

如果你在文件夹里找不到隐藏的 `.github/workflows/bot.yml`，第二步 2.4 里要粘贴的就是它，内容见本仓库该文件。它的作用就是告诉 GitHub“每 30 分钟运行一次机器人”。
