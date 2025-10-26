from __future__ import annotations
from typing import List, Dict, Optional

from app.core.config import KIDS_MODE

from app.db.memory import get_memories
from app.services.news_rss import get_news_for_topics


# 簡易キーワード → カテゴリのマップ（日本語の素朴な一致）
KEYWORD_TO_TOPIC = {
    # 学び/試験
    "勉強": "study",
    "試験": "study",
    "テスト": "study",
    "定期テスト": "study",
    "受験": "study",
    "英語": "english",
    "TOEIC": "english",
    "英検": "english",
    "留学": "study",
    # 進路/就活
    "就活": "career",
    "就職": "career",
    "インターン": "career",
    "インターンシップ": "career",
    "履歴書": "career",
    # 生活/お金
    "奨学金": "money",
    "バイト": "money",
    "アルバイト": "money",
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
}


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
    catalog = _curated_catalog()

    topics: List[str]
    if user_id:
        memos = get_memories(user_id, limit=10)
        topics = _infer_topics_from_texts(memos)
    else:
        topics = ["general"]

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

    # 次に固定カタログ（tips/events）で補完
    seen = set((it.get("type"), it.get("title")) for it in news_items)
    mixed: List[Dict[str, str]] = list(news_items)
    ex_set = set(u for u in (exclude_urls or []) if u and u != "#")

    for tp in topics + (["general"] if "general" not in topics else []):
        for it in catalog.get(tp, []):
            key = (it.get("type"), it.get("title"))
            if key in seen:
                continue
            url = it.get("url")
            if url and url != "#" and url in ex_set:
                continue
            seen.add(key)
            mixed.append(it)
            if len(mixed) >= limit:
                return mixed[:limit]
    # general で埋める
    for it in catalog.get("general", []):
        key = (it.get("type"), it.get("title"))
        if key in seen:
            continue
        url = it.get("url")
        if url and url != "#" and url in ex_set:
            continue
        seen.add(key)
        mixed.append(it)
        if len(mixed) >= limit:
            break
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
