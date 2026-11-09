"""定时发布的时间表。一天能加多条，也能一条都没有。"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.schemas.consultation import (
    ListingSamplesIn,
    ListingSamplesOut,
    PublishPreviewIn,
    PublishPreviewOut,
    PublishRunResult,
    PublishScheduleIn,
    PublishScheduleOut,
    PublishSlotOut,
)
from app.services.publish_schedule import (
    listing_from_product,
    normalize_copy,
    normalize_price,
    normalize_time,
    parse_samples,
    samples_to_text,
)
from app.services.publish_worker import run_slot

router = APIRouter(prefix="/api/publish", tags=["publish"])


def _schedule_out(request: Request) -> PublishScheduleOut:
    store = request.app.state.publish_store
    schedule = store.load()
    samples = store.list_samples()
    worker = getattr(request.app.state, "publish_worker", None)
    now = datetime.now()
    slots = []
    for slot in schedule["slots"]:
        preview_title = ""
        preview_description = ""
        product = request.app.state.knowledge.get(slot["product_id"])
        if product is not None:
            try:
                listing = listing_from_product(
                    product,
                    when=now,
                    slot_id=slot["slot_id"],
                    samples=samples,
                    price=slot.get("price") or None,
                )
            except ValueError:
                listing = None
            if listing is not None:
                preview_title = listing["title"]
                preview_description = listing["description"]
        slots.append(PublishSlotOut(**slot, preview_title=preview_title, preview_description=preview_description))
    return PublishScheduleOut(
        enabled=schedule["enabled"],
        slots=slots,
        runs=store.runs_on(now.date()),
        detail=worker.detail if worker is not None else "",
        samples_text=samples_to_text(samples),
    )


@router.get("/schedule", response_model=PublishScheduleOut)
def get_schedule(request: Request) -> PublishScheduleOut:
    return _schedule_out(request)


@router.put("/schedule", response_model=PublishScheduleOut)
def save_schedule(body: PublishScheduleIn, request: Request) -> PublishScheduleOut:
    knowledge = request.app.state.knowledge
    slots = []
    seen_ids: set[str] = set()
    for item in body.slots:
        try:
            clock = normalize_time(item.time)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if knowledge.get(item.product_id) is None:
            raise HTTPException(status_code=422, detail="选的服务不在资料里")
        try:
            amount = normalize_price(item.price)
            heading = normalize_copy(item.title, limit=30)
            body_text = normalize_copy(item.description, limit=800)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        slot_id = item.slot_id or uuid.uuid4().hex[:12]
        if slot_id in seen_ids:
            slot_id = uuid.uuid4().hex[:12]
        seen_ids.add(slot_id)
        slots.append(
            {
                "slot_id": slot_id,
                "time": clock,
                "product_id": item.product_id,
                "enabled": item.enabled,
                "price": amount,
                "title": heading,
                "description": body_text,
            }
        )
    request.app.state.publish_store.replace(enabled=body.enabled, slots=slots)
    return _schedule_out(request)


@router.put("/samples", response_model=ListingSamplesOut)
def save_samples(body: ListingSamplesIn, request: Request) -> ListingSamplesOut:
    try:
        samples = parse_samples(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    stored = request.app.state.publish_store.replace_samples(samples)
    return ListingSamplesOut(text=samples_to_text(stored))


@router.post("/preview", response_model=PublishPreviewOut)
def preview_listing(body: PublishPreviewIn, request: Request) -> PublishPreviewOut:
    """不连闲鱼，只按今天的规则写出将要发布的标题、描述和标价。"""
    product = request.app.state.knowledge.get(body.product_id)
    if product is None:
        raise HTTPException(status_code=422, detail="选的服务不在资料里")
    try:
        listing = listing_from_product(
            product,
            when=datetime.now(),
            slot_id=body.slot_id,
            samples=request.app.state.publish_store.list_samples(),
            price=body.price or None,
            title=body.title or None,
            description=body.description or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PublishPreviewOut(
        title=listing["title"],
        description=listing["description"],
        price=listing["price"],
        detail="这是试发，没有打开闲鱼，也没有上架。",
    )


@router.post("/slots/{slot_id}/run", response_model=PublishRunResult)
def run_now(slot_id: str, request: Request) -> PublishRunResult:
    try:
        result = run_slot(request.app, slot_id, manual=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PublishRunResult(**result)
