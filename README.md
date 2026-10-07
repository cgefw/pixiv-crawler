# pixiv-crawler

Pixiv 关键词图片爬虫：按关键词/标签批量下载原图，支持并发、多账号轮询、断点续爬。
A Pixiv keyword image crawler: batch-download original images by keyword/tag, with concurrency, multi-account rotation, and resumable progress.

[中文](#中文) | [English](#english)

---

## 中文

### 功能特性

- 关键词/标签搜索，每页约 60 个作品，超过最大页数自动截断
- 页数范围： `--pages 3`（第 1~3 页）或 `--pages 20-21`（指定范围）
- 并发搜索 + 并发下载，速度可调
- 多账号 Cookie 轮询，单账号连续失败自动暂停 5 分钟，请求失败自动换号重试
- 自动屏蔽 AI 生成图片（`ai_type=1`）
- 断点续爬：出错自动保存进度（`.progress.json`），`--resume` 从错误处继续
- 交互式脚本 `pixiv.sh`，无需记命令
- 中英文双语输出
- 纯 Python 标准库，零依赖

### 环境要求

- Python 3.6+（macOS / Linux / Windows 均可）

### 快速开始

```bash
git clone https://github.com/cgefw/pixiv-crawler.git
cd pixiv-crawler
cp .env.example .env   # 然后编辑 .env 填入你的 PHPSESSID
python3 pixiv_crawler.py 鹿乃 --pages 3
```

### Cookie 配置

Pixiv 未登录请求会返回 403，必须提供 `PHPSESSID`：

1. 浏览器登录 [pixiv.net](https://www.pixiv.net)
2. 按 `F12` 打开开发者工具 → **Network** 面板 → 刷新页面
3. 点任意请求，在 **Request Headers** 的 `Cookie` 里找到 `PHPSESSID=xxx`
4. 把 `xxx` 填入 `.env`：`PIXIV_PHPSESSID=xxx`（多账号用逗号分隔，自动轮询）

也可以用 `--cookie A,B,C` 参数或环境变量 `PIXIV_PHPSESSID` 传入。

> **安全提示**：`PHPSESSID` 等同账号密码。`.env` 已在 `.gitignore` 中，请勿提交或分享给他人。Cookie 过期后重新登录浏览器复制一份即可。

### 命令行用法

```bash
python3 pixiv_crawler.py 鹿乃 --pages 3        # 爬第 1~3 页
python3 pixiv_crawler.py 鹿乃 --pages 20-21    # 只爬第 20~21 页
python3 pixiv_crawler.py 鹿乃 --pages 999      # 填大数字会自动停在最大页
python3 pixiv_crawler.py 鹿乃 --resume         # 从上次出错处继续
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--pages` | 页数或范围 `N` / `A-B` | `3` |
| `--resume` | 从保存的进度继续（跳过已完成，重试失败） | 关 |
| `--save-dir` | 保存根目录（按关键词建子目录） | `~/pixiv_downloads` |
| `--workers` | 下载并发线程数 | `4` |
| `--search-workers` | 搜索并发线程数 | `3` |
| `--delay` | 每次请求前等待的秒数（每个线程分别计算） | `0.5` |
| `--cookie` | PHPSESSID，多个用逗号分隔 | 无 |

### 交互模式

```bash
bash pixiv.sh
```

菜单：开始新任务 → 继续未完成任务（自动列出可恢复的关键词）→ 添加 Cookie（粘贴整段 Cookie 自动提取）→ 查看账号状态。

### 断点续爬说明

- 每个关键词目录下保存 `.progress.json`（已完成的页/作品、失败列表、目标页数范围）
- 搜索出错：立即停止后续页（不爬新内容），保存进度并给出恢复命令
- 下载连续失败 10 次：自动停止，保存进度
- `--resume` 不传 `--pages` 时自动沿用上次范围

### 自动化调用

```bash
# 批量关键词
for kw in 鹿乃 初音ミク; do python3 pixiv_crawler.py "$kw" --pages 3; done

# cron 定时（注意写全路径）
0 3 * * * /usr/bin/python3 /path/to/pixiv_crawler.py 鹿乃 --pages 3
```

退出码：`0` 全部完成；`1` 搜索出错、连续失败停止或有作品下载失败（可用 `--resume` 继续）；`130` 被 Ctrl-C 中断。

### 免责声明

仅供个人学习使用。请遵守 Pixiv 使用条款，尊重画师版权，不要用于商业用途或大规模抓取，控制请求频率避免给服务器造成负担。

---

## English

### Features

- Keyword/tag search, ~60 artworks per page, auto-truncated at max pages
- Page ranges: `--pages 3` (pages 1-3) or `--pages 20-21` (explicit range)
- Concurrent searching and downloading with tunable speed
- Multi-account cookie rotation; a failing account is paused for 5 min and requests retry with another account
- AI-generated images filtered out (`ai_type=1`)
- Resumable: progress saved to `.progress.json` on error; continue with `--resume`
- Interactive shell `pixiv.sh` — no commands to memorize
- Bilingual (Chinese/English) output
- Pure Python standard library, zero dependencies

### Requirements

- Python 3.6+ (macOS / Linux / Windows)

### Quick start

```bash
git clone https://github.com/cgefw/pixiv-crawler.git
cd pixiv-crawler
cp .env.example .env   # then edit .env and fill in your PHPSESSID
python3 pixiv_crawler.py 鹿乃 --pages 3
```

### Cookie setup

Pixiv rejects anonymous requests with 403, so a `PHPSESSID` is required:

1. Log in to [pixiv.net](https://www.pixiv.net) in your browser
2. Press `F12` → **Network** panel → refresh the page
3. Click any request and find `PHPSESSID=xxx` in the `Cookie` request header
4. Put `xxx` into `.env`: `PIXIV_PHPSESSID=xxx` (comma-separated for multiple accounts, auto-rotated)

You can also use `--cookie A,B,C` or the `PIXIV_PHPSESSID` environment variable.

> **Security**: `PHPSESSID` is as sensitive as your password. `.env` is gitignored — never commit or share it. When the cookie expires, just copy a fresh one from your browser.

### CLI usage

```bash
python3 pixiv_crawler.py 鹿乃 --pages 3        # pages 1-3
python3 pixiv_crawler.py 鹿乃 --pages 20-21    # only pages 20-21
python3 pixiv_crawler.py 鹿乃 --pages 999      # large numbers stop at the max page
python3 pixiv_crawler.py 鹿乃 --resume         # resume from last saved progress
```

| Option | Description | Default |
| --- | --- | --- |
| `--pages` | Page count or range `N` / `A-B` | `3` |
| `--resume` | Resume from saved progress (skips finished, retries failed) | off |
| `--save-dir` | Output root dir (subdirectory per keyword) | `~/pixiv_downloads` |
| `--workers` | Download threads | `4` |
| `--search-workers` | Search threads | `3` |
| `--delay` | Seconds each thread waits before every request | `0.5` |
| `--cookie` | PHPSESSID(s), comma-separated | none |

### Interactive mode

```bash
bash pixiv.sh
```

Menu: start a new task → resume an unfinished task (auto-lists resumable keywords) → add a cookie (paste a full cookie string, auto-extracted) → show account status.

### Resume behavior

- A `.progress.json` is kept in each keyword directory (finished pages/artworks, failures, target page range)
- Search error: remaining pages are stopped immediately (nothing new is crawled), progress saved, and a resume command is printed
- 10 consecutive download failures: stops automatically and saves progress
- `--resume` without `--pages` reuses the page range from the previous run

### Automation

```bash
# Batch keywords
for kw in 鹿乃 初音ミク; do python3 pixiv_crawler.py "$kw" --pages 3; done

# cron (use absolute paths)
0 3 * * * /usr/bin/python3 /path/to/pixiv_crawler.py 鹿乃 --pages 3
```

Exit codes: `0` all done; `1` search error, stopped after repeated failures, or some artworks failed (continue with `--resume`); `130` interrupted with Ctrl-C.

### Disclaimer

For personal learning only. Respect Pixiv's Terms of Service and the artists' copyrights. Do not use commercially or for large-scale scraping; keep request rates modest to avoid burdening the servers.
