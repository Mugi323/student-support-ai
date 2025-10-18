# app/routers/chat_from_ai.py
from fastapi import APIRouter
import asyncio

router = APIRouter(prefix="/api")

@router.post("/chat_from_ai")
async def api_chat_stream():
    await asyncio.sleep(10)  # 10秒待機（非同期）
    return {"message": "お元気ですか？"}