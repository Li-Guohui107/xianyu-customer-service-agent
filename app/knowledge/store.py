"""虚构商品资料的读取和检索。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_PRODUCTS_PATH = Path(__file__).resolve().parents[2] / "data" / "products.json"
NOT_FOUND_TEXT = "没有查到该商品。不要编造价格、交付内容或周期。"


class Product(BaseModel):
    product_id: str
    title: str
    price: str
    condition: str
    selling_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    location: str = ""
    shipping: str = ""
    ship_time: str = ""
    bargain: str = ""
    floor_price: str = ""
    defects: str = ""
    stock: str = ""
    note: str


class ProductStore:
    """按商品编号精确查找；没有编号时，用关键词在买家消息里匹配。"""

    def __init__(self, path: Path | None = None, products: list[Product] | None = None) -> None:
        if products is not None:
            self.products = products
            return
        source = path or DEFAULT_PRODUCTS_PATH
        raw = json.loads(source.read_text(encoding="utf-8"))
        self.products = [Product.model_validate(item) for item in raw]

    def list_products(self) -> list[Product]:
        return list(self.products)

    def get(self, product_id: str) -> Product | None:
        for product in self.products:
            if product.product_id == product_id:
                return product
        return None

    def search(self, text: str) -> Product | None:
        best: Product | None = None
        best_length = 0
        for product in self.products:
            for keyword in product.keywords:
                if keyword and keyword in text and len(keyword) > best_length:
                    best = product
                    best_length = len(keyword)
        return best

    def resolve(self, product_id: str | None, buyer_message: str) -> Product | None:
        """指定了编号就只按编号查，避免用关键词误配到另一个商品。"""
        if product_id:
            return self.get(product_id)
        return self.search(buyer_message)


def _fact(value: str) -> str:
    return value.strip() or "资料未写"


def format_product(product: Product) -> str:
    points = "、".join(product.selling_points) if product.selling_points else "无"
    return "\n".join(
        [
            f"服务：{product.title}",
            f"价格：{product.price}",
            f"交付内容：{product.condition}",
            f"技术栈：{points}",
            f"交付方式：{_fact(product.shipping)}",
            f"周期：{_fact(product.ship_time)}",
            f"方式：{_fact(product.location)}",
            f"议价：{_fact(product.bargain)}",
            f"最低价：{_fact(product.floor_price)}",
            f"不包含：{_fact(product.defects)}",
            f"可接单：{_fact(product.stock)}",
            f"说明：{product.note}",
        ]
    )
