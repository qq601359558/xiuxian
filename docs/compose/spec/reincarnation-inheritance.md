# Spec：转世继承玩法（reincarnation-inheritance）

状态：已交付 v0.3.0-gray.7
基线：main `607ea3a`（v0.2.4-gray.6），全量回归基线 674 passed / 0 failed
目标版本：v0.3.0-gray.7

---

## 0. 现状盘点（实证，文件:行号见盘点记录）

**已存在、必须复用、不得重复造轮子：**

- 道统元进度权威在 `core/legacy.py`：`LegacyAccount`（player_legacy 整行 JSON，
字段 points/total_lives/total_points_earned/death_times/past_lives(截10)/
wallet_stones/wallet_ledger）；`PastLife` 只有 name/realm/cause/lifespan_lived/
sin/merit/points_gained/died_at 八个摘要字段。
- 道统点：`compute_points` 单世封顶 25（config LEGACY_MAX_PER_LIFE），
极速送死惩罚 ×0.5；池本身无账户上限，靠消费端钳制。
- 降生加成（既有「抉择」雏形）：`LEGACY_BOOSTS` 四项
（stones 1点/+150石、lifespan 2点/+8岁、root 4点/效率+0.25封顶2.5、
skill 2点/固定残篇四选一），`apply_birth_boosts` 去重、单次至多 3 项
（LEGACY_MAX_BOOSTS_PER_LIFE）、逐项查余额扣点。注意 skill 给的是
**固定残篇，不是前世功法本体**。
- 死亡结算中枢：server `World._settle_if_needed`（world.py:240-318）与
CLI `settle_and_reincarnate`（cli/main.py:327-412）双编排，共用引擎。
未结算分支顺序：置 DEAD → sweep 资金归集 → 死亡钩子（灵宠/灵田/委托/
诺言消散）→ `LegacyEngine.settle_death` → 落盘 → Chronicle LEGACY_SETTLE。
`settle_death` 靠调用方以 `death_settled` 守卫、文档注明「必须只调用一次」，
函数本身不自查。
- 转世：server `World.reincarnate`（world.py:408-471）/ CLI
`prompt_reincarnation`（cli/main.py:284-326）。`characters` 表按 user_id
唯一，新角 save 直接覆写旧行——**旧角行囊/功法/旧 id 在覆写后不可恢复，
继承素材必须在覆写前捕获到账户层**。转世冷却门 `check_reincarnate_gate`
目前只有 CLI 调用，server 未接（既有不一致，本轮 Out of Scope，见 §7）。
- 关系数据（全按角色 id 键、无账户键）：
- NPC 态度：`npc_minds.attitudes_json = {对方角色id: {value -100..100, label}}`，
`core/npc_mind.py` ensure_mind/attitude_toward/shift_attitude；
死亡无人处理，旧 id 条目成孤儿，新角从 0 开始。
- KarmaLink（core/bounty.py KarmaLink + core/collusion.py）：仇/恩/师徒/
结拜/诺/怨/断，strength 整数；死亡无人处理，成孤儿行。
- 诺言账 core/promises.py：死亡时 `PromiseEngine.on_owner_death`
把未结诺全部置 DISSOLVED（不判违约），行保留为终态历史；
该函数目前返回 None。
- 留痕现状：past_lives（账户私有）+ Chronicle LEGACY_SETTLE + 飞升榜
（ascension.py 只读 past_lives 计分，现世不入、NPC 排除）。
传说 legends 只由大劫写，死亡不写。**没有面向他人的「墓碑」查询，
没有结构化的前世清单给 Web**（CLI `/道统` 有前世典籍表，Web 只有
纯文本 feed；server `dead_payload.legacy` 不含 past_lives）。
- account-death-rework.md:154 既有裁定：「物品/成长类资产默认不保留」。
本轮遗物留存是**对该裁定的有界例外**（见 §2.4），须在本 spec 明示，
不得扩大解释。

**结论**：本轮不新建账本、不新建表。全部新状态落 `LegacyAccount`
新字段（Pydantic 默认值补齐、存量零迁移），新逻辑落新模块
`core/inheritance.py` + `core/legacy.py` 引擎扩展，两入口共用。

---

## 1. 五步推演（requirement-evaluator）

