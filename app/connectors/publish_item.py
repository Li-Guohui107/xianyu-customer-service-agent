"""在已经打开的浏览器进程里，后台打开发布页并提交。不新开窗口，也不动聊天页。"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGE_DIR = ROOT / "data" / "publish-images"
PUBLISH_URL = "https://www.goofish.com/publish"

FILL_JS = """
(payload) => {
  const setValue = (el, value) => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement : HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(proto.prototype, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const missing = [];
  const text = payload.title + "\\n" + payload.description;
  const editor = document.querySelector("[class*=editor--]")
    || document.querySelector("textarea");
  if (!editor) missing.push("描述");
  else if (editor.tagName === "TEXTAREA" || editor.tagName === "INPUT") setValue(editor, text);
  else {
    editor.textContent = text;
    editor.dispatchEvent(new InputEvent("input", { bubbles: true }));
  }
  const labelOf = (el) => {
    let node = el;
    for (let i = 0; i < 8 && node; i += 1) {
      node = node.parentElement;
      const label = ((node && node.innerText) || "").replace(/\\s+/g, "");
      if (label.includes("价格") || label.includes("原价") || label.includes("邮费")) return label;
    }
    return "";
  };
  const price = [...document.querySelectorAll("input")].find((el) => {
    const label = labelOf(el);
    return label.includes("价格") && !label.includes("原价") && !label.includes("邮费");
  });
  if (price) setValue(price, String(payload.price));
  else missing.push("价格");
  const ship = [...document.querySelectorAll("label, span")].find((el) => {
    return (el.innerText || "").replace(/\\s+/g, "") === "无需邮寄";
  });
  if (ship) ship.click();
  return { missing };
}
"""

WEB_CATEGORIES = ("软件/系统安装指导", "其他服务")

SELECT_CATEGORY_JS = r"""
async (label) => {
  const select = document.querySelector("[class*=categoryList--] .ant-select");
  if (!select) return false;
  const fiberKey = Object.keys(select).find((name) => name.startsWith("__reactFiber"));
  const handlers = [];
  let node = select[fiberKey];
  while (node) {
    const props = node.memoizedProps || {};
    if (typeof props.onChange === "function" && Array.isArray(props.options)) {
      const chosen = props.options.find((item) => item.label === label);
      if (chosen) handlers.push({ onChange: props.onChange, chosen });
    }
    node = node.return;
  }
  if (!handlers.length) return false;
  for (const handler of handlers) {
    handler.onChange(handler.chosen.value, Object.assign({}, handler.chosen, { isUserClick: "1" }));
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  return true;
}
"""

CURRENT_CATEGORY_JS = r"""
() => {
  const shown = document.querySelector("[class*=categoryList--] .ant-select-selection-item");
  return shown ? shown.innerText.trim() : "";
}
"""


def image_for(product_id: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = IMAGE_DIR / f"{product_id}{ext}"
        if path.is_file():
            return path
    for name in ("default.jpg", "default.jpeg", "default.png", "default.webp"):
        path = IMAGE_DIR / name
        if path.is_file():
            return path
    pictures = [
        path
        for path in IMAGE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ] if IMAGE_DIR.is_dir() else []
    if len(pictures) == 1:
        return pictures[0]
    return None


def _body_text(page) -> str:
    try:
        return page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        return ""


def ensure_publish_url(url: str) -> str:
    """聊天页和商品发布页不是同一个界面。发布只能停在发布页。"""
    address = url or ""
    if "/im" in address or "goofish.com/publish" not in address:
        raise RuntimeError("聊天页不能用来发布商品")
    return address


def _wait(page, milliseconds: int) -> None:
    wait = getattr(page, "wait_for_timeout", None)
    if callable(wait):
        wait(milliseconds)
    else:
        time.sleep(milliseconds / 1000)


def _click_exact(page, label: str) -> bool:
    return bool(
        page.evaluate(
            """(label) => {
              const el = [...document.querySelectorAll("button, [role='button']")].find((node) => {
                return (node.innerText || "").replace(/\\s/g, "") === label;
              });
              if (!el) return false;
              const key = Object.keys(el).find((name) => name.startsWith("__reactProps"));
              const props = key ? el[key] : null;
              if (props && typeof props.onClick === "function") {
                props.onClick({
                  preventDefault() {},
                  stopPropagation() {},
                  button: 0,
                  target: el,
                  currentTarget: el
                });
              }
              el.click();
              return true;
            }""",
            label,
        )
    )


def _targets(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
        data = json.loads(response.read().decode())
    return [item for item in data if item.get("type") == "page"]


class _PublishPage:
    """直接连到发布页自己的调试通道，不把这个标签拉到前台。"""

    def __init__(self, port: int, page_id: str):
        self.port = port
        self.page_id = page_id
        self.url = ""
        self._socket = None
        self._next = 0
        self._connect()

    def _connect(self) -> None:
        item = next((target for target in _targets(self.port) if target.get("id") == self.page_id), None)
        if item is None:
            raise RuntimeError("商品发布页没有在后台打开")
        from websockets.sync.client import connect

        self.url = item.get("url") or ""
        self._socket = connect(
            item["webSocketDebuggerUrl"],
            open_timeout=5,
            close_timeout=2,
            max_size=4_000_000,
        )

    def close(self) -> None:
        try:
            if self._socket is not None:
                self._socket.close()
        except Exception:
            pass

    def _call(self, method: str, params: dict | None = None, timeout: float = 8):
        if self._socket is None:
            self._connect()
        self._next += 1
        ident = self._next
        try:
            self._socket.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                incoming = json.loads(self._socket.recv(timeout=timeout))
                if incoming.get("id") != ident:
                    continue
                if "error" in incoming:
                    message = incoming["error"].get("message", "发布页执行失败")
                    raise RuntimeError(message)
                return incoming.get("result", {})
        except RuntimeError:
            raise
        except Exception as exc:
            self.close()
            self._socket = None
            raise RuntimeError("发布页没有响应") from exc
        raise RuntimeError("发布页没有响应")

    def evaluate(self, expression: str, arg=None, timeout: float = 8):
        text = expression.strip()
        if text.startswith("(") or text.startswith("function") or text.startswith("async"):
            argument = "" if arg is None else json.dumps(arg, ensure_ascii=False)
            expression = f"({text})({argument})"
        result = self._call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError("发布页脚本没有跑成")
        return remote.get("value")

    def set_files(self, paths: list[str]) -> bool:
        root = self._call("DOM.getDocument", {"depth": 0}).get("root", {})
        found = self._call(
            "DOM.querySelector",
            {"nodeId": root.get("nodeId"), "selector": "input[type='file']"},
        )
        if not found.get("nodeId"):
            return False
        self._call("DOM.setFileInputFiles", {"nodeId": found["nodeId"], "files": paths})
        return True


def _attach(port: int):
    """只接入已经开着调试端口的浏览器，不新开窗口，也不新建标签。"""
    from playwright.sync_api import sync_playwright

    from app.connectors.live_reply import debugger_is_open

    if not debugger_is_open(port):
        raise RuntimeError("还没连上闲鱼网页")
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    return playwright, browser


def _release(playwright, browsers) -> None:
    for browser in browsers:
        try:
            browser._impl_obj._connection = None
        except Exception:
            pass
    try:
        playwright.stop()
    except Exception:
        pass


def _open_background_publish_page(browser, port: int) -> tuple[str, str]:
    """在当前窗口里加一个不抢焦点的发布页。聊天页保持不动。

    返回标签 id 和页面 id。Chrome 里这两个不是同一个 id，关掉时要用标签 id。
    """
    existing = _targets(port)
    if not existing:
        raise RuntimeError("还没连上闲鱼网页")
    anchor = next((item for item in existing if "/im" in (item.get("url") or "")), existing[0])
    before_ids = {item["id"] for item in existing}
    session = browser.new_browser_cdp_session()
    tab_id = ""
    try:
        created = session.send(
            "Target.createTarget",
            {"url": PUBLISH_URL, "background": True, "newWindow": False, "forTab": True},
        )
        tab_id = created.get("targetId", "")
        if not tab_id:
            raise RuntimeError("没有在浏览器进程里打开商品发布页")
        deadline = time.monotonic() + 8
        publish = None
        while time.monotonic() < deadline:
            publish = next(
                (
                    item
                    for item in _targets(port)
                    if item.get("id") not in before_ids and "goofish.com/publish" in (item.get("url") or "")
                ),
                None,
            )
            if publish is not None:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("商品发布页没有在后台打开")
        if "/im" in (publish.get("url") or ""):
            raise RuntimeError("聊天页不能用来发布商品")
        anchor_window = session.send("Browser.getWindowForTarget", {"targetId": anchor["id"]})["windowId"]
        publish_window = session.send("Browser.getWindowForTarget", {"targetId": tab_id})["windowId"]
        if anchor_window != publish_window:
            raise RuntimeError("发布页跑到了另一个窗口，这一条没有发")
        return tab_id, publish["id"]
    except Exception:
        _close_target(browser, tab_id)
        raise
    finally:
        session.detach()


def _close_target(browser, target_id: str) -> None:
    if not target_id:
        return
    session = browser.new_browser_cdp_session()
    try:
        session.send("Target.closeTarget", {"targetId": target_id})
    except Exception:
        pass
    finally:
        session.detach()


def _wait_for_form(page) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ready = page.evaluate(
            "() => Boolean(document.querySelector('[class*=editor--]') || document.querySelector('textarea'))"
        )
        if ready:
            return
        _wait(page, 300)
    raise RuntimeError("发布页还没出来")


def _current_category(page) -> str:
    try:
        return page.evaluate(CURRENT_CATEGORY_JS) or ""
    except Exception:
        return ""


def _web_blocks(page) -> bool:
    return "网页版暂不支持" in _body_text(page)


def _use_web_category(page) -> str:
    """留下网页自己识别出来、并且网页允许发布的分类。"""
    deadline = time.monotonic() + 8
    label = ""
    while time.monotonic() < deadline:
        label = _current_category(page)
        if label:
            break
        _wait(page, 300)
    if label and not _web_blocks(page):
        return label
    for candidate in WEB_CATEGORIES:
        if not page.evaluate(SELECT_CATEGORY_JS, candidate, timeout=12):
            continue
        _wait(page, 800)
        if _current_category(page) == candidate and not _web_blocks(page):
            return candidate
    raise RuntimeError("网页版这些分类都不能发")


def fill_and_submit(page, listing: dict) -> str:
    """只在商品发布页里填写并点击。不把这个页拉到前台。"""
    ensure_publish_url(getattr(page, "url", "") or "")
    _wait_for_form(page)
    body = _body_text(page)
    if "登录" in body and "描述" not in body and "价格" not in body:
        raise RuntimeError("闲鱼网页还没登录，这一条没有发")
    filled = page.evaluate(FILL_JS, listing)
    missing = filled.get("missing") if isinstance(filled, dict) else ["标题"]
    if missing and _click_exact(page, "卖闲置"):
        _wait(page, 600)
        filled = page.evaluate(FILL_JS, listing)
        missing = filled.get("missing") if isinstance(filled, dict) else ["标题"]
    if missing:
        raise RuntimeError("发布页没找到" + "、".join(missing))
    image = image_for(listing["product_id"])
    if image is None:
        raise RuntimeError("先放一张图片到 data/publish-images")
    if not page.set_files([str(image)]):
        raise RuntimeError("发布页没有图片上传框")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if "添加细节图" in _body_text(page):
            break
        _wait(page, 300)
    else:
        raise RuntimeError("图片没有传上去")
    category = _use_web_category(page)
    if not _click_exact(page, "发布"):
        raise RuntimeError("发布页没有发布按钮")
    deadline = time.monotonic() + 8
    after = ""
    url = getattr(page, "url", "") or ""
    while time.monotonic() < deadline:
        try:
            page.url = page.evaluate("() => location.href") or page.url
        except Exception:
            pass
        after = _body_text(page)
        url = getattr(page, "url", "") or ""
        if "/im" in url:
            raise RuntimeError("聊天页不能用来发布商品")
        if "item?id=" in url or "发布成功" in after or "上架成功" in after:
            return "已提交到闲鱼。分类是" + category + "。"
        if any(phrase in after for phrase in ("请上传图片", "请添加图片", "至少上传", "图片不能为空")):
            raise RuntimeError("闲鱼没有收下图片")
        _wait(page, 400)
    for line in after.splitlines():
        text = line.strip()
        if text and any(word in text for word in ("请", "必须", "不能", "失败")) and len(text) <= 40:
            raise RuntimeError(text)
    raise RuntimeError("点了发布，但页面没有显示成功")


def publish_listing(listing: dict) -> str:
    from app.connectors.live_reply import DEBUG_PORT

    playwright, browser = _attach(DEBUG_PORT)
    browsers = [browser]
    tab_id = ""
    page = None
    try:
        tab_id, page_id = _open_background_publish_page(browser, DEBUG_PORT)
        page = _PublishPage(DEBUG_PORT, page_id)
        return fill_and_submit(page, listing)
    finally:
        if page is not None:
            page.close()
        _close_target(browser, tab_id)
        _release(playwright, browsers)
