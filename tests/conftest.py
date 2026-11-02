"""测试使用临时数据库和模板生成器，不读取 .env，也不访问网络。"""

import pytest
from fastapi.testclient import TestClient

from app.llm.template import TemplateReplyGenerator
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    application = create_app(
        database_path=str(tmp_path / "agent.db"),
        generator=TemplateReplyGenerator(),
        load_env_file=False,
    )
    with TestClient(application) as test_client:
        yield test_client
