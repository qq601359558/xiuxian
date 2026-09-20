---
feature: trade-hub
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 坊市四通道：当面交易 · NPC 专柜 · 寄售 · 拍卖行

## Report

**What was built** — 新增 `core/trade.py`：玩家当面交易（同地+安全区，双方报价锁定/同意成交/拒绝与超时退回）、NPC 职分专柜（`/npc货单` `/npc买` `/npc卖`，态度改价）、拍卖行（限时竞价+一口价，超价自动退款，流拍/落槌结算，卖家 5% 手续费）。寄售保持 `market.py` 原语义；`/坊市` 汇总四通道。`auction_lots` 表 + `AuctionLotRepository` 持久化；`world.py` 接入全部指令。

**Verification** — `pytest tests/test_trade_hub.py` → 14 passed；全量 `pytest tests` → **134 passed**。评审 critical（一口价先退款后校验、转世 id 孤儿）已修并补回归用例。

**Journey log**
- 无 git → in-place；结算必须从库加载双方，`world.py` 在 accept/reject 后重载 `char`，禁止陈旧对象覆盖。
- `save` 在 `user_id` 冲突时同步 `id` 列，否则 `get_by_id` 落空。
- 拍卖补 `seller_user_id`/`leader_user_id`，`get_by_id` 失败时按 user_id 兜底。
- 一口价：先校验净支付，再动账退款。
- `tests/test_events_ai.py` 危机事件偶发空 effects（AI 路径），PRE-EXISTING 偶发，与本特性无关。

## [S1] Problem

局域网服已有商会买卖与玩家寄售，但缺少：
1. **玩家当面交易**——只能挂单买断，无法协商互换；
2. **NPC 专柜**——`/购买` 走统一货单，NPC 职分与态度不影响成交；
3. **拍卖行**——无竞价/一口价/流拍；
4. 寄售与新入口文案分散。

创作者拍板（2026-09-17）：当面交易限**同地+安全区**；拍卖=**限时竞价+一口价**；NPC=**职分货单+态度改价**；本轮**四通道一次交付**。

## [S2] Design

### 2.1 总原则

- **规则权威**：价格、手续费、是否可交易、落槌结果全由规则裁决；AI 不改数值。
- **契约担保**：成交即原子落账（灵石+货物）。
- **复用**：寄售沿用 `MarketListing`；拍卖 `AuctionLot`；NPC 买卖套职分/态度系数。
- **安全**：`can_use_market` 统一门禁（死亡/闭关/庇护）。

### 2.2 玩家当面交易

**前置**：双方存活、非闭关、可转移资产；**同一地点**；`is_safe`。

**指令**：`/交易 <道号>` · `/交易出 <灵石> [物品…]` · `/交易` · `/交易同意` · `/交易拒绝`

**会话** `TradeSession`：出价时从 inventory 锁入会话；改报价清双方同意；超时 10 分钟自动取消退回；成交原子交换并写大事记。结算从库加载双方；`world.py` accept/reject 后重载本人。

### 2.3 NPC 专柜

**指令**：`/npc货单 <道号>` · `/npc买 <道号> <货名> [数量]` · `/npc卖 <道号> <货名> [数量]`

**职分**：丹/药/掌柜→pill；铁/剑/匠→equip；商/市/货→全；阵→array；其他→material+pill。

**态度买价**：≥40→0.90；≤-40→1.20；否则 1.00。卖给 NPC 系数 1.10 / 0.80 / 1.00。

### 2.4 寄售

`/寄售` `/买寄售` `/撤单` 语义不变；`/坊市` 并列展示。

### 2.5 拍卖行

`AuctionLot`：底价/一口价/当前价/领先者/`ends_at`。

- 时长 120 分钟；加价 `max(1, 5%当前价)`；出价即扣款，被超价自动全额退回。
- 一口价：先校验净支付（自己是领先者则扣差额），再退款落槌。
- 流拍退回物品；成交向卖家抽 5%；有出价不可撤拍。
- 阵盘可上拍（take/give 走 inventory 或 arrays）。

**指令**：`/拍卖行` · `/上拍 <货> <底价> [一口价]` · `/拍 <编号> <出价>` · `/一口 <编号>` · `/撤拍 <编号>`

### 2.6 数据

- TradeSession：进程内 dict，超时惰性清扫，结束即 pop。
- AuctionLot：SQLite `auction_lots`；含 `seller_user_id`/`leader_user_id` 供转世兜底。

### 2.7 测试边界

见 `tests/test_trade_hub.py`（成交/门禁/退回/职分/态度/竞价退款/一口价副作用/流拍/落槌/超时/撤拍）。

## [S3] Out of Scope

- 拍卖实时推送/UI；跨服；担保行；远程交易；讨价还价对话成交；寄售改价。

## Tasks

- [x] T1: 模型与引擎 `core/trade.py` — acceptance: 单元可调用，规则见 S2 (covers: S2.1–S2.5)
- [x] T2: 持久化 AuctionLot Repository — acceptance: 上拍/落槌/撤拍后可 list_all 恢复 (covers: S2.6; depends: T1)
- [x] T3: `server/world.py` 接入指令与 `/坊市` 面板 — acceptance: `/交易` `/npc买` `/上拍` 等走通 (covers: S2.1–S2.5; depends: T1)
- [x] T4: 测试 `tests/test_trade_hub.py` 覆盖 S2.7 — acceptance: pytest 全绿；全量 tests 不回归 (covers: S2.7; depends: T1–T3)
- [x] T5: 独立 Review + Spec Finalize — acceptance: review critical 已修；status=delivered (depends: T4)
