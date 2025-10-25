from __future__ import annotations
import os
import time
from typing import List, Dict, Iterable, Optional
from urllib.parse import urlparse, urljoin
import re
import random

import httpx
import feedparser

from app.db.sqlite import execute, query_all, now_iso

# NHK以外のデフォルトRSS（環境変数が未設定の場合のフォールバック）
# 利用規約に従って見出し・概要・リンクを表示する前提。必要に応じて差し替え可能。
DEFAULT_FEEDS: List[str] = [
    "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",  # ITmedia ニュース速報
    "https://japan.cnet.com/rss/index.rdf",  # CNET Japan 全記事
]


# 除外ドメイン（デフォルトでNHK系を除外）。カンマ区切りで上書き可: EXCLUDE_NEWS_DOMAINS
def _excluded_domains() -> List[str]:
    raw = os.getenv("EXCLUDE_NEWS_DOMAINS", "nhk.or.jp,nhk.jp,www3.nhk.or.jp").strip()
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _is_excluded(value: Optional[str]) -> bool:
    if not value:
        return False
    val = value.lower()
    try:
        netloc = urlparse(val).netloc or val
    except Exception:
        netloc = val
    for dom in _excluded_domains():
        if netloc.endswith(dom) or dom in val:
            return True
    return False


# フィードURLは環境変数で指定（NHKは使用しない方針）。
"""
環境変数の指定例（カンマ区切り）:
  NEWS_RSS_FEEDS="https://example.com/rss,https://another.com/feed"
トピック固有に設定したい場合:
  NEWS_RSS_FEEDS_STUDY, NEWS_RSS_FEEDS_CAREER, NEWS_RSS_FEEDS_GENERAL など
（存在しないトピックはスキップされます）
"""


def _parse_feed_env(var_name: str) -> List[str]:
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def _get_topic_feeds(topic: str) -> List[str]:
    topic_key = f"NEWS_RSS_FEEDS_{topic.upper()}"
    topic_feeds = _parse_feed_env(topic_key)
    if topic_feeds:
        return topic_feeds
    # 共通設定
    common = _parse_feed_env("NEWS_RSS_FEEDS")
    if common:
        return common
    # 環境変数が何も無い場合のフォールバック（NHK以外）
    return DEFAULT_FEEDS


def _extract_image_from_entry(entry) -> Optional[str]:
    # feedparser は media_thumbnail, media_content, links/enclosures を正規化してくれる
    try:
        thumbs = entry.get("media_thumbnail") or []
        if thumbs:
            url = thumbs[0].get("url")
            if url:
                return url
    except Exception:
        pass
    try:
        media = entry.get("media_content") or []
        for m in media:
            if str(m.get("type", "")).startswith("image") and m.get("url"):
                return m["url"]
    except Exception:
        pass
    try:
        enclosures = entry.get("enclosures") or []
        for e in enclosures:
            if str(e.get("type", "")).startswith("image") and e.get("href"):
                return e["href"]
    except Exception:
        pass
    # links に image が付くサイトもある
    try:
        for link_obj in entry.get("links", []) or []:
            if str(link_obj.get("type", "")).startswith("image") and link_obj.get(
                "href"
            ):
                return link_obj["href"]
    except Exception:
        pass
    # content:encoded や description 内の <img> から抽出（HTML埋め込みのケース）
    try:
        base_url = entry.get("link") or ""
        # content (優先)
        contents = entry.get("content") or []
        for c in contents:
            html = c.get("value") or ""
            m = re.search(
                r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE
            )
            if m:
                return urljoin(base_url, m.group(1))
        # summary/description
        for key in ("summary", "description"):
            html = entry.get(key) or ""
            m = re.search(
                r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE
            )
            if m:
                return urljoin(base_url, m.group(1))
    except Exception:
        pass
    return None


def _normalize_entries(feed_url: str, entries) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for e in entries:
        link = e.get("link") or ""
        if not link:
            continue
        title = e.get("title") or "(無題)"
        desc = e.get("summary") or e.get("description") or ""
        img = _extract_image_from_entry(e)
        published = None
        # feedparser は published_parsed を time.struct_time でくれることがある
        try:
            if e.get("published_parsed"):
                published = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", e["published_parsed"]
                )  # UTC近似
            elif e.get("updated_parsed"):
                published = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", e["updated_parsed"]
                )  # UTC近似
        except Exception:
            published = None

        items.append(
            {
                "title": title,
                "description": desc,
                "url": link,
                "image_url": img,
                "source": feed_url,
                "published_at": published,
            }
        )
    return items


async def _fetch_one(client: httpx.AsyncClient, url: str) -> List[Dict[str, str]]:
    try:
        r = await client.get(url, timeout=10.0)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
        return _normalize_entries(url, parsed.entries or [])
    except Exception:
        return []


