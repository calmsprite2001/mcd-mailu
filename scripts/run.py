#!/usr/bin/env python3
"""麦途主流程。

用法：
    python scripts/run.py                 # 真实数据（需要 MCD_MCP_TOKEN）
    python scripts/run.py --demo          # 用内置演示样本，不需要 Token

输出：
    output/mailu_card.html    轨迹卡
    终端打印清洗报告（订单明细不落盘）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import CleanReport, from_mall_order_list, from_order_list  # noqa: E402
from card_render import render_card  # noqa: E402
from mcp_client import McdMcpClient, McpError  # noqa: E402
from narrative import build_story  # noqa: E402
from scene_engine import detect_patterns, tag_orders  # noqa: E402


def load_demo_payload() -> dict:
    fixture = ROOT / "fixtures" / "demo_orders.json"
    if not fixture.exists():
        raise SystemExit(f"演示数据不存在：{fixture}（先跑 python scripts/gen_fixture.py）")
    return json.loads(fixture.read_text(encoding="utf-8"))


def fetch_payload() -> dict:
    client = McdMcpClient()
    payload = client.call_json("order-list", {})
    # 商城订单也拉，只用于旁注统计，不混入餐费
    mall_payload = client.call_json("mall-order-list", {})
    return {"meal": payload, "mall": mall_payload}


def print_report(report: CleanReport, label: str) -> None:
    print(f"--- 清洗报告[{label}] ---")
    print(f"  拉取 {report.total_fetched} 条，保留 {report.kept} 条")
    if report.duplicates_removed:
        print(f"  去重移除 {report.duplicates_removed} 条")
    for status, count in report.dropped_by_status.items():
        print(f"  剔除[{status}] × {count}")
    for failure in report.parse_failures:
        print(f"  [解析失败] {failure}")
    for warning in report.amount_warnings:
        print(f"  [金额告警] {warning}")
    if not (report.duplicates_removed or report.dropped_by_status or report.parse_failures or report.amount_warnings):
        print("  无异常")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="麦途：把麦当劳历史订单读成一个故事")
    parser.add_argument("--demo", action="store_true", help="使用内置演示数据，不连 MCP")
    parser.add_argument(
        "--out",
        default="",
        help="输出路径，默认 demo/index.html（--demo）或 output/mailu_card.html",
    )
    args = parser.parse_args(argv[1:])

    if args.demo:
        payload = load_demo_payload()
        meal_payload = payload
        mall_count = 0
    else:
        raw = fetch_payload()
        meal_payload = raw["meal"]
        mall_records, mall_report = from_mall_order_list(raw["mall"])
        mall_count = mall_report.kept

    orders, report = from_order_list(meal_payload)
    print_report(report, "餐食订单")
    if not args.demo and mall_count:
        print(f"商城订单另计：{mall_count} 单（不混入餐费统计）")

    tagged = tag_orders(orders)
    patterns = detect_patterns(tagged)
    story = build_story(orders, tagged, patterns)

    print(f"\n叙事模式：{story.mode}")
    print(f"首屏结论：{story.headline}")

    if args.out:
        out = Path(args.out)
    elif args.demo:
        out = ROOT / "demo" / "index.html"
    else:
        out = ROOT / "output" / "mailu_card.html"
    path = render_card(story, tagged, out)
    print(f"\n卡片已生成：{path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except McpError as exc:
        print(f"[MCP 错误] {exc}", file=sys.stderr)
        raise SystemExit(1)
