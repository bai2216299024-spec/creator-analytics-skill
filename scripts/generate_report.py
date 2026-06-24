#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate creator analytics daily report and machine-readable analysis."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import re
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
    parser.add_argument("--no-zone-sync", action="store_true", help="只生成报告，不同步到三区数据报表")
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


def platform_status_note(platform: str, data: dict) -> str:
    status = data.get("collection_status")
    empty_reason = data.get("empty_reason")
    login_status = data.get("login_status")
    parts = []
    if status:
        parts.append(f"采集状态: {status}")
    if empty_reason:
        parts.append(f"空结果原因: {empty_reason}")
    if login_status:
        parts.append(f"登录状态: {login_status}")
    if not parts:
        return ""
    return f"{platform} {'；'.join(parts)}。"


def build_platform_section(platform_key: str, data: dict | None) -> str:
    platform = platform_title(platform_key)
    lines = [f"## {platform}", ""]
    if data is None:
        lines.extend(["> 采集失败：未找到该平台数据文件，不能判断是否有新增发布。", ""])
        return "\n".join(lines)

    error = data.get("error")
    items = data.get("items", [])
    status_note = platform_status_note(platform, data)
    if status_note:
        lines.extend([f"> {status_note}", ""])
    if error:
        lines.append(f"> 采集失败：{error}")
        if not items:
            lines.extend(["> 不能把采集失败当成无新增发布。", ""])
            return "\n".join(lines)
        lines.append("")
    if not items:
        status = data.get("collection_status")
        empty_reason = data.get("empty_reason")
        if status == "skipped":
            lines.extend([f"> {platform} 本次为跳过/演练采集，未检查是否新增发布。", ""])
        elif status == "empty" and empty_reason in {"no_matching_date", "empty_list_visible"}:
            lines.extend([f"> {platform} 昨日无新增发布内容。", ""])
        elif status in {"list_unreadable", "login_required", "failed"}:
            lines.extend([f"> {platform} 未抓到目标日期内容，但原因是 {empty_reason or status}，不能直接等同于无新增发布。", ""])
        else:
            lines.extend([f"> {platform} 昨日无新增发布内容或列表不可见。", ""])
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
        stat_conf = diag.get("statistical_confidence", baseline.get("confidence", "normal"))
        conf_label = {"low": "低置信度", "medium": "中置信度", "high": "高置信度", "normal": "正常置信度"}.get(stat_conf, stat_conf)
        lines.append(f"### {idx}. {diag.get('platform')}｜{diag.get('title') or '-'}")
        lines.append(f"- **状态**: {diag.get('status')}；基准来源: {baseline.get('source')} ({conf_label}, 样本 {baseline.get('sample_size', 0)} 条)")
        lines.append(f"- **诊断标签**: {', '.join(diag.get('tags') or ['无明显标签'])}")
        lines.append(f"- **为什么差**: {'; '.join(diag.get('为什么差', []))}")
        lines.append(f"- **差在哪里**: {'; '.join(diag.get('差在哪里', []))}")
        lines.append(f"- **如何提升**: {'; '.join(diag.get('如何提升', []))}")
        lines.append(f"- **为什么好**: {'; '.join(diag.get('为什么好', []))}")
        lines.append(f"- **如何固定下来**: {'; '.join(diag.get('如何固定下来', []))}")

        # 新增：层次化根因诊断
        hierarchical = diag.get("hierarchical", {})
        if hierarchical:
            layers = hierarchical.get("layers", {})
            root_cause = hierarchical.get("root_cause_layer", "L4")
            lines.append(f"- **根因诊断**: {hierarchical.get('summary', '-')}")
            lines.append(f"  - L1 环境层: {layers.get('L1_environment', {}).get('conclusion', '-')}")
            lines.append(f"  - L2 账号层: {layers.get('L2_account', {}).get('conclusion', '-')}")
            lines.append(f"  - L3 选题层: {layers.get('L3_topic', {}).get('conclusion', '-')}")
            lines.append(f"  - L4 表达层: {layers.get('L4_expression', {}).get('conclusion', '-')}")
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
    source = plan.get("source_reference") or {}
    fresh_angle = plan.get("fresh_angle") or {}
    diversity = plan.get("diversity") or {}
    fitness = plan.get("platform_fitness") or {}
    lines = [
        "## 下一期内容决策",
        "",
        f"- **优先选题**: {plan.get('topic', '-')}",
        f"- **判断依据**: {plan.get('reason', '-')}",
    ]
    if source:
        lines.append(f"- **参考样本**: {source.get('platform') or '-'}「{source.get('title') or '-'}」")
    if fresh_angle:
        lines.append(f"- **新切入场景**: {fresh_angle.get('scene') or '-'}；核心问题：{fresh_angle.get('core_question') or '-'}")
        if fresh_angle.get("source"):
            lines.append(f"- **场景来源**: {fresh_angle['source']}")
    inherited_logic = plan.get("inherited_logic") or []
    if inherited_logic:
        lines.append(f"- **继承的底层逻辑**: {'; '.join(inherited_logic)}")
    avoid_repeating = plan.get("avoid_repeating") or []
    if avoid_repeating:
        lines.append(f"- **明确不重复**: {'; '.join(avoid_repeating[:3])}")
        if len(avoid_repeating) > 3:
            lines.append(f"  - ...及其他 {len(avoid_repeating) - 3} 条")
    # 新增：平台适配度
    if fitness:
        fit_str = "; ".join(f"{k}={v}" for k, v in fitness.items())
        lines.append(f"- **平台适配度**: {fit_str}")
    lines.extend([
        "",
        "### 小红书图文",
    ])
    for title in xhs.get("titles", []):
        lines.append(f"- 标题备选: {title}")
    lines.extend([
        f"- 卡片结构: {xhs.get('outline', '-')}",
        f"- 开头文案: {xhs.get('copy', '-')}",
        f"- 适配度: {xhs.get('fitness_score', '-')}",
        "",
        "### 抖音视频/图文",
        f"- 形式: {douyin.get('format', '-')}",
    ])
    for hook in douyin.get("hooks", []):
        lines.append(f"- 黄金 3 秒: {hook}")
    lines.extend([
        f"- 脚本结构: {douyin.get('script', '-')}",
        f"- 适配度: {douyin.get('fitness_score', '-')}",
        "",
        "### 微信公众号",
        f"- 标题: {wechat.get('title', '-')}",
        f"- 文章结构: {wechat.get('structure', '-')}",
        f"- 摘要: {wechat.get('摘要', '-')}",
        f"- 适配度: {wechat.get('fitness_score', '-')}",
        "",
        "### A/B 测试",
        f"- 变量: {ab.get('variable', '-')}",
        f"- 样本: {' / '.join(ab.get('samples', []))}",
        f"- 观察指标: {ab.get('metric_to_watch', '-')}",
        f"- 胜出标准: {ab.get('winning_standard', '-')}",
        "",
    ])
    return "\n".join(lines)


