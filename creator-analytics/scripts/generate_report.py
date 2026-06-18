#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日数据报告生成器

读取小红书和抖音的采集结果 JSON，生成 Markdown 格式的每日复盘报告。
"""

import argparse
import json
import sys
import datetime
from pathlib import Path
from paths import output_dir

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = output_dir()
DEFAULT_OUTPUT_DIR = output_dir()


def parse_args():
    parser = argparse.ArgumentParser(description="生成每日数据复盘报告")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR),
                        help="采集结果 JSON 所在目录")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="报告输出目录")
    parser.add_argument("--date", default=None,
                        help="报告日期 YYYY-MM-DD，默认昨天")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    return yesterday.isoformat()


def load_platform_data(input_dir: str, filename: str) -> dict | None:
    """加载平台采集数据"""
    path = Path(input_dir) / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def format_number(n: int) -> str:
    """格式化数字为可读格式"""
    n = safe_int(n)
    if n >= 100000000:
        return f"{n / 100000000:.2f}亿"
    elif n >= 10000:
        return f"{n / 10000:.1f}万"
    else:
        return str(n)


def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{numerator / denominator:.1%}"


def build_platform_section(platform: str, data: dict | None) -> str:
    """构建单个平台的报告章节"""
    section = []

    if data is None:
        section.append(f"## {platform_emoji(platform)} {platform}")
        section.append("")
        section.append("> ❌ 数据采集失败（采集器未运行或出错）")
        section.append("")
        return "\n".join(section)

    items = data.get("items", [])
    error = data.get("error")

    section.append(f"## {platform_emoji(platform)} {platform}")
    section.append("")

    if error:
        section.append(f"> ⚠️ 采集过程出现异常: {error}")
        section.append("")
        if not items:
            section.append(f"> ❌ {platform}采集未完成，不能判断昨日是否有新增发布内容")
            section.append("")
            return "\n".join(section)

    if not items:
        section.append(f"> 📭 {platform}昨日无新增发布内容")
        section.append("")
        return "\n".join(section)

    # 数据表格
    section.append("| 发布时间 | 类型 | 标题 | 播放量 | 点赞量 | 评论量 |")
    section.append("|---------|-----|-----|-------|-------|-------|")

    for item in items:
        pub_date = item.get("publish_date", "-")
        content_type = item.get("content_type", "-")
        title = item.get("title", "-")
        if len(title) > 30:
            title = title[:28] + "…"
        views = format_number(item.get("views", 0))
        likes = format_number(item.get("likes", 0))
        comments = format_number(item.get("comments", 0))
        section.append(f"| {pub_date} | {content_type} | {title} | {views} | {likes} | {comments} |")

    section.append("")
    section.append("**已读取内容摘要**")
    for idx, item in enumerate(items, start=1):
        content = item.get("content") or item.get("title") or "-"
        content = content.replace("\n", " ")
        if len(content) > 120:
            content = content[:118] + "…"
        section.append(f"- {idx}. {item.get('content_type', '-')}: {content}")

    section.append("")
    return "\n".join(section)


def platform_emoji(platform: str) -> str:
    if "小红" in platform:
        return "📕"
    elif "抖音" in platform:
        return "📱"
    return "📋"


def build_analysis(xhs_data: dict | None, douyin_data: dict | None) -> str:
    """构建复盘分析章节"""
    all_items = []

    if xhs_data and not xhs_data.get("error"):
        for item in xhs_data.get("items", []):
            normalized = dict(item)
            normalized["_platform"] = "小红书"
            all_items.append(normalized)

    if douyin_data and not douyin_data.get("error"):
        for item in douyin_data.get("items", []):
            normalized = dict(item)
            normalized["_platform"] = "抖音"
            all_items.append(normalized)

    all_items = [
        item for item in all_items
        if item.get("title") or safe_int(item.get("views")) or safe_int(item.get("likes")) or safe_int(item.get("comments"))
    ]

    if not all_items:
        return (
            "### 复盘分析\n\n"
            "昨日双平台均无新增发布内容。\n\n"
            "---\n\n"
            "*本报告由 creator-analytics 自动生成*\n"
        )

    analysis = ["### 复盘分析\n"]

    best_views = max(all_items, key=lambda x: safe_int(x.get("views")))
    if safe_int(best_views.get("views")) > 0:
        analysis.append(
            f"- 🏆 **播放量最高**: 「{best_views.get('title', '-')}」"
            f"（{format_number(best_views.get('views'))} 播放 · {best_views['_platform']}）"
        )

    best_likes = max(all_items, key=lambda x: safe_int(x.get("likes")))
    if safe_int(best_likes.get("likes")) > 0:
        analysis.append(
            f"- ❤️ **点赞量最高**: 「{best_likes.get('title', '-')}」"
            f"（{format_number(best_likes.get('likes'))} 点赞 · {best_likes['_platform']}）"
        )

    best_comments = max(all_items, key=lambda x: safe_int(x.get("comments")))
    if safe_int(best_comments.get("comments")) > 0:
        analysis.append(
            f"- 💬 **评论量最高**: 「{best_comments.get('title', '-')}」"
            f"（{format_number(best_comments.get('comments'))} 评论 · {best_comments['_platform']}）"
        )

    analysis.append("")
    analysis.append("#### 精准诊断")
    analysis.extend(generate_platform_diagnostics(all_items))
    analysis.append("")
    analysis.append("#### 下一期内容判断")
    analysis.extend(generate_next_content_plan(all_items))

    analysis.append("")
    analysis.append("---")
    analysis.append("")
    analysis.append("*本报告由 creator-analytics 自动生成*")
    analysis.append("")

    return "\n".join(analysis)


def generate_platform_diagnostics(all_items: list[dict]) -> list[str]:
    diagnostics = []
    for platform in ("小红书", "抖音"):
        items = [item for item in all_items if item.get("_platform") == platform]
        if not items:
            diagnostics.append(f"- **{platform}**: 昨日无可分析内容。")
            continue

        views = sum(safe_int(item.get("views")) for item in items)
        likes = sum(safe_int(item.get("likes")) for item in items)
        comments = sum(safe_int(item.get("comments")) for item in items)
        collects = sum(safe_int(item.get("collects")) for item in items)
        interactions = likes + comments + collects
        best = max(items, key=lambda item: safe_int(item.get("views")))

        parts = [
            f"- **{platform}**: {len(items)} 条，播放/浏览 {format_number(views)}，点赞 {format_number(likes)}，评论 {format_number(comments)}"
        ]
        if platform == "小红书":
            parts.append(f"收藏 {format_number(collects)}")
        parts.append(f"综合互动率 {pct(interactions, views)}")

        diagnosis = "。".join(parts) + "。"
        if platform == "小红书" and views > 0:
            if collects > likes:
                diagnosis += "收藏高于点赞，说明内容有资料价值，但情绪认同/爽点不够，需要更强结论和更明确的收藏理由。"
            elif comments > likes:
                diagnosis += "评论高于点赞，说明选题能引发问题或讨论，下一期应把评论里的疑问前置成标题。"
        if platform == "抖音" and views > 0:
            if comments >= likes:
                diagnosis += "评论不低于点赞，说明概念型内容有提问潜力，下一条要用案例降低理解门槛。"
            if safe_int(best.get("views")) == views:
                diagnosis += f"当前最佳样本是「{best.get('title', '-')}」。"
        diagnostics.append(diagnosis)
    return diagnostics


def generate_next_content_plan(all_items: list[dict]) -> list[str]:
    best_by_score = max(
        all_items,
        key=lambda item: safe_int(item.get("views")) + 3 * safe_int(item.get("comments")) + 2 * safe_int(item.get("collects")) + safe_int(item.get("likes")),
    )
    title = best_by_score.get("title", "")

    if "8个符号" in title or "八卦" in title:
        topic = "八卦取象的具体用法"
        next_title = "梅花易数入门｜8个符号怎么用？用一个生活问题讲清取象"
        reason = "小红书这条有浏览和收藏价值，适合继续做“可保存”的入门知识卡。"
    elif "三要" in title:
        topic = "三要感应法的生活案例"
        next_title = "梅花易数入门｜三要感应法：看到异常，怎么判断是不是“应”？"
        reason = "抖音这条在播放、点赞、评论里表现最好，说明“三要感应法”比纯概念更容易触发提问。"
    else:
        topic = "把最高互动内容继续案例化"
        next_title = f"{title}｜用一个真实场景讲清楚" if title else "梅花易数入门｜用一个真实场景讲清一个概念"
        reason = "当前样本量少，优先沿用已产生播放/评论的方向做连续测试。"

    return [
        f"- **下一期优先选题**: {topic}",
        f"- **判断依据**: {reason}",
        f"- **小红书图文标题**: 「{next_title}」",
        "- **小红书图文思路**: 6-7 页卡片。第 1 页用“零基础也能看懂”的承诺；第 2 页解释为什么要学这个概念；第 3-5 页给表格/口诀/生活例子；第 6 页总结；第 7 页用评论问题引导下一期。",
        "- **小红书开头文案**: 刷到先收藏。很多人学梅花易数，一开始卡住不是因为概念太多，而是不知道这些符号到底怎么落到生活里。今天用一个普通场景，把取象思路讲清楚。",
        "- **抖音视频/图文标题**: 「看到一个异常现象，古人会怎么取象？」",
        "- **抖音脚本思路**: 1-3 秒先抛问题；4-10 秒给核心判断句；11-30 秒讲一个具体场景；31-45 秒总结方法，并引导评论“想看八卦类象表扣 1”。",
        "- **抖音黄金 3 秒**: “很多人学不会梅花易数，不是因为难，而是第一步取象就错了。”",
        "- **A/B 测试标题**: A「看到异常就能起卦吗？」；B「梅花易数里的三要，到底看哪三件事？」；C「一个生活例子讲清三要感应法」。",
    ]


def build_report(xhs_data: dict | None, douyin_data: dict | None, report_date: str) -> str:
    """构建完整报告"""
    lines = [
        f"# 创作者平台每日数据报告 - {report_date}",
        "",
        f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 小红书
    lines.append(build_platform_section("小红书", xhs_data))
    lines.append("")

    # 抖音
    lines.append(build_platform_section("抖音", douyin_data))
    lines.append("")

    # 复盘分析
    lines.append(build_analysis(xhs_data, douyin_data))

    return "\n".join(lines)


def main():
    args = parse_args()
    report_date = target_date(args.date)
    input_dir = args.input_dir

    print(f"📊 生成每日数据报告 - {report_date}")
    print(f"{'=' * 50}")

    # 加载数据
    xhs_data = load_platform_data(input_dir, "xhs_data.json")
    douyin_data = load_platform_data(input_dir, "douyin_data.json")

    if xhs_data is None and douyin_data is None:
        print("⚠️ 未找到任何平台的数据文件，请先运行采集器")
        return 1

    if xhs_data:
        status = "✅" if not xhs_data.get("error") else "⚠️"
        count = len(xhs_data.get("items", []))
        print(f"{status} 小红书: {count} 条内容{'（采集异常）' if xhs_data.get('error') else ''}")

    if douyin_data:
        status = "✅" if not douyin_data.get("error") else "⚠️"
        count = len(douyin_data.get("items", []))
        print(f"{status} 抖音: {count} 条内容{'（采集异常）' if douyin_data.get('error') else ''}")

    # 生成报告
    report = build_report(xhs_data, douyin_data, report_date)

    # 保存报告
    output_dir = args.output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_file = Path(output_dir) / f"report_{report_date}.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n💾 报告已保存到 {out_file}")

    # 输出到终端
    print("\n" + "=" * 70)
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
