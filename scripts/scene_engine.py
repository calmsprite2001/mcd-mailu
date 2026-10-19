#!/usr/bin/env python3
"""场景识别引擎。

设计原则：规则驱动，每一条标签都能说出「为什么」。
识别结果会附上 evidence（命中的订单号 + 触发依据），
叙事层必须引用这些 evidence，不许凭感觉写文案。

规则词典是可扩展的——这就是本项目的开源邀请：
references/scene_rules.md 里公开所有规则，欢迎 PR 补充。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from adapters import OrderRecord

# ---------- 场景词典 ----------

# 店名关键词 → 场景标签。匹配方式为「包含」，全小写比对。
STORE_KEYWORDS: dict[str, list[str]] = {
    "出行慰藉": ["机场", "火车站", "高铁站", "高铁", "gtc", "航站楼", "客运", "口岸", "候车"],
    "医院守护": ["医院", "妇幼", "人民医", "中医"],
    "校园日常": ["大学", "学院", "中学", "小学"],
    "写字楼补给": ["写字楼", "商务", "金融城", "产业园", "大厦"],
    "商圈逛吃": ["万象城", "万达", "吾悦", "银泰", "大悦城", "印象城", "天街"],
}

# 时段规则：(起, 止) 均为「分钟数」，止 < 起 表示跨午夜。
TIME_SCENES: dict[str, tuple[int, int]] = {
    "早班开场": (5 * 60, 10 * 60 + 30),
    "午间补充": (10 * 60 + 30, 14 * 60),
    "下午茶": (14 * 60, 17 * 60 + 30),
    "晚餐": (17 * 60 + 30, 21 * 60),
    "深夜补给": (21 * 60, 5 * 60),
}

BURST_WINDOW = timedelta(minutes=30)
REGULAR_THRESHOLD = 3


@dataclass
class Visit:
    """一次到访：同店 30 分钟内的连续订单合并成一次。

    在机场候机 12 分钟连点两单，是「1 次到访、2 个订单」，
    不是「去了 2 次机场」。门店多样性必须按到访算，否则会被连点污染。
    """

    store: str
    store_name: str
    start: object
    end: object
    orders: list[OrderRecord] = field(default_factory=list)


def build_visits(orders: list[OrderRecord]) -> list[Visit]:
    visits: list[Visit] = []
    for order in sorted(orders, key=lambda x: x.placed_at):
        key = order.store_code or order.store_name
        if visits and visits[-1].store == key and (order.placed_at - visits[-1].end) <= BURST_WINDOW:
            visits[-1].orders.append(order)
            visits[-1].end = order.placed_at
        else:
            visits.append(Visit(store=key, store_name=order.store_name, start=order.placed_at, end=order.placed_at, orders=[order]))
    return visits


@dataclass
class Tag:
    name: str
    evidence: str


@dataclass
class TaggedOrder:
    order: OrderRecord
    tags: list[Tag] = field(default_factory=list)


def _minutes_of_day(order: OrderRecord) -> int:
    return order.placed_at.hour * 60 + order.placed_at.minute


def tag_orders(orders: list[OrderRecord]) -> list[TaggedOrder]:
    """给每单打标签。标签分三类：店名场景、时段场景、关系场景。"""
    tagged = [TaggedOrder(order=o) for o in orders]

    # 1. 店名场景
    for entry in tagged:
        name = entry.order.store_name.lower()
        for scene, keywords in STORE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in name:
                    entry.tags.append(Tag(scene, f"店名含「{kw}」"))
                    break

    # 2. 时段场景（最多取一个，按优先级从早到晚取第一个命中）
    for entry in tagged:
        minute = _minutes_of_day(entry.order)
        for scene, (start, end) in TIME_SCENES.items():
            hit = start <= minute < end if start <= end else (minute >= start or minute < end)
            if hit:
                entry.tags.append(
                    Tag(scene, f"下单于 {entry.order.placed_at.strftime('%H:%M')}")
                )
                break

    # 3. 关系场景：连点 / 新店 / 老地方
    by_store_count: dict[str, int] = {}
    for i, entry in enumerate(tagged):
        store = entry.order.store_code or entry.order.store_name

        if i > 0:
            prev = tagged[i - 1].order
            prev_store = prev.store_code or prev.store_name
            gap = entry.order.placed_at - prev.placed_at
            if store == prev_store and timedelta(0) <= gap <= BURST_WINDOW:
                entry.tags.append(
                    Tag("一单多点", f"距上一单 {int(gap.total_seconds() // 60)} 分钟、同店")
                )

        count = by_store_count.get(store, 0)
        if count == 0:
            entry.tags.append(Tag("新店打卡", f"{entry.order.store_name} 首次出现"))
        elif count == REGULAR_THRESHOLD - 1:
            entry.tags.append(Tag("老地方", f"该店第 {count + 1} 次光顾"))
        by_store_count[store] = count + 1

    return tagged


# ---------- 模式识别 ----------

@dataclass
class Pattern:
    name: str
    hit: bool
    evidence: str
    metric: float = 0.0


def detect_patterns(tagged: list[TaggedOrder]) -> list[Pattern]:
    """从标签集合识别整单模式。未命中的也要返回，叙事层需要知道哪些没命中。

    门店多样性一律按「到访」统计（同店 30 分钟内连点合并），
    否则在机场连吃两单会被算成「去了两次机场」，污染画像。
    """
    total = len(tagged)
    if total == 0:
        return []

    orders = [t.order for t in tagged]
    visits = build_visits(orders)
    visit_count = len(visits)
    unique_ratio = len({v.store for v in visits}) / visit_count

    travel_orders = [t for t in tagged if any(x.name == "出行慰藉" for x in t.tags)]
    travel_count = len(travel_orders)
    travel_visits = sum(
        1 for v in visits if any(any(x.name == "出行慰藉" for x in t.tags) for t in tagged if t.order in v.orders)
    )
    morning_count = sum(1 for t in tagged if any(x.name == "早班开场" for x in t.tags))
    night_count = sum(1 for t in tagged if any(x.name == "深夜补给" for x in t.tags))

    visit_counts: dict[str, int] = {}
    top_store, top_count = "", 0
    for v in visits:
        visit_counts[v.store_name] = visit_counts.get(v.store_name, 0) + 1
        if visit_counts[v.store_name] > top_count:
            top_store, top_count = v.store_name, visit_counts[v.store_name]
    top_ratio = top_count / visit_count

    return [
        Pattern(
            "天涯路人",
            travel_visits / visit_count >= 0.15,
            f"{total} 单合并为 {visit_count} 次到访，其中 {travel_visits} 次在机场/车站",
            travel_visits / visit_count,
        ),
        Pattern(
            "本地日常",
            top_ratio >= 0.4,
            f"{top_ratio:.0%} 的到访都发生在「{top_store}」",
            top_ratio,
        ),
        Pattern(
            "早餐型",
            morning_count / total >= 0.4,
            f"{morning_count}/{total} 单在 10:30 前下单",
            morning_count / total,
        ),
        Pattern(
            "深夜型",
            night_count / total >= 0.25,
            f"{night_count}/{total} 单在 21:00 后下单",
            night_count / total,
        ),
    ]


def top_items(tagged: list[TaggedOrder], limit: int = 5) -> list[tuple[str, int]]:
    """最常点的单品（含套餐子项展开）。没有单价，只能数次数和份数。"""
    counter: dict[str, int] = {}
    for t in tagged:
        for item in t.order.items:
            if item.sub_items:
                for sub in item.sub_items:
                    counter[sub.name] = counter.get(sub.name, 0) + sub.quantity * item.quantity
            else:
                counter[item.name] = counter.get(item.name, 0) + item.quantity
    return sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
