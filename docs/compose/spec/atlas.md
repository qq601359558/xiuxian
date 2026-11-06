# F09 宗门势力版图 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F09）。基线：61c1ece（F01–F08 已合，全量 381 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：各宗门在各区域有「影响力」版图数据，由成员活动累积；版图产生可感知效果；/版图 可查。
- **本质意图**：宗门至今只有「对内」维度（F08 议政落 sect_state 三维内务），缺「对外」维度——
  宗门在天下各区域的存在感。此数据必须**只认既有事实**（成员真实完成的探险/委托/除凶结算），
  不新造一套活动系统；效果必须真实落到价格（玩家钱包可感知）且封顶防套利；
  版图必须可易主（衰减），否则先入宗门永久霸盘、后进者无戏。
- **关键目标**：影响力 累积→衰减→主导判定→价格优惠 的闭环可玩通且全程规则可复算；
  与 F03 区域价组合无套利；钩子零重复计数；旧测试锚点（基准区价格等）零影响。

## 现状盘点（实测，2026-11-04）
- **区域体系**：`WORLD_LOCATIONS` 11 地点分属 4 区域（东荒·青州 / 中土·万岳 / 西陲·幽冥渊 / 海外·乱星海）；
  `MarketEngine.region_of(location)` 已是地点→区域单点（含未知地点回退基准区），`all_regions()` 有序枚举。
- **宗门体系**：`SECTS_CONFIG` 固定 4 宗（青云宗/万剑仙门/九幽天魔宗/四海散修商会，各有 headquarters 地点）；
  成员归属在 `Character.sect`（None=散修）；NPC 口径 `user_id` 以 `npc_`/`ai_npc_` 开头（quests._is_npc 先例）。
- **F08 先例**：宗门状态走 `WorldStateRepository` KV（`sect_state:{sect}` 三维内务，合并写）；
  council spec 明确「sect_state 不含区域维度，F09 自建其表」——本项照此自建 KV，不碰 sect_state。
- **F03 价格单点**：买入价 = `MarketEngine.market_price`（标价 × 区域系数 × 每日波动，四舍五入，下限 1）；
  回收价 = 市价 × 0.5 再经卖出侧防刷分档（交易点修饰先例：修饰只落成交函数，不进市价函数）。
  基准区锚点（聚气丹 40 等）被 test_market/test_trade 钉死，回归红线。
- **既有结算点（钩子候选，均为引擎单点、双端共用）**：
  探险 `AdventureEngine.explore` 成功落账段（sect_contrib.sync_ring 与 QuestEngine.note_adventure_win 同段先例）；
  委托 `QuestEngine.deliver` 两处成功出口（推进一环 / 全环达成）；
  除凶 `core/hunt.py settle_kill` 成功返回前（NPC 猎手经 combat_fate 亦走此点，天然含 NPC）；
  议政 `CouncilEngine.settle` 效果落账后（settled 幂等守卫之内、仅首次结算执行）。

## 关键设计决策（与备选对比）
1. **存储：world_state 专属 KV，不建表不改 models**。
   `sect_atlas:{region}` = `{"inf": {sect: float}, "ts": float}`（每区域一键，本引擎独占写）；
   每日上限另键 `sect_atlas_cap:{char_id}` = `{"date": ..., "vol": {region: raw_points}}`（trade_reg 先例，跨日自动重置）。
   专属键的「读-衰减结算-改-整值写回」即该键的合并写，不存在整表覆盖他人数据的问题
   （评审关注点：本引擎从不写 `sect_state:` / `sect_council:` 等他人键；sect_atlas 键无第二写者）。
   跨进程并发口径与 council/trade 先例一致（server 进程内锁串行；CLI 跨进程不保证事务）。
2. **衰减：惰性半衰期结算（纯计算，不写读路径）**。
   半衰期 `ATLAS_DECAY_HALF_LIFE_DAYS=7`（现实天）：读时按 `inf × 0.5^(距 ts 天数/7)` 折算，<0.5 的宗门剪除；
   写时先折算再叠加并刷新 ts。查询只读不落盘（不把折算结果写回，避免只读指令产生写副作用）；
   保证长期无活动的宗门影响力归零、版图可易主。备选「tick 定时衰减」否决：不新造线程（总纲口径）。
