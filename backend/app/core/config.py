from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
APP_TITLE = "Student Support (OpenAI Only + Streaming)"
TEMPLATE_DIR = "app/templates"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

# ニュース表示の受け手（オーディエンス）設定
# KIDS_MODE=1 の場合、ニュースは小中学生向けソース・フィルタで提供します。
KIDS_MODE: bool = os.getenv("KIDS_MODE", "0").strip() in {
    "1",
    "true",
    "True",
    "yes",
    "on",
}

# 子ども向けニュースの既定RSS（環境変数で上書き可能）
# 既定: NHK NEWS WEB EASY
KIDS_NEWS_FEEDS = os.getenv(
    "KIDS_NEWS_FEEDS",
    "https://www3.nhk.or.jp/news/easy/news-list.rss",
)

# 子どもが興味を持ちやすいテーマのキーワード（カンマ区切りで上書き可能）
# 例: 宇宙,恐竜,動物,パンダ,犬,猫,科学,実験,発見,ロボット,ゲーム,スポーツ,サッカー,野球,アニメ,マンガ,自然,海
KIDS_INTEREST_KEYWORDS = os.getenv(
    "KIDS_INTEREST_KEYWORDS",
    "宇宙,月,星,火星,宇宙飛行士,恐竜,動物,パンダ,犬,猫,生き物,昆虫,科学,実験,発見,ロボット,AI,ゲーム,eスポーツ,スポーツ,サッカー,野球,世界大会,オリンピック,アニメ,マンガ,キャラクター,自然,植物,海,深海",
)
