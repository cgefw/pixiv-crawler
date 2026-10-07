#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixiv 关键词图片爬虫 / Pixiv keyword image crawler

并发 + 多账号轮询 + 断点续爬 / Concurrency, multi-account rotation, resumable.

用法 / Usage:
    python3 pixiv_crawler.py 鹿乃 --pages 3        # 第 1~3 页 / pages 1-3
    python3 pixiv_crawler.py 鹿乃 --pages 20-21    # 只爬第 20~21 页 / only pages 20-21
    python3 pixiv_crawler.py 鹿乃 --resume         # 从上次出错处继续 / resume from last progress

Cookie (PHPSESSID) 提供方式, 可多个轮询 / Provide one or more PHPSESSID cookies:
    1. .env 文件:  PIXIV_PHPSESSID=A,B,C   (脚本所在目录 / next to this script)
    2. 命令行参数:  --cookie A,B,C
    3. 环境变量:    export PIXIV_PHPSESSID=A,B,C
    4. 多账号目录:  ~/.pixiv_cookies/ 下每个文件一个账号 / one account per file

获取 Cookie / Get your cookie: 浏览器登录 pixiv.net -> F12 -> Network -> 刷新 ->
任意请求 -> Request Headers 的 Cookie 里找 PHPSESSID=xxx
Log in to pixiv.net -> F12 -> Network -> refresh -> any request ->
find PHPSESSID=xxx in the Cookie request header.
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://www.pixiv.net"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
DELAY = 0.5
POOL = None
STOP_SEARCH = threading.Event()


class SessionPool:
    def __init__(self, cookies):
        self.sessions = [{"phpsessid": c, "fails": 0, "down_until": 0.0}
                         for c in cookies]
        self.lock = threading.Lock()
        self.idx = 0

    def acquire(self):
        with self.lock:
            now = time.time()
            for _ in range(len(self.sessions)):
                s = self.sessions[self.idx]
                self.idx = (self.idx + 1) % len(self.sessions)
                if now >= s["down_until"]:
                    return s
            s = min(self.sessions, key=lambda x: x["down_until"])
            self.idx = self.sessions.index(s)
            return s

    def mark_failure(self, s):
        with self.lock:
            s["fails"] += 1
            if s["fails"] >= 3:
                s["down_until"] = time.time() + 300
                s["fails"] = 0
                print(f"账号 {s['phpsessid'][:8]}... 连续失败, 暂停 5 分钟 / "
                      f"account paused for 5 min after repeated failures",
                      file=sys.stderr)

    def mark_success(self, s):
        with self.lock:
            s["fails"] = 0

    def __len__(self):
        return len(self.sessions)


def parse_phpsessid(text):
    text = text.strip()
    if "PHPSESSID=" in text:
        m = re.search(r"(?:^|;\s*)PHPSESSID=([^;\s]+)", text)
        if m:
            return m.group(1).strip()
    return text


def read_env_file(path):
    sources = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"(?:export\s+)?(?:PIXIV_)?PHPSESSID\s*=(.*)", line)
            if m:
                val = re.sub(r"\s+#.*", "", m.group(1)).strip().strip('"').strip("'")
                sources += [c for c in val.split(",") if c.strip()]
            elif "=" not in line or re.search(r"(?:^|;\s*)PHPSESSID=", line):
                # 裸值或整段 Cookie, 其他 KEY=value 一律忽略 / bare value or pasted Cookie
                # header; any other KEY=value line is ignored
                sources.append(line)
    return sources


def env_file_paths():
    p = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env")
    return [p] if os.path.isfile(p) else []


def read_cookie_file(path):
    sources = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sources.append(line)
    return sources


def load_cookies(args):
    sources = []
    if args.cookie:
        sources += [c for c in args.cookie.split(",")]
    env = os.environ.get("PIXIV_PHPSESSID")
    if env:
        sources += [c for c in env.split(",")]
    for p in env_file_paths():
        sources += read_env_file(p)
    cdir = os.path.expanduser("~/.pixiv_cookies")
    if os.path.isdir(cdir):
        for fn in sorted(os.listdir(cdir)):
            if fn.startswith("."):
                continue
            p = os.path.join(cdir, fn)
            if os.path.isfile(p):
                sources += read_cookie_file(p)
    seen, out = set(), []
    for c in sources:
        c = parse_phpsessid(c)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def request(url, timeout=60, retries=3):
    last_err = None
    use_pool = POOL and "pixiv.net" in url
    for _ in range(retries):
        s = POOL.acquire() if use_pool else None
        headers = {"User-Agent": UA, "Referer": BASE + "/"}
        if s:
            headers["Cookie"] = "PHPSESSID=" + s["phpsessid"]
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if s:
                POOL.mark_success(s)
            return data
        except urllib.error.HTTPError as e:
            if s:
                POOL.mark_failure(s)
            if e.code in (403, 429, 500, 502, 503):
                last_err = e
                time.sleep(DELAY)
                continue
            raise
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            last_err = e
            time.sleep(DELAY)
    raise last_err


def fetch_json(url):
    return json.loads(request(url).decode("utf-8"))


