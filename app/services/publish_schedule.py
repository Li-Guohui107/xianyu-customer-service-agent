"""算出今天到点该发的那一条，并把商品资料收成闲鱼表单。"""

from __future__ import annotations

import re
from datetime import datetime

from app.knowledge.store import Product
from app.services.risk import _seller_text

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
PRICE_RE = re.compile(r"\d+(?:\.\d{1,2})?")
MAX_SLOTS = 12
FORBIDDEN = ("包过", "保证及格", "保证录用", "代写论文", "代考", "替我交", "替我提交", "保分")


def normalize_time(value: str) -> str:
    text = value.strip()
    if TIME_RE.fullmatch(text) is None:
        raise ValueError("时间要写成 09:30 这种")
    return text


def normalize_copy(value: str, *, limit: int) -> str:
    """上架用的标题或描述。留空表示继续用每天自动写的那一版。"""
    text = value.replace("\r\n", "\n").strip()
    if not text:
        return ""
    if len(text) > limit:
        raise ValueError(f"文案最多 {limit} 个字")
    visible = _seller_text(text)
    if any(term in visible for term in FORBIDDEN):
        raise ValueError("这条文案里有不能发布的承诺")
    if "微信" in text:
        raise ValueError("上架文案里不能写微信号")
    return text


def normalize_price(value: str) -> str:
    """上架标价。留空表示用资料里的价格。"""
    text = value.strip().removesuffix("元").strip()
    if not text:
        return ""
    if PRICE_RE.fullmatch(text) is None:
        raise ValueError("价格要写成 500 这种")
    amount = float(text)
    if amount <= 0 or amount > 999999:
        raise ValueError("价格要写成 500 这种")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def due_slots(slots: list[dict], now: datetime, published_ids: set[str]) -> list[dict]:
    """到了设定时间、今天的定时还没发成功的条目。没到点的不发。"""
    now_minutes = now.hour * 60 + now.minute
    ready: list[dict] = []
    for slot in slots:
        if not slot.get("enabled", True):
            continue
        if slot["slot_id"] in published_ids:
            continue
        hour, minute = (int(part) for part in slot["time"].split(":"))
        if now_minutes >= hour * 60 + minute:
            ready.append(slot)
    return ready


def parse_samples(text: str) -> list[dict]:
    """空行隔开多条旧文案。第一条是标题，剩下的是描述。"""
    samples = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0][:30]
        body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
        samples.append({"title": title, "body": body[:500]})
    if len(samples) > 20:
        raise ValueError("旧文案最多贴 20 条")
    return samples


def samples_to_text(samples: list[dict]) -> str:
    blocks = []
    for sample in samples:
        body = sample["body"].strip()
        title = sample["title"].strip()
        blocks.append(title if body == title else f"{title}\n{body}")
    return "\n\n".join(blocks)


def _public_name(title: str) -> str:
    name = title.replace("演示用", "").strip()
    return name or title.strip()


def _choice(options: list[str], when: datetime | None, slot_id: str) -> str:
    if not options:
        return ""
    day = when.date().toordinal() if when else 0
    extra = sum(ord(char) for char in slot_id)
    return options[(day + extra) % len(options)]


def _safe_sample_lines(samples: list[dict] | None) -> list[str]:
    lines: list[str] = []
    for sample in samples or []:
        for raw in sample.get("body", "").splitlines():
            line = raw.strip(" 。")
            if len(line) < 4 or "微信" in line or "元" in line:
                continue
            if any(term in _seller_text(line) for term in FORBIDDEN):
                continue
            if line not in lines:
                lines.append(line)
    return lines


def listing_from_product(
    product: Product,
    *,
    when: datetime | None = None,
    slot_id: str = "",
    samples: list[dict] | None = None,
    price: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    """按旧文案的口气写一版。同一天同一条保持不变，换一天就换说法。

    标题或描述若是用户改过的，就用用户写的，不再换说法。
    """
    custom_title = normalize_copy(title or "", limit=30)
    custom_description = normalize_copy(description or "", limit=800)
    chosen = normalize_price(price or "")
    if not chosen:
        match = PRICE_RE.search(product.price or "")
        if match is None:
            raise ValueError("这个服务没有标价，不能发到闲鱼")
        chosen = match.group(0)
    name = _public_name(product.title)
    titles = [
        name,
        f"接{name}",
        f"{name}，按需求做",
        f"{name}，远程交付",
    ]
    for sample in samples or []:
        sample_title = sample.get("title", "").strip()
        if sample_title and any(keyword and keyword in sample_title for keyword in product.keywords):
            titles.append(sample_title[:30])
    title = custom_title or _choice(titles, when, slot_id)[:30]
    clauses = [
        part.strip("。")
        for part in (product.condition, product.ship_time, product.shipping, product.defects)
        if part and part.strip()
    ]
    if clauses:
        start = (when.date().toordinal() + sum(ord(char) for char in slot_id)) % len(clauses) if when else 0
        clauses = clauses[start:] + clauses[:start]
    extra = _choice(_safe_sample_lines(samples), when, slot_id + "x")
    if extra and extra not in "。".join(clauses):
        clauses.append(extra)
    description = "。".join(clauses)
    if description and not description.endswith("。"):
        description += "。"
    if custom_description:
        description = custom_description
    visible = _seller_text(f"{title}\n{description}")
    if any(term in visible for term in FORBIDDEN):
        raise ValueError("这条资料里有不能发布的承诺")
    if "微信" in visible:
        raise ValueError("上架文案里不能写微信号")
    return {
        "title": title,
        "description": description,
        "price": chosen,
        "product_id": product.product_id,
    }
