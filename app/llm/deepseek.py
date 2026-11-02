"""DeepSeek 聊天接口。测试注入假 HTTP 客户端，不发起真实请求。"""

from __future__ import annotations

from typing import Any

import httpx

SYSTEM_PROMPT = (
    "你是闲鱼上卖代码复现、机器学习、深度学习和 Python 脚本的客服。"
    "像卖家本人打字：口语、短，通常一句，最多两句。"
    "只答买家这一句问的事。打招呼就回「在的」，不要顺带报价格、内容和周期。"
    "不要用「周期：」「交付内容：」「标价」「卖点」这种标签，也不要复述商品标题。"
    "只根据提供的服务资料和对话回答。"
    "交付内容、周期和交付方式，只能使用资料里的原话。"
    "不要主动提技术栈、框架或库名。买家没问技术、也没指定技术时，回复里不要出现这些。"
    "买家指定了技术，就按买家说的来做，不要改成别的固定技术。"
    "资料里没有的信息要直接说不清楚，不要编造。"
    "买家问价格、优惠、最低价或出价时，不要回复任何金额，也不要说能不能便宜。"
    "这种情况只说价格微信详谈，并原样给出资料里的微信号。没有微信号就不要编造。"
    "可以做可运行代码和说明，不能代写论文正文，不能包过、保分、代考或替买家提交。"
    "退款和投诉不要答应。不要答应私下转账或扫码付款，下单留在闲鱼。"
    "只输出能直接发给买家的话，不要写审核说明，也不要说已经发送。"
)


class LLMError(RuntimeError):
    """模型调用失败。错误信息里不包含密钥。"""


class DeepSeekReplyGenerator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
        client: Any | None = None,
        wechat_id: str = "",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client
        self.wechat_id = wechat_id.strip()

    def generate(
        self,
        buyer_message: str,
        knowledge_text: str,
        history: list[dict] | None = None,
    ) -> str:
        system = SYSTEM_PROMPT
        if self.wechat_id:
            system += f"问价格时只给出这个微信号：{self.wechat_id}。"
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for item in history or []:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            role = "assistant" if item.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": f"商品资料：\n{knowledge_text}\n\n买家消息：\n{buyer_message}",
            }
        )
        http = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = http.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "max_tokens": 120},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek 调用失败") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("DeepSeek 没有返回草稿")
        return content.strip()
