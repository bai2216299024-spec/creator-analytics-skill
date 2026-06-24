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
from comments_utils import enrich_items_with_comments, load_self_accounts
from paths import config_dir, cookie_file, data_dir, output_dir, profile_dir
from wechat_api_client import WeChatApiError, collect_wechat_api

PLATFORM = "微信公众号"
HOME_URL = "https://mp.weixin.qq.com/"
LOGIN_URL = "https://mp.weixin.qq.com/cgi-bin/loginpage?t=wxm2-login&lang=zh_CN"
APPMSG_URL = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
DEFAULT_COOKIE_FILE = cookie_file("wechat")
DEFAULT_OUTPUT_DIR = output_dir()
DEFAULT_PROFILE_DIR = profile_dir("wechat")
DEFAULT_SELF_ACCOUNTS_FILE = config_dir() / "self_accounts.json"
DEFAULT_API_CONFIG_FILE = config_dir() / "wechat_api.json"
DEFAULT_API_TOKEN_CACHE_FILE = cookie_file("wechat_api_token")
DEFAULT_MANUAL_IMPORT_DIR = data_dir() / "manual"


def parse_args():
    parser = argparse.ArgumentParser(description="微信公众号后台数据采集")
    parser.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE), help="Cookie 文件路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser.add_argument("--headed", action="store_true", help="打开浏览器窗口（首次登录用）")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际采集")
    parser.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--comments-limit", type=int, default=50, help="每条内容最多采集的评论数，默认 50")
    parser.add_argument("--skip-comments", action="store_true", help="跳过评论明细采集")
    parser.add_argument("--browser-channel", default="chrome", choices=["chrome", "msedge", "chromium"],
                        help="公众号采集优先使用的浏览器通道，默认 chrome；不可用时回退 chromium")
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


def profile_init_notice(profile_exists: bool, cookie_exists: bool) -> str:
    if not profile_exists and cookie_exists:
        return "检测到旧 wechat_cookies.json，但尚未建立 data/browser/wechat_profile/；需要 headed 登录一次以建立公众号 profile。"
    if not profile_exists:
        return "尚未建立 data/browser/wechat_profile/；首次运行需要 headed 登录一次以保存公众号登录态。"
    return ""


