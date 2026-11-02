def test_blank_message_is_rejected(client):
    assert client.post("/api/drafts", json={"buyer_message": ""}).status_code == 422
    assert client.post("/api/drafts", json={"buyer_message": "   "}).status_code == 422


def test_template_draft_is_stable_without_api_key(client):
    payload = {"buyer_message": "代码复现还接吗", "product_id": "demo-repro-001"}
    first = client.post("/api/drafts", json=payload)
    second = client.post("/api/drafts", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["draft_reply"]
    assert first.json()["draft_reply"] == second.json()["draft_reply"]
    assert isinstance(first.json()["needs_human_review"], bool)
    assert first.json()["session_id"] != second.json()["session_id"]
