from __future__ import annotations
from typing import List, Dict, Optional
import random

from app.core.config import KIDS_MODE
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# from app.db.memory import get_memories  # personalization disabled
from app.services.news_rss import get_news_for_topics
from app.services.web_search import get_articles_for_topics
from app.services.social_mastodon import get_social_for_topics


# 簡易キーワード → カテゴリのマップ（日本語の素朴な一致）
KEYWORD_TO_TOPIC = {
    # 学び/試験
    "勉強": "study",
    "試験": "study",
    "テスト": "study",
    "定期テスト": "study",
    "受験": "study",
    "英語": "english",
    # 健康/メンタル
    "健康": "health",
    "体調": "health",
    "睡眠": "health",
    "メンタル": "mental",
    "不安": "mental",
    "ストレス": "mental",
    # 人間関係/部活
    "友達": "friends",
    "友人": "friends",
    "いじめ": "friends",
    "部活": "club",
    "恋愛": "friends",
    # 子ども向けの関心ワード（多彩さ重視）
    "宇宙": "space",
    "月": "space",
    "星": "space",
    "恐竜": "dinosaurs",
    "動物": "animals",
    "パンダ": "animals",
    "犬": "animals",
    "猫": "animals",
    "生き物": "animals",
    "昆虫": "animals",
    "科学": "science",
    "実験": "science",
    "発見": "science",
    "ロボット": "robot",
    "AI": "robot",
    "ゲーム": "games",
    "eスポーツ": "games",
    "スポーツ": "sports",
    "サッカー": "soccer",
    "野球": "baseball",
    "オリンピック": "sports",
    "アニメ": "anime",
    "マンガ": "manga",
    "キャラクター": "anime",
    "自然": "nature",
    "植物": "nature",
    "海": "ocean",
    "深海": "ocean",
}


def _normalize_url(raw: Optional[str]) -> str:
    """URLを重複排除しやすい形に正規化する。
    - スキームはそのまま（http/https差異は残す）だが、ホストは小文字化
    - クエリはトラッキング系を除去（utm_*, fbclid, gclid など）
    - フラグメントは削除
    - 末尾の無意味なスラッシュは統一（ただしルートは残す）
    """
    if not raw:
        return ""
    try:
        u = urlparse(raw)
        host = (u.netloc or "").lower()
        # クエリフィルタ
        q = []
        for k, v in parse_qsl(u.query, keep_blank_values=True):
            kl = k.lower()
            if kl.startswith("utm_"):
                continue
            if kl in {
                "fbclid",
                "gclid",
                "gclsrc",
                "ref",
                "ref_src",
                "ref_url",
                "feature",
                "si",
                "spm",
                "_hsmi",
                "_hsenc",
            }:
                continue
            q.append((k, v))
        query = urlencode(q, doseq=True)
        path = u.path or "/"
        # 末尾スラッシュ統一（ルートはそのまま）
        if path != "/":
            path = path.rstrip("/")
            if not path:
                path = "/"
        normalized = urlunparse((u.scheme or "https", host, path, "", query, ""))
        return normalized
    except Exception:
        return raw.strip()


def _curated_catalog() -> Dict[str, List[Dict[str, str]]]:
    """ローカル固定のレコメンドカタログ。
    実運用では外部API（ニュース/RSS/学内イベント）に置き換え可能。
    type: news | event | tip
    """
    return {
        "study": [
            {
                "type": "tip",
                "title": "勉強のコツ: 25分集中→5分休憩",
                "description": "ポモドーロ・テクニックで集中力を維持しよう",
                "url": "#",
            },
            {
                "type": "event",
                "title": "期末試験対策 学内勉強会",
                "description": "学習支援室で毎週開催中。基礎〜応用まで質問歓迎",
                "url": "#",
            },
        ],
        "english": [
            {
                "type": "news",
                "title": "TOEIC申込〆切チェック",
                "description": "次回公開テストの申込期限を確認して計画的に準備を",
                "url": "https://www.toeic.or.jp/",
            },
            {
                "type": "tip",
                "title": "英語学習: シャドーイング入門",
                "description": "短い音声を真似する練習で発音とリスニングを底上げ",
                "url": "#",
            },
        ],
        "career": [
            {
                "type": "event",
                "title": "学内 合同企業説明会",
                "description": "地元企業も多数参加。志望業界の研究に役立ちます",
                "url": "#",
            },
            {
                "type": "tip",
                "title": "履歴書の書き方テンプレ",
                "description": "基本構成とNG例・自己PRのコツを確認しよう",
                "url": "#",
            },
            {
                "type": "news",
                "title": "インターン求人まとめ",
                "description": "短期・長期インターンの最新募集をチェック",
                "url": "#",
            },
        ],
        "money": [
            {
                "type": "news",
                "title": "奨学金の募集要項更新",
                "description": "給付/貸与の条件や締切を確認して申請準備を",
                "url": "https://www.jasso.go.jp/",
            },
            {
                "type": "tip",
                "title": "初めての家計管理",
                "description": "固定費と変動費を分けるだけで見通しが良くなる",
                "url": "#",
            },
        ],
        "health": [
            {
                "type": "tip",
                "title": "睡眠リズムを整える",
                "description": "起床時間を固定すると体内時計が安定します",
                "url": "#",
            },
            {
                "type": "event",
                "title": "保健室だより（今月号）",
                "description": "季節の不調対策と相談窓口の案内",
                "url": "#",
            },
        ],
        "mental": [
            {
                "type": "tip",
                "title": "不安を和らげる呼吸法",
                "description": "4-7-8呼吸でリラックス反応を引き出す",
                "url": "#",
            },
            {
                "type": "event",
                "title": "メンタル健康相談WEEK",
                "description": "養護教諭/カウンセラーの個別相談（予約制）",
                "url": "#",
            },
        ],
        "friends": [
            {
                "type": "tip",
                "title": "対話の『アイメッセージ』",
                "description": "相手を責めずに気持ちを伝える表現を練習",
                "url": "#",
            },
        ],
        "club": [
            {
                "type": "event",
                "title": "部活動交流デイ",
                "description": "他クラブと合同での交流練習を企画中",
                "url": "#",
            },
        ],
        "general": [],
    }


