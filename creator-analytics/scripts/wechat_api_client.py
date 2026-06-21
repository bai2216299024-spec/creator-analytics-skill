#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official WeChat Official Account API collector.

The browser collector remains useful as a fallback, but mp.weixin.qq.com is
not stable enough for unattended daily collection. This module uses official
API endpoints when the user provides private credentials in config/wechat_api.json.
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
FREEPUBLISH_BATCHGET_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/batchget"
ARTICLE_SUMMARY_URL = "https://api.weixin.qq.com/datacube/getarticlesummary"
ARTICLE_TOTAL_URL = "https://api.weixin.qq.com/datacube/getarticletotal"
COMMENT_LIST_URL = "https://api.weixin.qq.com/cgi-bin/comment/list"


class WeChatApiError(RuntimeError):
    """Raised when official WeChat API collection cannot continue."""


def load_api_config(config_path: Path) -> dict[str, Any] | None:
    if not config_path.exists():
        return None
    data = json.loads(config_path.read_text(encoding="utf-8"))
    appid = (data.get("appid") or "").strip()
    appsecret = (data.get("appsecret") or "").strip()
    if not appid or not appsecret:
        raise WeChatApiError("wechat_api.json 缺少 appid 或 appsecret")
    return data


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise WeChatApiError(f"微信公众号 API 请求失败: {exc}") from exc
    data = json.loads(text)
    errcode = data.get("errcode")
    if errcode not in (None, 0):
        errmsg = data.get("errmsg") or "unknown"
        raise WeChatApiError(f"微信公众号 API 返回错误 {errcode}: {errmsg}")
    return data


def get_access_token(config: dict[str, Any], token_cache_path: Path) -> str:
    now = int(time.time())
    if token_cache_path.exists():
        try:
            cached = json.loads(token_cache_path.read_text(encoding="utf-8"))
            if cached.get("access_token") and int(cached.get("expires_at") or 0) > now + 120:
                return cached["access_token"]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    query = urllib.parse.urlencode(
        {
            "grant_type": "client_credential",
            "appid": config["appid"],
            "secret": config["appsecret"],
        }
    )
    data = request_json(f"{TOKEN_URL}?{query}")
    token = data.get("access_token")
    if not token:
        raise WeChatApiError("微信公众号 API 未返回 access_token")
    token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    token_cache_path.write_text(
        json.dumps(
            {
                "access_token": token,
                "expires_at": now + int(data.get("expires_in") or 7200),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return token


def api_url(base_url: str, token: str) -> str:
    return f"{base_url}?access_token={urllib.parse.quote(token)}"


def ts_to_local_date(value: Any) -> str:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def date_from_ts(value: Any) -> str:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.datetime.fromtimestamp(ts).date().isoformat()


def get_published_articles(token: str, target_date: str, max_pages: int = 5) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    offset = 0
    count = 20
    for _ in range(max_pages):
        payload = {"offset": offset, "count": count, "no_content": 0}
        data = request_json(api_url(FREEPUBLISH_BATCHGET_URL, token), payload)
        for item in data.get("item") or []:
            publish_time = item.get("update_time") or item.get("publish_time") or item.get("create_time")
            publish_date = date_from_ts(publish_time)
            content = item.get("content") or {}
            news_items = content.get("news_item") or item.get("news_item") or []
            for index, news in enumerate(news_items):
                if publish_date and publish_date != target_date:
                    continue
                articles.append(
                    {
                        "article_id": item.get("article_id"),
                        "msg_data_id": item.get("msg_data_id") or news.get("msg_data_id"),
                        "index": index,
                        "publish_date": ts_to_local_date(publish_time) or target_date,
                        "title": news.get("title") or item.get("title") or "",
                        "content": news.get("digest") or news.get("content") or "",
                        "content_type": "文章",
                        "source_url": news.get("url") or news.get("content_source_url"),
                        "detail_url": news.get("url") or news.get("content_source_url"),
                    }
                )
        if len(data.get("item") or []) < count:
            break
        offset += count
    return articles


def get_article_summaries(token: str, target_date: str) -> dict[str, dict[str, Any]]:
    payload = {"begin_date": target_date, "end_date": target_date}
    merged: dict[str, dict[str, Any]] = {}
    for url in (ARTICLE_SUMMARY_URL, ARTICLE_TOTAL_URL):
        try:
            data = request_json(api_url(url, token), payload)
        except WeChatApiError as exc:
            merged.setdefault("__errors__", {"errors": []})["errors"].append(str(exc))
            continue
        for row in data.get("list") or []:
            title = row.get("title") or row.get("msgid") or ""
            if not title:
                continue
            metrics = merged.setdefault(title, {})
            metrics.update(row)
    return merged


def number_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_metrics(item: dict[str, Any], summary_by_title: dict[str, dict[str, Any]]) -> dict[str, Any]:
    title = item.get("title") or ""
    metrics = summary_by_title.get(title) or {}
    item["reads"] = number_or_none(metrics.get("int_page_read_count") or metrics.get("ori_page_read_count"))
    item["shares"] = number_or_none(metrics.get("share_count"))
    item["collects"] = number_or_none(metrics.get("add_to_fav_count"))
    item["likes"] = number_or_none(metrics.get("like_count"))
    item["comments"] = number_or_none(metrics.get("comment_count"))
    item["wows"] = number_or_none(metrics.get("like_count"))
    if metrics:
        item["api_metrics_raw"] = metrics
    return item


def get_comments(token: str, item: dict[str, Any], limit: int) -> tuple[str, list[dict[str, Any]]]:
    msg_data_id = item.get("msg_data_id")
    if not msg_data_id:
        return "no_msg_data_id", []
    payload = {
        "msg_data_id": int(msg_data_id),
        "index": int(item.get("index") or 0),
        "begin": 0,
        "count": limit,
        "type": 0,
    }
    try:
        data = request_json(api_url(COMMENT_LIST_URL, token), payload)
    except WeChatApiError as exc:
        return f"failed:{exc}", []
    comments = []
    for row in data.get("comment") or []:
        comments.append(
            {
                "comment_id": str(row.get("user_comment_id") or row.get("id") or ""),
                "author_name": row.get("nick_name") or row.get("nickname"),
                "author_role": None,
                "content": row.get("content") or "",
                "publish_time": ts_to_local_date(row.get("create_time")) or None,
                "like_count": number_or_none(row.get("like_num")),
                "reply_to": None,
                "is_self": False,
                "source_area": "wechat_api",
                "collection_status": "ok",
                "confidence": "high",
            }
        )
    return ("ok" if comments else "empty"), comments


def collect_wechat_api(
    config_path: Path,
    token_cache_path: Path,
    target_date: str,
    comments_limit: int = 50,
    skip_comments: bool = False,
) -> dict[str, Any]:
    config = load_api_config(config_path)
    if not config:
        return {
            "available": False,
            "error": "api_not_configured",
            "items": [],
        }
    token = get_access_token(config, token_cache_path)
    items = get_published_articles(token, target_date)
    summary_by_title = get_article_summaries(token, target_date)
    for item in items:
        merge_metrics(item, summary_by_title)
        if skip_comments:
            item["comment_collection_status"] = "skipped"
            item["comments_detail"] = []
        else:
            status, comments = get_comments(token, item, comments_limit)
            item["comment_collection_status"] = status
            item["comments_detail"] = comments
    return {
        "available": True,
        "error": None,
        "items": items,
        "api_metric_errors": summary_by_title.get("__errors__", {}).get("errors", []),
    }