### 1.1 解构本质
- 表层需求：墓碑可查、因果影子、转世三选一继承。
- 本质诉求：死亡从「删档式惩罚」变成「跨世进度」——玩家要能
**看见**前世留下了什么（留痕）、**感受到**世界记得前世（因果影子）、
**做一次有代价的取舍**（抉择），且多世滚雪球被硬顶钳住。
- 验收本质：一个新角在转世后 1 分钟内，能在命盘/道统里逐条指出
「我继承了什么、来自哪一世、为什么」，且 NPC 对他的初始态度
确实不同于白板新角。

### 1.2 可行性评估
- 数据全在账户层可达：态度/KarmaLink/诺言/行囊/功法在死亡结算时
均可读；捕获点选在 `settle_death`（双入口共用引擎），一次实现两端生效。
- 存储零迁移：LegacyAccount 加带默认值的字段，旧行自动补齐（钱包先例）。
- 前端增量小：死亡弹层已有 legacy 汇聚点、命盘已有 dl.kv、/道统 已有
文本通路；只加一处结构化下发与两处渲染。

### 1.3 不足与盲区（已在设计中逐条堵住）
- 覆写时序坑：新角 save 覆写旧行 → 素材必须在 settle 时捕获进账户，
不能等转世时再读旧角（CLI 转世入口旧角对象已不在手边，同理）。
- 诺言在 settle_death 之前已被钩子消散 → 未了之诺快照必须由
`on_owner_death` 返回、经调用方注入 settle（见 §2.2）。
- 重放/双领：上一轮 sweep 崩溃重放教训——所有「领取」动作必须有
账户层已领标记（按世次 life_no + 角色 id 双键），且态度施加用
set（绝对值）不用 add，天然幂等。
- 玩家间关系（师徒/结拜）不能单方面复活：只入痕迹清单展示，
不重建 KarmaLink、不改对方数据（见 §2.3）。
- 飞升榜衔接：飞升榜只读 past_lives，本轮不动 past_lives 语义与
计分，痕迹是平行结构，禁止双记账（settle 只归档一次 PastLife，
trace 与之同源同次生成）。

### 1.4 举一反三
- 横向：墓碑查询与飞升榜「查名」同类——复用按名检索口径，但数据源
用 traces（含未上榜的平凡一世，墓碑面前人人有份）。
- 纵向：traces 截断策略须与 past_lives(10) 对齐防账户行膨胀；
影子施加只认最近一世（current trace），不叠加多世（防滚雪球）。
- 涟漪：LEGACY_BOOSTS 新增键会改变数字序号映射（/转世 数字选加成）
——新键只能**追加在 dict 末尾**，既有四键序号不变。

### 1.5 完善方案
即 §2 设计。备选（已否决）：新开 traces 表（侵入大、无 SQL 索引
需求）；遗物原样保留全部行囊（推翻既有裁定且破坏经济）；
诺言复活为新角的 ACTIVE 诺（对方已按消散结算，复活即双重记账）。

---

## 2. 设计

### 2.1 数据模型（LegacyAccount 新增，全部带默认值）

```python
class LifeTrace(BaseModel): # core/legacy.py 新增
life_no: int # 第几世（= 生成时的 total_lives+1）
character_id: str # 本世角色 id（捕获幂等键）
name: str; realm: str; cause: str
lifespan_lived: float = 0.0
sin: int = 0; merit: int = 0
points_gained: int = 0 # settle 后回填，与 PastLife 同值
died_at: float = 0.0
sect: str = "" # 本世宗门（空=散修）
skills_learned: List[str] = [] # 非默认功法名（skills 排除 吐纳术/御剑术 后，截 12）
belongings: List[str] = [] # 行囊+穿戴名快照（去重保序，截 20；遗物候选池）
shadow: List[ShadowEntry] = [] # 因果影子（见 2.3）
open_promises: List[PromiseEcho] = [] # 未了之诺回声（见 2.2）

class ShadowEntry(BaseModel):
npc_id: str; npc_name: str
value: int # 前世态度原值（-100..100）
kind: str = "attitude" # attitude | link（KarmaLink 折算，见 2.3）

class PromiseEcho(BaseModel):
other_name: str; desc: str; kind: str = ""
role: str = "" # 我许诺 / 诺于我

LegacyAccount 新增字段：
traces: List[LifeTrace] = [] # 截最近 10，与 past_lives 对齐
shadow_applied: Dict[str, Any] = {} # {"life_no": int, "char_id": str} 已施加标记
inheritance_claims: Dict[str, int] = {} # {"heirloom": life_no, "art_memory": life_no} 已领世次
```

