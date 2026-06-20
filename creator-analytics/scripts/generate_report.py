#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate creator analytics daily report and machine-readable analysis."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from analysis_engine import analyze_daily_data, format_number, load_benchmark_config, load_json, metric, normalize_all
from history_store import append_history, load_history
from paths import config_dir, history_dir, output_dir

DEFAULT_INPUT_DIR = output_dir()
DEFAULT_OUTPUT_DIR = output_dir()
DEFAULT_HISTORY_FILE = history_dir() / "content_history.jsonl"
DEFAULT_BENCHMARK_CONFIG = config_dir() / "benchmark_accounts.json"


def parse_args():
    parser = argparse.ArgumentParser(description="生成创作者三平台每日复盘报告")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="采集结果 JSON 所在目录")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="报告输出目录")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE), help="历史库 JSONL 路径")
    parser.add_argument("--benchmark-config", default=str(DEFAULT_BENCHMARK_CONFIG), help="对标账号配置")
    parser.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD，默认昨天")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def load_daily_data(input_dir: str) -> dict:
    base = Path(input_dir)
    return {
        "xhs": load_json(base / "xhs_data.json"),
        "douyin": load_json(base / "douyin_data.json"),
        "wechat": load_json(base / "wechat_data.json"),
    }


def platform_title(key: str) -> str:
    return {"xhs": "小红书", "douyin": "抖音", "wechat": "微信公众号"}[key]


def metric_label(platform_key: str) -> str:
    return "阅读量" if platform_key == "wechat" else "播放/浏览"


def display_metric(value) -> str:
    if value is None:
        return "未取到"
    return format_number(value)


