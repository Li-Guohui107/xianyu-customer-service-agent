from datetime import datetime

import pytest

from app.connectors.publish_item import ensure_publish_url
from app.knowledge.store import Product
from app.services.publish_schedule import due_slots, listing_from_product, normalize_price, normalize_time
def _product(**overrides) -> Product:
    data = {
        "product_id": "demo-ml-002",
        "title": "演示用机器学习项目",
        "price": "199元",
        "condition": "数据处理、模型训练脚本和结果说明",
        "ship_time": "确认数据后2天内交付",
        "shipping": "闲鱼传文件，无实物邮寄",
        "defects": "不含数据采集，不含课程报告正文",
        "note": "虚构演示服务，不是真实在售商品。",
    }
    data.update(overrides)
    return Product(**data)


def test_publish_stays_off_the_chat_page_and_does_not_open_a_window():
    source = open("app/connectors/publish_item.py", encoding="utf-8").read()
    assert "new_page(" not in source
    assert "launch_browser" not in source
    assert "bring_to_front" not in source
    assert "activateTarget" not in source
    assert '"forTab": True' in source
    assert '"background": True' in source
    assert "for (const handler of handlers)" in source
    with pytest.raises(RuntimeError, match="聊天页"):
        ensure_publish_url("https://www.goofish.com/im")
    assert ensure_publish_url("https://www.goofish.com/publish") == "https://www.goofish.com/publish"


def test_time_must_be_hour_and_minute():
    assert normalize_time("09:30") == "09:30"
    with pytest.raises(ValueError):
        normalize_time("9:30")
    with pytest.raises(ValueError):
        normalize_time("24:00")


def test_a_slot_stays_due_after_its_time_until_the_schedule_publishes():
    slots = [
        {"slot_id": "morning", "time": "09:30", "enabled": True},
        {"slot_id": "night", "time": "21:00", "enabled": True},
        {"slot_id": "off", "time": "09:31", "enabled": False},
    ]
    due = due_slots(slots, datetime(2026, 11, 3, 9, 32), set())
    assert [slot["slot_id"] for slot in due] == ["morning"]
    assert due_slots(slots, datetime(2026, 11, 3, 9, 29), set()) == []
    assert [slot["slot_id"] for slot in due_slots(slots, datetime(2026, 11, 3, 9, 40), set())] == ["morning"]
    assert due_slots(slots, datetime(2026, 11, 3, 9, 32), {"morning"}) == []


def test_listing_uses_the_saved_price_and_refuses_a_promise():
    listing = listing_from_product(_product(), when=datetime(2026, 11, 3, 9, 0), slot_id="a", price="500")
    assert listing["price"] == "500"
    assert normalize_price("") == ""
    with pytest.raises(ValueError):
        normalize_price("不贵")
    catalog = listing_from_product(_product(), when=datetime(2026, 11, 3, 9, 0), slot_id="a")
    assert catalog["price"] == "199"
    assert "微信" not in listing["description"]
    assert "最低价" not in listing["description"]
    assert "不含数据采集" in listing["description"]
    with pytest.raises(ValueError, match="不能发布"):
        listing_from_product(_product(condition="可以包过"), when=datetime(2026, 11, 3, 9, 0))


def test_listing_changes_on_the_next_day_and_keeps_a_sample_line():
    first = listing_from_product(_product(), when=datetime(2026, 11, 3, 9, 0), slot_id="a")
    second = listing_from_product(_product(), when=datetime(2026, 11, 4, 9, 0), slot_id="a")
    same = listing_from_product(_product(), when=datetime(2026, 11, 3, 18, 0), slot_id="a")
    assert first["description"] != second["description"]
    assert first == same
    sampled = listing_from_product(
        _product(),
        when=datetime(2026, 11, 3, 9, 0),
        slot_id="a",
        samples=[{"title": "机器学习 可运行", "body": "拍前说一下数据从哪来。"}],
    )
    assert "拍前说一下数据从哪来" in sampled["description"]
    assert "机器学习" in sampled["title"]


def test_preview_writes_copy_without_publishing(client):
    response = client.post("/api/publish/preview", json={"product_id": "demo-ml-002"})
    assert response.status_code == 200
    body = response.json()
    assert "机器学习" in body["title"]
    assert body["price"] == "199"
    assert "不含数据采集" in body["description"]
    assert "没有上架" in body["detail"]
    assert client.get("/api/publish/schedule").json()["runs"] == []
    missing = client.post("/api/publish/preview", json={"product_id": "missing"})
    assert missing.status_code == 422


