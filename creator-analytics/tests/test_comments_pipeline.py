import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_engine import analyze_daily_data, normalize_platform_data
from comments_utils import classify_comment_author, normalize_comment, summarize_comment_insights
from generate_report import build_comments_section


class CommentsPipelineTests(unittest.TestCase):
    def test_normalizes_comment_and_classifies_self_by_configured_alias(self):
        raw = {
            "comment_id": "c1",
            "author_name": "清净法典",
            "author_role": "",
            "content": "后续可以讲一个具体案例吗？",
            "publish_time": "2026-06-19 10:00",
            "like_count": "3",
            "reply_to": None,
            "source_area": "detail_comments",
        }
        self_accounts = {"xhs": {"aliases": ["清净法典"]}}

        comment = normalize_comment(raw, "xhs", self_accounts)

        self.assertEqual(comment["comment_id"], "c1")
        self.assertEqual(comment["author_name"], "清净法典")
        self.assertEqual(comment["like_count"], 3)
        self.assertTrue(comment["is_self"])
        self.assertEqual(comment["collection_status"], "ok")

    def test_classifies_other_comment_and_keeps_unknown_author_as_none(self):
        self_accounts = {"douyin": {"aliases": ["清净法典"]}}

        other = classify_comment_author("普通用户", "", "douyin", self_accounts)
        unknown = classify_comment_author("", "", "douyin", self_accounts)

        self.assertFalse(other)
        self.assertIsNone(unknown)

    def test_analysis_preserves_comments_detail_and_builds_insights_from_non_self_comments(self):
        daily = {
            "xhs": {
                "platform": "小红书",
                "date": "2026-06-19",
                "items": [
                    {
                        "publish_date": "2026-06-19 08:00",
                        "title": "八卦的具体用法",
                        "content_type": "图文/笔记",
                        "views": 100,
                        "likes": 5,
                        "comments": 2,
                        "collects": 3,
                        "comments_detail": [
                            {
                                "comment_id": "u1",
                                "author_name": "用户A",
                                "content": "能不能讲一个生活案例？",
                                "is_self": False,
                                "like_count": 4,
                                "collection_status": "ok",
                            },
                            {
                                "comment_id": "me1",
                                "author_name": "清净法典",
                                "content": "下一期安排案例。",
                                "is_self": True,
                                "like_count": 0,
                                "collection_status": "ok",
                            },
                        ],
                    }
                ],
            }
        }

        normalized = normalize_platform_data("xhs", daily["xhs"])
        analysis = analyze_daily_data(daily, history=[], benchmark_config={})
        joined = json.dumps(analysis, ensure_ascii=False)

        self.assertEqual(len(normalized[0]["comments_detail"]), 2)
        self.assertIn("comment_insights", analysis)
        self.assertIn("生活案例", joined)
        self.assertIn("自己账号回复", joined)
        self.assertNotIn("下一期安排案例。作为用户需求", joined)

    def test_comment_insights_summarize_unanswered_questions_and_reply_coverage(self):
        item = {
            "platform": "抖音",
            "title": "八卦的具体用法",
            "comments_detail": [
                {"author_name": "用户A", "content": "这个怎么用在工作选择？", "is_self": False, "like_count": 2},
                {"author_name": "用户B", "content": "收藏了，想看案例", "is_self": False, "like_count": 1},
                {"author_name": "清净法典", "content": "可以，下一条讲案例。", "is_self": True, "like_count": 0},
            ],
        }

        insights = summarize_comment_insights([item])

        self.assertEqual(insights["total_comments"], 3)
        self.assertEqual(insights["other_comments"], 2)
        self.assertEqual(insights["self_comments"], 1)
        self.assertEqual(insights["self_reply_coverage"], "1/2")
        self.assertTrue(insights["next_topic_candidates"])
        self.assertIn("工作选择", insights["unanswered_questions"][0]["content"])

    def test_report_renders_comment_insights_section(self):
        analysis = {
            "comment_insights": {
                "total_comments": 2,
                "other_comments": 1,
                "self_comments": 1,
                "self_reply_coverage": "1/1",
                "other_summary": ["用户追问：能不能讲一个生活案例？"],
                "self_summary": ["自己账号回复：下一期安排案例。"],
                "unanswered_questions": [],
                "next_topic_candidates": [{"platform": "小红书", "title": "八卦用法", "content": "能不能讲一个生活案例？"}],
                "collection_failures": [],
            }
        }

        section = build_comments_section(analysis)

        self.assertIn("## 评论洞察", section)
        self.assertIn("他人评论", section)
        self.assertIn("自己账号回复", section)
        self.assertIn("生活案例", section)


if __name__ == "__main__":
    unittest.main()
