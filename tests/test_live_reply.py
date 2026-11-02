from app.connectors.live_reply import OPEN_UNREAD_JS, SEND_JS, SNAPSHOT_JS, reply_once, safe_outgoing
from app.llm.template import TemplateReplyGenerator
from app.main import create_app


class FakePage:
    def __init__(self, buyer: str) -> None:
        self.state = {"id": "买家A", "buyer": buyer, "hasUnread": False}
        self.sent: list[str] = []

    def evaluate(self, script, arg=None):
        if script == SNAPSHOT_JS:
            return dict(self.state)
        if script == SEND_JS:
            self.sent.append(arg)
            return True
        raise AssertionError("意外脚本")


def _app(tmp_path, generator=None):
    return create_app(
        database_path=str(tmp_path / "agent.db"),
        generator=generator or TemplateReplyGenerator(),
        load_env_file=False,
        auto_reply=False,
    )


def test_new_buyer_message_is_sent_once(tmp_path):
    app = _app(tmp_path)
    page = FakePage("这个还能做吗")
    first = reply_once(page, app)
    assert first
    assert page.sent == [first]
    assert reply_once(page, app) is None
    assert page.sent == [first]


class PromiseGenerator:
    def generate(self, buyer_message: str, knowledge_text: str, history=None) -> str:
        return "可以包过，交给我。"


def test_academic_promise_is_replaced_before_send(tmp_path):
    app = _app(tmp_path, PromiseGenerator())
    page = FakePage("这个能包过吗")
    sent = reply_once(page, app)
    assert sent is not None
    assert "可以包过" not in sent
    assert "成绩承诺都不能做" in sent
    assert page.sent == [sent]


def test_unread_chat_is_replied_without_another_poll(tmp_path):
    app = _app(tmp_path)
    page = FakePage("")
    page.state = {"id": "买家B", "buyer": "", "hasUnread": True}

    def evaluate(script, arg=None):
        if script == SNAPSHOT_JS:
            return dict(page.state)
        if script == OPEN_UNREAD_JS:
            page.state = {"id": "买家B", "buyer": "在吗", "hasUnread": False}
            return True
        if script == SEND_JS:
            page.sent.append(arg)
            return True
        raise AssertionError("意外脚本")

    page.evaluate = evaluate
    sent = reply_once(page, app)
    assert sent
    assert page.sent == [sent]


def test_repeated_buyer_text_is_sent_again(tmp_path):
    app = _app(tmp_path)
    page = FakePage("在吗")
    page.state["sig"] = "6\told\t在吗\tb"
    assert reply_once(page, app)
    page.state["sig"] = "8\tseller\t在吗\tb"
    assert reply_once(page, app)
    assert len(page.sent) == 2


def test_refusal_is_not_rewritten():
    text = "不能包过，代码可以做。"
    assert safe_outgoing(text) == text
