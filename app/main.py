"""FastAPI 入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.drafts import router as drafts_router
from app.api.products import router as products_router
from app.api.sessions import router as sessions_router
from app.api.xianyu import router as xianyu_router
from app.config import build_generator, load_dotenv, load_settings
from app.knowledge.store import ProductStore
from app.llm.base import ReplyGenerator
from app.memory.store import SessionStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    *,
    database_path: str | None = None,
    generator: ReplyGenerator | None = None,
    products_path: Path | None = None,
    load_env_file: bool = True,
    wechat_id: str | None = None,
    auto_reply: bool = False,
) -> FastAPI:
    if load_env_file:
        load_dotenv()
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = None
        if app.state.auto_reply:
            from app.services.auto_reply import AutoReplyWorker

            worker = AutoReplyWorker(app)
            app.state.worker = worker
            worker.start()
        yield
        if worker is not None:
            worker.stop()

    app = FastAPI(title="闲鱼智能客服 Agent", version="0.1.0", lifespan=lifespan)
    app.state.knowledge = ProductStore(path=products_path)
    app.state.memory = SessionStore(database_path or settings.database_path)
    app.state.wechat_id = settings.wechat_id if wechat_id is None else wechat_id.strip()
    app.state.generator = generator or build_generator()
    app.state.auto_reply = auto_reply
    app.state.worker = None

    @app.get("/health")
    def health() -> dict[str, str]:
        """确认服务已经启动。"""
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.include_router(drafts_router)
    app.include_router(products_router)
    app.include_router(sessions_router)
    app.include_router(xianyu_router)
    return app


app = create_app(auto_reply=True)
