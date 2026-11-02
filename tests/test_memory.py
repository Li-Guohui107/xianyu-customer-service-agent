from fastapi.testclient import TestClient

from app.main import create_app
from app.memory.store import SessionStore


class RecordingGenerator:
    def __init__(self):
        self.history = None

    def generate(self, buyer_message, knowledge_text, history=None):
        self.history = history or []
        return "草稿"


def test_recent_messages_keep_the_latest_window(tmp_path):
    store = SessionStore(str(tmp_path / "memory.db"))
    session_id = store.create_session()
    for index in range(8):
        store.add_message(session_id, "buyer", f"m{index}", None)
    recent = store.recent_messages(session_id, limit=6)
    assert [item["content"] for item in recent] == [f"m{index}" for index in range(2, 8)]


def test_session_remembers_turns_and_new_session_is_isolated(client):
    first = client.post(
        "/api/drafts",
        json={"buyer_message": "代码复现还接吗", "product_id": "demo-repro-001"},
    )
    session_id = first.json()["session_id"]
    second = client.post(
        "/api/drafts",
        json={
            "buyer_message": "多久能好",
            "product_id": "demo-repro-001",
            "session_id": session_id,
        },
    )
    assert second.status_code == 200
    history = client.get(f"/api/sessions/{session_id}")
    messages = history.json()["messages"]
    assert [item["role"] for item in messages] == ["buyer", "assistant", "buyer", "assistant"]
    assert messages[0]["content"] == "代码复现还接吗"
    assert messages[2]["content"] == "多久能好"

    other = client.post("/api/drafts", json={"buyer_message": "机器学习还接吗"})
    other_id = other.json()["session_id"]
    assert other_id != session_id
    other_history = client.get(f"/api/sessions/{other_id}").json()["messages"]
    assert all(item["content"] != "代码复现还接吗" for item in other_history)


def test_unknown_session_is_not_created_silently(client):
    response = client.post(
        "/api/drafts",
        json={"buyer_message": "在吗", "session_id": "missing-session"},
    )
    assert response.status_code == 404
    assert client.get("/api/sessions/missing-session").status_code == 404


def test_second_turn_passes_previous_messages_to_generator(tmp_path):
    recorder = RecordingGenerator()
    application = create_app(
        database_path=str(tmp_path / "history.db"),
        generator=recorder,
        load_env_file=False,
    )
    with TestClient(application) as test_client:
        first = test_client.post(
            "/api/drafts",
            json={"buyer_message": "代码复现还接吗", "product_id": "demo-repro-001"},
        )
        session_id = first.json()["session_id"]
        test_client.post(
            "/api/drafts",
            json={
                "buyer_message": "多久能好",
                "product_id": "demo-repro-001",
                "session_id": session_id,
            },
        )
    assert [item["role"] for item in recorder.history] == ["buyer", "assistant"]
    assert recorder.history[0]["content"] == "代码复现还接吗"
