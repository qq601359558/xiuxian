# Spec：AI 天道事件链（karma-event-chains）

状态：待总管确认（主策产出，未开工）
基线：main `1cdcee9`（v0.3.0-gray.7），全量回归基线 689 passed / 0 failed
目标版本：v0.3.1-gray.8（版本号由发布岗最终裁定）
开发序列：Martinez 已拍板序列第二项（① 转世继承已交付 → ② 本轮 → ③ 真人试玩）

设计目标一句话：让玩家实感「世界在记事」——事件不再是一次性的，
施恩会等来报恩、结仇会招来报复、许过的诺言会被追着兑现，前因后果
串成一条玩家可查的因果链，把「AI 主导」招牌立起来。

---

## 0. 现状盘点（实证；文件/函数均为本轮逐个核读，非转述）

### 0.1 总管盘点已核实无误的事实

- `KarmaLink` 在 `core/bounty.py:75`：`a_id/b_id/link_type/strength/note`，
`link_type` 配置口径 `KARMA_LINK_TYPES=("仇","恩","师徒","宗门")`
（config.py:337），野外实际还存在 `诺`（promises 结算写）、`结拜`
（social_bonds）、`怨/断`（legacy 折算映射提及）等值；存储
`KarmaLinkRepository`（storage/db.py:625），全量 `list_all()` 读。
- `core/collusion.py:20` `ensure_link(a, b, link_type, note, now)` 是
upsert 式写入（同对同型已有则 `strength += 1` 并保存，否则新建
strength=1）；`links_of/links_between` 为读口。`BountyEngine.
ensure_feud_link`（bounty.py:357）是同语义的内存列表版（CLI 击杀后用）。
- 诺言账 `core/promises.py`：`Promise` + `PromiseEngine`，四类
gift/arrive/quest/no_attack，ttl 3~7×86400 现实秒，终态
KEPT/BROKEN/DISSOLVED 不可逆；`PromiseRepository`（db.py:762）；
`_settle` 是**唯一写终态入口**，先落终态存库（锚）再发效果，
终态重复触发短路——本轮幂等设计直接沿用此范式。
既有结算数值：`PROMISE_MERIT_KEPT=10`、`PROMISE_SIN_BROKEN=15`、
`PROMISE_ATTITUDE_DELTA=8`、`PROMISE_MAX_OPEN=3`。
- NPC 心智 `core/npc_mind.py`：`ensure_mind / attitude_toward /
shift_attitude(npc, other_id, delta, reason="")`；态度账在
`npc_minds` 表（`NpcMindRepository.set_attitude`，值钳 -100..100，
label 阈值 hostile ≤-40 / wary ≤-15 / friendly ≥15 / ally ≥40）；
`on_kill_update_attitudes(attacker, defender)`（击杀者对死者 -80、
同宗 NPC -45、记仇性格再 -15、同场 -20）。
- NPC 议程 `core/npc_agenda.py`：`NpcAgendaEngine.tick_one /
tick_world(max_npcs, force=False)`，单 NPC 冷却
`TICK_COOLDOWN_SECONDS=180`；`tick_world` 尾部顺带
`try_collude_in_world`、`maybe_flee_npc`、`rumors.maybe_ambient_tick`，
全部 try/except 包裹——本轮链推进挂点照此先例。
世界 tick 入口：`server/world.py` `World._tick_loop`（间隔
`NPC_TICK_INTERVAL_SECONDS`，默认 120s）调
`tick_world(max_npcs=3)`；`server/app.py` 开服
`tick_world(max_npcs=3)`、关服 `tick_world(max_npcs=8, force=True)`；
server `/tick`、`/世情` 与 CLI `/世情` 亦调 `tick_world`。
- 编年史 `ChronicleRepository`（db.py:837，`record(event_type,
actor_name, summary)`，只增不改）；`JianghuEventRepository`
（db.py:864）经 `core/jianghu.py` `append_event(...)` 写入，
public 事件自动同步一条 Chronicle；`EventLedgerRepository`
（db.py:931，角色级长期记忆账）；`WorldStateRepository`
（db.py:367，KV 整值 JSON 读改写）。
- 奇遇事件链 `core/event_chains.py` 已存在：2–3 步**交互式机会链**，
`WorldStateRepository` key=`event_chains`，每玩家至多 1 条 active，
全服上限 `EVENT_CHAIN_MAX_ACTIVE_GLOBAL=8`，超时
`EVENT_CHAIN_TIMEOUT_MIN=30` 分钟，效果经 `_clamp_effects`
钳 `EVENT_EFFECT_CAPS`。**新模块不得叫 event_chains**；
本轮新模块定名 `core/karma_chains.py`，边界见 §0.3。
- 转世继承 `core/inheritance.py`（v0.3.0 已交付）：死亡时态度
|v|≥30（`SHADOW_MIN_ABS`，top 6）+ KarmaLink 折叠成因果影子，
×0.4 衰减（`SHADOW_RETENTION`）、±25 封顶（`SHADOW_CAP`）、
<8 舍弃（`SHADOW_APPLY_MIN`）；未履诺言只做文字回声不重记账
（`LifeTrace.open_promises`，源头 `PromiseEngine.on_owner_death`
返回的消散摘要）；全部新状态在 `LegacyAccount` 新字段，
`Character` 模型未动；`LegacyEngine.settle_death` 有
trace 存在性崩溃重放闸门（MF-1）；领取类动作有
`inheritance_claims` 按世次标记。本轮死亡衔接与之对齐，见 §7。
- `core/memory.py` 有 `RevengeEngine.maybe_callback(character,
chance=0.35) / force_callback(character)`：从 `EventLedger`
的仇怨类事件（`query_feud_pairs` 只认 type ∈
KILL/BOUNTY/FEUD/FREE/COMBAT/REVENGE）续写回访叙事，效果经
`ai.gate.gate.admit` 清洗后走 `EventEngine.apply_effects`，
escalate 时可 spawn NPC。调用点：server `_go`（chance=0.25）、
server/CLI `/回访`（force）、app 关服（chance=0.4）。
与新链的关系裁定见 §0.2 末与 §4.5。
- 传闻 `core/rumors.py`：`add_rumor(text, origin, tags, truth, now)`，
池上限 40、TTL 7 现实日，WorldState key=`rumor_pool`；
有 `note_kill / note_collusion` 等规则侧写入先例。
- 心魔 `core/heart_demon_state.py`：`DemonStateEngine` 纯推导
魔念，杀业增量经 `SIN_SEED_FACTOR=0.5` 折算——链结算若加业力，
会经既有管道间接喂魔念（涟漪，见 §1.4），本轮不直动魔念。
- 目标 `core/goals.py`：`GoalEngine`，`fame` 目标的 sync 读
`jianghu.project_related`——链了结写 jianghu 事件后可能被其
计数，属既有口径的自然结果，本轮不新增目标源（见 §12）。
- 时间口径 `config.py:34-36`：`SECONDS_PER_GAME_YEAR=86400`
（1 游戏年 = 1 现实日，寿元铁律）、`SECONDS_PER_GAME_MONTH=
7200`、`SECONDS_PER_GAME_DAY=240`（1 游戏日 ≈ 现实 4 分钟）；
`core/clock.py` `WorldClock.format_game_time` 与之同源。
纪元 `SEASON_DAYS=84` 指**现实日**（core/season.py）。
- 效果上限体系 `config.py:675` `EVENT_EFFECT_CAPS`：
exp 800 / stones_gain 300 / stones_lose 200 / lifespan_gain 15 /
lifespan_burn 8 / sin 40 / merit 40 / dao_heart 幅度 20；
各子系统自设更严子顶（council `COUNCIL_EFFECT_CAPS`、
quests `QUEST_REWARD_STONES_CAP=200`、promises 上列常量、
heart_demon 入魔档 道心-20/业力+40 恰贴 caps）——本轮链结算
照此惯例自设子顶且严于 caps，见 §4.4。
- 双端命令注册先例（/墓碑）：引擎同源文本在
`core/inheritance.py` `find_tombstone`；server
`World.handle` 分支（world.py:736）与 CLI 分支
（cli/main.py:590）同命令同文案；Web 经通用 `/action` 文本
feed 呈现，无前端专属改动。本轮 /因果链 照此落地，见 §6。
- 存储扩表先例：`init_db()` 以 `CREATE TABLE IF NOT EXISTS`
只加新表（6b 典当 / 6c 著书 / 6d 诺言），仓储类照
`PromiseRepository` 写法（id 主键 + data_json + 状态/归属
列）。本轮存储选型沿此先例，见 §2.4。

### 0.2 与总管初步盘点的出入（4 处，Spec 已按实证修正）

1. **server 击杀不结悬赏**：`BountyEngine.settle_on_kill` 全仓
只有 CLI 击杀段（cli/main.py:1863）调用；server
`World._fight`（world.py:3108）只记 KILL 大事记，不调
settle_on_kill。→ 起链来源 (c) 的悬赏支必须挂在**引擎层**
（settle_on_kill 内部），server 端在该既有分歧修复前天然
不触发悬赏支（不恶化、不假装覆盖）；是否顺修 server 结赏
列为待裁决点 C-1（§13），本 Spec 默认 Out of Scope。
2. **`/因果` 双端语义已然分叉**：server `/因果` = `/回访`
别名（`RevengeEngine.force_callback`，world.py:1623）；
CLI `/因果` = KarmaLink 列表（`BountyEngine.list_links_for`
+ `render_karma_links`，cli/main.py:982）。→ 新查询命令
**不得复用 /因果**，定名 `/因果链`（见 §6）。
3. **「日」字口径不统一**：promises 的 ttl 以 86400 现实秒
为「日」（实为 1 游戏年）；奇遇链以分钟计；纪元以现实日计。
→ 本轮链计时**只认 `SECONDS_PER_GAME_DAY=240`** 并在 §2.3
写死换算，文案中的「日」一律指游戏日，禁止借用 promises
的「日」口径。
4. **「恩」KarmaLink 无 ensure_link 生产者**：全仓 `ensure_link`
调用点只写 仇/师徒/结拜；「恩」只由 `core/social_bonds.py`
出师流程（约:226）把既有师徒链**原地改型**为 恩 并保存
（不经 ensure_link、无 strength 自增）。→ 来源 (a) 的链路
支须分两钩：ensure_link 自增达阈（仇为主）+ 出师改型点
显式注记（见 §3 S2/S2b）。

### 0.3 与既有「链」类系统的边界（防命名/语义撞车）

| 系统 | 性质 | 与本轮关系 |
|---|---|---|
| `core/event_chains.py` 奇遇链 | 随机触发、交互式选择、即时落账的机会链 | **互不调用**：因果链非交互、无选项、不占奇遇的单 active 名额；奇遇不读因果链 |
| `KarmaLink` 因果（关系边） | 无状态的关系事实账（谁与谁有何恩怨） | 因果链的**输入之一**（达阈起链）；链不改写 link 语义，了结不删 link |
| `RevengeEngine` 复仇回访 | 概率触发的即时叙事回访（会话级） | **共存分工**：回访管「戏」，因果链管「账」——确定性定时、可查、防双重重惩见 §4.5 |
| `JianghuSimulator.cascade_kill` | 击杀即时涟漪（仇边/宗门议程→寻仇/传闻/频道） | 即时层归它；因果链只做**延迟层**记录与到期 reckoning，不重复即时结算 |
| 因果影子（inheritance） | 死亡跨世的态度折算 | 死亡时未了链不进影子、不另记账，见 §7 |
| `core/hunt.py` 除凶令 | 血煞目标的接令/围剿/结算状态机 | 非独立起链源：其击杀与 S4 同一击杀事实，经 S4 去重合并（见 §3） |

### 0.4 呈现通道现状（§4.3/§6 引用）

- NPC 主动上门：`NpcProactiveEngine.maybe_engage`（core/
npc_proactive.py）由 server `_go` 与 CLI 迁跃段在落点调用，
按态度 label 给开口概率（hostile 0.55 / ally 0.50…），
AI 预算 + 本地模板双路。本轮**不改其触发逻辑**；链到期
结果以「同场则当场留话、异地则传闻+江湖账+面板近史」
方式借道（见 §4.3），不伪造其内部状态。
- 世界频道：`WorldChannel.post(kind, text, level, actor,
location)`（core/world_channel.py），60s 同 kind+actor
去重 + 每分钟限流——只给血仇了结用（major），防刷屏。
- 江湖账：`core/jianghu.py` `append_event` 为结构化世界事件
唯一写入口，public 自动同步 Chronicle 一条。
- 面板近史先例：`PromiseEngine.panel_text`（进行中 + 近史
5 条，`PROMISE_HISTORY_N=5`）；`settle_due` 在面板前由
server `/诺言` 分支（world.py:1297-1303）与 CLI 同名
分支先行调用——链面板照此「先推进后呈现」。