3. **计分：只认三种既有结算 + 议政通过，数值入模块常量**。
   探险成功 +4（`ATLAS_POINTS_EXPLORE`）、委托每环交付 +6（`ATLAS_POINTS_QUEST`）、
   除凶结算 +10（`ATLAS_POINTS_HUNT`）、议政通过 +10 落本宗总坛区域（`ATLAS_POINTS_COUNCIL`，组织级、不占个人上限）。
   量级校准：主导阈值 100 ⇒ 一宗需约 25 次探险级活动（或混合）方主导一区，与 EVENT_EFFECT_CAPS/宗门环收益量级相称，不是一日之功。
4. **防刷：按角色+区域+日期双轨上限**。
   玩家每区域每日最多计 `ATLAS_DAILY_CAP_PLAYER=30` 原始分；NPC 每区域每日最多计 `ATLAS_DAILY_CAP_NPC=10` 原始分
   且入账权重 `ATLAS_NPC_WEIGHT=0.5`（NPC 即便被 tick 频繁驱动，单 NPC 单区日入账 ≤5，防自然膨胀霸盘）。
   上限按原始分记量（vol 记 attempted 中获准部分），部分获准（剩余额度 < 本次分值）按剩余额度入账，不整笔吞。
   议政分不走个人上限（组织事件、低频、已被 F08 窗口节律天然限流）。
5. **主导判定**：区域内影响力最高宗门，须 `≥ ATLAS_DOMINANCE_THRESHOLD(100)` 且**严格独占最高**
   （并列最高 → 无主，防两宗同分时的归属争议）；散修不是宗门、永不入表。
   门槛比较带容差 `ATLAS_THRESHOLD_TOLERANCE=0.01`：衰减为连续量，恰达门槛的影响力在读时已微亏
   （秒级读延迟即亏约 1e-5），无容差则「恰好 100」永不主导（实现期实测教训）。
6. **价格效果（唯一硬效果）：主导宗门成员在该区域向商会购货享九五折**。
   - 位序：`成交单价 = max(1, int(F03 市价 × (1 - ATLAS_DISCOUNT_RATE)))`，ATLAS_DISCOUNT_RATE=0.05；
     市价已含区域系数与每日波动（F03 公式不动），折扣只落在 `buy_from_guild` 成交点——
     与 F03 卖出侧防刷分档同为「交易点修饰」先例，`market_price/sell_unit_base` 纯函数不掺宗门维度，
     F03 全部价格锚点与套利遍历测试天然不受影响。
   - 套利分析（与 F03 组合）：同区买入（0.95×市价）再同区售回（0.5×市价）必亏，结构性无套利；
     跨区跑商毛利至多增加「买入价 5%」一档：F03 最坏路线（产地 0.55 含 -3% 波动 → 远方 1.35 含 +3% 波动、回收五折）
     毛利率由 ≈31% 升至 ≈37% 上限，仍受卖出侧防刷分档逐件压价封顶，且须先以 100 影响力主导买入区——
     是版图经营的正当回报而非印钞口。回收价不享折扣（只惠买入），寄售/拍卖不参与。
     （评审订正：NPC 专柜回收原本只认标价，与折扣组合成同地套利——已在专柜侧加区域锚封顶，
     见状态节整改记录；典当按未折扣市价五折、赎回含息，评审复核无套利。）
   - 呈现一致性：成交消息在既有区域注脚外追加「本宗主导此地，商会买价九五折」与折后单价；
     server `_market` 货单头在查看者宗门主导当地时加注「成交价九五折（货单为市价）」——货单价仍是市价单点，零口径分叉。
7. **招募效果（软效果，只展示）**：/版图 面板中，本宗主导的区域标注「声威所及，散修慕名投宗者众」；
   不落任何既有字段、不改拜入规则（evaluate_join 不动）——灰度只展示，避免为软效果改招募数值链。
   备选「主导区 NPC 入宗倾向数值化」否决：NPC 入宗无既有通道，硬接即新造系统，违背最小闭环。
8. **议政钩子时刻口径**：record_council 内部一律取**真实墙钟** time.time()，
   严禁透传 council 的注入逻辑时刻（F08 教训：逻辑时刻写盘会污染时间轴排序/衰减基线）。
