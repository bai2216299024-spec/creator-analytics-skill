---
name: creator-analytics
description: 一键采集并复盘小红书/抖音/公众号昨日数据，对比历史基准诊断好差原因与分发异常，并生成下一期选题和内容思路。当用户要求统计创作者数据、生成每日复盘、分析内容表现、诊断限流、生成选题/文案方向时使用。
---

# Creator Analytics

> **v2.0 · 2026-06-24** — 6 new analysis dimensions, L1→L4 hierarchical diagnosis, dynamic topic generation, percentile-based thresholds. Full optimization log: `references/darwin-optimization-v2.md`.

## Primary Entry

```bash
python scripts/one_click_review.py                    # 默认：昨日三平台
python scripts/one_click_review.py --date 2026-06-17   # 指定日期
python scripts/one_click_review.py --platform xhs       # 单平台
python scripts/one_click_review.py --headed             # 首次/登录过期
python scripts/one_click_review.py --skip-comments      # 只看指标
python scripts/setup.sh               # 安装/校验全部依赖
python scripts/validate_skill.py         # 校验 skill 完整性
```

🔴 CHECKPOINT · 🛑 STOP: Before running any collection script, confirm with the user ("即将采集[平台名]数据，是否继续？") and wait for explicit approval. This is required especially when --headed may be needed (first run or login expired).

After collection, review output files. If a platform shows no data, confirm real no-publish vs collection failure before trusting analysis.

## Workflow

1. Collect previous-day content from 小红书/抖音/微信公众号
2. Normalize into platform/content_type/metrics model
3. Append to `data/history/content_history.jsonl`
4. Compare each item against same-platform same-type history (last 30 items; fallback if < 5)
5. Read optional `config/benchmark_accounts.json`; if absent, state 未配置对标账号
6. Diagnose distribution anomalies (6 signals, see below)
7. Collect comments (default 50/item); separate is_self=true from is_self=false
8. Generate `data/output/report_YYYY-MM-DD.md` + `data/output/analysis_YYYY-MM-DD.json`

## Daily Review Behavior

For requests like `统计昨天数据` / `分析为什么差` / `下一期做什么`:

1. 🔴 Confirm with user before running: "即将采集昨日数据，是否继续？" Wait for explicit approval.
2. Run `python scripts/one_click_review.py`
3. Read the generated report — 🔴 CHECKPOINT: verify all expected platforms are present before diagnosing
4. Return key diagnosis + next-content recommendation
5. If user wants execution-ready content, expand the next-content plan into full copy/script/article

**Collection failure ≠ no new content.** Mark explicitly; never conflate.

## 🔴 Critical Rules

### Next-Content Novelty Rule

**Inherit the mechanism, not the material.** The high-performing post is evidence, not the new subject.

1. Extract performance logic: life scene, title hook, saveable structure, comment prompt, timing, format
2. Pick a fresh scene/question/angle that does NOT repeat the previous title, object, story, or example
3. Output `source_reference`, `inherited_logic`, `avoid_repeating`, `fresh_angle` in JSON plan
4. In Markdown, state what is inherited AND what must not be repeated

### Never treat null metrics as 0

If a platform hides a metric, preserve `null`/`未取到` — never substitute 0.

### Never claim 限流/降权 without evidence

Use hierarchical L1→L4 diagnosis. `none` level when no signals detected.

### Never use is_self=true comments as audience demand

Only is_self=false comments with high/medium confidence drive topic recommendations.

## Analysis Standard

The report answers seven questions per content item:

| Question | Diagnostic Target |
|---|---|
| 为什么差 | Weak entry, weak hook, unclear value, weak interaction design, poor format fit |
| 差在哪里 | Metrics vs historical baseline (per-platform, same-type) |
| 如何提升 | One concrete action (rewrite first 12 chars, add checklist, change first 3 seconds) |
| 为什么好 | Topic, hook, structure, save value, comment potential, share-worthy conclusion |
| 如何固定下来 | Convert working patterns into reusable formulas/structures/prompts |
| 是否限流 | Use L1→L4 tree; never claim punishment without evidence |
| 评论怎么用 | User comments = demand/questions/clues; creator replies = coverage metric, not demand |

**Six analysis dimensions** beyond metric summary (v2):

- **趋势追踪（7日滚动）**: Day vs 7-day average — distinguishes noise from trend
- **内容结构诊断**: Structure-to-performance mapping (tables, checklists, Q&A hooks → views/collects)
- **互动质量分析**: Collect/like ratio, question-comment ratio, comment-rate trends
- **选题疲劳预警**: Topic-cluster frequency + marginal-decay detection
- **层次化根因 L1→L4**: Environment → Account → Topic → Expression
- **选题多样性**: Content-type/topic-cluster distribution with coverage gaps

