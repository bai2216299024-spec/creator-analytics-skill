# Creator Analytics Changelog

This file records user-facing improvements for every GitHub update. Keep it readable for creators and portable for other agents.

## 2026-06-20

### Optimized

- Added a required GitHub update rule: every future push must include a changelog entry describing what was optimized.
- Documented the release checklist in SKILL.md so other agents know to update this file before committing.

### Why It Matters

- GitHub history now explains product-level improvements, not only code diffs.
- Future skill users can quickly see whether a version improved collection, diagnosis, automation, privacy, or content recommendations.

### Verification

- Skill validation passed.
- Unit tests passed.
- Documentation-only update; no runtime private data was added.

## 2026-06-19

### Optimized

- Added distribution / possible traffic-limit diagnosis to daily analysis.
- Added distribution_diagnosis to JSON output for reuse by other agents.
- Added a Distribution / Limit Diagnosis section to the Markdown daily report.
- Added tests for low reach with strong engagement and multi-platform slump scenarios.

### Why It Matters

- The skill no longer treats all weak performance as content failure.
- It can distinguish likely content-entry weakness from possible initial recommendation-pool weakness.
- It gives recovery actions such as retesting the same topic with a new title/opening, or entering account recovery mode when all platforms slump together.

### Verification

- Unit tests passed.
- Skill validation passed.
- Dry-run scheduling flow passed.
- Privacy scan found no high-risk secrets in the GitHub copy.
