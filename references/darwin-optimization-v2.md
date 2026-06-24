# Darwin Skill 2.0 Optimization — creator-analytics v2.0

> **Date**: 2026-06-24 | **Score**: 68.5 → 84.1 (+15.6) | **Rounds**: 3

## Baseline (Phase 1)

| Dim | Weight | Before | Key Weakness |
|-----|--------|--------|-------------|
| 1. Frontmatter | 7 | 7/10 | description > 1024 chars |
| 2. Workflow clarity | 12 | 8/10 | dense sections |
| 3. Failure mode encoding | 12 | 7/10 | diagnosis logic linear, no branching |
| 5. Executable specificity | 17 | 7/10 | FRESH_ANGLE_BANK hardcoded, AB samples vague |
| 8. Actual performance | 23 | 5/10 | shallow analysis, fixed thresholds, stale topic pool |
| **Total** | | **68.5** | |

## Changes (Phase 2)

### Round 1: analysis_engine.py (694 → 1515 lines)

**Axis 1 — New analysis dimensions (+5 functions)**:
- `build_trend_analysis()` — 7-day rolling averages, day-over-day change
- `analyze_content_structure()` — structure-to-performance mapping (tables, checklists, Q&A hooks)
- `detect_content_fatigue()` — topic-cluster frequency + marginal-decay detection
- `analyze_engagement_quality()` — collect/like ratio, question-comment ratio, comment-rate trends
- `calibrate_score_weights()` — data-driven weight importance from history

**Axis 2 — Diagnostic accuracy (+1 function, +4 modifications)**:
- `diagnose_hierarchical()` — L1 environment → L2 account → L3 topic → L4 expression root-cause tree
- `classify_item()` — fixed 0.8/1.2 thresholds → percentile-based (P25/P75 from history)
- `diagnose_distribution_for_item()` — 3 signals → 6 signals (+单日暴跌, +互动率异常升高, +价值-曝光错配)
- `compute_confidence()` — low/normal → low/medium/high with σ-distance
- `diagnose_item()` — added structure-analysis tags, engagement quality labels

**Axis 3 — Topic recommendation (+2 functions, +3 modifications)**:
- `generate_fresh_angles()` — hardcoded 7-scene bank → template-driven dynamic generation from winning patterns
- `score_topic_fitness()` — platform-specific scoring (小红书: save-value, 抖音: hook-conflict, 公众号: depth)
- `build_known_topics_from_history()` — auto-learn published topics from history
- `choose_fresh_angle()` — greedy first-match → scored selection with dynamic fallback
- `build_next_content()` — single-topic → diversity-aware with platform-differentiated recommendations
- `build_avoid_repeating()` — hardcoded KNOW_PUB_TOPICS → auto-populated from history

### Round 2: generate_report.py (482 → 587 lines)

Four new report sections:
- **趋势追踪（7日滚动）** — per-platform daily vs 7-day average
- **内容结构诊断** — table of structure patterns × avg views/collects
- **选题疲劳预警** — cluster frequency + score-trend alerts
- **互动质量分析** — collect/like ratio, question-comment %, comment rate

Modified sections:
- **精准诊断** — added L1→L4 hierarchical diagnosis per item, multi-level confidence
- **下一期内容决策** — added platform fitness scores, diversity report, specific AB samples
- **分发/限流诊断** — expanded to 6-signal priority-ordered decision logic

### Round 3: SKILL.md (456 → 183 lines, 76% reduction)

Moved implementation details to references; kept only guardrail rules the agent must remember. Added 8 anti-patterns across 2 new categories (diagnosis + topic recommendation).

## Tech Notes

- **Chinese-quote-in-Python-strings fix**: `"保留"概念"的"` breaks Python parsing. Replace inner ASCII `"` with `「」` (corner brackets) to avoid escape-hell.
- **No git fallback**: Darwin's `cp SKILL.md SKILL.md.bak.YYYYMMDD-HHMM` fallback works on Windows when git isn't available.
- **Smoke test pattern**: After each round, `python -c "from analysis_engine import ..."` + function call test before proceeding.

## Post-Optimization

| Dim | Before | After | Δ |
|-----|--------|-------|---|
| 3. Failure mode encoding | 7.0 | 8.5 | +1.8 |
| 5. Executable specificity | 7.0 | 8.5 | +2.6 |
| 7. Overall architecture | 7.0 | 8.5 | +1.8 |
| 8. Actual performance | 5.0 | 8.0 | +6.9 |
| 9. Anti-patterns/blacklist | 8.0 | 9.0 | +0.6 |
| **Total** | **68.5** | **84.1** | **+15.6** |

dim8 (actual performance) remains dry-run evaluated — full_test with real data would be the next validation step.
