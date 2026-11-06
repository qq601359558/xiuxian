# F07 NPC 委托链 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F07）。基线：2bee87b（F01–F06 已合，全量 344 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：同场 NPC 可发布一条 2–4 环的系列委托（送信/寻物/除妖），玩家接取后逐环交付推进，
  全环完成得灵石/声望类奖励与低概率功法线索；链可超时作废、可主动放弃。
- **本质意图**：给「世界活着」补一条玩家↔NPC 的**事务性纽带**——现有 /交谈 是社交、悬赏是杀伐、
  议程是 NPC 自己的事，玩家始终是旁观者。委托链让 NPC 第一次「有事相求」，
  且每环都把玩家推去用既有系统（迁跃寻人、坊市/掉落备货、探险除妖），是旧系统的编排层而非新轮子。
- **关键目标**：生成→接取→逐环核验→发奖闭环可玩通且全程规则可复算；核验只认既有事实
  （位置/行囊/探险计数），不可凭空刷；奖励接取时定价写死、只发一次；与悬赏板/宗门环/目标系统边界清晰。

## 现状盘点（实测，2026-11-04）
- **NPC 体系**：NPC 是普通 Character（user_id 以 `npc_`/`ai_npc_` 开头，`core.npc_mind._is_npc`），
  由 `core/npc_roster.seed_roster` 在 World 初始化时播种，存 characters 表；
  心智在 npc_minds 表（`ensure_mind`/`attitude_toward`/`shift_attitude(npc, other_id, delta, reason)`，
  态度值无硬钳、既有增量口径 ±10 内），议程在 npc_agendas 表（`ensure_agenda`，NPC 自己的行动线）。
  同场列表 `core/here.list_here` 按 location 聚合存活角色。
- **既有任务形态（三套，须区分）**：
  | 系统 | 形态 | 与委托链的边界 |
  |---|---|---|
  | 悬赏板（core/bounty.py + bounties 表） | 玩家出钱挂赏**杀人**，击杀自动结赏，带手续费与因果仇链 | 委托**不杀人、不收钱**：NPC 出题、系统按规则定价发奖，无目标玩家 |
  | 宗门环（core/sect_contrib.sync_ring） | 宗门内日环计数（explore 等动作同步进度），宗门专属 | 委托**与宗门无关**：任何同场 NPC 可发布，散修可玩 |
  | 目标系统（core/goals.py） | 玩家自己的世间志向（六类目标源），无发布者、无交付 | 委托有**明确发布 NPC 与当面交付**，是事务不是志向 |
  | 师门/结义任务（world 指令） | 特定关系（师徒/结义）内任务 | 委托面向**任意同场 NPC**，无关系前置 |
- **探险结算钩子**：`AdventureEngine.explore` 在落账段有 `if success: sync_ring(c, "explore")`
  的 try 包裹钩子先例；explore 只被 server handle 调用（/探险 为 LAN 专有），且 handle 在
  explore 后对同一 char 对象 `CharacterRepository.save`——在同一落账段加委托计数钩子，
  即「单点落账」，无陈旧对象覆盖风险（F05 教训）。
- **落账惯例**：server/cli handle 成功才 save；引擎先校验后改状态。角色新字段带默认值 = 旧档自动补
  （F01 pets / F06 cave_level 先例）。
- **奖励数值带**：探险盘缠 20/次、聚气丹 40、EVENT_EFFECT_CAPS 的 stones_gain 上限 300、merit 上限 40。

## 关键设计决策（与备选对比）
1. **状态存角色字段（不建表）**：`Character.active_quest: Optional[QuestChain] = None`（进行中链，至多 1 条）
   + `quest_cooldown_until: float = 0.0`。链与环都是 pydantic 模型（QuestChain/QuestRing，放 core/models.py，
   F06 FarmPlot 先例）。备选新表否决：一人至多一链，角色字段足够且天然随世消散（死亡=旧世记录，
   新世新角色无链，与 F01/F06 同口径，无需死亡钩子）。
2. **可接委托（offers）存 world_state**：玩家点 /委托 时，按「当前同场 NPC」生成每人一条预览链，
   存 `WorldStateRepository` 键 `quest_offers:{player_id}`（含生成时刻），TTL 3600s 内同场 NPC 集合不变则复用——
   保证「看到的链」与「接到的链」一致（备选确定性种子重算在跨窗口边界会变链，否决）。
   接取后该 offer 移除；集合变化（迁跃/新 NPC 到场）即重生成。