---

## 1. 五步推演（requirement-evaluator 全文）

### 1.1 第一步 · 解构本质

- **表层需求**：新增「AI 天道事件链」——把施恩/结仇/诺言等
事件串成可查的因果链，延迟兑现报恩/报复/追诺。
- **本质诉求**：当前世界「记事」是**只写不回**的：KarmaLink、
态度、诺言、江湖账都在记，但记完即沉底——玩家施恩后 NPC
态度变了却再无下文，结仇的后果只有即时涟漪（cascade 当场
播完即止），诺言终态结算完就进近史。玩家感受不到「天道
有记忆」，「AI 主导」招牌因此立不住：AI 现在只润色当场
的一句话，没有**跨时间**的叙事纵深。
- **真正缺口**：不是缺账本（账本有五套），而是缺一条
**「延迟兑现」管道**：重大因果在发生时被登记为一条有时限、
有强度、有状态的待办，到期由规则引擎确定性地兑现一次
后果，并把「前因→后果」整条链呈现给玩家查。
- **验收本质**：一名玩家在施恩/结仇/践诺/毁诺/行凶之后的
一次正常游玩会话内（或跨会话回来时），能在 `/因果链`
里指着一条链说出「这是我哪天对谁做了什么，它发酵到
几成、后来怎样了结」；且到期后果真实落账（态度/灵石/
功德业力之一发生变化）而非只播一段文案。

### 1.2 第二步 · 可行性评估

- **技术可行性：高。** 全部输入都是既有事实源且都有唯一
结算点：态度（shift_attitude 单点）、关系边（ensure_link
单点）、诺言（_settle 单点）、击杀（resolve_ambush /
cascade_kill 双引擎点）、悬赏（settle_on_kill 单点）。
推进可寄生 `tick_world` 尾部（先例三个顺带推进皆如此），
无需新线程/新调度。存储有「只加新表」成熟先例。
- **成本**：新模块 1 个（core/karma_chains.py）+ 新仓储 1 个
+ 配置常量一组 + 5 处 try/except 钩子 + 双端 1 条命令 +
tick 尾 1 处 + 死亡钩子 2 处（server/CLI 各一，与既有钩子
同位）。无既有接口签名变更，无 Character/LegacyAccount
模型变更。
- **性能**：链量被硬顶钳住（全服 active ≤40，见 §8）；
tick 每轮至多推进 5 条到期链 + 10 条发酵迁移，均为按
player/counterparty 列过滤的 SQLite 查询，量级与
promises `list_all` 全扫相当或更低。态度钩子在
shift_attitude 内只做一次整数比较（未跨阈直接返回），
热路径（交谈 ±10 内小步进）开销可忽略。
- **ROI**：不新建任何账本/表外状态，复用五套既有事实源与
四条既有呈现通道，是「用 20% 新代码撬动既有 80% 沉淀」
的典型高 ROI 形态。反之若另起一套事件总线或给 NPC 加
记忆数据库，成本翻倍且与影子/诺言重复记账——已否决
（见 §1.5 备选）。

### 1.3 第三步 · 不足与盲区（逐条已在设计中堵住，标注落点）

1. **[双重记账]** 诺言终态已结算功德/业力/态度，链再兑现
一次是否双罚/双赏？→ 链定位「延迟的关系性余波」，
数值刻意取小且与诺言即时结算不同账目
（§4.4 公式与总账表 §8.3）；毁诺链以传闻昭告为主、
数值仅象征性业力 +5。死亡时与影子/诺言回声的互斥
判定见 §7.2。
2. **[双重报复]** 击杀已触发 cascade_kill（同宗议程当场
转寻仇）+ RevengeEngine 概率回访 + 除凶/悬赏结算，
链再报复一次即三重追打。→ 血仇链**不直接扣玩家数值**
（除小额业力），其「牙齿」是发酵时把兑现者议程**再次**
确认为寻仇（与 cascade 同动作、幂等覆盖）与到期昭告；
真实战斗仍只由既有议程/斗法系统发生（§4.5 裁定）。
3. **[起链刷屏]** 态度小步进频繁（交谈 +1、成交 +3）：
若按「达阈即起链」扫描式实现，一次长谈可连起多链。→
只认**跨阈事件**（before < 60 ≤ after），跨过后天然
迟滞（再起须先跌回 ≤50 再跨），加 active 去重 + 对偶
冷却双保险（§3 S1、§8）。
4. **[NPC 已死/不存在]** 恩链对象在发酵中被别人杀了、
血仇链的死者同宗已绝：到期无兑现者。→ 每条链在推进
时做存活检查，兑现者按规则现选/降级消散，逐状态
写清（§2.3、§4.2）。
5. **[玩家死亡/转世]** 链以角色 id 为主体，死亡即旧世
终结；若链随转世复活则与「诺言消散」「影子折算」
两套既有裁定冲突。→ 一律消散、不进留痕、不折算，
理由与判定方法见 §7（与影子分工：影子带走的是
**态度值本身**，链不带走任何东西）。
6. **[离线发酵]** 玩家下线期间 tick 仍在跑（server
_tick_loop），链可能在其离线时到期。→ 到期结算不
依赖玩家在线（角色行在库中即可落账），呈现走持久
通道（江湖账/大事记/面板近史），玩家回来查得到；
WorldChannel 只作血仇昭告，不作唯一通知。
7. **[崩溃重放]** tick/钩子在「已落效果未落状态」或
反之崩溃会双发/丢失。→ 全链沿 promises 范式：
**先落终态锚再发效果**（at-most-once 数值），逐点
语义见 §5。
8. **[套利]** 施恩刷链领赏、恩仇反复横跳、 alt 互刷：
→ §8 经济账：领赏期望恒小于施恩成本、同对翻转
链只叙事不落数值、每日兑现预算与灵石子顶。
9. **[AI 依赖]** 若链推进要等 AI 生成台词，AI 故障即
断链——与「世界在记事」的可靠性诉求相悖。→ 数值/
时序/状态机 100% 规则，AI 只在最后一步润色一句
台词且有本地模板全覆盖（§9）。
10. **[存量兼容]** 旧存档没有链、老角色态度已 ≥60：
上线瞬间是否补起一地链？→ **不追溯**：只认上线后
发生的跨阈/终态/击杀事件（与心魔 seed「首同步只建
基线不追溯」同裁定）；旧存档兼容验收见 K-17。

### 1.4 第四步 · 举一反三

- **横向（同类系统）**：本仓已有三种「延迟/状态机」范式
——promises（惰性 settle_due + 唯一终态入口）、心魔
（惰性推导 + 锚点）、除凶令 hunt（WorldState 状态机）。
因果链取 promises 范式为主（显式状态 + 终态锚），
因为链需要**可查的历史**，惰性纯推导（心魔式）给不出
节点账；取 hunt 的教训：不用 WorldState 整包存状态机
（hunt 三套 KV 键已显拥挤）。
- **横向（其他事实源）**：宗门叛门（social_bonds shift
-20）、行窃被擒（chat_actions -50/-40）、委托完成
（quests +8）等态度事件都经 shift_attitude 单点——
S1 跨阈钩子天然覆盖它们，无需逐个埋点；这正是把钩子
放在 shift_attitude 而非各业务点的原因。
- **纵向（演进）**：本轮只做 玩家↔NPC。数据模型预留
`counterparty_kind` 字段（本轮恒 `"npc"`），将来若做
玩家↔玩家链（需处理双离线/双死亡），可同表扩展而
不迁移；本轮不实现（Out of Scope）。
- **涟漪**：
- 链结算的 attitude 变化会进 npc_minds → 死亡时被
影子快照读取（§7.2 判定为**正确单记**：影子带的
是态度值，链只是态度变化的来源之一，与赠礼/交谈
同性质）。
- 链结算的 sin 变化经 `add_sin` → 血煞标记与心魔
魔念推导（SIN_SEED_FACTOR）都按既有口径响应，
本轮不豁免、不加倍。
- 链了结写 jianghu public 事件 → `GoalEngine` fame
目标 sync 可能计数、编年史多一条——既有口径，
不特殊处理。
- tick 尾新增推进 → `_tick_loop` 单轮时长增加有界
（§1.2），且全程 try/except，异常不炸世界 tick
（与 auction advance 同例）。

### 1.5 第五步 · 完善方案（收敛为 §2–§9 的设计）

- **推荐方案**：新模块 `core/karma_chains.py`（模型 +
`KarmaChainEngine`）+ 新表 `karma_chains` +
`KarmaChainRepository`；五处规则钩子（shift_attitude
跨阈 / ensure_link 达阈 / promises._settle 终态 /
resolve_ambush·cascade_kill 击杀 / settle_on_kill
悬赏）全部 try/except 惰性调用；推进挂 `tick_world`
尾 + 查询命令惰性推进；呈现走 jianghu/rumors/
chronicle/同场留话四通道；双端 `/因果链` 同源面板。
- **备选 A（已否决）**：链存 WorldState KV（照奇遇链）。
否决：链是多主体、长周期、需按对偶/状态过滤与终态
历史留存的数据，KV 整包读改写在 tick 与命令并发下
有覆盖丢写风险，且无行级幂等锚；奇遇链能用 KV 是
因其每玩家至多 1 条、30 分钟即弃，量级完全不同。
- **备选 B（已否决）**：链挂 LegacyAccount（照影子）。
否决：链是**一世内**（角色键）状态，账户层是跨世层；
混放既污染账户行、又天然诱导「转世带链」与 §7 裁定
冲突，且 NPC 主体链无处安放。
- **备选 C（已否决）**：不起新表，把链塞进 KarmaLink
的 note/strength。否决：KarmaLink 无状态机/时间/节点
字段，硬塞即毁掉关系账的只读事实语义，且
render_karma_links、影子折算等多处读方会被污染。

### 1.6 真正需求条目（收敛，后续唯一依据）

- RQ-1 重大因果（§3 五源）发生时，系统登记一条因果链：
主体玩家、对象 NPC、类型、强度、起因节点，落账可查。
- RQ-2 链按游戏日发酵（潜伏→发酵），到期由规则引擎
一次性兑现后果（数值 + 叙事），全程不需要玩家操作、
不依赖 AI 可用。
- RQ-3 玩家可双端以 `/因果链` 查自己进行中的链（谁/
因何/发酵几成）与最近了结史（结果如何）。
- RQ-4 任何单链兑现的数值都被子顶钳住（§4.4），且
全系统存在防刷/防套利硬顶（§8）：刷链期望收益为负。
- RQ-5 死亡/转世时未了链按 §7 消散，与影子、诺言回声
零双重记账；旧存档零迁移可读。
- RQ-6 链的每一次状态迁移与兑现都有持久留痕
（链节点 + jianghu/chronicle 至少其一），可复盘。

---

## 2. 数据模型与存储

### 2.1 模型（新文件 `core/karma_chains.py`，Pydantic，照 Promise/EventChain 先例）

