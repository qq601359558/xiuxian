# F04 典当行 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F04）。基线：e623731（全量 294 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：行囊物品可典当换灵石（约五折），限期按「典当额 + 利息」赎回，逾期没收进坊市流通。
- **本质意图**：给灵石经济加一条「抵押周转」线——急用钱时不必贱卖（出售是终局五折），
  付出利息即可保住稀有装备/丹药；同时没收物流入寄售栏，给坊市增加一条低成本货源。
- **关键目标**：典当→赎回闭环可玩通且金额口径确定性可复算；典当不可变相无息套现；
  典当物在当期间全程不可用；逾期没收去向明确且玩家可感知；旧坊市行为逐字不变。

## 现状盘点（实测，2026-11-04）
- **行囊语义**：`Character.inventory` 为随身杂物名列表；穿戴（EquipEngine）把物品**移出** inventory 进
  `equipped`，卸下才放回（F01/F02 评审已钉死）。阵盘在 `arrays`，本项不动 arrays。
- **出售口径**：`MarketEngine.sell_to_guild` = 当地市价（F03 区域价）× `MARKET_SELL_BACK_RATE=0.5`，
  再按同货同日收购量分档压价（防刷回归）；卖出即终局、无赎回。
- **价格单点**：当地市价 = `MarketEngine.market_price(item, location)`（F03 收敛，基准区=标价，
  未知货回退 20）。典当估值必须复用此单点，禁止另起价格表。
- **寄售模式**：`market_listings` 表（id/data_json/status/seller_id/created_at）+
  `MarketListingRepository.save/list_all` + pydantic 模型存 data_json——新表照此写。
- **落账惯例**：server/cli handle 成功才 `CharacterRepository.save`；引擎先校验后改状态，失败不改。
  寄售的货款结算是「买家 handle 里给卖家入账」，卖家查无此人时款项自然沉淀（无人领取）。

## 关键设计决策（与备选对比）
1. **典当率与出售回收率的关系**：典当额 = 当地市价 × `PAWN_RATE=0.5`，与商会回收率同为五折。
   卖点不是价高，而是**可赎回**：出售是终局交易，典当是抵押借款。若典当率高于回收率，
   「典当后弃赎」会全量替代出售并绕开 F03 收购回归压价——故同率，且在文案中如实写明。
   典当不计入 F03 收购量回归（当铺与商会是两条线；典当的防刷靠利息+期限+张数上限，见决策 4）。
2. **利息模型：固定息（不按天滚动）**。赎回价 = 典当额 + 利息，
   利息 = max(1, ceil(典当额 × `PAWN_INTEREST_RATE=0.10`))。赎回总额恒 > 典当额（本金 ≥1 → 息 ≥1），
   「当→赎」回路净亏利息，结构性不可套现。备选按天计息否决：金额随墙钟漂移、玩家难预期、
   测试需多点采样；固定息一口价、当票上写死，简单且可复算。
3. **期限与没收**：当期 `PAWN_TERM_DAYS=3`（现实 3 天，`due_at = pawned_at + 3×86400`）。
   没收**惰性结算**：无后台任务，在玩家执行 /典当（查看或典当）或 /赎回 时先结算本人过期票——
   与仓库既有「惰性清理」惯例（如 hunt 过期清理挂在 /look）一致，测试可注入时间确定性触发。
4. **没收去向：转商会寄售栏（官价上架）**。过期物品生成一条 `MarketListing`：
   seller_id=`pawn_shop`、seller_name=「天道当铺」、价格 = 当地市价×0.5（按没收结算时**当铺所在地**
   ——即结算玩家当前地点——市价计，与回收价同口径，属低价货源）。任何人可 /买寄售 买走；
   成交款按既有寄售结算找「天道当铺」角色必然查无此人 → 款项沉淀销毁（经济漏，不印钞）。
   备选「进商会官价库存」否决：官价货单是 config 静态目录，无动态库存概念，硬塞要改货单结构；
   寄售栏是现成的动态流通池，零新机制。玩家在 /典当 查看时，已没收票以「已没收」标注保留展示
   （票据 status=FORFEITED，不再可赎），不会静默消失。
