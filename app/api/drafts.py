"""草稿接口。"""

from fastapi import APIRouter, HTTPException, Request

from app.llm.deepseek import LLMError
from app.memory.store import SessionNotFoundError
from app.schemas.consultation import ConsultationRequest, ConsultationResponse
from app.services.draft import build_draft

router = APIRouter(prefix="/api", tags=["drafts"])


@router.post("/drafts", response_model=ConsultationResponse)
def create_draft(body: ConsultationRequest, request: Request) -> ConsultationResponse:
    try:
        return build_draft(
            body,
            knowledge=request.app.state.knowledge,
            generator=request.app.state.generator,
            memory=request.app.state.memory,
            wechat_id=request.app.state.wechat_id,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