9. **查询口径**：/版图 为纯只读观照——双端闭关白名单放行（与 /行情 同口径）、死亡可查看（面板不调 advance 类写路径，本引擎查询本身零写盘）。

## 完善后的规则闭环（行为契约）
### 常量（core/atlas.py 模块常量）
- `ATLAS_POINTS = {"explore": 4, "quest": 6, "hunt": 10}`、`ATLAS_POINTS_COUNCIL = 10`
- `ATLAS_DAILY_CAP_PLAYER = 30`、`ATLAS_DAILY_CAP_NPC = 10`、`ATLAS_NPC_WEIGHT = 0.5`
- `ATLAS_DOMINANCE_THRESHOLD = 100.0`、`ATLAS_DISCOUNT_RATE = 0.05`
- `ATLAS_DECAY_HALF_LIFE_DAYS = 7.0`、`ATLAS_PRUNE_BELOW = 0.5`
- `ATLAS_STATE_PREFIX = "sect_atlas:"`、`ATLAS_CAP_PREFIX = "sect_atlas_cap:"`

### 引擎（core/atlas.py · AtlasEngine，规则单点，零 AI）
- `region_map(now=None) -> Dict[region, Dict[sect, float]]`：全区域衰减后影响力（只读折算，不写盘）。
- `influence_map(region, now=None)` / `dominant_sect(region, now=None) -> Optional[str]`（阈值 + 严格独占）。
- `record_activity(char, kind, location=None, now=None) -> float`：无宗籍/死亡/未知 kind → 0；
  区域由 location（缺省 char.location）经 MarketEngine.region_of 推导；查个人日上限（玩家/NPC 双轨），
  部分获准按剩余额度；NPC 权重折算；衰减结算后叠加写回；返回实际入账影响力。异常全吞（try 包裹，钩子永不阻断主结算，与仓库钩子惯例一致——引擎内部吞，钩子调用点亦 try）。
- `record_council(sect, now=None) -> float`：now 缺省取真实墙钟；宗门总坛区域 +10，不占个人上限；sect 不在 SECTS_CONFIG → 0。
- `discount_unit(unit_price, sect, region, now=None) -> int`：sect 为该区域主导宗门时
  `max(1, int(unit_price × (1 - 0.05)))`，否则原价返回（market 成交点调用，纯读判定）。
- `panel_text(char, region_arg=None, now=None) -> str`：无参 = 全图（逐区域：主导宗门/无主、本宗影响力、主导值）；
  有参 = 区域明细（子串匹配区域名，或地点名经 region_of 归区；排名降序、阈值线、本宗标注、九五折提示）。
  本宗主导区域附招募展示句。散修可看全图（本宗列作「—」）。

### 钩子（均为 try/except 惰性导入，失败不影响主流程）
- `core/adventure.py` explore 成功落账段（与 sync_ring 同段）：`record_activity(c, "explore")`（区域取 c.location，迁跃后落点）。
- `core/quests.py` deliver 两处成功出口（推进一环 / 全环达成）：`record_activity(char, "quest")`。
- `core/hunt.py` settle_kill 成功路径（落账后、return 前）：`record_activity(hunter, "hunt", location=victim.location)`。
- `core/council.py` settle 首次结算落账后：`record_council(sect)`（仅 passed 时）。

### 价格接入（core/market.py · buy_from_guild）
- 计价后、扣款前：`unit = AtlasEngine.discount_unit(unit, buyer.sect, region)`（惰性导入，异常降级原价）；
  成交总额按折后单价；消息在成交行后按需追加主导折扣注脚（非主导成员消息与旧版逐字一致——锚点红线）。
- sell_to_guild / 寄售 / 拍卖 / NPC 专柜：不参与。

### 指令（server/world.py 与 cli/main.py 双端一致）
- `/版图 [区域|地点]`（别名 `/atlas`）：面板；server 分支置于 /行情 附近，纯文本返回；
  双端闭关白名单加 `/版图` 与 `/atlas`；server `_help()` 坊市行后加 /版图；cli 帮助加一行。
- 网页：web/index.html「仙门 · 坊市」卡在「议政」按钮旁加「版图」按钮（data-cmd="/版图"），文本走既有日志区，前端零逻辑。