`Character` 模型**不加任何字段**（角色行活不过转世覆写，铁律）。

### 2.2 留痕固化（死亡时，`LegacyEngine.settle_death` 内）

- settle_death 在归档 PastLife 的同一次调用内生成 LifeTrace：
- 态度快照：遍历 `NpcMindRepository` 全部 mind 行，取
attitudes[char.id] 且 |value| ≥ 30（SHADOW_MIN_ABS）者，
按 |value| 降序截 6（SHADOW_MAX_ENTRIES），记 npc_id/name/value。
NPC 名经 CharacterRepository.get_by_id 取（取不到则跳过该条）。
- KarmaLink 快照：`KarmaLinkRepository` 中 a_id/b_id == char.id 且
对端为 NPC（user_id 以 npc_/ai_npc_ 开头）的行，按类型折算为
ShadowEntry(kind="link")：恩/师徒→+，仇/怨→−，结拜→+，
断→跳过；折算值 = clamp(strength*10, 10, 40) 带符号；
与态度条目同 npc 时**只保留绝对值大者**（去重合并）。
- 未了之诺：`PromiseEngine.on_owner_death` 改为**返回**被消散的
未结诺摘要列表 [{other_name, desc, kind, role}]（行为不变，
仅多返回）；server `_settle_if_needed` 与 CLI `settle_and_reincarnate`
两处调用方把返回值作为新参数 `dissolved_promises` 传入 settle_death，
写入 trace.open_promises（截 5）。直接调用 settle_death 未传参时为空。
- skills_learned / belongings / sect：从 char 本体快照。
- 幂等：traces 中已有 character_id 相同者 → 不重复生成
（settle_death 本身仍按既有契约只调用一次，此为崩溃重放防线）。
- 世界可见留痕（同次结算内，失败不阻断结算，try/except 静默）：
- ChronicleRepository.record("TOMBSTONE", name, 墓碑文：
「{name} · {realm} · {cause} · 享寿 {lived} 岁 · 业 {sin} 德 {merit}」)
- core/rumors.add_rumor 一条死亡传闻（truth 1.0，文本含道号与死因）。
- 飞升榜：不改。past_lives 照旧归档一次，score 口径不变（验收 R-4）。

### 2.3 因果影子（转世时自动施加，免费，非 boost）

新模块 `core/inheritance.py`：

```python
apply_karma_shadow(account, new_char, *, retention, cap) -> List[dict]
```
- 数据源：account.traces[-1]（最近一世）且其 character_id!= new_char.id；
无 trace（旧档/首世）→ 空操作返回 []。
- 幂等：account.shadow_applied == {"life_no": trace.life_no,
"char_id": new_char.id} → 直接返回已施加清单（不重复写）。
- 施加：对每条 ShadowEntry，value' = clamp(round(value*retention), -cap, cap)；
|value'| < 8 跳过；NPC 角色仍存在（get_by_id）才写：
`NpcMindRepository.set_attitude(npc_id, new_char.id, value')`
（绝对值写入，重复执行结果不变）。
- 基准参数（config）：SHADOW_RETENTION = 0.4、SHADOW_CAP = 25。
- 施加结果记 account.shadow_applied 并随 account 落盘；
返回 [{npc_name, value, label}] 供转世文案与因果清单展示。
- 玩家间 KarmaLink、师徒/结拜：**不施加、不重建**，只在因果清单
以文字呈现（trace 中以 kind="bond" 的展示条目保存对方名与类型？
——不进 shadow 数组；由 legacy_info 渲染时从 KarmaLink 孤儿行
现查现拼，见 2.5 注）。

### 2.4 继承抉择（扩既有 boosts，三项新键追加在 LEGACY_BOOSTS 末尾）

