# Spec：游戏感改造第三期（game-feel-phase3）

- 基线：worktree `.worktrees/game-feel-phase3`，分支 `feat/game-feel-phase3`，基线 main `76310b4` = v0.3.9-gray.16（二期已合入并发版）。
- 状态：**待实现**（本文件为唯一产出；本轮不写任何业务代码）。
- 定稿依据：`~/workspace/天道因果录-游戏感改造方案.md`（下称「方案」）§4c（仪式六幕全集）、§7 第三期、§9 已定口径；`docs/compose/spec/game-feel-phase1.md`（下称「一期 Spec」）§4 仪式框架与 §4.3 记账；`docs/compose/spec/game-feel-phase2.md`（下称「二期 Spec」）§5（戏剧待回应 KV）、§8.2、§10（现行 mobile 预算）与文末裁决记录（⑤.6 集成裁决）。**口径冲突时以方案为准；方案与代码现状冲突时按 §0.2 的实测口径施工并逐条记账；任务边界与方案冲突时以任务边界为准，记账于 §0.3。**
- 红线（全 Spec 通用，沿一、二期）：寿元是硬通货（规则一字不改）、规则引擎裁决数值、LLM 只叙事/言行；**仪式路径零新增 AI 调用、零锁内耗时增长**（一期 §4.1/C4 口径，本轮三幕全部纯本地模板拼装，连方案 §4c 允许的器灵 AI 台词也按任务铁律收为本地，见 §0.3-X4）；涉及角色数据遵循 `AGENTS.md` 道体合规守恒律（写路径统一 `CharacterRepository.save`——本轮仪式层本身零写路径）。
- 本轮范围（定死，不扩不缩）：① 仪式补全三幕——得宝幕（§3）、器灵认主幕（§4）、天劫独立幕（§5）；② 二期复审边角修复 S-1/S-2/S-4（`core/briefing.py` ⑤.6，§6）。明确不做见 §11（主线章节类型扩充、新图生成、二期复审其余建议项等逐项点名）。

---

## §0 · 五步推演结论摘要（requirement-evaluator）与代码事实纠正

### 0.1 五步推演（方案已定稿、Martinez 已全权授权；本推演只收敛派生口径，不重开方向）

**第一步 · 解构本质。** 表层需求是「补三幕仪式 + 修一个入局边角」；本质是把方案 §4c 的六幕仪式补到全集（C1–C4 首次六幕全验），并把二期截图验收后回写的 ⑤.6 常驻机制修到「最新待回应永不被挤出」。验收本质不是「多了三张弹窗」，而是：三幕的 `result_ref` 与既有落账逐项对得上（C1）、四种看/跳组合下最终状态逐字段相同（C2）、断网无 Key 时三幕文案无空白（C3）、仪式路径静态可证零 AI 且耗时不劣化（C4）；以及 ≥3 件待回应时刷新版 entry 的 queue 必含最新一条（S-1）。

**第二步 · 可行性评估。** 可行，且比方案字面更收敛：实测全仓真正能产出「高阶装备实体入包」的落账点只有藏宝图开匣与盲匣捡漏两处（§0.2-F6/§3.1 全表）——方案 §4c 写的「秘境/藏宝图/炼器」三来源中，秘境两系统结构上不产装备、炼器是名字字符串落账无 uid。器灵认主有唯一现成结算点（`ArtifactSpiritEngine.awaken` 的 `changed=True` 信号）。天劫没有独立结算——它就是 `attempt_breakthrough` 大境界分支本身，独立幕只能是「同一次结算、双幕呈现」，协议设计见 §5.2。成本画像：`core/ceremony.py` 新增 3 个 builder + 1 个谓词（纯读拼装，沿一期同文件先例）；服务端只增挂点 4 处（挖宝、捡漏、器灵唤灵、突破两出口改挂）；响应只增键 1 个（`ceremony_next`，§5.2）；新命令 0 条；新表/新字段/新 config 均为 0；前端双端改动为 kind 文案表/自动略过名单原地扩 + 一段双幕队列呈现逻辑（移动端估算 +18 行 / +0B，§8 实测余量充足，**不需要豁免**）。

**第三步 · 不足与盲区（均已在设计中堵住，标注落点）。**
1. 天劫与突破同源同响应：若沿一期把 `ceremony` 继续放突破幕，天劫幕无处落；若把两幕 beats 拼进一个 ceremony，per-kind 自动略过（`ceremony_skip_<kind>`）与 result_ref 对账都会串味 → §5.2 定「`ceremony`=天劫幕（第一幕）+ `ceremony_next`=突破幕（第二幕，只增键）」协议，并写死致死时 `ceremony_next=null`（死亡幕仍走 dead_payload，不在本响应叠演，沿一期口径）。
2. 命格三选一的可达性在拆幕后易被误伤：choices 若被挪进天劫幕或被第一幕的略过吞掉，一期 C2 即破 → §5.3 写死 choices 只留在突破幕 aftermath（`pending[0]`，MF-2 口径不动）、天劫幕 choices 恒 null、两幕略过互不吞没、双略过时命盘/`/命格` 仍可达。
3. 得宝门槛若按「图鉴点亮」定，信号会倒置（品阶与点亮无关，见 §3.2 裁决）→ 门槛定死为品阶谓词（equip tier≥4 / relic tier≥3），与器灵 `SPIRIT_MIN_TIER=4` 同线。
4. ⑤.6 修复若误改 `list_pending` 本体返回序，会波及 `/回应` 面板与 respond 的既有顺序语义 → §6.1 写死只改 briefing ⑤.6 的**迭代方向**，引擎读口一字不动。
5. queue 总截断 8 条与 highlight≤3 是既有口径：S-1 的「必含最新」保证范围须诚实界定为「补列机制本身不再丢最新项」，总截断挤出不在本条修复范围（§6.3 明示，验收以未触顶场景断言）。

**第四步 · 举一反三。** 横向：得宝谓词写成 ceremony 层通用纯函数（入参 kind/tier），未来探险扩池、自由言行奖励升格时按同型挂点补挂即可，不改门槛；双幕协议（`ceremony` + `ceremony_next`）是通用呈现队列，死亡→转世若未来要同响应连演可复用，本轮不预埋第二例。纵向：六幕齐后 kind 枚举定格为方案 §4c 的六值全集，后续轮次不应再新增 kind（新增即回主策岗）。涟漪：突破两出口的 `ceremony` 字段内容由 breakthrough 变为 tribulation——这是本轮唯一既有字段**内容**变更（键与结构不变），已核查无 handle 级既有测试断言该 kind（§0.2-F3），前端按 kind 通用渲染、文案表补齐即可（§7）。

**第五步 · 完善方案（收敛点，即本 Spec 的四个定死口径）。**
- **K1 · 得宝门槛**：谓词 `(kind=="equip" and tier>=4) or (kind=="relic" and tier>=3)`，挂点只两处（藏宝图开匣、盲匣捡漏），其余候选路径逐条以实测证据不挂（§3.1/§3.2）。
- **K2 · 双幕协议**：一次大境界结算拆两幕——`ceremony` 放天劫幕、`ceremony_next` 放突破幕（builder 本体不改）；致死时只有天劫幕。呈现顺序、略过独立性、命格可达性见 §5.2/§5.3。
- **K3 · 器灵认主信号**：认主发生的唯一事实 = `awaken()` 返回 `changed=True`（首次唤灵）；仪式挂服务端 `/器灵` 唤分支的该分支返回，只增 `ceremony`；台词走本地性格台词池（零 AI，§0.3-X4）。
- **K4 · S-1 修复面**：只动 `core/briefing.py` ⑤.6 一段（迭代方向 + 一行 `_queued_refs` 防御 + 注释口径），不动 `DramaEngine.list_pending`、不动 queue 的 priority/sort/截断口径。

### 0.2 代码事实纠正表（与方案/任务简报描述不符者，一律按实测施工）

