"""商品列表，供客服页面选择虚构商品。"""

from fastapi import APIRouter, Request

from app.schemas.consultation import ProductSummary

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products", response_model=list[ProductSummary])
def list_products(request: Request) -> list[ProductSummary]:
    return [
        ProductSummary(
            product_id=product.product_id,
            title=product.title,
            price=product.price,
            condition=product.condition,
            shipping=product.shipping,
            ship_time=product.ship_time,
            bargain=product.bargain,
            floor_price=product.floor_price,
            defects=product.defects,
            stock=product.stock,
            location=product.location,
        )
        for product in request.app.state.knowledge.list_products()
    ]