| key | 名 | 价 | 效果 | 硬顶/幂等 |
|---|---|---|---|---|
| `heirloom` | 遗物留存 | 5 点 | 从 traces[-1].belongings 选 1 件（参数式 `heirloom:<物品名>`）移入新角 inventory（不穿戴）；同时从死者旧行 belongings 语义上消费——实现上以 claims 标记为准，旧行反正被覆写 | 每世限 1 件；inheritance_claims["heirloom"]==life_no 即拒；物品不在候选池即报错不扣点 |
| `art_memory` | 前世心法 | 4 点 | 新角学会 traces[-1].skills_learned 的第 1 门（按快照序）；无候选时回退既有残篇表（与 skill 同口径取首门未学者） | 每世限 1 门；claims["art_memory"] 同上 |
| `bond_echo` | 旧缘重续 | 3 点 | 本次转世的影子施加改用 retention=0.75、cap=50（BOND_ECHO_RETENTION/CAP） | 只影响本次施加；施加本身幂等，重复转世请求被「此世尚存」门拦截 |

- `apply_birth_boosts(character, account, boost_keys, *, old_trace=None)`：
签名向后兼容（old_trace 可选）；boost token 允许 `key:param` 形式
（仅 heirloom 用 param，其余带 param 视为非法 key 报错）。
领取顺序：先校验（候选存在、未领、点数足）→ 再扣点 → 再落效果
→ 置 claims；任一校验失败该项进 errors、不扣点、不置标记（可改选）。
- 既有四项（stones/lifespan/root/skill）行为、价格、序号**零变更**；
单次至多 3 项总上限不变——三项新抉择与旧加成共同竞争 3 个名额，
这就是「不能全都要」的硬约束（spec 明示，不另设点数包）。
- server `/转世` 分发：token 命中（含 `heirloom:` 前缀）解析须扩展
（world.py:697-716），数字序号按 dict 顺序自然延伸至 7 项。
- CLI `_parse_boost_keys` 须能解析 heirloom 的物品参数
（编号选遗物时追问物品名或取 belongings 第 1 件并明示，见任务 T6）。
- 评审修订（MF-2 关联·观察1）：`heirloom`/`art_memory` 必须有 old_trace（来源世痕迹）才能领取；无前世痕迹时该项报错、不扣点、不置 claims，claims 一律以 trace.life_no 为键（不再用合成 life_no）。

### 2.5 查询与呈现（行为契约）

后端：
- `legacy_info` / `legacy_info_id` 返回新增（只增字段）：
- `traces`：最近 8 世 LifeTrace 摘要（含 shadow/promises 计数与清单）
- `karma_shadow`：当前角色这一世被施加的影子清单
[{npc_name, value, label, from_life}]——由 shadow_applied +
traces 对应世 shadow 按当前 retention 口径重算展示（只读推导，
不落新表）；未施加过为空。
- `dead_payload.legacy` 补 `past_lives`（同 legacy_info 口径）与
`trace`（刚逝一世的 LifeTrace 摘要，含 shadow 预览与 open_promises），
供死亡页渲染留痕摘要；旧字段不动。
- `_status_dict` 新增键 `past_life`（只增）：
{lives: int, last_name: str, last_cause: str, shadow_count: int}，
无前世时 lives=0、其余空/0。前端读它须走既有 ==null 降级。
- 新命令（双端）：
- `/前世`：server 补此别名 → 与 `/道统` 同一 handler（CLI 已有）。
- `/墓碑 <道号>`：core/inheritance.py `find_tombstone(name)` 扫描
LegacyRepository.list_all() 的 traces 按 name 精确匹配，
返回最近一座墓碑的文本（道号/境界/死因/享寿/业德/道统点/
一句因果摘要：影子条数与未了之诺条数）；查无 → 「江湖无此碑」。
server 与 CLI 各加一条分发，文案同源（引擎拼文本）。
- `/道统` 文本（server handler 与 CLI render_legacy_panel）追加
「前世因果」段：最近一世 trace 的 shadow 清单（NPC 名 + 态度词 +
折算后本世值）与 open_promises 回声（对方名 + 诺文摘要 +「已随
旧世消散」注），无则整段省略。
注：玩家间旧缘（师徒/结拜孤儿 KarmaLink）在该段以「旧缘：
{对方名}（{类型}）——已随旧世消散」文字行呈现，数据现查
KarmaLinkRepository 按旧 char id（取自 traces[-1].character_id）。