| # | 描述出处 | 实测现状 | 本 Spec 口径 |
|---|---|---|---|
| F1 | 方案 §4c 称得宝来源为「秘境/藏宝图/炼器」 | 全仓装备实体（`ItemKind.EQUIP`/`RELIC`）入包点逐一核查（§3.1 全表）：锁妖古窟（`core/dungeon.py`）掉落池只有灵草/丹药名+灵石，秘境（`core/secret_realm.py` step）只产修为/灵石/功德、零物品；炼器（`core/alchemy.py craft`）成功产物是目录名**字符串** append 进 `inventory`、无 `ItemEntity`、无 uid（实体在佩戴时才由 `ItemFactory.from_legacy_name` 补齐）；大荒探险（`core/adventure.py`）装备掉落池高档三件（赤霄剑/玄龟甲/避尘珠）目录 id 均 `_03`、tier 恒 3 封顶。真正产高阶装备实体的只有：藏宝图开匣 `TreasureEngine.dig`（`core/treasure_system.py:379`，四原型 outcome 均可产 `equipment` dict）与服务端内联的盲匣捡漏（`server/world.py` `/捡漏` 分发，RELIC tier4/EQUIP tier3 两档实体） | 得宝幕挂点按实测收敛为两处（§3.3）；其余路径逐条不挂并写证据（§3.1）。这是对方案字面的修正，理由：仪式 result_ref 必须有可对账的获得物锚（uid/实体），不存在的落账点演不出幕 |
| F2 | 方案 §4c 器灵幕称「器灵第一句话（AI 可用则 AI 说、不可用走模板）」；又称得宝「若达器灵门槛（tier≥4 已穿戴），接器灵认主幕」 | (a) 认主结算本体 `core/artifact_spirit.py awaken()`（:360）：门禁 = 已穿戴 + tier≥`SPIRIT_MIN_TIER=4` + 一生一次（`spirit.awakened` 闸门），返回 `{success, changed, message}`——`changed=True` 是首次唤灵的唯一信号（重复唤 `changed=False`、四维不重置；失败 `success=False`）；器灵状态落 `ItemEntity.custom_metadata["spirit"]`（随器不随人）；本地台词池现成（`PERSONALITIES[性格]["lines"]` + `_local_line()` 本地路径）。(b) 得宝入包的法宝在**行囊**里、未穿戴，不满足 awaken 门禁 | (a) 认主幕只挂 awaken 的 changed 分支（§4），台词按本轮铁律走本地台词池、零 AI（与任务铁律冲突处以铁律为准，§0.3-X4）；(b) 得宝幕**不自动串**认主幕，aftermath 只在 tier≥4 时预告「穿戴后可 /器灵 唤」——自动串幕在现状下恒不可达，写了即假承诺 |
| F3 | 一期 Spec §4.3 记账「天劫并入突破幕 beats」；任务简报问 ceremony 现有挂点 | `core/ceremony.py` 现有 builder 3 个（`build_breakthrough_ceremony`/`build_death_ceremony`/`build_rebirth_ceremony`），kind 枚举 = {breakthrough, death, rebirth}；挂点 4 处：突破两出口（`World._breakthrough` 出口①、`World.handle` 心魔后继段出口②，两处均以 `attempt.is_major` 为条件调同一 builder）、`dead_payload`（death）、`reincarnate`（rebirth）。既有测试对 handle 级 `ceremony.kind` 的断言只有 death/rebirth 两处（`tests/test_game_feel_phase1_backend.py` 的 P3-02 段）；breakthrough 的 kind 断言只在 builder 级（同文件 :628 直调 builder） | 本轮双幕协议（§5.2）把两出口的 `ceremony` 内容换为天劫幕、突破幕移 `ceremony_next`：builder 级断言不受影响，handle 级无既有断言被打破；此变更仍按「既有字段内容变更」在 §5.2 与回归口径（§9）中明列 |
| F4 | 任务简报问前端是否按 kind 通用渲染、新 kind 是否需新增分支 | 双端均为通用渲染：桌面 `maybeShowCeremony`（`web/workbench.js`）与移动 `maybeShowCeremonyM`（`web/mobile.js`）都只按 `beats[]` 循环渲染（stage 文案表 + `asset_key` 拼 `/assets/<key>.webp` + choices 按钮组 + result_ref 平铺行），**无 per-kind 渲染分支**。kind 相关硬编码只有三处：① kind 中文名表（桌面 `CEREMONY_KIND_CN`、移动 `CEREMONY_CN_M`，现各 3 项）；② 桌面标题图标三元（death 🕯️ / rebirth 🌿 / 其余 ⚡）；③ 自动略过取消名单 `["breakthrough","death","rebirth"]`（双端各一处：桌面 `ceremonySkipSectionHtml`、移动 `renderCeremonySkipOpsM`）。另注意：choices 按钮在双端都硬发 `/命格 <key>`（`data-fate-choice`），故**只有命格候选形状的 choices 可用此通道** | 新 kind 不需要渲染分支，只需：两张文案表各原地加 3 项、两处略过名单原地加 3 kind、桌面图标三元原地补 loot/spirit 两项；得宝/器灵/天劫三幕的 beats **一律不带 choices**（§2.2 写死），杜绝误触命格通道；新增工作只有双幕队列呈现（§7.2） |
| F5 | 方案 §4c 称天劫与突破「共用结算源，仪式层把一次结算拆成两幕演」 | 结算源唯一 = `BreakthroughEngine.attempt_breakthrough`（`core/breakthrough.py:19`）的大境界分支：小阶返回 `is_major=False`（无雷劫）；大境界返回 `is_major=True`，成功分支**无** `fail_tier` 键、失败四档 `fail_tier ∈ {DEATH, BASE_COLLAPSE, HEART_DEMON, WOUNDED}` 且 `is_fatal` 与 `fail_tier=="DEATH"` 恒等价（DEATH 有两个代码来源：fail_roll≤15 直死、道基崩溃削寿后寿尽转化——两者返回均带 `fail_tier="DEATH"` + `is_fatal=True`）；成功返回带 `roll/prob_pct/judge_source/judge_reason`，失败返回带 `prob_pct/judge_source/judge_reason`（无 roll）。结算内已自带全服昭告：成功且 tier≥2 发 WorldChannel「雷音」major 帖、DEATH/道基崩溃发「天劫」major 帖 | 天劫幕触发条件定死为 `attempt_result.is_major is True`（与现行突破幕同一条件、同一两出口）；result_ref 只取 attempt 返回中恒存在的键（§5.4）；方案 §4c 的「渡过则 epic 昭告」已在结算内既存，仪式只引用该事实、**不新增昭告**（防双发，§0.3-X5） |
| F6 | 二期 Spec §5/文末裁决称 ⑤.6 待回应常驻已上线；任务简报称其补列上限 2 条旧→新 | `DramaEngine.list_pending`（`core/npc_proactive.py:702`）= `_load_drama_pending` 直通：读 KV `drama_pending:{char_id}` 列表、惰性滤过期、**保序返回**；事件由 `DramaEngine.evaluate` 以 `pending.append(ev)` 追加（:694），故返回序恒为 `created_at` 升序（**旧→新**）。`core/briefing.py` ⑤.6 段（`build_entry` 内，:420–448，`queue.sort` 之前）：按 list_pending 返回序正向迭代、`_queued_refs` 去重、至多补 2 条——待回应 ≥3 件且无一已入队时，补进的是**最旧 2 条**，最新一条被挤出；随后 `queue.sort(key=priority)` 为 Python 稳定排序（同 priority 保入队序），`highlight = queue[:3]`，queue 截断 8 条 | S-1 按总管已裁决口径修（§6）：⑤.6 改为对 `_pending_drama` **逆序迭代**（最新→最旧取至多 2 条未入队项）；`list_pending` 本体、sort、截断、highlight 口径一律不动 |
| F7 | 二期 Spec §10 称现行 mobile 上限 js ≤1892 行 / css ≤28800B | 本 Spec 定稿时在基线 `76310b4` 实测：`web/mobile.js` = **1631 行**（`wc -l`），距上限余 **261 行**（净增口径同余：1631−1172=459 / 720）；`web/mobile.css` = **27395B**，距上限余 **1405B**；预算断言在 `tests/test_mobile_web.py::test_mobile_redesign_budgets` 与 `tests/test_game_feel_frontend_contract.py::test_mobile_budgets_game_feel_phase1` 两处（数值与二期 §10 一致） | 本轮移动端新增估算 +18 行 / +0B（§8 明细），余量充足，**不申请豁免**，上限维持二期 §10 不变 |
| F8 | 方案 §4c 得宝幕称「词缀逐条亮出（装备 affixes 已有数据）」 | `TreasureEngine.dig` 的返回 `equipment` dict 是全仓最完整的获得物摘要：`{uid, name, kind, tier, tierName, slot, stats, affixes:[{name,desc}], lore}`（四原型 outcome 同形状）；服务端 `/挖宝` 分发（`server/world.py:2181`）已把 `equipment/pill/stone_gain` 等透出到响应。相对地，`/做` 自由言行挖宝路（`resolve_free_action`）的返回**不透 equipment**、其法宝奖励（太虚流云履）恒 tier2，且属 AI DM 裁决路径 | 得宝 result_ref 直接以 dig 的 equipment dict 为对账源（§3.4）；自由言行路不挂并记为已知缺口（§3.1 第 10 条） |

### 0.3 方案/任务边界冲突记账（逐条处置口径）

- **X1 · 主线章节类型扩充（宗门章接议政）不做**：方案 §7 第三期字面含此项，任务边界明确将其列入「预期不做」（属主线规则变更）。处置：以任务边界为准，入 Out of Scope（§11 第 1 条）；本轮对 `core/fate_thread.py` 零改动。
- **X2 · 得宝来源按实测收敛**：方案 §4c 的三来源与现状不符（F1），处置见 §3.1 全表——挂点以「有实体、有 uid、已入包」的真实落账点为准；谓词写成通用纯函数，被排除路径未来若长出高阶实体落账，按同型挂点补挂即可，不改门槛口径。
- **X3 · 得宝不自动串认主**：方案 §4c 表格行「若达器灵门槛，接器灵认主幕」与 awaken 的已穿戴门禁冲突（F2b）。处置：得宝幕 aftermath 只作预告；认主幕只认 awaken 的 changed 信号。两幕关系是「预告—兑现」而非连演。
- **X4 · 器灵台词零 AI**：方案 §4c 允许器灵第一句走 AI；本轮任务铁律为「零新增 AI 调用」（映射 C4）。处置：以铁律为准，台词走 `_local_line` 本地路径（性格台词池），验收 TR/SP 组含无 Key 同结果断言。方案该句留待未来轮次另议，本轮不预埋 AI 通道。
- **X5 · 天劫昭告不新增**：方案 §4c 称渡过天劫「全服频道 epic 昭告」——实测昭告已在 `attempt_breakthrough` 结算内发出（F5）。处置：仪式 aftermath 只引用已发事实（如成功且 tier≥2 时述「雷音已传四方」），仪式层不发任何频道帖，防双发。
- **X6 · 一期 §4.3 记账被本轮取代**：一期把天劫并入突破幕 beats 是当期边界下的记账；方案 §7 第三期明列「天劫独立幕补齐」，本轮独立成幕即取代该记账。处置：突破幕 builder 与 beats **一字不改**（其 prelude 的劫云句保留）；天劫幕 prelude 用新 tier 分档模板（§5.4），不与突破幕 prelude 逐字重复——两幕连演时的文案分工为「天劫幕演劫、突破幕演果」。
- **X7 · 双幕与「ceremony 单字段」的关系**：既有结构是响应单 `ceremony` 字段。处置（只增不改）：保留单字段语义为「第一幕」，新增只增键 `ceremony_next` 承载第二幕（§5.2）。被否决案：把两幕 beats 拼进一个 ceremony——per-kind 自动略过与 result_ref 单源对账都会被破坏，且 kind 枚举将出现混合值，污染 F4 的通用渲染契约。
- **X8 · 新图不做**：任务边界定死本轮零新图。三幕配图只用已上线 139 张图库资产键：得宝/器灵取 `artifacts/*` 器型键（经 `artifact_key_for_item`/`artifact_key_for` 解析，必在全集内）、天劫取 `portraits/*` 境界键（经 `player_portrait_key`，二期已补满 20 组合，合体以上不再借图）。资产键缺失/解析失败时 beats 的 `asset_key=null` 合法（前端既有口径：无图不渲染图位）。

