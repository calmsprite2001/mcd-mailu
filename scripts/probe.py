#!/usr/bin/env python3
"""MCP 工具字段探测器。

为什么需要这个文件：麦当劳 MCP 各工具的返回结构没有稳定契约文档，
字段名和层级要靠实测。这个脚本把真实返回的「结构骨架」打出来（只打键路径
和类型，不打值），用来校准 adapters.py，同时避免把真实订单内容刷到终端。

用法：
    python scripts/probe.py schema order-list
    python scripts/probe.py call order-list '{"page":1,"pageSize":3}'
    python scripts/probe.py probe order-list '{"page":1,"pageSize":3}'
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_client import McdMcpClient, McpError  # noqa: E402

SENSITIVE = {"phone", "mobile", "telephone", "address", "receiver", "contact", "token", "password"}
RAW_DIR = Path(__file__).resolve().parent.parent / "raw"


def shape_of(obj, prefix: str = "", depth: int = 0, max_depth: int = 6) -> list[str]:
    """把任意 JSON 对象压成「键路径 : 类型」清单。"""
    lines: list[str] = []
    if depth > max_depth:
        return lines
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            masked = "***" if any(s in key.lower() for s in SENSITIVE) else ""
            if isinstance(value, dict):
                lines.append(f"{path} : object")
                lines.extend(shape_of(value, path, depth + 1, max_depth))
            elif isinstance(value, list):
                lines.append(f"{path} : array[{len(value)}]")
                if value:
                    lines.extend(shape_of(value[0], f"{path}[]", depth + 1, max_depth))
            else:
                preview = masked or _preview(value)
                lines.append(f"{path} : {type(value).__name__} = {preview}")
    elif isinstance(obj, list):
        if obj:
            lines.extend(shape_of(obj[0], f"{prefix}[]", depth + 1, max_depth))
    return lines


def _preview(value) -> str:
    text = str(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, tool = argv[1], argv[2]
    args = json.loads(argv[3]) if len(argv) > 3 else {}
    client = McdMcpClient()

    if cmd == "schema":
        client.initialize()
        for item in client.list_tools():
            if item.get("name") == tool:
                print(json.dumps(item, ensure_ascii=False, indent=2))
                return 0
        print(f"未找到工具 {tool}")
        return 1

    if cmd not in {"call", "probe"}:
        print(f"未知命令: {cmd}")
        return 2

    data = client.call_json(tool, args)

    if cmd == "call":
        print(json.dumps(data, ensure_ascii=False, indent=2)[:6000])
        return 0

    print(f"=== {tool} 返回结构 ===")
    for line in shape_of(data):
        print(line)

    RAW_DIR.mkdir(exist_ok=True)
    dump = RAW_DIR / f"{tool}.raw.json"
    dump.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n原始返回已存到 {dump}（已被 .gitignore 排除，请勿提交）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv))
    except McpError as exc:
        print(f"[MCP 错误] {exc}", file=sys.stderr)
        raise SystemExit(1)
