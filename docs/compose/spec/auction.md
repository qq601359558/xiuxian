# F05 拍卖专场（状态机）Spec

> 上位文档：docs/compose/spec/feature-completion.md（F05）。基线：287184c（F01–F04 已合，全量 309 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：在既有 auction_lots 表上补拍卖状态机：开场 → 出价 → 成交/流拍 → 结算；NPC 参与出价（规则预算），网页可看拍品与出价。
- **本质意图**：拍卖行要从「玩家之间的限时寄售变体」升级为「世界自己会办的专场」：
  有待开场的预告、有 NPC 在场竞价抬氛围、玩家不开服也有场次轮转；同时资金流必须全程守恒可审计
  （冻结/退款/佣金/沉淀每一笔都有账），不给自买回套利和凭空印钞留口子。
- **关键目标**：状态机流转确定性可测（时间注入）；NPC 跟价纯规则且有估值上限、绝不无限抬价；
  结算幂等（重复推进不重复发钱发物）；新旧指令并存（/拍卖行 /拍 不变，新增 /拍卖 /出价）；
  双端（server/CLI）同引擎同口径；网页可看可拍。

## 现状盘点（实测，2026-11-04）
- **引擎已存在**（与任务书假设不同）：`core/trade.py` 的 `AuctionEngine` 已有
  `list_item / bid / buyout / cancel / settle_expired / board` 与 `AuctionLot` 模型
  （OPEN/SOLD/EXPIRED/CANCELLED），`auction_lots` 表（id/data_json/status/seller_id/created_at，
  载荷走 data_json → 新字段加在 pydantic 模型上即可，**无需改表**）。
  `storage/db.py` 有 `AuctionLotRepository.save/list_all`。
- **既有规则**：时长 `AUCTION_DURATION_MIN=120` 分钟、最小加价 `max(1, 5%)`（`AUCTION_MIN_INCREMENT=1`）、
  成交佣金 `AUCTION_SETTLE_FEE_RATE=0.05`（卖家承担）、单人上拍上限 `AUCTION_MAX_LOTS=5`、
  出价即扣款冻结、被超价自动退上一出价者、一口价立即落槌。tests/test_trade_hub.py 已覆盖
  玩家竞价/退款/一口价/流拍退回/撤拍主链（基线全绿）。
- **既有接入**：server/world.py 有 /拍卖行 /上拍 /拍 /一口 /撤拍；CLI **未接入**（帮助里把 /拍卖 列为局域网专有）；
  网页 **无** 拍卖按钮；**无 NPC 参与**；**无待开场/系统场次**（上拍即 OPEN，来源只有玩家）。
- **可用性口径**：引擎统一走 `can_use_market`（死亡/闭关/保护期资产转移限制，与寄售/典当共用）。
  server 闭关白名单不含拍卖指令（全锁门，与 F04 /典当 同理：看板带惰性结算写状态，非纯只读）；
  CLI 闭关白名单同样不含（新接入天然同口径）。
- **惰性推进先例**：F04 没收、hunt 过期清理、拍卖自身 `settle_expired` 都挂在玩家操作点惰性结算；
  `WorldStateRepository`（world_state KV）存进程无关运行态（ai_health 先例）——系统场次排期存这里。
- **NPC 识别**：`core.npc_mind._is_npc`（user_id 前缀 npc_/ai_npc_）；NPC 是真实 Character 落库，
  有 spirit_stones 账（种子 NPC 约数百灵石）。
- **价格单点**：`MarketEngine.market_price(item, location=None)`（无地点=基准区市价），
  NPC 估值与系统场次起拍价复用此单点，禁止另起价格表（F03/F04 教训）。

## 关键设计决策（与备选对比）
1. **不重写引擎，补状态机缺口**。既有 OPEN/SOLD/EXPIRED 是已上线且有测试钉住的语义；
   本项新增 `PENDING`（待开场）状态与 `starts_at/source` 两字段（data_json 载荷，旧档默认
   starts_at=0/source="player" 自动兼容），把生命周期补成完整状态机（见下图）。
   「已结算」不单设状态：SOLD/EXPIRED 即「终局且结算已原子完成」——settle 只处理 OPEN/PENDING，
   状态翻篇后重复推进天然跳过（幂等由状态守卫保证，有专项用例钉住）。
