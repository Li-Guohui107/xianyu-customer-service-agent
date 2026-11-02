"""闲鱼消息的粘贴导入。不提供发送接口。"""

from fastapi import APIRouter, HTTPException

from app.connectors.xianyu import parse_pasted_chat
from app.schemas.consultation import ImportRequest, ImportResponse, XianyuStatus

router = APIRouter(prefix="/api/xianyu", tags=["xianyu"])


@router.get("/status", response_model=XianyuStatus)
def status() -> XianyuStatus:
    return XianyuStatus(mode="manual_paste", browser_enabled=False, sends_messages=False)


@router.post("/import", response_model=ImportResponse)
def import_chat(body: ImportRequest) -> ImportResponse:
    try:
        buyer_message = parse_pasted_chat(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImportResponse(buyer_message=buyer_message, source="manual_paste")
