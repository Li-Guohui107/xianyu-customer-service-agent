"""咨询草稿的请求和响应。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ConsultationRequest(BaseModel):
    buyer_message: str = Field(min_length=1, max_length=2000)
    product_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("buyer_message")
    @classmethod
    def buyer_message_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("买家消息不能为空")
        return stripped

    @field_validator("product_id", "session_id", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ConsultationResponse(BaseModel):
    draft_reply: str
    risk_level: Literal["low", "high"]
    risk_reasons: list[str]
    needs_human_review: bool
    session_id: str
    product_found: bool
    intent: str = ""


class ProductSummary(BaseModel):
    product_id: str
    title: str
    price: str = ""
    condition: str = ""
    shipping: str = ""
    ship_time: str = ""
    bargain: str = ""
    floor_price: str = ""
    defects: str = ""
    stock: str = ""
    location: str = ""


class SessionMessage(BaseModel):
    role: Literal["buyer", "assistant"]
    content: str
    risk_level: Literal["low", "high"] | None = None


class SessionResponse(BaseModel):
    session_id: str
    messages: list[SessionMessage]


class ImportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("粘贴内容不能为空")
        return stripped


class ImportResponse(BaseModel):
    buyer_message: str
    source: Literal["manual_paste"]


class XianyuStatus(BaseModel):
    mode: Literal["manual_paste"]
    browser_enabled: bool
    sends_messages: bool
