#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书创作者平台 — 内容数据采集器

从 https://creator.xiaohongshu.com 采集前一天发布的内容数据。
支持 cookie 持久化、自动检测过期、手动重新登录。
"""

import argparse
import json
import os
import sys
import datetime
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from paths import cookie_file, output_dir, profile_dir

PLATFORM = "小红书"
BASE_URL = "https://creator.xiaohongshu.com"
CONTENT_URL = "https://creator.xiaohongshu.com/new/note-manager"

# 脚本所在目录
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_COOKIE_FILE = cookie_file("xhs")
DEFAULT_OUTPUT_DIR = output_dir()
DEFAULT_PROFILE_DIR = profile_dir("xhs")


def parse_args():
    parser = argparse.ArgumentParser(description="小红书创作者平台数据采集")
    parser.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE),
                        help="Cookie 文件路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="输出目录")
    parser.add_argument("--headed", action="store_true",
                        help="打开浏览器窗口（首次登录用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="模拟运行，不实际采集")
    parser.add_argument("--date", default=None,
                        help="目标日期 YYYY-MM-DD，默认昨天")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    """获取目标日期字符串"""
    if date_str:
        return date_str
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    return yesterday.isoformat()


def load_cookies(cookie_file: str) -> dict | None:
    """加载已保存的浏览器状态。"""
    path = Path(cookie_file)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cookies(context, cookie_file: str):
    """保存 cookies 到文件"""
    path = Path(cookie_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"✅ Cookies 已保存到 {cookie_file}")


def scrape_xhs(cookie_file: str, output_dir: str, headless: bool, target_date_str: str) -> dict:
    """采集小红书内容数据"""
    result = {
        "platform": PLATFORM,
        "date": target_date_str,
        "items": [],
        "empty": True,
        "error": None,
    }

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(DEFAULT_PROFILE_DIR),
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        page = context.new_page()

        try:
            print(f"📕 正在访问小红书创作者平台...")
            page.goto(CONTENT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            page_text = page.inner_text("body", timeout=10000)
            if "你访问的页面不见了" in page_text or "页面不见了" in page_text:
                raise RuntimeError(f"小红书内容管理入口不可用: {page.url}")

            # 检测是否登录成功（看URL是否跳转到登录页）
            current_url = page.url
            if is_login_page(page) or "login" in current_url or "passport" in current_url:
                if headless:
                    raise RuntimeError("Cookie 已过期，请使用 --headed 模式重新登录")
                print("🔑 Cookie 已过期，请在打开的浏览器中扫码登录...")
                wait_until_logged_in(page, timeout_ms=300000)
                print("✅ 登录成功！保存新的 cookies...")
                save_cookies(context, cookie_file)
                page.goto(CONTENT_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            else:
                print("✅ 已登录")
                save_cookies(context, cookie_file)

            # 等待内容列表加载
            try:
                page.wait_for_selector("table, .note-list, [class*='content-list'], [class*='note-item'], [class*='note'], [class*='data']",
                                       timeout=30000)
            except PlaywrightTimeout:
                print("⚠️ 内容列表未加载，尝试等待更多时间...")
                page.wait_for_timeout(5000)

            # 尝试滚动加载全部内容
            prev_count = 0
            for i in range(5):
                items = page.query_selector_all(
                    "table tbody tr, .note-list .note-item, [class*='content-list'] > div, "
                    "[class*='note-item'], [class*='post-item'], [class*='note-card'], [class*='data-list'] > div"
                )
                if len(items) > 0 and len(items) == prev_count:
                    break
                prev_count = len(items)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            # 提取内容数据
            items_raw = page.query_selector_all(
                "table tbody tr, .note-list .note-item, [class*='content-list'] > div, "
                "[class*='note-item'], [class*='post-item'], [class*='note-card'], [class*='data-list'] > div"
            )
            print(f"📋 找到 {len(items_raw)} 条内容")

            parsed_items = []
            for item in items_raw:
                try:
                    entry = parse_content_row(item, page)
                    if entry:
                        parsed_items.append(entry)
                except Exception as e:
                    print(f"⚠️ 解析单条内容时出错: {e}")
                    continue

            # 获取所有可用的文本行作为备选方案
            if not parsed_items:
                print("🔄 尝试备选解析方案...")
                parsed_items = parse_content_via_text(page, target_date_str)
                if not parsed_items and not page_has_empty_state(page):
                    raise RuntimeError("未找到小红书内容列表，可能仍停留在非笔记管理页或页面结构已变化")

            # 过滤出目标日期的内容
            target_items = []
            for item in parsed_items:
                pub_date = item.get("publish_date", "")
                if matches_target_date(pub_date, target_date_str):
                    target_items.append(item)

            if target_items:
                target_items = dedupe_items(target_items)
                result["items"] = target_items
                result["empty"] = False
                print(f"🎯 找到 {len(target_items)} 条昨日发布的内容")
            else:
                print(f"📭 昨日无新增发布内容")

        except Exception as e:
            error_msg = str(e)
            result["error"] = error_msg
            print(f"❌ 异常: {error_msg}")
        finally:
            context.close()

    return result


def parse_content_row(element, page) -> dict | None:
    """解析单条内容行"""
    text = element.inner_text()
    if not text.strip():
        return None

    entry = {
        "publish_date": "",
        "title": "",
        "content": "",
        "content_type": "图文/笔记",
        "views": 0,
        "likes": 0,
        "comments": 0,
        "collects": 0,
        "shares": 0,
    }

    title_el = element.query_selector(".note-card__title")
    time_el = element.query_selector(".note-card__time")
    stat_els = element.query_selector_all(".note-card__stat")
    if title_el and time_el and len(stat_els) >= 5:
        entry["title"] = title_el.inner_text().strip()
        entry["content"] = entry["title"]
        entry["publish_date"] = time_el.inner_text().strip()
        stats = [parse_number(stat.inner_text()) for stat in stat_els[:5]]
        # 小红书笔记管理卡片顺序：浏览/观看、点赞、收藏、评论、分享。
        entry["views"], entry["likes"], entry["collects"], entry["comments"], entry["shares"] = stats
        return entry

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 尝试从文本中提取数据
    for line in lines:
        # 匹配日期格式: 2025-01-15 或 01-15 或 1月15日
        if any(c in line for c in ["-", "月", "日", "/", "昨天"]):
            entry["publish_date"] = line.strip()

        # 匹配数字指标
        if "播放" in line or "观看" in line or "浏览" in line or "阅读" in line:
            entry["views"] = parse_number(line)
        elif "点赞" in line:
            entry["likes"] = parse_number(line)
        elif "评论" in line:
            entry["comments"] = parse_number(line)

    # 标题通常是第一行或日期之前的行
    title_candidates = [l for l in lines if l not in [entry["publish_date"]] and
                        "播放" not in l and "观看" not in l and "浏览" not in l and
                        "点赞" not in l and "评论" not in l]
    if title_candidates:
        entry["title"] = title_candidates[0]
        entry["content"] = entry["title"]

    if not entry["title"] and not entry["publish_date"]:
        return None

    return entry


def parse_content_via_text(page, target_date_str: str) -> list[dict]:
    """备选方案：直接从页面文本中提取内容"""
    body_text = page.inner_text("body")
    items = []
    # 按行分割，尝试按内容块组织
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    current_item = {}
    for line in lines:
        if target_date_str[:7] in line and ("播放" in line or "点赞" in line):
            if current_item and current_item.get("title"):
                items.append(current_item)
            current_item = {"publish_date": "", "title": "", "views": 0, "likes": 0, "comments": 0}
            current_item["publish_date"] = target_date_str
        elif current_item:
            if not current_item["title"] and len(line) < 50 and "播放" not in line and "点赞" not in line:
                current_item["title"] = line
            elif "播放" in line or "浏览" in line or "观看" in line or "阅读" in line:
                current_item["views"] = parse_number(line)
            elif "点赞" in line:
                current_item["likes"] = parse_number(line)
            elif "评论" in line:
                current_item["comments"] = parse_number(line)

    if current_item and current_item.get("title"):
        items.append(current_item)

    return items


def parse_number(text: str) -> int:
    """解析含中文单位的数字，如 '1.2万' -> 12000"""
    import re
    text = text.replace(",", "").replace("，", "")
    nums = re.findall(r'([\d.]+)\s*(万|w|W)?', text)
    if not nums:
        return 0
    try:
        val = float(nums[0][0])
        unit = nums[0][1]
        if unit in ("万", "w", "W"):
            val *= 10000
        return int(val)
    except (ValueError, IndexError):
        return 0


def is_login_page(page) -> bool:
    """小红书登录层可能不改变 URL，优先用页面文本判断。"""
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    login_markers = ["扫码登录", "验证码登录", "登录/注册", "手机号登录", "密码登录", "短信登录", "发送验证码", "登 录"]
    content_markers = ["笔记管理", "数据表现", "发布笔记", "数据分析"]
    if any(marker in text for marker in login_markers):
        return not any(marker in text for marker in content_markers)
    return False


def wait_until_logged_in(page, timeout_ms: int):
    """等待扫码登录完成。登录成功后 URL 可能不变，所以轮询页面文本。"""
    deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=timeout_ms)
    while datetime.datetime.now() < deadline:
        if not is_login_page(page):
            page.wait_for_timeout(3000)
            if not is_login_page(page):
                return
        page.wait_for_timeout(2000)
    raise PlaywrightTimeout("等待小红书扫码登录超时")


def page_has_empty_state(page) -> bool:
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    empty_markers = ["暂无数据", "暂无内容", "还没有发布", "没有找到", "无内容"]
    return any(marker in text for marker in empty_markers)


def matches_target_date(text: str, target_date_str: str) -> bool:
    """匹配完整日期、短日期和“昨天”等平台展示格式。"""
    if not text:
        return False

    target = datetime.date.fromisoformat(target_date_str)
    normalized = text.strip()
    if target_date_str in normalized:
        return True
    if "昨天" in normalized:
        return target == datetime.date.today() - datetime.timedelta(days=1)
    if target.strftime("%m-%d") in normalized:
        return True
    if f"{target.month}月{target.day}日" in normalized:
        return True
    if f"{target.month}/{target.day}" in normalized or target.strftime("%m/%d") in normalized:
        return True
    return False


def dedupe_items(items: list[dict]) -> list[dict]:
    titled_dates = {
        item.get("publish_date", "")
        for item in items
        if item.get("title", "").strip()
    }
    titled_metric_keys = {
        (item.get("publish_date", ""), item.get("views", 0), item.get("likes", 0), item.get("comments", 0))
        for item in items
        if item.get("title", "").strip()
    }
    best_by_key = {}
    for item in items:
        title = item.get("title", "").strip()
        if not title and item.get("publish_date", "") in titled_dates:
            continue
        metric_key = (item.get("publish_date", ""), item.get("views", 0), item.get("likes", 0), item.get("comments", 0))
        if not title and metric_key in titled_metric_keys:
            continue
        key = (item.get("publish_date", ""), title or item.get("views", 0))
        score = len(title) + item.get("views", 0) + item.get("likes", 0) + item.get("comments", 0)
        previous = best_by_key.get(key)
        previous_score = -1
        if previous:
            previous_score = len(previous.get("title", "")) + previous.get("views", 0) + previous.get("likes", 0) + previous.get("comments", 0)
        if previous is None or score > previous_score:
            best_by_key[key] = item
    return list(best_by_key.values())


def save_output(data: dict, output_dir: str):
    """保存采集结果"""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    out_file = path / "xhs_data.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 数据已保存到 {out_file}")


def main():
    args = parse_args()
    target_date_str = target_date(args.date)
    headless = not args.headed

    print(f"📕 小红书数据采集 - 目标日期: {target_date_str}")
    print(f"{'=' * 50}")

    if args.dry_run:
        print("🔍 模拟运行模式")
        result = {
            "platform": PLATFORM,
            "date": target_date_str,
            "items": [],
            "empty": True,
            "error": None,
        }
    else:
        result = scrape_xhs(args.cookie_file, args.output_dir, headless, target_date_str)

    save_output(result, args.output_dir)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