def scrape_wechat(
    cookie_path: str,
    output_path: str,
    headless: bool,
    target_date_str: str,
    comments_limit: int = 50,
    skip_comments: bool = False,
    browser_channel: str = "chrome",
) -> dict:
    result = {
        "platform": PLATFORM,
        "date": target_date_str,
        "items": [],
        "empty": True,
        "error": None,
        "collection_status": "pending",
        "empty_reason": None,
        "login_status": "unknown",
        "collection_method": "web",
    }
    manual_result = load_manual_import(target_date_str)
    if manual_result:
        result.update(manual_result)
        return result

    api_result = try_collect_wechat_api(target_date_str, comments_limit, skip_comments)
    if api_result.get("available") and not api_result.get("error"):
        result["collection_method"] = "api"
        result["login_status"] = "api_credentials"
        result["items"] = api_result.get("items") or []
        result["empty"] = not bool(result["items"])
        result["collection_status"] = "ok" if result["items"] else "empty"
        result["empty_reason"] = None if result["items"] else "no_matching_date"
        if api_result.get("api_metric_errors"):
            result["api_metric_errors"] = api_result["api_metric_errors"]
        return result
    result["api_status"] = api_result.get("error") or "api_not_configured"
    if api_result.get("unsupported"):
        result["collection_method"] = "manual_import"
        result["collection_status"] = "skipped"
        result["empty_reason"] = "api_unsupported"
        result["login_status"] = "not_applicable"
        result["error"] = None
        result["manual_import_expected"] = str(DEFAULT_MANUAL_IMPORT_DIR / f"wechat_{target_date_str}.json")
        return result
    if api_result.get("available") and api_result.get("error"):
        result["collection_method"] = "api"
        result["collection_status"] = "failed"
        result["empty_reason"] = "api_error"
        result["login_status"] = "api_credentials"
        result["error"] = api_result["error"]
        return result

    notice = profile_init_notice(DEFAULT_PROFILE_DIR.exists(), Path(cookie_path).exists())
    if notice:
        print(f"ℹ️ {notice}")

    with sync_playwright() as p:
        try:
            context = launch_wechat_context(p, headless, browser_channel)
        except Exception as e:
            mark_browser_launch_failure(result, e)
            print(f"❌ 微信公众号浏览器启动失败: {result['error']}")
            return result
        page = context.new_page()
        try:
            print("📰 正在访问微信公众号后台...")
            page.goto(APPMSG_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            if is_relogin_page(page) or is_login_page(page):
                if headless:
                    result["collection_status"] = "login_required"
                    result["login_status"] = "expired_headless"
                    result["empty_reason"] = "login_required"
                    raise RuntimeError("微信公众号登录态过期，请使用 --headed 模式扫码登录")
                if is_relogin_page(page):
                    print("🔑 微信公众号显示“请重新登录”，正在跳转到扫码登录入口...")
                    open_login_entry(page)
                    if is_relogin_page(page):
                        result["collection_status"] = "login_required"
                        result["login_status"] = "relogin_entry_unavailable"
                        result["empty_reason"] = "login_required"
                        raise RuntimeError("微信公众号只显示“请重新登录”，未能打开扫码登录入口")
                print("🔑 请在打开的浏览器中扫码登录微信公众号后台...")
                result["login_status"] = "manual_login_required"
                wait_until_logged_in(page, timeout_ms=300000)
                result["login_status"] = "manual_login_completed"
                page.goto(APPMSG_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            else:
                result["login_status"] = "profile_reused"

            verify_backend_access(page, result)
            save_cookies(context, cookie_path)

            items = parse_items(page, target_date_str)
            if items:
                result["items"] = enrich_items_with_comments(
                    context,
                    dedupe_items(items),
                    "wechat",
                    load_self_accounts(DEFAULT_SELF_ACCOUNTS_FILE),
                    comments_limit,
                    skip_comments,
                )
                result["empty"] = False
                result["collection_status"] = "ok"
                print(f"🎯 找到 {len(result['items'])} 条昨日公众号内容")
            else:
                empty_status = classify_empty_page(page, target_date_str)
                result.update(empty_status)
                if result.get("collection_status") in {"list_unreadable", "login_required", "failed"}:
                    result["error"] = f"微信公众号列表不可确认：{result.get('empty_reason') or result.get('collection_status')}"
                print(f"📭 公众号未抓到目标日期内容：{empty_status.get('empty_reason')}")
        except Exception as e:
            emsg = str(e)
            if result.get("collection_status") == "pending":
                result["collection_status"] = "failed"
            result["error"] = emsg
            if "Target page" in emsg or "context or browser has been closed" in emsg:
                result["error"] += " — 微信浏览器页面意外关闭，请检查是否有其他程序占用 browser profile"
                print(f"❌ 微信公众号采集异常（页面关闭）: {emsg}")
                print(f"   ➜ 建议：关闭其他微信采集窗口，然后单独运行: --platform wechat --headed")
            else:
                print(f"❌ 微信公众号采集异常: {e}")
        finally:
            context.close()
    return result


def load_manual_import(target_date_str: str) -> dict | None:
    manual_file = DEFAULT_MANUAL_IMPORT_DIR / f"wechat_{target_date_str}.json"
    if not manual_file.exists():
        return None
    with manual_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        items = data
    else:
        items = data.get("items") or []
    return {
        "collection_method": "manual_import",
        "collection_status": "ok" if items else "empty",
        "empty": not bool(items),
        "empty_reason": None if items else "manual_import_empty",
        "login_status": "not_applicable",
        "items": items,
        "manual_import_file": str(manual_file),
        "error": None,
    }


def try_collect_wechat_api(target_date_str: str, comments_limit: int, skip_comments: bool) -> dict:
    try:
        api_result = collect_wechat_api(
            DEFAULT_API_CONFIG_FILE,
            DEFAULT_API_TOKEN_CACHE_FILE,
            target_date_str,
            comments_limit,
            skip_comments,
        )
    except WeChatApiError as exc:
        error = str(exc)
        if error.startswith("api_unsupported:"):
            return {"available": True, "unsupported": True, "error": error, "items": []}
        return {"available": True, "error": error, "items": []}
    if not api_result.get("available"):
        return {"available": False, "error": api_result.get("error") or "api_not_configured", "items": []}
    print("✅ 微信公众号使用官方 API 完成采集")
    return api_result


def launch_wechat_context(playwright, headless: bool, browser_channel: str):
    channels = []
    if browser_channel and browser_channel != "chromium":
        channels.append(browser_channel)
    channels.append(None)
    last_error = None
    for channel in channels:
        try:
            launch_options = {
                "user_data_dir": str(DEFAULT_PROFILE_DIR),
                "headless": headless,
                "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                "viewport": {"width": 1440, "height": 900},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
            }
            if channel:
                launch_options["channel"] = channel
                print(f"🌐 微信公众号采集使用系统浏览器通道: {channel}")
            else:
                print("🌐 微信公众号采集回退到 Playwright Chromium")
            return playwright.chromium.launch_persistent_context(**launch_options)
        except Exception as exc:
            last_error = exc
            if channel:
                print(f"⚠️ 系统浏览器通道 {channel} 启动失败，准备回退 Chromium: {exc}")
                continue
            raise
    raise last_error


def mark_browser_launch_failure(result: dict, error: Exception):
    message = str(error)
    result["collection_status"] = "failed"
    result["empty_reason"] = "browser_profile_locked"
    result["login_status"] = "browser_launch_failed"
    if "user data" in message.lower() or "profile" in message.lower() or "Target page" in message:
        result["error"] = "微信公众号浏览器 profile 可能已被另一个窗口占用，请关闭已打开的公众号采集浏览器后重试"
    elif "connection refused" in message.lower() or "closed" in message.lower():
        result["error"] = "微信公众号浏览器连接断开，请检查浏览器是否有异常崩溃"
    else:
        result["error"] = f"微信公众号浏览器启动失败: {message}"


def verify_backend_access(page, result: dict):
    """Fail loudly when WeChat still shows login after a manual/profile login attempt."""
    if is_backend_page(page):
        return
    if result.get("login_status") == "manual_login_completed":
        result["login_status"] = "manual_login_not_accepted"
    elif result.get("login_status") == "profile_reused":
        result["login_status"] = "profile_expired"
    result["collection_status"] = "login_required"
    result["empty_reason"] = "login_required"
    raise RuntimeError("微信公众号登录后仍未进入后台采集页，请重新扫码或检查该账号是否有公众号后台权限")


def classify_empty_page(page, target_date_str: str) -> dict:
    """Explain why WeChat returned no items, without treating every empty result as no publish."""
    if is_login_page(page):
        return {
            "collection_status": "login_required",
            "empty_reason": "login_required",
        }

    try:
        text = page.inner_text("body", timeout=10000)
    except Exception:
        return {
            "collection_status": "list_unreadable",
            "empty_reason": "body_unreadable",
        }

    backend_markers = ["首页", "新的创作", "发表记录", "内容管理", "统计", "群发", "已发表"]
    list_markers = ["发表记录", "已发表", "群发记录", "发布记录", "appmsgpublish"]
    empty_markers = ["暂无", "没有", "无数据", "暂无数据", "还没有"]

    if not any(marker in text for marker in backend_markers):
        return {
            "collection_status": "list_unreadable",
            "empty_reason": "backend_not_confirmed",
        }

    if matches_target_date(text, target_date_str):
        return {
            "collection_status": "list_unreadable",
            "empty_reason": "target_date_visible_but_parse_failed",
        }

    if any(marker in text for marker in list_markers):
        return {
            "collection_status": "empty",
            "empty_reason": "no_matching_date",
        }

    if any(marker in text for marker in empty_markers):
        return {
            "collection_status": "empty",
            "empty_reason": "empty_list_visible",
        }

    return {
        "collection_status": "list_unreadable",
        "empty_reason": "no_publish_list_marker",
    }


def is_login_page(page) -> bool:
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    login_markers = ["微信公众平台", "扫码登录", "请使用微信扫描二维码", "登录"]
    return any(marker in text for marker in login_markers) and not is_backend_page(page)


def is_backend_page(page) -> bool:
    try:
        text = page.inner_text("body", timeout=5000)
        url = page.url
    except Exception:
        return False
    backend_markers = ["首页", "新的创作", "发表记录", "内容管理", "统计", "群发", "已发表"]
    backend_urls = ("cgi-bin/home", "cgi-bin/appmsgpublish", "cgi-bin/appmsg", "cgi-bin/newoperatevote")
    return any(marker in text for marker in backend_markers) or any(marker in url for marker in backend_urls)


def is_relogin_page(page) -> bool:
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    return "请重新登录" in text or "重新登录" in text


def open_login_entry(page):
    for url in (LOGIN_URL, HOME_URL):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if not is_relogin_page(page):
            return


def wait_until_logged_in(page, timeout_ms: int):
    deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=timeout_ms)
    while datetime.datetime.now() < deadline:
        try:
            if is_backend_page(page):
                return
            page.wait_for_timeout(2000)
        except PlaywrightTimeout:
            # 检查页面是否仍然可用
            try:
                page.title()
            except Exception:
                raise RuntimeError("微信公众号页面已关闭（可能是浏览器崩溃或 profile 被占用），请关闭其他微信采集窗口后重试")
        except Exception as e:
            # 捕获页面导航/关闭等异常
            emsg = str(e)
            if "Target page" in emsg or "browser has been closed" in emsg or "context" in emsg.lower():
                raise RuntimeError(f"微信公众号浏览器页面意外关闭: {e}")
            raise
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
        result = {
            "platform": PLATFORM,
            "date": date_str,
            "items": [],
            "empty": True,
            "error": None,
            "collection_status": "skipped",
            "empty_reason": "dry_run",
            "login_status": "not_checked",
        }
    else:
        result = scrape_wechat(
            args.cookie_file,
            args.output_dir,
            not args.headed,
            date_str,
            args.comments_limit,
            args.skip_comments,
            args.browser_channel,
        )
    save_output(result, args.output_dir)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