---

## §1 · Problem

一期做了突破幕（含命格三选一）与死亡/转世合并幕，二期补齐了主线、戏剧与图库 139 张；但方案 §4c 的六幕仪式仍缺三幕：玩家掘出天品法宝、唤醒器灵、渡过大境界天劫时，看到的仍是结算行——图库里 20 张法宝器型图、高境界立绘在最高潮的时刻无处出场。同时，二期 ⑤.6 待回应常驻有一个已被复审钉住的边角：待回应戏剧 ≥3 件时，刷新版 entry 会漏掉最新一条——玩家最晚收到的那件「找上门的事」反而看不见。本轮在**不新增任何结算、数值、状态机**的前提下补齐三幕（全部是既有落账的只读呈现），并把 ⑤.6 的补列方向修对。

**真正需求条目（收敛结论，实现与验收的唯一依据）：**

- RQ-1（仪式全集）：六幕 kind 定格为方案 §4c 全集 `{breakthrough, tribulation, loot, spirit, death, rebirth}`；本轮新增 tribulation/loot/spirit 三幕的 builder 与挂点，既有三幕的 builder 与 beats 一字不改（突破幕的**呈现顺位**变化见 RQ-4）。
- RQ-2（得宝）：得宝幕只挂「高阶法宝/图鉴级收获」的真实入包点，门槛谓词与挂点按 §3 定死；单响应至多一幕；result_ref 与获得物逐项对账（C1）。
- RQ-3（器灵）：认主幕只认 `awaken` 的 `changed=True` 一次信号，挂服务端 `/器灵` 唤分支；重复唤、失败唤不演；台词本地模板（C3）。
- RQ-4（天劫）：大境界结算同源拆两幕——`ceremony`=天劫幕、`ceremony_next`=突破幕，致死时无第二幕；命格待选在拆分下的可达性与跳过等价按 §5.3 逐条可验（C2）。
- RQ-5（铁律映射）：方案 C1–C4 逐条落成验收——先结算后演出、ceremony 只读不落库、可跳过、同类自动略过（per-kind localStorage 既有机制扩名单）、零新增 AI、零锁内耗时增长、result_ref 逐项对账、跳过与看完最终状态逐字段相同。映射总表见 §2.3。
- RQ-6（S 组修复）：⑤.6 改最新优先迭代（S-1）+ `_queued_refs` 补登（S-2）+ 注释口径对齐（S-4），并补 ≥3 pending 的 cap/排序断言（复审 S-3 在本批的落点）；`list_pending` 与 queue 既有口径零变更。
- RQ-7（预算）：移动端在本轮估算内施工（js +18 行 / css +0B），现行上限（js ≤1892 行、css ≤28800B，二期 §10）不申请变更；桌面端只许增量追加，不许重构既有渲染函数（沿一、二期口径）。

---

## §2 · 仪式总契约增补（沿一期 §4.1，只增不改）

### 2.1 六幕清单核对（逐幕做/不做与理由）

| 幕（kind） | 状态 | 本轮处置与理由 |
|---|---|---|
| 突破 `breakthrough` | 一期已交付（builder + 两出口 + 命格三选一） | **不改 builder 与 beats**；仅呈现顺位由第一幕变第二幕（移入 `ceremony_next`，§5.2）——理由：天劫是同一次结算的前段，先劫后果是方案 §4c 的叙事序 |
| 死亡 `death` | 一期已交付（dead_payload 挂点） | 不动。渡劫致死的死亡幕仍走此路（登录后 dead_payload），不在突破响应里叠演（沿一期 §4.2 致死口径） |
| 转世 `rebirth` | 一期已交付（reincarnate 挂点） | 不动 |
| 得宝 `loot` | **本轮做** | §3。门槛与挂点按实测收敛（F1） |
| 器灵认主 `spirit` | **本轮做** | §4。挂 awaken 既有结算点（F2） |
| 天劫 `tribulation` | **本轮做（独立成幕）** | §5。方案 §7 第三期明列；与突破同源拆幕（F5） |
| ——（非仪式）主线章节类型扩充（宗门章接议政） | 方案 §7 第三期字面项 | **不做**：属主线规则变更，任务边界明列不做清单（X1），入 §11 |
| ——（非仪式）新图生成 | — | **不做**：三幕配图只用已上线 139 张资产键（X8） |

### 2.2 总契约增补（在一期 §4.1 之上只增四条）

1. **kind 枚举定格六值**：`breakthrough|tribulation|loot|spirit|death|rebirth`。builder 仍置 `core/ceremony.py`、仍为纯读拼装（已结算数据 + 本地模板）、仍不落库、仍 `skippable: true`、beats 仍三段 `{stage: prelude|reveal|aftermath, text, asset_key?, choices?}`。
2. **新三幕 beats 的 choices 恒为 null**（F4）：命格候选是全仓唯一合法 choices 形状（双端按钮硬发 `/命格`）；得宝/器灵/天劫无任何仪式内落账选择，不得借用该通道。
3. **双幕键 `ceremony_next`**：响应只增一键，值同为 ceremony 结构或 null；仅突破两出口使用（§5.2）。其余挂点响应不带此键（缺失即无第二幕，前端按缺失处理）。
4. **自动略过名单扩容**：`ceremony_skip_<kind>` 机制不变（只存前端 localStorage、双端同键、命盘/ops 提供取消入口）；双端硬编码名单由 3 kind 扩为 6 kind（§7.1），新 kind 的偏好键自动成立（键名规则既有）。

### 2.3 铁律 → 验收映射（C1–C4 与 S 组总表，详目在 §9）

| 铁律（方案/一期口径） | 落点条目 |
|---|---|
| C1 result_ref 与落账逐项对账 | LT-02（得宝）、SP-02（器灵）、TR-02（天劫） |
| C2 跳过与看完最终状态逐字段相同 | LT-04、SP-04、TR-05（双幕四组合）、TR-06（自动略过独立性） |
| C3 无 Key/断网本地模板兜底、无空白幕 | LT-05、SP-03、TR-07 |
| C4 零新增 AI 调用、零锁内耗时增长 | LT-06、SP-06、TR-08（静态检索 + 耗时同量级 + 结算本体零 diff） |
| 先结算后演出（仪式只读、拼装在既有 save 之后/之外） | §3.3/§4.2/§5.2 挂点次序写死 + LT-01/SP-01/TR-01 的构造断言 |
| 同类看过可设自动略过 | FE-01（名单扩容双端一致） |
| S-1 补列最新优先、刷新版必含最新待回应 | BR-01、BR-02 |
| S-2 补列项 id 加入 `_queued_refs` | BR-03 |
| S-4 ⑤.6 注释与新口径对齐 | BR-04 |
| 复审 S-3 落点（≥3 pending 的 cap/排序断言） | BR-01、BR-02（即 S-1 的测试面，不另立条目） |

---

## §3 · 件一：得宝幕（kind=loot）

### 3.1 候选落账点全表（实测逐条；「装备入包的全部路径」核查结论）

