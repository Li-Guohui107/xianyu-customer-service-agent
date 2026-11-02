import pytest

from app.connectors.xianyu import ConnectorUnavailable, XianyuReadOnlyConnector, parse_pasted_chat


def test_parse_buyer_lines_and_ignore_agent_lines():
    text = "买家: 这个台灯多少钱\n客服: 稍等\n买家：包邮吗"
    assert parse_pasted_chat(text) == "这个台灯多少钱\n包邮吗"


def test_plain_text_is_used_as_buyer_message():
    assert parse_pasted_chat("台灯多少钱") == "台灯多少钱"


def test_agent_only_text_is_rejected():
    with pytest.raises(ValueError, match="没有识别到买家消息"):
        parse_pasted_chat("客服: 你好")


def test_import_endpoint_extracts_buyer_message(client):
    response = client.post(
        "/api/xianyu/import",
        json={"text": "买家: 这个台灯多少钱\n客服: 稍等"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "buyer_message": "这个台灯多少钱",
        "source": "manual_paste",
    }


def test_import_rejects_agent_only_text(client):
    response = client.post("/api/xianyu/import", json={"text": "客服: 你好"})
    assert response.status_code == 422


def test_browser_connector_never_sends_and_is_unavailable(tmp_path):
    unconfigured = XianyuReadOnlyConnector()
    configured = XianyuReadOnlyConnector(user_data_dir=str(tmp_path))
    assert not hasattr(unconfigured, "send_message")
    with pytest.raises(ConnectorUnavailable):
        unconfigured.read_buyer_messages()
    with pytest.raises(ConnectorUnavailable, match="不会自动发送"):
        configured.read_buyer_messages()


def test_status_and_homepage_do_not_offer_sending(client):
    status = client.get("/api/xianyu/status")
    assert status.json() == {
        "mode": "manual_paste",
        "browser_enabled": False,
        "sends_messages": False,
    }
    page = client.get("/")
    assert page.status_code == 200
    assert "模拟买家说的话" in page.text
    assert "发送到闲鱼" not in page.text
