# MCP 集成说明 · 麦途 mcd-mailu

## 使用的麦当劳 MCP 服务

| MCP Server | 接入地址 | 协议 |
|---|---|---|
| 麦当劳官方 MCP | `https://mcp.mcd.cn` | Streamable HTTP |

## 使用的工具及用途

| 工具 | 用途 | 读/写 |
|---|---|---|
| `order-list` | 读取餐食历史订单（门店、时间、金额、商品明细） | 读 |
| `mall-order-list` | 读取商城订单（仅旁注计数，不混入餐费统计） | 读 |
| `now-time-info` | 获取服务器时间，作为「近 N 个月」的唯一时间基准 | 读 |

**本项目不调用任何写操作工具**（`create-order` / `cancel-order` / `mall-create-order` / `party-order-create` / `draw-lottery`）。麦途是只读产品。

## 调用流程

```
query 触发
  └─ order-list ──→ adapters.from_order_list   （清洗：状态过滤 / 去重 / 金额告警 / 时间归一）
  └─ mall-order-list ──→ adapters.from_mall_order_list（旁注计数）
  └─ now-time-info ──→ 时间基准
        └─ scene_engine.tag_orders      （场景标签，每条带 evidence）
        └─ scene_engine.detect_patterns （模式识别，按「到访」口径）
        └─ narrative.build_story        （叙事生成，每句话带订单依据）
        └─ card_render.render_card      （单文件 HTML 轨迹卡）
```

## 业务价值

现有麦当劳 MCP 参赛作品集中在「帮你点」——点餐、省钱、营养。麦途补的是另一端：**读懂已经发生的消费**。订单里的门店名与时间是被低估的数据源，店名藏着机场、火车站、写字楼，时间里藏着早班机与深夜加班。麦途把历史订单识别为场景、合并为「到访」、生成每句话可回溯到订单的叙事卡片。

## 实测发现（对其他参赛者有参考价值）

1. **返回包装层**：工具返回是一段带说明的文本，真实 JSON 在 `## Original Response` 之后，需先抠取再解析（见 `mcp_client.extract_json`）。
2. **`order-list` 无分页参数**：一次返回全量历史。对重度用户是否会被服务端截断，未能验证，属已知风险。
3. **`realTotalAmount` 为字符串、单位「元」**（如 `"11.9"`、`"38"`），非以分计。
4. **订单明细无单品单价**，只有订单总额；套餐子项在 `comboItemList` 里，无价格。
5. **`mall-order-list` 支持 `lastId` 游标翻页**，返回 `hasNext` 标记，与 `order-list` 行为不一致。
