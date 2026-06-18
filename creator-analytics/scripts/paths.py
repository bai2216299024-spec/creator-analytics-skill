#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared paths for creator-analytics scripts."""

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def data_dir() -> Path:
    """Return runtime data directory, overridable for portable installs."""
    return Path(os.environ.get("CREATOR_ANALYTICS_DATA_DIR", SKILL_DIR / "data")).resolve()


def output_dir() -> Path:
    return data_dir() / "output"


def history_dir() -> Path:
    return data_dir() / "history"


def config_dir() -> Path:
    return SKILL_DIR / "config"


def cookie_file(platform: str) -> Path:
    return data_dir() / "cookies" / f"{platform}_cookies.json"


def profile_dir(platform: str) -> Path:
    return data_dir() / "browser" / f"{platform}_profile"