```python
class ChainNode(BaseModel):
ts: float = 0.0 # 现实时间戳（time.time()）
game_day: int = 0 # 链内相对游戏日（自 created_at 起算，§2.3）
type: str = "" # origin|strengthen|ferment|rumor|resolve|dissipate|death
summary: str = "" # 本地模板句（AI 润色只替换 resolve 节点的呈现副本，不回写本字段，见 §9）
effects: Dict[str, Any] = Field(default_factory=dict) # 本节点落账摘要（resolve 时为兑现明细）
source_ref: str = "" # 起源事实引用（promise id / link id / ledger event 摘要等）

class KarmaChain(BaseModel):
id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
chain_key: str = "" # 幂等/去重键（§3 各源格式），引擎层唯一性校验
kind: str = "" # en|chou|nuo|xue（恩/仇/诺/血仇）
polarity: int = 0 # +1 恩向（对象欠主体）| -1 仇向（对象记恨主体）；nuo 由终态定：KEPT=+1，BROKEN=-1
player_id: str = "" # 主体（恒为玩家角色 id）
player_name: str = ""
counterparty_id: str = "" # 对象（本轮恒为 NPC 角色 id）
counterparty_name: str = ""
counterparty_kind: str = "npc" # 预留字段，本轮只写 "npc"
delivery_actor_id: str = "" # 兑现者（en/chou/nuo = 对象本人；xue = 到期现选的同宗 NPC，发酵时预选、到期复核，§4.2）
delivery_actor_name: str = ""
strength: int = 1 # 1..8（KARMA_CHAIN_STRENGTH_CAP）
status: str = "latent" # latent|fermenting|resolved|dissipated（§2.2）
origin_summary: str = "" # 起因一句话（面板展示，本地模板）
created_at: float = 0.0
ferment_at: float = 0.0 # 进入发酵的时刻（created + duration/2，落账时算定）
mature_at: float = 0.0 # 到期时刻（created + duration，落账时算定）
deadline_at: float = 0.0 # 兑现窗口尽头（mature + WINDOW，逾期未兑现则消散）
resolved_at: float = 0.0
budget_deferred: bool = False # R1/MF-3：曾被每日兑现预算暂缓的持久标记（豁免 §4.2/§8.1；只增字段，旧行缺省 False)
resolution: Dict[str, Any] = Field(default_factory=dict)
# {outcome: repaid|retaliated|honored|shamed|avenged|fizzled,
# effects: {...实际落账...}, narrative: str}
flipped: bool = False # 恩仇翻转降级标记（§8.2：True 时兑现只叙事不落数值）
nodes: List[ChainNode] = Field(default_factory=list) # 上限 KARMA_CHAIN_MAX_NODES=12
```

字段纪律：只增不改语义；`resolution.effects` 是兑现数值的
**唯一对账依据**（QA 按此核账，不以文案为准）。

### 2.2 状态机

```
起链（§3 任一源）
│
▼
┌─────────┐ age ≥ duration/2 且推进轮到
│ latent │ ───────────────────┐
│ 潜伏 │ ▼
└─────────┘ ┌────────────┐
│ │ fermenting │
│ │ 发酵 │
│ └────────────┘
│ │ │
任一消散事由（§2.3 表） │ │ age ≥ duration
│ │ ▼
▼ │ 兑现（§4.2/§5 锚定序）
┌────────────┐ │ │
│ dissipated │ ◄───────────┘ ▼
│ 已消散 │ 窗口逾期/无兑现者 ┌──────────┐
└────────────┘ │ resolved │
▲ │ 已兑现 │
└──────── 任一消散事由 ──────└──────────┘
（resolved 为终态，不可再迁移）
```

合法迁移穷举（实现须按此表校验，非法迁移直接拒绝并保持原状态）：

| 起 | 止 | 条件 |
|---|---|---|
| —（新建） | latent | §3 起链成功且过 §8 全部闸门 |
| latent | fermenting | 推进时 `now ≥ ferment_at` |
| latent | dissipated | 消散事由（下表） |
| fermenting | resolved | 推进时 `now ≥ mature_at` 且兑现成功落锚 |
| fermenting | dissipated | 消散事由，或 `now > deadline_at` 仍未兑现（`budget_deferred=True` 时 `expired`/`lifetime_cap` 两事由不适用，R1/MF-3 豁免，见 §4.2） |
| resolved | — | 终态 |
| dissipated | — | 终态 |

消散事由（reason 记入 dissipate 节点）：`player_dead`（主体
死亡，§7）/ `counterparty_dead`（对象死亡且无兑现者规则，
§4.2）/ `no_avenger`（血仇到期无同宗在世）/ `expired`
（窗口逾期）/ `lifetime_cap`（链龄 > 90 游戏日强制收束）/
`superseded_by_kill`（恩/诺链对象被主体亲手击杀——该击杀
另起血仇链，原链消散，见 §4.2）。

注：不设独立 `matured/pending` 状态——到期兑现在同一次
推进内原子完成（先落终态锚再发效果，§5），避免半状态
在崩溃/死亡交叉时产生归属争议；因每日兑现预算等原因
暂缓的链保持 fermenting 并在节点记 `defer`（不新增状态，
defer 不占节点上限名额，见 §2.3 节点纪律）。**R1/MF-3
补记**：预算暂缓除 defer 记法外，还须把模型字段
`budget_deferred` 置 True 并随链落库（§2.1）——豁免
判定（§4.2/§8.1）只认此持久标记，不认内存返回值或
defer 节点，以免进程重启后豁免资格丢失。

### 2.3 时间口径（写死，防「日」字歧义）

- 全部时间戳为现实秒（`time.time()`），与 promises/agenda/
event_chains 全仓惯例一致。
- **1 游戏日 = `SECONDS_PER_GAME_DAY` = 240 现实秒**。
链内相对游戏日 `game_day = floor((ts - created_at) /
SECONDS_PER_GAME_DAY)`；发酵时长、冷却、窗口、链龄
一律以游戏日为单位、先换算成秒落账为绝对时刻
（ferment_at/mature_at/deadline_at 在起链时算定存下，
推进时只比时刻不重算——防 config 改动追溯改链）。
- `time_scale()`（闭关测试倍速）**不影响**链（其作用域
仅闭关设计秒换算，见 clock.py）；纪元 `season_day`
（现实日）**不参与**链计时。
- 面板文案的「日」恒指游戏日；涉及现实时间的量（每日
兑现预算）明写「现实日」。

### 2.4 存储选型（结论：新表 + 新仓储）

**推荐：新表 `karma_chains` + `KarmaChainRepository`
（storage/db.py，照 PromiseRepository 先例）。**

```sql
CREATE TABLE IF NOT EXISTS karma_chains (
id TEXT PRIMARY KEY,
data_json TEXT NOT NULL,
status TEXT NOT NULL,
player_id TEXT NOT NULL,
counterparty_id TEXT NOT NULL,
created_at REAL NOT NULL
);
```

仓储最小面：`save(chain)`（ON CONFLICT(id) 更新 data_json/
status）、`get(chain_id)`、`list_by_player(player_id)`、
`list_active()`（status ∈ latent/fermenting）、
`list_by_pair(player_id, counterparty_id)`、`list_all()`
（测试/对账用）。索引不另建（LAN 量级，列过滤足够；
与既有仓储全扫惯例一致）。

选型理由与否决项见 §1.5（KV 整包覆盖风险 / LegacyAccount
层级污染）。补充一条：链需要**终态历史长期留存**
（面板近史 + QA 对账），KV 与账户行都有截断/膨胀压力，
独立表与 promises/books 同例，留存策略独立可控：
终态链保留最近每玩家 20 条，超出在起链时顺手清理
（只删 dissipated/resolved 旧行，active 永不删）。

**旧存档兼容**：`init_db()` 的 `CREATE TABLE IF NOT
EXISTS` 对老库自动补表（空表 = 无链，全部读口返回空，
与老角色/老账户行为逐值一致）；`Character`、
`LegacyAccount` 模型零改动，无迁移脚本；老库中不存在
的链功能对既有命令输出零影响（新命令除外）。验收 K-17。

### 2.5 节点纪律

- 起链必写 origin 节点；迁移 fermenting 必写 ferment
节点并发酵传闻（§4.3）；兑现/消散必写终态节点。
- strengthen（续链加强，§3）写 strengthen 节点；
节点总数达 `KARMA_CHAIN_MAX_NODES=12` 后，strengthen
仍可加 strength 但不再追加节点（终态节点不受此限：
达上限时挤掉最旧一条 strengthen 节点以腾位）。
- defer（预算暂缓）不写节点，只更新内存返回值供 tick
日志，避免节点被刷爆。

---

## 3. 起链来源（宁少而实：五源，逐个点名触发点）

总规则（五源共用，引擎入口 `KarmaChainEngine.
note_origin(...)` 内部统一执行）：

- 主体必须是**玩家**（user_id 不以 `npc_/ai_npc_` 开头，
判定照 promises `_is_npc`），对象必须是 **NPC**；
任一不满足直接跳过（NPC↔NPC 的恩怨归 agenda/collusion
既有系统，玩家↔玩家见 Out of Scope）。
- 起链前依次过闸：主体存活、对象存活（S4 血仇例外：
对象即死者，见 S4）、§8 上限与冷却、同对同 kind
已有 active 链 → 转**续链**（strength +1 钳顶 +
strengthen 节点 + 更新 origin 引用）而不是新建。
- 钩子一律 `try/except` 包裹并惰性导入（照 F14 钩子
例：异常不炸主流程，链不起不影响原结算一分一毫）。
- 每源给出**幂等键** `chain_key`：同一事实重复触发
（重复 tick/重复调用/崩溃重放）不得产生第二条链；
引擎以「同 chain_key 存在任意状态（含终态）的链」
判重——终态后同键永不再起（事实已消费）。

### S1 态度跨阈（恩/仇）— 主源

- **触发点**：`core/npc_mind.py` `shift_attitude(npc,
other_id, delta, reason)` 返回前（其内部已完成
`NpcMindRepository.set_attitude` 落账）。钩子读取
shift 前值 `cur`（函数内现成）与落账后值，跨阈才调
`KarmaChainEngine.note_attitude_cross(npc, other_id,
before, after, reason)`。
- **阈值**（config：`KARMA_CHAIN_ATT_GRACE=60` /
`KARMA_CHAIN_ATT_HOSTILE=-60`）：
- 恩：`before < 60 ≤ after` → kind=en，polarity=+1，
strength = 3 + (after ≥ 85? 2: after ≥ 70? 1: 0)
（即 60–69→3、70–84→4、85–100→5）。
- 仇：`before > -60 ≥ after` → kind=chou，polarity=-1，
strength 同式（按 |after|）。
- 迟滞：跨阈后 before 恒 ≥60（或 ≤-60），后续小步进
不再触发；须先回到 ≤50（或 ≥-50）再跨才可能再起，
且仍受 active 去重与 §8 冷却——迟滞由跨阈定义
天然实现，不另存标记。
- **防自触发**：`reason` 以 `"因果链"` 开头时跳过
（链兑现自身的 attitude 落账走此 reason，见 §4.4；
防「链兑现 → 跨阈 → 新链」自激）。
- **幂等键**：`att:{player_id}:{npc_id}:{en|chou}:
{epoch}`，epoch = 该对该 kind 已终态链条数 + 1
（引擎查 `list_by_pair` 推导；同 epoch 内 active 或
终态存在即判重/续链）。
- 覆盖面备注：赠礼（chat_actions do_gift，态度增量
自 R1/MF-1 起按实付计价，公式见 §8.3.1，不再是旧
固定 +5~+10）、成交/人情（人情支同 §8.3.1 计价；
目录成交 +3 不在本轮计价改革范围，见 §8.3.1 涟漪
清单注）、委托完成（quests +8）、行窃被擒（-50/-40）、
叛门（-20）、击杀亲友（on_kill_update_attitudes 的
-45/-20/-15）等一切既有 attitude 来源都经此单点，
无需逐个埋点；单次 delta 多在 ±10 内，跨 60 线通常
意味着长期经营或重大事件——正是「重大施恩/结仇」
的可观察定义。S1 本身仍按**原始 attitude 值**跨阈
判定（R1/MF-1 选 (A) 而非 (B)，不设影子计权进度，
理由见 §8.3.1）。

### S2 关系边达阈（仇/恩）

- **触发点**：`core/collusion.py` `ensure_link(a, b,
link_type, note, now)` 保存后（其 strength 自增路径）。
- **阈值**：link_type ∈ {仇， 恩} 且 `strength ≥
KARMA_CHAIN_LINK_MIN=3`（自增前 <3、自增后 ≥3 的
那一次才调引擎；之后每次自增走续链判断）。
strength = min(5, link.strength)。
- **幂等键**：`link:{link_id}:{en|chou}`——同一条边
一生只起一条链（终态后不再起；边的后续变化只在
链 active 期间可续链加强）。
- 注：击杀路径的 ensure_link（combat_fate/cascade 的
「仇」边 strength=1 起步）达不到 3，不与 S4 抢源；
长期反复结仇（合谋寻仇、坊市失窃等 jianghu_sim
多点 ensure_link）累积到 3 才成链，符合「积怨成链」。

### S2b 出师转恩（恩，补充钩）