async def _fetch_og_image(client: httpx.AsyncClient, page_url: str) -> Optional[str]:
    """記事ページから og:image / twitter:image などのサムネイルを抽出して返す。"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (student-support-ai)"}
        r = await client.get(page_url, timeout=10.0, headers=headers)
        r.raise_for_status()
        html = r.text
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+property=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, flags=re.IGNORECASE)
            if m:
                img = m.group(1).strip()
                if img:
                    return urljoin(page_url, img)
    except Exception:
        return None
    return None


async def refresh_feeds_for_topic(topic: str) -> List[Dict[str, str]]:
    feeds = _get_topic_feeds(topic)
    if not feeds:
        return []
    items: List[Dict[str, str]] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in feeds:
            entries = await _fetch_one(client, url)
            items.extend(entries)
        # 画像がない記事は OGP から補完
        for it in items:
            if not it.get("image_url") and it.get("url"):
                try:
                    og = await _fetch_og_image(client, it["url"])
                except Exception:
                    og = None
                if og:
                    it["image_url"] = og

    # DBへ保存（URLでユニーク化）
    now = now_iso()
    # ついでに除外ドメインの古いキャッシュを掃除（このトピックに限定）
    try:
        for dom in _excluded_domains():
            execute(
                "DELETE FROM news_cache WHERE topic=? AND (url LIKE ? OR source LIKE ?)",
                (topic, f"%{dom}%", f"%{dom}%"),
            )
    except Exception:
        pass

    for it in items:
        # 除外ドメインはスキップ
        if _is_excluded(it.get("url")) or _is_excluded(it.get("source")):
            continue
        try:
            execute(
                """
                INSERT OR IGNORE INTO news_cache (topic, title, description, url, image_url, source, published_at, fetched_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    topic,
                    it.get("title") or "(無題)",
                    it.get("description"),
                    it.get("url"),
                    it.get("image_url"),
                    it.get("source"),
                    it.get("published_at"),
                    now,
                ),
            )
        except Exception:
            # 既存行がある場合は最低限 fetched_at を更新
            try:
                execute(
                    "UPDATE news_cache SET fetched_at=? WHERE url=?",
                    (now, it.get("url")),
                )
            except Exception:
                pass
    return items


def get_cached_news(
    topic: str, limit: int = 10, ttl_minutes: int = 30
) -> List[Dict[str, str]]:
    # TTL内に取得された記事を優先
    rows = query_all(
        """
        SELECT title, description, url, image_url, source, published_at, fetched_at
        FROM news_cache
        WHERE topic=?
        ORDER BY COALESCE(published_at, fetched_at) DESC
        LIMIT ?
        """,
        (topic, limit),
    )
    items = []
    for title, desc, url, img, src, pub, fet in rows:
        # 除外ドメインは結果からも除外
        if _is_excluded(url) or _is_excluded(src):
            continue
        items.append(
            {
                "title": title,
                "description": desc,
                "url": url,
                "image_url": img,
                "source": src,
                "published_at": pub,
                "fetched_at": fet,
            }
        )
    return items


async def get_news_for_topics(
    topics: Iterable[str],
    limit_per_topic: int = 3,
    ttl_minutes: int = 30,
    force_refresh: bool = False,
    shuffle: bool = False,
) -> List[Dict[str, str]]:
    # まずキャッシュを読み、それでも少ない場合のみリフレッシュ
    collected: List[Dict[str, str]] = []
    seen_urls = set()
    valid_topics = [t for t in topics if _get_topic_feeds(t)]
    # 強制リフレッシュ指定時は先に最新化
    if force_refresh:
        for tp in valid_topics:
            await refresh_feeds_for_topic(tp)

    for tp in valid_topics:
        cached = get_cached_news(tp, limit=limit_per_topic, ttl_minutes=ttl_minutes)
        for c in cached:
            if c["url"] in seen_urls:
                continue
            seen_urls.add(c["url"])
            collected.append(c)

    # 十分な件数がなければ、最新を取得して再読込
    if len(collected) < limit_per_topic * len(valid_topics):
        for tp in valid_topics:
            await refresh_feeds_for_topic(tp)
        collected = []
        seen_urls = set()
        for tp in valid_topics:
            cached = get_cached_news(tp, limit=limit_per_topic, ttl_minutes=ttl_minutes)
            for c in cached:
                if c["url"] in seen_urls:
                    continue
                seen_urls.add(c["url"])
                collected.append(c)

    # 正規化して返却（type=news にして、既存UIと合わせる）
    if shuffle:
        random.shuffle(collected)
    normalized: List[Dict[str, str]] = []
    for it in collected:
        # 念のためここでも除外
        if _is_excluded(it.get("url")) or _is_excluded(it.get("source")):
            continue
        normalized.append(
            {
                "type": "news",
                "title": it.get("title"),
                "description": it.get("description"),
                "url": it.get("url"),
                "image_url": it.get("image_url"),
                "source": it.get("source"),
            }
        )
    return normalized
