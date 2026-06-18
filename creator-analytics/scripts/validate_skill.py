#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the portable creator-analytics skill package."""

import py_compile
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REQUIRED = [
    "one_click_review.py",
    "run_all.py",
    "scrape_xhs.py",
    "scrape_douyin.py",
    "generate_report.py",
    "paths.py",
]


def main() -> int:
    missing = [name for name in REQUIRED if not (SCRIPT_DIR / name).exists()]
    if missing:
        print(f"❌ 缺少脚本: {', '.join(missing)}")
        return 1

    for name in REQUIRED:
        py_compile.compile(str(SCRIPT_DIR / name), doraise=True)

    print("OK creator-analytics skill validation passed")
    print(f"Skill path: {SCRIPT_DIR.parent}")
    print("Entry point: scripts/one_click_review.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
