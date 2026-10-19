#!/usr/bin/env python3
"""叙事生成器。

每个句子都由规则触发、用真实数字填充，并附带 evidence（订单依据）。
轨迹模式（样本 <10 单）：按时间讲每一次，不装统计。
画像模式（样本 ≥10 单）：统计结论，比率带分母。

红线：数据里没有的餐品、场景、情绪，一个字都不写。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adapters import OrderRecord
from scene_engine import Pattern, TaggedOrder, top_items

MIN_SAMPLE_FOR_PROFILE = 10


@dataclass
class StoryLine:
    text: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Story:
    mode: str  # "轨迹" | "画像"
    headline: str
    subline: str
    lines: list[StoryLine]
    patterns: list[Pattern]


def _months_span(orders: list[OrderRecord]) -> int:
    if len(orders) < 2:
        return 1
    days = (orders[-1].placed_at - orders[0].placed_at).days
    return max(1, round(days / 30))


def _scene_count(tagged: list[TaggedOrder], scene: str) -> int:
    return sum(1 for t in tagged if any(x.name == scene for x in t.tags))


def _fmt_amount(value: float) -> str:
    return f"¥{value:g}"


def _headline_track(tagged: list[TaggedOrder], orders: list[OrderRecord]) -> str:
    """轨迹模式首屏句。"""
    months = _months_span(orders)
    total = len(orders)
    travel = _scene_count(tagged, "出行慰藉")
    if travel > 0:
        return f"{months} 个月里你吃了 {total} 次麦当劳——{travel} 次都在路上。"
    morning = _scene_count(tagged, "早班开场")
    if morning > 0:
        return f"{months} 个月里你吃了 {total} 次麦当劳——大多在清晨。"
    return f"{months} 个月里你吃了 {total} 次麦当劳。"


def _headline_profile(tagged: list[TaggedOrder], orders: list[OrderRecord], patterns: list[Pattern]) -> str:
    """画像模式首屏句：优先取命中的第一个模式；都没命中时用频次 + 主导时段。"""
    total = len(orders)
    months = _months_span(orders)
    hit = next((p for p in patterns if p.hit), None)
    if hit and hit.name == "天涯路人":
        return f"{months} 个月，{total} 次，你是天涯路人。"
    if hit and hit.name == "本地日常":
        return f"{months} 个月，{total} 次，你有自己的老地方。"
    if hit and hit.name == "早餐型":
        return f"{months} 个月，{total} 次，你的一天从麦当劳开始。"
    if hit and hit.name == "深夜型":
        return f"{months} 个月，{total} 次，你的深夜有人间烟火。"

    weekly = total / (months * 4.345)
    slot_short = {
        "早班开场": "清晨",
        "午间补充": "午间",
        "下午茶": "下午",
        "晚餐": "傍晚",
        "深夜补给": "深夜",
    }
    counts: dict[str, int] = {}
    for t in tagged:
        for tag in t.tags:
            if tag.name in slot_short:
                counts[tag.name] = counts.get(tag.name, 0) + 1
    dominant = slot_short[max(counts, key=counts.get)] if counts else "白天"
    return f"{months} 个月，{total} 次，平均每周 {weekly:.1f} 次——大多在{dominant}。"


def _track_lines(tagged: list[TaggedOrder]) -> list[StoryLine]:
    """轨迹模式：按时间顺序讲每一次。"""
    lines: list[StoryLine] = []
    for entry in tagged:
        order = entry.order
        scene_names = [t.name for t in entry.tags if t.name not in {"新店打卡", "老地方"}]
        scene_text = f"（{'、'.join(scene_names)}）" if scene_names else ""
        item_names = "、".join(i.name for i in order.items if i.name)
        text = (
            f"{order.placed_at.strftime('%Y-%m-%d %H:%M')}，{order.store_name}，"
            f"{_fmt_amount(order.total_yuan)}：{item_names}{scene_text}"
        )
        evidence = [t.evidence for t in entry.tags]
        lines.append(StoryLine(text, [order.order_id] + evidence))

    bursts = [t for t in tagged if any(x.name == "一单多点" for x in t.tags)]
    if bursts:
        first = bursts[0]
        gap = next(x.evidence for x in first.tags if x.name == "一单多点")
        lines.append(
            StoryLine(
                f"最拼的一次：{first.order.placed_at.strftime('%Y-%m-%d')}，{gap}，连吃两单。",
                [first.order.order_id, gap],
            )
        )
    return lines


def _profile_lines(tagged: list[TaggedOrder], orders: list[OrderRecord]) -> list[StoryLine]:
    """画像模式：统计结论，全部带分母。"""
    total = len(orders)
    total_amount = sum(o.total_yuan for o in orders)
    avg = total_amount / total if total else 0.0
    stores = {o.store_name for o in orders}

    lines = [
        StoryLine(
            f"{total} 单，共 {_fmt_amount(total_amount)}，平均每单 {_fmt_amount(round(avg, 1))}。",
            [o.order_id for o in orders],
        ),
        StoryLine(f"去过 {len(stores)} 家不同的店。", [o.store_code for o in orders]),
    ]

    travel = _scene_count(tagged, "出行慰藉")
    if travel:
        lines.append(
            StoryLine(
                f"{travel}/{total} 单在机场或火车站——这些地方从不是你的目的地。",
                [t.order.order_id for t in tagged if any(x.name == "出行慰藉" for x in t.tags)],
            )
        )

    morning = _scene_count(tagged, "早班开场")
    if morning:
        lines.append(
            StoryLine(
                f"{morning}/{total} 单在 10:30 前下单，你的一天开始得比多数人早。",
                [t.order.order_id for t in tagged if any(x.name == "早班开场" for x in t.tags)],
            )
        )

    items = top_items(tagged, limit=3)
    if items:
        top3 = "、".join(f"{name}×{qty}" for name, qty in items)
        lines.append(StoryLine(f"点得最多的三样：{top3}。", [t.order.order_id for t in tagged]))

    return lines


def build_story(orders: list[OrderRecord], tagged: list[TaggedOrder], patterns: list[Pattern]) -> Story:
    if not orders:
        return Story(
            mode="轨迹",
            headline="还没有数据",
            subline="",
            lines=[StoryLine("没有读到已完成订单，麦途暂时讲不了故事。", [])],
            patterns=patterns,
        )

    months = _months_span(orders)
    total = len(orders)
    span = f"{orders[0].placed_at.strftime('%Y-%m-%d')} — {orders[-1].placed_at.strftime('%Y-%m-%d')}"
    subline = f"近 {months} 个月 · {total} 单 · {span}"

    if total < MIN_SAMPLE_FOR_PROFILE:
        return Story(
            mode="轨迹",
            headline=_headline_track(tagged, orders),
            subline=subline,
            lines=_track_lines(tagged),
            patterns=patterns,
        )
    return Story(
        mode="画像",
        headline=_headline_profile(tagged, orders, patterns),
        subline=subline,
        lines=_profile_lines(tagged, orders),
        patterns=patterns,
    )
