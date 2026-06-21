#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load real next-topic candidates from the local Meihua workflow."""

from __future__ import annotations

import re
from pathlib import Path


SOURCE_PATTERNS = [
    ("公众号排期", "wechat", ("公众号专区", "运营排期"), 100),
    ("公众号选题库", "wechat", ("公众号专区", "内容策划", "选题库"), 90),
    ("公众号已发布标题", "wechat", ("公众号专区", "已发布内容"), 70),
    ("小红书过往标题", "xhs", ("小红书专区", "过往内容库"), 60),
    ("抖音过往标题", "douyin", ("抖音专区", "过往内容库"), 60),
]

STOP_CELLS = {
    "日期",
    "平台",
    "标题",
    "主题",
    "状态",
    "备注",
    "公众号",
    "小红书",
    "抖音",
    "待写",
    "待发布",
    "已发布",
    "完成",
    "公众号选题池",
    "选题池",
}

PLACEHOLDER_PHRASES = {"上一条高互动内容", "把高互动主题案例化", "把最高互动内容继续案例化"}


def clean_candidate_title(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"^[#>\-+*\d.、\s]+", "", text.strip())
    text = re.sub(r"^【?主?标题[备选选项A-Z/（）() 0-9]*】?[：:｜|\s]*", "", text)
    text = re.sub(r"^封面标题[：:｜|\s]*", "", text)
    text = text.strip(" 「」“”《》|｜\t")
    return re.sub(r"\s+", " ", text)


def looks_like_title(text: str) -> bool:
    title = clean_candidate_title(text)
    if not (6 <= len(title) <= 60):
        return False
    if title in STOP_CELLS:
        return False
    if any(phrase in title for phrase in PLACEHOLDER_PHRASES):
        return False
    if re.fullmatch(r"[-:：|｜\s]+", title):
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", title):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", title))


def extract_markdown_titles(path: Path) -> list[str]:
    titles: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()

    in_title_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            if "已归档" in stripped:
                continue
            cells = [clean_candidate_title(cell) for cell in stripped.strip("|").split("|")]
            cells = [cell for cell in cells if looks_like_title(cell)]
            if cells:
                titles.append(max(cells, key=len))
            continue

        if re.match(r"^#{1,4}\s+", stripped):
            heading = clean_candidate_title(re.sub(r"^#{1,4}\s+", "", stripped))
            in_title_section = any(key in heading for key in ("标题", "选题", "排期"))
            if looks_like_title(heading) and not any(
                key in heading
                for key in ("标题备选", "标题选项", "选题判断", "发布时间建议", "发布后", "数据复盘")
            ):
                titles.append(heading)
            continue

        if in_title_section or any(key in stripped for key in ("标题", "选题")):
            candidate = stripped
            if "|" in candidate and not candidate.startswith("|"):
                candidate = candidate.split("|")[-1]
            if "：" in candidate or ":" in candidate:
                candidate = re.split(r"[：:]", candidate, maxsplit=1)[-1]
            candidate = clean_candidate_title(candidate)
            if looks_like_title(candidate):
                titles.append(candidate)

    if not titles and looks_like_title(path.stem):
        titles.append(clean_candidate_title(path.stem))
    return titles


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for candidate in sorted(candidates, key=lambda row: -row["priority"]):
        key = candidate["title"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append({k: v for k, v in candidate.items() if k != "priority"})
    return deduped


def load_workflow_topic_candidates(workflow_root: str | Path | None, limit: int = 30) -> list[dict]:
    if not workflow_root:
        return []
    root = Path(workflow_root)
    if not root.exists():
        return []

    candidates: list[dict] = []
    for source_type, platform, parts, priority in SOURCE_PATTERNS:
        source_dir = root.joinpath(*parts)
        if not source_dir.exists():
            continue
        for path in source_dir.rglob("*.md"):
            for title in extract_markdown_titles(path):
                candidates.append(
                    {
                        "title": title,
                        "platform": platform,
                        "source_type": source_type,
                        "source_path": str(path),
                        "priority": priority,
                    }
                )
    return dedupe_candidates(candidates)[:limit]
