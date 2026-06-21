import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import wechat_api_client
from wechat_api_client import collect_wechat_api


class WeChatApiClientTests(unittest.TestCase):
    def test_missing_config_reports_api_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = collect_wechat_api(
                Path(tmp) / "wechat_api.json",
                Path(tmp) / "token.json",
                "2026-06-20",
            )

        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "api_not_configured")

    def test_api_unsupported_config_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "wechat_api.json"
            config_path.write_text(
                '{"appid":"YOUR_TEST_APPID","appsecret":"YOUR_WECHAT_OFFICIAL_ACCOUNT_APPSECRET","api_supported":false,"api_disabled_reason":"personal_unverified_official_account"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Exception, "api_unsupported:personal_unverified_official_account"):
                collect_wechat_api(config_path, Path(tmp) / "token.json", "2026-06-20")

    def test_collects_published_articles_and_metrics_without_network(self):
        responses = []

        def fake_request_json(url, payload=None, timeout=30):
            responses.append((url, payload))
            if "cgi-bin/token" in url:
                return {"access_token": "token", "expires_in": 7200}
            if "freepublish/batchget" in url:
                return {
                    "item": [
                        {
                            "article_id": "ARTICLE_ID",
                            "update_time": 1781913600,
                            "content": {
                                "news_item": [
                                    {
                                        "title": "公众号测试文章",
                                        "digest": "摘要",
                                        "url": "https://mp.weixin.qq.com/s/test",
                                        "msg_data_id": 123,
                                    }
                                ]
                            },
                        }
                    ]
                }
            if "datacube/getarticle" in url:
                return {
                    "list": [
                        {
                            "title": "公众号测试文章",
                            "int_page_read_count": 88,
                            "share_count": 3,
                            "add_to_fav_count": 5,
                        }
                    ]
                }
            if "comment/list" in url:
                return {
                    "comment": [
                        {
                            "user_comment_id": 1,
                            "nick_name": "读者A",
                            "content": "这个问题能不能展开讲？",
                            "create_time": 1781914600,
                            "like_num": 2,
                        }
                    ]
                }
            return {}

        with tempfile.TemporaryDirectory() as tmp, patch.object(wechat_api_client, "request_json", side_effect=fake_request_json):
            config_path = Path(tmp) / "wechat_api.json"
            config_path.write_text(
                '{"appid":"YOUR_TEST_APPID","appsecret":"YOUR_WECHAT_OFFICIAL_ACCOUNT_APPSECRET"}',
                encoding="utf-8",
            )
            result = collect_wechat_api(config_path, Path(tmp) / "token.json", "2026-06-20", comments_limit=50)

        self.assertTrue(result["available"])
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["title"], "公众号测试文章")
        self.assertEqual(item["reads"], 88)
        self.assertEqual(item["shares"], 3)
        self.assertEqual(item["collects"], 5)
        self.assertEqual(item["comment_collection_status"], "ok")
        self.assertEqual(item["comments_detail"][0]["is_self"], False)


if __name__ == "__main__":
    unittest.main()
