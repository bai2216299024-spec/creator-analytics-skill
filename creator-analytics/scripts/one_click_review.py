#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创作者平台一键全链路复盘

一键完成：采集小红书/抖音前一日内容 -> 读取发布内容 -> 数据诊断 -> 下一期选题与文案思路。
"""

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path
from paths import output_dir

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def parse_args():
    parser = argparse.ArgumentParser(description="一键完成创作者数据采集、内容读取、复盘分析和下一期选题建议")
    parser.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--platform", choices=["xhs", "douyin", "all"], default="all", help="平台，默认全部")
    parser.add_argument("--headed", action="store_true", help="打开浏览器窗口，适合首次登录或排错")
    parser.add_argument("--data-dir", default=None, help="运行态目录，保存登录态和报告；默认使用 skill/data")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def main() -> int:
    args = parse_args()
    if args.data_dir:
        os.environ["CREATOR_ANALYTICS_DATA_DIR"] = str(Path(args.data_dir).resolve())

    report_date = target_date(args.date)

    print("=" * 70)
    print("  创作者平台一键全链路复盘")
    print(f"  目标日期: {report_date}")
    print("  流程: 数据采集 -> 内容读取 -> 指标诊断 -> 下一期选题/文案思路")
    print("=" * 70)

    cmd = [sys.executable, str(SCRIPT_DIR / "run_all.py"), "--date", report_date, "--platform", args.platform]
    if args.headed:
        cmd.append("--headed")

    code = subprocess.call(cmd, cwd=str(SKILL_DIR))
    report_path = output_dir() / f"report_{report_date}.md"

    print("\n" + "=" * 70)
    if code == 0 and report_path.exists():
        print("✅ 一键全链路复盘完成")
        print(f"📄 报告文件: {report_path}")
        print("📌 报告已包含：内容读取摘要、数据诊断、下一期图文/视频选题和文案思路")
        return 0

    print("❌ 一键全链路复盘未完整完成")
    if report_path.exists():
        print(f"📄 已生成部分报告: {report_path}")
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