def search_page(keyword, page):
    api = BASE + "/ajax/search/artworks/" + urllib.parse.quote(keyword)
    qs = urllib.parse.urlencode({
        "word": keyword, "order": "date_d", "mode": "all",
        "s_mode": "tag", "p": page, "type": "all", "lang": "zh",
        "ai_type": 1,
    })
    data = fetch_json(f"{api}?{qs}")
    if data.get("error"):
        raise RuntimeError(data.get("message", "search failed"))
    manga = (data.get("body") or {}).get("illustManga") or {}
    return manga.get("data") or [], manga.get("total") or 0


def search_task(keyword, page):
    if STOP_SEARCH.is_set():
        return page, None, None, "cancelled"
    try:
        data, total = search_page(keyword, page)
        return page, data, total, None
    except Exception as e:
        STOP_SEARCH.set()
        return page, None, None, str(e)


def page_urls(illust_id):
    data = fetch_json(f"{BASE}/ajax/illust/{illust_id}/pages")
    if data.get("error"):
        return []
    return [p["urls"]["original"] for p in data["body"]]


def ext_of(url):
    name = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
    m = re.search(r"\.(jpg|jpeg|png|gif|zip)$", name, re.I)
    return ("." + m.group(1).lower()) if m else ".jpg"


def download_image(url, path):
    if os.path.exists(path):
        return False
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(request(url))
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def download_artwork(iid, save_dir):
    try:
        urls = page_urls(iid)
        if not urls:
            return iid, True, f"跳过 {iid}: 无原图 / skip {iid}: no original image"
        n = 0
        for i, u in enumerate(urls):
            path = os.path.join(save_dir, f"{iid}_p{i}{ext_of(u)}")
            if download_image(u, path):
                n += 1
                time.sleep(DELAY)
        return iid, True, f"作品 {iid}: 下载 {n}/{len(urls)} 张 / {n}/{len(urls)} image(s)"
    except Exception as e:
        return iid, False, f"作品 {iid}: 失败 / failed - {e}"


def parse_page_range(spec):
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", spec.strip())
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    if spec.strip().isdigit():
        return (1, int(spec.strip()))
    raise ValueError(f"无效的页数格式 / invalid page range: {spec} (支持 N 或 A-B / use N or A-B)")


def progress_path(save_dir):
    return os.path.join(save_dir, ".progress.json")


def load_progress(save_dir):
    p = progress_path(save_dir)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"pages_done": [], "done_ids": [], "failed_ids": []}


def save_progress(save_dir, prog):
    tmp = progress_path(save_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=1)
    os.replace(tmp, progress_path(save_dir))