def _all_topics() -> List[str]:
    """利用可能なトピック一覧（general含む）"""
    from_topics = set(KEYWORD_TO_TOPIC.values())
    from_catalog = set(_curated_catalog().keys())
    all_set = from_topics.union(from_catalog)
    return sorted(all_set)


def _pick_diverse_topics(k: int = 4) -> List[str]:
    """ユーザー嗜好を使わず、多彩なトピックからランダムに選ぶ。
    general は補完用に回し、まずは general 以外から選択。
    """
    all_tps = [t for t in _all_topics() if t != "general"]
    random.shuffle(all_tps)
    sel = all_tps[:k]
    return sel or ["general"]


def _infer_topics_from_texts(texts: List[str]) -> List[str]:
    counts: Dict[str, int] = {}
    for t in texts or []:
        for kw, topic in KEYWORD_TO_TOPIC.items():
            if kw in t:
                counts[topic] = counts.get(topic, 0) + 1
    # スコア順に上位3カテゴリ
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [k for k, _ in ranked[:3]] or ["general"]


async def get_recommendations_async(
    user_id: Optional[str],
    limit: int = 6,
    *,
    force_refresh: bool = False,
    shuffle: bool = False,
    audience: Optional[str] = None,
    exclude_urls: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """会話の要約（user_memories）から関心カテゴリを推定し、
    ローカルカタログからニュース/イベント/豆知識を返す。
    未ログインやメモなしの場合は general を返す。
    """
    # 固定カタログは使用しない（疑似コンテンツ非表示）

    # パーソナライズを無効化し、多彩なカテゴリから選択
    topic_count = 4 if limit >= 8 else (3 if limit >= 6 else 2)
    topics: List[str] = _pick_diverse_topics(k=topic_count)

    # まずはRSSニュースを取得
    news_items: List[Dict[str, str]] = []
    try:
        # audience が未指定で KIDS_MODE が有効なら kids を既定に
        effective_audience = audience or ("kids" if KIDS_MODE else None)
        news_items = await get_news_for_topics(
            topics,
            limit_per_topic=3,
            ttl_minutes=30,
            force_refresh=force_refresh,
            shuffle=shuffle,
            audience=effective_audience,
            exclude_urls=exclude_urls,
        )
    except Exception:
        news_items = []

    # 一般Web記事（Bing Web Search; 任意設定）
    article_items: List[Dict[str, str]] = []
    try:
        article_items = await get_articles_for_topics(
            topics, limit_per_topic=2, audience=audience, exclude_urls=exclude_urls
        )
    except Exception:
        article_items = []

    # SNS（Mastodon; 任意設定）
    social_items: List[Dict[str, str]] = []
    try:
        # ニュースと同程度を目指して/トピックあたりの取得数を増やす
        social_items = await get_social_for_topics(
            topics, limit_per_topic=3, audience=audience, exclude_urls=exclude_urls
        )
    except Exception:
        social_items = []

    # URLベースで重複排除（無い場合は type+title を小文字化して使用）
    def key_of(it: Dict[str, str]):
        u = _normalize_url(it.get("url"))
        if u:
            return ("url", u)
        t = (it.get("type") or "").strip().lower()
        title = (it.get("title") or "").strip().lower()
        return (t, title)

    seen = set()
    mixed: List[Dict[str, str]] = []

    # ニュース・SNS・記事をラウンドロビンで均等に採用
    sources = [list(news_items), list(social_items), list(article_items)]
    idxs = [0, 0, 0]
    total_sources = len(sources)
    cursor = 0
    while len(mixed) < limit and any(
        idxs[i] < len(sources[i]) for i in range(total_sources)
    ):
        for i in range(total_sources):
            j = (cursor + i) % total_sources
            if idxs[j] >= len(sources[j]):
                continue
            it = sources[j][idxs[j]]
            idxs[j] += 1
            k = key_of(it)
            if k in seen:
                continue
            seen.add(k)
            mixed.append(it)
            if len(mixed) >= limit:
                break
        cursor = (cursor + 1) % total_sources
    # exclude は現状、外部ソース側の取得で適用済み（ニュースRSS側）
    # 疑似コンテンツ（固定のイベント/豆知識）は表示しない
    return mixed[:limit]


def get_recommendations(
    user_id: Optional[str],
    limit: int = 6,
    *,
    audience: Optional[str] = None,
    exclude_urls: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """同期APIから利用するための薄いラッパー。
    ページレンダリングでは同期関数しか使えない箇所があるため、ここでイベントループを扱う。
    FastAPI の同期エンドポイントから呼ばれる想定。
    """
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            # ランニング中（例: Uvicorn のメインループ上）では新規に実行
            return loop.run_until_complete(
                get_recommendations_async(
                    user_id, limit, audience=audience, exclude_urls=exclude_urls
                )
            )  # type: ignore
        else:
            return loop.run_until_complete(
                get_recommendations_async(
                    user_id, limit, audience=audience, exclude_urls=exclude_urls
                )
            )  # type: ignore
    except RuntimeError:
        # イベントループ未作成時
        import asyncio

    return asyncio.run(
        get_recommendations_async(
            user_id, limit, audience=audience, exclude_urls=exclude_urls
        )
    )
