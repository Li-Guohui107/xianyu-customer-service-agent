"""把商品知识、生成器、风险规则和会话记忆串成一次草稿。"""

from __future__ import annotations

from app.knowledge.store import NOT_FOUND_TEXT, Product, ProductStore, format_product
from app.llm.base import ReplyGenerator
from app.llm.template import TemplateReplyGenerator
from app.memory.store import SessionNotFoundError, SessionStore
from app.schemas.consultation import ConsultationRequest, ConsultationResponse
from app.services.reply import (
    below_floor_reason,
    compose_reply,
    intent_label,
    history_without_fixed_stack,
    knowledge_without_prices,
    without_quoted_prices,
    without_unsolicited_stack,
)
from app.services.risk import assess_risk


def build_draft(
    request: ConsultationRequest,
    *,
    knowledge: ProductStore,
    generator: ReplyGenerator,
    memory: SessionStore,
    wechat_id: str = "",
) -> ConsultationResponse:
    if request.session_id:
        if not memory.exists(request.session_id):
            raise SessionNotFoundError(request.session_id)
        session_id = request.session_id
    else:
        session_id = memory.create_session()

    history = memory.recent_messages(session_id, limit=6)
    product = _resolve_product(request, knowledge, memory, session_id)
    if product is None:
        knowledge_text = NOT_FOUND_TEXT
        product_text = ""
        product_found = False
    else:
        knowledge_text = format_product(product)
        product_text = knowledge_text
        product_found = True
        memory.set_focus_product(session_id, product.product_id)

    if isinstance(generator, TemplateReplyGenerator):
        reply = compose_reply(request.buyer_message, product, wechat_id)
    else:
        reply = generator.generate(
            request.buyer_message,
            knowledge_without_prices(knowledge_text, wechat_id),
            history_without_fixed_stack(history, product),
        )
    reply = without_quoted_prices(reply, wechat_id)
    reply = without_unsolicited_stack(reply, request.buyer_message, product)
    assessment = assess_risk(request.buyer_message, reply, product_text)
    reasons = list(assessment.risk_reasons)
    floor_reason = below_floor_reason(request.buyer_message, product)
    if floor_reason and floor_reason not in reasons:
        reasons.append(floor_reason)
    risk_level = "high" if reasons else "low"
    memory.add_message(session_id, "buyer", request.buyer_message, None)
    memory.add_message(session_id, "assistant", reply, risk_level)
    return ConsultationResponse(
        draft_reply=reply,
        risk_level=risk_level,
        risk_reasons=reasons,
        needs_human_review=risk_level == "high",
        session_id=session_id,
        product_found=product_found,
        intent=intent_label(request.buyer_message),
    )


def _resolve_product(request, knowledge: ProductStore, memory: SessionStore, session_id: str) -> Product | None:
    """页面指定的商品优先；否则按这句话匹配；同一会话里的后续问题沿用上次商品。"""
    if request.product_id:
        return knowledge.get(request.product_id)
    matched = knowledge.search(request.buyer_message)
    if matched is not None:
        return matched
    remembered = memory.get_focus_product(session_id)
    if remembered:
        return knowledge.get(remembered)
    return None