5. **逐件成票**：一次 /典当 只当 1 件，生成 1 张票（id 8 位 uuid，同寄售惯例）。
   同名多件即多张票互不相干；/赎回 <物品名> 赎**最早到期**的一张 OPEN 票（FIFO，防玩家挑票）。
   在途票上限 `PAWN_MAX_TICKETS=8`（与寄售栏上限同值），满额拒绝新典当。
6. **可用性口径（与既有坊市指令对齐）**：
   - 死亡（status=DEAD）：典当/赎回拒绝（同 buy 的「死人不可逛坊市」）；/典当 查看放行（只读遗容）。
     角色坐化转世后是**新角色 id**，旧票按 char_id 归属旧世，不可赎回（spec 明示，非 bug）。
   - 闭关（MEDITATING）：三条指令**均不进** server med 白名单、cli 白名单，与 /购买 /出售 同口径锁门。
     理由：/典当 查看带惰性没收结算（写状态），不是纯只读观照，不做 F03 /行情 式例外。
   - 典当物在当期间：已移出行囊 → 穿戴/服用/出售/寄售/交易天然不可达（各引擎都只认 inventory），
     无需逐个引擎加黑名单；测试以「出售该物失败」钉住。

## 完善后的规则闭环（行为契约）
### 常量（config.py，坊市节后新增「典当行（F04）」节）
- `PAWN_RATE = 0.5`（典当率：当地市价 × 此率 = 典当额，与 MARKET_SELL_BACK_RATE 同值，理由见决策 1）
- `PAWN_INTEREST_RATE = 0.10`（固定息比例，按典当额计，一次计清）
- `PAWN_TERM_DAYS = 3`（当期，现实天）
- `PAWN_MAX_TICKETS = 8`（单人 OPEN 票上限）
- `PAWN_SHOP_ID = "pawn_shop"` / `PAWN_SHOP_NAME = "天道当铺"`（没收寄售的挂单主体）

### 数据（新表，只加不改）
- 表 `pawn_tickets`（照 market_listings 结构）：id / data_json / status / owner_id / created_at。
- 模型 `PawnTicket`（core/pawn.py，pydantic）：id、owner_id、owner_name、item_name、kind、
  principal（典当额）、interest（利息，成票时写死）、pawned_at、due_at、
  status（OPEN / REDEEMED / FORFEITED）。
- `PawnTicketRepository.save / list_all / list_by_owner(owner_id)`（storage/db.py，照寄售仓储写）。

### 引擎（core/pawn.py · PawnEngine，规则单点）
- `pawn_value(item_name, location) -> int`：max(1, int(MarketEngine.market_price × PAWN_RATE))。
- `interest_for(principal) -> int`：max(1, ceil(principal × PAWN_INTEREST_RATE))。
- `pawn_item(char, item_name, now=None) -> (ticket|None, res)`：先 `settle_expired(char.id, now)`；
  校验顺序：DEAD → 行囊无此物（在 equipped 中 → 「已穿戴须先卸下」专属文案）→ OPEN 票满额。
  成功：inventory 移除 1 件、灵石 += 典当额、成票（kind 取 ITEM_CATALOG，无目录记 material）。
- `redeem_item(char, item_name, now=None) -> res`：先结算过期；找本人该物品最早到期 OPEN 票；
  无票 → 失败文案；灵石 < 本金+息 → 失败且**票保持 OPEN**（到期前仍可再赎）；
  成功：扣灵石、物品回 inventory、票 status=REDEEMED。
- `settle_expired(owner_id=None, now=None) -> List[PawnTicket]`：OPEN 且 due_at <= now 的票 →
  FORFEITED + 生成当铺寄售（MarketListingRepository.save）；价格按结算者当前地点市价×0.5
  （owner_id=None 的全量结算按票主当前地点——本项只在玩家指令路径按单人结算，全量入口仅供测试/GM）。
