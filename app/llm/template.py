"""离线模板生成器。按买家问法回答，测试和未配置密钥时使用。"""

from __future__ import annotations

from app.knowledge.store import Product
from app.services.reply import compose_reply


class TemplateReplyGenerator:
    def __init__(self, product: Product | None = None) -> None:
        self.product = product

    def generate(
        self,
        buyer_message: str,
        knowledge_text: str,
        history: list[dict] | None = None,
    ) -> str:
        _ = history
        if knowledge_text.startswith("没有查到该商品"):
            return compose_reply(buyer_message, None)
        return compose_reply(buyer_message, self.product)