2. **开场来源：玩家上拍 + 系统场次并行**（任务书允许在 spec 定）。
   - 玩家上拍：既有 list_item，上拍成功即 OPEN（竞拍中），无待开场（玩家在场即开场）。
   - 系统场次：拍卖行宝库直供，卖家为伪主体 `auction_house`「天道宝库」。
     惰性排期（world_state `auction_next_system_at`）：任意 advance 时点若已到期且无在场系统拍品，
     生成一张 PENDING 系统拍品（starts_at = now + 5 分钟待开场），排期顺延 2 小时；
     到 starts_at 惰性晋升 OPEN，ends_at = starts_at + 120 分钟。
     拍品从 `AUCTION_SYSTEM_ITEMS` 按 world_state 序号确定性轮换，起拍价 = 市价 × 0.8、一口价 = 市价 × 1.25。
     系统拍品**流拍即收回宝库（物品消散，不回任何人行囊）**；**成交款全额沉淀**
     （买家冻结款不退、不付任何卖家——宝库即天道，款项回归经济漏）。
     备选「NPC 角色当卖家」否决：要给 NPC 凭空塞物品、成交款入 NPC 账等于系统印钞给 NPC，
     伪主体沉淀口径更干净且资金守恒可断言（Δ = −成交价）。
3. **NPC 跟价：纯规则、真实账户、有硬上限**。
   - 主体：存活 NPC 角色（_is_npc），走其真实 spirit_stones 账（扣款/被超价退款与玩家同路径 `_apply_bid`），
     不设虚拟预算池——NPC 穷了就是穷了，守恒断言覆盖 NPC 账。
   - 估值上限（防无限抬价）：`cap = min(NPC 灵石, 市价 × AUCTION_NPC_CAP_MULT(1.3) × 意愿系数)`，
     意愿系数由 crc32(lot_id:npc_id) 确定性导出 ∈ [0.85, 1.24]（同场同 NPC 上限固定，不随刷新漂移）；
     出价恒为当前合法地板价（起拍价或现价+步长），够不上 cap 即不跟。
   - 触发点（惰性，不新造线程）：`advance(now, react=True)` —— 由 **看板**（/拍卖、/拍卖行 双端）
     与 **server 世界 tick** 调用；出价/上拍/结算路径只调 `advance(react=False)`（只做排期/晋升/结算），
     保既有 bid/list 行为逐字不变、既有测试零扰动（评审 F04 教训：共享路径上不埋随机副作用）。
   - 概率门：每次 advance 对每个 OPEN 拍品以 `AUCTION_NPC_BID_CHANCE=0.55` 决定是否有一名 NPC 跟价一口；
     NPC 已领先则换人（领先者本人不跟自己的价）。force 参数供测试确定性触发。
   - NPC 达一口价即按一口价落槌（与玩家同规则，走 _settle_buyout）。
4. **指令命名：新旧并存**。任务书口径 /拍卖（查看）/出价 之外，既有 /拍卖行 /拍 已在玩家肌肉记忆与
   帮助文本中，不改名、只加别名：server 与 CLI 同步加 `/拍卖`→看板、`/出价`→出价。
   `/出价 <金额>`（无编号）：恰有一张 OPEN 拍品时直拍该件；0 张报无场次、多张报错并列编号让玩家用 /拍。
   `/出价 <编号> <金额>` 与 /拍 等价。
5. **资金守恒口径（可断言）**：
   - 玩家拍品成交：全场总灵石 Δ = −佣金（fee = 成交价 × 5%，卖家实收 = 价 − fee，买家冻结款即成交价）。
   - 系统拍品成交：Δ = −成交价（全额沉淀，见决策 2）。
   - 流拍/撤拍/未到期：Δ = 0（冻结全额退回、物品回卖家；系统流拍物品消散但灵石 Δ=0）。
   - NPC 参与不改变上式（NPC 账计入全场总额）。
6. **AI 边界**：零新增 AI 调用。NPC 跟价纯规则；系统拍品描述用物品目录 desc。
   既有 settle/buyout 里的 ai_flavor 司仪润色为存量行为，不动不增。