def build_platform_section(platform_key: str, data: dict | None) -> str:
    platform = platform_title(platform_key)
    lines = [f"## {platform}", ""]
    if data is None:
        lines.extend(["> 采集失败：未找到该平台数据文件，不能判断是否有新增发布。", ""])
        return "\n".join(lines)

    error = data.get("error")
    items = data.get("items", [])
    if error:
        lines.append(f"> 采集失败：{error}")
        if not items:
            lines.extend(["> 不能把采集失败当成无新增发布。", ""])
            return "\n".join(lines)
        lines.append("")
    if not items:
        lines.extend([f"> {platform} 昨日无新增发布内容。", ""])
        return "\n".join(lines)

    first_metric = metric_label(platform_key)
    extra = "收藏/在看"
    lines.append(f"| 发布时间 | 类型 | 标题/主题 | {first_metric} | 点赞 | 评论 | {extra} |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for item in items:
        title = (item.get("title") or "-").replace("|", "｜")
        if len(title) > 42:
            title = title[:40] + "..."
        views = item.get("reads") if platform_key == "wechat" else item.get("views")
        extra_value = item.get("wows") if platform_key == "wechat" else item.get("collects")
        lines.append(
            f"| {item.get('publish_time') or item.get('publish_date') or '-'} "
            f"| {item.get('content_type') or '-'} "
            f"| {title} "
            f"| {display_metric(views)} "
            f"| {display_metric(item.get('likes'))} "
            f"| {display_metric(item.get('comments'))} "
            f"| {display_metric(extra_value)} |"
        )
    lines.append("")
    lines.append("**内容读取摘要**")
    for idx, item in enumerate(items, start=1):
        content = (item.get("content_summary") or item.get("content") or item.get("title") or "-").replace("\n", " ")
        if len(content) > 140:
            content = content[:138] + "..."
        lines.append(f"- {idx}. {content}")
    lines.append("")
    return "\n".join(lines)


def build_highlights(analysis: dict) -> str:
    lines = ["## 核心结果", ""]
    highlights = analysis.get("highlights", {})
    mapping = [
        ("highest_views", "播放/阅读最高", "views"),
        ("highest_likes", "点赞最高", "likes"),
        ("highest_comments", "评论最高", "comments"),
    ]
    for key, label, metric_key in mapping:
        item = highlights.get(key)
        if item:
            lines.append(f"- **{label}**: {item.get('platform')}「{item.get('title') or '-'}」({format_number(metric(item, metric_key))})")
    lines.append(f"- **外部对标**: {analysis.get('benchmark_status', {}).get('external', '未配置对标账号')}")
    lines.append("")
    return "\n".join(lines)


def build_diagnostics(analysis: dict) -> str:
    lines = ["## 精准诊断", ""]
    diagnostics = analysis.get("content_diagnostics", [])
    if not diagnostics:
        lines.extend(["三平台无新增可分析内容。", ""])
        return "\n".join(lines)

    for idx, diag in enumerate(diagnostics, start=1):
        baseline = diag.get("baseline", {})
        confidence = "低置信度" if baseline.get("confidence") == "low" else "正常置信度"
        lines.append(f"### {idx}. {diag.get('platform')}｜{diag.get('title') or '-'}")
        lines.append(f"- **状态**: {diag.get('status')}；基准来源: {baseline.get('source')} ({confidence}, 样本 {baseline.get('sample_size', 0)} 条)")
        lines.append(f"- **诊断标签**: {', '.join(diag.get('tags') or ['无明显标签'])}")
        lines.append(f"- **为什么差**: {'；'.join(diag.get('为什么差', []))}")
        lines.append(f"- **差在哪里**: {'；'.join(diag.get('差在哪里', []))}")
        lines.append(f"- **如何提升**: {'；'.join(diag.get('如何提升', []))}")
        lines.append(f"- **为什么好**: {'；'.join(diag.get('为什么好', []))}")
        lines.append(f"- **如何固定下来**: {'；'.join(diag.get('如何固定下来', []))}")
        lines.append("")
    return "\n".join(lines)


def build_platform_summary(analysis: dict) -> str:
    lines = ["## 平台汇总", ""]
    for row in analysis.get("platform_summaries", []):
        tags = row.get("tags") or []
        tag_text = f"；主要标签：{', '.join(tags)}" if tags else ""
        lines.append(f"- **{row.get('platform')}**: {row.get('summary')}{tag_text}")
    lines.append(f"- **跨平台判断**: {analysis.get('cross_platform')}")
    lines.append("")
    return "\n".join(lines)


def build_distribution_section(analysis: dict) -> str:
    distribution = analysis.get("distribution_diagnosis") or {}
    lines = ["## 分发/限流诊断", ""]
    lines.append(f"- **诊断级别**: {distribution.get('level', 'unknown')}")
    signals = distribution.get("signals") or []
    lines.append(f"- **异常信号**: {', '.join(signals) if signals else '未发现明确限流/分发异常信号'}")
    for item in distribution.get("判断", []):
        lines.append(f"- **判断**: {item}")
    evidence = distribution.get("证据") or []
    if evidence:
        for item in evidence:
            lines.append(f"- **证据**: {item}")
    for item in distribution.get("解决动作", []):
        lines.append(f"- **解决动作**: {item}")
    lines.append("")
    return "\n".join(lines)


def build_comments_section(analysis: dict) -> str:
    insights = analysis.get("comment_insights") or {}
    lines = ["## 评论洞察", ""]
    total = insights.get("total_comments", 0)
    if not total:
        lines.extend(["暂无可分析评论。", ""])
        failures = insights.get("collection_failures") or []
        for failure in failures:
            lines.append(f"- 评论采集失败：{failure.get('platform') or '-'}「{failure.get('title') or '-'}」：{failure.get('status')}")
        if failures:
            lines.append("")
        return "\n".join(lines)

    lines.append(
        f"- **评论总量**: {total}；他人评论 {insights.get('other_comments', 0)}；"
        f"自己账号回复 {insights.get('self_comments', 0)}；回复数量比例 {insights.get('self_reply_ratio', '0/0')}"
    )
    health = insights.get("comment_collection_health") or {}
    if health:
        health_text = "；".join(f"{key}={value}" for key, value in health.items() if value)
        lines.append(f"- **评论采集健康度**: {health_text or '暂无采集状态'}")
    lines.append("")
    render_comment_lines(lines, "他人评论摘要", insights.get("other_summary") or [])
    render_comment_lines(lines, "自己账号回复摘要", insights.get("self_reply_summary") or insights.get("self_summary") or [])
    render_comment_refs(lines, "用户高价值问题", insights.get("user_questions") or [])
    if insights.get("unanswered_questions"):
        render_comment_refs(lines, "已确认未回复的问题", insights.get("unanswered_questions") or [])
    render_comment_refs(lines, "可直接变成下一期选题的评论", insights.get("topic_candidates_from_comments") or insights.get("next_topic_candidates") or [])
    failures = insights.get("collection_failures") or []
    if failures:
        lines.append("**评论采集异常**")
        for failure in failures:
            lines.append(f"- {failure.get('platform') or '-'}「{failure.get('title') or '-'}」：{failure.get('status')}")
        lines.append("")
    return "\n".join(lines)


def render_comment_lines(lines: list[str], title: str, values: list[str]):
    lines.append(f"**{title}**")
    if not values:
        lines.append("- 暂无")
    else:
        lines.extend(f"- {value}" for value in values)
    lines.append("")


def render_comment_refs(lines: list[str], title: str, refs: list[dict]):
    lines.append(f"**{title}**")
    if not refs:
        lines.append("- 暂无")
    else:
        for ref in refs[:5]:
            content = (ref.get("content") or "").replace("\n", " ")
            if len(content) > 80:
                content = content[:78] + "..."
            lines.append(f"- {ref.get('platform') or '-'}「{ref.get('title') or '-'}」：{content}")
    lines.append("")


def build_next_content(analysis: dict) -> str:
    plan = analysis.get("next_content") or {}
    xhs = plan.get("xhs", {})
    douyin = plan.get("douyin", {})
    wechat = plan.get("wechat", {})
    ab = plan.get("ab_test", {})
    lines = [
        "## 下一期内容决策",
        "",
        f"- **优先选题**: {plan.get('topic', '-')}",
        f"- **判断依据**: {plan.get('reason', '-')}",
        "",
        "### 小红书图文",
    ]
    for title in xhs.get("titles", []):
        lines.append(f"- 标题备选: {title}")
    lines.extend([
        f"- 卡片结构: {xhs.get('outline', '-')}",
        f"- 开头文案: {xhs.get('copy', '-')}",
        "",
        "### 抖音视频/图文",
        f"- 形式: {douyin.get('format', '-')}",
    ])
    for hook in douyin.get("hooks", []):
        lines.append(f"- 黄金 3 秒: {hook}")
    lines.extend([
        f"- 脚本结构: {douyin.get('script', '-')}",
        "",
        "### 微信公众号",
        f"- 标题: {wechat.get('title', '-')}",
        f"- 文章结构: {wechat.get('structure', '-')}",
        f"- 摘要: {wechat.get('摘要', '-')}",
        "",
        "### A/B 测试",
        f"- 变量: {ab.get('variable', '-')}",
        f"- 样本: {' / '.join(ab.get('samples', []))}",
        f"- 胜出标准: {ab.get('winning_standard', '-')}",
        "",
    ])
    return "\n".join(lines)


def build_report(daily_data: dict, analysis: dict, report_date: str) -> str:
    lines = [
        f"# 创作者三平台每日复盘 - {report_date}",
        "",
        f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        build_highlights(analysis),
        build_platform_section("xhs", daily_data.get("xhs")),
        build_platform_section("douyin", daily_data.get("douyin")),
        build_platform_section("wechat", daily_data.get("wechat")),
        build_platform_summary(analysis),
        build_distribution_section(analysis),
        build_comments_section(analysis),
        build_diagnostics(analysis),
        build_next_content(analysis),
        "---",
        "",
        "*本报告由 creator-analytics 自动生成*",
        "",
    ]
    return "\n".join(lines)


def main():
    args = parse_args()
    report_date = target_date(args.date)
    print(f"生成创作者三平台每日复盘 - {report_date}")
    print("=" * 50)

    daily_data = load_daily_data(args.input_dir)
    if all(value is None for value in daily_data.values()):
        print("未找到任何平台的数据文件，请先运行采集器")
        return 1

    history_file = Path(args.history_file)
    history = load_history(history_file)
    benchmark_config = load_benchmark_config(args.benchmark_config)
    analysis = analyze_daily_data(daily_data, history, benchmark_config)

    current_items = normalize_all(daily_data)
    updated_history = append_history(history_file, current_items)
    analysis["history"] = {"path": str(history_file), "total_items": len(updated_history), "added_or_updated": len(current_items)}

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    analysis_file = out_dir / f"analysis_{report_date}.json"
    with analysis_file.open("w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    report = build_report(daily_data, analysis, report_date)
    report_file = out_dir / f"report_{report_date}.md"
    with report_file.open("w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已保存到 {report_file}")
    print(f"分析 JSON 已保存到 {analysis_file}")
    print("\n" + "=" * 70)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