| # | 路径（落账点） | 落账形态与品阶事实 | 处置 |
|---|---|---|---|
| 1 | 藏宝图开匣 `TreasureEngine.dig`（`core/treasure_system.py:379`），服务端出口 `server/world.py:2181` `/挖宝` | 四原型 outcome 均可产装备实体并以 `equipment` dict 透出（F8）：解谜成功 equip tier = 图 tier 钳 [2,5]；守护战缴获 = 图 tier；涉险残损 = 图 tier−1；地渊遗迹 = RELIC「纯阳离火印」tier 恒 3。图 tier 本身可达 5（仙档图，二期 `maps/map-celestial`） | **挂（H-L1）**：`/挖宝` 分发 return 只增 `ceremony`（条件见 §3.2/§3.3） |
| 2 | 盲匣捡漏（`server/world.py` `/捡漏` 分发内联，约:4029） | 当场构造实体入包：RELIC tier4「太古遗迹真仙古卷」（15%）/ EQUIP tier3「古修断纹玄阴剑」（30%）/ 丹 tier2 / 材料 tier1；入包前已查 bag 未满、入包后已 save，响应带 `loot` 名 | **挂（H-L2）**：该分发 return 只增 `ceremony`（实际只有 tier4 relic 一档可触发，见 §3.2） |
| 3 | 锁妖古窟 `DungeonEngine.retreat`（`core/dungeon.py:580`） | stash 只含灵石 + 灵草/丹药**名**（战斗掉落表写死：凝血草/朱果/涅槃芝、聚气丹/筑基丹/九转金丹），入包走 `ItemFactory.from_legacy_name` 只产 herb/pill/material——**结构上永无 equip/relic** | 不挂（无可演之物；谓词即使挂上也恒不触发，属死代码） |
| 4 | 秘境 `SecretRealmEngine.step`（`core/secret_realm.py:233`） | 只产修为/灵石/功德，零物品落账 | 不挂（无获得物） |
| 5 | 大荒探险 `AdventureEngine.explore`（`core/adventure.py:242`，出口 `server/world.py:2573`） | equip 掉落走目录名 → `from_legacy_name`；池内高档三件目录 id 均 `_03`、tier 恒 ≤3，永不达门槛 | 不挂（门槛下无样本；未来扩池至天品时按 H-L1 同型补挂，谓词不改） |
| 6 | 炼器 `alchemy.craft`（`core/alchemy.py:153`，出口 `/炼丹`/`/炼器` 分发:2610） | 成功产物以目录名**字符串** append `inventory`，无实体、无 uid、无 affixes——result_ref 无对账锚；且炼器是玩家自选配方的定向制作，产物开炉前已知，无「揭晓」可言 | 不挂（双理由：无锚 + 非收获语义） |
| 7 | 天工造化 `core/forge.py` + `/悟器` 分发（:2620） | 产出是**配方**（`learn_recipe`），不是物品入包 | 不挂（非落账点） |
| 8 | 交易类：寄售成交（`core/market.py` buyer 入包:916）、专柜买卖/赠礼（`core/trade.py`）、典当赎回（`core/pawn.py`） | 既有实体易主（花钱买入/赎回自物/玩家与 NPC 间转移），非「得宝」语义；买入高阶法宝演得宝幕会把消费演成天降横财 | 不挂（语义不符；本轮不扩） |
| 9 | 世界内联小落账：仙鹤衔回/领取（material/map）、灵泉（pill）、草园（material）等 `server/world.py` 内联分发 | kind 恒为 material/pill/map，永不达谓词 | 不挂 |
| 10 | 自由言行挖宝 `TreasureEngine.resolve_free_action`（`core/treasure_system.py:717`，`/做` 路由） | AI DM 裁决路径；返回不透 `equipment`；其法宝奖励恒 tier2 | 不挂（已知缺口：该路径若未来奖励升格，须先透 equipment 字段再回主策岗议挂点） |

图库轮（gallery）的关系：图鉴点亮走 `gallery.unlock*` 的派生/事件双通道，与单次落账不在同一时点（多在 status 拼装时扫），**不作为得宝触发源**（理由见 §3.2 裁决 2）；得宝幕的图（器型图）取自 `artifact_key_for*` 解析，与点亮状态无关。

### 3.2 门槛定死（K1）与裁决理由

谓词（置 `core/ceremony.py`，纯函数，建议名 `loot_ceremony_candidate(kind, tier) -> bool`）：

```
(kind == "equip" and tier >= 4) or (kind == "relic" and tier >= 3)
```

- **equip 线取 tier≥4（天品/仙品）**：与器灵 `SPIRIT_MIN_TIER=4` 同一品阶线——得宝幕 aftermath 对 tier≥4 说「灵性已萌」是真话（穿戴后即可唤灵），两幕口径互锁；tier≤3 的地品及以下在探险/开匣中属常见收获，逐件演幕必成打扰（方案 §9 口径 8 的节制原则）。
- **「图鉴点亮」口径否决**（任务简报给的备选）：法宝图键按**器型**分（20 键），点亮与单件品阶无关——tier1 的新器型照样点亮、tier5 的已有点亮器型不再点亮；以点亮为门槛会使仪式有无取决于收集进度而非收获分量，信号倒置。且落账点无人调用 derive（F8/§3.1 图库条），引它作触发还要在挂点新增一次图鉴扫描写，违 C4 的零新增耗时精神。**故门槛只认品阶。**
- **relic 线取 tier≥3**：全仓 relic 产出只有两处（开匣地渊原型的「纯阳离火印」tier 恒 3、盲匣「太古遗迹真仙古卷」tier4），kind 本身即「稀世重宝」语义；若按 tier≥4 一刀切，藏宝图最高风险原型的头奖将永不入幕，与「高阶/图鉴级收获才触发」的意图相悖。此例外只覆盖 relic 一个 kind，不扩散到 equip/pill/material。
- 频次自检（构造性）：dig 的 equip tier 由图 tier 决定，达线须古代档（tier4）以上宝图或 tier5 图的涉险残损（tier4）——属低频高光时刻；盲匣达线率 15%×单次 80 灵石的付费开匣，频次由其既有经济口径自然节制。仪式层不另加频控（沿一期「同一时刻只演一次、结算是幂等的」口径：一次落账至多一幕，§3.3）。

### 3.3 挂点与拼装次序（先结算后演出，写死）

- **H-L1（/挖宝）**：`server/world.py` `/dig`、`/挖宝` 分发内，在既有次序（dig → 线索链 `on_chest_opened` 钩子 → `res.get("success")` 时 `CharacterRepository.save`）**之后**、组装 return dict 时：若 `res.get("success")` 且 `res.get("equipment")` 满足谓词，以该 equipment dict 调 `build_loot_ceremony(character, res["equipment"], source="treasure_dig")`，结果只增为 return 的 `ceremony` 键；不满足或拼装异常 → `ceremony: None`（沿既有 try/except 降级惯例，拼装失败不炸主流程）。return 其余键一字不改。
- **H-L2（/捡漏）**：同分发内，`char.add_item_entity(loot)` 与 `CharacterRepository.save(char)` **之后**、return 组装时：以 loot 实体属性调同一 builder（`source="blind_box"`，equip_info 由实体字段组装，形状与 §3.4 的归一入参一致）；不达谓词（tier3 剑/丹/材三档）→ `ceremony: None`。
- 单响应至多一幕是构造性成立的：dig 返回的 equipment 恒为单个 dict、盲匣恒为单个实体，不存在多件达线争一幕的问题，无需仲裁规则。
- builder 为纯读：入参 char 只读（取 gender/地点等呈现变量时亦只读）、equip_info 只读；不调 gallery unlock、不写任何仓储。

### 3.4 builder 契约（`build_loot_ceremony`）

入参归一形状 `equip_info = {uid, name, kind, tier, tier_name, slot, affixes: [{name, desc}], lore}`（dig 的 equipment dict 原样即此形状；盲匣路由实体字段组装同形状，`affixes` 取实体 affixes、`lore` 取 `lineage_lore`）。

beats 定稿：
- **prelude「异象」**：本地模板按 kind 分族（equip 3 条 / relic 2 条，变量只取器型中文与地点），确定性选句（`zlib.crc32(uid) % len`，沿一期评语/突破的稳定哈希先例）；`asset_key = artifact_key_for(name, slot=slot)`（解析失败/不在全集时为 null）。
- **reveal「揭晓」**：法宝图（同一 asset_key）+ 一行定稿式文本：`{name}` + affixes 逐条亮出（每词缀一行 `{name}：{desc}`，无词缀时只一行品阶句）；relic 无 affixes 时以 lore 一句代之（lore 为空则省略）。
- **aftermath「余韵」**：入包事实一句（「已入纳戒」）；equip 且 tier≥4 时追加器灵预告一句（定稿含 `/器灵 唤` 指引与「须先穿戴」明示，口径与 F2b 一致，不承诺自动认主）；relic 时追加一句图鉴/重宝口径文案（只述「稀世重宝」事实，不承诺点亮时点）。

result_ref 定稿：`{uid, name, kind, tier, tier_name, slot, source, affixes_text}`（`affixes_text` 为词缀名顿号拼接串、无词缀为 ""——取字符串而非数组的理由见 §7.1：双端既有 result_ref 平铺渲染对数组呈现不佳，不为此改前端）——与 dig 的 equipment dict（H-L1）或盲匣实体（H-L2）逐项可对账，且 uid 必须能在落账后 `character.items` 中按 uid 查到该实体（C1 的入包锚断言，LT-02）。

---

## §4 · 件二：器灵认主幕（kind=spirit）

### 4.1 结算点核查（认主发生的确切位置）

认主 = 唤灵首次成功，全仓唯一结算函数：`core/artifact_spirit.py` 的 `awaken(char, item_name, now=None)`（:360，经 `ArtifactSpiritEngine.awaken` 门面）。事实链：门禁（assert_alive/assert_idle）→ 对象须已穿戴（`find_equipped`）且 `_is_equip` 且 tier≥`SPIRIT_MIN_TIER=4` → 已有 spirit 时返回 `{success: True, changed: False}`（不重置四维）→ 首次时构造 spirit dict（`{awakened, name（uid 哈希定名）, personality（uid 哈希定型）, growth: 0, mood: 60, …}`）写入 `item.custom_metadata["spirit"]`、记 chronicle「唤灵」、调 `gallery.unlock_from_character`，返回 `{success: True, changed: True, message}`。服务端出口唯一：`server/world.py:1650` `/器灵`、`/spirit` 分发的「唤」分支——`res.changed` 时 handler 调 `CharacterRepository.save(char)` 落盘（awaken 本体不落盘角色行，spirit 随 item 实体经角色行 save 落地）。`/温养`、`/灵语` 不是认主（阶段晋升/对话），本轮不挂（§11）。

