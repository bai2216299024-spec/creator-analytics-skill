#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent history for creator analytics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def load_history(path: str | Path) -> list[dict]:
    history_path = Path(path)
    if not history_path.exists():
        return []
    rows: list[dict] = []
    with history_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def history_key(item: dict) -> tuple:
    platform = item.get("platform", "")
    publish_time = item.get("publish_time") or item.get("publish_date") or ""
    title = (item.get("title") or "").strip()
    if title:
        return platform, publish_time, title
    metrics = item.get("metrics") or {}
    return platform, publish_time, metrics.get("views"), metrics.get("likes"), metrics.get("comments")


def append_history(path: str | Path, items: Iterable[dict]) -> list[dict]:
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    merged = {history_key(row): row for row in load_history(history_path)}
    for item in items:
        merged[history_key(item)] = item

    rows = list(merged.values())
    with history_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return rows
