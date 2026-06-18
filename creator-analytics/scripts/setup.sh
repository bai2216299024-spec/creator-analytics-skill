#!/bin/bash
# -*- coding: utf-8 -*-
#
# creator-analytics — 依赖安装脚本
# Usage: bash scripts/setup.sh

set -e

echo "========================================"
echo " 创作者平台日报 — 环境安装"
echo "========================================"

# 检查 Python 版本
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 需要 Python 3.10+，请先安装"
    exit 1
fi
echo "✅ Python: $($PYTHON --version)"

# 检查 pip
if ! $PYTHON -m pip --version &>/dev/null; then
    echo "❌ pip 未安装"
    exit 1
fi
echo "✅ pip 可用"

# 安装 Playwright
echo ""
echo "📦 安装 Playwright..."
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install playwright -q
echo "✅ Playwright 安装完成"

# 安装 Chromium 浏览器
echo ""
echo "🌐 安装 Chromium 浏览器..."
$PYTHON -m playwright install chromium
echo "✅ Chromium 安装完成"

# 验证
echo ""
echo "🔍 验证安装..."
$PYTHON -c "from playwright.sync_api import sync_playwright; print('✅ Playwright 可用')"

# 创建数据目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
mkdir -p "$SKILL_DIR/data/cookies"
mkdir -p "$SKILL_DIR/data/output"
echo "✅ 数据目录已创建"

echo ""
echo "========================================"
echo " 🎉 安装完成！"
echo "========================================"
echo ""
echo "首次使用请运行："
echo "  python3 scripts/run_all.py --headed"
echo ""
echo "日常使用请运行："
echo "  python3 scripts/run_all.py"
echo ""