- **触发点**：`core/social_bonds.py` 出师流程将
`l.link_type` 改为 `"恩"` 并 `KarmaLinkRepository.
save(l)` 之后（约:226–228）。
- **条件**：师徒双方恰一方为玩家、一方为 NPC（双方
玩家跳过）；kind=en，strength=3。
- **幂等键**：`link:{link_id}:en`（与 S2 同键——出师边
若此前已由 S2 起过链则只续链，不双起）。

### S3 诺言终态（诺）

- **触发点**：`core/promises.py` `PromiseEngine.
_settle(p, outcome, note, t, promiser_obj)`——唯一
终态入口，在既有「落终态锚 → `_apply_effects` →
BROKEN 时 `_broadcast_broken`」全部完成后、返回前
调 `KarmaChainEngine.note_promise_settled(p,
outcome, t)`。
- **条件**：outcome ∈ {KEPT, BROKEN}（**DISSOLVED
永不起链**：未成/撤回/身死都不是「诺的兑现」）；
且 `p.promisee_is_npc` 为真（受诺人是 NPC；立诺者
恒为玩家——make_promise 的主体即玩家。玩家间诺言
不起链，见 Out of Scope）。
- **定链**：kind=nuo；KEPT → polarity=+1，strength=2；
BROKEN → polarity=-1，strength=3。
- **幂等键**：`promise:{p.id}`——诺言 id 全局唯一且
终态不可逆，此键天然防重放（_settle 本身终态短路，
钩子即使被异常路径二次调用也撞键跳过）。

### S4 击杀（血仇）

- **触发点（双引擎点，同一事实只认一条链）**：
- 玩家主动斗法：`core/combat_fate.py`
`CombatFateEngine.resolve_ambush` 的 kill 分支
末尾（既有 record_event/on_kill/ensure_link/
cascade 段之后）；
- NPC 议程/离线江湖杀戮：`core/jianghu_sim.py`
`JianghuSimulator.cascade_kill(killer, victim,
location, loot)` 末尾（其本身亦被 resolve_ambush
调用——两点靠幂等键合流，见下）。
- **条件**：killer 为玩家、victim 为 NPC（玩家杀玩家、
NPC 杀玩家、NPC 杀 NPC 均不起链：NPC 杀玩家走 §7
玩家死亡消散与既有 cascade；NPC 间杀戮无玩家主体）。
kind=xue，polarity=-1，strength=5。对象
counterparty 记**死者本人**（链的「仇主」），
delivery_actor 到期现选（§4.2）。
- **幂等键**：`kill:{victim_id}:{victim 本次死亡的
settled 标识}`——取 `victim.death_cause` 与死亡时刻
近似不可靠；定为 `kill:{killer_id}:{victim_id}:
{victim_created_or_incarnation}` 亦不足。**采用**：
`kill:{victim_id}:{nodes 无关}` 简化为
`kill:{victim_id}` + 引擎规则「同 victim 的 xue 链
终态后永不再起」——NPC 角色 id 全局唯一且死后不
复用（转世覆写的是玩家行，NPC 死亡行 id 不再入世），
故 victim_id 即足够唯一。此点在实现时须以
`CharacterRepository` 现行 id 生成方式复核
（uuid/花名册固定 id 均满足不复用），复核结论记入
实现报告。
- 与 hunt/悬赏的合流：同一击杀内的 `settle_kill`
（除凶）、S5 悬赏结算都发生在 S4 钩子前后（引擎内
或 CLI 调用段），一律只**续链**（见 S5），不另起。

### S5 悬赏销案（仇，仅续链源）【R1/MF-2 改写】

- **触发点**：`core/bounty.py` `BountyEngine.
settle_on_kill(killer, victim, bounties, now)`
返回 `bounty_paid=True` 的路径内（引擎层，CLI 现行
调用自动生效；server 未调用此函数的既有分歧见
§0.2-1 与待裁决 C-1）。
- **条件**：killer 为玩家、victim 为 NPC、实付赏金
≥1 笔。行为：**仅续链**——同对已有 active 链
（通常是 S4 血仇）→ strength +1（钳 8）+ strengthen
节点（summary 记「悬赏销案」与赏金总额）；**无
active 链 → 不新建链**，引擎入口直接返回 None /
无操作（悬赏销案事实本身已由 bounty 结算落账，
不单独成链）。
- **【废弃口径】** 原「无 active 链 → 兜底新建
kind=chou、strength=3」语义自 R1 起删除：该兜底在
现行调用图下不可达（settle_on_kill 的真实击杀路径
必先经 S4 起血仇链），属死代码语义，且使 K-5 的
「无链」情形无从验收。新建用的
chain_key=`bounty:{victim_id}:{首笔 bounty id}`
一并废弃。
- **幂等键**：续链以 `bounty:{sorted bounty ids}` 记入
节点 source_ref，同组悬赏重复结算（settle_on_kill
本身 COMPLETED 短路）不二次加强。

### 起链来源总表

| 源 | 触发文件/函数 | kind | polarity | 初始 strength | 幂等键 |
|---|---|---|---|---|---|
| S1 | npc_mind.shift_attitude（跨 ±60） | en/chou | +1/-1 | 3–5 | att:{pair}:{kind}:{epoch} |
| S2 | collusion.ensure_link（strength 达 3） | en/chou | 按边型 | min(5, 边 strength) | link:{link_id}:{kind} |
| S2b | social_bonds 出师改型点 | en | +1 | 3 | link:{link_id}:en |
| S3 | promises.PromiseEngine._settle（KEPT/BROKEN, NPC 受诺） | nuo | +1/-1 | 2/3 | promise:{promise_id} |
| S4 | combat_fate.resolve_ambush kill 分支 / jianghu_sim.cascade_kill | xue | -1 | 5 | kill:{victim_id} |
| S5 | bounty.BountyEngine.settle_on_kill（paid） | 仅续链（无链不新建，R1/MF-2） | — | +1（续） | 续链 source_ref=bounty:{ids} |

---

## 4. 推进与结果

### 4.1 推进挂点（tick 衔接）

- **主推进**：`NpcAgendaEngine.tick_world` 尾部（在
`rumors.maybe_ambient_tick` 之后）加一段 try/except：
`KarmaChainEngine.tick_world(now)`——经全部既有
tick 入口自动生效（server _tick_loop 120s / 开服 /
关服 / `/tick` / 双端 `/世情`）。单轮预算：
到期兑现至多 `KARMA_CHAIN_TICK_RESOLVE_MAX=5` 条
（按 mature_at 升序）、发酵迁移至多 10 条；超额
顺延下一轮（链状态不丢，时刻已落账）。
- **惰性推进**：双端 `/因果链` 处理在渲染前先调
`KarmaChainEngine.advance_for(char, now)`（只推进
该玩家名下链，含到期兑现；照 promises
settle_due→panel_text 先例）——保证玩家查时所见
为最新，且离线错过的兑现在其回来查询时已落账
并能在近史中看到。
- 推进顺序（单条）：存活/消散检查 → 发酵迁移 →
到期兑现。同一玩家同一轮至多兑现 1 条惰性 +
tick 预算内若干（与 §8 每日预算共同钳制）。

### 4.2 发酵与到期兑现流程

发酵时长（游戏日，起链时按 kind/polarity 查表算定）：

| kind/polarity | duration（游戏日） | 约合现实时间 | ferment_at |
|---|---|---|---|
| en | 9 | ≈36 分钟 | duration/2 |
| chou | 15 | ≈60 分钟 | duration/2 |
| nuo / KEPT | 6 | ≈24 分钟 | duration/2 |
| nuo / BROKEN | 9 | ≈36 分钟 | duration/2 |
| xue | 21 | ≈84 分钟 | duration/2 |

兑现窗口：`deadline_at = mature_at + 14 游戏日`；
逾期未兑现 → dissipated（expired）。链龄硬顶
90 游戏日（lifetime_cap 消散）。

**预算暂缓豁免（R1/MF-3，总管裁决）**：因每日兑现
预算（`KARMA_CHAIN_DAILY_RESOLVE_MAX` 或
`KARMA_CHAIN_DAILY_STONES_MAX`，§8.1）暂缓的链，
**豁免**上述 deadline 消散与链龄硬顶消散：

- **生效条件（标记）**：仅当链在一次正规推进中
已到期（`now ≥ mature_at`）、本可兑现、仅因当日
预算已被占满而被顺延时，引擎在该次顺延当场把
`budget_deferred` 置 True 并落库（§2.1/§2.2）。
从未被推进到到期、或因其他原因未兑现的链不享
豁免——其逾期仍按 expired / lifetime_cap 消散
（K-7 口径）。
- **豁免期行为**：链保持 fermenting，不因
`now > deadline_at` 或链龄 > 90 游戏日被消散；
预算按现实日重置后，在其后第一次正规推进
（tick_world / advance_for）中按 mature_at 升序
优先兑现（仍受新一日预算钳制；若新一日预算再
被占满，再次顺延，豁免不失效）。
- **豁免边界（不豁免项）**：主体死亡（§7
player_dead）、对象/兑现者死亡（counterparty_dead /
no_avenger / superseded_by_kill）在豁免期内照常
消散——推进时的存活检查先于豁免判定执行。
豁免只挡「时间到」类消散，不挡「人没了」类消散。

**发酵迁移时（latent→fermenting）做三件事**：
1. 落状态 + ferment 节点（先落账，后副作用，§5）；
2. 发酵传闻一条（§4.3）；
3. 仅 xue：预选兑现者（规则：死者同宗、存活、NPC，
按 |对玩家态度| 降序、id 升序 tiebreak；无同宗 →
不预选，到期再判 no_avenger）并把其主议程 upsert
为 revenge（target_hint=玩家名，照 cascade_kill 的
`NpcAgendaRepository.upsert` 写法；已为 revenge
则只更新 target_hint/note，不清 progress 之外
字段——照既有 upsert 全字段口径，实现时以
ensure_agenda 现行字段为准）。

**到期兑现时（fermenting→resolved）做四步（顺序即
§5 锚定序）**：
1. 复核：主体存活（否则转 §7 消散）、对象/兑现者
存活（en/chou/nuo 对象死亡 → dissipated
counterparty_dead；但若对象是被主体亲手所杀且
已有对应 xue 链 → reason=superseded_by_kill；
xue 兑现者按预选复核，预选者已死则按同规则重选，
无人可选 → dissipated no_avenger + 一条传闻收尾）；
2. 算效：按 §4.4 公式算 effects（纯函数，可单测）；
3. 落锚：链置 resolved、写 resolution（含 effects
与本地叙事）+ resolve 节点并 `save`；
4. 发效：按 resolution.effects 落账（玩家行/态度行
各自既有仓储）、写 jianghu/chronicle/传闻/同场
留话（§4.3）。第 4 步任一子项异常只丢该子项，
不回滚锚、不重发（§5）。

### 4.3 呈现通道（逐 kind 写清，全部既有通道）

| 时点 | en | chou | nuo | xue |
|---|---|---|---|---|
| 发酵 | rumors.add_rumor（truth 0.85，「听闻屡屡念及的恩义」类模板） | rumors（truth 0.9，记恨类） | rumors（KEPT: 0.85 赞许 / BROKEN: 0.9 昭告） | rumors（truth 0.9，同宗誓仇类） |
| 兑现·结构化 | jianghu.append_event(kind="karma_chain") + Chronicle（由 append_event public 同步） | 同 | 同 | 同 + WorldChannel.post(level="major"，「同门寻仇 · 天道记账」昭告) |
| 兑现·当面 | 兑现时刻主体与兑现者**同场**（双方 location 相等）→ record_event(type="TALK") 留话一句并进 tick 返回文本（/世情、/tick 可见）；异地不强求，靠江湖账+面板近史送达 | 同 | 同 | 同（留话为警告句，**不触发战斗**) |
| 兑现·回看 | `/因果链` 近史（§6）+ 命盘不新增字段 | 同 | 同 | 同 |

明确不用：奇遇链通道（EventChainEngine，交互式、
占名额，§0.3）、RevengeEngine 回访通道（概率叙事，
§4.5）、goals 目标通道（不新增目标源）。

### 4.4 结果奖惩（规则裁决口径与硬顶）

总原则：链兑现是**余波**，不是第二份全额结算——所有
单项子顶严于 `EVENT_EFFECT_CAPS`，且每链只走**一条**
数值支（灵石 XOR 修为，由 `hash(chain.id)` 奇偶定，
起链即可预知、不可操纵）+ 固定小额的关系/账目项。