- `my_tickets(char_id)` / `panel_text(char, now=None)`：/典当 查看文本——OPEN 票逐行
  （物品、当额、赎回价、到期剩余），FORFEITED 票标注「已逾期没收，已流入坊市寄售」，
  REDEEMED 不展示（已了结）；无票给空文案 + 用法提示。

### 指令（server/world.py 与 cli/main.py 双端一致）
- `/典当`（无参）：查看本人当票（先惰性结算过期）。
- `/典当 <物品名>`：典当 1 件（成功才落库：CharacterRepository.save + PawnTicketRepository.save）。
- `/赎回 <物品名>`：赎回最早到期的一张 OPEN 票（成功才落库）。
- 别名：/pawn、/redeem 与中文同路（沿用坊市指令的双语别名惯例）。
- server 帮助行、cli 帮助行各加 /典当 /赎回；_market 通道行加「/典当 /赎回」。

### 网页
- web/index.html 仙门·坊市卡加：「典当」按钮（data-cmd="/典当"，查看）、
  「典当…」（data-prompt，prefix /典当，placeholder「物品名，如：青锋剑」）、
  「赎回…」（data-prompt，prefix /赎回，placeholder「物品名」）；
  web/app.js hints 加 典当/赎回 两条说明。前端零逻辑改动。

### AI 边界
- 零新增 AI 调用：当铺文案全为本地模板（对照 F03 trade_board 的零 AI 口径）。

## 边界与异常
- 行囊无此物 / 只有已穿戴件 / 票已逾期（赎回时先结算 → 报「已没收」）/ 灵石不足赎回（票仍有效）/
  票满 8 张 / 典当额下限 1 灵石（贱货也成票）/ 未知货（按市价回退 20 估值，与出售同口径）。
- 并发：server handle 持世界锁串行；CLI 单进程。引擎内先校验后改状态，失败不落任何改动。
- 旧档兼容：纯新表 + 零角色字段变更，老存档打开即用（init_db 的 CREATE TABLE IF NOT EXISTS 兜底）。
- 没收寄售的价格地点口径：以结算触发者（票主本人）当前地点为准；票主久不上线则票一直 OPEN
  挂账，直到其本人下次操作当铺指令时结算——惰性口径的已知取舍（无后台扫表），spec 明示。

## 验收标准
1. tests/test_pawn.py 覆盖：典当成功与金额口径（基准区聚气丹 40×0.5=20）、行囊移除且不可出售/穿戴、
   赎回闭环（扣 本金+息、物回行囊）、赎回总额 > 典当所得（防套现）、灵石不足赎回失败且票仍 OPEN、
   逾期没收（改 due_at 模拟）+ 没收物流入寄售栏且可被他人买走、已穿戴不可典当、无此物/无票边界、
   到期时间确定性（due_at = pawned_at + 3 天，注入 now 复算）、逐件成票与 FIFO 赎回、
   server handle 链路至少 1 条（含闭关锁门）、旧档兼容（无票角色查看正常）。
2. 全量回归 0 失败（基线 294 + 新增）。
3. 独立评审子代理审 diff，必须修项整改后复跑全量。

## Out of Scope
- 阵盘（arrays）典当、一次典当多件/数量参数（逐件成票已覆盖多件场景）。
- 按天滚动计息、展期/续当、部分赎回。
- 当铺 NPC 议价、典当物拍卖（F05 范畴）、没收款项的去向再分配（沉淀即漏）。
- 后台定时扫表没收（惰性结算已闭环；GM 全量结算入口仅留引擎函数，不接指令）。
- 死亡后旧世当票的继承/转世赎回（新世新角色口径，不做）。

## 状态
- [x] 阶段一细化（本文）
- [ ] 实现（引擎/存储/双端/网页）
- [ ] 新增测试与全量回归
- [ ] 独立评审与整改
