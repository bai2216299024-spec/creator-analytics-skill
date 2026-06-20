# Creator Analytics Changelog

This file records user-facing improvements for every GitHub update. Keep it readable for creators and portable for other agents.

## 2026-06-21

### Optimized

- Added explicit WeChat empty-result evidence fields: collection_status, empty_reason, and login_status.
- Updated the Markdown report so unreadable WeChat lists or dry-runs are not reported as confirmed "no new publish".
- Added regression tests for no_matching_date, target-date-visible parse failures, list-unreadable reporting, and dry-run reporting.
- Made WeChat manual-login verification fail loudly when scanning does not actually reach the backend collection page.
- Added WeChat "please re-login" page handling: jump to the real scan-login entry instead of waiting on a dead-end page.
- Converted WeChat browser/profile launch failures into structured reportable errors instead of raw Playwright tracebacks.
- Prevented duplicate WeChat headed retries after the scheduler has already run WeChat in a visible browser.
- Changed the daily scheduler so WeChat Official Account collection runs with a visible browser first when auto-login is enabled.
- Kept dry-run, explicit --headed, and --no-auto-login behavior unchanged.
- Added regression coverage for the WeChat headed-first path and the no-auto-login path.

### Why It Matters

- The WeChat backend can challenge headless browser sessions even when a persistent profile exists.
- Running WeChat headed first avoids a false "login expired" pass and makes daily review behavior easier to understand.
- Empty WeChat results now carry enough evidence to distinguish "no matching publish date" from "the list was not readable".
- A manual scan that returns to the login page is now treated as login_required instead of a successful empty collection.
- The collector no longer waits on the blank "请重新登录" page; it redirects to the login entry or fails with a clear login_required status.
- If an existing WeChat collection browser is still using the persistent profile, the report now says browser_profile_locked and asks the user to close the old window before retrying.
- WeChat login failure now prompts once per run instead of retrying the same headed attempt twice.
- Other platforms still use the normal retry flow, so the change is scoped to the platform with the unstable headless session.

### Verification

- Targeted login retry unit test passed.
- Full unit test suite passed.
- Skill validation passed.
- Dry-run WeChat workflow passed without opening a browser.
- Privacy scan confirmed no real account names, cookies, profiles, history, reports, or logs are included in the public repo copy.

## 2026-06-20

### Optimized

- Hardened comment collection for production daily reviews: platform-specific containers only, no whole-page text fallback, explicit collection statuses, and confidence scoring.
- Changed comment insights to use user questions / high-value questions unless reliable reply thread data exists.
- Added comment collection health reporting and stricter topic-candidate filtering so creator replies and unknown-source comments do not drive next-topic recommendations.
- Added WeChat profile initialization notice when legacy cookie JSON exists but persistent profile has not been established.
- Upgraded WeChat Official Account login persistence from storage-state cookies only to a persistent browser profile.
- Added cross-platform comment-detail collection with comments_detail and comment_collection_status.
- Added creator-account comment classification through private config/self_accounts.json.
- Added comment insights to JSON analysis and Markdown reports, including other-user comments, self replies, unanswered questions, and next-topic candidates.
- Added --comments-limit and --skip-comments to the daily workflow.
- Added a required GitHub update rule: every future push must include a changelog entry describing what was optimized.
- Documented the release checklist in SKILL.md so other agents know to update this file before committing.

### Why It Matters

- GitHub history now explains product-level improvements, not only code diffs.
- Future skill users can quickly see whether a version improved collection, diagnosis, automation, privacy, or content recommendations.
- Daily reports can now use real audience comments for next-topic decisions while keeping creator replies separate.

### Verification

- Skill validation passed.
- Unit tests passed.
- Dry-run workflow passed with comments options.
- Privacy scan confirmed runtime private data and real self-account config are excluded.

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