### 4.2 挂点与 builder 契约

- **挂点（H-S1）**：`/器灵` 唤分支内，`res.get("changed")` 为真且既有 save 完成**之后**、return 组装时：以 `find_equipped(char, target_name)` 重取该器物（save 后对象同一性沿 handler 既有口径），调 `build_spirit_ceremony(char, item)`，结果只增为 return 的 `ceremony` 键；`changed` 为假（重复唤）或 `success` 为假 → 不带 ceremony（return 其余键一字不改，连 `ceremony: None` 都不加——该分支既有 return 无 ceremony 键，保持缺失即无幕的既有降级口径；H-L1/H-L2 的 dig/捡漏 return 同理以「只增」为准，键缺失与 null 前端等价处理，沿 F4 通用渲染的缺失不渲染惯例）。拼装异常 → 无 ceremony、主流程不炸。
- **builder（`build_spirit_ceremony(char, item)`）**：纯读 `get_spirit(item)` 与 `public_spirit_dict(item)`（后者已含法宝图 `img` 与阶段/性格中文，是命盘下发的同一事实源）。beats 定稿：
- prelude：法宝图放大——`asset_key = artifact_key_for_item(item)`；文本为器物名+品阶一句（本地模板 2 条按 slot 分族，crc32(item.uid) 选句）。
- reveal：器灵名号与性格揭晓 + **器灵第一句话**：取 `_local_line(item, spirit, now)` 的本地路径产物（awaken 时点 mood=60、stage=萌生，其返回恒为 `PERSONALITIES[personality]["lines"]` 池内句，source 口径为 local）——零 AI（X4）；若该函数异常，降级为台词池以 crc32(uid) 直取一条，再失败则 reveal 只留名号行（不得空白幕，C3）。
- aftermath：器灵常驻指引一句（命盘法宝卡可见其头像与状态——`public_spirit_dict` 已在一期/图库轮下发至 `equipped[].spirit`，呈现本体不新增下发）+ 温养/灵语入口各一句。
- result_ref 定稿：`{item_uid, item_name, tier, spirit_name, personality, personality_cn, stage: 0, mood: 60}`——与落账后 `item.custom_metadata["spirit"]` 逐项对账（stage/mood/growth 三值为 awaken 写定的初值，SP-02）。

---

## §5 · 件三：天劫独立幕（kind=tribulation）

### 5.1 结算形态核查（触发条件据此定死）

`attempt_breakthrough`（F5）是大境界天劫的唯一裁决：`sub_tier<3` 的小阶无雷劫（返回 `is_major=False`，现状两出口均不演任何幕）；大境界必带雷劫段（成功 message 首行即「紫霄天劫」，失败四档全是雷劫反噬形态），返回 `is_major=True`。故天劫幕的触发条件与现行突破幕**完全同闸**：两出口在 `attempt_result.get("is_major")` 为真时拼装。心魔后继段（出口②）只是 attempt 的调用方式不同（带 `heart_mod`），返回形状同一，本协议同等适用。守卫失败返回（未圆满/门禁拦截）无 `is_major` 键 → 不演（沿现状）。

### 5.2 拆幕协议（K2：一次结算、两幕呈现、单字段结构的落法）

两出口（`World._breakthrough` 出口①、`World.handle` 心魔后继段出口②）的 return 改挂如下（其余键一字不改）：

```python
# is_major 为真时（try/except 降级惯例沿既有：任一拼装失败只缺该幕）
ceremony       = build_tribulation_ceremony(char, attempt_result)          # 第一幕：劫
ceremony_next  = None if attempt_result.get("is_fatal") \
                 else build_breakthrough_ceremony(char, attempt_result, fate_drawn=…)  # 第二幕：果
# is_major 为假/缺失时：ceremony 与 ceremony_next 均为 None（沿既有 _bt_ceremony=None 口径）
```

- **突破幕 builder 与 beats 一字不改**（含其 result_ref 与 MF-2 的 choices 口径），只是从 `ceremony` 移到 `ceremony_next`。`fate_drawn` 的计算口径沿既有（两出口各自的 `_pend_before` 对比，不动）。
- **致死时无第二幕**：`is_fatal`（即 `fail_tier=="DEATH"`）时 `ceremony_next=None`——此身已殁，突破幕的成败揭晓无从谈起；后续由登录 dead_payload 的死亡幕接续（沿一期致死口径）。天劫幕 aftermath 在致死时承担桥接文案（§5.4）。
- **呈现顺序（前端契约，§7.2）**：先演 `ceremony`；其被关闭（点略过）或被自动略过（`ceremony_skip_tribulation`）后，再以同一呈现函数演 `ceremony_next`（其自身受 `ceremony_skip_breakthrough` 独立判定）；`ceremony` 为 null 而 `ceremony_next` 非 null 时直接演后者（单边拼装失败的降级口径）。两幕都不存在/都被略过时无任何弹窗——与现状「无幕」态等价。
- 此协议下 `ceremony` 字段的**结构**不变（仍是单个 ceremony dict），变化的只是大境界突破时其 kind 内容（breakthrough → tribulation）与新增键 `ceremony_next`——按只增不改的边界记账于 §0.1 第四步与 F3，回归口径见 §9。

### 5.3 命格待选在拆幕下的可达性与跳过等价（写死）

1. **抽定点不动**：命格抽定仍在 attempt 成功分支尾部（`draw_fate_pending`），拆幕不碰 `core/breakthrough.py` 任何一行（TR-08 以 diff 断言）。
2. **choices 只在第二幕**：三选一候选仍只出现在突破幕 aftermath（`pending[0]` 一抽，MF-2 口径），天劫幕三段 beats 的 choices **恒 null**（§2.2 第 2 条）——玩家必须走完（或略过）劫幕才见到命格抉择，叙事序为「先渡劫、后定命格」，与一期「揭晓幕里三选一」的语义一致（突破幕即揭晓幕）。
3. **略过互不吞没**：略过/自动略过天劫幕只影响天劫幕呈现，不消耗、不隐藏突破幕；反之亦然（§7.2 的队列呈现逐幕独立判定 skip 键）。
4. **双略过仍可达**：两幕皆被自动略过时，待选抽原样留在角色行（`fate_pending`），命盘待选区与 `/命格` 命令可达性与一期逐字相同——C2 的根基（待选状态机）不因拆幕改变。
5. **跳过等价（C2）**：两幕均为纯前端呈现，关闭/略过不发任何写请求；四组合（看完两幕 / 只跳劫幕 / 只跳突破幕 / 全跳）下最终角色行逐字段相同（`chosen_at/drawn_at` 时间戳豁免沿一期 §4.2 口径）；在第二幕内以 `/命格 <key>` 选择与在命盘选择走同一 `apply_fate_choice`（一期唯一函数），TR-05/TR-06 逐项断言。

### 5.4 builder 契约（`build_tribulation_ceremony`）

纯读 attempt_result + char 只读字段 + 本地模板；与突破幕共用 `_FAIL_LINES` 时只许引用、不许改写其文案（突破幕 reveal 在用）。

beats 定稿：
- **prelude「劫兆」**：劫云预兆——新模板按**目标 tier 分三档**（tier≤2 初劫 / 3≤tier≤4 大劫 / tier≥5 天劫，各 1 条定稿、变量只取目标境界名），与突破幕 prelude 的 `_TRIBULATION_PRELUDES` 轮换句**不逐字重复**（X6 的分工：此幕演劫象本身）；`asset_key` = char **当前（劫前）tier** 的境界立绘键（`player_portrait_key(gender, char.realm.tier)`，与突破幕 prelude 用目标 tier 新立绘形成「劫前本相 → 劫后新身」的对照；拼装时点 char 已被 attempt 改为新 tier 者，以 `attempt_result` 反推劫前 tier = 新 tier−1（成功时）/ 现 tier（失败时 realm 未升），实现岗按此口径取键，取不到则 null）。
- **reveal「渡劫」**：三段递进合为一段 reveal 文本（以 `\n` 分行，沿死亡幕 prelude 多行先例；前端节奏由呈现层按行处理，后端只给结构，沿方案 §4c「每段一行一顿（前端节奏，后端只给结构）」）：① 劫雷行——按成败/ fail_tier 取定稿模板（成功 1 条、四档各 1 条，变量只取境界名与已结算数值）；② 心魔行——`DemonStateEngine.summary` 阶段>0 时取其魔念拼句（与突破幕 prelude 同源只读），无心魔数据时用定稿静默句（「劫雷之下，道心守一。」），不得编造心魔事实；③ 成败行——只述天劫本身的裁决结论（成功：「劫云为之让路」式 1 条；失败按 fail_tier 的天劫侧结论 1 条），境界/寿元等**果**的数字留给突破幕 result_ref，此行不重复报数（防两幕连演时数字双播）。
- **aftermath「劫后」**：成功且新 tier≥2 → 引用既有昭告事实一句（「雷音已传四方」口径，X5；tier<2 无昭告则用散云句）；非致死失败 → 按 fail_tier 的劫后一句（与 `_FAIL_LINES` 不逐字重复，新写 4 条短句）；致死 → 桥接句（定稿含「此身已殁，归府之仪将于再入轮回时续演」口径，指向 dead_payload 死亡幕，不在此幕内演回望）。

