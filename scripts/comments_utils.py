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
VALID_CONFIDENCE = {"high", "medium", "low"}
COMMENT_SELECTORS_BY_PLATFORM = {
    "xhs": ("[class*='comment-item']", "[class*='commentItem']", "[class*='comment-card']", "[class*='reply-item']"),
    "douyin": ("[class*='comment-item']", "[class*='CommentItem']", "[class*='reply-item']", "[class*='commentContent']"),
    "wechat": ("[class*='comment_item']", "[class*='comment-item']", "[class*='reply_item']", "[class*='留言']"),
}
NON_COMMENT_MARKERS = (
    "作品管理", "全部作品", "查看数据", "编辑作品", "发布笔记", "发布作品", "数据表现",
    "播放量", "播放", "浏览", "阅读", "点赞量", "收藏", "分享", "转发", "已发布",
)
UI_ONLY_LINES = {"评论", "留言", "回复", "点赞", "展开", "收起", "查看更多", "暂无评论", "全部评论", "互动"}


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
        "confidence": normalize_confidence(raw.get("confidence"), author_name, content),
    }


def normalize_comments(raw_comments: list[dict], platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    normalized = [normalize_comment(raw, platform_key, self_accounts) for raw in raw_comments[: max(limit, 0)]]
    return [comment for comment in normalized if comment.get("content")]


def normalize_confidence(value: Any, author_name: str, content: str) -> str:
    if value in VALID_CONFIDENCE:
        return str(value)
    if author_name and content:
        return "high" if is_question(content) or has_any(content, POSITIVE_MARKERS + NEGATIVE_MARKERS) else "medium"
    if content:
        return "low"
    return "low"


def parse_comment_blocks_from_text(text: str, platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    return extract_platform_comments_from_blocks(text.split("\n\n"), platform_key, self_accounts, limit)


def extract_platform_comments_from_blocks(block_texts: list[str], platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    raw_comments = []
    for idx, text in enumerate(block_texts):
        raw = comment_from_block_text(text, platform_key, idx)
        if raw:
            raw_comments.append(raw)
        if len(raw_comments) >= limit:
            break
    return normalize_comments(raw_comments, platform_key, self_accounts, limit)


def extract_comments_from_page(page, platform_key: str, self_accounts: dict | None, limit: int = 50) -> list[dict]:
    selectors = COMMENT_SELECTORS_BY_PLATFORM.get(platform_key, ())
    block_texts = []
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
            if text:
                block_texts.append(text)
        if block_texts:
            break
    return extract_platform_comments_from_blocks(block_texts, platform_key, self_accounts, limit)


def comment_from_block_text(text: str, platform_key: str, idx: int) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if looks_like_non_comment_block(lines):
        return None
    cleaned = [line for line in lines if not is_ui_line(line)]
    if not cleaned:
        return None
    author = cleaned[0] if is_probable_author_line(cleaned[0]) and len(cleaned) > 1 else ""
    candidate_lines = cleaned[1:] if author else cleaned
    content_candidates = [line for line in candidate_lines if is_probable_comment_content(line)]
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
        "confidence": "high" if author and content else "low",
    }


def is_ui_line(line: str) -> bool:
    stripped = line.strip()
    if stripped in UI_ONLY_LINES:
        return True
    if re.fullmatch(r"\d+\s*(赞|点赞|回复|条评论)?", stripped):
        return True
    return False


def is_metric_line(line: str) -> bool:
    return any(marker in line for marker in NON_COMMENT_MARKERS) and safe_int(line) is not None


def is_probable_author_line(line: str) -> bool:
    if len(line) > 40 or is_ui_line(line) or is_metric_line(line):
        return False
    return not is_question(line) and not has_any(line, POSITIVE_MARKERS + NEGATIVE_MARKERS)


def is_probable_comment_content(line: str) -> bool:
    if len(line) < 2 or len(line) > 240:
        return False
    if is_ui_line(line) or is_metric_line(line):
        return False
    if any(marker in line for marker in ("http://", "https://")):
        return False
    return True


def looks_like_non_comment_block(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    metric_hits = sum(1 for marker in NON_COMMENT_MARKERS if marker in joined)
    has_user_signal = any(is_question(line) or has_any(line, POSITIVE_MARKERS + NEGATIVE_MARKERS) for line in lines)
    if metric_hits >= 2 and not has_user_signal:
        return True
    if any(line in ("作品管理", "全部作品", "查看数据", "编辑作品") for line in lines):
        return True
    return False


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
        if page_requires_login(page):
            return [], "login_required"
        has_container = page_has_comment_container(page, platform_key)
        comments = extract_comments_from_page(page, platform_key, self_accounts, limit)
        if comments:
            return comments, "ok"
        return [], "empty" if has_container else "no_comment_container"
    except Exception as exc:
        return [], f"failed: {exc}"
    finally:
        try:
            page.close()
        except Exception:
            pass


def page_has_comment_container(page, platform_key: str) -> bool:
    for selector in COMMENT_SELECTORS_BY_PLATFORM.get(platform_key, ()):
        try:
            if page.query_selector_all(selector):
                return True
        except Exception:
            continue
    return False


def page_requires_login(page) -> bool:
    try:
        text = page.inner_text("body", timeout=3000)
    except Exception:
        return False
    return any(marker in text for marker in ("扫码登录", "登录/注册", "密码登录", "验证码登录", "请使用微信扫描二维码"))


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
    health = {"ok": 0, "empty": 0, "skipped": 0, "no_detail_url": 0, "no_comment_container": 0, "login_required": 0, "failed": 0}
    for item in items:
        status = item.get("comment_collection_status")
        if status:
            status_key = "failed" if str(status).startswith("failed") else status
            health[status_key] = health.get(status_key, 0) + 1
        if status and status not in ("ok", "empty", "skipped"):
            failures.append({"platform": item.get("platform"), "title": item.get("title"), "status": status})
        for comment in item.get("comments_detail") or []:
            comments.append({**comment, "_platform": item.get("platform"), "_title": item.get("title")})

    other_comments = [comment for comment in comments if comment.get("is_self") is False]
    self_comments = [comment for comment in comments if comment.get("is_self") is True]
    unknown_comments = [comment for comment in comments if comment.get("is_self") is None]
    trusted_other_comments = [comment for comment in other_comments if comment_confidence(comment) in ("high", "medium")]
    questions = [comment for comment in trusted_other_comments if is_question(comment.get("content", ""))]
    positives = [comment for comment in other_comments if has_any(comment.get("content", ""), POSITIVE_MARKERS)]
    negatives = [comment for comment in other_comments if has_any(comment.get("content", ""), NEGATIVE_MARKERS)]
    unanswered = build_unanswered_questions(other_comments, self_comments)
    topic_candidates = (questions or trusted_other_comments)[:5]

    return {
        "total_comments": len(comments),
        "other_comments": len(other_comments),
        "self_comments": len(self_comments),
        "unknown_comments": len(unknown_comments),
        "self_reply_ratio": f"{len(self_comments)}/{len(other_comments)}" if other_comments else "0/0",
        "self_reply_coverage": f"{len(self_comments)}/{len(other_comments)}" if other_comments else "0/0",
        "comment_collection_health": health,
        "other_summary": summarize_lines(other_comments, "用户评论"),
        "self_reply_summary": summarize_lines(self_comments, "自己账号回复"),
        "self_summary": summarize_lines(self_comments, "自己账号回复"),
        "positive_feedback": summarize_lines(positives, "正向反馈"),
        "negative_feedback": summarize_lines(negatives, "疑问/阻力"),
        "user_questions": compact_comment_refs(questions[:5]),
        "unanswered_questions": compact_comment_refs(unanswered[:5]),
        "topic_candidates_from_comments": compact_comment_refs(topic_candidates),
        "next_topic_candidates": compact_comment_refs(topic_candidates),
        "collection_failures": failures,
    }


def build_unanswered_questions(other_comments: list[dict], self_comments: list[dict]) -> list[dict]:
    if not any(comment.get("reply_to") for comment in self_comments + other_comments):
        return []
    answered = {str(comment.get("reply_to")) for comment in self_comments if comment.get("reply_to")}
    unanswered = []
    for comment in other_comments:
        comment_id = str(comment.get("comment_id") or "")
        if not is_question(comment.get("content", "")):
            continue
        if comment_id and comment_id in answered:
            continue
        unanswered.append(comment)
    return unanswered


def comment_confidence(comment: dict) -> str:
    value = comment.get("confidence")
    if value in VALID_CONFIDENCE:
        return value
    if comment.get("author_name") and comment.get("content"):
        return "medium"
    if comment.get("content"):
        return "low"
    return "low"


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
