"""把粘贴的闲鱼对话整理成买家消息。

浏览器读取默认关闭：不打开闲鱼页面，不读取 Cookie，也不发送消息。
"""

from __future__ import annotations

BUYER_PREFIXES = ("买家:", "买家：", "对方:", "对方：")
AGENT_PREFIXES = ("客服:", "客服：", "卖家:", "卖家：", "我:", "我：")


class ConnectorUnavailable(RuntimeError):
    """无法从浏览器读取时抛出。调用方应改用粘贴。"""


def _strip_prefix(line: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def parse_pasted_chat(text: str) -> str:
    """识别「买家:」开头的行。没有角色前缀时，把整段文字当作买家消息。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    buyer_lines: list[str] = []
    saw_role = False
    for line in lines:
        buyer = _strip_prefix(line, BUYER_PREFIXES)
        if buyer is not None:
            saw_role = True
            if buyer:
                buyer_lines.append(buyer)
            continue
        if _strip_prefix(line, AGENT_PREFIXES) is not None:
            saw_role = True
    if not saw_role:
        message = text.strip()
    else:
        message = "\n".join(buyer_lines)
    if not message:
        raise ValueError("没有识别到买家消息")
    return message


class XianyuReadOnlyConnector:
    """闲鱼只读入口。没有 send 方法，不能替客服发出消息。"""

    def __init__(self, user_data_dir: str | None = None) -> None:
        self.user_data_dir = user_data_dir or None

    def read_buyer_messages(self) -> list[str]:
        if not self.user_data_dir:
            raise ConnectorUnavailable(
                "未配置 XIANYU_BROWSER_USER_DATA。请粘贴买家消息。系统不会自动发送消息。"
            )
        raise ConnectorUnavailable(
            "已忽略浏览器目录，当前不会打开闲鱼，也不会自动发送消息。请粘贴买家消息。"
        )
