from app.knowledge.store import ProductStore


def test_lookup_by_id_and_keyword():
    store = ProductStore()
    service = store.get("demo-repro-001")
    assert service is not None
    assert service.price == "299元"
    assert "可运行代码" in service.condition
    assert store.get("missing-item") is None
    assert store.search("请问机器学习还接吗").product_id == "demo-ml-002"
    assert store.search("你好") is None
    assert store.resolve("missing-item", "代码复现还接吗") is None
    assert store.resolve(None, "这个代码复现多少钱").title == "演示用论文代码复现"


def test_known_product_reply_uses_only_catalog_facts(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "这个还接吗", "product_id": "demo-repro-001"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["product_found"] is True
    assert "可运行代码" in body["draft_reply"]
    assert "299元" not in body["draft_reply"]
    assert "199元" not in body["draft_reply"]
    assert "399元" not in body["draft_reply"]
    assert "159元" not in body["draft_reply"]


def test_unknown_product_does_not_invent_facts(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "这个服务还接吗", "product_id": "missing-item"},
    )
    body = response.json()
    assert body["product_found"] is False
    assert "没有查到该商品" in body["draft_reply"]
    assert "299元" not in body["draft_reply"]
    assert "199元" not in body["draft_reply"]
    assert "399元" not in body["draft_reply"]
    assert "159元" not in body["draft_reply"]


def test_keyword_match_when_product_id_omitted(client):
    response = client.post("/api/drafts", json={"buyer_message": "请问机器学习还接吗"})
    body = response.json()
    assert body["product_found"] is True
    assert "模型训练脚本" in body["draft_reply"]
    assert "199元" not in body["draft_reply"]