有效强度：`eff = clamp(strength - floor(age_game_days
/ 30), 1, 5)`（age 自 created_at 至兑现时刻；发酵内
正常兑现衰减多为 0，顺延越久衰减越多，见 §4.2 窗口）。

| kind | 数值支（二选一，hash 定） | 固定项 | 单链硬顶（校验点） |
|---|---|---|---|
| en | 灵石 `15+10·eff`（45–60）**或** 修为 `20·eff`（60–100） | 对象对玩家 attitude +5（reason="因果链·报恩") | stones ≤60 ≤ caps 300；exp ≤100 ≤ caps 800 |
| nuo KEPT | 灵石 `10+5·eff`（20) **或** 修为 `20·eff`（40) | 功德 +5（add_merit)；attitude +5（因果链·践诺余绪） | merit 5 ≤ caps 40 |
| chou | 扣灵石 `min(余额, 10+5·eff)`（25–35）**或** 修为回落 `10·eff`（30–50，current_exp 钳 ≥0) | attitude `-min(20, 10+2·eff)`（-16~-20，因果链·报复）；道心 -3 | stones_lose ≤35 ≤ caps 200；exp_lose ≤50；dao_heart 3 ≤ caps 20 |
| nuo BROKEN | 无数值支 | 业力 +5（add_sin)；attitude -12（因果链·追诺）；传闻昭告（§4.3 truth 0.9） | sin 5 ≤ caps 40 |
| xue | **无直接数值支**（§4.5) | 兑现者对玩家 attitude -20（因果链·寻仇）；玩家业力 +10（add_sin)；议程已於发酵时置寻仇（§4.2） | attitude 20；sin 10 ≤ caps 40 |

> **注脚 1（括注口径，R1/OBS-5）**：上表数值支括注
> 中的单值（如 nuo KEPT 的灵石 (20) / 修为 (40)）为
> 该 kind **初始 strength** 下的参考值，不是兑现
> 上限。链经续链加强（§3，strength 钳 8）后，兑现额
> 按上文 `eff` 公式以加强后的 strength 重算，可
> 高于括注值；最终兑现以 eff 公式与
> `KARMA_CHAIN_EFFECT_CAPS` 子顶为准（括注区间值
> 同理为对应 strength 区间的示意）。

- **寿元：全 kind 恒为 0**（增减皆不走链）——寿元是
硬通货，链不得成为寿元来源或绕过斗法的寿元剥夺
通道。此条为铁律级，验收 K-9 专门断言。
- **修为落账钳制（R1/OBS-2）**：exp 兑现落账按既有
先例（events / event_chains 的 apply_effects 口径）
钳 `max_exp`：`current_exp = min(max_exp,
current_exp + exp_gain)`，exp_lose 钳 ≥0（既有）；
且 `resolution.effects["exp_gain"]` 必须记**实际
落账值**（= 落账后 current_exp − 落账前 current_exp，
已满时为 0 并可省略该键），不得记公式名义值——
QA 对账以 effects 与角色行实际增量一致为准
（K-8 注脚同此口径）。
- attitude 落账一律经 `NpcMindRepository.set_attitude`
绝对值钳 ±100 的既有口径（shift_attitude 读现值
相加后 set）；且 reason 带「因果链」前缀触发 S1
防自激跳过（§3）。
- 灵石增支为系统发放（与世界事件/奇遇落账同性质，
非从 NPC 余额转移——NPC 灵石不做守恒账，既有系统
皆如此）；扣支钳余额、永不为负。
- 与 caps 的关系一句话：`KARMA_CHAIN_EFFECT_CAPS =
{stones_gain:60, stones_lose:40, exp_gain:120,
exp_lose:60, sin:15, merit:10, dao_heart:5,
attitude:20, lifespan:0}` 为本系统子顶，公式极值
均 ≤ 子顶，子顶均 ≤ EVENT_EFFECT_CAPS 对应项
（dao_heart 子顶 5 < caps 幅度 20；attitude/lifespan
为 caps 外维度，单列并在此定顶）。

### 4.5 与 RevengeEngine / cascade 的分工裁定（防双重报复）

- **即时层归既有**：击杀当场的仇边、同宗议程转寻仇、
传闻、频道、除凶/悬赏结算，一律仍由 cascade_kill /
hunt / settle_on_kill 在当场完成，因果链不复制。
- **回访层归 RevengeEngine**：其概率回访叙事与经
gate 的效果维持原样，本轮**不改其一行**；因果链
写入 jianghu 的 kind 为 `"karma_chain"`、写
EventLedger 时 type 用 `"KARMA_CHAIN"`——不在
`query_feud_pairs` 的 type 集合内，链事件永不
成为回访的新种子（防「链生回访、回访再生事」）。
- **记账层归因果链**：确定性、定时、可查；数值刻意
与回访错开——血仇链不扣灵石/修为/寿元（§4.4），
故最坏重叠只是「叙事上被提两次」，不存在数值
双重重惩。此裁定为本轮争议点 C-3（§13），若总管
要求血仇有直接数值牙齿，须另行收紧回访侧，二者
不可同时全额。

---

## 5. 幂等与防重放

沿用上一轮两条教训（inheritance_claims 领取标记 +
settle_death trace 存在性闸门）与 promises 范式：

1. **起链幂等**：chain_key 判重（§3 总规则）——同键
任意状态存在即不新建；active 存在时钩子只走续链
判断。钩子本身可被同事实重复调用（combat_fate
与 cascade 双点、settle 重放），结果恒为至多一条链。
2. **结算一次性闸门**：`_resolve(chain, now)` 与
`_dissipate(chain, reason, now)` 是仅有的两个写
终态入口（照 PromiseEngine._settle 地位）：入口
先查 status ∈ {latent, fermenting}，终态直接
return False；**先 save 终态 + resolution（含
effects 明细）再发效果**。崩溃在锚后效前 →
效果丢失但永不双发（at-most-once，与 promises
同取舍：丢 ≤60 灵石优于双发刷钱）；崩溃在锚前
→ 下轮推进按存量状态重算，同公式同结果。
3. **发酵一次性**：ferment 迁移先 save 状态再发
传闻/议程；崩溃重放时 status 已 fermenting，
不重复发传闻、不重复 upsert 议程（upsert 本身
幂等，此为双保险）。
4. **续链幂等**：strengthen 以 source_ref 判重
（S5 的 bounty ids、S2 的 link 自增次数序号）：
节点中已有同 source_ref 的 strengthen 节点则
跳过加强。
5. **重复 tick/重复命令**：tick_world 与 advance_for
可任意重入；终态短路 + 时刻比较使重复推进为
空转。server lock（World.handle 的 RLock）与
CLI 单进程下无并发写；跨进程（CLI 与 server
同开同库）沿全仓既有惯例不做跨进程锁（与
promises/event_chains 现状一致，明示不新造）。
6. **死亡重放**：on_owner_death（§7）对已 dissipated
的链短路；`_settle_if_needed` 本身有 death_settled
守卫，链消散随之至多执行一次有效迁移。

---

## 6. 玩家可见（双端查询与留痕规格）

### 6.1 命令（双端同命令同文案，照 /墓碑 先例）

- 命令：`/因果链`，别名 `/karma_chains`。
**禁用** `/因果`（双端既有语义已分叉，§0.2-2，
本轮不动其任何一端语义）。
- server 落点：`World.handle` 新增分支（与 /墓碑
分支同段），先 `advance_for` 后渲染，返回
`{ok: True, text: <引擎同源文本>}`；闭关只读
白名单**不加**本命令（链查询非观照类，与 /诺言
不在白名单的现状一致）。
- CLI 落点：主循环新增分支（与 /墓碑 分支同段），
先 `advance_for` 后 `console.print` 同一文本。
- 引擎同源：`KarmaChainEngine.panel_text(char,
now)` 一处拼装（照 PromiseEngine.panel_text /
inheritance.tombstone_text 先例），双端逐字一致，
验收以同源断言钉死（K-19）。
- Web：经 `/action` 通用文本 feed 呈现，**前端零
改动**即可用；`_status_dict` 只增可选键
`karma_chains: {active: int, fermenting: int,
nearest_mature_game_days: int|null}`（纯增字段，
旧前端忽略；前端可视化呈现列 Out of Scope）。

### 6.2 面板内容规格

```
天道记账，前因后果皆有回音。
〔进行中〕（n/4）
· [恩·发酵 6/9 日] ——起因一句话（origin_summary）
强度 4 · 余波将至：对象念恩（恩向）/ 对象记恨（仇向，只给方向不给数值细目）
· [血仇·潜伏 3/21 日] ——起因……
〔近史〕（最近 5 条终态，照 PROMISE_HISTORY_N）
· [已兑现·恩] ——结果一句话：落账摘要（如 灵石+55，态度+5）
· [已消散·诺] ——消散原因中文（对象已逝/诺随旧世/逾期无果……）
（无链时：眼下无因果缠身。施恩、结仇、立诺、行凶，天道都记着。）
```

- 发酵进度 = `floor(100 × age / duration)` 钳 99
（resolved 前不显示 100），并给「已过游戏日 /
总发酵游戏日」双数，玩家可自行估时。
- 呈现要素齐 §RQ-3：谁（对象名）、因何
（origin_summary)、发酵进度、了结结果
（resolution 摘要 + effects 中文摘要）。

### 6.3 了结留痕规格

- 每条链 resolved：jianghu.append_event
(kind="karma_chain", visibility="public") 一条
（自动同步 Chronicle 一条）；xue 另加 WorldChannel
major 一条（受其 60s 去重/限流约束，失败静默，
不影响落账）。
- dissipated：仅当链曾进入 fermenting（外界已知其
存在）才写 jianghu 一条收尾；latent 消散只记链
节点与面板近史（防大事记刷屏）。
- 发酵传闻与兑现文案模板见 §9（本地模板表）。

---

## 7. 死亡衔接

### 7.1 处置规则（逐状态）

挂点：server `World._settle_if_needed` 与 CLI
`settle_and_reincarnate` 的死亡钩子段，紧随
`PromiseEngine.on_owner_death(char)` 之后、
`LegacyEngine.settle_death` 之前，调
`KarmaChainEngine.on_owner_death(char, now) ->
List[Dict]`（返回值只供调用方日志/大事记计数，
**不注入 settle_death**——与诺言摘要注入留痕的
做法刻意不同，理由 §7.2）。大劫
`_settle_apocalypse` 经 `_settle_if_needed` 逐人
结算，自动覆盖，不另挂点。NPC 死亡不调本钩子
（NPC 非链主体；其作为对象的死亡由推进时存活
检查处理，§4.2）。

| 链状态（主体=死者） | 处置 |
|---|---|
| latent | → dissipated(reason=player_dead)，静默（不写 jianghu) |
| fermenting | → dissipated(reason=player_dead)，写 jianghu 收尾一条「未了之链随旧世而散」 |
| 已到期未推进（fermenting 且 now ≥ mature_at) | **仍消散，不抢先兑现**：死亡结算优先于链兑现（与诺言「死亡消散不判违约」同裁定）；推进与死亡同刻竞争时以 handle lock 内先到者为准，死后 advance 见 DEAD 必跳过 |
| resolved / dissipated | 不动（历史保留，新角按自己 id 查不到旧链——面板以 player_id 过滤，天然隔离） |

对象（NPC）在主体死亡同一结算中的状态不影响上表。

### 7.2 与因果影子 / 诺言回声不双重记账的判定

判定方法（三问，全过才允许落账，本轮设计逐项自检）：

