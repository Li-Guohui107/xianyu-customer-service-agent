from app.services.risk import assess_risk


def test_ordinary_question_is_low_risk():
    result = assess_risk("这个还在吗", "价格：99元", "价格：99元")
    assert result.risk_level == "low"
    assert result.needs_human_review is False
    assert result.risk_reasons == []


def test_refund_offsite_and_abuse_are_high_risk():
    refund = assess_risk("我要退款", "草稿", "")
    offsite = assess_risk("加微信交易", "草稿", "")
    abuse = assess_risk("你这个骗子", "草稿", "")
    assert refund.needs_human_review is True
    assert offsite.risk_reasons == ["涉及站外交易或转账"]
    assert abuse.risk_level == "high"


def test_multiple_risk_signals_are_kept():
    result = assess_risk("我要退款，加微信", "草稿", "")
    assert result.risk_reasons == ["涉及退款或投诉", "涉及站外交易或转账"]


def test_promise_missing_from_knowledge_is_high_risk():
    result = assess_risk("还在吗", "好的，可以包邮，假一赔十", "价格：99元")
    assert result.risk_level == "high"
    assert any("可以包邮" in reason for reason in result.risk_reasons)
    assert any("假一赔十" in reason for reason in result.risk_reasons)


def test_asking_about_shipping_is_not_a_promise():
    result = assess_risk("包邮吗", "不包邮，运费8元", "运费：不包邮，运费8元")
    assert result.risk_level == "low"


def test_promise_present_in_knowledge_is_not_flagged():
    result = assess_risk("可以包邮", "草稿", "卖点：可以包邮")
    assert result.risk_level == "low"


def test_api_marks_refund_for_human_review_and_still_returns_draft(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "我要退款，复现还接吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "high"
    assert body["needs_human_review"] is True
    assert body["draft_reply"]
    assert "可运行代码" in body["draft_reply"]
    assert "299元" not in body["draft_reply"]


def test_api_ordinary_question_does_not_require_review(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "这个还接吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert body["risk_level"] == "low"
    assert body["needs_human_review"] is False