def main():
    ap = argparse.ArgumentParser(
        description="Pixiv 关键词图片爬虫 / Pixiv keyword image crawler "
                    "(并发 concurrency + 多账号轮询 multi-account + 断点续爬 resumable)")
    ap.add_argument("keyword", help="搜索关键词 / search keyword, 例如 e.g. 鹿乃")
    ap.add_argument("--pages", default=None,
                    help="页数或范围 / pages or range: 3 = 第1~3页 pages 1-3, "
                        "20-21 = 第20~21页 pages 20-21, 默认 default 3")
    ap.add_argument("--resume", action="store_true",
                    help="从上次进度继续 / resume from saved progress")
    ap.add_argument("--save-dir", default="~/pixiv_downloads",
                    help="保存根目录 / output root dir, 默认 default ~/pixiv_downloads")
    ap.add_argument("--cookie", default="",
                    help="PHPSESSID, 多个用逗号分隔 / comma-separated for multi-account; "
                        "也可用 .env / 环境变量 / or use .env, env var")
    ap.add_argument("--delay", type=float, default=0.5,
                    help="请求间隔秒数 / delay between requests in seconds, 默认 default 0.5")
    ap.add_argument("--workers", type=int, default=4,
                    help="下载并发线程数 / download threads, 默认 default 4")
    ap.add_argument("--search-workers", type=int, default=3,
                    help="搜索并发线程数 / search threads, 默认 default 3")
    args = ap.parse_args()

    global DELAY, POOL
    DELAY = args.delay

    cookies = load_cookies(args)
    if not cookies:
        print("错误: 未提供 PHPSESSID (Pixiv 未登录请求会被拒绝 403)\n"
              "Error: PHPSESSID not found (Pixiv rejects anonymous requests with 403)\n"
              "请在 .env 中设置 PIXIV_PHPSESSID=你的值, 或用 --cookie 传入\n"
              "Set PIXIV_PHPSESSID in .env, or pass --cookie", file=sys.stderr)
        sys.exit(1)
    POOL = SessionPool(cookies)
    print(f"已加载 {len(cookies)} 个账号, 请求自动轮询 / "
          f"Loaded {len(cookies)} account(s), rotating per request", flush=True)

    keyword = args.keyword.strip()
    save_dir = os.path.join(os.path.expanduser(args.save_dir), re.sub(r'[\\/:*?"<>|]', "_", keyword))
    os.makedirs(save_dir, exist_ok=True)

    prog = load_progress(save_dir) if args.resume else \
        {"pages_done": [], "done_ids": [], "failed_ids": []}
    done_pages = set(prog.get("pages_done", []))
    done_ids = set(prog.get("done_ids", []))
    failed_ids = set(prog.get("failed_ids", []))

    if args.pages is not None:
        try:
            start, end = parse_page_range(args.pages)
        except ValueError as e:
            print(f"错误 / Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.resume and prog.get("page_range"):
        start, end = prog["page_range"]
        print(f"继续上次的任务: 第 {start}~{end} 页 / Resuming previous task: pages {start}-{end}",
              flush=True)
    else:
        start, end = 1, 3

    pages_to_search = [p for p in range(start, end + 1)
                       if not (args.resume and p in done_pages)]
    if args.resume and not pages_to_search:
        print("所有页已搜索完成 / All pages already searched", flush=True)

    artworks, total, had_error = [], 0, False
    if pages_to_search:
        with ThreadPoolExecutor(max_workers=args.search_workers) as pool:
            futures = {pool.submit(search_task, keyword, p): p
                       for p in pages_to_search}
            got = 0
            for fut in as_completed(futures):
                page, data, t, err = fut.result()
                got += 1
                if err:
                    had_error = True
                    print(f"搜索第 {page} 页失败 / Search page {page} failed: {err} "
                          f"(其余页已停止, 进度已保存 / remaining pages stopped, progress saved)",
                          file=sys.stderr)
                    continue
                if data is None:
                    continue
                if t and not total:
                    total = t
                    max_pages = (total + 59) // 60
                    if end > max_pages:
                        print(f"该关键词共 {max_pages} 页, 已自动截断 / "
                              f"keyword has {max_pages} pages max; truncated", flush=True)
                        end = max_pages
                artworks.extend(data)
                done_pages.add(page)
                print(f"搜索进度 / Search progress {got}/{len(futures)} "
                      f"(第 {page} 页完成 / page {page} done)", flush=True)

    if total:
        max_pages = (total + 59) // 60
        print(f"共 {total} 个作品, 最大 {max_pages} 页, 目标范围 {start}~{end} 页 / "
              f"{total} artworks total, max {max_pages} pages, target {start}-{end}")

    artworks = [a for a in artworks if a]
    ids = []
    seen = set()
    for a in artworks:
        iid = a.get("id")
        if iid and iid not in done_ids and iid not in seen:
            seen.add(iid)
            ids.append(iid)
    for iid in failed_ids:
        if iid not in seen:
            seen.add(iid)
            ids.append(iid)

    if had_error:
        print(f"搜索出错, 保留进度, 不再继续爬取 / Search error: progress saved, "
              f"no further crawling.\n修复后运行 / After fixing, run: "
              f"python3 {os.path.basename(__file__)} {keyword} --resume",
              file=sys.stderr)
    elif not ids and not pages_to_search:
        print("没有需要下载的作品 / Nothing to download", flush=True)

    stopped = False
    if ids and not had_error:
        retry_n = len(failed_ids & set(ids))
        print(f"待下载 {len(ids)} 个作品 (已完成 {len(done_ids)} 个, 重试 {retry_n} 个) / "
              f"{len(ids)} to download ({len(done_ids)} done, {retry_n} retry)", flush=True)
        pool = ThreadPoolExecutor(max_workers=args.workers)
        futures = {pool.submit(download_artwork, iid, save_dir): iid
                   for iid in ids}
        done_n, consec_fail = 0, 0
        try:
            for fut in as_completed(futures):
                iid, ok, msg = fut.result()
                done_n += 1
                print(f"[{done_n}/{len(futures)}] {msg}", flush=True)
                if ok:
                    done_ids.add(iid)
                    failed_ids.discard(iid)
                    consec_fail = 0
                else:
                    failed_ids.add(iid)
                    consec_fail += 1
                    if consec_fail >= 10:
                        stopped = True
                        print("连续失败 10 次, 已停止下载, 进度已保存 / "
                              "10 consecutive failures; stopped, progress saved. "
                              "用 --resume 继续 / use --resume to continue",
                              file=sys.stderr)
                        for f in futures:
                            f.cancel()
                        break
        finally:
            pool.shutdown(wait=True)

    save_progress(save_dir, {
        "keyword": keyword,
        "page_range": [start, end],
        "pages_done": sorted(done_pages),
        "done_ids": sorted(done_ids),
        "failed_ids": sorted(failed_ids),
    })

    if failed_ids:
        print(f"完成 (有 {len(failed_ids)} 个失败) / Done with {len(failed_ids)} failure(s). "
              f"图片目录 / dir: {save_dir}")
        print("修复问题后运行 --resume 可继续 / Fix the issue and rerun with --resume",
              flush=True)
    elif stopped:
        print(f"已停止, 进度已保存 / Stopped, progress saved. "
              f"继续请运行 --resume, 图片目录 / dir: {save_dir}")
    else:
        print(f"完成! 图片已保存到 / Done! Saved to: {save_dir}")


if __name__ == "__main__":
    main()
