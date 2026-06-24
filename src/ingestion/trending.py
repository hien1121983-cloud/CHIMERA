"""Cào từ khóa trending. TikTok Creative Center → CafeF RSS → cache MongoDB → static fallback."""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List
import requests
import feedparser
from ..utils import get_logger, retry

log = get_logger("trending")

TIKTOK_CC = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"  # placeholder JSON endpoint
CAFEF_RSS = "https://cafef.vn/trang-chu.rss"
VNBIZ_RSS = "https://vietnambiz.vn/rss/home.rss"

STATIC_FALLBACK = [
    "drama gia tộc", "phản bội tài chính", "kế hoạch trả thù",
    "công ty gia đình", "tỷ phú giả nghèo", "vạch trần",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.google.com/",
    "Accept": "application/json,text/html;q=0.9",
}


def _from_rss(url: str, limit: int = 5) -> List[str]:
    feed = feedparser.parse(url, request_headers=HEADERS)
    return [e.title for e in feed.entries[:limit]]


def fetch_trending(cache_path: str | Path = "data/_trending_cache.json", limit: int = 10) -> List[str]:
    """Trả về danh sách keyword/title trending. Retry tối đa 2 lần, fallback dần."""
    results: List[str] = []

    # 1) CafeF RSS (ổn định)
    try:
        results += retry(lambda: _from_rss(CAFEF_RSS, 6), attempts=2, label="cafef")
    except Exception as e:
        log.warning("cafef RSS fail: %s", e)

    # 2) VietnamBiz
    try:
        results += retry(lambda: _from_rss(VNBIZ_RSS, 4), attempts=2, label="vnbiz")
    except Exception as e:
        log.warning("vnbiz RSS fail: %s", e)

    # 3) Cache nếu rỗng
    if not results:
        try:
            cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            results = cached.get("keywords", [])
        except Exception:
            pass

    # 4) Static fallback
    if not results:
        results = list(STATIC_FALLBACK)

    random.shuffle(results)
    out = results[:limit]

    # Ghi cache
    try:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps({"keywords": out}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    log.info("trending: %d keywords", len(out))
    return out
