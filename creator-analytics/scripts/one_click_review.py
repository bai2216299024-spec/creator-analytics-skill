#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创作者平台一键全链路复盘

一键完成：采集小红书/抖音/微信公众号前一日内容 -> 读取发布内容 -> 数据诊断 -> 下一期选题与文案思路。
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from paths import config_dir, output_dir

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ZONES_CONFIG = config_dir() / "zones_sync.json"


def parse_args():
    parser = argparse.ArgumentParser(description="一键完成创作者数据采集、内容读取、复盘分析和下一期选题建议")
    parser.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--platform", choices=["xhs", "douyin", "wechat", "all"], default="all", help="平台，默认全部")
    parser.add_argument("--headed", action="store_true", help="打开浏览器窗口，适合首次登录或排错")
    parser.add_argument("--data-dir", default=None, help="运行态目录，保存登录态和报告；默认使用 skill/data")
    parser.add_argument("--comments-limit", type=int, default=50, help="每条内容最多采集的评论数，默认 50")
    parser.add_argument("--skip-comments", action="store_true", help="跳过评论明细采集，只采集基础指标")
    return parser.parse_args()


def target_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def _first_run_zone_setup(dry_run: bool):
    """Offer interactive zone-sync setup on first run."""
    if ZONES_CONFIG.exists():
        return  # already configured
    if not sys.stdin.isatty():
        return  # cron / scheduled task
    if dry_run:
        return  # don't prompt during dry-run

    print("\n" + "=" * 60)
    print("  🔧 检测到首次使用，是否配置三专区数据自动同步？")
    print()
    print("  这将使每日采集报告自动写入抖音/小红书/公众号的")
    print("  「数据报表」文件夹，方便在各专区直接查看指标。")
    print()
    print("  [1] 现在配置")
    print("  [2] 跳过（以后可用 scripts/setup_zones.py 重新配置）")
    print("=" * 60)

    try:
        choice = input("  请选择 [1/2]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已跳过配置。")
        return

    if choice == "1":
        zones_root = input("\n📂 请输入内容工作区根目录（如 D:/my-content）: ").strip()
        if not zones_root:
            print("  未输入路径，已跳过配置。")
            return
        config = {
            "enabled": True,
            "zones_root": zones_root,
            "platforms": {
                "xhs": {"zone": "小红书专区", "folder": "数据报表"},
                "douyin": {"zone": "抖音专区", "folder": "数据报表"},
                "wechat": {"zone": "公众号专区", "folder": "数据报表"},
            },
        }
        ZONES_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with open(ZONES_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 配置已保存，继续执行每日采集...\n")
    else:
        print("  已跳过配置，可稍后运行 python scripts/setup_zones.py 配置。\n")


def main() -> int:
    args = parse_args()
    if args.data_dir:
        os.environ["CREATOR_ANALYTICS_DATA_DIR"] = str(Path(args.data_dir).resolve())

    report_date = target_date(args.date)

    # First-run zone sync setup
    _first_run_zone_setup(dry_run="--dry-run" in sys.argv)

    print("=" * 70)
    print("  创作者平台一键全链路复盘")
    print(f"  目标日期: {report_date}")
    print("  流程: 数据采集 -> 内容读取 -> 历史基准 -> 指标诊断 -> 下一期选题/成稿思路")
    print("=" * 70)

    cmd = [sys.executable, str(SCRIPT_DIR / "run_all.py"), "--date", report_date, "--platform", args.platform]
    if args.headed:
        cmd.append("--headed")
    cmd.extend(["--comments-limit", str(args.comments_limit)])
    if args.skip_comments:
        cmd.append("--skip-comments")

    code = subprocess.call(cmd, cwd=str(SKILL_DIR))
    report_path = output_dir() / f"report_{report_date}.md"

    print("\n" + "=" * 70)
    if code == 0 and report_path.exists():
        print("✅ 一键全链路复盘完成")
        print(f"📄 报告文件: {report_path}")
        print("📌 报告已包含：内容读取摘要、好/差归因、提升动作、可复用模式、下一期成稿思路")
        return 0

    print("❌ 一键全链路复盘未完整完成")
    if report_path.exists():
        print(f"📄 已生成部分报告: {report_path}")
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
