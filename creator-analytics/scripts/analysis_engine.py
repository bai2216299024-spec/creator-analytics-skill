#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analysis engine for creator analytics daily reports."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from comments_utils import summarize_comment_insights

PLATFORM_NAMES = {
    "xhs": "小红书",
    "douyin": "抖音",
    "wechat": "微信公众号",
}

METRIC_ALIASES = {
    "views": ("views", "reads"),
    "likes": ("likes",),
    "comments": ("comments",),
    "collects": ("collects",),
    "shares": ("shares",),
    "wows": ("wows", "watching"),
}

FALLBACK_BASELINES = {
    "小红书": {"views": 100, "likes": 5, "comments": 2, "collects": 3},
    "抖音": {"views": 100, "likes": 3, "comments": 1},
    "微信公众号": {"views": 80, "likes": 2, "comments": 1, "wows": 1},
}


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def metric(item: dict, name: str) -> int:
    metrics = item.get("metrics") or {}
    for key in METRIC_ALIASES.get(name, (name,)):
        value = safe_int(metrics.get(key))
        if value is not None:
            return value
    return 0


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def format_number(n: Any) -> str:
    value = safe_int(n) or 0
    if value >= 100000000:
        return f"{value / 100000000:.2f}亿"
    if value >= 10000:
        return f"{value / 10000:.1f}万"
    return str(value)


