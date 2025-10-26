from __future__ import annotations
import os
from typing import Iterable, List, Dict, Optional
import re

import httpx


# シンプルなトピック -> ハッシュタグ候補
TOPIC_TO_HASHTAGS = {
    # 学校・学習
    "study": ["勉強", "学習", "受験"],
    "english": ["英語", "英検"],
    # 生活
    "health": ["健康", "睡眠"],
    "mental": ["メンタル", "ストレス", "不安"],
    "friends": ["友達"],
    "club": ["部活"],
    # 子どもが関心を持ちやすいテーマ
    "space": ["宇宙", "星", "月"],
    "dinosaurs": ["恐竜"],
    "animals": ["動物", "パンダ", "犬", "猫"],
    "science": ["科学", "実験"],
    "robot": ["ロボット", "AI"],
    "games": ["ゲーム", "eスポーツ"],
    "sports": ["スポーツ"],
    "soccer": ["サッカー"],
    "baseball": ["野球"],
    "anime": ["アニメ"],
    "manga": ["マンガ"],
    "nature": ["自然", "植物"],
    "ocean": ["海", "深海"],
    # フォールバック
    "general": ["学校", "学生生活"],
}


def _conf() -> Optional[Dict[str, str]]:
    base = os.getenv("MASTODON_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("MASTODON_ACCESS_TOKEN", "").strip()
    if not base or not token:
        return None
    return {"base": base, "token": token}


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", str(text))


async def _search_statuses(
    client: httpx.AsyncClient, base: str, token: str, query: str, *, limit: int = 5
) -> List[Dict]:
    # v2 search: https://docs.joinmastodon.org/methods/search/#v2
    url = f"{base}/api/v2/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "statuses", "resolve": "true", "limit": str(limit)}
    try:
        r = await client.get(url, headers=headers, params=params, timeout=10.0)
        r.raise_for_status()
        return (r.json() or {}).get("statuses", [])
    except Exception:
        return []


async def get_social_for_topics(
    topics: Iterable[str],
    *,
    limit_per_topic: int = 3,
    audience: Optional[str] = None,  # 今後のフィルタ用
    exclude_urls: Optional[Iterable[str]] = None,
) -> List[Dict[str, str]]:
    """Mastodonの検索API（任意設定）で、トピックに関連する最近の投稿を取得します。
    認証情報が無い場合は空配列でフォールバックします。
    正規化された item(dict) を返却: {type:'social', title, description, url, image_url, source}
    title: 投稿冒頭、description: アカウント情報など
    """
    cfg = _conf()
    if not cfg:
        return []
    excluded = set(u for u in (exclude_urls or []) if u and u != "#")
    collected: List[Dict[str, str]] = []
    seen = set()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for tp in topics:
            tags = TOPIC_TO_HASHTAGS.get(tp, TOPIC_TO_HASHTAGS["general"])
            # ハッシュタグを OR 検索相当で投げる（インスタンス実装に依存）
            q = " ".join([f"#{t}" for t in tags[:3]])
            statuses = await _search_statuses(
                client, cfg["base"], cfg["token"], q, limit=limit_per_topic
            )
            for st in statuses:
                url = st.get("url") or st.get("uri")
                if not url or url in seen or url in excluded:
                    continue
                seen.add(url)
                media = st.get("media_attachments") or []
                img = None
                for m in media:
                    if m.get("type") in ("image", "gifv") and m.get("preview_url"):
                        img = m.get("preview_url")
                        break
                acct = st.get("account") or {}
                acct_disp = acct.get("display_name") or acct.get("acct") or ""
                content = _strip_html(st.get("content"))
                # 子ども向けフィルタ（簡易）
                if (audience == "kids") or os.getenv("KIDS_MODE", "0") in {
                    "1",
                    "true",
                    "True",
                    "yes",
                    "on",
                }:
                    block = [
                        "殺人",
                        "自殺",
                        "自死",
                        "暴行",
                        "傷害",
                        "性的",
                        "性犯罪",
                        "強姦",
                        "レイプ",
                        "売春",
                        "麻薬",
                        "ドラッグ",
                        "覚醒剤",
                        "大麻",
                        "タバコ",
                        "喫煙",
                        "酒",
                        "アルコール",
                        "賭博",
                        "ギャンブル",
                        "テロ",
                        "爆弾",
                        "銃",
                        "拳銃",
                        "ポルノ",
                        "わいせつ",
                    ]
                    joined = (content or "") + "\n" + (acct_disp or "")
                    if any(kw in joined for kw in block):
                        continue
                title = content[:80] + ("…" if len(content) > 80 else "")
                collected.append(
                    {
                        "type": "social",
                        "title": title or "(投稿)",
                        "description": acct_disp,
                        "url": url,
                        "image_url": img,
                        "source": cfg["base"],
                    }
                )
    return collected
