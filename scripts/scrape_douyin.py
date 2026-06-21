#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音创作者平台 — 内容数据采集器

从 https://creator.douyin.com 采集前一天发布的内容数据。
支持 cookie 持久化、虚拟滚动加载、自动检测过期。
"""

import argparse
import json
import os
import sys
import datetime
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from comments_utils import enrich_items_with_comments, load_self_accounts
from paths import config_dir, cookie_file, output_dir

PLATFORM = "抖音"
BASE_URL = "https://creator.douyin.com"
CONTENT_URL = "https://creator.douyin.com/creator-micro/content/manage"

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_COOKIE_FILE = cookie_file("douyin")
DEFAULT_OUTPUT_DIR = output_dir()
DEFAULT_SELF_ACCOUNTS_FILE = config_dir() / "self_accounts.json"


def parse_args():
    parser = argparse.ArgumentParser(description="抖音创作者平台数据采集")
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
    parser.add_argument("--comments-limit", type=int, default=50,
                        help="每条内容最多采集的评论数，默认 50")
    parser.add_argument("--skip-comments", action="store_true",
                        help="跳过评论明细采集")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    return yesterday.isoformat()


def load_cookies(cookie_file: str) -> dict | None:
    path = Path(cookie_file)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cookies(context, cookie_file: str):
    path = Path(cookie_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"✅ Cookies 已保存到 {cookie_file}")


def scrape_douyin(cookie_file: str, output_dir: str, headless: bool, target_date_str: str, comments_limit: int = 50, skip_comments: bool = False) -> dict:
    """采集抖音内容数据"""
    result = {
        "platform": PLATFORM,
        "date": target_date_str,
        "items": [],
        "empty": True,
        "error": None,
    }

    storage_state_path = Path(cookie_file)
    storage_state = str(storage_state_path) if storage_state_path.exists() else None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        try:
            print(f"📱 正在访问抖音创作者平台...")
            page.goto(CONTENT_URL, wait_until="domcontentloaded", timeout=60000)

            # 检测登录状态
            current_url = page.url
            if is_login_page(page) or "login" in current_url or "passport" in current_url or "sso" in current_url:
                if headless:
                    raise RuntimeError("Cookie 已过期，请使用 --headed 模式重新登录")
                print("🔑 Cookie 已过期，请在打开的浏览器中扫码登录...")
                try:
                    wait_until_logged_in(page, timeout_ms=300000)
                    print("✅ 登录成功！保存新的 cookies...")
                    save_cookies(context, cookie_file)
                except PlaywrightTimeout:
                    raise RuntimeError("登录超时，请重试")
            else:
                print("✅ 已登录")
                save_cookies(context, cookie_file)

            # 等待内容列表加载（抖音通常使用虚拟滚动）
            page.wait_for_timeout(5000)

            # 滚动加载全部内容
            print("🔄 滚动加载内容列表...")
            prev_count = 0
            for i in range(10):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)

                # 检测是否有"加载更多"或"加载中"元素
                loading = page.query_selector("[class*='loading'], [class*='Loading'], .loading-icon")
                if loading:
                    page.wait_for_timeout(2000)

                # 统计当前可见的内容卡片数量
                items = page.query_selector_all(
                    "[class*='card'], [class*='content-item'], [class*='video-card'], "
                    "[class*='post-item'], [class*='work-item'], table tbody tr, "
                    "[class*='DataList'] > div, [class*='list-item']"
                )
                print(f"   第 {i+1} 轮滚动: {len(items)} 条可见")
                if len(items) > 0 and len(items) == prev_count:
                    # 连续两次数量不变，认为已加载完毕
                    page.wait_for_timeout(2000)
                    items_after = page.query_selector_all(
                        "[class*='card'], [class*='content-item'], [class*='video-card'], "
                        "[class*='post-item'], [class*='work-item'], table tbody tr, "
                        "[class*='DataList'] > div, [class*='list-item']"
                    )
                    if len(items_after) == prev_count:
                        break
                prev_count = max(len(items), prev_count)

            # 提取内容数据
            items_raw = page.query_selector_all(
                "[class*='card'], [class*='content-item'], [class*='video-card'], "
                "[class*='post-item'], [class*='work-item'], table tbody tr, "
                "[class*='DataList'] > div, [class*='list-item']"
            )
            print(f"📋 找到 {len(items_raw)} 条内容")

            parsed_items = []
            for item in items_raw:
                try:
                    entry = parse_content_card(item, target_date_str)
                    if entry:
                        parsed_items.append(entry)
                except Exception as e:
                    print(f"⚠️ 解析单条内容时出错: {e}")
                    continue

            # 备选方案：页面文本提取
            if not parsed_items:
                print("🔄 尝试备选解析方案...")
                parsed_items = parse_content_via_page_text(page, target_date_str)

            # 过滤目标日期
            target_items = []
            for item in parsed_items:
                pub_date = item.get("publish_date", "")
                if matches_target_date(pub_date, target_date_str):
                    target_items.append(item)

            if target_items:
                target_items = dedupe_items(target_items)
                target_items = enrich_items_with_comments(
                    context,
                    target_items,
                    "douyin",
                    load_self_accounts(DEFAULT_SELF_ACCOUNTS_FILE),
                    comments_limit,
                    skip_comments,
                )
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
            browser.close()

    return result


def parse_content_card(element, target_date_str: str) -> dict | None:
    """解析单条抖音内容卡片"""
    text = element.inner_text()
    if not text.strip():
        return None

    entry = {
        "publish_date": "",
        "title": "",
        "content": "",
        "content_type": "未知",
        "views": 0,
        "likes": 0,
        "comments": 0,
    }
    href = extract_first_href(element)
    if href:
        entry["detail_url"] = href

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for idx, line in enumerate(lines):
        # 日期
        if any(c in line for c in ["-", "月", "日", "/", ":", "昨天"]) and len(line) < 40:
            # 只匹配短日期格式
            if "昨天" in line:
                entry["publish_date"] = target_date_str
            elif any(y in line for y in [str(datetime.date.today().year), str(datetime.date.today().year - 1)]):
                entry["publish_date"] = line.strip()
            elif re.search(r'\d{2}-\d{2}', line):
                entry["publish_date"] = line.strip()
            elif re.search(r'\d{1,2}月\d{1,2}日', line):
                entry["publish_date"] = line.strip()

        # 指标
        value = parse_metric_value(lines, idx)
        if is_metric_label(line, ["播放", "播放量", "观看", "观看量", "浏览", "浏览量", "阅读", "阅读量"]):
            entry["views"] = value
        elif is_metric_label(line, ["点赞", "点赞量", "赞"]):
            entry["likes"] = value
        elif is_metric_label(line, ["评论", "评论量"]):
            entry["comments"] = value

    entry["title"] = extract_title(lines, entry["publish_date"], target_date_str)
    entry["content"] = extract_content(lines, entry["publish_date"], target_date_str)
    entry["content_type"] = detect_content_type(lines)

    if not entry["title"] and not entry["publish_date"]:
        return None

    return entry


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
        return BASE_URL + href
    return href


def parse_content_via_page_text(page, target_date_str: str) -> list[dict]:
    """备选方案：从页面全文中提取内容数据"""
    body_text = page.inner_text("body")
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    items = []
    current_item = {}
    date_found = False

    for i, line in enumerate(lines):
        # 检测日期行（包含目标日期）
        has_date = matches_target_date(line, target_date_str)

        # 如果发现新日期行，开始新的内容条目
        if has_date and i < len(lines) - 2:
            if current_item and "title" in current_item:
                items.append(current_item)
            current_item = {
                "publish_date": target_date_str,
                "title": "",
                "content": "",
                "content_type": "未知",
                "views": 0,
                "likes": 0,
                "comments": 0,
            }
            date_found = True
            continue

        if date_found and current_item is not None:
            if not current_item["title"] and len(line) < 60 and "播放" not in line and "点赞" not in line:
                current_item["title"] = line
            elif is_metric_label(line, ["播放", "播放量", "观看", "观看量", "浏览", "浏览量", "阅读", "阅读量"]):
                current_item["views"] = parse_metric_value(lines, i)
            elif is_metric_label(line, ["点赞", "点赞量", "赞"]):
                current_item["likes"] = parse_metric_value(lines, i)
            elif is_metric_label(line, ["评论", "评论量"]):
                current_item["comments"] = parse_metric_value(lines, i)

    if current_item and current_item.get("title"):
        items.append(current_item)

    return items


def parse_number(text: str) -> int:
    """解析含中文单位的数字"""
    text = text.replace(",", "").replace("，", "")
    nums = re.findall(r'([\d.]+)\s*(万|w|W|亿)?', text)
    if not nums:
        return 0
    try:
        val = float(nums[0][0])
        unit = nums[0][1]
        if unit in ("亿",):
            val *= 100000000
        elif unit in ("万", "w", "W"):
            val *= 10000
        return int(val)
    except (ValueError, IndexError):
        return 0


def is_login_page(page) -> bool:
    """抖音登录层有时不改 URL，只能通过页面文本判断。"""
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    login_markers = ["扫码登录", "验证码登录", "密码登录", "登录/注册", "需在手机上进行确认"]
    content_markers = ["作品管理", "全部作品", "内容管理"]
    if any(marker in text for marker in login_markers):
        return not any(marker in text for marker in content_markers)
    return False


def wait_until_logged_in(page, timeout_ms: int):
    """等待扫码登录完成。登录成功后 URL 可能不变，所以轮询页面文本。"""
    deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=timeout_ms)
    last_login = True
    while datetime.datetime.now() < deadline:
        if not is_login_page(page):
            page.wait_for_timeout(3000)
            if not is_login_page(page):
                return
        page.wait_for_timeout(2000)
    if last_login:
        raise PlaywrightTimeout("等待抖音扫码登录超时")


def parse_metric_value(lines: list[str], idx: int) -> int:
    """解析当前行或下一行里的指标数字，兼容“播放量\\n123”结构。"""
    value = parse_number(lines[idx])
    if value:
        return value
    if idx + 1 < len(lines):
        return parse_number(lines[idx + 1])
    return 0


def is_metric_label(line: str, labels: list[str]) -> bool:
    normalized = line.strip()
    if normalized in labels:
        return True
    return any(normalized.startswith(label) and parse_number(normalized) > 0 for label in labels)


def extract_title(lines: list[str], publish_date: str, target_date_str: str) -> str:
    blocked = {
        "作品管理", "全部作品", "视频", "图文", "合集", "置顶", "数据", "查看数据",
        "编辑作品", "设置权限", "作品置顶", "删除作品", "已发布",
    }
    candidates = []
    for line in lines:
        if not line or line == publish_date or line in blocked:
            continue
        if matches_target_date(line, target_date_str):
            continue
        if re.fullmatch(r"\d+\s*张", line):
            continue
        if line.startswith("http") or line.startswith("#"):
            continue
        if is_metric_label(line, ["播放", "播放量", "观看", "观看量", "浏览", "浏览量", "阅读", "阅读量", "点赞", "点赞量", "赞", "评论", "评论量", "收藏", "分享", "转发"]):
            continue
        if len(line) >= 6:
            candidates.append(line)

    if not candidates:
        return ""

    title = max(candidates, key=len)
    for sep in ["。", "！", "？", "\n"]:
        if sep in title:
            first = title.split(sep, 1)[0].strip()
            if len(first) >= 6:
                return first + sep if sep != "\n" else first
    return title[:80]


def extract_content(lines: list[str], publish_date: str, target_date_str: str) -> str:
    candidates = []
    blocked = {
        "作品管理", "全部作品", "视频", "图文", "合集", "置顶", "数据", "查看数据",
        "编辑作品", "设置权限", "作品置顶", "删除作品", "已发布",
    }
    for line in lines:
        if not line or line == publish_date or line in blocked:
            continue
        if matches_target_date(line, target_date_str):
            continue
        if re.fullmatch(r"\d+\s*张", line):
            continue
        if is_metric_label(line, ["播放", "播放量", "观看", "观看量", "浏览", "浏览量", "阅读", "阅读量", "点赞", "点赞量", "赞", "评论", "评论量", "收藏", "分享", "转发"]):
            continue
        if line.startswith("http"):
            continue
        if len(line) >= 10:
            candidates.append(line)
    if not candidates:
        return ""
    return max(candidates, key=len)


def detect_content_type(lines: list[str]) -> str:
    joined = "\n".join(lines)
    if re.search(r"\d+\s*张", joined):
        return "图文"
    if "视频" in joined:
        return "视频"
    return "视频/图文"


def dedupe_items(items: list[dict]) -> list[dict]:
    best_by_key = {}
    for item in items:
        key = (item.get("publish_date", ""), item.get("title", ""))
        if not key[1]:
            key = (item.get("publish_date", ""), item.get("views", 0), item.get("likes", 0), item.get("comments", 0))
        score = len(item.get("title", "")) + item.get("views", 0) + item.get("likes", 0) + item.get("comments", 0)
        previous = best_by_key.get(key)
        previous_score = -1
        if previous:
            previous_score = len(previous.get("title", "")) + previous.get("views", 0) + previous.get("likes", 0) + previous.get("comments", 0)
        if previous is None or score > previous_score:
            best_by_key[key] = item
    return list(best_by_key.values())


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


def save_output(data: dict, output_dir: str):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    out_file = path / "douyin_data.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 数据已保存到 {out_file}")


def main():
    args = parse_args()
    target_date_str = target_date(args.date)
    headless = not args.headed

    print(f"📱 抖音数据采集 - 目标日期: {target_date_str}")
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
        result = scrape_douyin(args.cookie_file, args.output_dir, headless, target_date_str, args.comments_limit, args.skip_comments)

    save_output(result, args.output_dir)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