## 完善后的规则闭环（行为契约）
### 状态机
```
（玩家上拍）──────────────┐
                          ▼
系统排期 ──► PENDING 待开场 ──(starts_at 到，advance 晋升)──► OPEN 竞拍中
                                                              │  ├─ 玩家/NPC 出价（冻结、超价退款）
                                                              │  ├─ 一口价 ──► SOLD 已成交·已结算
                                                              │  ├─ 卖家撤拍（无出价时）──► CANCELLED 已结算（物回卖家）
                                                              └─ 到期 advance 结算 ──► 有出价 SOLD / 无出价 EXPIRED 已流拍·已结算
SOLD：玩家场=卖家得款−佣金、赢家得物；系统场=款全额沉淀、赢家得物。
EXPIRED：玩家场=物回卖家；系统场=物消散。终局状态再 advance 恒跳过（幂等）。
```
### 常量（config.py 拍卖节补充）
- 既有：`AUCTION_DURATION_MIN=120`、`AUCTION_MIN_INCREMENT=1`（另有 5% 步长取大）、
  `AUCTION_SETTLE_FEE_RATE=0.05`、`AUCTION_MAX_LOTS=5` 不动。
- 新增：`AUCTION_NPC_BID_CHANCE=0.55`、`AUCTION_NPC_CAP_MULT=1.3`、
  `AUCTION_SYSTEM_INTERVAL_SECONDS=7200`（系统场次间隔）、`AUCTION_SYSTEM_LEAD_SECONDS=300`（待开场时长）、
  `AUCTION_SYSTEM_START_RATE=0.8`、`AUCTION_HOUSE_ID="auction_house"`、`AUCTION_HOUSE_NAME="天道宝库"`、
  `AUCTION_SYSTEM_ITEMS`（目录内真实物品轮换表）。
### 数据（零改表）
- `AuctionLot` 加字段：`starts_at: float = 0.0`、`source: str = "player"`；`AuctionStatus` 加 `PENDING`。
- world_state KV：`auction_next_system_at`（float）、`auction_system_seq`（int）。
### 引擎（core/trade.py · AuctionEngine 增量）
- `_apply_bid(lot, bidder, amount)`：从 bid() 抽出的落账单点（退上一领先者→扣款→更新领先→存 lot 与出价者），
  bid() 与 NPC 跟价共用，行为与旧 bid 逐字等价。
- `floor_price(lot) -> int`：当前合法最低出价（无出价=起拍价；有出价=现价+max(1, 5%) 步长），bid 与 NPC 共用。
- `npc_cap(lot, npc) -> int` / `npc_maybe_bid(lot, now, rng, force=False) -> res|None`：按决策 3。
- `advance(now=None, rng=None, react=False) -> List[str]`：排期生成系统拍品（PENDING）→ 晋升到期 PENDING →
  settle_expired → （react 时）对每张 OPEN 拍品 npc_maybe_bid 至多一次。返回摘要（晋升/结算/跟价行）。
- `board()`：改走 advance(react=True)，看板分「待开场」（PENDING：拍品/起拍/开场倒计时）与
  「竞拍中」（OPEN：现价/领先/剩余时间）两段呈现。
- `settle_expired`：加系统场分支（EXPIRED 不回物、SOLD 不付款，全额沉淀；摘要注明）。
- `bid()`：PENDING 拍品专属文案「尚未开场」；入口改调 advance(react=False) 做晋升/结算（替代原 settle_expired 直调，
  list_item/buyout/cancel 同步换 advance(react=False)，语义等价超集）。
- `open_lots(now)`：供 /出价 无编号解析当前 OPEN 列表。
### 指令（server/world.py 与 cli/main.py 双端一致）
- `/拍卖` = `/拍卖行`（看板，advance react）；`/出价`（见决策 4）；其余 /上拍 /拍 /一口 /撤拍 双端齐全
  （CLI 本项新接入全部拍卖指令，帮助行补齐，并从「局域网专有」行移除 /拍卖）。
- server 世界 tick 挂接 advance(react=True)（try 包裹，失败不扰 tick 主循环）。
- 死亡/闭关口径：引擎 can_use_market 统一（死亡/闭关不可出价/上拍/一口/撤拍）；
  看板在闭关白名单外（双端同口径，与 F04 一致，理由：看板带写推进）。