result_ref 定稿：`{success, is_major: true, is_fatal, fail_tier（成功时 null）, new_realm, target_tier, prob_pct, judge_source}`——全部直取 attempt 返回键（成功时 `new_realm` 为新境界名、失败时该键缺失则以 char 现境界名兜底且在对账时注明：attempt 失败返回无 new_realm 键，result_ref 的该字段口径为「结算后境界名」）；`roll` 只在成功返回中存在，不入 result_ref（避免成功/失败形状分叉）。

---

## §6 · 件四：二期复审 S-1/S-2/S-4 修复（core/briefing.py ⑤.6）

### 6.1 现状核查（实测，含返回序与相互作用）

- **返回序**：`DramaEngine.list_pending(player, now)`（`core/npc_proactive.py:702`）直通 `_load_drama_pending`（:363）：读 KV `drama_pending:{char_id}`、滤过期（保序）、返回列表本体；事件由 evaluate 以 `pending.append(ev)`（:694）尾插，故返回序恒为 created_at 升序（旧→新）。respond 按 id 查找、panel_text 按返回序逐条列出——两者都不依赖「新在前」的假设。
- **bug 形态**：`build_entry` ⑤.6 段（`core/briefing.py:420–448`，位于 ⑤.5 之后、`queue.sort` 之前）正向迭代该列表、`_added_pending` 上限 2：≥3 件待回应且无一已在 queue 时，入队的是最旧 2 件，**最新一件被挤出**；登录版 entry 若已含 ⑤.5 新建件（其必为最新）尚可，刷新版（`allow_proactive=False`，无 ⑤.5）必漏最新——与二期文末裁决「待回应戏剧常驻」的立意相悖（常驻的意义首先是最新那件不丢）。
- **sort 稳定性与 highlight 的相互作用**：⑤.6 之后 `queue.sort(key=lambda q: q["priority"])`（:449）是 Python 稳定排序——同 priority（drama 恒 2）内保入队序；drama 项之间在 queue 中的相对序 = 它们被 append 的顺序。`highlight = queue[:3]` 在 sort 与 8 条截断之后取，故同 priority 内越靠前越容易进 highlight。现行正向迭代使最旧的 drama 排在同级最前；改逆序后，最新 drama 在同级内最靠前——这正是 S-1 要的「刷新版必含最新」（在未触 8 条总截断时，最新 drama 必在 queue 内；同级排序亦对其有利）。

### 6.2 修复口径（总管已裁决，写入裁决记录 §12；三项同批）

- **S-1（迭代方向）**：⑤.6 的迭代改为对 `_pending_drama` **逆序**：`for _ev in reversed(_pending_drama):`，其余逻辑（`isinstance` 校验、`_queued_refs` 去重、`_added_pending >= 2` 上限、drama 项的拼装形状/target/options）**逐字不变**。效果：补列取「最新→最旧至多 2 条未入队项」；⑤.5 已新建入队者（必为最新）被 `_queued_refs` 去重跳过后，补列顺位取次新两件——登录版与刷新版口径一致。
- **S-2（一行防御）**：⑤.6 循环内每成功 append 一条补列项后，把其 id 加入 `_queued_refs`（`_queued_refs.add(str(_ev.get("id") or ""))`，与 append 同步一行）。现状 `_queued_refs` 只在循环前快照一次，若 `list_pending` 因任何原因返回重复 id（KV 脏数据/未来写入方变更），同 id 会被补列两次；补登后循环自身的去重闭环成立。纯防御，不改变正常路径行为。
- **S-4（注释对齐）**：⑤.6 段头注释改写为与新口径一致的措辞，须含三要素：常驻立意（沿二期裁决原文要点）、**最新优先（逆序取至多 2 条未入队项，S-1）**、去重含补列自登记（S-2）；不得再出现「按返回序补列」类与实现不符的表述（现行注释未明说顺序，属措辞缺位而非错误陈述，按「对齐」处理）。

### 6.3 不变口径（写死，防修复扩散）

- `DramaEngine.list_pending` 本体与 KV 形状一字不改；`/回应` 面板（panel_text）的列出顺序仍为旧→新（本轮不改其呈现序）。
- queue 的 priority 表、稳定 sort、8 条截断、`highlight = queue[:3]`、`rest_count` 口径全部不变。**保证范围明示**：S-1 保证的是补列机制不再丢最新项；在同轮 priority≤2 事项极多、queue 触 8 条总截断的极端场景下，drama 项仍可能被既有截断挤出——那属既有截断口径，不在本条修复范围（验收 BR-01/BR-02 以未触顶场景断言，并以一条触顶场景的负例注明此界）。
- 去重口径不变：去重键仍为 queue 各项的 `ref_id` 与 pending 事件 `id` 的字符串相等比较；⑤.5 与 ⑤.6 的关系（新建优先、补列只补未入队者）不变。
- 改动面只许 `core/briefing.py` ⑤.6 一段（含注释）；`core/npc_proactive.py` 零改动。

---

## §7 · 前端呈现契约（双端）

### 7.1 通用渲染核查结论与必改点（F4）

双端 ceremony 渲染器均按结构通用渲染，新三幕**不需要新增渲染分支**；必改点只有下列原地扩容（双端同口径）：

| 改点 | 桌面（web/workbench.js） | 移动（web/mobile.js） |
|---|---|---|
| kind 中文名表加 3 项：`tribulation: "天劫"`、`loot: "得宝"`、`spirit: "器灵认主"` | `CEREMONY_KIND_CN` 原地加 | `CEREMONY_CN_M` 原地加 |
| 标题图标：loot 用「💎」、spirit 用「🔮」、tribulation 沿默认「⚡」 | 图标三元原地补两项 | 无图标位，不改 |
| 自动略过取消名单扩为 6 kind | `ceremonySkipSectionHtml` 的 kinds 数组原地加 `tribulation/loot/spirit` | `renderCeremonySkipOpsM` 的数组原地加同三项 |
| 双幕队列呈现 | 新增（§7.2），无行数预算约束（仓内现状） | 新增（§7.2），计入 §8 估算 |

呈现细节沿既有：beats 的 `asset_key` 以 `/assets/<key>.webp` 拼图（得宝/器灵的 artifacts 键、天劫的 portraits 键都走同一拼装，键为不带扩展名的相对键，与既有 builder 口径一致）；result_ref 平铺行沿既有渲染（三幕的 result_ref 均为标量/短列表，affix_names 列表在桌面会被既有过滤（非 object 才显示）以数组 toString 呈现、移动同理——可接受，不为它新增渲染分支；如实现岗认为列表呈现不佳，只许在 builder 侧把 affix_names 拼为字符串字段 `affixes_text` 替代，**不得改前端过滤逻辑**——此为 builder 侧二选一口径，定稿取后者：result_ref 用 `affixes_text`（顿号拼接，无词缀为 ""），不带 affix_names 数组）。

### 7.2 双幕队列呈现（新逻辑，双端同契约）

- 响应处理入口（双端既有 `maybeShowCeremony*` 的调用点，含 /action 与登录/转世 payload 两路）改为：先把 `data.ceremony_next` 暂存（建议 `state.ceremonyNext`），再呈现 `data.ceremony`；顺序与单边缺失的降级按 §5.2 写死口径。
- 当前幕关闭时（点「略过」按钮的关闭路径——桌面 ceremony 弹窗的关闭须走一个 ceremony 专用关闭函数，不得劫持通用 `closeJadeDialog` 的其他调用方；移动 `data-ceremony-close` 路径同理）若暂存有下一幕，立即以同一呈现函数演下一幕（其 skip 键独立判定：已被自动略过则直接丢弃暂存、不弹窗）；当前幕在呈现入口即被自动略过时，同理顺延判定下一幕。
- 命格 choices 的点击（`data-fate-choice`）发生在第二幕内，其既有行为（一期：发 `/命格` 命令）不变；点选后是否关幕沿既有双端现状（移动点选即关 overlay、桌面经命令回执刷新），不因队列逻辑改变。第二幕关闭后队列清空（无第三幕，本轮协议最多两幕）。
- 非突破响应永不带 `ceremony_next`，队列逻辑对既有三幕与得宝/器灵单幕零影响（暂存恒空）。

---

## §8 · 移动端预算登记（沿二期 §10 体例；本轮不申请豁免）

实测（本 Spec 定稿时，基线 `76310b4`）：`web/mobile.js` = **1631 行**，现行上限 1892 行（文件口径）/ 净增上限 720（1631−1172=459），**两口径余量同为 261 行**；`web/mobile.css` = **27395B**，现行上限 28800B，**余量 1405B**；`web/mobile.html` 本轮零改动。

本轮移动端新增面估算（前端岗按此上限施工）：

| 新增面 | mobile.js 估算 | mobile.css 估算 | 说明 |
|---|---|---|---|
| kind 文案表 +3 项、略过名单 +3 kind | +0 行（原地改既有行） | +0B | §7.1 |
| 双幕队列呈现（暂存 + 关闭顺延 + skip 独立判定） | +14 行 | +0B（全复用 `gf-card`/`gf-overlay` 既有类） | §7.2 |
| 响应接线（两处调用点改传/暂存 ceremony_next） | +4 行 | +0B | 既有 `maybeShowCeremonyM` 调用点 |
| **合计** | **+18 行** | **+0B** | |

