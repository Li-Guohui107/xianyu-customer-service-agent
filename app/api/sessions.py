"""会话历史。"""

from fastapi import APIRouter, HTTPException, Request

from app.memory.store import SessionNotFoundError
from app.schemas.consultation import SessionMessage, SessionResponse

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, request: Request) -> SessionResponse:
    try:
        messages = request.app.state.memory.list_messages(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return SessionResponse(
        session_id=session_id,
        messages=[SessionMessage.model_validate(item) for item in messages],
    )
