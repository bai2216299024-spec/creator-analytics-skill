#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信公众号后台文章数据采集器。"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright
from paths import cookie_file, output_dir

PLATFORM = "微信公众号"
HOME_URL = "https://mp.weixin.qq.com/"
APPMSG_URL = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
DEFAULT_COOKIE_FILE = cookie_file("wechat")
DEFAULT_OUTPUT_DIR = output_dir()


def parse_args():
    parser = argparse.ArgumentParser(description="微信公众号后台数据采集")
    parser.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE), help="Cookie 文件路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser.add_argument("--headed", action="store_true", help="打开浏览器窗口（首次登录用）")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际采集")
    parser.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD，默认昨天")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def save_cookies(context, path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(context.storage_state(), f, ensure_ascii=False, indent=2)
    print(f"✅ 微信公众号 Cookies 已保存到 {path}")


def scrape_wechat(cookie_path: str, output_path: str, headless: bool, target_date_str: str) -> dict:
    result = {"platform": PLATFORM, "date": target_date_str, "items": [], "empty": True, "error": None}
    storage_state = str(cookie_path) if Path(cookie_path).exists() else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            storage_state=storage_state,
        )
        page = context.new_page()
        try:
            print("📰 正在访问微信公众号后台...")
            page.goto(APPMSG_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            if is_login_page(page):
                if headless:
                    raise RuntimeError("微信公众号登录态过期，请使用 --headed 模式扫码登录")
                print("🔑 请在打开的浏览器中扫码登录微信公众号后台...")
                wait_until_logged_in(page, timeout_ms=300000)
                save_cookies(context, cookie_path)
                page.goto(APPMSG_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            else:
                save_cookies(context, cookie_path)

            items = parse_items(page, target_date_str)
            if items:
                result["items"] = dedupe_items(items)
                result["empty"] = False
                print(f"🎯 找到 {len(result['items'])} 条昨日公众号内容")
            else:
                print("📭 公众号昨日无新增发布内容或列表不可见")
        except Exception as e:
            result["error"] = str(e)
            print(f"❌ 微信公众号采集异常: {e}")
        finally:
            browser.close()
    return result


def is_login_page(page) -> bool:
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    login_markers = ["微信公众平台", "扫码登录", "请使用微信扫描二维码", "登录"]
    backend_markers = ["首页", "新的创作", "发表记录", "内容管理", "统计"]
    return any(marker in text for marker in login_markers) and not any(marker in text for marker in backend_markers)


def wait_until_logged_in(page, timeout_ms: int):
    deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=timeout_ms)
    while datetime.datetime.now() < deadline:
        if not is_login_page(page):
            page.wait_for_timeout(3000)
            if not is_login_page(page):
                return
        page.wait_for_timeout(2000)
    raise PlaywrightTimeout("等待微信公众号扫码登录超时")


def parse_items(page, target_date_str: str) -> list[dict]:
    selectors = [
        ".weui-desktop-card",
        ".publish_card",
        ".appmsg_list_item",
        "[class*='publish'] [class*='item']",
        "table tbody tr",
    ]
    raw_blocks = []
    for selector in selectors:
        try:
            blocks = page.query_selector_all(selector)
        except Exception:
            blocks = []
        if blocks:
            raw_blocks = blocks
            break

    parsed = []
    for block in raw_blocks:
        text = block.inner_text().strip()
        item = parse_block_text(text, target_date_str)
        if item and matches_target_date(item.get("publish_date", ""), target_date_str):
            href = extract_first_href(block)
            if href:
                item["detail_url"] = href
            parsed.append(item)

    if parsed:
        return parsed
    return parse_page_text(page, target_date_str)


def parse_block_text(text: str, target_date_str: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    entry = {
        "publish_date": "",
        "title": "",
        "content": "",
        "content_type": "文章",
        "reads": None,
        "likes": None,
        "comments": None,
        "wows": None,
    }
    for idx, line in enumerate(lines):
        if matches_target_date(line, target_date_str):
            entry["publish_date"] = line
        if "阅读" in line:
            entry["reads"] = parse_metric_value(lines, idx)
        elif "点赞" in line:
            entry["likes"] = parse_metric_value(lines, idx)
        elif "评论" in line:
            entry["comments"] = parse_metric_value(lines, idx)
        elif "在看" in line:
            entry["wows"] = parse_metric_value(lines, idx)

    blocked = {"发表记录", "已发表", "群发", "数据", "详情", "阅读", "点赞", "评论", "在看"}
    candidates = [
        line for line in lines
        if line not in blocked
        and not matches_target_date(line, target_date_str)
        and not any(label in line for label in ("阅读", "点赞", "评论", "在看"))
        and len(line) >= 4
    ]
    if candidates:
        entry["title"] = candidates[0][:100]
        entry["content"] = entry["title"]
    if not entry["title"] and not entry["publish_date"]:
        return None
    if not entry["publish_date"] and target_date_str in text:
        entry["publish_date"] = target_date_str
    return entry


def parse_page_text(page, target_date_str: str) -> list[dict]:
    try:
        text = page.inner_text("body", timeout=10000)
    except Exception:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    current = None
    for idx, line in enumerate(lines):
        if matches_target_date(line, target_date_str):
            if current and current.get("title"):
                items.append(current)
            current = {
                "publish_date": line,
                "title": "",
                "content": "",
                "content_type": "文章",
                "reads": None,
                "likes": None,
                "comments": None,
                "wows": None,
            }
            continue
        if not current:
            continue
        if "阅读" in line:
            current["reads"] = parse_metric_value(lines, idx)
        elif "点赞" in line:
            current["likes"] = parse_metric_value(lines, idx)
        elif "评论" in line:
            current["comments"] = parse_metric_value(lines, idx)
        elif "在看" in line:
            current["wows"] = parse_metric_value(lines, idx)
        elif not current["title"] and len(line) >= 4 and len(line) <= 100:
            current["title"] = line
            current["content"] = line
    if current and current.get("title"):
        items.append(current)
    return items


def extract_first_href(element) -> str | None:
    link = element.query_selector("a[href]")
    if not link:
        return None
    href = link.get_attribute("href")
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://mp.weixin.qq.com" + href
    return href


def parse_number(text: str) -> int | None:
    normalized = text.replace(",", "").replace("，", "")
    nums = re.findall(r"([\d.]+)\s*(万|w|W|亿)?", normalized)
    if not nums:
        return None
    value = float(nums[0][0])
    unit = nums[0][1]
    if unit == "亿":
        value *= 100000000
    elif unit in ("万", "w", "W"):
        value *= 10000
    return int(value)


def parse_metric_value(lines: list[str], idx: int) -> int | None:
    value = parse_number(lines[idx])
    if value is not None:
        return value
    if idx + 1 < len(lines):
        return parse_number(lines[idx + 1])
    return None


def matches_target_date(text: str, target_date_str: str) -> bool:
    if not text:
        return False
    target = datetime.date.fromisoformat(target_date_str)
    normalized = text.strip()
    return (
        target_date_str in normalized
        or target.strftime("%Y年%m月%d日") in normalized
        or target.strftime("%m-%d") in normalized
        or f"{target.month}月{target.day}日" in normalized
        or ("昨天" in normalized and target == datetime.date.today() - datetime.timedelta(days=1))
    )


def dedupe_items(items: list[dict]) -> list[dict]:
    best = {}
    for item in items:
        key = (item.get("publish_date", ""), item.get("title", ""))
        score = len(item.get("title", "")) + (item.get("reads") or 0) + (item.get("likes") or 0) + (item.get("comments") or 0)
        if key not in best or score > best[key][0]:
            best[key] = (score, item)
    return [row for _, row in best.values()]


def save_output(data: dict, output_path: str):
    path = Path(output_path)
    path.mkdir(parents=True, exist_ok=True)
    out_file = path / "wechat_data.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 微信公众号数据已保存到 {out_file}")


def main():
    args = parse_args()
    date_str = target_date(args.date)
    print(f"📰 微信公众号数据采集 - 目标日期: {date_str}")
    print("=" * 50)
    if args.dry_run:
        result = {"platform": PLATFORM, "date": date_str, "items": [], "empty": True, "error": None}
    else:
        result = scrape_wechat(args.cookie_file, args.output_dir, not args.headed, date_str)
    save_output(result, args.output_dir)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
