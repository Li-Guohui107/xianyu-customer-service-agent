"""按闲鱼常见问法组织可复制的回复。只使用商品资料里的事实。"""

from __future__ import annotations

import re

from app.knowledge.store import Product

INTENT_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("offsite", "站外交易", ("微信", "威信", "加微", "vx", "v信", "私下", "站外", "转账", "扫码付")),
    ("academic", "超范围要求", ("代写论文", "包过", "保分", "保证及格", "代考", "替我交", "替我提交")),
    ("refund", "退款售后", ("退款", "退货", "投诉", "差评", "举报")),
    ("bargain", "议价", ("便宜", "少点", "优惠", "小刀", "刀一", "最低", "能出", "能卖")),
    ("shipping", "交付", ("包邮", "运费", "邮费", "快递费", "怎么发", "传文件", "网盘")),
    ("deadline", "周期", ("多久", "几天", "周期", "什么时候好", "交付时间")),
    ("scope", "交付内容", ("包含", "交付内容", "注释", "环境", "报告")),
    ("stack", "技术栈", ("框架", "技术栈", "用什么写", "什么语言", "用什么技术", "哪种技术")),
    ("price", "价格", ("多少钱", "价格", "怎么卖", "多钱")),
    ("availability", "接单", ("还在", "还接", "有货", "在吗", "有空", "接单")),
    ("greeting", "打招呼", ("你好", "在么", "hi", "hello")),
)


def detect_intents(buyer_message: str) -> list[tuple[str, str]]:
    lowered = buyer_message.lower()
    found: list[tuple[str, str]] = []
    for code, label, terms in INTENT_RULES:
        if any(term in lowered for term in terms):
            found.append((code, label))
    if extract_offer(buyer_message) is not None and all(code != "bargain" for code, _label in found):
        found.insert(0, ("bargain", "议价"))
    if not found:
        found.append(("general", "综合咨询"))
    return found


def intent_label(buyer_message: str) -> str:
    return "、".join(label for _code, label in detect_intents(buyer_message))


def extract_offer(buyer_message: str) -> int | None:
    match = re.search(r"(\d{2,5})\s*(?:元|块|块钱)?", buyer_message)
    if match is None:
        return None
    if any(word in buyer_message for word in ("便宜", "少", "刀", "优惠", "最低", "出", "卖", "行", "可以", "做")):
        return int(match.group(1))
    return None


def _yuan(text: str) -> int | None:
    match = re.search(r"(\d+)", text or "")
    if match is None:
        return None
    return int(match.group(1))


def below_floor_reason(buyer_message: str, product: Product | None) -> str | None:
    if product is None:
        return None
    offer = extract_offer(buyer_message)
    floor = _yuan(product.floor_price)
    if offer is None or floor is None or offer >= floor:
        return None
    return f"买家出价{offer}元，低于最低价{product.floor_price}，需要人工决定"


_AMOUNT = re.compile(r"\d+\s*(?:元|块钱|块)")
_TECH_NAME = re.compile(
    r"pytorch|tensorflow|keras|sklearn|scikit-learn|pandas|numpy|scipy|jax|paddlepaddle|paddle|mindspore|huggingface|transformers|opencv|yolo|bert|langchain|django|flask|fastapi|python|java|golang|rust|c\+\+",
    re.IGNORECASE,
)


def price_talk(wechat_id: str) -> str:
    """问价格时不报金额，只把对方引到微信。"""
    wechat_id = wechat_id.strip()
    if wechat_id:
        return f"价格微信详谈，微信号 {wechat_id}。"
    return "价格微信详谈。"


def knowledge_without_prices(knowledge_text: str, wechat_id: str) -> str:
    """模型看到的资料里去掉金额，避免它把价格复述给买家。"""
    if knowledge_text.startswith("没有查到该商品"):
        return knowledge_text
    kept = [
        line
        for line in knowledge_text.splitlines()
        if not line.startswith(("价格：", "最低价：", "议价：", "技术栈："))
    ]
    kept.append("价格：不要报任何金额，让买家加微信详谈。")
    kept.append("技术：不要主动提技术栈或库名。买家指定了技术，就按买家的技术做，不要改成固定技术。")
    wechat_id = wechat_id.strip()
    kept.append(f"微信号：{wechat_id}" if wechat_id else "微信号：不要编造。")
    return "\n".join(kept)


def named_technologies(text: str) -> list[str]:
    """买家原话里点名的技术，保留买家自己的写法。"""
    found: list[str] = []
    seen: set[str] = set()
    for match in _TECH_NAME.finditer(text or ""):
        name = match.group(0)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    return found