def load_json(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_benchmark_config(path: str | Path | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_platform_data(platform_key: str, data: dict | None) -> list[dict]:
    if not data or data.get("error"):
        return []

    platform = data.get("platform") or PLATFORM_NAMES.get(platform_key, platform_key)
    normalized = []
    for raw in data.get("items", []):
        metrics = {
            "views": raw.get("views") if raw.get("views") is not None else raw.get("reads"),
            "likes": raw.get("likes"),
            "comments": raw.get("comments"),
            "collects": raw.get("collects"),
            "shares": raw.get("shares"),
            "wows": raw.get("wows") if raw.get("wows") is not None else raw.get("watching"),
        }
        metrics = {k: v for k, v in metrics.items() if v is not None}
        normalized.append(
            {
                "platform": platform,
                "platform_key": platform_key,
                "content_type": raw.get("content_type") or "未知",
                "publish_time": raw.get("publish_time") or raw.get("publish_date") or "",
                "title": raw.get("title") or "",
                "content_summary": raw.get("content_summary") or raw.get("content") or raw.get("title") or "",
                "metrics": metrics,
                "source_url": raw.get("source_url"),
                "detail_url": raw.get("detail_url"),
                "comments_detail": raw.get("comments_detail") or [],
                "comment_collection_status": raw.get("comment_collection_status"),
                "collection_status": raw.get("collection_status") or "ok",
            }
        )
    return normalized


def normalize_all(daily_data: dict[str, dict | None]) -> list[dict]:
    items: list[dict] = []
    for key in ("xhs", "douyin", "wechat"):
        items.extend(normalize_platform_data(key, daily_data.get(key)))
    return items


def build_baseline(item: dict, history: list[dict]) -> dict:
    platform = item.get("platform")
    content_type = item.get("content_type")
    peers = [
        row for row in history
        if row.get("platform") == platform and row.get("content_type") == content_type
    ][-30:]
    source = "account_history" if len(peers) >= 5 else "fallback_threshold"
    confidence = "normal" if len(peers) >= 5 else "low"
    fallback = FALLBACK_BASELINES.get(platform, {"views": 100, "likes": 3, "comments": 1})

    values = {}
    for key in ("views", "likes", "comments", "collects", "shares", "wows"):
        series = [metric(row, key) for row in peers if metric(row, key) > 0]
        values[key] = int(statistics.median(series)) if series else fallback.get(key, 0)

    best = None
    if peers:
        best = max(peers, key=lambda row: score_item(row))
    return {
        "source": source,
        "confidence": confidence,
        "sample_size": len(peers),
        "median": values,
        "best_title": best.get("title") if best else "",
        "best_score": score_item(best) if best else 0,
    }


def score_item(item: dict | None) -> int:
    if not item:
        return 0
    return (
        metric(item, "views")
        + 6 * metric(item, "comments")
        + 4 * metric(item, "collects")
        + 3 * metric(item, "shares")
        + 2 * metric(item, "likes")
        + 3 * metric(item, "wows")
    )


def classify_item(item: dict, baseline: dict) -> str:
    views = metric(item, "views")
    likes = metric(item, "likes")
    comments = metric(item, "comments")
    med = baseline["median"]
    view_ratio = views / med["views"] if med.get("views") else 0
    engagement = likes + comments + metric(item, "collects") + metric(item, "wows")
    base_engagement = med.get("likes", 0) + med.get("comments", 0) + med.get("collects", 0) + med.get("wows", 0)
    engagement_ratio = engagement / base_engagement if base_engagement else 0
    if view_ratio >= 1.2 or engagement_ratio >= 1.4:
        return "good"
    if view_ratio < 0.8 or engagement_ratio < 0.7:
        return "bad"
    return "normal"


def diagnose_item(item: dict, baseline: dict) -> dict:
    platform = item["platform"]
    views = metric(item, "views")
    likes = metric(item, "likes")
    comments = metric(item, "comments")
    collects = metric(item, "collects")
    shares = metric(item, "shares")
    wows = metric(item, "wows")
    status = classify_item(item, baseline)
    med = baseline["median"]

    tags: list[str] = []
    bad_reasons: list[str] = []
    good_reasons: list[str] = []
    fixes: list[str] = []
    lock_patterns: list[str] = []

    if views < med.get("views", 0):
        tags.append("流量入口弱")
        bad_reasons.append(f"播放/阅读 {format_number(views)} 低于同类型历史基准 {format_number(med.get('views'))}")
        fixes.append("重写标题前 12 个字，把概念名改成具体问题、冲突或收益承诺")
    else:
        good_reasons.append(f"播放/阅读达到或高于基准，说明选题有入口吸引力")
        lock_patterns.append("保留“概念 + 具体问题/收益”的标题结构")

    like_rate = rate(likes, views)
    comment_rate = rate(comments, views)
    save_like_signal = collects > likes and collects > 0
    if views and like_rate < 0.02:
        tags.append("情绪认同弱")
        bad_reasons.append("点赞率偏低，用户可能觉得有用但缺少立刻认同的观点句")
        fixes.append("在开头和结尾各加一句明确判断，例如“新手最容易错在这里”")
    if views and comment_rate >= 0.03:
        tags.append("评论潜力强")
        good_reasons.append("评论率较高，说明内容能引发疑问或补充")
        fixes.append("下一条直接把评论里的问题改成标题，并在结尾设置二选一提问")
        lock_patterns.append("固定“讲概念后抛问题”的评论引导")
    if platform == "小红书" and save_like_signal:
        tags.append("资料价值强")
        good_reasons.append("收藏高于点赞，说明内容有保存价值")
        fixes.append("下一篇增加表格、口诀、步骤清单，并在标题加入“收藏版/对照表”")
        lock_patterns.append("固定为“收藏型知识卡 + 表格/口诀/清单”")
    if platform == "抖音" and views < med.get("views", 0):
        tags.append("前三秒弱")
        bad_reasons.append("抖音播放低于基准，优先怀疑开头没有足够冲突或场景")
        fixes.append("前三秒从“概念解释”改为“一个具体错误/场景问题”")
    if platform == "微信公众号" and views < med.get("views", 0):
        tags.append("标题打开率弱")
        bad_reasons.append("公众号阅读低于基准，标题和摘要需要更具体的结果承诺")
        fixes.append("标题加入对象、场景和结果，摘要第一句直接说明读完能解决什么")
    if shares > 0 or wows > 0:
        good_reasons.append("分享/在看信号存在，说明内容有传播或态度表达价值")
        lock_patterns.append("保留可转发的结论句，并把它前置成金句")

    if not good_reasons:
        good_reasons.append("当前主要价值信号还不突出，需要通过标题和结构放大内容利益点")
    if not bad_reasons:
        bad_reasons.append("没有明显短板，下一步重点是复用高表现结构并连续测试")
    if not fixes:
        fixes.append("用同选题做一个更具体的案例版，观察播放/阅读和评论率是否提升")
    if not lock_patterns:
        lock_patterns.append("沉淀为“标题承诺 + 案例解释 + 结尾提问”的基础结构")

    return {
        "platform": platform,
        "title": item.get("title", ""),
        "content_type": item.get("content_type", ""),
        "status": status,
        "score": score_item(item),
        "baseline": baseline,
        "distribution": diagnose_distribution_for_item(item, baseline),
        "tags": sorted(set(tags)),
        "为什么差": bad_reasons,
        "差在哪里": compare_metrics(item, med),
        "如何提升": fixes,
        "为什么好": good_reasons,
        "如何固定下来": lock_patterns,
    }


def diagnose_distribution_for_item(item: dict, baseline: dict) -> dict:
    views = metric(item, "views")
    likes = metric(item, "likes")
    comments = metric(item, "comments")
    collects = metric(item, "collects")
    wows = metric(item, "wows")
    med = baseline.get("median", {})
    base_views = med.get("views", 0)
    base_interactions = med.get("likes", 0) + med.get("comments", 0) + med.get("collects", 0) + med.get("wows", 0)
    interactions = likes + comments + collects + wows
    view_ratio = views / base_views if base_views else 0
    interaction_ratio = interactions / base_interactions if base_interactions else 0
    interaction_rate = rate(interactions, views)

    signals = []
    evidence = []
    if base_views and view_ratio <= 0.4 and (interaction_rate >= 0.08 or interaction_ratio >= 0.8):
        signals.append("疑似初始推荐池未放量")
        evidence.append("播放/阅读明显低于历史基准，但互动率或互动总量没有同步崩掉")
    if base_views and view_ratio <= 0.4 and interaction_ratio < 0.4:
        signals.append("内容入口与互动双弱")
        evidence.append("播放/阅读和互动都明显低于历史基准，更像选题/标题/开头没有过初筛")
    if views == 0 and interactions > 0:
        signals.append("采集或平台展示异常")
        evidence.append("互动存在但播放/阅读为 0，需要优先复核平台后台数据")

    return {
        "view_ratio": round(view_ratio, 3) if base_views else None,
        "interaction_ratio": round(interaction_ratio, 3) if base_interactions else None,
        "interaction_rate": round(interaction_rate, 4) if views else 0,
        "signals": signals,
        "evidence": evidence,
    }


def compare_metrics(item: dict, median: dict) -> list[str]:
    comparisons = []
    labels = {"views": "播放/阅读", "likes": "点赞", "comments": "评论", "collects": "收藏", "wows": "在看"}
    for key, label in labels.items():
        current = metric(item, key)
        base = median.get(key, 0)
        if not current and not base:
            continue
        if base and current < base:
            comparisons.append(f"{label}低于基准：{format_number(current)} vs {format_number(base)}")
        elif base and current >= base:
            comparisons.append(f"{label}达到/超过基准：{format_number(current)} vs {format_number(base)}")
        elif current:
            comparisons.append(f"{label}有正向信号：{format_number(current)}")
    return comparisons or ["样本指标不足，先按内容结构和互动信号判断"]


def platform_summaries(items: list[dict], diagnostics: list[dict], daily_data: dict[str, dict | None] | None = None) -> list[dict]:
    summaries = []
    daily_data = daily_data or {}
    for platform_key, platform in PLATFORM_NAMES.items():
        platform_items = [item for item in items if item.get("platform") == platform]
        if not platform_items:
            source_data = daily_data.get(platform_key) or {}
            if source_data.get("error"):
                status = source_data.get("collection_status") or "failed"
                reason = source_data.get("empty_reason") or source_data.get("error")
                summaries.append({
                    "platform": platform,
                    "summary": f"采集失败：{status}（{reason}）",
                    "items": 0,
                    "collection_status": status,
                })
                continue
            status = source_data.get("collection_status")
            if status in {"list_unreadable", "login_required", "failed"}:
                reason = source_data.get("empty_reason") or status
                summaries.append({
                    "platform": platform,
                    "summary": f"采集未确认：{status}（{reason}）",
                    "items": 0,
                    "collection_status": status,
                })
                continue
            summaries.append({"platform": platform, "summary": "无新增发布或无可分析内容", "items": 0})
            continue
        total_views = sum(metric(item, "views") for item in platform_items)
        total_likes = sum(metric(item, "likes") for item in platform_items)
        total_comments = sum(metric(item, "comments") for item in platform_items)
        tags = sorted({tag for d in diagnostics if d["platform"] == platform for tag in d["tags"]})
        summaries.append(
            {
                "platform": platform,
                "items": len(platform_items),
                "summary": f"{len(platform_items)} 条，播放/阅读 {format_number(total_views)}，点赞 {format_number(total_likes)}，评论 {format_number(total_comments)}",
                "tags": tags,
            }
        )
    return summaries


FRESH_ANGLE_BANK = [
    {
        "scene": "门突然被风关上",
        "topic": "外应取象的三步判断",
        "core_question": "先看门、风，还是那一声响？",
        "avoid_terms": ["门", "风", "关上"],
    },
    {
        "scene": "手机突然亮屏",
        "topic": "三要取象里的动静判断",
        "core_question": "取手机，取消息，还是取你当下的念头？",
        "avoid_terms": ["手机", "亮屏", "消息"],
    },
    {
        "scene": "灯忽明忽暗",
        "topic": "离卦取象和环境异常",
        "core_question": "这是火象，还是普通环境问题？",
        "avoid_terms": ["灯", "明暗", "火象"],
    },
    {
        "scene": "纸被风吹动",
        "topic": "巽卦取象和主次关系",
        "core_question": "为什么不是只看纸，而要先看风？",
        "avoid_terms": ["纸", "风", "吹动"],
    },
    {
        "scene": "钥匙突然找不到",
        "topic": "失物场景里的取象顺序",
        "core_question": "先看物，先看方位，还是先看起因？",
        "avoid_terms": ["钥匙", "找不到", "失物"],
    },
]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def choose_fresh_angle(best_title: str, content: str) -> dict:
    source_text = f"{best_title} {content}"
    for angle in FRESH_ANGLE_BANK:
        if not _contains_any(source_text, angle["avoid_terms"]):
            return angle
    fallback = dict(FRESH_ANGLE_BANK[0])
    fallback["note"] = "可用新场景库已全部命中过往内容关键词，使用默认新场景并要求人工复核。"
    return fallback


def extract_effective_logic(best: dict, diagnostics: list[dict]) -> list[str]:
    best_tags = []
    for diag in diagnostics:
        if diag.get("title") == best.get("title") and diag.get("status") == "good":
            best_tags.extend(diag.get("tags") or [])
    logic = [
        "用具体生活异常切入抽象概念，降低理解门槛。",
        "标题采用二选一或冲突提问，让读者先产生判断欲。",
        "正文做成步骤表、对照表或清单，承接收藏行为。",
        "结尾设置案例征集或选择题，放大评论信号。",
    ]
    if "评论潜力强" in best_tags:
        logic.append("保留开放式判断题，因为它能带来真实讨论。")
    if "资料价值强" in best_tags:
        logic.append("保留可保存的卡片结构，但更换案例和知识点。")
    return logic


def build_avoid_repeating(best_title: str, content: str) -> list[str]:
    avoid = [f"不要复述上一条标题：{best_title}"]
    text = f"{best_title} {content}"
    if _contains_any(text, ["水杯", "杯", "水", "打翻"]):
        avoid.append("不要继续讲水杯打翻、杯/水取象或同一生活场景。")
    avoid.append("不要只把旧标题换成“新手收藏版”“生活例子讲清楚”等包装词。")
    avoid.append("只继承高表现内容的底层机制，不继承题材本体。")
    return avoid


def build_next_content(items: list[dict], diagnostics: list[dict]) -> dict:
    best = max(items, key=score_item) if items else {}
    best_title = best.get("title") or "上一条高互动内容"
    content = best.get("content_summary", "")
    angle = choose_fresh_angle(best_title, content)
    topic = f"{angle['scene']}：{angle['topic']}"
    inherited_logic = extract_effective_logic(best, diagnostics)
    avoid_repeating = build_avoid_repeating(best_title, content)
    reason = "不是复述上一条内容，而是继承其底层机制：具体生活异常 + 二选一问题 + 步骤化收藏结构 + 评论引导。"
    weak = [d for d in diagnostics if d["status"] == "bad"]
    if weak:
        reason += f" 同时修正短板：{'; '.join(weak[0]['tags'][:2])}。"

    return {
        "section": "下一期内容决策",
        "topic": topic,
        "source_reference": {
            "platform": best.get("platform"),
            "title": best_title,
            "metrics": best.get("metrics") or {},
        },
        "fresh_angle": angle,
        "inherited_logic": inherited_logic,
        "avoid_repeating": avoid_repeating,
        "reason": reason,
        "xhs": {
            "platform": "小红书",
            "titles": [
                f"{angle['scene']}，古人会先看什么？",
                f"{angle['topic']}｜一个生活场景讲清楚",
                f"新手取象练习：{angle['core_question']}",
                f"收藏版：{angle['scene']}的取象步骤表",
            ],
            "outline": f"6-7 页卡片：{angle['scene']} -> 新手常见误判 -> 主象/辅象怎么分 -> 三步判断表 -> 一个反例 -> 总结口诀 -> 评论征集下一种生活外应。",
            "copy": f"这期不重复上一条案例，只沿用它好用的结构：从一个具体生活异常切入。比如「{angle['scene']}」，真正要练的不是背概念，而是判断：{angle['core_question']}",
        },
        "douyin": {
            "platform": "抖音",
            "format": "30-45 秒短视频或图文",
            "hooks": [
                f"{angle['scene']}，你第一反应会取什么？{angle['core_question']}",
                f"新手取象最容易错：看到{angle['scene'][:2]}就急着下结论，其实第一步不是这个。",
            ],
            "script": f"1-3 秒抛出场景：{angle['scene']}；4-10 秒让观众二选一：{angle['core_question']}；11-30 秒讲主象、辅象、动因三步；31-45 秒给一句口诀，并让评论区提交下一个生活场景。",
        },
        "wechat": {
            "platform": "微信公众号",
            "title": f"{angle['scene']}：从一个外应场景讲清取象顺序",
            "structure": "开头承接读者熟悉的生活异常；正文分“先别急着取象”“主次怎么分”“如何避免牵强附会”三个小标题；结尾给可收藏清单和下一篇案例预告。",
            "摘要": "公众号不复写短内容，而是把同一底层逻辑沉淀成更系统的取象顺序和误区辨析。",
        },
        "ab_test": {
            "variable": "新场景切入方式",
            "samples": ["生活异常型", "二选一提问型", "步骤清单型"],
            "winning_standard": "发布后 24 小时内，优先看播放/阅读是否高于历史中位数，其次看评论率和收藏/在看信号；若旧场景词再次出现，判定为选题重复而不是有效复用。",
        },
    }


def build_distribution_diagnosis(items: list[dict], diagnostics: list[dict]) -> dict:
    if not diagnostics:
        return {
            "section": "分发诊断",
            "level": "none",
            "signals": [],
            "判断": ["三平台无新增可分析内容，不能判断是否限流或分发异常。"],
            "证据": [],
            "解决动作": ["继续发布并保持数据采集，等有新增内容后再判断。"],
        }

    signals = []
    evidence = []
    for diag in diagnostics:
        distribution = diag.get("distribution") or {}
        for signal in distribution.get("signals", []):
            signals.append(signal)
        for item_evidence in distribution.get("evidence", []):
            evidence.append(f"{diag.get('platform')}「{diag.get('title')}」: {item_evidence}")

    active_platforms = {diag.get("platform") for diag in diagnostics}
    bad_platforms = {
        diag.get("platform")
        for diag in diagnostics
        if diag.get("distribution", {}).get("view_ratio") is not None
        and diag["distribution"]["view_ratio"] <= 0.4
    }
    weak_interaction_platforms = {
        diag.get("platform")
        for diag in diagnostics
        if diag.get("distribution", {}).get("interaction_ratio") is not None
        and diag["distribution"]["interaction_ratio"] < 0.4
    }

    if len(active_platforms) >= 2 and len(bad_platforms) == len(active_platforms):
        signals.append("三平台同步低迷" if len(active_platforms) >= 3 else "多平台同步低迷")
        evidence.append("多个平台同日播放/阅读都显著低于各自历史基准")

    signals = sorted(set(signals))
    if "三平台同步低迷" in signals or "多平台同步低迷" in signals:
        level = "account"
        if weak_interaction_platforms == active_platforms:
            judgment = ["疑似账号/选题阶段异常：三平台入口和互动都弱，优先按选题风险或表达疲劳处理。"]
        else:
            judgment = ["疑似账号/选题阶段异常：多平台同时低于历史基准，先不要只怪单个平台算法。"]
        actions = [
            "进入账号恢复模式：连续 2-3 条降低表达风险，用更具体的生活案例替代抽象概念。",
            "暂停同质标题和同质开头，下一条只测试一个变量：标题入口或前三秒场景。",
            "减少玄学承诺，统一改成国学文化科普、传统思维方法、案例观察。",
        ]
    elif "疑似初始推荐池未放量" in signals:
        level = "platform"
        judgment = ["不是单纯内容差：低播放/阅读但互动不弱，说明内容可能有价值，只是初始推荐池没有放量。"]
        actions = [
            "同主题继续测试，不要立刻换大选题；改标题入口和开头场景。",
            "下一条把概念解释改成具体错误、具体问题或生活冲突。",
            "用小红书做收藏版承接，用抖音做案例版验证，用公众号做长文沉淀。",
        ]
    elif "内容入口与互动双弱" in signals:
        level = "content"
        judgment = ["更像内容入口和互动设计共同偏弱，不优先判断为限流。"]
        actions = [
            "换选题包装：标题前 12 个字必须出现对象、痛点或具体收益。",
            "减少纯概念解释，改成“问题-案例-方法-提问”的结构。",
            "下一条不要复用原封面/原开头，避免连续同质低表现。",
        ]
    else:
        level = "normal"
        judgment = ["未发现明确限流/分发异常信号，按常规内容优化处理。"]
        actions = ["继续积累历史样本，重点观察下一条是否重复出现低播放高互动。"]

    return {
        "section": "分发诊断",
        "level": level,
        "signals": signals,
        "判断": judgment,
        "证据": evidence,
        "解决动作": actions,
    }


def infer_topic(title: str, content: str) -> str:
    text = f"{title} {content}"
    for keyword in ("八卦", "三要", "取象", "起卦", "体用", "梅花易数"):
        if keyword in text:
            return f"{keyword}的具体用法"
    return title[:24] if title else "把高互动主题案例化"


def benchmark_status(config: dict) -> dict:
    accounts = config.get("accounts") or config.get("benchmark_accounts") or []
    if not accounts:
        return {
            "external": "未配置对标账号",
            "note": "当前只使用账号历史基准；配置对标账号后，可加入同平台选题和互动结构参照。",
        }
    return {
        "external": f"已配置 {len(accounts)} 个对标账号",
        "note": "首版只保留配置位，外部对标采集将在后续启用。",
    }


def analyze_daily_data(daily_data: dict[str, dict | None], history: list[dict], benchmark_config: dict | None = None) -> dict:
    items = normalize_all(daily_data)
    diagnostics = []
    for item in items:
        diagnostics.append(diagnose_item(item, build_baseline(item, history)))

    best_views = max(items, key=lambda item: metric(item, "views"), default=None)
    best_likes = max(items, key=lambda item: metric(item, "likes"), default=None)
    best_comments = max(items, key=lambda item: metric(item, "comments"), default=None)

    return {
        "items": items,
        "benchmark_status": benchmark_status(benchmark_config or {}),
        "highlights": {
            "highest_views": best_views,
            "highest_likes": best_likes,
            "highest_comments": best_comments,
        },
        "content_diagnostics": diagnostics,
        "distribution_diagnosis": build_distribution_diagnosis(items, diagnostics),
        "comment_insights": summarize_comment_insights(items),
        "platform_summaries": platform_summaries(items, diagnostics, daily_data),
        "cross_platform": build_cross_platform_summary(diagnostics),
        "next_content": build_next_content(items, diagnostics),
    }


def build_cross_platform_summary(diagnostics: list[dict]) -> str:
    if not diagnostics:
        return "三平台无新增可分析内容。"
    positive_tags = {"评论潜力强", "资料价值强"}
    good_tags = [tag for d in diagnostics for tag in d["tags"] if tag in positive_tags]
    weak_tags = [tag for d in diagnostics for tag in d["tags"] if tag not in positive_tags]
    if good_tags:
        return f"优先固定 {good_tags[0]} 对应的表达方式，再修正 {weak_tags[0] if weak_tags else '标题入口'}。"
    if weak_tags:
        return f"当前主要短板是 {weak_tags[0]}，下一期先改标题入口和开头结构。"
    return "整体表现接近基准，下一期用同选题不同表达做 A/B 测试。"