def test_saved_sample_shows_up_in_today_preview(client):
    saved = client.put(
        "/api/publish/samples",
        json={"text": "机器学习 可运行\n拍前说一下数据从哪来。"},
    )
    assert saved.status_code == 200
    schedule = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002"}]},
    )
    preview = schedule.json()["slots"][0]["preview_description"]
    assert "拍前说一下数据从哪来" in preview
    assert "微信" not in preview


def test_schedule_round_trip_and_unknown_product(client):
    saved = client.put(
        "/api/publish/schedule",
        json={
            "enabled": True,
            "slots": [
                {"time": "09:30", "product_id": "demo-ml-002"},
                {"time": "21:05", "product_id": "demo-python-004"},
            ],
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["enabled"] is True
    assert [slot["time"] for slot in body["slots"]] == ["09:30", "21:05"]
    again = client.get("/api/publish/schedule")
    assert [slot["slot_id"] for slot in again.json()["slots"]] == [slot["slot_id"] for slot in body["slots"]]

    rejected = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "missing"}]},
    )
    assert rejected.status_code == 422


def test_saved_price_is_what_gets_published(client):
    saved = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002", "price": "500"}]},
    )
    assert saved.status_code == 200
    slot = saved.json()["slots"][0]
    assert slot["price"] == "500"
    sent = []
    client.app.state.publisher = lambda listing: sent.append(listing) or "已提交到闲鱼"
    result = client.post(f"/api/publish/slots/{slot['slot_id']}/run")
    assert result.status_code == 200
    assert sent[0]["price"] == "500"
    rejected = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002", "price": "不贵"}]},
    )
    assert rejected.status_code == 422


def test_edited_copy_is_what_gets_published(client):
    saved = client.put(
        "/api/publish/schedule",
        json={
            "enabled": True,
            "slots": [{
                "time": "09:30",
                "product_id": "demo-ml-002",
                "price": "500",
                "title": "我改过的标题",
                "description": "我自己写的描述。",
            }],
        },
    )
    assert saved.status_code == 200
    slot = saved.json()["slots"][0]
    assert slot["title"] == "我改过的标题"
    assert slot["description"] == "我自己写的描述。"
    sent = []
    client.app.state.publisher = lambda listing: sent.append(listing) or "已提交到闲鱼"
    result = client.post(f"/api/publish/slots/{slot['slot_id']}/run")
    assert result.status_code == 200
    assert sent[0]["title"] == "我改过的标题"
    assert sent[0]["description"] == "我自己写的描述。"
    assert sent[0]["price"] == "500"
    rejected = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002", "title": "加微信"}]},
    )
    assert rejected.status_code == 422


def test_manual_publish_does_not_use_up_todays_schedule(client):
    saved = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002"}]},
    )
    slot_id = saved.json()["slots"][0]["slot_id"]
    client.app.state.publisher = lambda listing: "已提交到闲鱼"
    result = client.post(f"/api/publish/slots/{slot_id}/run")
    assert result.json()["status"] == "published"
    assert slot_id not in client.app.state.publish_store.published_ids(datetime.now().date())


def test_manual_run_uses_the_injected_publisher_once(client):
    saved = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002"}]},
    )
    slot_id = saved.json()["slots"][0]["slot_id"]
    sent = []
    client.app.state.publisher = lambda listing: sent.append(listing) or "已提交到闲鱼"
    first = client.post(f"/api/publish/slots/{slot_id}/run")
    assert first.status_code == 200
    assert first.json()["status"] == "published"
    assert "机器学习" in sent[0]["title"]
    assert "不含数据采集" in sent[0]["description"]
    assert "演示用" not in sent[0]["title"]
    schedule = client.get("/api/publish/schedule").json()
    assert schedule["runs"][0]["status"] == "published"


def test_failed_publish_is_recorded(client):
    saved = client.put(
        "/api/publish/schedule",
        json={"enabled": True, "slots": [{"time": "09:30", "product_id": "demo-ml-002"}]},
    )
    slot_id = saved.json()["slots"][0]["slot_id"]

    def explode(_listing):
        raise RuntimeError("闲鱼网页还没登录，这一条没有发")

    client.app.state.publisher = explode
    result = client.post(f"/api/publish/slots/{slot_id}/run")
    assert result.json()["status"] == "failed"
    assert "还没登录" in result.json()["detail"]
    missing = client.post("/api/publish/slots/missing/run")
    assert missing.status_code == 404
