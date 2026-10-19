#!/usr/bin/env python3
"""HTML 轨迹卡渲染。

配色采用麦当劳官方品牌色：
  麦当劳红 #DA291C / 拱门黄 #FFC72C / 深棕黑 #27251F
红黄只用于强调，正文始终是深棕黑，保证可读性与克制感。

输出单文件、零外链、零 JS 的 HTML，断网可开，适合截图转发。
时间轴布局：每单一个节点，节点带场景标签。4 单好看，80 单也好看。
"""

from __future__ import annotations

import html
from pathlib import Path

from narrative import Story
from scene_engine import TaggedOrder

RED = "#DA291C"
YELLOW = "#FFC72C"
INK = "#27251F"
GRAY = "#757575"
LINE = "#E4E2DD"
PAPER = "#FFFFFF"
PAGE = "#F2F1EE"

# 重点场景用红底白字，其余用黄底深字。整体只走红/黄两个色系。
MAJOR_SCENES = {"出行慰藉", "早班开场", "深夜补给", "一单多点"}


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _chip(scene: str) -> str:
    if scene in MAJOR_SCENES:
        bg, fg = RED, "#FFFFFF"
    else:
        bg, fg = YELLOW, INK
    return (
        f'<span style="display:inline-block;padding:1.5px 8px;margin:0 4px 3px 0;'
        f'border-radius:3px;background:{bg};color:{fg};font-size:11px;'
        f'letter-spacing:0.3px">{_esc(scene)}</span>'
    )


def _node(entry: TaggedOrder) -> str:
    o = entry.order
    scenes = [t.name for t in entry.tags if t.name not in {"新店打卡", "老地方"}]
    chips = "".join(_chip(s) for s in scenes)
    items = "、".join(_esc(i.name) for i in o.items if i.name)
    return f"""
      <div style="position:relative;padding:0 0 20px 22px">
        <div style="position:absolute;left:-4.5px;top:6px;width:9px;height:9px;border-radius:50%;background:{RED};border:2px solid {PAPER}"></div>
        <div style="font-size:11px;color:{GRAY};letter-spacing:0.5px">{o.placed_at.strftime('%Y-%m-%d %H:%M')}</div>
        <div style="font-size:14px;font-weight:500;color:{INK};margin:3px 0 2px;line-height:1.4">{_esc(o.store_name)}</div>
        <div style="font-size:13px;color:#444;line-height:1.6">{items} <span style="color:{RED};font-weight:500">¥{o.total_yuan:g}</span></div>
        <div style="margin-top:5px">{chips}</div>
      </div>"""


def render_card(story: Story, tagged: list[TaggedOrder], output_path: str | Path) -> Path:
    total = len(tagged)
    total_amount = sum(t.order.total_yuan for t in tagged)
    stores = len({t.order.store_name for t in tagged})
    nodes = "".join(_node(t) for t in reversed(tagged))  # 最近的在上面
    hit_patterns = [p for p in story.patterns if p.hit]
    pattern_text = " · ".join(p.name for p in hit_patterns) if hit_patterns else "样本有限"

    lines_html = "".join(
        f'<li style="margin-bottom:7px">{_esc(line.text)}</li>' for line in story.lines
    )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>我的麦途</title>
</head>
<body style="margin:0;padding:0;background:{PAGE}">
<div style="max-width:680px;margin:0 auto;background:{PAPER};font-family:system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif">

  <div style="background:{RED};padding:22px 24px 20px;border-bottom:5px solid {YELLOW}">
    <div style="font-size:11px;letter-spacing:3px;color:{YELLOW};font-weight:500">麦途 · MY McD JOURNEY</div>
    <h1 style="font-size:21px;font-weight:500;color:#FFFFFF;margin:10px 0 6px;line-height:1.45">{_esc(story.headline)}</h1>
    <div style="font-size:11px;color:rgba(255,255,255,0.78)">{_esc(story.subline)}</div>
  </div>

  <div style="display:flex;padding:20px 24px 16px;gap:8px;border-bottom:1px solid {LINE}">
    <div style="flex:1;text-align:center">
      <div style="font-size:30px;font-weight:500;color:{RED};line-height:1.1">{total}</div>
      <div style="font-size:11px;color:{GRAY};margin-top:4px">订单 单</div>
    </div>
    <div style="flex:1;text-align:center;border-left:1px solid {LINE};border-right:1px solid {LINE}">
      <div style="font-size:30px;font-weight:500;color:{INK};line-height:1.1">¥{total_amount:g}</div>
      <div style="font-size:11px;color:{GRAY};margin-top:4px">总花费</div>
    </div>
    <div style="flex:1;text-align:center">
      <div style="font-size:30px;font-weight:500;color:{INK};line-height:1.1">{stores}</div>
      <div style="font-size:11px;color:{GRAY};margin-top:4px">门店 家</div>
    </div>
  </div>

  <div style="padding:14px 24px 0">
    <span style="display:inline-block;background:{YELLOW};color:{INK};font-size:11px;font-weight:500;padding:3px 9px;border-radius:3px;letter-spacing:0.5px">模式识别 · {_esc(pattern_text)}</span>
  </div>

  <div style="padding:16px 24px 4px">
    <h2 style="font-size:13px;font-weight:500;color:{INK};margin:0 0 8px;padding-left:8px;border-left:3px solid {RED};letter-spacing:0.5px">数据在说什么</h2>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#3A3A36;line-height:1.75">{lines_html}</ul>
  </div>

  <div style="padding:12px 24px 18px">
    <h2 style="font-size:13px;font-weight:500;color:{INK};margin:0 0 12px;padding-left:8px;border-left:3px solid {RED};letter-spacing:0.5px">时间轴</h2>
    <div style="border-left:1.5px solid {LINE};margin-left:4px">{nodes}</div>
  </div>

  <div style="background:{INK};padding:14px 24px;font-size:10px;color:#B9B7B2;line-height:1.7">
    本卡片由「麦途 mcd-mailu」基于麦当劳 MCP 历史订单生成。所有结论可回溯至真实订单，无虚构内容。<br>
    订单明细仅在本机内存中处理，卡片不含完整订单号、手机号与地址。<br>
    麦当劳程序员创意开发大赛参赛作品，由参赛者独立开发，<span style="color:{YELLOW}">非麦当劳官方产品</span>。
  </div>
</div>
</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
