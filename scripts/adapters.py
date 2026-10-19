#!/usr/bin/env python3
"""把麦当劳 MCP 返回的原始结构适配成内部 OrderRecord。

字段契约来自 2026-10-18 对 order-list / mall-order-list 的实测，
原始结构存档见 raw/*.raw.json（已被 .gitignore 排除）。
接口结构一旦变化，只需改这一个文件。

order-list 实测要点（写死，勿改）：
- 无分页参数，一次返回全量历史
- realTotalAmount 是字符串、单位「元」，如 "11.9"、"38"
- orderStatus 为中文文本，如「订单已完成」
- orderProductList[].comboItemList[] 是套餐子项，子项没有价格
- 明细里没有单品单价，只有订单总额
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from money import flag_suspicious, parse_time

DONE_STATUS = {"订单已完成", "已完成", "交易完成", "已取餐", "已完成订单"}


@dataclass
class SubItem:
    name: str
    quantity: int = 1


@dataclass
class Item:
    name: str
    quantity: int = 1
    product_code: str = ""
    sub_items: list[SubItem] = field(default_factory=list)


@dataclass
class OrderRecord:
    order_id: str
    placed_at: datetime
    order_type: str
    status: str
    store_name: str
    store_code: str
    total_yuan: float
    items: list[Item] = field(default_factory=list)


@dataclass
class CleanReport:
    total_fetched: int = 0
    kept: int = 0
    dropped_by_status: dict[str, int] = field(default_factory=dict)
    duplicates_removed: int = 0
    parse_failures: list[str] = field(default_factory=list)
    amount_warnings: list[str] = field(default_factory=list)


def from_order_list(payload: dict[str, Any]) -> tuple[list[OrderRecord], CleanReport]:
    """把 order-list 的返回清洗成订单列表。"""
    report = CleanReport()
    rows = (payload or {}).get("data", {}).get("list", []) or []
    report.total_fetched = len(rows)

    records: list[OrderRecord] = []
    seen: set[str] = set()

    for row in rows:
        order_id = str(row.get("orderId") or "").strip()
        if not order_id:
            report.parse_failures.append("缺 orderId，跳过一条")
            continue
        if order_id in seen:
            report.duplicates_removed += 1
            continue
        seen.add(order_id)

        status = str(row.get("orderStatus") or "").strip()
        if status not in DONE_STATUS:
            report.dropped_by_status[status or "未知状态"] = (
                report.dropped_by_status.get(status or "未知状态", 0) + 1
            )
            continue

        try:
            placed_at = parse_time(row.get("createTime"))
        except ValueError as exc:
            report.parse_failures.append(f"订单 {order_id} 时间解析失败：{exc}")
            continue

        amount_raw = row.get("realTotalAmount")
        try:
            total_yuan = float(str(amount_raw).replace(",", "").strip())
        except (TypeError, ValueError):
            report.parse_failures.append(f"订单 {order_id} 金额「{amount_raw}」不是数字")
            continue
        for warning in flag_suspicious(amount_raw, "元"):
            report.amount_warnings.append(f"订单 {order_id}：{warning}")

        items: list[Item] = []
        for product in row.get("orderProductList") or []:
            sub_items = [
                SubItem(name=str(s.get("name") or "").strip(), quantity=int(s.get("quantity") or 1))
                for s in product.get("comboItemList") or []
            ]
            items.append(
                Item(
                    name=str(product.get("productName") or "").strip(),
                    quantity=int(product.get("quantity") or 1),
                    product_code=str(product.get("productCode") or ""),
                    sub_items=sub_items,
                )
            )

        records.append(
            OrderRecord(
                order_id=order_id,
                placed_at=placed_at,
                order_type=str(row.get("orderType") or ""),
                status=status,
                store_name=str(row.get("storeName") or "").strip(),
                store_code=str(row.get("storeCode") or "").strip(),
                total_yuan=total_yuan,
                items=items,
            )
        )

    records.sort(key=lambda r: r.placed_at)
    report.kept = len(records)
    return records, report


def from_mall_order_list(payload: dict[str, Any]) -> tuple[list[dict], CleanReport]:
    """商城订单单独解析，仅做汇总计数，不混入餐费。

    mall-order-list 返回结构：data 为数组，每页含 hasNext / lastId / list。
    这里只做归集，字段明细留待有更多真实数据时补充。
    """
    report = CleanReport()
    records: list[dict] = []
    pages = (payload or {}).get("data") or []
    if isinstance(pages, dict):
        pages = [pages]
    for page in pages:
        for row in page.get("list") or []:
            records.append(row)
    report.total_fetched = len(records)
    report.kept = len(records)
    return records, report