### 网页
- web/index.html 仙门·坊市卡加：「拍卖」按钮（data-cmd="/拍卖行"）、
  「出价…」（data-prompt，prefix /拍，placeholder「编号 出价」）、「上拍…」（data-prompt，prefix /上拍）；
  web/app.js hints 加 出价/上拍 说明。拍品/现价/剩余/领先由看板文本呈现（零前端逻辑）。

## 边界与异常
- 出价 < 地板价 / 余额不足 / 自拍自买 / 已是领先者 / 拍品不存在 / PENDING 未开场 / 已结束：全部既有或新增文案拒绝且零落账。
- NPC 边界：无 NPC 存活、NPC 灵石不足、cap < 地板价、NPC 是卖家（系统场卖家为宝库伪主体，天然排除）时不跟价；
  NPC 跟价后被玩家超价，退款回 NPC 账（同 _apply_bid 路径）。
- 系统场排期已存而拍品被撤/异常：house 拍品不可撤（seller 不匹配任何玩家）；PENDING 期间玩家出价被拒。
- 并发：server handle 世界锁串行 + CLI 单进程；引擎先校验后落账，失败不改状态（NPC 跟价失败静默跳过，不扰玩家操作）。
- 旧档兼容：auction_lots 旧 data_json 无新字段 → pydantic 默认值补齐；旧 OPEN 拍品照常结算。
- 时间确定性：advance/settle/bid/board 全部接受 now 注入，测试改 ends_at/starts_at/world_state 排期值模拟。

## 验收标准
1. tests/test_auction.py 覆盖：状态机全流转（系统场 PENDING→晋升→NPC/玩家竞价→成交结算）、
   玩家场成交守恒 Δ=−佣金、系统场成交 Δ=−全价、流拍退回（玩家场）与消散（系统场）、
   出价校验（低于地板/余额不足/自买/已领先/PENDING 未开场）、结算幂等（advance 连推两次、board 连查两次守恒）、
   NPC 跟价（force 触发、cap 上限不超、NPC 被超价退款、NPC 一口价落槌）、
   /出价 无编号单场直拍与多场报错、server 与 CLI 双端 handle 各至少 1 条（含闭关锁门）、
   旧档兼容（旧字段缺失的 lot JSON 可读且可结算）、无场次空看板。
2. 全量回归 0 失败（基线 309 + 新增）。
3. 独立评审子代理审 diff，必须修项整改后复跑全量。

## Out of Scope
- 拍卖保证金/报名费、延时竞价（防狙击顺延）、多件打包上拍、拍卖搜索/分类。
- NPC 主动上拍（系统场以宝库伪主体代行）、NPC 之间纯离线互拍（只在 advance 触发点跟价）。
- 系统场次的真实定时线程（惰性排期已闭环；server tick 挂接为额外推进点，不新增线程）。
- 佣金分账给宗门/世界频道改造（既有落槌播报/传闻为存量，不动）。

## 状态
- [x] 阶段一细化（本文）
- [x] 实现（引擎增量/双端/网页/tick 挂接）
- [x] 新增测试与全量回归（322 passed = 基线 309 + 13）
- [x] 独立评审与整改（必须修 2 项已整改并复跑全量 322 全绿：
  M1 陈旧角色对象覆盖结算款——四入口 advance 前后做 DB 资产差分吸收
  （`_snapshot_assets`/`_absorb_advance_delta`，只并入增量不整表覆盖，
  保「先 append 行囊再上拍」的既有调用方式），CLI 看板后同法吸收；
  M2 `_settle_buyout` 补系统场显式分支（不付款、文案明示全额沉淀），补系统场一口价用例。
  建议项同批处理：NPC 候选加 can_use_market 同口径过滤；坊市摘要 _market 改 board(react=False)
  只读推进（react 触发点收敛为拍卖看板 + 世界 tick）；tick advance 异常加 log_event。
  未采纳/保留：玩家出价高于一口价按出价成交（存量行为，本项不改，NPC 路径封顶一口价）；
  _apply_bid 退款按 id 查（与基线一致）；系统排期为「上一场终局后顺延」口径，
  在场守卫命中不顺延 next_at，实际间隔≈场次时长+间隔常量之和的一部分，以排期常量为准。）