1. **是否新增了跨世资产？** 否。链不写 LegacyAccount
任何字段、不进 LifeTrace（traces 结构零改动）、
on_owner_death 返回值不注入 settle_death。
转世后新角名下零链（新 id)，「前世未了之链」
不在 /道统 前世因果段呈现（该段仍只有影子 +
诺言回声两项，与 v0.3.0 逐字不变）。
2. **同一事实是否被结两次？** 诺言链（S3）：诺言
本体的功德/业力/态度在 `PromiseEngine._settle`
时已结清；链兑现的是**另一时点、另一名目**
（余绪/追诺）的子顶小额（§4.4)，且诺言死亡
回声只收 DISSOLVED 的未结诺——而已终态
(KEPT/BROKEN）诺本就不入回声，链更不入，
三者集合互斥。
3. **影子是否把链的账又折一遍？** 影子快照
`_snapshot_shadow` 只读 attitudes 与 KarmaLink
两源。链兑现造成的 attitude 变化与赠礼/交谈
造成的变化同性质地被快照——那是「世界对你的
态度」这一**存量**的折算，不是链资产的转移；
链本身的待兑现权利（未到期部分）随死亡归零，
不折算、不补偿。此判定与「KarmaLink 折算」
先例一致：折的是关系存量，不是未结账目。

---

## 8. 克制与防刷

### 8.1 上限总表

| 闸门 | 值 | 位置 |
|---|---|---|
| 单玩家 active 链（latent+fermenting) | 4 (`KARMA_CHAIN_MAX_ACTIVE_PER_PLAYER`) | 起链闸 |
| 单 NPC 对象 active 链（跨玩家） | 2 | 起链闸 |
| 全服 active 链 | 40 (`KARMA_CHAIN_MAX_ACTIVE_GLOBAL`) | 起链闸 + tick 预算前提 |
| 单链节点 | 12 (§2.5) | 写入时 |
| 单链 strength | 8（初始 ≤5，续链 +1 钳顶） | 起/续链 |
| 单 NPC 新起链频率 | 同一 NPC 每 10 游戏日 至多作对象新起 1 链（续链不限） | 起链闸（查该 NPC 最近 created_at) |
| 同对同 kind 终态冷却 | 30 游戏日（终态后该窗口内同对同 kind 不新起；S1 epoch 键 + 本冷却双检） | 起链闸 |
| 每玩家每日兑现数 | 2 / 现实日（超出顺延；顺延链带 `budget_deferred` 标记并享 §4.2 豁免，R1/MF-3） | 兑现闸 |
| 每玩家每日链灵石所得 | ≤120 / 现实日（增支累计，超出部分当日兑现的灵石支自动改走修为支或顺延——定为**顺延**，不改支防预期外落账；因此顺延的链同享 §4.2 豁免） | 兑现闸（按 resolution.effects 回查当日已兑现链） |
| 预算暂缓豁免（R1/MF-3） | `budget_deferred=True` 的链不因 deadline / 链龄 90 游戏日硬顶消散，保持 fermenting 至预算重置后兑现；死亡类消散不豁免（§4.2 边界） | 推进闸（存活检查先于豁免判定） |

### 8.2 施恩—结仇横跳堵口（翻转降级）

- 定义：同对（玩家， NPC）在任一链终态后 30 游戏日
内，新起**相反 polarity** 的链 → 新链 `flipped=
True`。
- flipped 链：照常发酵、照常呈现、照常写痕，但
**兑现只叙事不落任何数值**（resolution.effects
恒为 {}，outcome 记 `fizzled` + 节点注明「恩仇
反复，天道不赏」）。
- 再犯：flipped 链终态后 30 游戏日内同对再起链
（无论 polarity）→ 起链闸直接拒绝（连叙事链
都不给），闸门以 pair 终态史查询实现。
- 依据：横跳的成本（把态度从 +60 打到 -60 再拉回）
本已不低，翻转降级把其**边际收益归零**，套利
动机消失；而真实剧情型反目（长期跨度 >30 游戏日）
不受影响。

### 8.3 经济账（净收益论证）【R1/MF-1 改写】

- **恩链（主要「收益」源）**：到 +60 态度的赠礼
路径成本自 R1/MF-1 路线 (A) 改革后由公式保证
（§8.3.1）：真实 `do_gift` / 人情支路径把态度从
0 冲到 60 的**最低灵石成本 ≥300**；委托 +8/次、
交谈 +1~+2/次皆为时间成本（不在灵石口径内，
且单靠其跨阈耗时与 §8 闸门使刷链期望仍为负，
口径不变）。恩链兑现上限：灵石
60 或修为 100（≈ 坊市价外不可直接折石）+ attitude
+5。**灵石口径净收益 ≤ 60 − 300 = −240 < 0**，
恒为负。此为总管裁决的验收标准原文，不得以
计权口径等 reinterpretation 替换（§8.3.1）。
- **诺链 KEPT**：践诺本身需完成赠物/抵达/委托的
真实行为成本，链余绪 ≤ 灵石 20/修为 40 + 功德 5，
为附赠级，不构成刷诺动机（且 PROMISE_MAX_OPEN=3
与同类去重在源头钳量）。
- **仇/血仇链**：对玩家只有负项或零（§4.4)，无
套利面；故意结仇引链再「化解」无任何正收益
出口（本轮无化解机制，见 Out of Scope）。
- **总量**：单玩家链灵石所得理论日顶 =
min（每日兑现 2 条 × 60, 日灵石子顶 120) = 120
灵石/现实日，且每条都需前置真实成本——低于
既有委托链（单链封顶 200）与悬赏（单笔至 5000）
的既有经济水位，不冲击坊市。

### 8.3.1 MF-1 路线裁定：选 (A) 赠礼侧改革（R1 新增）

**选择：(A)，不选 (B)。** 理由：

1. **病根在赠礼本体，不在链**：固定增量与实付脱钩
使「1 灵石 ×12 次 = 态度 0→60」不只套利因果链，
同样套利一切 attitude 消费方——目录成交折扣
（attitude ≥30 的 0.85 系数）、NPC 主动搭话的
ally 概率、死亡时因果影子快照（|v|≥30）等。
(B) 只给链加影子计权账，病根留给其他系统。
2. **验收口径不容 reinterpretation**：总管验收
标准写的是「真实 do_gift 路径把**态度**从 0 冲到
60 的最低灵石成本 ≥300」。(B) 下原始 attitude
仍是 12 灵石到 60，只能把验收改读为「计权进度
到 60」——等于改动裁决本身，R1 无此权限。(A)
使原始 attitude 本身满足字面标准。
3. **(A) 无新状态、(B) 需新账**：(A) 公式只落在
`chat_actions` 两个既有分支内，无签名变更、无
持久化新增；(B) 须新增按对计权进度存储、处理
负增量与迟滞回落、还要把实付额穿透
`shift_attitude` 签名或 reason 字符串，复杂度
与出错面都更大，收益只是保住 1 灵石 +5 的手感。

**计价公式（可验收口径；常量进 config.py，
§10 增补）**：

- `do_gift`（`core/chat_actions.py`）：设本次实际
扣除灵石 `paid`（既有 `min(stones, 余额)` 钳后
且已落账的值）、所赠物品目录价
`item_value = ITEM_CATALOG[item]["price"]`
（物品不在 ITEM_CATALOG 时计 0），赠值
`V = paid + item_value`，则
**`delta = min(GIFT_ATTITUDE_MAX_PER_GIFT=10,
V // GIFT_ATTITUDE_STONES_PER_POINT=5)`**。
返回值 `attitude_delta` 记此实际 delta（可为 0）。
物品转移、手稿 `BookEngine.on_gifted`、诺言
`PromiseEngine.note_gift` 核验均不依赖 delta，
逐项不变。
- `do_trade` 人情支（无目录货、出灵石换人情）：
**`delta = min(FAVOR_ATTITUDE_MAX_PER_TRADE=4,
paid // 5)`**（同一 `STONES_PER_POINT`）。目录
成交支 +3 不在本条范围（见涟漪清单注）。
- **成本下限证明**：每笔 `delta_i ≤ paid_i / 5`
（floor 与单笔 cap 只减不增；纯灵石赠礼时
item_value=0），故态度累计到 60 蕴含
`Σ paid_i ≥ 5 × 60 = 300`，与拆分笔数、单笔大小
无关。**可达性**：6 笔 × 50 灵石（每笔恰 +10，
不触 cap 浪费）即态度 = 60、总成本恰 300——
下限紧而可达，不是把赠礼改死。物品入账口径：
物品按目录价计入 V，其「成本」为实付灵石 +
所耗物品目录价（机会成本）；K-1A 的强制验收
路径为纯灵石路径。
- **同对递减 / 日限：经评估不另设**。裁决路线
(A) 描述中的递减/日限是防拆分套利的手段，而
线性计价已使总成本与拆分方式无关（拆小只多
吃 floor 损失、拆大只多吃 cap 损失），目的已达；
再加递减/日限须新增按对按日状态且误伤正常
赠礼。此点为主策对路线 (A) 内部取舍，验收
标准（≥300 / 净 ≤0 / 真实路径回归）不依赖它；
若总管坚持要递减/日限，属新增裁决，另行回填。
- **【废弃口径】** 以下旧口径自 R1 起全部废弃，
实现与测试不得再引用：`do_gift` 旧式
`delta = 5 + (3 if stones ≥ 50) + (2 if item)`；
人情支旧式「任意 ≥1 灵石固定 +4」；§8.3 旧论证
前提（「灵石赠礼达 +3 档需单次 ≥50、纯赠礼约
≥300」——该前提系误读：旧式 +5 为无条件基础值，
实测 12 灵石即可 0→60，评审 MF-1 已证伪）。

**涟漪清单（选 (A) 的已知影响面，实现/回归须逐项过）**：

| 影响面 | 影响与处置 |
|---|---|
| `core/chat_actions.py` 本体 | 仅 do_gift / do_trade 人情支两处 delta 公式与 `attitude_delta` 返回值变化；函数签名、扣款、物品转移、错误路径不变。小额赠礼（V<5）delta=0：赠礼台词为风味文案、不承诺数值，不改；任何按 `attitude_delta>0` 判定的调用方须复核（现行调用方只透传文本，实现报告须 grep 复核结论） |
| 会话系统（`core/npc_chat.py`、server 会话分支） | 交谈 delta（reason=交谈/会话）不经 do_gift、不受影响；但靠赠礼快速拉高态度再谈的节奏变慢，属预期内平衡变化 |
| 诺言（`core/promises.py` + tests/test_promises.py） | 践诺核验认「真赠出同名物品」事实，不认 delta，功能不变；若夹具借赠礼顺带断言态度，须按新公式改期望值 |
| tests/test_chat_actions.py | 赠礼/人情既有用例（物品转移、拒收、压价）行为不变；新增公式边界断言归 K-1A |
| 态度消费方（不改代码、验行为） | 目录成交 0.85 折扣门槛（态度 ≥30）、`npc_proactive` ally/hostile 开口概率、商店态度系数（NPC_ATTITUDE_FRIENDLY=40 等）：门槛本身不动，但经赠礼达到门槛的成本上升——这正是堵套利的目的，冒烟时各验一次可达性（经委托/交谈/足额赠礼） |
| 因果影子（`core/inheritance.py`） | 快照阈值 |v|≥30 不动；经赠礼刷出的廉价影子原料消失，属正向修复 |
| 委托（`core/quests.py`） | QUEST_ATTITUDE_DELTA=+8 不动；相对权重上升（成为低成本态度来源之首），其时间/任务成本即为对价，不另调 |
| 因果链 S1（本 Spec §3） | S1 判定逻辑与 K-1（shift_attitude 直调）不动；新增真实路径验收 K-1A 补齐「直设态度冒充经营」的证据缺口 |
| 前端/Web | `attitude_delta` 字段名/类型不变，数值变小；无契约变更 |

---

## 9. 数值与 AI 边界