前端（web/，只动必要面，id/存储键冻结规则沿用 ui-polish 轮）：
- 死亡弹层：`showDeath` 在 deathLegacy 区追加渲染「前世留痕」摘要
（legacy.trace：享寿/死因已有首行，本次加：影子预览
「{npc} 对你前世{态度词}，余绪及身」逐条 + 未了之诺条数），
数据缺失（旧后端/恢复路径无 trace）时整段不渲染、不报错。
- boostBox：boosts 列表自动含新三项（后端 list_boosts 驱动）；
heirloom 被选中时，在 boostBox 下方出现候选物品下拉
（legacy.trace.belongings，无候选则该项置灰并注「前世无遗物」）；
doReborn 拼命令时 heirloom 拼为 `heirloom:<所选物品名>`。
- 命盘：dl.kv 加一行「前世」`stPastLife`，applyStatus 读
st.past_life（lives>0 显示「{last_name} · {last_cause}」，
另起小字示 shadow_count>0 时「因果余绪 {n} 条」），
键缺失按既有降级写「—」。
- 不新增 data-cmd 按钮（/墓碑、/前世 走敕令栏输入；
避免前端契约测试的双端平价面扩大）。

### 2.6 数值总表（全部进 config，规则引擎裁决）

| 常量 | 值 | 说明 |
|---|---|---|
| SHADOW_MIN_ABS | 30 | 态度快照门槛 |
| SHADOW_MAX_ENTRIES | 6 | 每世影子条数上限 |
| SHADOW_RETENTION | 0.4 | 基准衰减 |
| SHADOW_CAP | 25 | 基准施加绝对值顶 |
| SHADOW_APPLY_MIN | 8 | 施加后绝对值低于此不落 |
| BOND_ECHO_RETENTION | 0.75 | 旧缘重续衰减 |
| BOND_ECHO_CAP | 50 | 旧缘重续顶 |
| 遗物 | 1 件/世，5 点 | 候选池 = trace.belongings |
| 前世心法 | 1 门/世，4 点 | 候选 = trace.skills_learned |
| 既有上限 | 单世道统 25、单次 boosts ≤3、新角 150 石 | 全部不变 |

多世碾压防线小结：影子只认最近一世、不叠加；态度本身 ±100 钳；
boosts 3 名额与点数池（单世入账 ≤25）双钳；遗物/心法每世各 1。

## 3. Out of Scope（明确不做）
- 不复活诺言为新角的 ACTIVE 诺；不重建任何 KarmaLink。
- 不动飞升榜计分、past_lives 结构与截断。
- 不修 server 转世冷却门未接的既有不一致（另立项）。
- 不做墓碑地图/遗迹探索玩法；墓碑只有查询。
- 不改 `characters` 表结构、不加新表、不改 API 既有字段语义（只增）。
- 遗物不含阵盘（arrays 不入 belongings 快照池）、不含自创功法 DSL
整体迁移（art_memory 只带功法名；自创功法名若在 skills 中，
带名后其 DSL 不随——新角学到同名时按普通功法处理，属已知降级，
在报告残留风险中明示）。

## 4. 任务与验收（编号，逐条可观察）

实现任务：
- T1 core/legacy.py：LifeTrace/ShadowEntry/PromiseEcho 模型 +
LegacyAccount 三新字段；settle_death 生成 trace（含快照/合并/
幂等）+ 回填 points_gained；world 纪录（chronicle TOMBSTONE +
rumor）以 try/except 包裹。
- T2 core/promises.py：on_owner_death 返回消散摘要（行为不变）。
server/world.py 与 cli/main.py 两处调用方注入 dissolved_promises。
- T3 core/inheritance.py：apply_karma_shadow、find_tombstone、
tombstone 文本、因果清单拼装 helpers。
- T4 config.py + core/legacy.py：LEGACY_BOOSTS 末尾追加三键；
apply_birth_boosts 支持 old_trace 与 heirloom:param、claims 校验。
- T5 server/world.py：reincarnate 接 shadow 施加（顺序：建角 →
boosts（含 bond_echo 判定 retention）→ apply_karma_shadow →
落盘）与响应加 karma_shadow/applied 字段；dead_payload.legacy
补 past_lives/trace；legacy_info(_id) 补 traces/karma_shadow；
_status_dict 加 past_life；/道统 文本加前世因果段；新增
/前世 别名、/墓碑 分发。
- T6 cli/main.py + cli/views.py：/墓碑 分发；render_legacy_panel
加前世因果段；_parse_boost_keys 支持 heirloom（编号选遗物时
列 belongings 并让玩家选件，缺候选明示跳过）。
- T7 web 前端三处（见 2.5 前端段）。
- T8 tests/test_reincarnation_inheritance.py 新文件（见 R 组）。
- T9 发版 v0.3.0-gray.7 四处同步（config VERSION/README/
CHANGELOG/gray-runbook）。