Classification uses **percentile thresholds** (P25/P75 from history) not fixed ratios. Confidence graded low/medium/high.

## Distribution / Limit Diagnosis

Six signals (priority-ordered decision logic):

| Signal | Criteria | Action |
|---|---|---|
| 价值-曝光错配 | High save rate + low views | Fix title/cover, test different posting times |
| 单日暴跌 | view_ratio < 0.3 (single day) | Check sensitive keywords/cover review before changing topic |
| 互动率异常升高 | interaction_rate > 15% | Spot-check comment quality: controversy or genuine engagement? |
| 疑似初始推荐池未放量 | Low reach + strong interaction | Same topic, change title/scene, test again |
| 内容入口与互动双弱 | Low reach + low interaction | Fix packaging before blaming platform |
| 三平台同步低迷 | 2+ platforms simultaneously low | Account recovery mode: safer framing, concrete cases |

For Meihua Yishu content: frame recommendations as `国学文化科普` / `传统文化学习` / `古人思维方式`.

## Platform Notes

- **小红书**: High collect/low like = save-value signal. Never treat as weakness.
- **抖音**: Low views = first-3-seconds/title problem before optimizing structure.
- **微信公众号**: Hidden metrics → `null`/`未取到`, never `0`.

## Comment Rules

- Only is_self=false + high/medium confidence → next-topic evidence
- is_self=true → reply coverage metric, not audience demand
- No thread info → call them "user questions", not "unanswered questions"
- Default: 50 comments per item. `--skip-comments` for metric-only runs.

For WeChat collection, runtime state, benchmark config, zone sync, and detailed anti-patterns: see `references/` directory and code comments in `scripts/`.

## 反例与黑名单（Anti-patterns）

### 🚫 数据类

| 反例 | 正确做法 |
|---|---|
| 把 `null`/`未取到` 当 `0` | 保持 null，报「未取到」 |
| 声称「限流」无证据 | 分级诊断，无证据标 `none` |
| 跨平台套用诊断 | 按平台独立分析 |
| 采集失败=无发布 | 标记 `collection_failed` |

### 🚫 内容生产类

| 反例 | 正确做法 |
|---|---|
| 直接改编历史最高分内容 | 提取机制，换场景/角度 |
| 把 is_self=true 当受众需求 | 只用 is_self=false 高置信度评论 |
| 无 thread 说「未回答问题」 | 称「用户评论/高价值评论」 |

### 🚫 安全类

| 反例 | 正确做法 |
|---|---|
| 复制浏览器 profile 到不可信机器 | 新机器重新扫码 |
| 提交 wechat_api.json / self_accounts.json | 加入 .gitignore |

### 🚫 诊断类（v2 新增）

| 反例 | 正确做法 |
|---|---|
| 单日波动当趋势判读 | 先看 7 日滚动 + P25/P75 |
| 固定阈值（0.8/1.2）一刀切 | 用历史百分位 |
| 不区分 L1→L4 就下结论 | 按四层根因树排查 |
| 只看互动数量不看质量 | 加入收藏-点赞比、问题评论占比 |
| 选题不检查多样性 | 加入 diversity report，填覆盖缺口 |

### 🚫 选题推荐类（v2 新增）

| 反例 | 正确做法 |
|---|---|
| 三平台推荐相同选题 | 按平台特性打分 |
| AB 建议空洞（"测试新场景"） | 基于最弱信号生成具体变量 |
| 依赖 7 个硬编码场景 | 从 history 动态生成 |

### 🚫 流程类

| 反例 | 正确做法 |
|---|---|
| 一平台失败就放弃全报告 | 标记失败，继续其他平台 |
| headless 跑微信采集 | 先 headed 建立登录态或配 API |

## Scheduled Run Pattern

When running as a cron job or scripted flow (no interactive user):

1. **Read report**: `read_file(report_path)` from `data/output/report_YYYY-MM-DD.md`
2. **Read analysis**: `read_file(analysis_path)` from `data/output/analysis_YYYY-MM-DD.json`
3. **Generate topics**: Based on diagnostic conclusions (not repeating published titles), create 3 new topics covering different `content_type` categories
4. **Deliver**: Summarize key findings + topic recommendations

## Quick Reference

| Topic | Path |
| 抖音发布 | `references/douyin-publish.md` |
| 平台排错 | `references/platform_notes.md` |
| 优化日志 | `references/darwin-optimization-v2.md` |
| 验证 | `python scripts/validate_skill.py` |
