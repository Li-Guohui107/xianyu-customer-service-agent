"""盯着闲鱼网页，有新消息就直接回复。"""

from __future__ import annotations

import asyncio
import threading

from app.connectors.live_reply import connect_page, reply_once
from app.schemas.consultation import XianyuStatus


class AutoReplyWorker:
    def __init__(self, app, interval: float = 0.2) -> None:
        self.app = app
        self.interval = interval
        self.attached = False
        self.detail = "正在连接浏览器"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="xianyu-auto-reply", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> XianyuStatus:
        return XianyuStatus(
            mode="browser_auto",
            browser_enabled=self.attached,
            sends_messages=True,
            detail=self.detail,
        )

    def _loop(self) -> None:
        # 清掉可能从服务线程带过来的事件循环，否则 Playwright 会拒绝接入。
        asyncio._set_running_loop(None)
        connection = None
        while not self._stop.is_set():
            try:
                if connection is None:
                    connection = connect_page()
                    self.attached = True
                    self.detail = "已连上闲鱼网页，新消息会直接回复"
                sent = reply_once(connection[2], self.app)
            except Exception as exc:
                self.detail = str(exc).splitlines()[0][:180]
                self._stop.wait(1.0)
                continue
            if sent:
                continue
            self._stop.wait(self.interval)
        self.attached = False
