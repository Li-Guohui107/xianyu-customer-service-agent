"""到了设定的钟点，就用闲鱼网页发一条。"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime

from app.services.publish_schedule import due_slots, listing_from_product


class PublishWorker:
    def __init__(self, app, interval: float = 20.0) -> None:
        self.app = app
        self.interval = interval
        self.detail = "定时发布还没开始"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="xianyu-publish", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        asyncio._set_running_loop(None)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                self.detail = str(exc).splitlines()[0][:180]
            self._stop.wait(self.interval)

    def _tick(self) -> None:
        store = self.app.state.publish_store
        schedule = store.load()
        if not schedule["enabled"]:
            self.detail = "定时发布没开"
            return
        now = datetime.now()
        due = due_slots(schedule["slots"], now, store.published_ids(now.date()))
        if not due:
            self.detail = f"已保存 {len(schedule['slots'])} 个发布时间"
            return
        run_slot(self.app, due[0]["slot_id"])


def run_slot(app, slot_id: str, *, manual: bool = False) -> dict:
    """发一条并记下今天的结果。手动再发一次会覆盖今天的记录。"""
    worker = getattr(app.state, "publish_worker", None)
    lock = worker._lock if worker is not None else threading.Lock()
    with lock:
        store = app.state.publish_store
        slot = store.get_slot(slot_id)
        if slot is None:
            raise RuntimeError("这个时间点还没保存")
        today = datetime.now().date()
        if not manual and slot_id in store.published_ids(today):
            return {"status": "published", "detail": "今天这个时间已经发过"}
        product = app.state.knowledge.get(slot["product_id"])
        if product is None:
            store.mark_run(slot_id, today, "failed", "商品不在资料里", source=_run_source(manual))
            return {"status": "failed", "detail": "商品不在资料里"}
        try:
            listing = listing_from_product(
                product,
                when=datetime.now(),
                slot_id=slot_id,
                samples=store.list_samples(),
                price=slot.get("price") or None,
                title=slot.get("title") or None,
                description=slot.get("description") or None,
            )
            publisher = app.state.publisher or _browser_publish
            detail = publisher(listing)
        except Exception as exc:
            message = str(exc).splitlines()[0][:180] or "发布失败"
            store.mark_run(slot_id, today, "failed", message, source=_run_source(manual))
            if worker is not None:
                worker.detail = message
            return {"status": "failed", "detail": message}
        store.mark_run(slot_id, today, "published", detail, source=_run_source(manual))
        if worker is not None:
            worker.detail = detail
        return {"status": "published", "detail": detail}


def _run_source(manual: bool) -> str:
    return "manual" if manual else "schedule"


def _browser_publish(listing: dict) -> str:
    from app.connectors.publish_item import publish_listing

    return publish_listing(listing)
