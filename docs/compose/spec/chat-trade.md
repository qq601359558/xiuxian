---
feature: chat-trade
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: (see git)
---

# 加强聊天交易：会话内自然语买卖

## Report

**What was built** — 聊天窗/`/说` 内：`有什么货` 看货架；`买下聚气丹`/`买2个…` 按 NPC 职分定价成交；`卖你妖兽内丹 2` 商会回收或私易压价；出价过低拒绝；态度差拒商。规则落账（灵石/行囊），恐慌价接入。

**Verification** — `tests/test_chat_trade.py` 等 **15 passed**；全量见交付。

## [S1] Problem

NPC 会话只能闲聊，买卖仍要跳 `/坊市`。需要在聊天里用自然语完成交易。

## [S2] Design

- 意图：trade（买/卖/货单/出价）→ `do_trade(..., text)`
- 职分：掌柜/伙计/商会=shop（货单价）；散修=person（转手加价/私易压价）
- 数量：`_extract_qty`；售卖走 `MarketEngine.sell_to_guild` 或私易
- 拒绝：态度 hostile / 出价 < 要价

## Out of Scope

玩家当面 `/交易` 多步撮合；拍卖行。

## Tasks

- [x] T1 do_trade 买卖/货单/职分定价
- [x] T2 分类词表 + 测试 + 服务器路径
