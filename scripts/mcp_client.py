#!/usr/bin/env python3
"""麦当劳 MCP 最小客户端（仅标准库实现 Streamable HTTP）。

设计原则：
1. 零第三方依赖 —— 只有标准库，任何人 clone 下来就能跑。
2. Token 只从环境变量读，绝不打印、绝不落盘。
3. 429 限流按官方建议退避重试一次，仍失败则抛出，不做无限重试。

用法：
    export MCD_MCP_TOKEN=xxxxx
    python mcp_client.py list            # 列出全部工具
    python mcp_client.py call query-my-account '{}'
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """MCP 调用失败。"""


class McdMcpClient:
    """一个够用的 MCP 客户端：初始化、列工具、调工具。"""

    def __init__(self, token: str | None = None, url: str | None = None, timeout: int = 45):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "").strip()
        self.url = url or os.environ.get("MCD_MCP_URL", DEFAULT_ENDPOINT)
        self.timeout = timeout
        self.session_id: str | None = None
        self._next_id = 0
        if not self.token:
            raise McpError(
                "未找到 MCD_MCP_TOKEN。请到 https://open.mcd.cn/mcp 手机号登录后领取，"
                "然后设置环境变量后再运行。"
            )

    # ---------- 底层传输 ----------

    def _post(self, payload: dict, expect_response: bool = True, retry: bool = True) -> dict | None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", errors="replace")
                ctype = (resp.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code == 401:
                raise McpError(f"401 Token 无效或已过期。请检查 MCD_MCP_TOKEN。({detail})") from exc
            if exc.code == 429 and retry:
                time.sleep(2)
                return self._post(payload, expect_response=expect_response, retry=False)
            raise McpError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise McpError(f"网络不可达: {exc.reason}") from exc

        if not expect_response:
            return None
        if not raw.strip():
            return None
        if "text/event-stream" in ctype:
            return self._parse_sse(raw)
        return json.loads(raw)

    @staticmethod
    def _parse_sse(raw: str) -> dict | None:
        """从 SSE 流里取出最后一个 data: 负载。"""
        last = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        last = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
        return last

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            self._next_id += 1
            payload["id"] = self._next_id

        result = self._post(payload, expect_response=not notify)
        if result and "error" in result:
            err = result["error"]
            raise McpError(f"{method} 失败: {err.get('message', err)}")
        return result.get("result") if result else None

    # ---------- 协议方法 ----------

    def initialize(self) -> dict:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"roots": {"listChanged": False}},
                "clientInfo": {"name": "mcd-points-butler", "version": "1.0.0"},
            },
        ) or {}
        self._rpc("notifications/initialized", {}, notify=True)
        return result

    def list_tools(self) -> list[dict]:
        self.initialize()
        tools: list[dict] = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._rpc("tools/list", params) or {}
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        if not self.session_id:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}}) or {}
        if result.get("isError"):
            raise McpError(f"工具 {name} 返回错误: {_text_of(result)}")
        return result

    def call_json(self, name: str, arguments: dict | None = None):
        """调用工具并把返回内容尽量解析成 Python 对象。"""
        return _decode_payload(self.call_tool(name, arguments))


def _text_of(result: dict) -> str:
    return "\n".join(
        part.get("text", "") for part in result.get("content", []) if part.get("type") == "text"
    )


RESPONSE_MARKER = "## Original Response"


def _decode_payload(result: dict):
    """MCP 工具返回是 content 数组，内容可能是纯文本或 JSON 字符串，统一解出来。

    麦当劳 MCP 多数工具会把真实结果包成一段带说明的文本，形如：

        # API Response Information
        ## Response Structure
        ...
        ## Original Response
        {"success":true,"code":200,"data":{...}}

    所以要先把 Original Response 后面的 JSON 抠出来，否则拿到的只是一段废文本。
    """
    text = _text_of(result).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    extracted = extract_json(text)
    return extracted if extracted is not None else text


def extract_json(text: str):
    """从夹杂说明文字的文本里扣出最后一个完整 JSON 对象。"""
    if RESPONSE_MARKER in text:
        text = text.split(RESPONSE_MARKER, 1)[1]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    client = McdMcpClient()
    cmd = argv[1]
    if cmd == "list":
        for tool in client.list_tools():
            print(f"{tool.get('name'):<28} {tool.get('description', '')[:70]}")
        return 0
    if cmd == "call":
        if len(argv) < 3:
            print("用法: python mcp_client.py call <tool-name> '<json-args>'")
            return 2
        args = json.loads(argv[3]) if len(argv) > 3 else {}
        print(json.dumps(client.call_json(argv[2], args), ensure_ascii=False, indent=2))
        return 0
    print(f"未知命令: {cmd}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv))
    except McpError as exc:
        print(f"[MCP 错误] {exc}", file=sys.stderr)
        raise SystemExit(1)
