from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, json, httpx

app = FastAPI(title="ChatGPT Web Service (FastAPI)")

class ChatIn(BaseModel):
    messages: list

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/chat")
async def chat(incoming: ChatIn):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",  # 利用モデルは任意に変更可
                    "messages": incoming.messages,
                },
            )
        # 成功/エラーともに OpenAI の応答本文を返す（必要なら整形）
        return json.loads(r.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upstream error: {e}")