3. **环的交付点统一为「当面交付」**：每环写死 `deliver_npc_id`——
   送信环 = 信件目标 NPC 本人（须赶到其**当前**所在地当面交）；
   寻物/除妖环 = 发布 NPC 本人（备齐/办妥后回其当前所在地复命）。
   核验只查三类既有事实：交付对象存活且与玩家同地点（CharacterRepository 实时查）、
   寻物环查 inventory 有货（交付扣 1 件）、除妖环查环内 progress（探险钩子计数）。
   NPC 会迁跃（agenda tick），面板动态显示交付对象当前地点，不冻结生成时地点——找人是玩法不是 bug。
4. **除妖计数只认 AdventureEngine.explore 的规则成功**：在 explore 落账段 `sync_ring` 旁加
   try 包裹钩子 `QuestEngine.note_adventure_win(c)`：当前环为 slay 且 progress<need 才 +1（封顶 need）。
   不新造战斗、不认斗法击杀玩家（防拿玩家刷环）、不认失败探险。钩子异常不炸探险结算（与既有钩子同模式）。
5. **奖励接取时定价写死、完成时一次发放**：成链即算 `reward_stones = min(封顶 200, 环数×30 + 发布者境界 tier×10)`、
   `reward_merit = 5`（存 QuestChain 字段，交付时口径不漂移）。逐环无奖励（防中途弃链套利）。
   发放与清链同一步：deliver() 全环完成 → 先清 active_quest 并写冷却 → 再入账灵石/功德——
   重复 /交付 只会扑空（无进行中链），结构性幂等（有测试钉住）。
   **功法线索**：完成时以 `QUEST_ART_CLUE_P=0.25` 掷骰（rng 可注入），命中则从
   QUEST_ART_CLUE_POOL 中取玩家未习得的第一门授入 skills（与 events.apply_effects 的 skill 授予同路径语义：
   只追加未有者）；全已习得则不发（不折灵石）。每链至多 1 门，概率与池都在常量，封顶明确。
6. **冷却与上限防刷链**：同时进行中链上限 `QUEST_MAX_ACTIVE=1`；链了结（完成/放弃/过期作废）后
   全局接取冷却 `QUEST_ACCEPT_COOLDOWN_SECONDS=600`（防「接→弃→再接」洗链挑环）。
   链有效期 `QUEST_CHAIN_TTL_SECONDS=86400`（现实 24h），惰性判定：任一委托指令先 settle。
   过期/放弃**无惩罚**（灰度口径：委托是帮忙不是契约，惩罚会抑制尝试；防刷靠冷却不靠罚）。
7. **与 agenda 共存（轻量）**：全环完成时 `shift_attitude(发布NPC, 玩家id, +8, "完成委托")`
   （既有态度口径）+ `jianghu.append_event(kind="quest", ...)` 落一条世情播报。不改 agenda 本身、
   不新造好感系统；发布 NPC 已陨落时跳过态度（事件仍落，actor 缺席不炸）。
   当前环**交付对象**在交付前陨落 → 该链当场作废无惩罚（deliver 时判定，面板亦标注）；
   发布者若不是当前环交付对象，其陨落不作废全链，完成时仅跳过态度（评审 S6 口径统一）。
8. **可用性口径**：闭关（MEDITATING）四指令**均不进**双端白名单（接取/交付带状态写、面板带惰性作废结算，
   与 F04 /典当 查看同口径锁门）；死亡：/委托 查看放行（遗容，含惰性结算），接取/交付/弃委托由引擎 DEAD 拒绝
   （DEAD 校验前置于结算，死人指令零副作用，F04 S2 先例）。

## 完善后的规则闭环（行为契约）
### 常量（core/quests.py 模块常量）
- `QUEST_MAX_ACTIVE = 1`、`QUEST_CHAIN_MIN_RINGS = 2`、`QUEST_CHAIN_MAX_RINGS = 4`
- `QUEST_CHAIN_TTL_SECONDS = 86400`、`QUEST_ACCEPT_COOLDOWN_SECONDS = 600`、`QUEST_OFFER_TTL_SECONDS = 3600`
- `QUEST_REWARD_STONES_PER_RING = 30`、`QUEST_REWARD_TIER_BONUS = 10`、`QUEST_REWARD_STONES_CAP = 200`
- `QUEST_REWARD_MERIT = 5`、`QUEST_ART_CLUE_P = 0.25`、`QUEST_ATTITUDE_DELTA = 8`
- `QUEST_FETCH_ITEMS = ["妖兽内丹", "百年灵芝", "聚灵草", "灵谷"]`（均在 ITEM_CATALOG，可买可掉）
- `QUEST_ART_CLUE_POOL = ["裂风斩", "寒冰诀", "厚土诀", "流云步"]`
- `QUEST_SLAY_NEED_RANGE = (1, 2)`
- 环模板池 `QUEST_RING_TEMPLATES`：每 kind 2–3 条本地口吻模板（规则文案，零 AI）。

