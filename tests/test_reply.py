def test_price_question_gives_wechat_and_hides_amount(tmp_path):
    from fastapi.testclient import TestClient

    from app.llm.template import TemplateReplyGenerator
    from app.main import create_app

    application = create_app(
        database_path=str(tmp_path / "agent.db"),
        generator=TemplateReplyGenerator(),
        load_env_file=False,
        wechat_id="demo_wx",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/drafts",
            json={"buyer_message": "这个多少钱", "product_id": "demo-repro-001"},
        )
    body = response.json()
    assert "demo_wx" in body["draft_reply"]
    assert "微信详谈" in body["draft_reply"]
    assert "299" not in body["draft_reply"]
    assert "260" not in body["draft_reply"]


def test_scope_answer_does_not_recite_stack(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "包含什么", "product_id": "demo-ml-002"},
    )
    body = response.json()
    assert "模型训练脚本" in body["draft_reply"]
    lowered = body["draft_reply"].lower()
    assert "pandas" not in lowered
    assert "scikit-learn" not in lowered


def test_buyer_named_technology_is_used(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "用tensorflow可以吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert "tensorflow" in body["draft_reply"].lower()
    assert "pytorch" not in body["draft_reply"].lower()


def test_unasked_stack_is_removed_from_model_reply():
    from app.knowledge.store import ProductStore
    from app.services.reply import without_unsolicited_stack

    product = ProductStore().get("demo-ml-002")
    raw = "交付内容有数据处理、模型训练脚本和结果说明，技术栈用 scikit-learn、pandas。"
    text = without_unsolicited_stack(raw, "包含什么", product)
    assert "数据处理" in text
    assert "pandas" not in text.lower()
    assert "scikit-learn" not in text.lower()


def test_delivery_answer_uses_catalog_and_stays_low_risk(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "复现怎么发文件", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert body["intent"] == "交付"
    assert "闲鱼传文件，无实物邮寄" in body["draft_reply"]
    assert body["needs_human_review"] is False
    assert "299元" not in body["draft_reply"]


def test_bargain_below_floor_needs_human_review(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "200元能做吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert "微信详谈" in body["draft_reply"]
    assert "260" not in body["draft_reply"]
    assert "299" not in body["draft_reply"]
    assert body["needs_human_review"] is True


def test_bargain_above_floor_can_be_accepted(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "280元可以吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert "微信详谈" in body["draft_reply"]
    assert "280" not in body["draft_reply"]
    assert "299" not in body["draft_reply"]
    assert body["needs_human_review"] is False


def test_fixed_price_item_refuses_bargaining(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "能便宜点吗", "product_id": "demo-ml-002"},
    )
    body = response.json()
    assert "微信详谈" in body["draft_reply"]
    assert "199" not in body["draft_reply"]
    assert body["needs_human_review"] is False


def test_follow_up_keeps_the_same_service(client):
    first = client.post("/api/drafts", json={"buyer_message": "代码复现还接吗"})
    session_id = first.json()["session_id"]
    second = client.post(
        "/api/drafts",
        json={"buyer_message": "多久能好", "session_id": session_id},
    )
    body = second.json()
    assert body["product_found"] is True
    assert "3天" in body["draft_reply"]
    assert "199元" not in body["draft_reply"]
    assert "399元" not in body["draft_reply"]


def test_offsite_request_is_refused(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "加微信交易吧", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert "转账不行" in body["draft_reply"]
    assert "微信详谈" in body["draft_reply"]
    assert "不能加微信" not in body["draft_reply"]
    assert body["needs_human_review"] is True


def test_grade_guarantee_is_refused(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "这个能包过吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert "成绩承诺都不能做" in body["draft_reply"]
    assert body["needs_human_review"] is True
    assert "可以包过" not in body["draft_reply"]