def build_trend_section(analysis: dict) -> str:
    """新增：趋势追踪章节"""
    trend = analysis.get("trend_analysis") or {}
    platforms = trend.get("platforms") or {}
    lines = ["## 趋势追踪（7日滚动）", ""]
    if not platforms:
        lines.extend(["> 历史数据不足，无法计算趋势", ""])
        return "\n".join(lines)

    for name, data in platforms.items():
        if data.get("note"):
            lines.append(f"- **{name}**: {data['note']}")
            continue
        change = data.get("change", {})
        today = data.get("today", {})
        avg_7d = data.get("avg_7d", {})
        lines.append(f"- **{name}**: 今日播放 {format_number(today.get('views', 0))} ({change.get('views', 'N/A')})，"
                     f"7日均 {format_number(avg_7d.get('views', 0))} | "
                     f"点赞 {format_number(today.get('likes', 0))} ({change.get('likes', 'N/A')}) | "
                     f"评论 {format_number(today.get('comments', 0))} ({change.get('comments', 'N/A')})")
    lines.append(f"- **综合判断**: {trend.get('overall', '-')}")
    lines.append("")
    return "\n".join(lines)


def build_structure_section(analysis: dict) -> str:
    """新增：内容结构诊断章节"""
    structure = analysis.get("content_structure") or {}
    patterns = structure.get("patterns") or []
    lines = ["## 内容结构诊断", ""]
    if not patterns:
        lines.extend(["> 样本不足，无法分析内容结构", ""])
        return "\n".join(lines)

    lines.append("| 结构特征 | 出现次数 | 均播放 | 均收藏 |")
    lines.append("|---|---:|---:|---:|")
    for p in patterns[:5]:
        lines.append(f"| {p['pattern']} | {p['frequency']} | {format_number(p['avg_views'])} | {format_number(p['avg_collects'])} |")
    lines.append("")
    lines.append(f"- **洞察**: {structure.get('insight', '-')}")
    lines.append("")
    return "\n".join(lines)


def build_fatigue_section(analysis: dict) -> str:
    """新增：选题疲劳预警章节"""
    fatigue = analysis.get("content_fatigue") or {}
    alerts = fatigue.get("fatigue_alerts") or []
    lines = ["## 选题疲劳预警", ""]
    lines.append(f"- **总体判断**: {fatigue.get('overall', '-')}")
    if alerts:
        for alert in alerts:
            scores = alert.get("score_trend", [])
            scores_str = " → ".join(format_number(s) for s in scores)
            lines.append(f"- ⚠️ {alert.get('cluster', '-')}: {alert.get('suggestion', '-')}（得分: {scores_str}）")
    lines.append("")
    return "\n".join(lines)


