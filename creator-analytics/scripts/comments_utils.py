#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comment helpers for creator analytics collectors and reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SELF_ROLE_MARKERS = ("作者", "我", "自己", "官方", "置顶作者", "号主")
QUESTION_MARKERS = ("?", "？", "吗", "怎么", "如何", "能不能", "为什么", "哪", "什么")
POSITIVE_MARKERS = ("收藏", "有用", "学到", "清楚", "明白", "期待", "喜欢")
NEGATIVE_MARKERS = ("看不懂", "不懂", "太难", "没懂", "哪里", "问题")


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").replace("，", "").strip()
    match = re.search(r"([\d.]+)\s*(万|w|W|亿)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "亿":
        number *= 100000000
    elif unit in ("万", "w", "W"):
        number *= 10000
    return int(number)


def load_self_accounts(config_path: str | Path | None) -> dict:
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def aliases_for_platform(platform_key: str, self_accounts: dict | None) -> set[str]:
    config = (self_accounts or {}).get(platform_key, {})
    if isinstance(config, list):
        aliases = config
    else:
        aliases = config.get("aliases") or config.get("names") or []
    return {str(alias).strip().casefold() for alias in aliases if str(alias).strip()}


def classify_comment_author(author_name: str | None, author_role: str | None, platform_key: str, self_accounts: dict | None) -> bool | None:
    name = (author_name or "").strip()
    role = (author_role or "").strip()
    if not name and not role:
        return None

    aliases = aliases_for_platform(platform_key, self_accounts)
    if name and name.casefold() in aliases:
        return True
    if role and any(marker in role for marker in SELF_ROLE_MARKERS):
        return True
    return False


def normalize_comment(raw: dict, platform_key: str, self_accounts: dict | None) -> dict:
    author_name = (raw.get("author_name") or raw.get("nickname") or raw.get("user_name") or "").strip()
    author_role = (raw.get("author_role") or raw.get("role") or "").strip()
    content = (raw.get("content") or raw.get("text") or "").strip()
    like_count = safe_int(raw.get("like_count") if raw.get("like_count") is not None else raw.get("likes"))
    is_self = raw.get("is_self")
    if is_self is None:
        is_self = classify_comment_author(author_name, author_role, platform_key, self_accounts)

    return {
        "comment_id": str(raw.get("comment_id") or raw.get("id") or ""),
        "author_name": author_name,
        "author_role": author_role,
        "content": content,
        "publish_time": raw.get("publish_time") or raw.get("time") or "",
        "like_count": like_count,
        "reply_to": raw.get("reply_to"),
        "is_self": is_self,
        "source_area": raw.get("source_area") or "detail_comments",
        "collection_status": raw.get("collection_status") or ("ok" if content else "empty"),
    }


def normalize_comments(raw_comments: list[dict], platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    normalized = [normalize_comment(raw, platform_key, self_accounts) for raw in raw_comments[: max(limit, 0)]]
    return [comment for comment in normalized if comment.get("content")]


def parse_comment_blocks_from_text(text: str, platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    raw_comments: list[dict] = []
    blocked = {"评论", "留言", "回复", "点赞", "展开", "收起", "查看更多", "暂无评论"}
    for idx, line in enumerate(lines):
        if line in blocked or len(line) < 2:
            continue
        if len(line) > 240:
            continue
        if any(marker in line for marker in ("播放", "阅读", "收藏", "分享")) and safe_int(line) is not None:
            continue
        previous = lines[idx - 1] if idx > 0 else ""
        raw_comments.append(
            {
                "comment_id": f"{platform_key}-{idx}",
                "author_name": previous if previous and len(previous) <= 40 and previous not in blocked else "",
                "content": line,
                "source_area": "page_text_comments",
            }
        )
        if len(raw_comments) >= limit:
            break
    return normalize_comments(raw_comments, platform_key, self_accounts, limit)


def extract_comments_from_page(page, platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    selectors = [
        "[class*='comment']",
        "[class*='Comment']",
        "[class*='reply']",
        "[class*='Reply']",
        "[class*='留言']",
        "[class*='评论']",
    ]
    raw_comments: list[dict] = []
    for selector in selectors:
        try:
            blocks = page.query_selector_all(selector)
        except Exception:
            blocks = []
        for idx, block in enumerate(blocks):
            try:
                text = block.inner_text().strip()
            except Exception:
                continue
            raw = comment_from_block_text(text, platform_key, idx)
            if raw:
                raw_comments.append(raw)
            if len(raw_comments) >= limit:
                return normalize_comments(raw_comments, platform_key, self_accounts, limit)
        if raw_comments:
            break
    if raw_comments:
        return normalize_comments(raw_comments, platform_key, self_accounts, limit)
    try:
        return parse_comment_blocks_from_text(page.inner_text("body", timeout=10000), platform_key, self_accounts, limit)
    except Exception:
        return []


def comment_from_block_text(text: str, platform_key: str, idx: int) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    author = lines[0] if len(lines[0]) <= 40 else ""
    content_candidates = [line for line in lines[1:] if len(line) >= 2]
    if not content_candidates and author:
        content_candidates = [author]
        author = ""
    if not content_candidates:
        return None
    content = max(content_candidates, key=len)
    if len(content) > 240:
        content = content[:240]
    like_count = None
    for line in lines:
        if any(label in line for label in ("赞", "点赞")):
            like_count = safe_int(line)
            break
    return {
        "comment_id": f"{platform_key}-{idx}",
        "author_name": author,
        "content": content,
        "like_count": like_count,
        "source_area": "detail_comments",
    }


def collect_comments_from_url(context, url: str, platform_key: str, self_accounts: dict | None, limit: int = 50) -> tuple[list[dict], str]:
    if not url:
        return [], "no_detail_url"
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        click_comment_entry(page)
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)
        comments = extract_comments_from_page(page, platform_key, self_accounts, limit)
        return comments, "ok" if comments else "empty"
    except Exception as exc:
        return [], f"failed: {exc}"
    finally:
        try:
            page.close()
        except Exception:
            pass


def click_comment_entry(page):
    labels = ("评论", "留言", "全部评论", "查看评论", "互动")
    for label in labels:
        try:
            locator = page.get_by_text(label, exact=False).first
            if locator.count():
                locator.click(timeout=2000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue


def enrich_items_with_comments(context, items: list[dict], platform_key: str, self_accounts: dict | None, limit: int = 50, skip_comments: bool = False) -> list[dict]:
    for item in items:
        if skip_comments or limit <= 0:
            item["comments_detail"] = []
            item["comment_collection_status"] = "skipped"
            continue
        url = item.get("detail_url") or item.get("source_url") or ""
        comments, status = collect_comments_from_url(context, url, platform_key, self_accounts, limit)
        item["comments_detail"] = comments
        item["comment_collection_status"] = status
    return items


def summarize_comment_insights(items: list[dict]) -> dict:
    comments = []
    failures = []
    for item in items:
        status = item.get("comment_collection_status")
        if status and status not in ("ok", "empty", "skipped"):
            failures.append({"platform": item.get("platform"), "title": item.get("title"), "status": status})
        for comment in item.get("comments_detail") or []:
            comments.append({**comment, "_platform": item.get("platform"), "_title": item.get("title")})

    other_comments = [comment for comment in comments if comment.get("is_self") is False]
    self_comments = [comment for comment in comments if comment.get("is_self") is True]
    unknown_comments = [comment for comment in comments if comment.get("is_self") is None]
    questions = [comment for comment in other_comments if is_question(comment.get("content", ""))]
    positives = [comment for comment in other_comments if has_any(comment.get("content", ""), POSITIVE_MARKERS)]
    negatives = [comment for comment in other_comments if has_any(comment.get("content", ""), NEGATIVE_MARKERS)]

    return {
        "total_comments": len(comments),
        "other_comments": len(other_comments),
        "self_comments": len(self_comments),
        "unknown_comments": len(unknown_comments),
        "self_reply_coverage": f"{len(self_comments)}/{len(other_comments)}" if other_comments else "0/0",
        "other_summary": summarize_lines(other_comments, "用户评论"),
        "self_summary": summarize_lines(self_comments, "自己账号回复"),
        "positive_feedback": summarize_lines(positives, "正向反馈"),
        "negative_feedback": summarize_lines(negatives, "疑问/阻力"),
        "unanswered_questions": compact_comment_refs(questions[:5]),
        "next_topic_candidates": compact_comment_refs((questions or other_comments)[:5]),
        "collection_failures": failures,
    }


def is_question(text: str) -> bool:
    return has_any(text, QUESTION_MARKERS)


def has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def summarize_lines(comments: list[dict], prefix: str) -> list[str]:
    lines = []
    for comment in sorted(comments, key=lambda row: row.get("like_count") or 0, reverse=True)[:5]:
        content = comment.get("content", "")
        if len(content) > 60:
            content = content[:58] + "..."
        lines.append(f"{prefix}: {content}")
    return lines


def compact_comment_refs(comments: list[dict]) -> list[dict]:
    refs = []
    for comment in comments:
        refs.append(
            {
                "platform": comment.get("_platform") or comment.get("platform"),
                "title": comment.get("_title") or comment.get("title"),
                "author_name": comment.get("author_name"),
                "content": comment.get("content"),
                "like_count": comment.get("like_count"),
            }
        )
    return refs
