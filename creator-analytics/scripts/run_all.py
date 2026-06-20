#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创作者平台日报 — 主调度器

按顺序执行小红书、抖音和微信公众号的数据采集，然后生成报告。
"""

import argparse
import json
import subprocess
import sys
import datetime
from pathlib import Path
from paths import output_dir

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def parse_args():
    parser = argparse.ArgumentParser(description="创作者平台日报 — 主调度器")
    parser.add_argument("--headed", action="store_true",
                        help="打开浏览器窗口（首次登录或 cookie 过期时使用）")
    parser.add_argument("--date", default=None,
                        help="目标日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--platform", choices=["xhs", "douyin", "wechat", "all"], default="all",
                        help="采集指定平台，默认全部")
    parser.add_argument("--dry-run", action="store_true",
                        help="模拟运行，不实际采集")
    parser.add_argument("--no-auto-login", action="store_true",
                        help="检测到登录过期时不自动打开浏览器重试")
    parser.add_argument("--comments-limit", type=int, default=50,
                        help="每条内容最多采集的评论数，默认 50")
    parser.add_argument("--skip-comments", action="store_true",
                        help="跳过评论明细采集，只采集基础指标")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    return yesterday.isoformat()


def run_script(script_name: str, *extra_args) -> int:
    """运行指定 Python 脚本"""
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        print(f"❌ 脚本不存在: {script_path}")
        return 1

    python = sys.executable
    cmd = [python, str(script_path)] + list(extra_args)
    print(f"\n{'=' * 70}")
    print(f"🚀 运行: {script_name}")
    print(f"{'=' * 70}")

    result = subprocess.run(cmd, cwd=str(SKILL_DIR))
    return result.returncode


def build_common_args(report_date: str, headed: bool, dry_run: bool, comments_limit: int, skip_comments: bool) -> list[str]:
    common_args = ["--date", report_date, "--comments-limit", str(comments_limit)]
    if headed:
        common_args.append("--headed")
    if dry_run:
        common_args.append("--dry-run")
    if skip_comments:
        common_args.append("--skip-comments")
    return common_args


PLATFORM_OUTPUT_FILES = {
    "xhs": "xhs_data.json",
    "douyin": "douyin_data.json",
    "wechat": "wechat_data.json",
}


LOGIN_ERROR_MARKERS = [
    "登录",
    "扫码",
    "Cookie 已过期",
    "登录态过期",
    "--headed",
    "重新登录",
]


def platform_requires_login(platform: str) -> bool:
    """Return true when the latest platform output says visible login is required."""
    filename = PLATFORM_OUTPUT_FILES.get(platform)
    if not filename:
        return False
    path = output_dir() / filename
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    error = str(data.get("error") or "")
    return any(marker in error for marker in LOGIN_ERROR_MARKERS)


def run_platform(platform: str, script_name: str, common_args: list[str], auto_login: bool) -> int:
    """Run one platform collector, retrying once with a visible browser if login is required."""
    run_args = list(common_args)
    if platform == "wechat" and auto_login and "--headed" not in run_args:
        print("\n🔑 微信公众号后台对无头浏览器登录态不稳定，优先使用可见浏览器复用 profile。")
        run_args.append("--headed")

    code = run_script(script_name, *run_args)
    if code == 0 or not auto_login:
        return code

    if platform_requires_login(platform):
        print(f"\n🔑 {platform} 需要登录，自动打开浏览器重试。请在浏览器中扫码/完成登录。")
        headed_args = list(run_args)
        if "--headed" not in headed_args:
            headed_args.append("--headed")
        return run_script(script_name, *headed_args)

    return code


def main():
    args = parse_args()
    report_date = target_date(args.date)
    print(f"{'=' * 70}")
    print(f"  创作者平台日报 — 数据采集与报告")
    print(f"  目标日期: {report_date}")
    print(f"  平台: {'全部' if args.platform == 'all' else args.platform}")
    print(f"{'=' * 70}")

    common_args = build_common_args(report_date, args.headed, args.dry_run, args.comments_limit, args.skip_comments)
    auto_login = not args.headed and not args.dry_run and not args.no_auto_login

    exit_codes = {}

    # 第一步: 采集小红书
    if args.platform in ("xhs", "all"):
        code = run_platform("xhs", "scrape_xhs.py", common_args, auto_login)
        exit_codes["xhs"] = code
    else:
        print("\n⏭️ 跳过小红书采集")

    # 第二步: 采集抖音
    if args.platform in ("douyin", "all"):
        code = run_platform("douyin", "scrape_douyin.py", common_args, auto_login)
        exit_codes["douyin"] = code
    else:
        print("\n⏭️ 跳过抖音采集")

    # 第三步: 采集微信公众号
    if args.platform in ("wechat", "all"):
        code = run_platform("wechat", "scrape_wechat.py", common_args, auto_login)
        exit_codes["wechat"] = code
    else:
        print("\n⏭️ 跳过微信公众号采集")

    # 第四步: 生成报告
    print(f"\n{'=' * 70}")
    print(f"📊 生成每日数据报告...")
    print(f"{'=' * 70}")

    report_args = ["--date", report_date]
    code = run_script("generate_report.py", *report_args)
    exit_codes["report"] = code

    # 汇总
    print(f"\n{'=' * 70}")
    print(f"  执行汇总")
    print(f"{'=' * 70}")
    status_map = {
        "xhs": "✅" if exit_codes.get("xhs") == 0 else "❌",
        "douyin": "✅" if exit_codes.get("douyin") == 0 else "❌",
        "wechat": "✅" if exit_codes.get("wechat") == 0 else "❌",
        "report": "✅" if exit_codes.get("report") == 0 else "❌",
    }
    print(f"  小红书: {status_map.get('xhs', '⏭️')}")
    print(f"  抖音:   {status_map.get('douyin', '⏭️')}")
    print(f"  公众号: {status_map.get('wechat', '⏭️')}")
    print(f"  报告:   {status_map.get('report', '⏭️')}")
    print(f"{'=' * 70}")

    # 报告路径提示
    report_path = output_dir() / f"report_{report_date}.md"
    print(f"\n📄 报告文件: {report_path}")

    failed_collectors = [k for k, v in exit_codes.items() if k != "report" and v != 0]
    if failed_collectors:
        print(f"\n⚠️ 以下平台采集有异常，报告已按可用数据生成: {', '.join(failed_collectors)}")
    if exit_codes.get("report") != 0:
        return 1

    print("\n🎉 全部完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
