---
name: creator-analytics
description: 一键采集并复盘小红书和抖音创作者账号前一天发布的图文/视频内容数据。Use when the user asks to 统计创作者数据、生成每日复盘、分析小红书/抖音发布内容表现、读取已发布图文或视频内容、判断下一期选题、生成下一期小红书图文或抖音视频文案思路、设置每日内容数据自动复盘。
---

# Creator Analytics

Use this skill as a portable one-click workflow for creator account analytics.

## Primary Entry

Run only the public entrypoint unless you are debugging internals:

```bash
python scripts/one_click_review.py
```

Common options:

```bash
python scripts/one_click_review.py --date 2026-06-17
python scripts/one_click_review.py --platform xhs
python scripts/one_click_review.py --platform douyin
python scripts/one_click_review.py --headed
python scripts/one_click_review.py --data-dir D:\creator-analytics-data
```

For scheduled daily execution on Windows, use the bundled PowerShell runner:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily_review.ps1
```

To install a Windows daily task from this skill:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -At 09:00
```

The workflow performs:

1. Collect previous-day 小红书 and 抖音 posts.
2. Read content type, title, available body/content summary, publish time, and metrics.
3. Group results by platform.
4. Diagnose performance with platform benchmarks.
5. Recommend next topic, Xiaohongshu card-copy direction, Douyin video/carousel direction, hook, structure, and A/B tests.

## Operating Plan

Use this skill in five modes.

### 1. Daily Review

For requests like `统计昨天数据`, `生成昨日复盘`, or scheduled daily review:

1. Run `python scripts/one_click_review.py`.
2. Read the generated `report_YYYY-MM-DD.md`.
3. Return the key numbers, diagnosis, and next-content recommendation to the user.
4. If the user asks for execution-ready content, expand the recommended topic into Xiaohongshu card copy or Douyin script in the same turn.

### 2. Specific Date Or Platform

Use date/platform parameters when the user asks for a specific scope:

```bash
python scripts/one_click_review.py --date YYYY-MM-DD
python scripts/one_click_review.py --platform xhs
python scripts/one_click_review.py --platform douyin
```

After running, compare the requested scope against the output. Do not infer missing platform data from previous reports.

### 3. First Login Or Reauthorization

Use headed mode when a platform asks for login, verification, or returns a login page:

```bash
python scripts/one_click_review.py --headed
```

Wait for the user to complete login in the browser. Then run the same command without `--headed` to confirm the saved browser profile works.

### 4. Portable Or Multi-Agent Use

When another agent or machine needs this skill:

1. Copy the whole `creator-analytics` folder.
2. Run `python scripts/validate_skill.py`.
3. Install Playwright if needed.
4. Use `--data-dir` to keep login state and reports outside the copied skill:

```bash
python scripts/one_click_review.py --data-dir D:\creator-analytics-data
```

Do not copy a live user’s browser profile to an untrusted machine. Prefer a fresh login in the target environment.

### 5. Daily Task Installation

When the user asks to make this a daily task inside another agent or machine:

1. Copy the whole `creator-analytics` skill folder.
2. Run `python scripts/validate_skill.py`.
3. Run the bundled installer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -At 09:00
```

Use optional arguments when needed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -TaskName CreatorAnalyticsDailyReview -At 09:00 -PythonExe C:\Path\to\python.exe -DataDir D:\creator-analytics-data
```

For Codex App automations, configure the automation prompt to call `scripts\run_daily_review.ps1` by absolute path. Avoid relative `scripts/...` paths unless the automation working directory is the skill root.

## Decision Rules

Use the report to decide next content, not just to summarize numbers:

- If Xiaohongshu has high collects but low likes, create a more save-worthy card note with clearer tables, formulas, or checklists, and strengthen the emotional payoff in the title.
- If Xiaohongshu has comments above likes, turn the comment question into the next note title.
- If Douyin comments are high relative to likes, make the next piece a concrete example or scenario explanation, not a pure definition.
- If Douyin views are low, revise the first 3 seconds: start with conflict, curiosity, or scene pain before explaining the concept.
- If both platforms respond to the same concept, make a two-format package: Xiaohongshu as reference cards, Douyin as short scenario script.
- If data volume is too small, recommend one focused A/B test instead of broad conclusions.

For Meihua Yishu content, keep public-facing recommendations in `国学文化科普`, `传统文化学习`, and `古人思维方式` framing.

## Report-To-Content Workflow

When the user asks `下一期做什么` or `根据数据写文案`:

1. Identify the best-performing topic by views plus interaction signals.
2. Explain why it won: topic fit, hook/title, usefulness, comment potential, or platform fit.
3. Choose one next topic.
4. Produce both:
   - Xiaohongshu: 4 title options, final note copy direction, card-by-card plan, hashtags, pinned comment.
   - Douyin: format, 2 hook options, 30-45 second script outline, subtitle highlights, caption, hashtags.
5. Include one A/B test with variable, sample, and winning standard.

## Runtime State

By default, runtime data is stored inside `data/` in this skill:

- `data/browser/` stores persistent browser profiles and login state.
- `data/cookies/` stores Playwright storage state snapshots.
- `data/output/` stores JSON data and Markdown reports.

For portable installs or other agents, prefer setting a runtime data directory:

```bash
python scripts/one_click_review.py --data-dir D:\creator-analytics-data
```

The first run on a new machine or new data directory may require `--headed` login. After successful login, later runs should reuse the browser profile.

## Output

Reports are saved to:

```text
<data-dir>/output/report_YYYY-MM-DD.md
```

The report should include:

- per-platform content table
- content summary for each published item
- highest views/likes/comments
- platform diagnosis
- next issue topic decision
- Xiaohongshu graphic-note direction
- Douyin video/carousel script direction
- title and hook A/B tests

If a platform has no new content, say so clearly. If collection fails, mark it as collection failure and never treat it as no new content.

## Validation

After copying this skill to another agent or machine, run:

```bash
python scripts/validate_skill.py
```

If Playwright is missing, install dependencies in the target environment:

```bash
python -m pip install playwright
python -m playwright install chromium
```
