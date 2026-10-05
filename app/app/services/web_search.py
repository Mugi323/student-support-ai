from __future__ import annotations
import os
from typing import Iterable, List, Dict, Optional
import re

import httpx


# トピック -> 検索クエリ（日本語中心）
TOPIC_TO_QUERY = {
    "study": "(勉強 OR 学習 OR 受験 OR テスト OR 定期テスト)",
    "english": "(英語 OR TOEIC OR 英検 OR 留学)",
    # 子ども向けでは大人向け話題に寄りにくくするため、career/moneyは除外
    "health": "(健康 OR 体調 OR 睡眠)",
    "mental": "(メンタル OR 不安 OR ストレス)",
    "friends": "(友達 OR 友人 OR いじめ)",
    "club": "(部活 OR クラブ活動)",
    # 子どもが関心を持ちやすいテーマ
    "space": "(宇宙 OR 月 OR 星 OR 宇宙飛行士)",
    "dinosaurs": "(恐竜)",
    "animals": "(動物 OR パンダ OR 犬 OR 猫)",
    "science": "(科学 OR 実験 OR 発見)",
    "robot": "(ロボット OR AI)",
    "games": "(ゲーム OR eスポーツ)",
    "sports": "(スポーツ)",
    "soccer": "(サッカー)",
    "baseball": "(野球)",
    "anime": "(アニメ)",
    "manga": "(マンガ)",
    "nature": "(自然 OR 植物)",
    "ocean": "(海 OR 深海)",
    "general": "(学生 生活 お役立ち コツ)",
}


def _bing_config() -> Optional[Dict[str, str]]:
    key = os.getenv("BING_SEARCH_API_KEY", "").strip()
    endpoint = os.getenv(
        "BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com"
    ).strip()
    if not key:
        return None
    return {"key": key, "endpoint": endpoint.rstrip("/")}


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    # 簡易にタグを削除
    return re.sub(r"<[^>]+>", "", str(text))


async def _bing_web_search(
    client: httpx.AsyncClient, query: str, *, count: int = 5, mkt: str = "ja-JP"
) -> List[Dict[str, str]]:
    cfg = _bing_config()
    if not cfg:
        return []
    url = f"{cfg['endpoint']}/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": cfg["key"]}
    params = {"q": query, "mkt": mkt, "count": count, "responseFilter": "Webpages"}
    try:
        r = await client.get(url, headers=headers, params=params, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        items = []
        for w in (data.get("webPages", {}) or {}).get("value", []):
            items.append(
                {
                    "type": "article",
                    "title": w.get("name"),
                    "description": _strip_html(w.get("snippet")),
                    "url": w.get("url"),
                    # サムネは search API では薄いので省略（OGP補完は news_rss の仕組みを流用するなら別途）
                    "image_url": None,
                    "source": w.get("displayUrl") or "bing",
                }
            )
        return items
    except Exception:
        return []


async def get_articles_for_topics(
    topics: Iterable[str],
    *,
    limit_per_topic: int = 3,
    audience: Optional[str] = None,  # ここでは未使用。将来フィルタに利用可能。
    exclude_urls: Optional[Iterable[str]] = None,
) -> List[Dict[str, str]]:
    """Bing Web Search (任意設定) を用いて、各トピックに沿った一般Web記事を取得。
    APIキー未設定時は空配列を返す（フォールバック）。
    正規化された item(dict) を返却: {type:'article', title, description, url, image_url, source}
    """
    if not _bing_config():
        return []

    excluded = set(u for u in (exclude_urls or []) if u and u != "#")
    collected: List[Dict[str, str]] = []
    seen = set()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for tp in topics:
            q = TOPIC_TO_QUERY.get(tp, TOPIC_TO_QUERY["general"]) + " site:jp"
            results = await _bing_web_search(client, q, count=limit_per_topic)
            for it in results:
                url = it.get("url")
                if not url or url in seen or url in excluded:
                    continue
                seen.add(url)
                # 子ども向けフィルタ（簡易）
                if (audience == "kids") or os.getenv("KIDS_MODE", "0") in {
                    "1",
                    "true",
                    "True",
                    "yes",
                    "on",
                }:
                    text = (
                        (it.get("title") or "") + "\n" + (it.get("description") or "")
                    )
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
                    if any(kw in text for kw in block):
                        continue
                collected.append(it)
    return collected
