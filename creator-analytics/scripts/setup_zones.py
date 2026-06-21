#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interactive setup for Zone Sync feature.

Guides first-time users to configure the three-zone content workspace path.
Run standalone:  python scripts/setup_zones.py
Non-interactive: python scripts/setup_zones.py --zones-root /path/to/workspace
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "zones_sync.json"
EXAMPLE_PATH = CONFIG_DIR / "zones_sync.example.json"

PLATFORMS = {
    "xhs": {"zone": "小红书专区", "folder": "数据报表"},
    "douyin": {"zone": "抖音专区", "folder": "数据报表"},
    "wechat": {"zone": "公众号专区", "folder": "数据报表"},
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="配置 creator-analytics 三专区数据自动同步"
    )
    parser.add_argument("--zones-root", default=None,
                        help="内容工作区根目录（非交互模式）")
    return parser.parse_args()


def guess_zones_root() -> str | None:
    """Try to guess the content workspace from common paths."""
    candidates = []
    home = Path.home()
    for name in ("content-workspace", "梅花易数工作流", "workspace"):
        p = home / name
        if p.is_dir():
            candidates.append(str(p))
    for drive_letter in "DEFG":
        for name in ("content-workspace", "梅花易数工作流", "workspace"):
            p = Path(f"{drive_letter}:/{name}")
            if p.is_dir():
                candidates.append(str(p))
    return candidates[0] if candidates else None


def validate_zones_root(root: str) -> dict[str, bool]:
    """Check which platform zone folders exist under the workspace root."""
    results = {}
    base = Path(root)
    for key, cfg in PLATFORMS.items():
        zone_dir = base / cfg["zone"] / cfg["folder"]
        results[key] = zone_dir.is_dir()
    return results


def write_config(zones_root: str):
    """Write zones_sync.json to the config directory."""
    config = {
        "enabled": True,
        "zones_root": zones_root,
        "platforms": PLATFORMS,
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def interactive_setup():
    """Walk user through first-time configuration."""
    print("\n" + "=" * 60)
    print("  🔧 配置三专区数据自动同步")
    print("=" * 60)
    print()
    print("creator-analytics 可以将每日采集报告自动写入")
    print("抖音/小红书/公众号的「数据报表」文件夹。")
    print()

    guessed = guess_zones_root()
    if guessed:
        print(f"💡 检测到可能的工作区: {guessed}")
        answer = input("使用此路径？[Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            zones_root = guessed
        else:
            zones_root = input("请输入内容工作区根目录: ").strip()
    else:
        zones_root = input("请输入内容工作区根目录: ").strip()

    if not zones_root:
        print("❌ 未输入路径，已取消配置。")
        return 1

    root_path = Path(zones_root)
    if not root_path.is_dir():
        print(f"⚠️  路径不存在: {zones_root}")
        proceed = input("是否仍然保存配置？[y/N] ").strip().lower()
        if proceed not in ("y", "yes"):
            print("已取消配置。")
            return 1

    write_config(zones_root)
    print(f"\n✅ 配置已保存到 {CONFIG_PATH}")
    print()

    results = validate_zones_root(zones_root)
    for key, cfg in PLATFORMS.items():
        status = "✅" if results[key] else "❌ (文件夹不存在)"
        print(f"  {status}  {cfg['zone']}/{cfg['folder']}/")

    if not all(results.values()):
        print("\n⚠️  部分专区文件夹不存在。创建对应的「数据报表」文件夹后即可同步。")
        print("   也可以稍后运行 python scripts/setup_zones.py 重新配置。")

    print(f"\n下次运行 one_click_review.py 时将自动同步。")
    return 0


def noninteractive_setup(zones_root: str) -> int:
    """Setup without user prompts (for scripts/cron)."""
    print(f"[setup] 配置三专区同步: zones_root={zones_root}")
    write_config(zones_root)
    print(f"[OK] 配置已保存到 {CONFIG_PATH}")
    results = validate_zones_root(zones_root)
    for key, cfg in PLATFORMS.items():
        status = "[OK]" if results[key] else "[WARN]"
        print(f"  {status}  {cfg['zone']}/{cfg['folder']}/")
    return 0


def main() -> int:
    args = parse_args()
    if args.zones_root:
        return noninteractive_setup(args.zones_root)
    return interactive_setup()


if __name__ == "__main__":
    sys.exit(main())