**结论：不需要豁免。** 估算 +18 行 « 余量 261 行、CSS 零新增 « 余量 1405B；现行上限（js ≤1892 行、css ≤28800B）维持二期 §10 不变，预算断言（`tests/test_mobile_web.py`、`tests/test_game_feel_frontend_contract.py` 两处）**不修订**。施工硬线（防估算漂移）：交付时 mobile.js 须 ≤1660 行（估算 +18 + 机动 11），mobile.css 须 ≤27455B（机动 +60B）；若实现中发现必须突破此硬线（例如队列呈现需要新样式类），**停工回主策岗补豁免申请，未批不得动**（沿二期 §10 体例）。桌面端 workbench.js/css 无行数/字节预算约束（仓内现状），只许增量追加、不许重构既有渲染函数。

---

## §9 · Acceptance（逐条编号；每条标注铁律映射）

本 Spec 共 **32 条**（LT 7 + SP 6 + TR 8 + BR 5 + FE 3 + RG 3）。

### 9.1 得宝幕（§3）

- **LT-01（先结算后演出）** 触发构造：藏宝图开匣构造达线两例——(a) tier4 图解谜成功得 equip tier4、(b) 地渊遗迹 outcome 得 relic「纯阳离火印」——`/挖宝` 响应均含 `ceremony.kind == "loot"`；且 ceremony 存在时，从 DB 重读的角色行 `items` 已含 result_ref.uid 对应实体（落账先于拼装的锚断言）。盲匣以播种 roll<0.15 构造 tier4 relic 一例，同断言。
- **LT-02（C1）** result_ref 对账：LT-01 各例的 result_ref 与 dig 返回 `equipment` dict 逐项相等（uid/name/kind/tier/tier_name↔tierName 值、slot、source），`affixes_text` 与 equipment.affixes 的 name 序列一致；盲匣例与 loot 实体属性逐项相等。
- **LT-03（门槛负例集）** 不触发：dig 得 equip tier3（涉险残损/低阶图）一例、盲匣 tier3 剑与 tier2 丹各一例，响应均无 loot 幕（ceremony 为 None/缺失）；谓词函数级真值表见 LT-07；探险高档三件与炼器产物以 handler 级各构造一例断言无幕（§3.1 第 5/6 条的销账）。
- **LT-04（C2）** 跳过等价：同一播种的达线开匣两路对照（看完 / 点略过），最终角色行（含 items/灵石/修为）逐字段相同；略过路径零写请求（网络层断言，沿一期 P3-03 口径）。
- **LT-05（C3）** 无 Key/断网环境：两挂点各构造一例，beats 三段齐全、text 均非空、reveal 含获得物名；asset_key 或为 `GALLERY_ASSET_KEYS` 内键或为 null，无空白幕、无报错。
- **LT-06（C4）** 静态检索证明 `core/ceremony.py` 本轮新增代码不引用 AI 网关/`WorldDirector`/`_chat_json`；带 ceremony 的 `/挖宝` 响应耗时与基线同法中位数劣化 <20%（沿一期 P3-06 测法）；builder 直调拼装耗时毫秒级（单测内计时断言 <50ms）。
- **LT-07（谓词与单幕性）** `loot_ceremony_candidate` 真值表全组合：equip tier 3/4/5 → False/True/True；relic tier 2/3/4 → False/True/True；pill/material/map/herb 任意 tier → False。连续两次达线开匣各演一幕、result_ref 互不串扰。

### 9.2 器灵认主幕（§4）

- **SP-01（触发信号）** 首唤（已穿戴 tier≥4、未唤灵）响应含 `ceremony.kind == "spirit"`；重复唤（changed=False）无幕；未穿戴/tier<4/器物不存在三类失败唤无幕；`/温养`、`/灵语` 响应无 spirit 幕（负例）。
- **SP-02（C1）** result_ref 对账：与落账后 `item.custom_metadata["spirit"]` 逐项相等（spirit_name/personality 对应 name/personality、stage==0、mood==60），item_uid/item_name/tier 与器物实体一致。
- **SP-03（C3）** 台词本地性：无 Key 环境 reveal 的器灵台词 ∈ `PERSONALITIES[personality]["lines"]`；有 Key 环境重跑台词口径不变（恒本地池，X4）；beats 三段非空。
- **SP-04（C2）** 跳过等价：看完/略过两路，spirit dict 与角色行逐字段相同（认主落账在 awaken 本体，仪式零写）。
- **SP-05（不回归）** 器灵既有行为零漂移：`panel_text`、`public_spirit_dict`、`ArtifactSpiritEngine.power_bonus` 输出与基线一致；器灵相关既有套件全绿（基线内既有失败除外）。
- **SP-06（C4）** 静态检索证明 spirit 挂点与 builder 无 AI 调用（awaken 本体既有的 chronicle/gallery unlock 不算新增）；`/器灵 唤` 带幕响应耗时与基线同量级（中位数劣化 <20%）。

### 9.3 天劫独立幕（§5）

- **TR-01（触发矩阵）** 两出口各构造：大境界成功一例、致死一例（handle 级）均有天劫幕；小阶突破两键皆 None；四档 fail_tier 在 builder 级逐档构造（attempt 结果注入），beats/result_ref 形状合 §5.4。
- **TR-02（C1）** result_ref 与 attempt 返回逐项对账（成功/失败各一例）：success/is_fatal/fail_tier（成功 null）/prob_pct/judge_source 直取一致，new_realm 口径合 §5.4 注明。
- **TR-03（拆幕协议）** 非致死大境界：`ceremony.kind == "tribulation"` 且 `ceremony_next.kind == "breakthrough"`；致死：`ceremony_next is None`；一期 handle 级 death/rebirth 断言（P3-02）复跑不受影响。
- **TR-04（命格可达）** 成功且 fate_drawn 时：`ceremony_next` 的 aftermath choices == `fate_pending[0].candidates`（与一期 MF-2 口径一致），且其 result_ref 的 fate_pending_count/newer_count 与角色行一致；天劫幕三段 beats 的 choices 全为 null。
- **TR-05（C2）** 跳过等价四组合：同播种角色四路（看完两幕/只跳劫幕/只跳突破幕/全跳）最终角色行逐字段相同（chosen_at/drawn_at 豁免，沿一期口径）；第二幕内 `/命格 <key>` 选择与命盘选择同 key 的最终状态一致（一期 P3-03 在拆幕后复跑）。
- **TR-06（自动略过独立性）** 前端三例：只设 `ceremony_skip_tribulation` → 只演突破幕；只设 `ceremony_skip_breakthrough` → 只演天劫幕；双设 → 无弹窗且待选仍可经 `/命格` 择定（角色行断言）。
- **TR-07（C3）** 无 Key/断网：成功与致死两例的天劫幕 beats 三段齐全非空、心魔行在无心魔数据时为定稿静默句、无报错。
- **TR-08（C4）** `core/breakthrough.py` 本轮 diff 为空（git diff 断言——结算本体一字不改）；双幕拼装静态无 AI/无导演调用；两出口带双幕的响应耗时与基线同法中位数劣化 <20%。

### 9.4 S 组修复（§6）

- **BR-01（S-1 本体，含复审 S-3 的 cap 断言面）** 构造 3 件待回应（created_at 递增，记 id 为旧/中/新），以 `allow_proactive=False` 调 `build_entry`：queue 中 drama 项的 ref_id 恰为 {新, 中}（不含旧）、补列数 ≤2；构造 4 件时恰为 {最新, 次新}。
- **BR-02（S-1 排序面，含 S-3 的排序断言面）** BR-01 场景且无其他事项时：最新 drama 项在 `highlight` 内；两件 drama 在 queue 中的相对序为新→旧。触顶负例：构造 ≥8 条 priority≤2 事项时，只断言截断行为与既有口径一致（§6.3 的保证界），不作必含断言——此界须在测试注释中明示。
- **BR-03（S-2）** `list_pending` 返回含重复 id 的列表（[x, x, y]，以 KV 直写或 monkeypatch 构造）时，queue 中 id=x 的 drama 项只出现一次（补列自登记生效）；正常列表下行为与 BR-01 一致（防御不改正常路径）。
- **BR-04（S-4 + 改动面）** ⑤.6 段头注释含「最新优先」口径三要素（人读销账，评审岗核对）；本件 git diff 只含 `core/briefing.py` ⑤.6 段（含注释），`core/npc_proactive.py` 零改动（diff 范围断言）。
- **BR-05（不回归）** 二期 DR-08（待回应常驻）用例复跑全绿；`list_pending` 返回序断言仍为旧→新（3 件构造）；`/回应` panel_text 列序不变；登录路径共存例：⑤.5 新建 1 件（最新）入队后，⑤.6 补列取次新两件、新建件不重复入队。

### 9.5 前端呈现（§7/§8）

- **FE-01** 前端契约断言：双端源文件均含 tribulation/loot/spirit 三 kind 的中文名与六 kind 自动略过名单；桌面图标映射含 loot/spirit 两项。
- **FE-02** 双幕队列四情形（双看/跳劫/跳突破/双自动略过）双端行为与 §7.2 一致（以 §13 截图 + 前端契约测试销账）；非突破响应的呈现与基线逐字一致（暂存恒空的负例）。
- **FE-03（预算硬线）** `tests/test_mobile_web.py` 与 `tests/test_game_feel_frontend_contract.py` 的预算断言（未修订版）全绿，且交付实测 mobile.js ≤1660 行、mobile.css ≤27455B（§8 本轮硬线）。

### 9.6 回归口径（写死）

