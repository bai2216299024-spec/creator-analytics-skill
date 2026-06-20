import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analysis_engine import analyze_daily_data, normalize_platform_data
from comments_utils import (
    classify_comment_author,
    extract_platform_comments_from_blocks,
    normalize_comment,
    summarize_comment_insights,
)
from generate_report import build_comments_section, build_platform_section
from scrape_wechat import classify_empty_page, is_relogin_page, mark_browser_launch_failure, open_login_entry, profile_init_notice, verify_backend_access


class FakePage:
    def __init__(self, text):
        self.text = text
        self.visited_urls = []

    def inner_text(self, selector, timeout=0):
        return self.text

    def goto(self, url, wait_until=None, timeout=0):
        self.visited_urls.append(url)
        self.text = "微信公众平台\n扫码登录\n请使用微信扫描二维码"

    def wait_for_timeout(self, timeout):
        return None


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
        self.assertEqual(comment["confidence"], "high")
        self.assertEqual(comment["collection_status"], "ok")

    def test_plain_page_text_does_not_become_comments(self):
        blocks = [
            "八卦的具体用法\n播放量 100\n点赞 2\n评论 1\n编辑作品",
            "作品管理\n全部作品\n查看数据\n发布于 2026-06-19",
        ]

        comments = extract_platform_comments_from_blocks(blocks, "xhs", {}, limit=50)

        self.assertEqual(comments, [])

    def test_structured_comment_block_becomes_medium_or_high_confidence_comment(self):
        blocks = ["用户A\n能不能讲一个生活案例？\n3赞\n2026-06-19"]

        comments = extract_platform_comments_from_blocks(blocks, "douyin", {}, limit=50)

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["author_name"], "用户A")
        self.assertIn("生活案例", comments[0]["content"])
        self.assertIn(comments[0]["confidence"], {"medium", "high"})

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
        self.assertEqual(insights["self_reply_ratio"], "1/2")
        self.assertTrue(insights["topic_candidates_from_comments"])
        self.assertIn("工作选择", insights["user_questions"][0]["content"])
        self.assertEqual(insights["unanswered_questions"], [])

    def test_self_and_unknown_comments_do_not_enter_topic_candidates(self):
        item = {
            "platform": "小红书",
            "title": "八卦用法",
            "comments_detail": [
                {"author_name": "用户A", "content": "想看生活案例", "is_self": False, "confidence": "medium"},
                {"author_name": "创作者本人", "content": "下一期我来讲。", "is_self": True, "confidence": "high"},
                {"author_name": "", "content": "未知来源问题", "is_self": None, "confidence": "medium"},
                {"author_name": "用户B", "content": "低置信度内容", "is_self": False, "confidence": "low"},
            ],
        }

        insights = summarize_comment_insights([item])
        joined = json.dumps(insights["topic_candidates_from_comments"], ensure_ascii=False)

        self.assertIn("想看生活案例", joined)
        self.assertNotIn("下一期我来讲", joined)
        self.assertNotIn("未知来源问题", joined)
        self.assertNotIn("低置信度内容", joined)

    def test_unanswered_questions_only_when_reply_threads_exist(self):
        item = {
            "platform": "微信公众号",
            "title": "八卦用法",
            "comments_detail": [
                {"comment_id": "c1", "author_name": "用户A", "content": "这个怎么用？", "is_self": False, "confidence": "high"},
                {"comment_id": "c2", "author_name": "用户B", "content": "能讲案例吗？", "is_self": False, "confidence": "high"},
                {"comment_id": "r1", "author_name": "公众号作者", "content": "可以。", "is_self": True, "reply_to": "c1", "confidence": "high"},
            ],
        }

        insights = summarize_comment_insights([item])
        joined = json.dumps(insights["unanswered_questions"], ensure_ascii=False)

        self.assertNotIn("这个怎么用", joined)
        self.assertIn("能讲案例吗", joined)

    def test_report_renders_comment_insights_section(self):
        analysis = {
            "comment_insights": {
                "total_comments": 2,
                "other_comments": 1,
                "self_comments": 1,
                "self_reply_ratio": "1/1",
                "comment_collection_health": {"ok": 1, "failed": 0, "empty": 0},
                "other_summary": ["用户追问：能不能讲一个生活案例？"],
                "self_reply_summary": ["自己账号回复：下一期安排案例。"],
                "unanswered_questions": [],
                "user_questions": [{"platform": "小红书", "title": "八卦用法", "content": "能不能讲一个生活案例？"}],
                "topic_candidates_from_comments": [{"platform": "小红书", "title": "八卦用法", "content": "能不能讲一个生活案例？"}],
                "collection_failures": [],
            }
        }

        section = build_comments_section(analysis)

        self.assertIn("## 评论洞察", section)
        self.assertIn("他人评论", section)
        self.assertIn("自己账号回复", section)
        self.assertIn("用户高价值问题", section)
        self.assertIn("生活案例", section)
        self.assertNotIn("未回复但值得回复", section)

    def test_wechat_profile_notice_when_cookie_exists_without_profile(self):
        notice = profile_init_notice(profile_exists=False, cookie_exists=True)

        self.assertIn("需要 headed 登录一次", notice)
        self.assertIn("wechat_profile", notice)

    def test_wechat_empty_page_classifies_no_matching_date(self):
        page = FakePage("首页\n发表记录\n2026-06-19\n第一期文章\n阅读 100")

        status = classify_empty_page(page, "2026-06-20")

        self.assertEqual(status["collection_status"], "empty")
        self.assertEqual(status["empty_reason"], "no_matching_date")

    def test_wechat_empty_page_classifies_parse_failure_when_target_date_visible(self):
        page = FakePage("首页\n发表记录\n2026-06-20\n阅读 100\n点赞 3")

        status = classify_empty_page(page, "2026-06-20")

        self.assertEqual(status["collection_status"], "list_unreadable")
        self.assertEqual(status["empty_reason"], "target_date_visible_but_parse_failed")

    def test_wechat_report_does_not_claim_no_publish_when_list_unreadable(self):
        section = build_platform_section(
            "wechat",
            {
                "platform": "微信公众号",
                "date": "2026-06-20",
                "items": [],
                "empty": True,
                "error": None,
                "collection_status": "list_unreadable",
                "empty_reason": "target_date_visible_but_parse_failed",
                "login_status": "manual_login_completed",
            },
        )

        self.assertIn("不能直接等同于无新增发布", section)
        self.assertIn("target_date_visible_but_parse_failed", section)

    def test_wechat_report_does_not_claim_no_publish_on_dry_run(self):
        section = build_platform_section(
            "wechat",
            {
                "platform": "微信公众号",
                "date": "2026-06-20",
                "items": [],
                "empty": True,
                "error": None,
                "collection_status": "skipped",
                "empty_reason": "dry_run",
                "login_status": "not_checked",
            },
        )

        self.assertIn("未检查是否新增发布", section)
        self.assertNotIn("昨日无新增发布内容。", section)

    def test_wechat_manual_login_must_reach_backend(self):
        result = {"login_status": "manual_login_completed", "collection_status": "pending", "empty_reason": None}
        page = FakePage("微信公众平台\n扫码登录\n请使用微信扫描二维码")

        with self.assertRaises(RuntimeError):
            verify_backend_access(page, result)

        self.assertEqual(result["login_status"], "manual_login_not_accepted")
        self.assertEqual(result["collection_status"], "login_required")
        self.assertEqual(result["empty_reason"], "login_required")

    def test_wechat_relogin_page_opens_login_entry(self):
        page = FakePage("公众号\n请重新登录")

        self.assertTrue(is_relogin_page(page))
        open_login_entry(page)

        self.assertTrue(page.visited_urls)
        self.assertFalse(is_relogin_page(page))
        self.assertIn("扫码登录", page.inner_text("body"))

    def test_wechat_browser_profile_lock_is_reported_without_traceback(self):
        result = {"collection_status": "pending", "empty_reason": None, "login_status": "unknown", "error": None}

        mark_browser_launch_failure(result, RuntimeError("Target page, context or browser has been closed; user data directory is already in use"))

        self.assertEqual(result["collection_status"], "failed")
        self.assertEqual(result["empty_reason"], "browser_profile_locked")
        self.assertEqual(result["login_status"], "browser_launch_failed")
        self.assertIn("profile", result["error"])


if __name__ == "__main__":
    unittest.main()