def _tidy_fragment(text: str) -> str:
    text = re.sub(r"技术栈[是用为：:\s]*", "", text)
    text = re.sub(r"[、，,]{2,}", "，", text)
    text = re.sub(r"(?:用|是|和|跟|以及)[、，,\s]*(?=[。！？]|$)", "", text)
    text = re.sub(r"[、，,\s]+(?=[。！？])", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ，,、")


def without_unsolicited_stack(reply: str, buyer_message: str, product: Product | None) -> str:
    """买家没问技术时去掉固定技术栈；买家指定了技术就按买家的来。"""
    if product is None or not reply:
        return reply
    named = named_technologies(buyer_message)
    asks = any(code == "stack" for code, _label in detect_intents(buyer_message))
    removable = [
        point
        for point in product.selling_points
        if point and point.lower() not in buyer_message.lower()
    ]
    if asks or named:
        text = reply
        for point in removable:
            text = re.sub(re.escape(point), "", text, flags=re.IGNORECASE)
        text = _tidy_fragment(text)
        if named and not any(name.lower() in text.lower() for name in named):
            return f"可以，按{'、'.join(named)}来做。"
        return text or (f"可以，按{'、'.join(named)}来做。" if named else "你需要哪种技术，我按那种做。")
    if not removable and "技术栈" not in reply:
        return reply
    pieces = re.split(r"(?<=[。！？\n])", reply)
    kept: list[str] = []
    for piece in pieces:
        lowered = piece.lower()
        if "技术栈" not in piece and not any(point.lower() in lowered for point in removable):
            kept.append(piece)
            continue
        cut = piece
        for marker in ("技术栈", "，用", ",用"):
            index = cut.find(marker)
            if index != -1:
                cut = cut[:index]
                break
        else:
            for point in removable:
                cut = re.sub(re.escape(point), "", cut, flags=re.IGNORECASE)
        cut = _tidy_fragment(cut)
        if not cut:
            continue
        if cut[-1] not in "。！？\n":
            cut += "。"
        kept.append(cut)
    return "".join(kept).strip() or "在的。"


def history_without_fixed_stack(history: list[dict] | None, product: Product | None) -> list[dict]:
    """历史草稿里的固定技术栈不再传给模型，避免下一句跟着说。"""
    if not history:
        return []
    buyer_text = "\n".join(
        str(item.get("content", "")) for item in history if item.get("role") != "assistant"
    )
    cleaned: list[dict] = []
    for item in history:
        content = str(item.get("content", ""))
        if item.get("role") == "assistant":
            content = without_unsolicited_stack(content, buyer_text, product)
        cleaned.append({**item, "content": content})
    return cleaned


def without_quoted_prices(reply: str, wechat_id: str) -> str:
    """草稿里如果还是出现了金额，就删掉金额并补上微信详谈。"""
    if not _AMOUNT.search(reply):
        return reply
    text = _AMOUNT.sub("", reply)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"[，,]\s*([。！？])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ，,")
    talk = price_talk(wechat_id)
    if "微信" not in text:
        text = f"{text}\n{talk}".strip() if text else talk
    return text


def _sentences(buyer_message: str, product: Product, wechat_id: str) -> list[str]:
    codes = {code for code, _label in detect_intents(buyer_message)}
    lowered = buyer_message.lower()
    asks_wechat = any(term in lowered for term in ("微信", "威信", "加微", "vx", "v信"))
    parts: list[str] = []
    if "offsite" in codes:
        parts.append("下单留在闲鱼，转账不行。")
    if "academic" in codes:
        parts.append("代码和说明可以做。论文正文、考试、替交和成绩承诺都不能做。")
    if "refund" in codes:
        parts.append("退款走闲鱼订单，聊天里我不能直接答应。")
    if "academic" not in codes and ("price" in codes or "bargain" in codes or asks_wechat):
        parts.append(price_talk(wechat_id))
    if "shipping" in codes:
        shipping = product.shipping or "资料未写"
        parts.append(f"{shipping}。" if shipping != "资料未写" else "怎么发资料里没写，我确认后再告诉你。")
    if "deadline" in codes:
        parts.append(f"{product.ship_time or '周期资料里没写，我确认后再告诉你'}。")
    if "scope" in codes:
        missing = product.defects or "资料未写"
        parts.append(f"给你{product.condition}。不含{missing}。")
    named = named_technologies(buyer_message)
    if "stack" in codes or named:
        parts.append(f"可以，按{'、'.join(named)}来做。" if named else "你需要哪种技术，我按那种做。")
    if "availability" in codes or ("general" in codes and not named):
        parts.append(f"在的，给你{product.condition}。")
    elif "greeting" in codes and len(codes) == 1:
        parts.append("在的，直接问就行。")
    return parts


def compose_reply(buyer_message: str, product: Product | None, wechat_id: str = "") -> str:
    """生成给买家看的短回复，不写内部审核说明。"""
    if product is None:
        return "没有查到该商品。你说下是哪个服务，我再回你。"
    reply = "\n".join(_sentences(buyer_message, product, wechat_id)).strip()
    return reply or f"在的，给你{product.condition}。"