- **RG-01（基线获取方法）** 基线 = main `76310b4`（v0.3.9-gray.16）。实现开工前在基线提交上以**新鲜 DB** 全量实跑一次 `pytest tests/ -q` 并留档，其失败集即本轮**操作基线**（获取方法沿二期 RG-01；二期交付时的已知失败名单以该次实跑复核为准，不凭记忆沿用）。
- **RG-02（红线）** 交付全量：**新增失败必须为 0**（交付失败集 ⊆ 操作基线失败集 ∪ 复跑可绿的已知 flaky）。本轮预期**零既有断言修订**（F3 已核：handle 级 ceremony.kind 无既有断言、builder 级断言不受拆幕影响）；实现中若发现必须修订既有断言，须逐条列出处与理由回主策岗裁决，不得自行放宽数值/安全类断言。
- **RG-03（定向套件）** 下列套件全绿（基线内既有失败除外并逐条注明）：`test_game_feel_phase1_backend.py`、`test_game_feel_phase1_rework*.py`、`test_game_feel_phase2_drama.py`、`test_game_feel_phase2_fate.py`、`test_game_feel_frontend_contract.py`、`test_mobile_web.py`、`test_login_latency_fix.py`，及器灵（artifact_spirit 相关）、藏宝（treasure 相关）、突破（breakthrough 相关）用例所在文件。

---

## §10 · 风险与兜底

| 风险 | 兜底（已写入设计何处） |
|---|---|
| 双幕协议被只读 `ceremony` 的旧消费者误读（CLI 无呈现层、第三方脚本） | CLI 本就无仪式呈现面，命格可达性由 `/命格` 与命盘承载（§5.3 第 4 条）；`ceremony_next` 缺失/多余对既有消费者均为只增键（沿仓内只增惯例，忽略不报错） |
| 天劫幕 prelude 的劫前 tier 反推出错（成功时 char 已升 tier） | §5.4 写死反推口径；取键失败时 asset_key=null 合法降级（LT-05/TR-07 以「全集内键或 null」验收，不把图当硬断言） |
| dig 的 equipment dict 与实体落账不一致（满包/溢出路） | dig 前置 `assert_bag_space` 拦截、钩子在线索链结算与 save 之后（§3.3）；LT-01 以 DB 重读按 uid 查实体兜底，查不到即不过 |
| 盲匣挂点在 `server/world.py` 内联分发，改动面易碰既有 return | H-L2 只增一键、拼装 try/except 降级（§4.2 同型口径适用于全部挂点）；LT-03 负例锁住其余三档行为 |
| S-1 修复被误扩为改 list_pending 返回序 | §6.3 写死不变口径 + BR-04 的 diff 范围断言 + BR-05 的返回序断言三重锁 |
| 两幕连演被玩家嫌长（方案 §9 口径 8 的节制问题） | 默认短版三段、per-kind 自动略过（TR-06）、天劫幕 reveal 不重复报数（§5.4）——频次与长度都已在设计内节制 |
| 前端队列呈现在桌面通用对话框上劫持其他弹窗关闭路径 | §7.2 写死 ceremony 专用关闭函数，不得改通用 `closeJadeDialog` 语义；FE-02 负例（非突破响应零影响） |

---

## §11 · Out of Scope（逐项点名，本轮不做、不顺手做）

1. 主线章节类型扩充（宗门章接议政结果）与一切主线/戏剧**规则**变更（X1）；`core/fate_thread.py` 本轮零改动。
2. 新图生成与资产键新增；图鉴分组/称号/点亮规则变更（X8）。三幕只消费既有 139 键。
3. 器灵的阶段晋升幕（通灵/化形）、沉睡/闹脾气/护主等事件幕；`/温养`、`/灵语` 的一切呈现改造（本轮只做认主一幕）。
4. 得宝幕向 §3.1 不挂路径的扩展：探险、炼器、天工、交易类、自由言行挖宝路；得宝谓词门槛的任何调整（tier 线/relic 例外均已定死）。
5. 二期复审其余建议项：S-3 中除「⑤.6 ≥3 pending 的 cap/排序断言」之外的部分（目标侧等未登记项）、以及历轮遗留名单（一期 §8 的 S-1～S-7、桌面命盘 `[object Object]` 观察项、影子 RELATION 留痕、place 类 closed 开关）——本轮一律不处理、不顺手修。
6. 仪式协议泛化：三幕以上队列、死亡→转世同响应连演、ceremony 落库/重演（沿一期「关掉即跳过、后果为零」口径）。
7. 器灵台词与三幕文案的 AI 润色通道（X4；未来轮次另议，本轮不预埋）。
8. 突破结算本体（`core/breakthrough.py`）、`attempt_breakthrough` 返回键、命格池/数值/待选状态机的任何改动（TR-08 以 diff 为空锁死）。

---

## §12 · 裁决记录

> 本节记本轮已定裁决与出处；正文与本节冲突时以本节为准（沿二期体例）。集成/评审阶段的回写只许追加于本节末尾，不改上方契约正文。

- **总管裁决（S-1 口径，本轮派工时已定）**：⑤.6 待回应补列改为**最新优先迭代**——补列时按最新→最旧取至多 2 条未入队项，使刷新版 entry 必含最新待回应项（保证界见 §6.3）；同时补 ≥3 pending 的 cap/排序断言（复审 S-3 的落点，即 BR-01/BR-02）。同批登记 S-2（补列项 id 加入 `_queued_refs`，一行防御性修复）与 S-4（⑤.6 注释措辞与新口径对齐）。落点：§6、BR-01～BR-05。
- **主策裁决 K1（得宝门槛）**：谓词 `(equip ∧ tier≥4) ∨ (relic ∧ tier≥3)`；「图鉴点亮」门槛否决（信号倒置 + 落账点无 derive 调用，§3.2）。挂点仅开匣（H-L1）与盲匣（H-L2）两处，其余候选路径以 §3.1 实测证据逐条不挂——方案 §4c「秘境/藏宝图/炼器」三来源口径按现状修正（X2/F1）。
- **主策裁决 K2（双幕协议）**：`ceremony`=天劫幕 + `ceremony_next`=突破幕（只增键）；致死无第二幕；beats 拼接案否决（X7）。突破幕 builder/beats 零改动，命格 choices 只留第二幕（§5.3）。
- **主策裁决 K3（器灵信号）**：认主唯一信号 = `awaken` 的 `changed=True`；得宝不自动串认主（X3）；台词零 AI 走本地台词池（X4，覆盖方案 §4c 的 AI 选项）。
- **主策裁决 K4（预算）**：本轮移动端估算 +18 行/+0B，余量充足（261 行/1405B），**不申请豁免**、现行上限与预算断言均不修订；另设本轮施工硬线（js ≤1660 行、css ≤27455B），超硬线须停工回主策岗（§8）。
- **主策记账 X5/X6**：天劫昭告不新增（结算内既存，仪式只引用）；一期 §4.3「天劫并入突破 beats」记账由本 Spec §5 取代，突破幕 prelude 劫云句保留、天劫幕用新分档模板避免逐字重复。

### 集成/评审回写（实现后回填，本轮留空）

- （待回填）

---

## §13 · 截图验收清单（双端，实现岗交付时随附；每张对应验收编号）

桌面（web/index.html + workbench.js）：
- **S-D1** 得宝幕三段（tier4 开匣样本：器型图 + 词缀逐条 + 器灵预告行）（LT-01、LT-05）
- **S-D2** 器灵认主幕（法宝图 + 名号性格 + 第一句话）（SP-01、SP-03）
- **S-D3** 天劫幕（劫兆/渡劫三行/劫后）与紧随的突破幕（命格三选一同屏于第二幕 aftermath）（TR-03、TR-04）
- **S-D4** 入局刷新版含 ≥3 件待回应中的最新一条（feed/入局 queue 实拍）（BR-01）

移动（web/mobile.html + mobile.js）：
- **S-M1** 得宝幕全屏卡（LT-01）
- **S-M2** 天劫→突破双幕连演两帧（跳过第一幕后第二幕自动呈上）（TR-03、FE-02）
- **S-M3** 器灵认主幕全屏卡（SP-01）
- **S-M4** 仪式偏好段：六 kind 中已设自动略过者的取消入口（FE-01）

缺图即对应条目未验（沿一、二期口径）。

---

## 附录 · 新增/变更总表（实现岗索引）

- **新函数**（均置 `core/ceremony.py`）：`build_loot_ceremony`、`build_spirit_ceremony`、`build_tribulation_ceremony`、`loot_ceremony_candidate`（谓词）。
- **既有函数改挂（只增/移位）**：`server/world.py` 四处——`/挖宝` 分发 return 只增 `ceremony`（H-L1）、`/捡漏` 分发 return 只增 `ceremony`（H-L2）、`/器灵` 唤分支 return 只增 `ceremony`（H-S1）、突破两出口 return 的 `ceremony` 改挂天劫幕并只增 `ceremony_next`（§5.2）。
- **既有函数修复**：`core/briefing.py` `build_entry` ⑤.6 段（S-1 逆序迭代 + S-2 一行补登 + S-4 注释改写），仅此一段。
- **零变更清单（写死）**：`core/breakthrough.py`、`core/npc_proactive.py`、`core/artifact_spirit.py`、`core/treasure_system.py`、`core/fate_thread.py`；无新表、无新模型字段、无新 config、无新命令、无新资产键。
- **只增字段总表**：突破两出口响应 +`ceremony_next`（天劫/突破双幕）；`/挖宝`、`/捡漏`、`/器灵` 唤三处响应 +`ceremony`（无幕时为 None 或缺失，前端等价处理）；前端 localStorage 偏好键按既有规则自然新增 `ceremony_skip_tribulation`、`ceremony_skip_loot`、`ceremony_skip_spirit` 三键（后端零感知）。
