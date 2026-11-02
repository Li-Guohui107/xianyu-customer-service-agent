"""回复生成器接口。路由只依赖这个接口，不关心具体模型。"""

from __future__ import annotations

from typing import Protocol


class ReplyGenerator(Protocol):
    def generate(
        self,
        buyer_message: str,
        knowledge_text: str,
        history: list[dict] | None = None,
    ) -> str:
        """根据买家消息、商品资料和近期对话生成回复草稿。"""
