#!/usr/bin/env python3
"""金额与时间字段的归一化工具。

麦当劳数据里「元」和「分」混用是踩坑率最高的一处：
商品价常是「元」（58 表示 ¥58），而场次/服务类价格常是「分」（5800 表示 ¥58）。
一个静默的 100 倍误差比一个明确的报错危险得多，所以这里的策略是：
单位必须显式声明，量级可疑只报警、不自动改数。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

CENT_UNITS = {"cent", "cents", "分", "fen", "penny"}
YUAN_UNITS = {"yuan", "rmb", "cny", "元", "块"}

CN_TZ = timezone(timedelta(hours=8))


class UnitAmbiguity(ValueError):
    """金额单位不明确，拒绝计算。"""


class TimeParseError(ValueError):
    """时间字段无法解析。"""


# ---------- 金额 ----------

def to_yuan(amount, unit: str | None) -> float:
    """把金额换成元。单位必须显式给出，不做猜测。"""
    if amount is None or amount == "":
        raise UnitAmbiguity("金额为空，无法换算")
    if isinstance(amount, str):
        cleaned = amount.replace(",", "").replace("¥", "").replace("￥", "").strip()
        if not cleaned:
            raise UnitAmbiguity(f"金额「{amount}」清洗后为空")
        try:
            value = float(cleaned)
        except ValueError as exc:
            raise UnitAmbiguity(f"金额「{amount}」不是数字") from exc
    else:
        value = float(amount)

    normalized = (unit or "").strip().lower()
    if normalized in CENT_UNITS:
        return value / 100.0
    if normalized in YUAN_UNITS:
        return value
    raise UnitAmbiguity(f"未知金额单位「{unit}」，请显式声明是元还是分")


def flag_suspicious(amount, claimed_unit: str | None) -> list[str]:
    """给可疑金额打标记，不改数。

    规则：标称「元」但数值 ≥500 且是整数时，很可能实际以分为单位。
    返回告警文案列表，空列表表示无疑点。
    """
    warnings: list[str] = []
    if amount is None:
        return warnings
    try:
        num = float(str(amount).replace(",", "").replace("¥", "").replace("￥", "").strip())
    except (TypeError, ValueError):
        return [f"金额「{amount}」不是数字"]
    if (claimed_unit or "").strip().lower() in YUAN_UNITS and num >= 500 and num == int(num):
        warnings.append(
            f"金额 {num:g} 标称为元，量级异常，疑似以分为单位（= ¥{num / 100:.2f}），请核对来源"
        )
    return warnings


def guess_unit_hint(raw_value, fee_like: bool = False) -> str:
    """给出单位猜测提示（不用于计算，只用于诊断报告）。

    fee_like 表示这是配送费/服务费这类通常以分为单位的字段。
    返回 "cent" / "yuan" / "unknown"，调用方必须自己确认后才可用于换算。
    """
    try:
        num = float(str(raw_value).replace(",", "").strip())
    except (TypeError, ValueError):
        return "unknown"
    if fee_like and num >= 100 and num == int(num):
        return "cent"
    if num >= 500 and num == int(num):
        return "cent"
    return "yuan"


# ---------- 时间 ----------

_TS_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
)

_DIGITS = re.compile(r"^-?\d+(\.\d+)?$")


def parse_time(raw) -> datetime:
    """把各种形状的时间字段统一成本地时区 datetime。

    支持：10 位秒级时间戳、13 位毫秒级时间戳、常见日期字符串、ISO 8601。
    """
    if raw is None or raw == "":
        raise TimeParseError("时间为空")

    # 数字或纯数字字符串 → 时间戳
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and _DIGITS.match(raw.strip())):
        num = float(raw)
        if num > 1e11:  # 毫秒
            num /= 1000.0
        elif num < 1e8:  # 明显不是时间戳（比如 20261018 这种 yyyymmdd）
            text = str(int(num))
            if len(text) == 8:
                return datetime.strptime(text, "%Y%m%d").replace(tzinfo=CN_TZ)
            raise TimeParseError(f"数值 {raw} 不像有效时间戳")
        return datetime.fromtimestamp(num, tz=CN_TZ)

    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=CN_TZ) if dt.tzinfo is None else dt.astimezone(CN_TZ)
    except ValueError:
        pass
    for pattern in _TS_PATTERNS:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=CN_TZ)
        except ValueError:
            continue
    raise TimeParseError(f"无法解析时间「{raw}」")
