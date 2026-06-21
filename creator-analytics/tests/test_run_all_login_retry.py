import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_all


class RunAllLoginRetryTests(unittest.TestCase):
    def test_detects_login_required_from_platform_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CREATOR_ANALYTICS_DATA_DIR"] = tmp
            output = Path(tmp) / "output"
            output.mkdir(parents=True)
            (output / "wechat_data.json").write_text(
                json.dumps({"error": "微信公众号登录态过期，请使用 --headed 模式扫码登录"}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertTrue(run_all.platform_requires_login("wechat"))

    def test_retries_failed_non_wechat_platform_with_headed_when_login_required(self):
        calls = []

        def fake_run_script(script_name, *args):
            calls.append((script_name, args))
            return 1 if len(calls) == 1 else 0

        with patch.object(run_all, "run_script", side_effect=fake_run_script), patch.object(run_all, "platform_requires_login", return_value=True):
            code = run_all.run_platform("xhs", "scrape_xhs.py", ["--date", "2026-06-18"], auto_login=True)

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("scrape_xhs.py", ("--date", "2026-06-18")))
        self.assertEqual(calls[1], ("scrape_xhs.py", ("--date", "2026-06-18", "--headed")))

    def test_common_args_include_comment_options(self):
        args = run_all.build_common_args("2026-06-18", headed=False, dry_run=False, comments_limit=25, skip_comments=True)

        self.assertEqual(args, ["--date", "2026-06-18", "--comments-limit", "25", "--skip-comments"])

    def test_wechat_runs_headed_first_when_auto_login_enabled(self):
        calls = []

        def fake_run_script(script_name, *args):
            calls.append((script_name, args))
            return 0

        with patch.object(run_all, "run_script", side_effect=fake_run_script):
            code = run_all.run_platform("wechat", "scrape_wechat.py", ["--date", "2026-06-20"], auto_login=True)

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("scrape_wechat.py", ("--date", "2026-06-20", "--headed")))

    def test_wechat_headed_first_failure_is_not_retried_again(self):
        calls = []

        def fake_run_script(script_name, *args):
            calls.append((script_name, args))
            return 1

        with patch.object(run_all, "run_script", side_effect=fake_run_script), patch.object(run_all, "platform_requires_login", return_value=True):
            code = run_all.run_platform("wechat", "scrape_wechat.py", ["--date", "2026-06-20"], auto_login=True)

        self.assertEqual(code, 1)
        self.assertEqual(calls, [("scrape_wechat.py", ("--date", "2026-06-20", "--headed"))])

    def test_wechat_does_not_force_headed_when_auto_login_disabled(self):
        calls = []

        def fake_run_script(script_name, *args):
            calls.append((script_name, args))
            return 0

        with patch.object(run_all, "run_script", side_effect=fake_run_script):
            code = run_all.run_platform("wechat", "scrape_wechat.py", ["--date", "2026-06-20"], auto_login=False)

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("scrape_wechat.py", ("--date", "2026-06-20")))

    def test_dry_run_disables_zone_sync_for_report_generation(self):
        calls = []

        def fake_run_script(script_name, *args):
            calls.append((script_name, args))
            return 0

        argv = ["run_all.py", "--dry-run", "--date", "2026-06-20", "--skip-comments"]
        with patch.object(sys, "argv", argv), patch.object(run_all, "run_script", side_effect=fake_run_script):
            code = run_all.main()

        self.assertEqual(code, 0)
        self.assertIn(("generate_report.py", ("--date", "2026-06-20", "--no-zone-sync")), calls)


if __name__ == "__main__":
    unittest.main()