- **铁律对齐**：链的存在、时刻、强度、状态迁移、
effects 全部由 `core/karma_chains.py` 规则函数
裁决；LLM 只允许在兑现呈现时润色**一句话台词**
（兑现者口吻），且润色发生在 effects 落锚之后，
结果只进呈现文本（tick 返回/panel 近史的
narrative 副本），**不回写** resolution.effects、
不影响任何后续判定。
- **接入方式**：照 `core/ai_flavor.py` 既有范式
新增 `polish_karma_outcome(kind, polarity, npc_name,
player_name, outcome_summary, personality="") ->
Optional[str]`（预算复用 ai_flavor 的 40/小时
预算与 `_ask` 通道；失败/无 AI/超预算返回 None)。
- **本地模板（全覆盖，非兜底残缺版）**：模块内按
(kind, polarity, outcome）备模板表，含对象性格
占位（ensure_mind 的 personality 只读带入语气词），
AI 不可用时呈现质量以模板为准绳——验收 K-18
以「AI 全关 + AI 抛异常」两姿势跑通全链路为据：
起链、发酵传闻、兑现数值、面板、近史逐项与
AI 开启时**除台词文本外逐值一致**。
- 链推进**永不等待** AI: tick 路径中 AI 调用在
落锚发效之后、且单独 try/except + 短超时
（沿 ai_flavor timeout=12s 上限，tick 批量时
至多对本轮第 1 条兑现做润色，其余直接模板——
防 tick 被 AI 拖慢，此为实现约束，写入 T 任务）。

---

## 10. 配置常量总表（全部进 config.py，规则单点）

| 常量 | 值 | 说明 |
|---|---|---|
| KARMA_CHAIN_ATT_GRACE | 60 | S1 恩跨阈 |
| KARMA_CHAIN_ATT_HOSTILE | -60 | S1 仇跨阈 |
| KARMA_CHAIN_LINK_MIN | 3 | S2 边 strength 达阈 |
| KARMA_CHAIN_STRENGTH_CAP | 8 | strength 钳顶 |
| KARMA_CHAIN_MAX_ACTIVE_PER_PLAYER | 4 | §8 |
| KARMA_CHAIN_MAX_ACTIVE_PER_NPC | 2 | §8 |
| KARMA_CHAIN_MAX_ACTIVE_GLOBAL | 40 | §8 |
| KARMA_CHAIN_MAX_NODES | 12 | §2.5 |
| KARMA_CHAIN_PAIR_COOLDOWN_DAYS | 30（游戏日） | 同对同 kind 终态冷却 / 翻转窗口 |
| KARMA_CHAIN_NPC_START_INTERVAL_DAYS | 10（游戏日） | 单 NPC 新起链间隔 |
| KARMA_CHAIN_WINDOW_DAYS | 14（游戏日） | 兑现窗口 |
| KARMA_CHAIN_LIFETIME_DAYS | 90（游戏日） | 链龄硬顶 |
| KARMA_CHAIN_DAILY_RESOLVE_MAX | 2 / 现实日 | 每玩家兑现预算 |
| KARMA_CHAIN_DAILY_STONES_MAX | 120 / 现实日 | 每玩家链灵石子顶 |
| KARMA_CHAIN_TICK_RESOLVE_MAX | 5 | 单轮 tick 兑现预算 |
| KARMA_CHAIN_EFFECT_CAPS | {stones_gain 60, stones_lose 40, exp_gain 120, exp_lose 60, sin 15, merit 10, dao_heart 5, attitude 20, lifespan 0} | §4.4 子顶 |
| 发酵时长表 KARMA_CHAIN_DURATIONS | {en 9, chou 15, nuo+ 6, nuo- 9, xue 21}（游戏日） | §4.2 |

R1/MF-1 增补（路线 (A) 计价常量，归 chat 段）：

| 常量 | 值 | 说明 |
|---|---|---|
| GIFT_ATTITUDE_STONES_PER_POINT | 5 | §8.3.1：赠值每 5 灵石（或等价目录价）折 attitude +1 |
| GIFT_ATTITUDE_MAX_PER_GIFT | 10 | §8.3.1：单笔赠礼 attitude 增量上限 |
| FAVOR_ATTITUDE_MAX_PER_TRADE | 4 | §8.3.1：人情支单笔 attitude 增量上限（沿旧 +4 上限） |

既有常量一律不动：EVENT_EFFECT_CAPS、SHADOW_*、
PROMISE_*、SECONDS_PER_GAME_*、NPC_TICK_*。

---

## 11. 实现任务拆分（供后端/前端岗领活，非本轮交付）

- T1 config.py：§10 常量组（文件尾部新段，不动既有值）。
- T2 storage/db.py：init_db 加 karma_chains 表（6e 号位
注释）；KarmaChainRepository（照 PromiseRepository)。
- T3 core/karma_chains.py：模型 + KarmaChainEngine
(note_* 五源入口 / tick_world / advance_for /
on_owner_death / panel_text / 纯函数 effects 计算 /
本地模板表）。
- T4 钩子（各一处 try/except 惰性调用）：npc_mind.
shift_attitude(S1)、collusion.ensure_link(S2)、
social_bonds 出师段（S2b)、promises._settle(S3)、
combat_fate kill 段 + jianghu_sim.cascade_kill(S4)、
bounty.settle_on_kill(S5)。
- T5 推进：npc_agenda.tick_world 尾加链推进段；
server/world.py 与 cli/main.py 死亡钩子段加
on_owner_death（promises 钩子之后）。
- T6 命令：server handle /因果链 分支 + _status_dict
只增 karma_chains 键；CLI /因果链 分支；_help 文案
与 CLI 帮助各加一行（照 /墓碑 增补方式）。
- T7 ai_flavor.polish_karma_outcome + karma_chains
呈现接线（§9 约束）。
- T8 tests/test_karma_chains.py 新文件（§12 K 条目
逐条落测）；前端契约如因 _status_dict 增键需同步
则归前端岗（只增键，旧契约不断）。
- T9 发版：VERSION/README/CHANGELOG/gray-runbook
四处同步（沿上一轮发布清单）。

---

## 12. 验收条目（K 编号；每条带可观察方法）

起链（阈值与去重）:

- K-1 S1 阈值与迟滞：tests/test_karma_chains.py
`test_att_cross_thresholds`——构造 attitude 59→60
起 en 链（strength 3)、69→70 段内不起新链、跌回
50 后再跨 60 在 active 存在时走续链、-59→-60 起
chou 链；断言链数与 strength。
- K-1A 赠礼计价与真实路径成本（R1/MF-1，路线 (A)）：
tests/test_chat_actions.py
`test_gift_attitude_priced_by_value`——公式边界：
纯灵石赠礼 paid=1/4 → delta 0、5 → 1、49 → 9、
50 → 10、500 → 10（cap）；赠聚气丹（目录价 40、
paid=0）→ delta 8；人情支 paid=1 → 0、19 → 3、
20 → 4、100 → 4（cap）。tests/test_karma_chains.py
`test_real_gift_path_cost_to_en_chain`——**必须走
真实入口** `chat_actions.do_gift` / 人情支
`chat_actions.do_trade` 经营态度，**禁止**以
`NpcMindRepository.set_attitude` 直设或
`shift_attitude` 直调代替经营段（直调仅许用于
K-1 的 S1 单元口径）：断言 (i) 以最省策略
（1 灵石连赠、人情 1 灵石连投、任意拆分组合）
累计实付 <300 时 attitude <60 且无 en 链；
(ii) 6 笔 × 50 灵石后 attitude 恰 60 且 en 链
起链；(iii) 该链兑现的净收益 = resolution.
effects 灵石增支（≤60）− 实付（≥300）≤ −240，
即净收益 ≤0（若该链走修为支，灵石增支计 0，
净收益更低，断言同立）。
- K-2 S1 防自激：`test_chain_attitude_no_self_trigger`
——以 reason="因果链·报复" 调用 shift_attitude
跨 -60 线，断言不起链。
- K-3 S2/S2b 边达阈：`test_link_threshold_and_graduation`
——ensure_link 同对仇边自增至 3 起链、至 4 只续链；
师徒出师改型起 en 链且同 link 键不双起。
- K-4 S3 诺言终态：`test_promise_settle_starts_chain`
——NPC 受诺 KEPT 起 nuo+ 链（strength 2)、BROKEN
起 nuo- 链（strength 3)、DISSOLVED（含死亡消散）
不起链、玩家受诺不起链；复用 tests/test_promises.py
的构造夹具。
- K-5 S4/S5 击杀合流与 S5 仅续链（R1/MF-2 改写）：
`test_kill_and_bounty_single_chain`
——走 resolve_ambush 真实击杀（玩家→NPC）后 xue
链恰 1 条；再走 CLI 口径 settle_on_kill 结赏，
链仍 1 条且 strength +1、节点含 bounty source_ref;
重复调 settle_on_kill 不再加强。**新增无链断言**：
同测试内（或同名后缀用例）对一对**无任何 active
链**的玩家/NPC 单独走 settle_on_kill 结赏路径
（paid），断言链总数为 0、`note_bounty_settled`
返回 None——S5 无链不新建（原兜底新建断言如
存在，一并删除，属废弃口径）。

发酵与兑现：

- K-6 发酵迁移：`test_ferment_transition_and_rumor`
——以注入 now 推进至 ferment_at 前后：之前 status
=latent 且无传闻；之后 =fermenting、rumor_pool 多
1 条对应模板、xue 链兑现者已预选且其议程为
revenge; 重复推进不重复发传闻。
- K-7 到期兑现与窗口：`test_mature_resolve_and_expire`
——推进至 mature_at 兑现落账且 status=resolved;
逾期消散场景须用**未被预算暂缓**的链（R1/MF-3
口径修正：如链在 mature 后不做任何推进、一次
推进直接跳过 deadline_at——模拟推进停摆），
断言 status=dissipated(reason=expired）且零落账。
原「以每日预算占满制造顺延后推过 deadline 断言
expired」的写法与 §4.2 豁免冲突，废弃；预算
暂缓链的跨窗行为只认 K-10。

结果结算与硬顶：

- K-8 公式与子顶：`test_effects_formula_and_caps`
——五 kind × 两 hash 支参数化：断言每项 effects
≤ KARMA_CHAIN_EFFECT_CAPS 对应子顶且 ≤
EVENT_EFFECT_CAPS 对应项（lifespan 键恒不存在
或为 0,见 K-9)，attitude 落账走 set_attitude
钳制。**exp 实际落账注脚（R1/OBS-2）**：参数化
另加一例——玩家 current_exp 距 max_exp 小于公式
exp_gain 时兑现，断言落账后 current_exp ==
max_exp 且 resolution.effects["exp_gain"] ==
max_exp − 落账前 current_exp（实际落账值，
非名义值，§4.4）。另注（R1/OBS-5）：公式断言
以 eff 与 caps 为准，§4.4 表括注单值仅为初始
strength 参考，续链加强后的期望值按 eff 重算。
- K-9 寿元铁律：`test_effects_never_touch_lifespan`
——全 kind 兑现前后 `lifespan.death_timestamp /
birth_base / accumulated_gain` 逐值不变（对照
同一角色走 EventEngine 事件可变的事实，证明
链路径独立为零）。
- K-10 每日预算与暂缓豁免（R1/MF-3 改写）：
`test_daily_resolve_budget`——同玩家 3 条**同刻
到期**链，全程只以**单调递增的注入 now** 走引擎
正规入口（tick_world / advance_for）推进：
(i) 到期日（现实日 D，取当日中段时刻起链以便
同日内大幅推进游戏日）推进：只兑现 2 条，第 3 条
保持 fermenting 且 `budget_deferred == True`、
灵石增支当日累计 ≤120；(ii) 在同一现实日内把
now 推过第 3 条的 deadline_at 且推过其链龄
90 游戏日硬顶：第 3 条**仍为 fermenting**
（豁免生效，不断言 expired/lifetime_cap 消散）；
(iii) 把 now 推过下一现实日界（D+86400 之后）
再推进：第 3 条兑现为 resolved、effects 只落
一次账。**证据纪律（明文）**：禁止回拨或改写
库内 `resolved_at`、`created_at`、`mature_at`、
`deadline_at` 等任何落账时刻、禁止直接改
data_json 充当跨日/跨窗证据；原测试中「把已兑现
两条的 resolved_at 回拨一个现实日」的写法判为
**无效证据，须删除重写**。预算按 now 所属现实日
判定，now 单调前进即完成真实跨日。

幂等与重入：

- K-11 终态锚与重放：`test_resolve_idempotent_replay`
——对已 resolved 链重复调 tick_world/advance_for/
_resolve：玩家灵石/修为/态度逐值不变，
resolution 不变；模拟「锚已落、效未发」中间态
（手工置 resolved + 空 effects 落账痕迹）再推进：
不补发、不双发。
- K-12 起链重放：`test_origin_hooks_replay`——同
一 promise _settle 重放、同 kill 双点（resolve_
ambush + cascade）各调两次：链总数恒为预期
（S3 一条、S4 一条）。

上限与防刷：

- K-13 上限闸门：`test_caps_and_cooldowns`——玩家
active 满 4 后新源不起链；同 NPC 对象满 2 跨
玩家不起；同对同 kind 终态 30 游戏日内不起、
31 日后可起；同 NPC 10 游戏日内第二条新链被拒。
- K-14 翻转降级：`test_flip_flop_narrative_only`
——en 链 resolved 后 30 游戏日内同对起 chou 链：
flipped=True，兑现后玩家全部数值逐值不变、
resolution.effects=={}；其终态后 30 日内再起链
被拒。

死亡衔接：

