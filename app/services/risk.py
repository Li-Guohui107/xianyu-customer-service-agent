"""不访问网络的风险规则。高风险只打标，不拦截草稿。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

REFUND_TERMS = ("退款", "退货", "投诉", "差评", "举报")
OFFSITE_TERMS = ("微信", "威信", "加微", "vx", "v信", "私下", "站外", "转账", "扫码付")
ABUSE_TERMS = ("傻逼", "智障", "骗子", "垃圾卖家")
ACADEMIC_TERMS = ("代写论文", "包过", "保分", "保证及格", "代考", "替我交", "替我提交")
PROMISE_TERMS = ("一定包邮", "可以包邮", "能包邮", "假一赔十", "包过", "保证及格", "保证录用", "代写论文")


@dataclass(frozen=True)
class RiskAssessment:
    risk_level: Literal["low", "high"]
    risk_reasons: list[str]
    needs_human_review: bool


def _seller_text(text: str) -> str:
    """去掉否定说法，避免把拒绝承诺看成答应承诺。"""
    for phrase in (
        "不能代写论文",
        "不代写论文",
        "不能包过",
        "不包过",
        "不保证录用",
        "不保证成绩",
        "不能保证",
        "不包邮",
        "非包邮",
    ):
        text = text.replace(phrase, "")
    return text


def assess_risk(buyer_message: str, draft_reply: str, product_text: str) -> RiskAssessment:
    reasons: list[str] = []
    lowered = buyer_message.lower()

    if any(term in buyer_message for term in REFUND_TERMS):
        reasons.append("涉及退款或投诉")
    if any(term in lowered for term in OFFSITE_TERMS):
        reasons.append("涉及站外交易或转账")
    if any(term in buyer_message for term in ABUSE_TERMS):
        reasons.append("包含辱骂")
    if any(term in buyer_message for term in ACADEMIC_TERMS):
        reasons.append("涉及论文代写、保分或替交")

    draft_view = _seller_text(draft_reply)
    product_view = _seller_text(product_text)
    for phrase in PROMISE_TERMS:
        if phrase in draft_view and phrase not in product_view:
            reasons.append(f"出现知识库未记载的承诺：{phrase}")
    draft_view = draft_view.replace("一定包邮", "").replace("可以包邮", "").replace("能包邮", "")
    if "包邮" in draft_view and "包邮" not in product_view:
        reasons.append("出现知识库未记载的承诺：包邮")

    risk_level: Literal["low", "high"] = "high" if reasons else "low"
    return RiskAssessment(
        risk_level=risk_level,
        risk_reasons=reasons,
        needs_human_review=risk_level == "high",
    )