### 数据（core/models.py，只加带默认值的字段/模型）
- `QuestRing`：kind（deliver/fetch/slay）、desc（模板文案）、deliver_npc_id、deliver_npc_name、
  item_name（fetch 用）、need（slay 次数；fetch 恒 1）、progress（slay 已计数）。
- `QuestChain`：id（8 位 uuid）、publisher_id、publisher_name、rings、ring_index、
  accepted_at、expires_at、reward_stones、reward_merit。
- `Character.active_quest: Optional[QuestChain] = None`、`Character.quest_cooldown_until: float = 0.0`。

### 引擎（core/quests.py · QuestEngine，规则单点）
- `generate_chain(publisher, player, rng) -> QuestChain`：环数 rng 2–4；环 kind 轮选（相邻不同 kind；
  无其他存活 NPC 时禁用 deliver 环）；deliver 目标 = 随机一名其他存活 NPC；fetch 物品 rng 出池；
  slay need rng 1–2；奖励按公式定价（accepted_at/expires_at 接取时才写）。
- `offers_for(player, now=None, rng=None) -> List[(npc, QuestChain)]`：取同场存活 NPC（list_all_alive 过滤
  location 与 _is_npc），命中 world_state 缓存（TTL 内且 npc 集合一致）则复用，否则重生成并落 KV。
- `settle_expired(char, now=None) -> bool`：active_quest 已过期 → 清链 + 写冷却，返回是否变更。
- `accept(char, hint, now=None, rng=None) -> res`：DEAD 拒绝 → 先 settle → 已有链拒绝 → 冷却中拒绝 →
  按 hint（序号或 NPC 名子串）在 offers 中定位 → 链落 char.active_quest（写 accepted_at/expires_at）、
  offers 移除该条。不在同场/无此 offer → 失败文案。
- `deliver(char, now=None, rng=None) -> res`：DEAD 拒绝 → settle（过期则报作废）→ 无链失败 →
  交付对象陨落 → 作废清链（无惩罚）→ 不在交付对象当前同地点 → 失败（文案给出其当前地点）→
  fetch 无货 → 失败（不扣物）；slay progress<need → 失败（报进度）。
  成功：fetch 扣 1 件；ring_index+1；未完环 → 报下一环；全环完 → 按决策 5 发奖 + 态度 + 世情 + 清链 + 冷却。
- `abandon(char, now=None) -> res`：DEAD 拒绝 → 无链失败；成功清链 + 冷却，无惩罚。
- `note_adventure_win(char) -> None`：探险钩子（见决策 4），无链/非 slay 环静默。
- `panel_text(char, now=None) -> str`：先 settle（调用方负责 save 变更）；有链：发布者、环进度、
  当前环 desc + 核验进度 + 交付对象与其实时地点、到期剩余；无链：offers 列表（编号/NPC/环数/奖励预告/首环）
  + 接取提示；同场无 NPC 给空文案。交付对象已陨落时标注「已陨落，交付即作废」。

### 指令（server/world.py 与 cli/main.py 双端一致，成功或 settle 变更才 CharacterRepository.save）
- `/委托`（/quests）：面板。`/接委托 <NPC名|编号>`（/acceptquest）：接取。
- `/交付`（/deliver）：交付当前环。`/弃委托`（/abandonquest）：放弃。
- server `_help()` 与 cli 帮助各加委托行；server 闭关白名单不加（决策 8），CLI 闭关放行名单不加。

### 网页
- web/index.html 同场修士卡的 hereList 后加 btn-grid：委托（data-cmd="/委托"）、
  接委托…（data-prompt，prefix /接委托，placeholder「同场 NPC 名」）、交付（data-cmd="/交付"）、
  弃委托（data-cmd="/弃委托"）；web/app.js hints 加 接委托 一条。前端零逻辑改动。
- _status_dict 新增 `quest`（None 或 {publisher, ring: "x/y", kind}，纯新增）。

### AI 边界
- 零新增 AI 调用、零 AI 决策：环目标/奖励/文案全规则模板；AI 在线时也不参与委托（spec 明示，
  与 F03/F04/F06 本地模板口径一致）。

