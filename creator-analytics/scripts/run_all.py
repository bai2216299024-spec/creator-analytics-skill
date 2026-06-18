#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创作者平台日报 — 主调度器

按顺序执行小红书和抖音的数据采集，然后生成报告。
"""

import argparse
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
    parser.add_argument("--platform", choices=["xhs", "douyin", "all"], default="all",
                        help="采集指定平台，默认全部")
    parser.add_argument("--dry-run", action="store_true",
                        help="模拟运行，不实际采集")
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


def main():
    args = parse_args()
    report_date = target_date(args.date)
    headless = not args.headed

    print(f"{'=' * 70}")
    print(f"  创作者平台日报 — 数据采集与报告")
    print(f"  目标日期: {report_date}")
    print(f"  平台: {'全部' if args.platform == 'all' else args.platform}")
    print(f"{'=' * 70}")

    common_args = ["--date", report_date]
    if args.headed:
        common_args.append("--headed")
    if args.dry_run:
        common_args.append("--dry-run")

    exit_codes = {}

    # 第一步: 采集小红书
    if args.platform in ("xhs", "all"):
        code = run_script("scrape_xhs.py", *common_args)
        exit_codes["xhs"] = code
    else:
        print("\n⏭️ 跳过小红书采集")

    # 第二步: 采集抖音
    if args.platform in ("douyin", "all"):
        code = run_script("scrape_douyin.py", *common_args)
        exit_codes["douyin"] = code
    else:
        print("\n⏭️ 跳过抖音采集")

    # 第三步: 生成报告
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
        "report": "✅" if exit_codes.get("report") == 0 else "❌",
    }
    print(f"  小红书: {status_map.get('xhs', '⏭️')}")
    print(f"  抖音:   {status_map.get('douyin', '⏭️')}")
    print(f"  报告:   {status_map.get('report', '⏭️')}")
    print(f"{'=' * 70}")

    # 报告路径提示
    report_path = output_dir() / f"report_{report_date}.md"
    print(f"\n📄 报告文件: {report_path}")

    # 如果有失败，返回非零
    failed = [k for k, v in exit_codes.items() if v != 0]
    if failed:
        print(f"\n⚠️ 以下步骤有异常: {', '.join(failed)}")
        return 1

    print("\n🎉 全部完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
