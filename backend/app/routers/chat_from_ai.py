# app/routers/chat_from_ai.py
from fastapi import APIRouter
import asyncio
import random

router = APIRouter(prefix="/api")

MESSAGES = [
    "今日はどんな気分ですか？",
    "最近、面白いニュースや出来事ありましたか？",
    "名前は聞いたことあるけど、よく知らないものってありますか？",
    "最近の学習、順調に進んでいますか？",
]

@router.post("/chat_from_ai")
async def api_chat_stream():
    # （デモ用）10秒待ってから返す。不要ならこの行は削除可
    await asyncio.sleep(1)
    return {"message": random.choice(MESSAGES)}