def build_engagement_quality_section(analysis: dict) -> str:
    """新增：互动质量分析章节"""
    eq_data = analysis.get("engagement_quality") or {}
    signals = eq_data.get("quality_signals") or []
    lines = ["## 互动质量分析", ""]
    lines.append(f"- **收藏/点赞比**: {eq_data.get('collect_like_ratio', 0)}（>1.5 说明强保存价值）")
    lines.append(f"- **点赞率**: {eq_data.get('like_rate', 0):.2%}")
    lines.append(f"- **评论率**: {eq_data.get('comment_rate', 0):.2%}")
    lines.append(f"- **问题型评论占比**: {eq_data.get('question_comment_ratio', 0):.1%}（{eq_data.get('total_comments_analyzed', 0)} 条他人评论中）")
    if signals:
        for signal in signals:
            lines.append(f"- ✅ {signal}")
    lines.append("")
    return "\n".join(lines)


def build_report(daily_data: dict, analysis: dict, report_date: str) -> str:
    lines = [
        f"# 创作者三平台每日复盘 - {report_date}",
        "",
        f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        build_highlights(analysis),
        build_trend_section(analysis),
        build_structure_section(analysis),
        build_engagement_quality_section(analysis),
        build_platform_section("xhs", daily_data.get("xhs")),
        build_platform_section("douyin", daily_data.get("douyin")),
        build_platform_section("wechat", daily_data.get("wechat")),
        build_platform_summary(analysis),
        build_fatigue_section(analysis),
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


CONFIG_PATH = config_dir() / "zones_sync.json"

# Mapping from report heading to platform key
HEADING_PLATFORM_MAP = {
    "## 小红书": "xhs",
    "## 抖音": "douyin",
    "## 微信公众号": "wechat",
}


def _safe_zone_target(zones_root: Path, zone: str, folder: str) -> Path | None:
    """Resolve a zone target and ensure it cannot escape zones_root."""
    try:
        root = zones_root.resolve()
        target = (root / zone / folder).resolve()
        target.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return target


def sync_to_zones(report_date: str, report_text: str):
    """Split the multi-platform report and write per-platform files into zone folders.

    Reads config/zones_sync.json.  If the file is missing or disabled, this
    function returns silently so that the core report workflow is unaffected.
    """
    if not CONFIG_PATH.exists():
        return
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"[WARN] zones_sync.json 格式有误，跳过同步")
        return
    if not config.get("enabled"):
        return

    zones_root = Path(config.get("zones_root", ""))
    if not zones_root.is_dir():
        print(f"[WARN] 工作区路径不存在，跳过同步: {zones_root}")
        return
    try:
        zones_root = zones_root.resolve()
    except OSError as exc:
        print(f"[WARN] 工作区路径不可解析，跳过同步: {exc}")
        return

    platforms = config.get("platforms", {})
    file_name = f"{report_date}-指标日报.md"

    # Split the report by platform headings
    for heading, platform_key in HEADING_PLATFORM_MAP.items():
        platform_cfg = platforms.get(platform_key)
        if not platform_cfg:
            continue
        section = _extract_section(report_text, heading)
        if section is None:
            continue
        zone = str(platform_cfg.get("zone") or "")
        folder = str(platform_cfg.get("folder") or "")
        target_dir = _safe_zone_target(zones_root, zone, folder)
        if target_dir is None:
            print(f"  [WARN] 跳过不安全的专区路径: {platform_key}")
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name
        try:
            target_path.write_text(section, encoding="utf-8")
            print(f"  [OK] 已同步 {platform_cfg['zone']}/{platform_cfg['folder']}/{file_name}")
        except OSError as exc:
            print(f"  [WARN] 写入失败 {target_path}: {exc}")


def _extract_section(text: str, heading: str) -> str | None:
    """Extract the section starting with *heading* until the next H2 or EOF."""
    pattern = re.escape(heading) + r"\n"
    match = re.search(pattern, text)
    if not match:
        return None
    start = match.start()
    rest = text[match.end():]
    next_h2 = re.search(r"\n(?=## )", rest)
    if next_h2:
        return text[start: match.end() + next_h2.start()]
    return text[start:]


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

    # Zone sync (optional — skipped silently if not configured)
    if not args.no_zone_sync:
        try:
            sync_to_zones(report_date, report)
        except Exception as exc:
            print(f"[WARN] 三专区同步出错（不影响报告生成）: {exc}")

    print("\n" + "=" * 70)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
