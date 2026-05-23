<p align="center">
  <img src="https://cdn.simpleicons.org/x/ffffff" width="72" alt="X logo">
</p>

<h1 align="center">xplus.skill</h1>

<p align="center">
  一个给 Codex 和其他本地 agent 用的 X/Twitter 浏览器监控 skill。
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">中文</a> ·
  <a href="SKILL.md">Skill</a>
</p>

---

xplus.skill 是一个用浏览器监控 X/Twitter 的小工具。

它可以做三件事：

1. 打开 X 首页或 X List。
2. 发现新帖子。
3. 把新帖子保存到本地文件，也可以推送到 Discord。

默认不需要 Discord。先让它把结果保存到本地，跑通以后再接 Discord。

## 适合谁

适合想让 Codex 或其他 agent 帮你盯 X 的人。

你不需要 X API。  
你也不一定需要安装 Google Chrome。  
如果没有 Chrome，它会使用 Playwright 自带的 Chromium。

## 第一步：安装

需要先安装 Python 3.10 或更新版本。

然后在项目目录里运行：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 第二步：创建运行目录

Windows：

```bash
mkdir .runtime
copy config.example.json .runtime\config.json
```

macOS / Linux：

```bash
mkdir -p .runtime
cp config.example.json .runtime/config.json
```

`.runtime` 是运行时目录。登录信息、状态、抓到的帖子都会放在这里。

## 第三步：改配置

打开：

```text
.runtime/config.json
```

最重要的是这几个：

```json
{
  "x_home_enabled": false,
  "x_list_enabled": true,
  "x_list_url": "https://x.com/i/lists/YOUR_LIST_ID",
  "output_sinks": ["jsonl"],
  "discord_enabled": false,
  "browser_channel": "auto"
}
```

如果你要监控首页，把 `x_home_enabled` 改成 `true`。

如果你要监控 List，把 `x_list_enabled` 改成 `true`，然后填好 `x_list_url`。

## 第四步：登录 X

运行：

```bash
python scripts/x_monitorplus_service.py --root .runtime open-profile
```

它会弹出一个浏览器窗口。

你要做的是：

1. 在这个窗口里登录 X。
2. 打开你要监控的首页或 List。
3. 确认页面能正常看到帖子。
4. 关闭这个浏览器窗口。

注意：登录窗口没关之前，不要启动后台监控。

## 第五步：启动监控

启动：

```bash
python scripts/x_monitorplus_service.py --root .runtime start
```

查看状态：

```bash
python scripts/x_monitorplus_service.py --root .runtime status
```

停止：

```bash
python scripts/x_monitorplus_service.py --root .runtime stop
```

## 抓到的帖子在哪里

主要看这个文件：

```text
.runtime/event_archive.jsonl
```

每一行就是一条记录。Codex 或其他 agent 可以直接读这个文件。

常用字段：

- `handle`：发帖账号
- `url`：帖子链接
- `created_at`：帖子时间
- `original_text`：原文
- `source_full_text`：更完整的原文
- `target_url`：来自哪个首页或 List

## 推荐接 Discord，但不是必须

本地文件跑通以后，如果你想让消息实时推到 Discord，可以打开 Discord。

把 `.runtime/config.json` 改成类似这样：

```json
{
  "output_sinks": ["jsonl", "discord"],
  "discord_enabled": true,
  "discord_channel_id": "YOUR_CHANNEL_ID",
  "discord_bot_token": "Bot YOUR_TOKEN"
}
```

不要把真实 token 发到 GitHub。

## 没有 Chrome 怎么办

不用管。默认：

```json
"browser_channel": "auto"
```

它会先找 Chrome。  
找不到 Chrome，就自动使用 Playwright 自带的 Chromium。

如果你想强制使用自带 Chromium：

```json
"browser_channel": "chromium"
```

## 多账号以后再说

先跑一个账号、一个 `.runtime`。

如果以后要多个账号，再创建多个运行目录：

```bash
python scripts/x_monitorplus_service.py --root .runtime/slot-1 open-profile
python scripts/x_monitorplus_service.py --root .runtime/slot-2 open-profile
```

每个目录都会保存自己的登录状态。

## 常见问题

`missing_config`  
说明配置没填好。检查有没有开启首页或 List。

`chrome_not_found`  
说明你强制用了 Chrome，但电脑没有 Chrome。改成 `auto` 或 `chromium`。

启动失败或提示 profile 被占用  
先关掉登录时弹出的浏览器窗口。

没有抓到新帖子  
先运行：

```bash
python scripts/x_monitorplus_service.py --root .runtime status
```

再确认 X 已经登录、List 链接能打开。

## 测试

```bash
python -m unittest discover -s tests
python scripts/x_monitorplus_regression_smoke.py
```

## License

MIT. See `LICENSE`.