- K-15 逐状态消散：`test_death_dissipates_by_state`
——latent/fermenting/已到期未推进三态各一链，
走 server _settle_if_needed（或 CLI 同等路径）：
全部 dissipated(player_dead)、零数值落账、
LegacyAccount traces/shadow 字段与无链对照组
逐值一致（双重记账反证）。**server 编年史断言
（R1/MF-4 补）**：本条必须有一组用例走 **server
`World._settle_if_needed`** 真实路径（不得只以
引擎 `on_owner_death` 直调代替）：(i) 死者名下
**只有 latent 链**时，结算前后 Chronicle 记录
**零新增**；(ii) 含 fermenting 链时，Chronicle
新增**恰 1 条**且为引擎经 jianghu public 同步的
收尾条、**全库不存在** `event_type ==
"KARMA_CHAIN_DEATH"` 的记录（server 侧汇总
编年史已按 MF-4 裁决删除，§7.1/§6.3 口径：
latent 静默、fermenting 由引擎 `_dissipate`
单记——回归对象包含 `server/world.py` 不得再
record 该事件类型）。
- K-16 对象死亡与无仇主：`test_counterparty_death_paths`
——en 链对象发酵中死亡 → dissipated
(counterparty_dead)；xue 链死者无同宗在世 →
到期 dissipated(no_avenger）且有传闻收尾；
对象被主体亲杀 → 原链 superseded_by_kill 且
xue 链另起。

兼容与降级：

- K-17 旧存档兼容：`test_old_save_compat`——以
v0.3.0 的 tiandao.db 副本（或删除 karma_chains
表的老库构造）启动 init_db：补表成功、老角色
登录/状态/诺言/道统全流程不报错、/因果链 返回
空面板；老角色既有 ≥60 态度在上线后首次小步进
（不跨阈）不起追溯链。
- K-18 AI 降级不断链：`test_ai_down_chain_unbroken`
——monkeypatch ai_ready=False 与 _chat_json 抛
异常两姿势：全流程（起链→发酵→兑现→面板）
数值与状态逐值同 AI 开启组（台词文本除外），
tick 不抛异常、耗时无 AI 等待。

双端与留痕：

- K-19 双端查询一致：`test_dual_end_panel_same_source`
——同一库状态下 server handle /因果链 与 CLI
面板函数输出逐字相等（照 /墓碑 同源断言法）；
查询前惰性推进生效（到期链在首次查询即呈
resolved 近史）。
- K-20 了结留痕：`test_resolution_traces`——
行为要求不变（原文）；**必测断言清单
（R1/MF-5 补明，后端补测验收依据，缺一即
本条未达）**：
  (a) jianghu：任一链 resolved 后，jianghu_events
  中该链对应 `kind="karma_chain"` 条目**恰 1 条**；
  (b) 编年史同步：同一 resolved 触发
  world_chronicle 同步**恰 1 条**（经 append_event
  public 同步产生），无第二条链来源的编年史；
  (c) 世界频道：xue 链 resolved 后 world_messages
  中有 level="major" 的昭告**恰 1 条**；非 xue
  链 resolved 不产生 major 条；
  (d) 消散留痕差异：latent 链 dissipated →
  jianghu **零新增**、chronicle **零新增**（只记
  链节点与面板近史）；fermenting 链 dissipated
  → jianghu 收尾**恰 1 条**（+ 其 public 同步的
  chronicle 1 条）；
  (e) 账本隔离：链事件写入 EventLedger 时
  `type="KARMA_CHAIN"`；断言
  `EventLedgerRepository.query_feud_pairs`（或其
  引擎等价读口）结果不含该链事件，且构造「仅有
  KARMA_CHAIN 事件」的账调
  `RevengeEngine.force_callback` 时返回 None 或
  结果不取链事件为种子（链不入 RevengeEngine
  种子集，§4.5）。

回归与冒烟：

- K-21 回归：全量 pytest ≥ 689 + 新增且 0 failed;
`node --check web/app.js` 过；test_qa2_frontend_
contract 3 例过（_status_dict 只增键断言）。
- K-22 隔离冒烟（全新 DB 副本）：注册玩家 →
赠礼/交谈经营态度跨 +60（赠礼按 §8.3.1 计价，
冒烟号须备足 ≥300 灵石或以委托/交谈补足，
R1/MF-1）→ /因果链 见 latent
en 链 → 快进时间（注入/改库时刻）走 /世情
推进至 resolved → 查灵石/修为落账与子顶 →
/因果链 近史见结果 → 击杀一名 NPC → xue 链
起 → 死亡结算 → 旧链全 dissipated → 转世
新角 /因果链 为空、/道统 前世因果段与
v0.3.0 口径一致。

---

## 13. Out of Scope（明确不做）

- 玩家↔玩家因果链（含玩家间诺言起链、玩家杀
玩家起链）：双离线/双死亡/对端呈现均无既有
管道，本轮只留 counterparty_kind 字段预留。
- NPC↔NPC 起链（其恩怨归 agenda/collusion/
jianghu_sim 既有系统）。
- 修 server `_fight` 不调 settle_on_kill 的既有
双端分歧（§0.2-1）——待裁决 C-1；本轮 S5 只
挂引擎层，不顺手改 server 战斗结算。
- 改 `/因果` 任一端既有语义；改 RevengeEngine、
cascade_kill、hunt、EventChainEngine 的任何
既有行为。
- 链的玩家主动操作：无「化解/偿还/催讨/弃链」
指令（链是天道记账，不是任务系统）；不进
goals 目标系统、不新增目标源。
- LifeTrace/LegacyAccount/Character 模型改动；
前世因果段呈现未了之链；转世带链或链折算
道统点。
- Web 前端可视化（命盘链进度条等）：本轮只给
文本面板 + _status_dict 只增键，前端渲染另立项。
- 链的跨纪元特殊处理：大劫走逐人死亡结算即
覆盖（§7.1)，不做纪元级批量清算代码。
- 心魔/道心系统联动钩子：链 sin 落账经既有
管道自然传导（§1.4)，不新增直连。

---

## 14. 待总管裁决点（主策已给推荐，裁决后回填本节）

> **总管裁决（2026-11-05，开工前回填）：C-1 另立工单（本轮不顺修 server 结赏，S5 只挂引擎层）；C-2 维持游戏日尺度；C-3 维持血仇链无直接数值支；C-4 接受玩家↔NPC 限定；C-5 采用 `/因果链`。五点全按主策推荐执行，后端/前端不得另行变更。**

- C-1 server 击杀不结悬赏的既有分歧：本轮顺修
还是另立工单？**推荐另立工单**（属 account/
combat 域的双端一致性问题，与链解耦；链 S5
挂引擎层已为其留好接口）。若裁决顺修，须给
后端岗追加 server _fight 结赏 + 回归
test_bounty 双端用例，K-5 扩展 server 路径。
- C-2 发酵时长尺度：本 Spec 用游戏日（240s/日，
报恩 ≈36 分钟现实）。若 Martinez 要「数日后
才来报恩」的史诗感，可整体 ×60 改现实日尺度
——但灰度真人试玩（序列 ③）将很难在试玩期内
见到一条链走完。**推荐维持游戏日尺度**，
以试玩可验证优先。
- C-3 血仇链无直接数值支（§4.5）：靠议程寻仇
这一既有牙齿 + 态度/业力小额记账。**推荐
维持**；若要直接牙齿，须同步收紧 RevengeEngine
回访效果（防双重重惩），属跨系统改动，另议。
- C-4 玩家↔NPC 限定：(a）源题面即玩家对 NPC,
但诺言存在玩家间形态——本轮玩家间诺言不起链
是否可接受？**推荐可接受**（v1 宁少而实，
数据模型已预留）。
- C-5 命令名 `/因果链`：与 CLI 既有 `/因果`
(KarmaLink 列表）相邻易混。备选 `/天链`。
**推荐 /因果链**——语义自明，且 server 端
/因果 是回访别名、更需以全名区分新命令；
帮助文案中三者并列注明。

---

## 15. 流程门禁（沿一人公司技能）

主策（本 Spec）→ 总管确认 + §14 裁决回填 →
后端/前端按 §11 在本 worktree 实现 → QA 对账
（数值账：K-8/K-10 与 §8.3 经济账；幂等账：
K-11/K-12；兼容账：K-17；死亡账：K-15）→
独立评审（只审不改，must-fix 销账）→ 发版 +
ls-remote 核验 → 总管汇总（含微信同步，沿
站立要求）。线上常驻服不重启（沿既例，待
Martinez 指示）。

---

## 16. 评审返工裁决回填（R1）（新增）

独立评审 5 条 must-fix 经总管裁决后，由主策岗
回填本节索引；裁决原文不改，正文以各落点为准。
实现返工任务编号 T-R1 起，供后端岗领活。

| 编号 | 总管裁决（要点） | Spec 落点 | 实现返工（T-R1） |
|---|---|---|---|
| MF-1 | 恩链净负旧论证被实测推翻（12 灵石可 0→60）；验收：真实 do_gift 路径 0→60 最低灵石成本 ≥300、恩链兑现净收益 ≤0、须真实 do_gift 回归（禁 set_attitude 直设充经营） | 路线选 **(A) 赠礼侧改革**：§8.3 改写 + 新增 §8.3.1（公式/下限证明/涟漪清单/废弃旧口径）、§3 S1 覆盖备注、§10 增补计价常量、新增 **K-1A**、K-22 冒烟注 | T-R1a：`chat_actions.do_gift/do_trade` 人情支按 §8.3.1 公式改 delta；T-R1b：按 K-1A 补公式边界 + 真实路径成本两组测试 |
| MF-2 | S5 兜底新建为死代码，采方案 (b)：删除兜底新建语义，S5 仅续链 | §3 S5 改写（标题/行为/废弃口径）、§3 来源总表 S5 行、**K-5 改写**（续链 +1 保留 + 无链断言不新建） | T-R1c：`KarmaChainEngine.note_bounty_settled` 删除无链新建分支，无链返回 None |
| MF-3 | 被每日预算暂缓的链豁免 deadline 与链龄硬顶消散；K-10 原回拨 resolved_at 写法判无效证据须重写 | §2.1 新增 `budget_deferred` 字段、§2.2 迁移表注、§4.2 新增豁免块（标记/行为/死亡不豁免边界）、§8.1 新增豁免行、**K-10 改写**（真实 now 单调推进三段全程 + 明文禁回拨）、K-7 逾期场景口径随之修正 | T-R1d：推进逻辑落豁免（存活检查先行）+ 顺延时置标记落库；T-R1e：按新 K-10 重写 `test_daily_resolve_budget`、按修正后 K-7 调逾期用例 |
| MF-4 | 删除 server/world.py 的 KARMA_CHAIN_DEATH 汇总编年史；Spec 口径不改 | §7.1/§6.3 **维持原文不改**；**K-15 补** server 路径断言（走 `_settle_if_needed`：latent-only 编年史零新增、fermenting 只由引擎留一条、全库无 KARMA_CHAIN_DEATH） | T-R1f：删 server/world.py 对应 record 块；T-R1g：K-15 补 server 路径用例 |
| MF-5 | K-20 零证据：补必测断言清单作为补测验收依据，行为要求不改 | **K-20 改写**：加 (a)–(e) 必测断言清单（jianghu kind=karma_chain 恰一条 / 编年史同步恰一条 / xue 的 WorldChannel major / latent 与 fermenting 消散留痕差异 / EventLedger KARMA_CHAIN 不入 RevengeEngine 种子且 force_callback 不取链） | T-R1h：按清单补齐 `test_resolution_traces` 断言 |

OBS 顺手项（Spec 侧确认）：

- OBS-1/OBS-2（润色落锚）：§9 与 §2.1 的**润色
相关口径维持原文不改**——润色在落锚发效之后、
只替换呈现副本；实现须回齐至与原文一致，此点
Spec 无改动（§2.1 模型因 MF-3 新增
`budget_deferred` 字段，与润色口径无关，不在此
列）。唯 OBS-2 的 exp 侧落字：§4.4 新增「修为
落账钳制」条（落账钳 max_exp、resolution.effects
记实际落账值），K-8 加对应断言注脚。
- OBS-5（诺链括注）：§4.4 表加注脚 1——括注
单值为初始 strength 参考值，续链加强后兑现
以 eff 公式与 KARMA_CHAIN_EFFECT_CAPS 为准；
K-8 注脚同此口径。
