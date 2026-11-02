"""通过浏览器调试端口操作闲鱼网页。不读取 Cookie，不走私信接口。"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from app.llm.template import TemplateReplyGenerator
from app.schemas.consultation import ConsultationRequest
from app.services.draft import build_draft
from app.services.reply import detect_intents
from app.services.risk import _seller_text

ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "browser-profile"
DEBUG_PORT = 9222
MESSAGE_URL = "https://www.goofish.com/im"

SNAPSHOT_JS = """
() => {
  const textOf = (el) => (el.innerText || "").trim();
  const input = document.querySelector("textarea[placeholder*='请输入消息']");
  const inputRect = input ? input.getBoundingClientRect() : null;
  const panelLeft = inputRect ? inputRect.left - 20 : 450;
  const panelRight = inputRect ? inputRect.right + 20 : window.innerWidth - 40;
  const panelBottom = inputRect ? inputRect.top - 8 : window.innerHeight - 80;
  const panelMid = (panelLeft + panelRight) / 2;
  const bubbles = [...document.querySelectorAll("[class*='message-content--']")].map((el) => {
    const rect = el.getBoundingClientRect();
    const lines = textOf(el).split(/\\n+/).map((line) => line.trim()).filter((line) => line && line !== "已读");
    const parentText = el.parentElement ? textOf(el.parentElement) : "";
    return { text: lines[0] || "", top: rect.top, left: rect.left, nick: parentText.split(/\\n+/)[0].trim() };
  }).filter((item) => item.text && item.left > panelLeft && item.left < panelRight && item.top > 100 && item.top < panelBottom);
  bubbles.sort((a, b) => a.top - b.top);
  const last = bubbles.length ? bubbles[bubbles.length - 1] : null;
  const prev = bubbles.length > 1 ? bubbles[bubbles.length - 2].text : "";
  const fromBuyer = Boolean(last) && last.left < panelMid;
  const badge = [...document.querySelectorAll("[class*='conversation-item--'] .ant-scroll-number")].find((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.width < 36 && /^[1-9]\\d*$/.test(textOf(el));
  });
  const sig = last ? [bubbles.length, prev, last.text, fromBuyer ? "b" : "s"].join("\\t") : "";
  return {
    id: (last && last.nick) || "open",
    buyer: fromBuyer && last ? last.text : "",
    hasUnread: Boolean(badge),
    sig,
  };
}
"""

OPEN_UNREAD_JS = """
() => {
  const viewW = window.innerWidth;
  const badge = [...document.querySelectorAll("span, em, i, sup")].find((el) => {
    const rect = el.getBoundingClientRect();
    const text = (el.innerText || "").trim();
    return rect.left < viewW * 0.32 && rect.width > 0 && rect.width < 30 && /^[1-9]\\d*$/.test(text);
  });
  const item = badge && (badge.closest("a, li, [role='listitem']") || badge.parentElement);
  if (!item) return false;
  item.click();
  return true;
}
"""

SEND_JS = r"""
(text) => {
  const input = document.querySelector("textarea[placeholder*='请输入消息']");
  if (!input) return false;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  setter.call(input, text);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  const button = [...document.querySelectorAll("button")].find((el) => (el.innerText || "").replace(/\s/g, "") === "发送");
  if (!button) return false;
  button.click();
  return true;
}
"""

FORBIDDEN_PROMISES = ("包过", "保证及格", "保证录用", "代写论文", "代考", "替我交", "替我提交", "保分")


def safe_outgoing(text: str) -> str:
    """答应代写、包过或替交的句子不发出，改成拒绝。"""
    cleaned = _seller_text(text)
    if any(term in cleaned for term in FORBIDDEN_PROMISES):
        return "代码和说明可以做。论文正文、考试、替交和成绩承诺都不能做。"
    return text.strip()


def _deliver(page, text: str) -> bool:
    """优先用真实按键填入，闲鱼这个输入框认的是页面事件。"""
    if not hasattr(page, "locator"):
        return bool(page.evaluate(SEND_JS, text))
    box = page.locator("textarea[placeholder*='请输入消息']")
    if box.count() == 0:
        return False
    box.fill(text, timeout=2000)
    page.get_by_role("button", name="发 送").click(timeout=2000)
    return True


def session_id_for(chat_key: str) -> str:
    digest = hashlib.sha256(chat_key.encode("utf-8")).hexdigest()[:30]
    return f"xy{digest}"


_INSTANT = {"greeting", "price", "bargain", "availability"}


def _local_reply(buyer: str) -> bool:
    """打招呼、在不在、问价格这类短句用本地规则，不等模型。"""
    text = buyer.strip()
    if len(text) > 30:
        return False
    codes = {code for code, _label in detect_intents(text)}
    return bool(codes) and codes <= _INSTANT


def _open_next(page) -> None:
    if not page.evaluate(OPEN_UNREAD_JS):
        return
    wait = getattr(page, "wait_for_timeout", None)
    if callable(wait):
        wait(200)


def reply_once(page, app) -> str | None:
    """读当前网页对话。有新的买家消息就立刻写进输入框并点发送。"""
    memory = app.state.memory
    state = page.evaluate(SNAPSHOT_JS)
    buyer = ""
    chat_key = "open"
    token = ""
    for _ in range(2):
        buyer = str(state.get("buyer") or "").strip()
        chat_key = str(state.get("id") or "open").strip() or "open"
        token = str(state.get("sig") or buyer).strip() or buyer
        if buyer and not memory.has_sent_reply(chat_key, token):
            break
        if not state.get("hasUnread"):
            return None
        _open_next(page)
        state = page.evaluate(SNAPSHOT_JS)
    else:
        return None
    session_id = session_id_for(chat_key)
    memory.ensure_session(session_id)
    generator = TemplateReplyGenerator() if _local_reply(buyer) else app.state.generator
    draft = build_draft(
        ConsultationRequest(buyer_message=buyer, session_id=session_id),
        knowledge=app.state.knowledge,
        generator=generator,
        memory=memory,
        wechat_id=getattr(app.state, "wechat_id", ""),
    )
    outgoing = safe_outgoing(draft.draft_reply)
    sent = _deliver(page, outgoing)
    if not sent:
        raise RuntimeError("没找到闲鱼网页的输入框")
    memory.remember_sent_reply(chat_key, token)
    return outgoing


def debugger_is_open(port: int = DEBUG_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.4) as response:
            return response.status == 200
    except Exception:
        return False


def chrome_executable() -> str | None:
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def launch_browser(port: int = DEBUG_PORT) -> None:
    executable = chrome_executable()
    if executable is None:
        raise RuntimeError("没找到 Chrome 或 Edge")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            executable,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={PROFILE_DIR}",
            "--new-window",
            MESSAGE_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_debugger(port: int = DEBUG_PORT, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if debugger_is_open(port):
            return True
        time.sleep(0.2)
    return False


def connect_page(port: int = DEBUG_PORT):
    """接到已经打开调试端口的浏览器。只接入，不关闭浏览器进程。"""
    from playwright.sync_api import sync_playwright

    if not debugger_is_open(port):
        launch_browser(port)
        if not wait_for_debugger(port):
            raise RuntimeError("浏览器进程没有打开调试端口")
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    page = None
    for context in browser.contexts:
        for candidate in context.pages:
            if "goofish.com" in candidate.url:
                page = candidate
                break
        if page is not None:
            break
    if page is None:
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(MESSAGE_URL, wait_until="domcontentloaded")
    return playwright, browser, page


def disconnect_without_closing_browser(connection) -> None:
    """断开控制连接，保留用户已经登录的 Chrome。"""
    if not connection:
        return
    browser = connection[1]
    try:
        browser._impl_obj._connection = None
    except Exception:
        pass