验收条目：
- R-1 留痕落账：构造 NPC 态度 ±(≥30 与 <30 各一)、一条未结诺的
角色死亡结算后，traces[-1] 含：态度快照只收 ≥30 者、link 折算
合并去重、open_promises 与消散摘要一致、belongings/skills_learned
快照正确；PastLife 仍只归档一份、道统点与旧口径一致。
- R-2 留痕幂等：同角色重复走 _settle_if_needed / 崩溃重放路径，
traces 不增、道统点不双发、TOMBSTONE 大事记不双记（或至多与
既有 LEGACY_SETTLE 同步一次）。
- R-3 影子施加：转世后目标 NPC 对新角态度 == clamp(round(v*0.4),±25)
且 |v'|≥8 才落；白板对照（无 trace 账户）态度为 0；
同一转世重复调 apply_karma_shadow 结果不变（值不翻倍）。
- R-4 飞升榜不重复记账：同一死亡前后 AscensionEngine 对该账户
条目数与分数不变（trace 不入榜）。
- R-5 抉择互斥与硬顶：一次转世选满 3 项后第 4 项被拒（既有口径）；
heirloom+art_memory+bond_echo 三项同选可成，但各自 claims 落账；
点数不足时对应项失败、不扣点、不置 claims。
- R-6 继承幂等：heirloom 对同一世重复领取（直接调引擎构造重入）
第二次被拒且物品不复制；art_memory 同理；reincarnate 活角
重入被「此世尚存」拦截（既有）。
- R-7 遗物候选约束：选不在 belongings 中的物品名 → 报错不扣点；
成功时新角 inventory 恰含该件 1 份、未穿戴。
- R-8 bond_echo：选它时影子按 0.75/±50 施加（与 R-3 对照数值差）；
不选时按基准。二者 label 随 set_attitude 既有口径。
- R-9 前世因果可见：legacy_info 返回 traces 与 karma_shadow；
/道统 文本含「前世因果」段；dead_payload.legacy 含 trace 与
past_lives；_status_dict 含 past_life 四键。
- R-10 墓碑可查：他人 token 以 /墓碑 <已故道号> 查得墓碑文本；
查不存在名字返回无此碑；CLI 同命令同文案（引擎同源断言）。
- R-11 旧存档兼容：以缺新字段的旧 LegacyAccount JSON 加载成功
且默认值正确；旧角色（无 trace）死亡/转世全流程不报错、
影子为空操作。
- R-12 回归：全量 pytest ≥674+新增 且 0 failed；前端契约 3 例过；
node --check web/app.js 过；test_web_lifecycle.py 脚本实跑过。
- R-13 冒烟（隔离副本全新 DB）：注册→置态度/结诺→模拟死亡→
登录见 dead payload（含 trace）→/转世 选 heirloom+art_memory→
新角 /道统 见前世因果、/墓碑 查前世、NPC 态度实测为影子值、
行囊含遗物、skills 含前世心法。

## 5. 流程门禁（沿一人公司技能）
主策（本 spec）→ 后端/前端隔离实现 → QA 对账（经济账：道统点
入账/消费守恒；幂等账：R-2/R-6；兼容账：R-11）→ 独立评审
（只审不改，must-fix 销账）→ 发版 v0.3.0-gray.7 + ls-remote 核验
→ 总管汇总。线上常驻服不重启。
