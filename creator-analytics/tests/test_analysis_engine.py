import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_engine import analyze_daily_data, normalize_platform_data
from history_store import append_history, load_history


class CreatorAnalyticsAnalysisTests(unittest.TestCase):
    def test_normalizes_legacy_platform_data_to_unified_items(self):
        data = {
            "platform": "小红书",
            "date": "2026-06-17",
            "items": [
                {
                    "publish_date": "2026-06-17 20:01",
                    "title": "梅花易数入门｜用8个符号概括万物？上篇",
                    "content": "正文摘要",
                    "content_type": "图文/笔记",
                    "views": 127,
                    "likes": 0,
                    "comments": 9,
                    "collects": 11,
                    "shares": 1,
                }
            ],
        }

        items = normalize_platform_data("xhs", data)

        self.assertEqual(items[0]["platform"], "小红书")
        self.assertEqual(items[0]["publish_time"], "2026-06-17 20:01")
        self.assertEqual(items[0]["content_summary"], "正文摘要")
        self.assertEqual(items[0]["metrics"]["views"], 127)
        self.assertEqual(items[0]["metrics"]["likes"], 0)
        self.assertEqual(items[0]["metrics"]["collects"], 11)
        self.assertEqual(items[0]["collection_status"], "ok")

    def test_history_append_dedupes_same_platform_time_and_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "content_history.jsonl"
            item = {
                "platform": "小红书",
                "content_type": "图文",
                "publish_time": "2026-06-17 20:01",
                "title": "同一条内容",
                "metrics": {"views": 10, "likes": 1, "comments": 0},
            }

            append_history(history_file, [item])
            append_history(history_file, [dict(item, metrics={"views": 20, "likes": 2, "comments": 1})])

            rows = load_history(history_file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["metrics"]["views"], 20)

    def test_analysis_explains_bad_and_good_performance_with_next_content(self):
        daily = {
            "xhs": {
                "platform": "小红书",
                "date": "2026-06-17",
                "items": [
                    {
                        "publish_date": "2026-06-17 20:01",
                        "title": "梅花易数入门｜用8个符号概括万物？上篇",
                        "content": "用八卦符号解释入门概念",
                        "content_type": "图文/笔记",
                        "views": 127,
                        "likes": 0,
                        "comments": 9,
                        "collects": 11,
                        "shares": 1,
                    }
                ],
            },
            "douyin": {
                "platform": "抖音",
                "date": "2026-06-17",
                "items": [
                    {
                        "publish_date": "2026年06月17日 20:00",
                        "title": "梅花易数入门｜三要感应法：卦未成，应已到。",
                        "content": "三要感应法，取动不取静，取异不取常。",
                        "content_type": "图文",
                        "views": 35,
                        "likes": 1,
                        "comments": 2,
                    }
                ],
            },
        }
        history = [
            {
                "platform": "小红书",
                "content_type": "图文/笔记",
                "publish_time": f"2026-06-{day:02d} 20:00",
                "title": f"历史内容 {day}",
                "metrics": {"views": 80 + day, "likes": 8, "comments": 1, "collects": 3},
            }
            for day in range(1, 7)
        ]

        analysis = analyze_daily_data(daily, history, benchmark_config={})

        self.assertEqual(analysis["benchmark_status"]["external"], "未配置对标账号")
        self.assertTrue(analysis["content_diagnostics"])
        joined = json.dumps(analysis, ensure_ascii=False)
        self.assertIn("为什么差", joined)
        self.assertIn("为什么好", joined)
        self.assertIn("如何提升", joined)
        self.assertIn("固定下来", joined)
        self.assertIn("下一期", joined)
        self.assertIn("小红书", analysis["next_content"]["xhs"]["platform"])
        self.assertIn("抖音", analysis["next_content"]["douyin"]["platform"])
        self.assertIn("公众号", analysis["next_content"]["wechat"]["platform"])


if __name__ == "__main__":
    unittest.main()
