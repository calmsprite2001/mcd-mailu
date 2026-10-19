#!/usr/bin/env python3
"""生成演示数据：一个虚构的重度用户「阿麦」的 80 单历史。

输出结构与 order-list 的真实返回完全一致（data.list[]），
所以演示数据和真实数据走的是同一条清洗-识别-叙事链路，
不会出现「demo 好看、真跑拉胯」的货不对板。

数据全部为人工构造：人物虚构、订单虚构、门店为通用命名风格。
商品名采用麦当劳在售餐品的公开名称。

seed 固定为 1024（程序员节），任何人重跑结果一致。
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 1024
OUT = Path(__file__).resolve().parent.parent / "fixtures" / "demo_orders.json"

BREAKFAST_MENU = [
    ("猪柳蛋麦满分组合", 15.0, ["猪柳蛋麦满分", "鲜煮咖啡"]),
    ("吉士蛋麦满分组合", 12.5, ["吉士蛋麦满分", "豆浆"]),
    ("大脆鸡扒麦满分组合", 16.0, ["大脆鸡扒麦满分", "鲜煮咖啡"]),
    ("北非蛋风味猪柳蛋麦满分组合", 25.0, ["北非蛋风味猪柳蛋麦满分", "鲜煮咖啡"]),
    ("芝芝火腿扒堡组合", 11.9, ["芝芝火腿扒堡", "豆浆"]),
    ("脆薯饼", 6.5, ["脆薯饼"]),
    ("皮蛋瘦肉粥", 8.0, ["皮蛋瘦肉粥"]),
]

MEAL_MENU = [
    ("巨无霸套餐", 33.5, ["巨无霸", "中薯条", "中可乐"]),
    ("麦辣鸡腿堡套餐", 31.0, ["麦辣鸡腿堡", "中薯条", "中可乐"]),
    ("板烧鸡腿堡套餐", 34.0, ["板烧鸡腿堡", "中薯条", "中可乐"]),
    ("双层吉士汉堡套餐", 30.0, ["双层吉士汉堡", "中薯条", "中雪碧"]),
    ("安格斯厚牛堡套餐", 45.0, ["安格斯厚牛堡", "中薯条", "中可乐"]),
    ("麦香鱼套餐", 29.5, ["麦香鱼", "玉米杯", "中雪碧"]),
    ("麦乐鸡10块", 22.0, ["麦乐鸡"]),
    ("中薯条", 13.0, ["中薯条"]),
    ("麦旋风", 12.0, ["麦旋风"]),
    ("香芋派", 7.0, ["香芋派"]),
    ("菠萝派", 7.0, ["菠萝派"]),
]

# (门店名, 权重, 场景类型)。权重决定被抽中的概率。
STORES = [
    ("麦当劳成都天府三街新希望国际餐厅", 0.32, "office"),
    ("麦当劳成都银泰城餐厅", 0.14, "mall"),
    ("麦当劳成都春熙路餐厅", 0.08, "mall"),
    ("麦当劳成都天府机场GTC餐厅", 0.10, "airport"),
    ("麦当劳成都东站候车厅餐厅", 0.06, "railway"),
    ("麦当劳重庆江北机场T3航站楼餐厅", 0.05, "airport"),
    ("麦当劳深圳北站餐厅", 0.04, "railway"),
    ("麦当劳上海虹桥火车站餐厅", 0.03, "railway"),
    ("麦当劳成都高新区环球中心餐厅", 0.10, "office"),
    ("麦当劳成都玉林生活广场餐厅", 0.08, "mall"),
]

# 时段：(起小时, 止小时, 权重, 菜单类型)
SLOTS = [
    (7, 9, 0.42, "breakfast"),
    (11, 13, 0.30, "meal"),
    (14, 16, 0.08, "snack"),
    (17, 19, 0.12, "meal"),
    (21, 23, 0.08, "snack"),
]


def _weighted_choice(rng: random.Random, options: list, weights: list[float]):
    return rng.choices(options, weights=weights, k=1)[0]


def _make_product(rng: random.Random, name: str, price: float, subs: list[str], serial: int) -> dict:
    return {
        "productCode": f"99{serial:08d}",
        "productName": name,
        "quantity": 1,
        "comboItemList": [
            {"productCode": f"52{serial:04d}{i}", "name": s, "quantity": 1}
            for i, s in enumerate(subs)
        ]
        if len(subs) > 1
        else [],
    }


def generate() -> dict:
    rng = random.Random(SEED)
    orders: list[dict] = []
    end = datetime(2026, 10, 18, 12, 0, 0)
    start = end - timedelta(days=200)

    serial = 0
    for _ in range(80):
        serial += 1
        store_name, _, store_kind = _weighted_choice(rng, STORES, [s[1] for s in STORES])
        slot = _weighted_choice(rng, SLOTS, [s[2] for s in SLOTS])

        day = start + timedelta(days=rng.randint(0, 199))
        # 机场/高铁站门店优先落到清晨或傍晚，符合赶车赶飞机的真实节奏
        if store_kind in {"airport", "railway"}:
            hour = rng.choice([6, 7, 8, 17, 18, 19])
            minute = rng.randint(0, 59)
        else:
            hour = rng.randint(slot[0], slot[1])
            minute = rng.randint(0, 59)
        placed = day.replace(hour=hour, minute=minute, second=rng.randint(0, 59))

        menu = BREAKFAST_MENU if slot[3] == "breakfast" and hour < 10 else MEAL_MENU
        name, price, subs = _weighted_choice(rng, menu, [1.0] * len(menu))
        if store_kind in {"airport", "railway"}:
            price = round(price * rng.uniform(1.15, 1.4), 1)

        products = [_make_product(rng, name, price, subs, serial)]
        total = price

        # 机场/车站 30% 概率 15 分钟内连点一单甜品——候机时再补一口甜的
        if store_kind in {"airport", "railway"} and rng.random() < 0.35:
            serial += 1
            extra_name, extra_price, extra_subs = _weighted_choice(
                rng,
                [m for m in MEAL_MENU if "派" in m[0] or "麦旋风" in m[0]],
                [1.0, 1.0, 1.0],
            )
            orders.append(
                _order(serial, store_name, placed, [ _make_product(rng, name, price, subs, serial) ], price)
            )
            serial += 1
            follow = placed + timedelta(minutes=rng.randint(8, 22))
            orders.append(
                _order(serial, store_name, follow, [_make_product(rng, extra_name, extra_price, extra_subs, serial)], extra_price)
            )
            continue

        orders.append(_order(serial, store_name, placed, products, total))

    orders.sort(key=lambda o: o["createTime"], reverse=True)
    return {"success": True, "code": 200, "message": "请求成功", "data": {"list": orders}}


def _order(serial: int, store_name: str, placed: datetime, products: list[dict], total: float) -> dict:
    return {
        "orderId": f"DEMO{serial:016d}",
        "orderType": "1",
        "createTime": placed.strftime("%Y-%m-%d %H:%M:%S"),
        "beType": "1",
        "beCode": "",
        "storeCode": str(abs(hash(store_name)) % 10_000_000),
        "storeName": store_name,
        "orderStatus": "订单已完成",
        "orderProductList": products,
        "realTotalAmount": f"{total:g}",
    }


def main() -> int:
    payload = generate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    count = len(payload["data"]["list"])
    first = payload["data"]["list"][-1]["createTime"]
    last = payload["data"]["list"][0]["createTime"]
    print(f"已生成 {count} 单演示数据（{first} — {last}）→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
