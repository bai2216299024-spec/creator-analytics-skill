---
name: creator-analytics
description: 一键采集并复盘小红书、抖音、微信公众号创作者账号前一天发布的图文/视频/文章数据，基于账号历史基准和可选对标账号配置分析为什么数据好或差、差在哪里、怎么提升、如何固定有效表达，并生成下一期选题、标题、图文卡片、短视频脚本和公众号文章思路。Use when the user asks to 统计创作者数据、生成每日复盘、分析小红书/抖音/公众号内容表现、读取已发布图文视频文章、判断下一期选题、生成下一期小红书图文/抖音视频/公众号文章文案思路、设置每日内容数据自动复盘。
---

# Creator Analytics

Use this skill as a portable one-click workflow for creator account analytics across Xiaohongshu, Douyin, and WeChat Official Account.

## Primary Entry

Run only the public entrypoint unless debugging internals:

```bash
python scripts/one_click_review.py
```

Common options:

```bash
python scripts/one_click_review.py --date 2026-06-17
python scripts/one_click_review.py --platform xhs
python scripts/one_click_review.py --platform douyin
python scripts/one_click_review.py --platform wechat
python scripts/one_click_review.py --platform all
python scripts/one_click_review.py --headed
python scripts/one_click_review.py --data-dir D:\creator-analytics-data
```

For scheduled daily execution on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily_review.ps1
```

To install a Windows daily task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -At 09:00
```

## Workflow

The workflow performs:

1. Collect previous-day 小红书, 抖音, and 微信公众号 published content.
2. Normalize each item into a shared model: platform, content type, publish time, title, content summary, metrics, URLs, and collection status.
3. Append normalized items to `data/history/content_history.jsonl`.
4. Compare each item against same-platform, same-content-type account history. Use the latest 30 items; if fewer than 5 exist, use fallback thresholds and mark low confidence.
5. Read optional benchmark account config from `config/benchmark_accounts.json`. If absent, clearly state external benchmarking is not configured.
6. Generate Markdown and JSON outputs:
   - `data/output/report_YYYY-MM-DD.md`
   - `data/output/analysis_YYYY-MM-DD.json`

## Daily Review Behavior

For requests like `统计昨天数据`, `生成昨日复盘`, `分析为什么差`, `下一期做什么`, or scheduled daily review:

1. Run `python scripts/one_click_review.py`.
2. Read the generated Markdown report and JSON analysis when needed.
3. Return the key diagnosis and next-content recommendation.
4. If the user asks for execution-ready content, expand the included next-content plan into full Xiaohongshu copy, Douyin script, or WeChat article.

If a platform has no new content, say so clearly. If collection fails, mark it as collection failure and never treat it as no new content.

## Analysis Standard

Do not only summarize metrics. Use the report to answer:

- **为什么差**: Diagnose weak traffic entry, weak title hook, unclear value, weak interaction design, poor content-format fit, or timing/form mismatch.
- **差在哪里**: Compare views/reads, likes, comments, collects, shares, and WeChat wows against account historical baseline.
- **怎么提升**: Provide one concrete next action, such as rewriting the first 12 title characters, adding a table/checklist, changing the first 3 seconds, or turning a comment question into the next title.
- **为什么好**: Identify the topic, hook, structure, save value, comment potential, or share-worthy conclusion that drove performance.
- **如何固定下来**: Convert working patterns into reusable title formulas, hook formulas, content structures, comment prompts, and platform-specific formats.

For Meihua Yishu content, keep public-facing recommendations in `国学文化科普`, `传统文化学习`, and `古人思维方式` framing.

## Platform Notes

- 小红书: collect views, likes, comments, collects, and shares where visible. Treat high collect/low like as useful but emotionally underpowered.
- 抖音: collect views, likes, comments, and content type. Treat low views as a first-3-seconds/title-entry problem before over-optimizing later structure.
- 微信公众号: collect article reads, likes, comments, and 在看 where visible. If a metric is hidden or unavailable, preserve it as `null` / `未取到`, not `0`.

## Benchmark Accounts

External benchmark accounts are optional in v1. Copy the example file before filling real accounts:

```text
config/benchmark_accounts.example.json -> config/benchmark_accounts.json
```

If no benchmark config exists, the report must say `未配置对标账号` and continue using account history. When benchmark accounts are configured, use them as a future extension point for same-platform topic and interaction-structure comparison; do not block the daily report if benchmark collection is unavailable.

## Portable Or Multi-Agent Use

When another agent or machine needs this skill:

1. Copy the whole `creator-analytics` folder.
2. Run `python scripts/validate_skill.py`.
3. Install Playwright if needed.
4. Use `--data-dir` to keep login state and reports outside the copied skill:

```bash
python scripts/one_click_review.py --data-dir D:\creator-analytics-data
```

Do not copy a live user's browser profile to an untrusted machine. Prefer a fresh login in the target environment.

## Runtime State

Runtime data is private and should not be committed:

- `data/browser/` stores persistent browser profiles and login state.
- `data/cookies/` stores Playwright storage state snapshots.
- `data/history/` stores account historical performance.
- `data/output/` stores JSON analysis and Markdown reports.
- `data/logs/` stores scheduled-task logs.

First run on a new machine or new data directory may require:

```bash
python scripts/one_click_review.py --headed
```

After successful login, later runs should reuse the saved browser state.

## Validation

After copying or editing this skill, run:

```bash
python scripts/validate_skill.py
python -m unittest discover -s tests
```

If Playwright is missing:

```bash
python -m pip install playwright
python -m playwright install chromium
```
