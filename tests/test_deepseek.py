import json
import os

import httpx
import pytest

from app.config import build_generator, load_dotenv
from app.llm.deepseek import SYSTEM_PROMPT, DeepSeekReplyGenerator, LLMError
from app.llm.template import TemplateReplyGenerator


class FakeHttp:
    def __init__(self, payload=None, error=None):
        if payload is None:
            payload = {"choices": [{"message": {"content": " 这是草稿 "}}]}
        self.payload = payload
        self.error = error
        self.url = None
        self.headers = None
        self.json = None
        self.timeout = None

    def post(self, url, headers=None, json=None, timeout=None):
        if self.error:
            raise self.error
        self.url = url
        self.headers = headers
        self.json = json
        self.timeout = timeout

        class Response:
            def raise_for_status(self):
                return None

            def json(inner_self):
                return payload

        payload = self.payload
        return Response()


def test_request_contains_buyer_message_product_facts_and_timeout():
    fake = FakeHttp()
    generator = DeepSeekReplyGenerator(
        api_key="test-key",
        base_url="https://example.invalid",
        model="deepseek-chat",
        client=fake,
    )
    text = generator.generate("还在吗", "价格：99元", [{"role": "buyer", "content": "上一句"}])
    body = json.dumps(fake.json, ensure_ascii=False)
    assert text == "这是草稿"
    assert fake.url == "https://example.invalid/chat/completions"
    assert fake.headers["Authorization"] == "Bearer test-key"
    assert "test-key" not in body
    assert "还在吗" in body
    assert "价格：99元" in body
    assert "上一句" in body
    assert "不要编造" in SYSTEM_PROMPT
    assert SYSTEM_PROMPT in body
    assert fake.timeout == 30


def test_http_failure_raises_llm_error_without_calling_network():
    fake = FakeHttp(error=httpx.TimeoutException("timed out"))
    generator = DeepSeekReplyGenerator(api_key="test-key", client=fake)
    with pytest.raises(LLMError, match="DeepSeek 调用失败"):
        generator.generate("你好", "没有查到该商品", [])


def test_malformed_response_raises_llm_error():
    fake = FakeHttp(payload={})
    generator = DeepSeekReplyGenerator(api_key="test-key", client=fake)
    with pytest.raises(LLMError):
        generator.generate("你好", "价格：99元", [])


def test_missing_key_uses_template(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert isinstance(build_generator(), TemplateReplyGenerator)


def test_blank_key_uses_template(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    assert isinstance(build_generator(), TemplateReplyGenerator)


def test_key_selects_deepseek_without_request(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    generator = build_generator()
    assert isinstance(generator, DeepSeekReplyGenerator)


def test_dotenv_does_not_override_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    load_dotenv(env_file)
    assert os.environ["DEEPSEEK_API_KEY"] == "from-env"


def test_env_example_has_no_secret():
    from pathlib import Path

    text = Path(".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in text
    assert "sk-" not in text