## 边界与异常
- 同场无 NPC / 发布者就是唯一 NPC（deliver 环禁用、链仍可生成）/ 接取时 NPC 已离开同场（offers 按
  生成时同场集合，接取时复核发布者仍同场，否则该 offer 失效并刷新）/ 重复接取与已有链时接取（拒绝）/
  冷却中接取（报剩余秒）/ 到错地点交付（文案给当前地点）/ 寻物无货（不扣物不推进）/
  除妖计数未满 / 当前环交付对象陨落（作废；发布者非交付对象时陨落不作废，见决策 7）/ 过期后在面板与交付两路径惰性作废 /
  功法线索池全习得（不发）/ 奖励封顶（公式极值 210，封顶 200 真实生效）。
- 并发：server handle 世界锁串行；CLI 单进程。引擎先校验后改状态，失败不落改动（settle 的过期清链除外，
  其本身即结算动作，调用方 save）。
- 旧档兼容：纯角色新字段（带默认值）+ world_state 新键，无新表无改表；无链角色全部委托指令正常空跑。

## 验收标准
1. tests/test_quests.py 覆盖：链生成结构（2–4 环、kind 相邻不同、deliver 目标为他人、奖励公式与封顶）、
   接取（成功落链/已有链拒绝/重复接取拒绝/冷却拒绝/不在场 NPC 拒绝）、送信环（错地点失败、到对地点推进）、
   寻物环（无物失败、有物扣 1 推进）、除妖环（探险钩子计数、未满交付失败、满后推进）、
   全链完成发奖（灵石/功德到账、态度 +8、重复交付不重发）、过期作废（面板与交付两路径）、弃链（清链+冷却）、
   发布者陨落作废、server handle 至少 1 条全链路（含闭关锁门）、CLI 源码对齐（与既有 parity 口径一致，
   由双端同引擎 + server 全链路兜底）、旧档反序列化兼容。
2. 全量回归 0 失败（基线 344 + 新增）。
3. 独立评审子代理审 diff（重点：核验钩子可刷性、奖励幂等、与悬赏板重复造轮子），必须修项整改后复跑全量。

## Out of Scope
- 玩家对玩家发布委托、多人协作同一链、连环长篇剧情链（>4 环）与分支抉择环。
- 委托专属物品/信物实体化（送信凭手令无实物，不占行囊）。
- 按好感/议程动态定价、NPC 主动找玩家派单（npc_proactive 范畴）、委托排行榜。
- F15 除凶令状态机对悬赏板的收尾（本项只做边界区分，不动 bounty 语义）。

## 评审整改（独立 Review 后，2026-11-04）
- **[必须修 M1] deliver 核验分发 fail-open**：未知 kind 原会穿过核验段直接推进发奖。
  已改 fail-closed： kind 白名单（deliver/fetch/slay），未知 kind 与下标越界同口径作废清链、不发奖，
  并补回归用例（test_unknown_ring_kind_fails_closed）。
- **[建议修 S1] panel_text 内置 settle**：惰性结算收进引擎面板自身，直调方不再看到过期链「进行中」；
  双端 handle 的先行 settle 保留（重复 settle 幂等）。
- **[建议修 S2] offers 逐 NPC 复用**：缓存新鲜时按 NPC 逐条复用预览链，仅新到场者现生成——
  接走一条不再连带其余预览整表重掷，「所见即所接」更严。
- **[建议修 S3] 定价 docstring 订正**：封顶 220 → 200（与常量一致，min() 本已正确生效）。
- **[建议修 S4] offers 缓存容错**：world_state 中 at 被写坏成非数值时按过期处理，不再抛错。
- **[建议修 S5] 测试补口**：新增 DEAD 三指令前置拒绝且零副作用用例；
  新增 server handle「接取的原链不换链、全程交付落库」用例（逐环构造核验条件真推进）。
- **[建议修 S6] 口径回写**：发布者陨落口径统一（见决策 7 与边界清单修订）；accept 上限改显式引用
  QUEST_MAX_ACTIVE 常量。
- 评审确认无问题：除妖钩子单点落账只认规则成功、封顶与速率门齐全，不可刷；发奖先清链后入账、
  异常不落库，结构性幂等且封顶真实；与悬赏板（bounty 独立表/玩家出钱/击杀结赏）、宗门环
  （sect_contrib 独立计数）、目标系统（goals 未触碰）边界清晰，无重复造轮子；其余契约逐条符合，
  双端 save 口径一致，web 纯入口。

## 状态
- [x] 阶段一细化（本文）
- [x] 实现（模型/引擎/探险钩子/双端/网页）
- [x] 新增测试与全量回归（整改后复跑见交付报告）
- [x] 独立评审与整改（必须修 1 项 M1 + 建议 S1–S6，已整改）
- [ ] Finalize：合并与打版由总纲统一收尾（本分支不自行合并）
