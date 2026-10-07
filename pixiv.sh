#!/bin/bash
# Pixiv 图片爬虫交互脚本 / Interactive shell for pixiv-crawler
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="python3"
SCRIPT="$DIR/pixiv_crawler.py"
SAVE_ROOT="$HOME/pixiv_downloads"
ENV_FILE="$DIR/.env"

count_accounts() {
    "$PY" -c "
import sys, argparse
sys.path.insert(0, '$DIR')
import pixiv_crawler as p
print(len(p.load_cookies(argparse.Namespace(cookie=''))))
" 2>/dev/null || echo 0
}

new_task() {
    echo
    read -r -p "搜索关键词 / Keyword: " kw
    [ -z "$kw" ] && { echo "关键词不能为空 / keyword required"; return; }
    read -r -p "页数或范围 / Pages (如 e.g. 3 或/or 20-21, 默认 default 3): " pages
    pages=${pages:-3}
    read -r -p "下载线程数 / Download workers (默认 default 4): " workers
    workers=${workers:-4}
    read -r -p "请求间隔秒 / Delay seconds (默认 default 0.5): " delay
    delay=${delay:-0.5}
    echo
    echo "开始爬取 / Start: $kw (页数 pages $pages)"
    "$PY" "$SCRIPT" "$kw" --pages "$pages" --workers "$workers" \
        --delay "$delay" --save-dir "$SAVE_ROOT"
}

resume_task() {
    echo
    list=()
    if [ -d "$SAVE_ROOT" ]; then
        for d in "$SAVE_ROOT"/*/ "$SAVE_ROOT"/.[!.]*/ "$SAVE_ROOT"/..?*/; do
            [ -f "$d/.progress.json" ] || continue
            # 目录名里的 / 等字符已被替换成 _, 原关键词从进度文件读取 / dir names are sanitized
            kw=$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("keyword", ""))' \
                "$d/.progress.json" 2>/dev/null)
            list+=("${kw:-$(basename "$d")}")
        done
    fi
    if [ ${#list[@]} -eq 0 ]; then
        echo "没有找到未完成的任务 / No resumable task found (no .progress.json)"
        return
    fi
    echo "可继续的任务 / Resumable tasks:"
    i=1
    for name in "${list[@]}"; do
        echo "  $i) $name"
        i=$((i + 1))
    done
    read -r -p "选择编号 / Pick a number: " sel
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || [ "$sel" -lt 1 ] || [ "$sel" -gt ${#list[@]} ]; then
        echo "无效选择 / invalid choice"
        return
    fi
    kw="${list[$((sel - 1))]}"
    echo "继续任务 / Resuming: $kw"
    "$PY" "$SCRIPT" "$kw" --resume --save-dir "$SAVE_ROOT"
}

add_cookie() {
    echo
    echo "浏览器登录 www.pixiv.net -> F12 -> Network -> 刷新 -> 点任意请求"
    echo "在 Request Headers 的 Cookie 里找到 PHPSESSID=xxx"
    echo "Log in to pixiv.net -> F12 -> Network -> refresh -> any request"
    echo "Find PHPSESSID=xxx in the Cookie request header"
    echo
    read -r -p "请粘贴 PHPSESSID (整段 Cookie 也可以 / full cookie string works too): " raw
    [ -z "$raw" ] && { echo "未输入内容 / nothing entered"; return; }
    val=$("$PY" - "$raw" <<'EOF'
import re, sys
t = sys.argv[1].strip()
m = re.search(r"(?:^|;\s*)PHPSESSID=([^;\s]+)", t)
print(m.group(1) if m else t)
EOF
)
    if [ -z "$val" ]; then
        echo "提取失败 / extraction failed"
        return
    fi
    if [ ! -f "$ENV_FILE" ]; then
        printf '# Pixiv Cookie 配置 / config (此文件勿提交 git / never commit this file)\n' > "$ENV_FILE"
    fi
    echo "PIXIV_PHPSESSID=$val" >> "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "已添加 / Added to $ENV_FILE (当前共 total $(count_accounts) 个账号/accounts)"
}

show_cookies() {
    echo
    echo "已配置的账号 / Configured accounts:"
    "$PY" -c "
import sys, argparse
sys.path.insert(0, '$DIR')
import pixiv_crawler as p
cs = p.load_cookies(argparse.Namespace(cookie=''))
for i, c in enumerate(cs, 1):
    print(f'  {i}) {c[:12]}... (len {len(c)})')
print(f'  共 {len(cs)} 个 / total {len(cs)}')
" 2>/dev/null
}

while true; do
    echo
    echo "=============================="
    echo "  Pixiv 图片爬虫 / Crawler"
    echo "=============================="
    echo "  1) 开始新任务 / New task"
    echo "  2) 继续未完成任务 / Resume task"
    echo "  3) 添加账号 Cookie / Add cookie"
    echo "  4) 查看账号状态 / Show accounts"
    echo "  0) 退出 / Exit"
    echo
    read -r -p "请选择 / Choose [0-4]: " choice
    case "$choice" in
        1) new_task ;;
        2) resume_task ;;
        3) add_cookie ;;
        4) show_cookies ;;
        0) echo "再见 / Bye"; exit 0 ;;
        *) echo "无效选择 / invalid choice" ;;
    esac
done