## 边界与异常
- 散修活动不计分（无宗可归）；叛门后 sect=None，后续活动不再计（存量影响力不追溯扣除，随衰减消散）。
- 角色死亡：record 前置 DEAD/寿尽返回 0（钩子点本身都在成功结算后，属双保险）。
- KV 损坏/非 dict 形状：读降级为空表（trade_reg 先例），不炸主流程。
- 未知区域参数：/版图 面板提示可查区域列表，不报错崩溃。
- 同分并列最高：判无主，无折扣；一方再 +1 即易主（衰减后浮点比较，eps=1e-9 内视为并列）。
- 旧档兼容：无任何 sect_atlas KV 时全图皆空、价格与旧版逐字一致（新系统纯增量）。

## 验收标准
- [ ] tests/test_atlas.py 覆盖：三钩子计分（探险/委托/除凶真实引擎链路或引擎直调 + NPC 口径权重与上限）、
      每日上限（玩家/NPC、部分获准）、衰减与易主、主导判定（阈值未达/并列无主/独占）、
      价格优惠真实生效且与 F03 区域价共存的数值断言（含下限钳制、非主导与散修价格不变、同区买售无套利）、
      议政钩子（通过 +10 落总坛区域、否决不加、重复结算不重复加）、查询面板（全图/明细/未知区域）、
      双端 handle 至少 1 条（server /版图 + 闭关放行）、旧档兼容（空 KV 价格不变）、
      夹具零残留（自造角色置死、清 sect_atlas*/cap KV、恢复随机流）。
- [ ] 全量回归 0 失败（基线 381 + 新增）。
- [ ] 独立评审子代理审 diff（重点：F03 套利组合、钩子重复计数、KV 整表覆盖），必须修项整改后复跑全量。

## Out of Scope
- 版图影响跑商税率/回收价/招募数值（总纲 F09 原文提及税与招募，本最小闭环只落买价折扣 + 招募展示，税率无既有通道不新造）。
- NPC 入宗倾向数值化、版图争夺战/宣战、区域驻守玩法、版图对 F15 除凶/F07 委托收益的加成（任务书明确不做收益叠加）。
- sect_state（F08）结构变更；WORLD_LOCATIONS/SECTS_CONFIG 静态数据变更；新 AI 调用（本项零 AI）。

## 状态
- [x] 阶段一细化（本文）
- [x] 实现（引擎/钩子/价格/双端/网页）
- [x] 新增测试与全量回归：首跑 395 passed（基线 381 + 新增 14）；评审整改后定向 56 passed；整改后全量第二跑 398 passed + 1 failed（`test_qi_pace.py::test_newbie_meditation_boost`，经排查为既有随机性 flaky——新建角色灵根随机使 6h 闭关产出在 123~376 间波动，与版图代码无交集，隔离跑通过）；第三跑 **399 passed（基线 381 + 新增 18），0 失败**
- [x] 独立评审与整改
  - **必须修 1 条（已整改）**：折扣 × NPC 专柜「交好回收」无上限套利——专柜回收旧口径只认标价
    （交好恒标价×0.55、无资金池/分档约束），产地区折后买价约标价×0.52，同地买入→专柜回收可无限刷。
    本 spec §6 原套利分析只覆盖商会回收，漏了专柜通道（教训：套利分析须遍历全部卖出通道）。
    整改：`NpcShopEngine.sell` 回收价以「当地市价 × 回收率 × 态度系数」min 封顶（core/trade.py 区域锚），
    只收紧区域价低于标价之地，基准区/远方行为逐字不变；补真实闭环回归（买入 折后价 > 专柜回收，必亏）
    与全货 × 14 日波动遍历（产地折后买价恒 > 交好专柜回收价）。
  - 建议修已采纳：议政双快照 settle 只计一次的用例、除凶重入幂等用例、测试夹具区域 KV 改保存/还原、
    无 ts 的损坏 KV 降级为空表（防永不衰减的僵尸影响力）、日上限日期口径与注入时刻对齐。
  - 已知限制：KV 跨进程无事务（与仓库先例同口径）；其他模块经议政钩子写入的 atlas 状态由各模块
    自行清理，本项夹具对区域键做保存/还原以保无损。
