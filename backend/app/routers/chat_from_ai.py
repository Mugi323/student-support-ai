from fastapi import APIRouter


router = APIRouter(prefix="/api")


@router.post("/chat_from_ai")
def api_chat_stream():
    return
