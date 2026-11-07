# Spec：游戏感改造第一期（game-feel-phase1）

- 基线：worktree `.worktrees/game-feel-phase1`，分支 `feat/game-feel-phase1`，基线 main `90ce9c8` = v0.3.7-gray.14。
- 状态：**待实现**（本文件为唯一产出；本轮不写任何业务代码）。
- 定稿依据：`~/workspace/天道因果录-游戏感改造方案.md`（下称「方案」）§3、§4a（简版拆分线见 §7 第 2 件）、§4b、§4c（只突破幕 + 死亡/转世合并幕）、§4d（只关系可见化部分）、§5、§7 第一期与验收、§9 已定口径。**口径冲突时以方案为准；方案与本任务边界冲突时以任务边界为准，并已在 §0.3 逐条记账。**
- 红线（全 Spec 通用）：寿元是硬通货（规则一字不改）、规则引擎裁决数值、LLM 只叙事/言行；登录路径零新增 AI 调用（唯一例外是方案明列的 `NpcProactiveEngine.maybe_engage` 既有预算闸，见 §2.4）；仪式路径零 AI、零导演调用；涉及角色数据遵循 `AGENTS.md` 道体合规守恒律（写路径统一 `CharacterRepository.save`）。
- 本轮四件（定死，不扩不缩）：① 入口重做（§2）；② 简版人生开局 `core/origin.py`（§3）；③ 仪式演出两幕（§4）；④ 关系可见化（§5）。Out of Scope 见 §8。

---

## §0 · 五步推演结论摘要（requirement-evaluator）与代码事实纠正

### 0.1 五步推演（方案已定稿、Martinez 已全权授权；本推演只收敛派生口径，不重开方向）

**第一步 · 解构本质。** 表层需求是四件呈现/组织改造；本质是把方案 §1.2 的三条可检验标准落成一期可验收切片：新号前 30 分钟拿到「只属于他的人生」（出身卡 + 短期目标 + 终局命题）、老号每次登录前 3 分钟先处理「找上门的事」（入局队列）、高潮时刻有仪式（突破/死亡/转世）、关系变化看得见。验收本质不是「页面多了几块」，而是：出身的每一项都能在既有账上对账（A6）、目标判定式能离线复算（A7）、评语三落点可查（A8）、仪式跳过与看完最终状态逐字段相同（C2）、登录耗时不回归（B2）。

**第二步 · 可行性评估。** 可行性高，但落点与方案的文字描述有 9 处偏差（§0.2），全部已按实测现状改口径后才可施工。成本画像：新模块 2 个（`core/origin.py`、`core/ceremony.py` 建议名，含评语拼装可并入 origin 或独立 `core/epitaph.py`，由实现岗定，但函数契约以本 Spec 为准）；`Character` 新增 3 个带默认值字段（`origin` / `fate_boons` / `fate_pending`，零迁移）；`LifeTrace` 新增 4 个带默认值字段；`Promise` 新增 1 个带默认值字段（`paid`）+ `PROMISE_KINDS` 新增 1 类；零新表、零新 API 端点（全部挂既有 `/login`、`/join`、`/register`、`/world/briefing`、`/action` 响应，只增字段）；新命令恰 1 条（`/命格`，见 §4.2，含 CLI 双端）。

**第三步 · 不足与盲区（均已在设计中堵住，标注落点）。**
1. 目标挂 `GoalEngine` 会被既有 7 日过期与 6 条上限挤掉 → §3.7 定 `origin`/`fate` 两源豁免口径。
2. 诺言账没有「旧债」类型、且 `make_promise` 要求同场 → §3.5 定新 kind `debt` + 生成器直写仓储的专用路径 + 还款事实钩子。
3. `EventLedger` 没有 `data_json` 列 → §5.1 定 RELATION 的结构化载体为 `refs_json`（`k:v` 串列表）+ `effects_digest` 人读摘要。
4. 因果链兑现走仓储自读自存，与登录拼装的活对象存在 F05 陈旧覆写风险 → §2.3 定「拼装只用新读对象、拼装后至多一次回存」铁律。
5. 命格若只存仪式里，玩家跳过即丢选择 → §4.2 定待选状态机（候选结算时已抽定落盘，仪式与命盘走同一选择函数）。
6. `accounts.last_login` 只写无读 → §2.2 定新增只读 getter，且水位必须在 app 层 `touch_login` 之前于 `World.join` 内捕获。

**第四步 · 举一反三。** 横向：RELATION 留痕挂在 `shift_attitude` 单点，与因果链 S1 钩子同位，后续任何态度来源自动可见，不逐调用点补；判定式求值收敛为一个求值器（§3.7），第二期中期目标/章节 check 直接复用同一求值器与同一 kind 白名单；`ceremony` 响应结构按方案 §4c 的六幕通用形状定（一期只产两幕），第三期补幕不改前端协议。纵向：origin 块与 `FateThread.origin` 同形状（§3.2），第二期收编是复制而非转换。涟漪：`_status_dict` 只增键（`origin` / `fate` / `relations_recent` / `relations_marks`）；`trace_summary` 只增键；登录响应只增 `entry`（及回退路径的 `entry: null`）；既有前端忽略新键不报错（沿仓内只增字段惯例）。

**第五步 · 完善方案（收敛点，即本 Spec 的四个定死口径）。**
- **K1 · origin 块存储通道**：`Character.origin: Dict[str, Any]` 新字段（默认值 `{}`），不用账户级 KV。理由见 §3.2。
- **K2 · 命格待选状态机**：结算时抽定、落 `Character.fate_pending`（FIFO 队列，≤2 抽），选择走唯一函数、仪式内外等价。状态机见 §4.2。
- **K3 · 判定式求值点清单**：求值器只挂 6 个既有点（登录拼装 / 诺言终态 / 突破成功 / 态度移位 / 死亡结算 / `sync_progress` 既有调用链），不新增 tick 扫描。清单见 §3.7。
- **K4 · 移动端预算**：实测余量 CSS 136B / JS 4 行，必然不够；豁免申请数额见 §9.1（CSS 上限 25702B → 27400B；mobile.js 净增上限 190 行 → 390 行）。

### 0.2 代码事实纠正表（与方案/任务简报描述不符者，一律按实测施工）

| # | 描述出处 | 实测现状 | 本 Spec 口径 |
|---|---|---|---|
| F1 | 方案 §1.1/§4b 称 `build_briefing` 已在登录链路被调用（`server/app.py:344`、`server/world.py:1441`） | 函数真名是 `core/briefing.py:11 briefing(character, *, world_limit=6, me_limit=4)`，调用方以 `briefing as build_briefing` 别名导入；它**不在** `/login`、`/join`、`/register` 响应里——登录响应（`World.join` / `World.dead_payload`）根本不含 briefing；现行调用点只有 HTTP `GET /world/briefing`（`server/app.py:373` 一带）与 `/近况` 命令（`server/world.py:1516` 一带）。返回形状：`{ok, dead, location, world[], related[], goals[], text}`，三段文本由 `format_briefing_text` 拼装（世间/与你何干/世间目标） | 入局是**新挂**到登录响应的结构（§2.2），不是「把已有字段升级」；`briefing()` 本体与既有两处调用点行为零改动，只在其返回上只增 `entry` 键 |
| F2 | 方案 §4b 称简报水位复用 `last_login` 即可 | `accounts.last_login` 存在（`storage/db.py:198`），`AccountRepository.touch_login`（:1625）在 app 层「实际发会话后」才写（`server/app.py:68 _touch_login_on_session`，回退/503 不写）；但**没有任何读口**：`get_by_username` 不选该列，无 getter | 新增 `AccountRepository.get_last_login(user_id)` 只读方法；水位在 `World.join` 内、app 层 touch 之前捕获（§2.2） |
| F3 | 方案 §4a 称债落诺言账「类型=旧债」 | `core/promises.py:40 PROMISE_KINDS` 只有 gift/arrive/quest/no_attack 四类，无旧债；`PromiseEngine.make_promise`（:144）要求立诺双方同场、受诺方存活、未结诺 ≤`PROMISE_MAX_OPEN=3`、同（对象，kind）不可叠诺；NPC 对象立诺即 ACTIVE 并按 kind 的 ttl（现实秒，3 或 7 日）设 deadline；到期非 no_attack 一律 BROKEN（`_advance`），KEPT 只认既有事实钩子（赠礼/抵达/委托/斗法） | 新增 kind `debt`（§3.5）：生成器直写仓储（不走 `make_promise` 的同场门禁）、还款走新事实钩子 `note_debt_payment`、到期 BROKEN 复用既有 `_advance` |
| F4 | 方案 §4d 称 `shift_attitude` 是态度「唯一写入口」、RELATION 留痕 `data` 带结构化字段 | (a) 存储层真写入口是 `NpcMindRepository.set_attitude`；`core/npc_mind.py:86 shift_attitude(npc, other_id, delta, reason="")` 是业务层入口，但 `core/inheritance.py apply_karma_shadow` **直调** `set_attitude` 施加影子（不经 shift）。(b) `shift_attitude` 在 reason 非空时已写一条 `type="ATTITUDE"` 的 EventLedger（经 `core/memory.py:40 record_event`，但**不传 target**，行内 target_id 为空）。(c) `event_ledger` 表（`storage/db.py:150`）**没有 data 列**：只有 `effects_digest`（append 时截 120 字）与 `refs_json` 两处可承载结构 | RELATION 挂 `shift_attitude`（业务路径全覆盖）；影子直写路径一期不留痕（已有 `karma_shadow` 展示通道，§5.4 明列）；结构走 `refs_json` 的 `k:v` 串 + `effects_digest` 摘要（§5.1）；既有 ATTITUDE 行保留不删（NPC 记忆检索在用） |
| F5 | 方案 §4c 称命格效果「走既有赐福通道、挂 dungeon/战斗既有生效点」 | `DAO_BOON_CATALOG`（`core/dungeon.py:134`，5 键 pure_yang/iron_wall/sword_heart/spirit_well/ice_soul，值只有 key/name/icon/desc，desc 是局内数值如「伤害 +35%」）的生效点只有两处：`core/spells.py:152 create_player_entity(char, boons=None)` 与同文件战斗步进函数——且**仓内除 dungeon 会话外没有任何调用方传 boons**（dungeon 传的是会话内 `sess["boons"]`，出窟即焚）。`CombatEngine.calculate_power`（`core/combat.py:86`）不读 boons，但有成熟的乘子链先例（装备/功法/灵宠/心法槽/器灵 `ArtifactSpiritEngine.power_bonus`/`BodySoulEngine` 均以 try/except 挂在此链） | 命格借目录的 key/name/icon 作身份与文案，**数值不套局内 desc**；生效点改挂 `calculate_power` 乘子链（器灵先例），数值走新 config 表 `FATE_BOON_POWER`（§4.2）。这是对方案字面的修正，理由：局内会话生效点在结构上无法承载跨会话命格 |
| F6 | 方案 §4a 称路径开关可调「地点既有解锁条件」 | `/go` 迁跃（`server/world.py:1462`）与 `core/world_grid.py` 节点（danger/is_safe/density）**没有**任何解锁/境界门槛参数；地点层面的既有门槛只有宗门洞府免费闭关（属宗门权益） | 一期 place 类开关**只产 favored 一种**，载体为出生地落点 + origin 块记录，不产 closed（无既有参数可关，硬造旅行封锁属新规则，越界）；sect closed 与 vendor 态度载体照常（§3.6） |
| F7 | 任务简报称 `LifeTrace`、`settle_death` 在 `core/inheritance.py` | `LifeTrace` / `ShadowEntry` / `LegacyAccount` / `LegacyEngine.settle_death` 真身在 **`core/legacy.py`**（LifeTrace :56、ShadowEntry :40、LegacyAccount :89、`total_lives` :93、settle_death :247、痕迹构建 `_build_trace`）；`core/inheritance.py` 是影子施加（`apply_karma_shadow`）+ `trace_summary`（:195）+ `tombstone_text`（:231，现行墓碑**不含**评语行） | 评语/fate_summary/signature/unfinished 四字段加在 `core/legacy.py` 的 `LifeTrace`；生成点在 `settle_death` 的 `_build_trace` 同次（§3.9）；`tombstone_text` 与 `trace_summary` 在 inheritance.py 只增 |
| F8 | 方案 §4a 数据模型称出身块暂存「角色既有数据通道」；仓内似有自由字段 | `Character`（`core/models.py:278`）**没有**通用自由 JSON 字段；既有扩展惯例是「加带默认值字段」（`gender`/`demon_seed`/`pill_*` 等皆然，旧档零迁移）。账户级 KV（`WorldStateRepository`，图鉴 `gallery_atlas:{user_id}` 先例）是**跨世账户**生命周期，与出身的**单世**生命周期相反 | 选 `Character.origin` 新字段（K1，§3.2 给全理由）；待选命格同理走 `Character.fate_pending/fate_boons` |
| F9 | 方案 §4d 称交谈弹窗旧账行等三处可见化 | 本轮任务边界只做两处（命盘近 5 条 + 同场箭头） | 交谈旧账行入 Out of Scope（§8），与任务边界一致 |

### 0.3 任务边界优先于方案的记录（按指令记账）

- 方案 §4c 六幕一期只做两幕（突破含命格、死亡/转世合并）；天劫不单独立幕（并入突破幕 beats，见 §4.3）；得宝/器灵/天劫独立幕入 Out of Scope。
- 方案 §4a 的世仇强制植入一期不做（§8）；一期转世混合只做未竟之志头号候选 + 影子合并（§3.10）。
- 方案 §4d 主动戏剧五类一期不做（§8）；入局时 `maybe_engage` 补触发是 §4b 口径，不算戏剧扩展。

---

## §1 · Problem

玩家登录后面对工作台与 99 条命令，没有「局」；建角是白纸开局（人人 150 灵石、同落点、无关系无往事）；突破与死亡只有结算行；态度变化只在交谈时可见。方案第一期要求在**不新增持续状态机（fate_threads）、不动任何既有数值与命令语义**的前提下，交付四件可感知改造：入局成为主界面范式、简版人生开局（纯规则生成器）、两幕仪式、关系可见化。本 Spec 把四件逐件落到真实文件/函数/字段，给出接口契约（只增字段清单）、频控与性能约束，以及逐条可观察验收（§7，每条标注方案验收编号）。

**真正需求条目（收敛结论，实现与验收的唯一依据）：**

- RQ-1（入口）：登录响应只增 `entry` 结构；入局含三线动态与事件队列（高亮 ≤3、个人因果优先、无事明示「江湖无事」）；桌面默认渲染层改为入局、移动端动态分区置顶卡 + 默认落点 feed；工具层（工作台全部视图、99 条命令 + 新增 `/命格` 1 条）行为与语义零改动。
- RQ-2（开局）：新模块 `core/origin.py` 纯规则零 AI 生成五维出身包，全随机 + 全部 bounds + 总分中位带钳制 + 近 3 世防重；落账全走既有设施；注册建角与转世各生成一次，老角色不追溯；出身卡双端第一屏。
- RQ-3（目标与评语）：短期目标（出身派生）与终局命题以 `check` 判定式挂 `Character.goals`（`GoalEngine` 结构扩展）；求值只挂既有钩子/拼装点；到期未达成转未竟之志入 `LifeTrace`；一生评语模板版与 `fate_summary`、`origin_signature` 同次入 `LifeTrace`，三落点可查。
- RQ-4（仪式）：突破幕与死亡/转世合并幕只增响应层 `ceremony` 结构，先结算后演出、零 AI、零锁内耗时；命格三选一的待选状态机保证跳过等价（C2）。
- RQ-5（关系）：`shift_attitude` 挂 RELATION 留痕写 EventLedger；`_status_dict` 只增 `relations_recent`/`relations_marks`；双端两处展示（命盘近 5 条、同场近变箭头）。
- RQ-6（守恒）：零新表；拼装按 player 过滤禁全表扫描（既有仓储的既有全表口径不新增、不背锅，见 §6）；全量回归不新增失败（基线见 §7.6）。

---

## §2 · 件一：入口重做（方案 §4b 全量）

### 2.1 现状锚点（实测）

| 对象 | 现状 |
|---|---|
| `core/briefing.py briefing()` | 入参 `character`（+ `world_limit/me_limit`）；内部调 `jianghu.list_recent`、`jianghu.project_related(character.id)`、`GoalEngine.sync_progress`、`GoalEngine.list_for`（只回 active）；返回 `{ok, dead, location, world[], related[], goals[], text}` |
| 登录链路 | `POST /register`（`server/app.py`）→ `core/account.register` 建账号行 → `World.join`；`POST /login` → `core/account.login` 验密 → 死者先 `World.dead_payload`（非空即返回）→ 否则 `World.join(auto_rebirth=False)`；`POST /join` → `World.join(auto_rebirth=True)`。`World.join`（`server/world.py:281`）短临界区建角/发 token，锁外做任务板与 first-night 异步调度，返回 snap（token/user_id/character_id/name/realm/location/rem_years/legacy_points/lives/is_new_life/resumed/lock_fallback/session_issued/newbie_feed/first_night）。`dead_payload`（:712）返回死者 dict（legacy 含 `trace` 摘要、wallet、settlement、lock_fallback/session_issued/settlement_pending/settled） |
| `last_login` | `AccountRepository.touch_login` 由 app 层在 join/dead 返回后、且 result 带非空 token 时调用（`_touch_login_on_session`）；无读口（F2） |
| 桌面默认层 | `web/workbench.js` 视图集 `[sanctum, sect, wilderness, inventory, bazaar, gallery]`，`setView` 非法值回退 `sanctum`，登录后默认 sanctum（玄阁洞府全景） |
| 移动默认层 | `web/mobile.js` 视图集 `[feed, sanctum, bag, world, ops]`，`showApp()` 即 `setView("feed")`——动态分区本就是默认落点；`web/mobile.html` feed pane 内只有 `#feedLog` |
| 队列数据源现状 | `KarmaChainEngine.advance_for(char, now)`（`core/karma_chains.py:1033`，按 `list_by_player` 取本玩家链、单轮至多兑现 1 条，兑现时引擎自读自存玩家行）；`KarmaChainEngine.status_summary(char)`（:1131，只读 `{active, fermenting, nearest_mature_game_days}`，`_status_dict` 已在用）；`PromiseEngine.settle_due(char, now, actor_obj)`（`core/promises.py:313`，返回 bool，docstring 明示须传 `actor_obj=活对象` 防陈旧覆写）；`EventChainEngine.active_for(char_id)`（`core/event_chains.py:139`，读 WorldState KV）；`core/omen_scene.py:668 get_scene(player_id)`（未散场会话）；`NpcProactiveEngine.maybe_engage(player, chance_scale=1.0, max_speakers=1, force=False)`（`core/npc_proactive.py:115`，类冷却 90 秒进程内 + AI 预算闸）；`core/world_arc.py:264 active_arcs()` 与 `core/world_director.py:706 active_directives()`（均读 WorldState KV）；`core/here.py list_here` 与态度账见 §5 |

### 2.2 数据与拼装（零新表、零新状态）

新增拼装函数（建议名 `build_entry`，置 `core/briefing.py`）：

```python
def build_entry(character, *, since: float, now: float | None = None,
                allow_proactive: bool = True) -> dict
```

- `since`（水位）由调用方传入，函数内不自读账户行：`World.join` 在锁外收尾段调用前，先以新增的 `AccountRepository.get_last_login(uid)` 读**上一次**登录时刻（app 层 touch 尚未执行，读到的必是旧值）；`since <= 0` 或无账户行时回退 `character.born_at`。`GET /world/briefing` 调用时传当前 `get_last_login`（注：该值已被本次登录 touch 更新，窗口收窄为本会话内——这是明示口径：入局的权威下发面是登录响应，briefing 端点/entry 刷新只作同会话内增量，不得据此判 B1 不过，B1 以登录响应断言）。
- 拼装顺序（写死，顺序即副作用次序）：① 以 `character` 活对象调 `PromiseEngine.settle_due(character, now, actor_obj=character)`（调用前先按 §2.3 捕获到期诺言快照）；② `KarmaChainEngine.advance_for(character, now)`；③ §3.7 求值器 `evaluate_checked_goals`（拼装点 E1）；④ 只读组装 lines 与 queue（数据源见 §2.3）；⑤ `allow_proactive` 时至多 1 次 `maybe_engage(character, force=False)`，其产出（开口 NPC/台词）转成 1 条 queue 项（kind=`npc_visit`）并附在返回的 `proactive` 字段（前端可同时 pushFeed）。
- **陈旧对象铁律**：`advance_for` 的兑现由引擎自读自存玩家行（F05 先例），`settle_due` 靠 `actor_obj` 落活对象。拼装所用 `character` 必须是**锁外新读**的对象（join 锁外段以 `CharacterRepository.get_by_user_id` 重读，或 briefing 端点入口处的新读）；拼装全程结束后，若 ①②③ 任一产生变更，调用方以该新读对象 `CharacterRepository.save` **至多回存一次**；严禁用锁内旧对象在拼装后回存。join 的 snap 标量字段在锁内已定，拼装不改 snap。
- 拼装失败隔离：每个数据源各自 try/except（沿仓内惯例），单源失败只缺该源的项，不得使登录失败；`build_entry` 整体异常时 join 返回 `entry: null` 照常发会话（入口降级为旧行为）。

### 2.3 接口契约（只增字段清单）

**登录响应**（`World.join` 正常返回、app 层 `/login` `/join` `/register` 的 200 体）：只增一键 `entry`（结构见下）；锁忙回退快照（`_live_fallback_snapshot`）只增 `entry: null` + `entry_pending: true`（与 `settlement_pending` 同型口径，繁忙即不拼装）。`dead_payload` 正常与回退两路**不增 entry**（死者走 §4.4 仪式），只增 `ceremony`（见 §4.4）。`GET /world/briefing` 与 `/近况` 命令的响应：在 `briefing()` 既有返回上只增 `entry` 键（值同下；`allow_proactive=False`——命令/端点刷新不重复触发来访，来访只挂登录拼装一次）。

`entry` 结构（定稿）：

```jsonc
{
  "version": 1,
  "since": 0.0, "generated_at": 0.0,
  "lines": {
    "fate": "命途：<终局命题文>（<状态>）· 短期：<短期目标标题>（<状态>）",  // 无 origin 老角色回退见下
    "chains": {"fermenting": 0, "nearest_mature_game_days": null, "text": "发酵中因果链 N 条，最近一条约 X 游戏日后到期"},
    "relations": [ /* 近 3 条，形状同 §5.3 relations_recent 项 */ ]
  },
  "queue": [ /* 全部项（≤8），已按优先级排序，形状见下 */ ],
  "highlight": [ /* queue 前 ≤3 条的同一对象引用序列化 */ ],
  "rest_count": 0,
  "empty": false,
  "empty_text": "江湖无事，可自由行动"   // 仅 empty=true 时前端展示此句（B3）
}
```

- `lines.fate`（命途占位，一期无主线）：有 origin 的角色取其终局命题目标 + 短期目标的当前状态（读 `character.goals` 中 source=`fate`/`origin` 项）；无 origin（老角色）回退为第一个 active 目标的 `title — detail`；无任何 active 目标时为「命途：尚未立命，转世后自有新命」。
- `lines.chains`：数据源 `KarmaChainEngine.status_summary(character)` 只读拼装，不另查链表。
- `lines.relations`：数据源 §5 的 RELATION 查询（同 §5.3，取近 3 条，`ts > since` 优先；不足时以最近 3 条兜底并以 `ts` 明示）。

`queue[]` 项结构：`{kind, priority, title, text, ref_id, target, ts}`，`target` 只许两种形态：`{"command": "/因果链"}`（前端走既有 sendCmd）或 `{"view": "sanctum"|"world"|...}`（前端走既有 setView），均为既有命令/视图深链，不新造交互。来源与优先级（priority 升序 = 因果深浅，写死）：

| priority | kind | 数据源与生成条件 | target |
|---|---|---|---|
| 0 | `karma_resolved` | `advance_for` 本轮返回 `action == "resolved"` 的链（≤1，引擎单轮上限） | command `/因果链` |
| 1 | `promise_settled` | 拼装前快照中已到期（ACTIVE 且 `deadline < now`，或 PENDING 且过应诺期）的诺言，在 `settle_due` 后复查已入终态者，逐条成项（≤2，超出合并为一条计数项） | command `/诺言` |
| 2 | `goal_flip` | 求值器本轮新翻转（done/failed）的 origin/fate 目标，逐条成项（≤2） | view `sanctum`（命盘命途段） |
| 3 | `karma_maturing` | `advance_for` 返回的 ferment/dormant 推进项，或 status_summary 显示有链将在 1 游戏日内到期 | command `/因果链` |
| 4 | `omen_active` | `EventChainEngine.active_for` 非空，或 `omen_scene.get_scene` 非空（未散场） | command `/奇遇` |
| 5 | `npc_visit` | 本轮 `maybe_engage` 实际开口（≤1） | view `world`（移动）/ 桌面同场抽屉（前端既有打开方式） |
| 6 | `opportunity` | `character.goals` 中 source=`omen` 的 active 机缘目标（≤1，取最新） | command `/目标` |
| 7 | `world_arc` | `active_arcs()` 中 location == 角色 location 或 sect == 角色 sect 的弧（≤1）；无个人相关弧时才取 `active_directives()` 中 `calamity_forecast` 类 1 条 | command `/世情` |

队列总项截断 8 条（按 priority 截断尾部），`highlight = queue[:3]`，`rest_count = max(0, len(queue)-3)`。无任何项时 `empty=true` 且 queue/highlight 为空数组（前端必须显示 `empty_text`，不得硬凑）。

### 2.4 频控与性能约束

- 只在登录拼装（join 锁外段）与显式 briefing 刷新时拼装；join 路径每登录至多 1 次 `build_entry`、至多 1 次 `maybe_engage`（其自有 90 秒冷却/预算闸兜底，force 恒 False）。
- **零新增 AI 调用**的口径：`build_entry` 自身与其数据源（advance/settle/求值/lines/queue 组装）零 AI；唯一例外是 `maybe_engage` 内部沿既有预算闸可能发动的 1 次 proactive AI——这是方案 §4b 明列的既有引擎补触发，不是新通道，且受其冷却与 5 分钟窗口配额约束。B2 测法据此分两层（§7）。
- 全部查询按 player 过滤：链走 `list_by_player`、诺言走 `_involving(char.id)` 既有口径、 ledger 走 §5 的 target 索引查询、 goals/origin 读角色行内数据；`active_arcs/active_directives` 是 WorldState KV 单键读（非全表扫描）。禁止在拼装路径出现 `list_all` 类全表调用（既有引擎内部既有口径不在本条追责范围，但不得新增）。

### 2.5 前端动线与呈现

- **桌面**（`web/workbench.js` + `web/index.html`）：视图集新增 `entry`（入局）为第 7 视图并列入 nav 首位；登录成功（`showApp` 后）默认 `setView("entry")`；入局视图渲染 `state.entry`（登录响应存入 state；进入该视图时以 `GET /world/briefing` 刷新 entry 并合并）；顶部 nav 常驻入局 tab 即「随时可回」。既有 6 视图（工具层）渲染函数与行为一字不改，只改默认落点与 nav 顺序。队列项按钮按 `target` 分发既有 `sendCmd`/`setView`；`lines` 三行置于队列上方。出身卡与仪式呈现见 §3.11/§4.5（同在本视图/弹窗层实现）。
- **移动**（`web/mobile.js` + `web/mobile.html`）：不新增分区；feed pane 内 `#feedLog` 之前新增置顶容器（建议 id `entryCard`），`renderFeed` 前先渲染入局卡（数据同 `state.entry`，登录响应或 briefing 刷新）；默认落点保持 feed（现状即 feed，零改动）；入局卡样式复用既有 card/玉简条类与 token，新增样式计入 §9.1 豁免额度。
- 双端共同：`entry` 缺失/null 时不渲染入局层（桌面回退默认 sanctum、移动不显示置顶卡），沿既有降级惯例。

---

## §3 · 件二：简版人生开局（新模块 `core/origin.py`，纯规则零 AI）

### 3.1 现状锚点（实测）

| 对象 | 现状 |
|---|---|
| 建角 | `WorldClock.create_new_character(user_id, name)`（`core/clock.py:54`）：随机灵根（WASTE 50%/TRUE 35%/MUTANT 10%/HEAVEN 5%）、出生寿元 70–100、`spirit_stones=150`、落点写死「青云坊市客栈」、背包空。调用点：`World.join` 锁内建角并 `CharacterRepository.save`；`World.reincarnate`（`server/world.py:874`）锁内建角 → `LegacyEngine.apply_birth_boosts` → `apply_karma_shadow` → 双 save |
| 灵石发放口径 | 建角 150 即唯一发放口；转世新角同为 150（reincarnate 返回文明示「新角随身 150 灵石不变」，账户钱包另走 `/钱包提取`） |
| NPC 池 | `core/npc_roster.py ROSTER` 37 人，`seed_roster()` 幂等播种为 Character（user_id `npc_*`）；join 对新号在锁外、AI 之前同步播种。NPC 境界 tier 1–5 俱全，商会 sect=`四海散修商会` |
| 态度 | `shift_attitude(npc, other_id, delta, reason)` 为 delta 语义（在现值上增减），新角色 id 全新 → 对其初始现值恒 0（影子预写除外，见 §3.10） |
| KarmaLink 种子 | 模型 `core/bounty.py:75 KarmaLink{a_id,a_name,b_id,b_name,link_type,strength,note,created_at}`；既有造边入口 `core/collusion.py:20 ensure_link(a, b, link_type, note)`：同（双方，type）已有则 strength+1 并在 仇/恩 且 strength≥3 时回调因果链 S2 起链判断；新建 strength=1 |
| 宗门门槛 | `core/sect.py evaluate_join(c, sect)` 读 `SECTS_CONFIG`（config.py:459 起 4 宗门：`req_dao_heart`/`max_sin`/`min_sin` + 总坛地点 + 万剑仙门灵根特例） |
| 专柜门槛 | `core/trade.py:653 attitude_buy_mult /:665 attitude_sell_mult`：纯按态度值对 `NPC_ATTITUDE_FRIENDLY/HOSTILE` 阈值给折扣/加价——**态度本身就是专柜门槛参数** |
| 目标 | `Character.goals: List[Dict]`（角色行内）；`GoalEngine`（`core/goals.py`）：项形状 `{id, source, title, detail, status, progress, created_at, **extra}`，status ∈ active/done/expired/rejected/superseded；`ensure_goals` 对 active 超 7 现实日者置 expired、基础源 dao/newbie/season 恒补、`GOAL_MAX_ACTIVE=6`（config:198）；`add_opportunity(character, title, detail)` 建 source=`omen` 项（满额时先 supersede 一条旧 omen，仍满则失败返回）；`sync_progress` 由 `briefing()` 每次调用，只处理 dao/fame/survive/newbie 的 progress |

### 3.2 origin 块形状与存储通道（口径 K1 定死）

存储：`Character` 新增字段 `origin: Dict[str, Any] = Field(default_factory=dict)`，空 dict = 无出身（全部老角色与 NPC）。选此通道的理由（与备选逐项对比，结论写死）：

- 备选 A（账户级 WorldState KV，如图鉴 `gallery_atlas:{user_id}`）：生命周期错误——KV 按 user_id 是跨世账户数据，出身是单世数据，按 char_id 挂 KV 会产生孤儿键，且死亡结算 `_build_trace`（锁内/结算路径）需为出身多一次 KV 读、生成时灵石与出身分两处落盘存在崩溃不一致窗口。**否决**。
- 备选 B（塞 `Character.goals` 或某 List[Dict]）：语义污染目标系统，`ensure_goals/list_for` 会误读。**否决**。
- 选定（新字段）：仓内唯一惯例就是带默认值字段扩展（gender/demon/pill 先例），与角色行同生同灭、`CharacterRepository.save` 原子落盘（含道体审计）、`_status_dict` 直读零新增查询（护 B2）、`_build_trace` 直读零新增 IO。第二期收编：建 `fate_threads` 时把 `char.origin` **逐字复制**为 `FateThread.origin`（同形状，故字段名与嵌套以方案 §4a 的 origin 定义为准），此后主线为主、角色行内块冻结为快照；signature 另已入 LifeTrace，防重不依赖任一处。

块形状（与方案 §4a `FateThread.origin` 同形）：

```jsonc
{
"family": "药农", "family_text": "青石镇药农之子", // 家世类 + 一句定稿文案
"signature": "药农|父辈旧债|npc_sh_02|debt", // §3.8
"birthplace": "青云坊市客栈",
"stones_final": 110, // 落账后的随身灵石绝对值 ∈[80,260]
"debt": {"creditor_npc_id": "...", "creditor_name": "...", "amount": 80, "promise_id": "..."} | null,
"relations": [{"npc_id": "...", "npc_name": "...", "role": "kin|foe|witness",
"init_value": 40, "is_creditor": false}],
"old_story": {"kind": "父辈旧债", "npc_id": "...", "item_ref": "", "summary": "……"},
"path_gates": [{"gate": "sect|vendor|place", "target_ref": "...", "effect": "closed|favored"}],
"strength_score": -12,
"short_goal_id": "g_origin_…", "fate_goal_id": "g_fate_…",
"extreme_bad": false, "dedup_retries": 0, "generated_at": 0.0, "life_no": 1
}
```

### 3.3 家世池（定稿 12 类，≥10 的硬线在此销账）

抽取为等权随机（灵根衔接只调旧事/关系权重，不调家世权重——保 A9 的构成差异可观察）。`birthplace` 候选只许公共安全节点（F6）：`青云坊市客栈`、`落霞山灵泉`、`青云宗外门山门`、`万剑仙门峰`。

| # | 家世 | family_text 模板 | 出生地候选 | 旧事权重偏向 | 灵石基调（生成器内权重，非玩家可见） |
|---|---|---|---|---|---|
| 1 | 寒门农家 | 山野寒门之子 | 客栈/灵泉 | 家道中落、幼年奇遇 | 偏低 |
| 2 | 药农 | 青石镇药农之子 | 客栈/灵泉 | 父辈旧债、宝物遗失 | 中 |
| 3 | 商贾 | 行商之子 | 客栈 | 父辈旧债、家道中落 | 偏高 |
| 4 | 书香门第 | 书香门第之后 | 客栈/青云山门 | 师门旧怨、幼年奇遇 | 中 |
| 5 | 宗门旁支 | 宗门旁支子弟 | 青云山门/万剑峰 | 师门旧怨、族仇未雪 | 中 |
| 6 | 罪族遗孤 | 没落罪族遗孤 | 客栈 | 族仇未雪、背案在身 | 中低 |
| 7 | 猎户 | 山野猎户之子 | 灵泉/客栈 | 幼年奇遇、恩人救命 | 中低 |
| 8 | 流民 | 流民之子 | 客栈 | 家道中落、恩人救命 | 低 |
| 9 | 渔户 | 泽国渔户之子 | 灵泉/客栈 | 幼年奇遇、宝物遗失 | 中 |
| 10 | 铁匠 | 坊市铁匠之子 | 客栈 | 父辈旧债、宝物遗失 | 中 |
| 11 | 镖师之后 | 镖局子弟 | 客栈/万剑峰 | 族仇未雪、背案在身 | 中 |
| 12 | 医户 | 杏林医户之子 | 客栈/灵泉 | 恩人救命、父辈旧债 | 中 |

### 3.4 旧事模板族（定稿 8 类）

每类定：触发素材、必绑定的关系角色、终局命题候选映射（§3.7）。对象必为本包 relations 中某人（债主可为 old_story 对象且不必另占关系名额，见 §3.5）。

| kind | 一句话summary 模板（变量：{npc}=绑定对象名） | 绑定角色 | 命题映射 |
|---|---|---|---|
| 父辈旧债 | 父辈欠下{npc}一笔旧账，父债子偿 | creditor | debt_clear |
| 家道中落 | 家道中落，祖产散尽，只剩一口气 | witness | family_revive |
| 幼年奇遇 | 幼年曾在山中遇异事，醒来只记得{npc}的名字 | witness | stand_firm |
| 族仇未雪 | 族中长辈死于{npc}之手/其同门之手，旧账未清 | foe | foe_reckoning |
| 恩人救命 | 幼年落难，蒙{npc}出手相救，恩未报 | kin | stand_firm |
| 背案在身 | 身上背着一桩说不清的旧案，{npc}知情 | witness(+foe 可) | foe_reckoning/stand_firm |
| 师门旧怨 | 长辈与{npc}一门有旧怨，绵延至今 | foe | foe_reckoning |
| 宝物遗失 | 家传之物遗失多年，传言与{npc}有关 | witness | lost_relic（item_ref 按家世取：药农=祖传药碾/铁匠=祖传锻锤/渔户=避水珠/其余=家传玉佩） |

### 3.5 资源与债（落账口径写死）

- 灵石：生成器抽 `stones_final ∈ [80, 260]`（整数，按家世基调加权抽取后仍须落在此闭区间，越界重抽该维）；生成时以**赋值**把 `char.spirit_stones = stones_final`（建角的 150 只是生成前初值，不是增减基准的账面事实），随生成落盘一次完成（见 §3.10 时机）。A6 对账口径：落账后角色行灵石 == origin.stones_final。
- 债：约半数包带债由旧事/抽签决定（`父辈旧债` 必带债；其余 kind 以 35% 概率带债且债主与旧事对象可不同人）；`amount ∈ [0, 120]` 整数（0 即无债，debt=null）；债主池 = 在世 NPC 中 `sect == 四海散修商会` 或 agenda == `treasure` 者（钱债找钱口，天然可还），生成时以仓储对象复核在世（status 非 DEAD 且寿元未竭），不在世则重抽债主，无可用债主则本包无债。
- 债的落账（F3）：`PROMISE_KINDS` 新增 `"debt": {"cn": "旧债", "ttl": 10 * 86400.0}`——注意既有 ttl 是**现实秒**口径而方案要 10 **游戏日**：生成器不依赖 kind ttl，而是直写 `deadline = generated_at + 10 * SECONDS_PER_GAME_DAY`（用 config 当值换算成绝对时刻，与因果链的游戏日口径一致；`PROMISE_KINDS["debt"]["ttl"]` 仅作面板文案与 describe 兜底）。生成器构造 `Promise(promiser=新角, promisee=债主, promisee_is_npc=True, kind="debt", param=str(amount), desc="旧债：欠{amount} 灵石（出身）", status=ACTIVE, activated_at=now, deadline=…)` 直调 `PromiseRepository.save`——不走 `make_promise`（同场门禁对生成场景不适用；新角此刻未结诺恒 0 条，`PROMISE_MAX_OPEN` 不冲突，生成后占 1 条额度，明示）。
- `Promise` 模型新增字段 `paid: int = 0`（仅 debt 类使用，旧档默认 0）。
- 还款事实钩子（新函数，建议名 `PromiseEngine.note_debt_payment(payer, creditor, amount, now)`）：累计 `paid += amount`，`paid >= int(param)` 时走既有唯一终态入口 `_settle(KEPT, "旧债已清", …)`（功德/态度/KarmaLink「诺」边等既有 KEPT 效果照常发生）。挂点两处（均为「灵石/财货真实流向债主」的既有落账点）：① `core/trade.py` 专柜买入结算（玩家向 NPC 付款额）；② `core/chat_actions.py` 赠礼结算（赠礼按既有计价口径折算的价值）。两处均以「对方 NPC 恰为某条 ACTIVE debt 的 promisee」为触发条件、try/except 包裹、失败不炸主流程。玩家绕过两通道时债不清、到期 BROKEN——与既有诺言「只认事实钩子」的哲学一致，文案在出身卡与诺言面板明示还款路径（买其货/赠其物皆可抵债）。

### 3.6 初始关系与路径开关（落账口径写死）

- 关系构成：先按旧事绑定角色，再从构成模式表抽一种补齐，总 distinct NPC ∈ [2, 4]：模式 ∈ {kin+foe, kin+witness, kin+foe+witness, kin+kin+foe, kin+foe+witness+witness}。选人约束（全部硬校验，不合重抽该人）：在世 NPC；foe 的 `realm.tier ≤ char.realm.tier + 1`（新角 tier 恒 1 → foe tier ≤ 2）；kin 优先同出生地或商会/散修且 tier ≤ 3；witness tier ≤ 4；同包不重复；转世时影子已覆盖的 NPC 不入选（§3.10）。
- 初始值：kin ∈ [+25, +55]、foe ∈ [-45, -15]、witness ∈ [-10, +15]（中立知情，可微偏）。落账唯一路径：逐人 `shift_attitude(npc_char, char.id, delta=init_value, reason="origin")`——新角现值恒 0（影子覆盖者已排除），delta 即终值；每次调用自带 §5 的 RELATION 留痕（reason=origin 在留痕中原样可见）。foe 另加一条 KarmaLink 种子边：`ensure_link(char, foe_npc, "仇", note="出身旧怨：{old_story.kind}")`——新建 strength=1 < 3，不触发因果链 S2 起链（种子只是引用，验收须断言无链生成）。
- 路径开关：抽 0–2 个，`effect=closed` 至多 1 个。生成与载体：
- `sect/closed`：任选一宗门（≠ 影子/旧事已指向的宗门时优先随机）→ 载体是新判定点：`evaluate_join` 在既有校验后追加一条 origin 校验——`char.origin.path_gates` 含 `{gate:"sect", target_ref:<宗门名>, effect:"closed"}` 时返回拒止（文案定稿为「【山门拒止】{宗门}与你有出身旧怨，山门不对你开。」）；`sect/favored`：对目标宗门 `req_dao_heart` 判定值临时 −10（config 常量 `ORIGIN_SECT_FAVORED_DAO_WAIVER = 10`，只减判定门槛、不改角色道心、不改 config 本体）。生存主干（四海散修商会无门槛宗）永不成为 closed 目标。
- `vendor/favored|closed`：目标 = 某名商会/专柜 NPC；**载体就是初始态度**（favored 者必须是 kin 档、closed 者必须是 foe 档，二者与关系抽取联动决定，不另设判定点）——态度阈值既有折扣/加价即门槛参数本身，A9 以专柜实际成交价差验收。
- `place/favored`（F6，只 favored）：target_ref = 出生地，载体为落点本身；不产 place/closed。
- 生存主干恒开校验：生成器断言——坊市基础交易（商会 NPC 不得全体为 foe；至少债主/一名 kin 中有一人可交易）、闭关与迁跃不引用 origin 任何字段（结构上天然成立，验收以代码检索 + A6 死局样本断言双证）。

### 3.7 分层目标简版：check 判定式、求值器与求值点（口径 K3 定死）

**挂载方式**：目标仍是 `Character.goals` 的 Dict 项，新增 source 两类：`origin`（短期）、`fate`（终局命题）。项形状在既有字段上只增：`{…, "tier": "short"|"final", "check": {...}, "deadline_at": float}`。对 `core/goals.py` 的契约变更（仅此四点，余皆不动）：① `ensure_goals` 的 7 日过期跳过 source ∈ {origin, fate}（其期限由 check 的 deadline 独立管辖）；② 新增两源不计入 `GOAL_MAX_ACTIVE` 计数、也不被 omen 的 supersede 逻辑选中；③ `reject` 对 source=`fate` 返回不可弃（同 dao 口径，加入 `NON_REJECTABLE`），source=`origin` 可弃（弃后不转未竟之志，记 rejected 即终局）；④ `KINDS` 增 `"origin": "出身"`, `"fate": "命途"` 展示名。新增挂载函数（建议名 `add_checked_goal(character, *, source, title, detail, check, deadline_days)`）：同 source 同 `check.ref` 已有 active 项时不重复挂（幂等，生成重入防线）。

**check 形状与一期 kind 白名单（写死，不得扩）**：`{kind, ref, …params, deadline_days}`，求值结果三态：done / pending / failed（failed 只由到期产生，见求值规则）。

| kind | params | done 条件（只读既有账） | 主要求值点 |
|---|---|---|---|
| `promise_settled` | ref=promise_id | PromiseRepository 中该诺 status == KEPT（BROKEN/DISSOLVED → 见到期规则按 failed 处理，但 BROKEN 当下即判 failed，不等到期） | E1/E2 |
| `stones_at_least` | amount | `char.spirit_stones >= amount` | E1/E6 |
| `realm_at_least` | tier, sub（可选） | `char.realm.tier > tier` 或 `== tier 且 sub_tier >= sub` | E1/E3/E6 |
| `npc_attitude_at_least` | npc_id, value | `attitude_toward(npc, char.id).value >= value`；**死亡终判特例**（仅 E5）：目标 NPC 已死 → done（恩怨两消） | E1/E4/E5 |
| `item_in_bag` | item_ref | 角色 `inventory`/`items` 中有名字含 item_ref 者（子串匹配，与旧事遗物口径一致） | E1/E6 |
| `sect_joined` | ref=宗门名或 ""（任意） | `char.sect` 非空且（ref 为空或相等） | E1/E6 |
| `item_in_bag_at_death` | item_ref | 同 item_in_bag，但**只在 E5 终判**求值（生前恒 pending） | E5 |

**求值点清单（写死，禁止新增 tick/轮询）**：求值器（建议名 `evaluate_checked_goals(character, now, *, final=False) -> List[flipped]`，置 `core/goals.py`，纯读既有账 + 只改入参 char 的 goals 项 status）：
- E1 登录拼装：`build_entry` 内（§2.2 顺序 ③）。
- E2 诺言终态：`PromiseEngine._settle` 完成 KEPT/BROKEN 后，对 promiser 的活对象（若可得）求值其 `promise_settled` 类；不便得活对象时允许跳过（E1/E6 必兜底，翻转至多迟到一次登录/近况）。
- E3 突破成功：`World._breakthrough` 与心魔后继突破段在既有 `GoalEngine.on_breakthrough_major` 同位追加求值（该钩子本就存在）。
- E4 态度移位：`shift_attitude` 返回前对 other 一方的 `npc_attitude_at_least` 类求值——other 活对象不可得时跳过（同 E2 兜底逻辑）；**注意**：origin 生成时逐人 shift 不得当场把 foe 命题判 done（初值 −45..−15 < 0 恒 pending，结构上成立，验收断言）。
- E5 死亡终判：`LegacyEngine.settle_death` 内、构建 trace 之前以 `final=True` 求值（见 §3.9）。
- E6 `sync_progress` 尾部：既有函数被 briefing/近况每次调用，在其既有逻辑后追加全量求值（stones/item/sect/realm 的兜底点）。
求值规则：pending 且 done 条件成立 → status=done、写 `done_at/done_reason="判定式达成"`；pending 且 `now > deadline_at`（deadline_days 为空者无到期）→ status=failed、写 `done_reason="到期未达成"`，且该目标成为未竟之志候选（短期与命题都是候选，命题优先，见 §3.9）；`promise_settled` 遇 BROKEN/DISSOLVED 立即 failed（不等到期）。求值器**从不自行落盘**：翻转写在入参 char 内存对象上，落盘归各求值点调用方的既有保存路径（E1 按 §2.2 铁律、E3 既有 save、E5 结算 save、E6 随 briefing 调用方既有节奏；崩溃丢失的翻转可由下个求值点重演，幂等）。

**短期目标族（每世恰 1 条，按出身派生，优先级写死）**：
1. 有债 → `{kind: promise_settled, ref: <旧债 id>, deadline_days: 10}`，title「偿清旧债」，detail 含债主与金额。
2. 无债且有 foe → `{kind: realm_at_least, tier: 1, sub: 2, deadline_days: 15}`，title「先站稳脚跟」。
3. 无债且有 sect/favored 门 → `{kind: sect_joined, ref: <该宗门>, deadline_days: 20}`，title「拜入{宗门}」。
4. 其余 → `{kind: stones_at_least, amount: 100, deadline_days: 7}`，title「攒下安身钱」。

**终局命题族（每世恰 1 条定盘，模板定稿 6 类）**：文案一句话 + check（无 deadline，终判在 E5 或生前达成）：

| kind（命题） | 文案模板 | check | 选取条件（优先级序） |
|---|---|---|---|
| `debt_clear` | 还清旧债，护住{家业词} | promise_settled(debt promise) | 上世未竟之志为此类且本世有债（§3.10）→ 本世有债 |
| `foe_reckoning` | 向{npc}讨个说法，让其再不敢轻慢你 | npc_attitude_at_least(foe, 0) | 未竟之志为此类且本世有 foe → 本世有 foe（旧事为族仇/师门旧怨时优先于 debt 之后） |
| `lost_relic` | 寻回遗失的{item_ref} | item_in_bag_at_death(item_ref) | 旧事 == 宝物遗失 |
| `family_revive` | 攒下 500 灵石，重振家业 | stones_at_least(500) | 旧事 == 家道中落，或家世 ∈ {商贾， 药农， 医户} |
| `sect_inner` | 拜入一门，站稳脚跟 | sect_joined("") | 家世 == 宗门旁支 |
| `stand_firm` | 筑基立身，不再任人摆布 | realm_at_least(tier=2) | 兜底（恒可用） |

选取顺序写死：未竟之志候选（可重实例化时）> debt_clear（有债）> foe_reckoning（有 foe）> lost_relic（旧事命中）> family_revive > sect_inner > stand_firm。

### 3.8 总分钳制、防重与逆袭种子（写死）

- 综合强度总分（生成器内部量，落 origin.strength_score）：`score = stones_part + relation_part + gate_part`，其中 `stones_part = round(((stones_final - 150) - debt_amount) / 10)`（范围约 [−19, +11]）、`relation_part = round(sum(init_value for relations) / 10)`、`gate_part = Σ(favored +8 / closed −8)`（place favored 计 +4）。中位带 **[−20, +20]**：带外 → 整包重抽（换全部随机维），至多 20 次；20 次仍带外 → 对最后一包做确定性修正（把 stones_final 向 150 方向逐 10 调整至入带，修正后仍须 ∈[80,260] 且在 origin 内记 `score_clamped: true`）。重抽/修正均为生成器内部行为，玩家无 reroll 入口（方案口径 4）。
- 极端坏命：最终 `score ≤ −15` → `extreme_bad=true`，生成尾声以 `GoalEngine.add_opportunity(char, "逆袭之机", "命途多舛，天道另开一线：……（按旧事模板一句）")` 附一条机缘种子。调用次序写死：**先** add_opportunity（其内部 ensure_goals 会先填基础目标，留出 omen 位）**后**挂 origin/fate 两条 checked 目标（两源不占上限，见 §3.7），保证种子不被上限拒收；若 add_opportunity 仍返回失败（如已有 omen active），不重试、不报错，origin 记 `extreme_bad_seed: false`。
- 防重：`signature = f"{family}|{old_story.kind}|{primary_npc_id}|{'debt' if debt else 'nodebt'}"`，primary 取 foe > creditor > 第一名 relations 的 npc_id。与本账户 `LegacyAccount.traces` 最近 3 世的 `origin_signature` 比对（第一世 traces 为空，恒不命中），命中 → 整包重抽至多 10 次（origin.dedup_retries 记实际次数）；10 次仍命中则接受最后一包并记 `dedup_exhausted: true`（池深有限时的诚实降级，不得无限循环）。

### 3.9 死亡衔接：一生评语、fate_summary、未竟之志（落 `core/legacy.py`）

`LifeTrace` 新增 4 字段（默认值保证旧档零迁移）：`fate_summary: str = ""`、`life_epitaph: str = ""`、`origin_signature: str = ""`、`unfinished_prop: Dict[str, Any] = {}`。

生成点与次序（写死）：`LegacyEngine.settle_death` 内、trace 构建（`_build_trace`）时同次生成，整段以 try/except 包裹，任何异常只使四字段留空，**不阻断结算**（含幂等重放路径：已有 trace 时不重算，沿既有 already_settled 口径）。`_build_trace` 可见入参 char 的 `origin`、`goals` 与 account 全量，直接拼装：

1. 先以求值点 E5（`final=True`）终判该角全部 checked 目标（态度类死亡特例在此生效）。
2. `origin_signature` = `char.origin.signature`（无 origin 老角色为 ""）。
3. 未竟之志：终判后 status=failed 的 fate 目标优先、其次 failed 的 origin 目标、再次死亡时仍 active 的 fate 目标（命题未及即逝，同记未竟）；取其一写入 trace.unfinished_prop = `{kind, text, check}`（check 原样），且在 fate_summary 中成句。仍 active 的短期目标不入未竟（小事随风）。
4. `fate_summary`（定稿拼装式，一行）：`出身{family_text}，{old_story.kind}起；终局命题「{命题文}」{成|憾}；短期目标{成|憾|未立}；最高{realm}。` + 未竟时追加 `未竟之志：{未竟文}。`无 origin 的老角色：fate_summary 按既有数据拼 `无出身记录；最高{realm}。`（不得编造）。
5. `life_epitaph`（评语）= 汇总句 + 定性句：汇总句即 fate_summary 的压缩形（规则拼装：出身/命题成败/最高境界/死因）；定性句按（命题 kind × 成/憾）选命题句式、按死因类别选尾句，拼接而成。死因分类（对 `death_cause` 字符串匹配，写死）：含「天劫/渡劫」→ tribulation；含「心魔」→ heart_demon；含「斩/斗法/擒/仇」→ violent；含「寿/坐化」→ natural；其余 → misc。选句确定性：`hash(f"{char.id}:{life_no}") % len(候选)`，同输入恒同输出（可复算）。模板族（定稿，每格 ≥1 句，實現可同格增至 2–3 句但不得改键）：

| 命题 kind | 成 | 憾 |
|---|---|---|
| debt_clear | 债清身轻，这一世把欠天下的都还上了。 | 债未清，人已去，账还留在世上。 |
| foe_reckoning | 该讨的说法都讨到了，恩怨两清。 | 那个名字，到死也没能再当面叫一声。 |
| lost_relic | 遗物归怀，家里的灯又亮了一盏。 | 那件旧物，终究没能找回来。 |
| family_revive | 家业重振，灶火重新旺了起来。 | 家道未复，这一世只来得及挣扎。 |
| sect_inner | 有门有派，这一世站住了。 | 山门终究没能收留他。 |
| stand_firm | 从任人摆布到立身于世，他做到了。 | 立身未成，命已先尽。 |
| （无命题/老角色） | 这一世有始有终。 | 这一世匆匆而过。 |

尾句：natural「寿终正寝，也算善终。」/ tribulation「殁于天劫，是修士的葬礼。」/ heart_demon「败给了心里的那个自己。」/ violent「死于人手，江湖恩怨从不等人。」/ misc「世事无常，道途如此。」

**三落点**（A8）：① 墓碑——`core/inheritance.py tombstone_text` 在既有行末只增一行：life_epitaph 非空时追加 `一生评语：{life_epitaph}`；`trace_summary` 只增 `fate_summary/life_epitaph/origin_signature/unfinished_prop` 四键（dead_payload 与 legacy_info 自动受益）。② 死亡/转世仪式余韵（§4.4 beats 只读引用）。③ 新世出身卡「前世曰」一行（§3.11，数据源 = 上一世 trace.life_epitaph）。

### 3.10 生成时机与转世混合（一期口径写死）

- 生成函数（建议名 `OriginEngine.generate_for_new_life(char, account, *, rng=None, now=None) -> origin dict`）：全部随机经入参 `rng`（`random.Random`，缺省用模块 random），保证测试可播种复算（A6/A7）。幂等闸：`char.origin` 非空即直接返回既有块，不重生成、不重复落账。
- 时机一（注册建角）：`World.join` 锁外收尾段、既有 `seed_roster()` 同步播种**之后**（NPC 必须已存在）、first-night 调度前后不论，但必须在 join 返回之前完成并 `CharacterRepository.save(char)` 一次落盘（含灵石赋值/落点/目标挂载）。生成失败（异常）→ 吞掉异常、char.origin 留空、建角照常成功（出身是增益层，不是建角门禁）。
- 时机二（转世）：`World.reincarnate` 内，在 `apply_karma_shadow` **之后**、统一 save 之前调用（reincarnate 本就全程持锁，生成是纯规则毫秒级 + 既有仓储写，不新增锁内 AI/网络，符合 C4 口径）。影子合并（写死）：`apply_karma_shadow` 的实际施加清单（其返回值 npc_name 集 + account.shadow_applied 口径）所覆盖的 NPC，origin 选人时**排除**（随机只填未覆盖者）；同 NPC 态度以影子值为准，origin 不对这些人调 shift_attitude。
- 未竟之志头号候选：account.traces[-1].unfinished_prop 非空且其 kind 可重实例化时，本世命题 kind 直接取之（文案沿用未竟文，check 按本世新事实重建：debt_clear 需本世有债、foe_reckoning 需本世有 foe、lost_relic 沿用同一 item_ref、family_revive/stand_firm/sect_inner 直接重建）；不可重实例化（如上世 debt_clear 而本世无债）→ 回退 §3.7 优先级序。**世仇强制植入明确不做**（第二期，§8）：一期转世的 foe 只来自本世新随机 + 影子，不因上世血仇强制塞人。
- 老角色：不追溯补发——origin 恒空、命途行走回退口径（§2.3）、其首次获得出身的时点是**下一次转世**。出身卡、「前世曰」对其同理缺省不渲染。

### 3.11 出身卡呈现（双端第一屏，数据只读下发）

- 下发：`_status_dict` 只增 `origin` 键（值 = char.origin 块原样，无 origin 时为 `null`）；join/reincarnate 响应只增 `origin_card` 键：`{origin: <块>, prev_epitaph: <上一世评语或 "">, just_created: bool}`（join 新号 just_created=true；reincarnate 恒 true；普通登录 resume 时 _status_dict.origin 可读但不弹卡，前端以 just_created 为唯一弹卡依据）。
- 桌面：登录/转世后在入局视图顶部以整卡呈现（家世/旧事/债与关系/路径开关各一行 + 底行终局命题 + prev_epitaph 非空时首行「前世曰：…」）；关闭后收进命盘（sanctum）「出身」折叠段（status.origin 只读渲染），随时可回看。
- 移动：全屏卡（复用 gate 视觉语言与既有 token），呈现内容同桌面；关闭后收进命盘页出身段。
- 前端缺失即不渲染：origin 为 null/缺键时两端都不出现卡与折叠段（老角色零打扰）。

---

## §4 · 件三：仪式演出两幕（方案 §4c 子集，归府流）

### 4.1 总契约（先结算后演出）

- 仪式是响应层只增结构 `ceremony`，**不落库**（待选命格是唯一例外，它是结算的一部分，落角色行，见 §4.2）：

```jsonc
{"kind": "breakthrough|death|rebirth",
 "beats": [{"stage": "prelude|reveal|aftermath", "text": "…", "asset_key": "portraits/male-jindan|null", "choices": null}],
 "result_ref": { /* 已结算结果摘要，与落账逐项对账（C1） */ },
 "skippable": true}
```

- 拼装函数（建议置新模块 `core/ceremony.py`）：纯读已结算数据 + 本地模板，毫秒级；**禁止**在仪式路径调用 `WorldDirector.run_cycle`、任何 `_chat_json`/AI 网关、NPC AI（突破既有的导演触发保持其在 `_breakthrough` 原位，不挪动）。无 Key/断网时 beats 文案全部有本地模板（C3）——本结构本来就零 AI，天然满足。
- 同类仪式自动略过偏好：**只存前端 localStorage**，键名双端统一 `ceremony_skip_<kind>`（值 `"1"`），仪式不落库故偏好不入后端；在仪式卡片页脚提供「同类自动略过」勾选，命盘（桌面 sanctum/移动 ops）提供同键的取消入口。注意：自动略过只跳过**呈现**，命格待选不受影响（§4.2）。

### 4.2 突破幕与命格三选一（状态机定死，口径 K2）

**现状锚点**：`BreakthroughEngine.attempt_breakthrough(character, use_pill, pill_bonus, heart_mod)`（`core/breakthrough.py:19`）是唯一裁决点：小阶（sub_tier<3）返回 `{success, is_major: False, …}`；大境界返回含 `is_major: True`、`new_realm`、`lifespan_gained`、失败档 `fail_tier`/`is_fatal`。服务端两条出口：① `World._breakthrough`（`server/world.py:4767`，sub_tier==3 时先开心魔会话pending，普通路径直调 attempt 并 save、成功后走既有 `GoalEngine.on_breakthrough_major` + 导演触发）；② 心魔后继段（`World.handle` 心魔分支 :1045 一带，过关后直调 attempt 并 save）。心魔数据：`Character.demon_seed/demon_anchor_at`（`core/heart_demon_state.py DemonStateEngine.summary` 可只读取阶段/魔念一句）。CLI 有同名突破路径（双端契约：同一 attempt 出口即同覆盖）。

**命格池（定稿）**：候选 = DAO_BOON_CATALOG 5 键（pure_yang/iron_wall/sword_heart/spirit_well/ice_soul）+ AFFIX_POOL（`core/items.py:129`，5 键破煞/嗜血/凝神/固元/生光，stat_key ∈ pierce/lifesteal/mind_guard/defense/charm）中按灵根首元素过滤的子集。词缀无 element 字段（实测），过滤表在此定稿（按 stat_key 亲和）：金→[破煞， 固元]、木→[生光， 凝神]、水→[凝神， 生光]、火→[嗜血， 破煞]、土→[固元， 凝神]、风→[破煞]、雷→[破煞， 嗜血]、冰→[凝神， 破煞]。命格统一形状：`{key, name, desc, icon, source: "dao"|"affix"}`——dao 键 key/name/icon/desc 直引目录（desc 只作展示文案）；affix 键 key 定为 `fate_<stat_key>`（如 fate_pierce），name=词缀名，desc 直引 AFFIX_POOL desc，icon 定为「✦」。

**命格数值（F5 修正口径）**：config 新增 `FATE_BOON_POWER: Dict[str, float]`（dao 五键 ∈ [1.02, 1.04]：pure_yang 1.03 / iron_wall 1.04 / sword_heart 1.04 / spirit_well 1.02 / ice_soul 1.03；affix 五键恒 1.02）与 `FATE_BOON_POWER_CAP = 1.15`、`FATE_BOON_MAX = 5`。生效点唯一：`CombatEngine.calculate_power` 乘子链尾部以既有 try/except 先例挂 `FateBoonEngine.power_bonus(char)`（建议置 `core/ceremony.py` 或独立小模块）= `min(CAP, Π FATE_BOON_POWER[k] for k in char.fate_boons)`，无命格时恒 1.0（旧行为逐值不变）。

**待选状态机（定死）**：`Character` 新增 `fate_boons: List[Dict] = []`（已选：`{key, name, from_tier, chosen_at}`）与 `fate_pending: List[Dict] = []`（待选抽：`{candidates: [命格形状×3], from_tier, drawn_at}`，FIFO，长度 ≤2）。

- 抽定点：在 `attempt_breakthrough` 大境界**成功**分支返回前（裁决引擎内，唯一漏斗）：若 `len(fate_pending) < 2`，从池中剔除已选 key 后随机抽 3 个不重复候选组成一抽 append；已满 2 抽则不抽（message 尾行注「命格待选已满」）。小阶成功、任何失败：不抽。随机用模块 random（测试以 mock/播种复算候选集 ⊆ 池且 3 个互异即可，不要求复算具体抽序）。
- 选择点（唯一函数，建议名 `apply_fate_choice(char, key) -> dict`）：校验 key ∈ fate_pending[0].candidates（只许取最老一抽，FIFO 写死）且 `len(fate_boons) < FATE_BOON_MAX`；通过则 pop 该抽、append fate_boons、返回成功；否则零副作用失败。调用面三处同函数：① 仪式内选择（前端按钮 → 新命令 `/命格 <key>`，见下）；② 命盘待选区选择（同一命令）；③ CLI 同命令。新命令 `/命格`（别名 `/fate`）：无参 = 查看待选与已选（文本 + status 只增 `fate` 块，前端按钮组由此渲染）；带参 = 选择。命令目录 `core/command_catalog.py` 新增恰此 1 条（99 → 100，B4 的「逐条可达」按 100 条验，见 §7）。
- **跳过等价（C2 对账口径）**：仪式「略过」是纯前端关闭，零请求、零落账；待选抽原样留在角色行。玩家之后在命盘以同一 `/命格` 函数选同一 key，最终角色行除 `chosen_at` 时刻外逐字段相同（对账时 `chosen_at/drawn_at` 两类时间戳字段豁免逐字比对，其余字段——fate_boons 的 key/name/from_tier、fate_pending 余量、realm/lifespan/灵石等全部数值——必须逐字段相等）。仪式里选择与命盘选择走同一命令同一函数，不存在第二条落账路径。
- 累积上限：每抽至多选 1、抽数 ≤ 大境界成功次数（构造性成立），叠加硬顶 `FATE_BOON_MAX=5` 与战力乘子顶 1.15——「总档位随已突破大境界数封顶」的口径即 `len(fate_boons) ≤ 已突破大境界数（= realm.tier − 1 + 已跌境修正不追溯）`，以构造性上限 + 硬顶双保险落字，不另设可回收逻辑；死亡后两字段随旧角消亡（新角默认空），不入 LifeTrace（命格是单世 build，不是跨世资产）。

**突破幕 beats**（挂点：两条服务端出口在既有返回上只增 `ceremony`，条件 = attempt 返回 is_major（成功/失败/致死都演）；小阶不演）：prelude「闭关异象」= 新境界立绘 asset_key（`GALLERY_ASSET_KEYS` 境界键，按 gender/新 tier 取，缺 gender 用既有占位口径）+ 心魔一句（读 `DemonStateEngine.summary` 的阶段/魔念本地拼句，零 AI）；reveal = 成败与 result_ref；成功且本轮有新抽时 beats 尾附 choices（候选 3 个的命格形状）；失败按 fail_tier 给定稿模板句（DEATH/BASE_COLLAPSE/走火/轻伤四档各 1 句，变量只取已结算数值）。result_ref 定稿：`{success, is_major, new_realm, lifespan_gained, fail_tier, fate_drawn: bool, fate_pending_count}`——与 attempt 返回和角色行逐项可对账（C1）。致死时本响应同时带既有 death/legacy/sweep 字段，死亡幕不在此重复（玩家下一步登录/转世走 §4.4）。

### 4.3 天劫口径（一期不立独立幕）

大境界突破中的雷劫段并入突破幕 beats 的 prelude/reveal 文案（劫云模板按目标 tier 取 3 条轮换之一定稿于实现，变量只取境界名），不单独产 `kind: "tribulation"`。此点与方案 §4c 六幕表的差异已在 §0.3 记账（任务边界：只两幕）。

### 4.4 死亡/转世合并幕（归府流）

**死亡幕**挂点：`World.dead_payload` 的**已结算**返回（settled=true 路）只增 `ceremony`（kind=`death`）；锁忙回退路（settlement_pending=true）`ceremony: null`（未结算不得演回望，诚实降级）。拼装数据源（全部已落账）：account.traces[-1]（含 §3.9 新字段）、trace_summary、wallet/settlement 既有字段。beats 定稿：
- prelude「回望」三条（逐条真实记录，缺哪条跳哪条，不得编造）：① fate_summary 原文；② 关系最深者——traces[-1].shadow 按 |value| 首条拼「{npc_name} 与你的前世态度 {value}，恩怨随影入轮回」；③ 最大因果——open_promises 计数与 shadow 条数拼「未了之诺 N 条 · 因果余绪 M 条」（一期无主线/链终局专账，以此二数代之，方案 §4c 的「以出身与目标记录代」口径同此）。
- reveal：死因 + `tombstone_text(trace)` 全文（已含评语行）。
- aftermath「余韵」：死讯传闻已入池的既有事实一句（settle_death 内 rumors truth=1.0 先例）+ life_epitaph 原文再显一次（评语落点②）。
result_ref：`{cause, points_gained, lifespan_lived, life_no, epitaph_present: bool}`，与 trace 逐项对账。

**转世幕**挂点：`World.reincarnate` 返回只增 `ceremony`（kind=`rebirth`）与 §3.11 的 `origin_card`。beats：
- prelude：上一世墓碑尾段 + 「前世曰：{life_epitaph}」（traces[-1]，无则跳过）。
- reveal：影子预览 = 既有返回 `karma_shadow` 清单原文拼句；继承抉择结果 = `boosts_applied` 与道统余点（抉择**入口**仍是既有 dead 面板对 boosts 的选择与 reincarnate 请求参数，仪式只呈现其已结算结果，不新增二次确认接口——「在仪式流内完成」的落法是：dead_payload 的 legacy.boosts 选择 → /转世 → 本幕 reveal 呈现抉择生效全貌，属同一归府流）。
- aftermath：新角出身卡摘要（family_text + 命题一行，与 §3.11 共用 origin_card 数据）。
result_ref：`{name, realm, legacy_points, boosts_applied, shadow_count, origin_signature}`。

### 4.5 前端呈现

桌面：弹窗沿既有 omenModal/jade dialog 先例的全屏卡；移动：全屏卡。两端只认 `ceremony` 结构渲染（kind/beats/result_ref/skippable），beats 按 stage 顺序逐段呈现（节奏在前端，后端只给结构）；「略过」按钮恒在；命格 choices 按钮发 `/命格 <key>` 命令（既有 /action 通道），成功后以返回 status 刷新命盘待选区。仪式状态不落库：关页面 = 跳过，后果为零（结果已落账；命格待选已落盘）。

---

## §5 · 件四：关系可见化（方案 §4d 子集）

### 5.1 现状锚点（实测，见 F4）

`core/npc_mind.py:86 shift_attitude(npc, other_id, delta, reason="")`：`ensure_mind` → 读现值 cur → `NpcMindRepository.set_attitude` 写新值并返回 `{value, label, …}` → reason 非空时 `record_event(type="ATTITUDE", actor=npc, summary=…, effects_digest=f"attitude {cur}->{new_v}", location=npc.location)`（**不带 target**）→ 尾部挂因果链 S1 跨阈钩子（reason 以「因果链」开头者跳过防自激，异常不炸主流程）。标签口径：`ATTITUDE_LABELS`（hostile 仇视/wary 戒备/neutral 中立/friendly 友善/ally 亲近），阈值与 `core/inheritance.py label_for_value` 同源（≤−40 hostile / ≤−15 wary / ≥40 ally / ≥15 friendly）。

### 5.2 RELATION 留痕（写入口与形状定死）

在 `shift_attitude` 内、既有 ATTITUDE 写入**之后**、S1 钩子**之前**，新增 RELATION 写入（try/except 包裹，失败不炸主流程，与 S1 同纪律）：

- 触发条件（写死）：`delta != 0` 且（新值 != cur 或 label 变化）——纯 0 移位（如 proactive 的 delta=0 开场）不留痕，防近 5 条被寒暄刷屏。reason 为空时也留痕（summary 用「无名由」兜底句），因为可见化不能有盲区。
- 写入口：`core/memory.py record_event(type="RELATION", actor=npc, target=<other 活对象>, summary=…, effects_digest=…, refs=[…])`；other 活对象以 `CharacterRepository.get_by_id(other_id)` best-effort 解析，解析失败则改直调 `EventLedgerRepository.append` 以 target_id=other_id、target_name="" 落行（保证 target 索引可查，§2/§5.3 的查询都按 target_id 走）。
- 形状（F4 的载体裁定）：`summary` 定稿模板 `「{npc.name}对你{由中立转友善|态度升温|态度降温}：{reason 或 '无名由'}」`（转档时用「由{before_cn}转{after_cn}」，未转档用升温/降温）；`effects_digest = f"attitude {cur}->{new_v} ({delta:+d})"`（≤120 字天然满足）；`refs` 定稿四串：`["delta:{delta}", "before:{before_label}", "after:{after_label}", "reason:{reason}"]`（label 为英文键）；location=npc.location。
- origin 初始关系经 §3.6 的 shift 调用自动落痕（reason=`origin` 在 refs 与 summary 中可查）——这是 D1 一期口径的组成部分，不另设生成器侧留痕。
- 影子施加（apply_karma_shadow 直调 set_attitude）**不**经本钩子、一期不补留痕（§8 明列）；其可见性由既有 karma_shadow 展示承担。

### 5.3 下发（_status_dict 只增两键）

`World._status_dict` 只增：
- `relations_recent`：近 5 条 RELATION，数据源为 EventLedger 新查询（建议名 `EventLedgerRepository.query_by_type_for_target(target_id, type="RELATION", limit=30)`，走既有 `idx_ev_target` 索引、ts 倒序）；每项形状 `{npc_id, npc_name, delta, before_label, after_label, before_cn, after_cn, reason, summary, ts}`（label 解析自 refs，cn 由 `ATTITUDE_LABELS` 映射，解析失败的旧/脏行跳过不报错）。取 30 条是为同出 marks（下条），recent 取其前 5。
- `relations_marks`：同一批 30 条里按 actor（NPC）取**首现**（即最近一次）拼 `{npc_id: {delta, ts}}`，供同场箭头 join（前端以 NPC id 对齐其既有同场列表项 id——`core/here.py list_here` 项本就带 id/attitude/attitude_value；对齐失败时以 npc_name 兜底匹配）。
无任何 RELATION 时两键分别为空数组/空对象（不省略键，前端判定简单）。

### 5.4 前端呈现（双端两处）

- 命盘「关系动态」：桌面 sanctum 社交段、移动命盘社交卡各增一段，渲染 `relations_recent` 近 5 条（方向箭头按 delta 符号、文案用 summary、标签用 after_cn），无数据时整段不渲染。
- 同场近变箭头：桌面同场抽屉 NPC 项、移动 world 分区 NPC 子卡的 attitude pill 旁，按 `relations_marks[npc_id].delta` 显示 ↑（正）/↓（负）+ 幅度；marks 无该 NPC 时不显示箭头。箭头与命盘必须同源一致（同一 status 响应内的两键，D1 断言点）。
- 不做：交谈弹窗旧账行、主动戏剧（§8）。

---

## §6 · 通用约束（四件共守）

- **只增字段总表**（实现岗不得改/删任何既有键）：登录响应 +`entry`（回退 +`entry:null, entry_pending:true`）；dead_payload +`ceremony`（回退路为 null）；join/reincarnate 响应 +`origin_card`；reincarnate 响应 +`ceremony`；突破两出口响应 +`ceremony`；`/命格` 响应 +`fate`（亦进 _status_dict）；`briefing()` 返回 +`entry`；`_status_dict` +`origin`/`fate`/`relations_recent`/`relations_marks`；`trace_summary` +4 键（§3.9）。
- **新模型字段总表**（全部带默认值、旧档零迁移）：`Character.origin/fate_boons/fate_pending`（origin 块内只增键含 `fate_kind`：生成器写入本世终局命题 kind、供 `core/legacy.py` 命题映射读取，评审后补记账）、`LifeTrace.fate_summary/life_epitaph/origin_signature/unfinished_prop`、`Promise.paid`；config 新增 `ORIGIN_SECT_FAVORED_DAO_WAIVER=10`、`FATE_BOON_POWER`、`FATE_BOON_POWER_CAP=1.15`、`FATE_BOON_MAX=5`；`PROMISE_KINDS` 新增 `debt`；命令目录新增 `/命格` 1 条。
- **锁与耗时**：新增拼装全部在锁外（join 锁外段、briefing 端点、handle 既有返回组装点）或 reincarnate 既有持锁段内的纯本地计算（origin 生成，毫秒级，既有仓储写）；仪式拼装零 IO 阻塞等待、零 AI；入口拼装的仓储读均为按 player/按 target 索引查询 + WorldState 单键读。
- **AI 口径**：四件中 AI 参与度为零（origin/评语/仪式/留痕全本地模板与规则）；唯一例外是 §2.4 的 maybe_engage 既有预算闸补触发。无 Key 环境下四件全功能可用（验收含无 Key 复测项）。
- **道体守恒**：origin 生成涉及的写路径以 `CharacterRepository.save` 收尾（灵石赋值走建角发放口径的绝对值设定，不经增减通道、不产生负数）；命格选择不涉灵石/背包；`attempt_breakthrough` 本体数值零改动（只在其成功分支尾部追加抽定与字段写，随调用方既有 save 落盘）。

---

## §7 · Acceptance（逐条编号；每条标注方案验收编号）

记法：等为方案原编号；「一期部分」按任务边界裁剪的范围以本条文字为准。

### 7.1 件一 · 入口

- **P1-01（方案 B1）** 离线事件三连：人为让一条因果链到期、一条诺言到期（ACTIVE debt/普通诺过期）、一场世界弧升级后登录——登录响应 `entry.lines` 三线俱在（chains/relations/fate 非空口径按构造事实断言），`entry.queue` 含 `karma_resolved` 项且其 target 一键可达 `/因果链`（前端点击实际发出该命令、面板打开）。
- **P1-02（方案 B1）** 诺言与奇遇项：构造 settle_due 实际翻转一条诺言、挂一场未散场奇遇（omen_scene）后登录，queue 分别含 `promise_settled`、`omen_active` 两项，priority 序符合 §2.3 表（karma < promise < goal_flip < maturing < omen < visit < opportunity < world）。
- **P1-03（方案 B2）** 登录耗时分两层测（测法写死，见 §9.2）：(a) 拼装层——以 `allow_proactive=False` 对同一角色连测 20 次 `build_entry`，单次耗时与同机 `briefing()` 基线同量级（中位数 ≤ 基线 3 倍且绝对值 < 200ms，NAS 等级机器放宽至 < 500ms，报告须注明机器）；(b) 链路层——proactive 预冷（先登录一次吃满其 90 秒冷却）后连测 10 次 /login 全链路，中位数不劣于 v0.3.7 同法基线的 1.5 倍；且以静态检索证明拼装路径无 `list_all` 新增调用、无 AI 网关调用（maybe_engage 内部除外）。
- **P1-04（方案 B3）** 队列纪律：构造 5+ 件可入队事项登录，`highlight` 恒 ≤3、`rest_count == len(queue) − 3`、排序合 priority 表；清空全部事项后登录，`entry.empty == true`、queue 为空、双端入局层实际显示「江湖无事，可自由行动」。
- **P1-05（方案 B4）** 工具层零阉割：命令目录全量（99 既有 + 新增 `/命格` = 100 条）逐条可达性回归通过（沿既有命令目录/冒烟测试口径）；桌面 6 个既有视图与移动 5 分区逐个打开行为与基线一致（截图清单 §7.6 对照）；`/世情`、敕令栏、工作台全景入口仍在且语义未变。
- **P1-06（方案 B4 / §2 回退口径）** 回退与降级：世界锁繁忙时 /login 返回既有回退快照且 `entry == null && entry_pending == true`、无 token 谎报；`build_entry` 单数据源人为抛错时 entry 其余部分照常生成、登录不失败。

### 7.2 件二 · 人生开局（A6–A9 一期口径）

- **P2-01（方案 A6）** 落账对账：播种 rng 生成 20 个新角，逐角核对四处——角色行灵石 == origin.stones_final；PromiseRepository 中 debt 诺（若有）promisee/param/deadline 与 origin.debt 一致；每名 relations 的态度账现值 == init_value（经 `attitude_toward` 读）；path_gates 中 sect/closed 在 `evaluate_join` 实际拒止、sect/favored 的道心判定按 −10 生效、vendor 两态在专柜实际成交价上体现既有折扣/加价倍率。
- **P2-02（方案 A6）** bounds 与死局：离线批量生成 200 个出身包（不起服务、直调生成器于模拟角色）——200 包全部满足：灵石 ∈[80,260]、债 ∈[0,120] 且债主在世、foe tier ≤ 起始 tier+1、kin/foe/witness 值域合规、relations ≤4、closed ≤1、strength_score ∈[−20,20]；死局样本为 0（断言口径：每包至少一名可交易 NPC 非 foe 档、商会基础交易可达、闭关/迁跃判定不引用 origin）。
- **P2-03（方案 A6 / A9 防重部分）** 防重：同一账户模拟连续 5 世生成，origin_signature 两两不同（dedup_exhausted 的包除外且须有标记）；生成器同 rng 播种两次产出逐字段相同（可复算）。
- **P2-04（方案 A7（一期部分））** 判定式复算：构造短期 4 族各 1 例 + 命题 6 类各 1 例，用既有账数据离线重算 done/pending 与线上求值器（E1/E6 点）结果逐个一致；无 Key 环境复测一遍结论不变。
- **P2-05（方案 A7（一期部分））** 到期转未竟之志：把一条短期目标 deadline 拨到过去，求值后 status=failed；角色死亡结算后，LifeTrace.unfinished_prop 与该目标（或命题目标，若其 failed/未结）对应、fate_summary 含「未竟之志」句；origin 短期目标被玩家 reject 时不入未竟（负例断言）。
- **P2-06（方案 A8（评语部分））** 评语生成与三落点：角色死亡后同一 trace 同时含非空 fate_summary、life_epitaph、origin_signature（有 origin 者）；`/墓碑` 文本含「一生评语：」行；dead_payload 的 ceremony（kind=death）aftermath 含评语原文；转世后新角 origin_card.prev_epitaph == 上一世 life_epitaph 且出身卡实际渲染「前世曰」行（双端截图 §7.6）。
- **P2-07（方案 A8）** 未竟之志头号候选：上世留 debt_clear 类未竟、本世生成有债时，新世命题 kind == debt_clear 且 check.ref 指向**本世新债**（非旧 id）；上世未竟为 foe_reckoning 而本世无 foe 时回退优先级序且 origin 块可查命题来源（负例）。
- **P2-08（方案 A9）** 两出身对照：按方案 §5 对照走法构造「药农欠债」与「罪族带仇」两包（播种 rng 定向），两名新角前 30 分钟流程内：可达宗门集合（evaluate_join 逐宗门判定）、首笔专柜成交价、出生地、首个短期目标 check 四项中至少三项实际不同（逐项列证据，不许只比文案）。
- **P2-09（§3.10 时机口径）** 时机与不追溯：老角色（origin 为空）在本轮上线后登录，origin 仍为空、命途行走回退文案；其转世后新角首次获得 origin；注册新号在 join 返回时 origin 已落盘（响应 origin_card.just_created == true）。

### 7.3 件三 · 仪式两幕（C1–C4 子集）

- **P3-01（方案 C1（突破幕））** 构造大境界突破成功/失败各一次：响应含 ceremony（kind=breakthrough、三段齐全），result_ref 与 attempt_breakthrough 返回及角色行逐项一致（success/new_realm/lifespan_gained/fail_tier）；成功时 fate_pending 新增一抽（3 候选互异、⊆ §4.2 池、剔除已选 key）。
- **P3-02（方案 C1（死亡/转世幕））** 构造死亡→登录（dead_payload ceremony=death，result_ref 与 traces[-1] 对账）→转世（ceremony=rebirth，shadow_count 与 karma_shadow 长度一致、origin_signature 与新角 origin.signature 一致）全链各一次；锁忙回退的 dead_payload ceremony == null（负例）。
- **P3-03（方案 C2（突破幕））** 跳过等价：同一播种角色两路对照——甲看完仪式并在仪式内以 `/命格 <key>` 选择，乙点略过后在命盘以 `/命格 <key>` 选同一 key；两路最终角色行逐字段相同（chosen_at/drawn_at 时间戳豁免，口径见 §4.2）；仪式呈现本身不发任何写请求（网络层断言：略过路径零 /action 写调用）。
- **P3-04（方案 C2（死亡/转世幕））** 略过死亡/转世仪式与看完两路对照：道统点、钱包 sweep、traces、影子施加结果逐字段相同（仪式纯呈现的构造性断言 + 实际对照跑一遍）。
- **P3-05（方案 C3）** 无 Key/断网环境：突破成功、突破致死、死亡、转世四场仪式文案全部有本地模板、无空白幕、无报错；命格候选 name/desc 非空（dao 引目录、affix 引 AFFIX_POOL）。
- **P3-06（方案 C4）** 仪式路径零 AI/零锁内耗时：静态检索证明 ceremony 拼装模块不引用 ai 网关与 WorldDirector.run_cycle；请求耗时日志核对——带 ceremony 的 /突破、/login（dead）响应耗时与 v0.3.7 同法基线同量级（中位数劣化 < 20%）；calculate_power 在无命格角色上与基线逐值相同（旧数值零漂移），有命格时乘子 == config 表连乘并被 1.15 截断（边界用例）。

### 7.4 件四 · 关系可见化（D1 一期部分）

- **P4-01（方案 D1（一期部分））** 跨阈留痕：构造赠礼使某 NPC 对玩家态度跨 friendly 阈、构造结仇跨 hostile 阈各一次——EventLedger 各新增一条 type=RELATION 行，refs 中 delta/before/after 与态度账前后值逐项一致；同两条在 _status_dict.relations_recent 中可查（近 5 内）。
- **P4-02（方案 D1（一期部分））** 双端一致：同一 status 响应下，命盘「关系动态」首条与同场列表该 NPC 的箭头方向/幅度一致（relations_recent 与 relations_marks 同源断言 + 双端截图）；delta=0 的 proactive 开场不产生 RELATION 行（负例）。
- **P4-03（方案 D1（origin 留痕并入））** 新角生成后逐名 relations 查 RELATION 行：reason=origin、after 值 == init_value、条数 == relations 人数；影子施加的态度变化**不**产生 RELATION 行（一期口径负例，与 §5.2 一致）。

### 7.5 回归口径（写死）

- **P5-01（回归口径）** 全量回归基线 = v0.3.7 发布实测，且已由本 Spec 定稿时在本 worktree（基线 `90ce9c8`，`.venv` 全量 `pytest tests/ -q`，2026-11-08，耗时 1114s）逐字复现：**1179 passed / 9 failed**。9 条逐条列名，并已逐条单跑复验定性（单跑 2 passed / 7 failed，与发布口径「7 有效 + 2 flaky」严丝合缝）：
  - **有效基线失败 7 条**（单跑复验仍红，本轮不得新增、亦不要求修复，但若因本轮改动面扩大须逐条归因）：① `tests/test_auth_hardening.py::test_world_join_requires_explicit_nonempty_authenticated_uid`；② `tests/test_karma_chains.py::test_kill_and_bounty_single_chain`；③ `tests/test_natural_omen.py::test_initial_character_and_config`（建角自带藏宝图断言，clock 建角处的合并裁定已知牺牲项）；④ `tests/test_qa_account_death_acceptance.py::test_qa2_join_dead_http_and_anonymous_unchanged`；⑤ `tests/test_status_dict_gray.py::test_status_dict_includes_bag_and_marks`；⑥ `tests/test_status_dict_gray.py::test_status_dict_follows_real_equip_flow`；⑦ `tests/test_workbench_api.py::test_login_then_look_here`。
  - **已知 flaky 2 条**（全量红、单跑复验绿）：⑧ `tests/test_farm.py::test_settle_meditation_cave_bonus_and_chain`；⑨ `tests/test_world_director.py::test_local_director_run_persists_and_channel`。
  - 执行口径：交付时全量失败集 ⊆（上述 7 条 ∪ 上述 2 条 flaky）即视为不新增失败；基线内的条目在本轮转绿不算功劳、转红的非基线条目逐条归因；flaky 在交付跑中出现时须单跑复验并注明结果，不得静默放过。
- **P5-02（回归口径）** 本轮交付时全量重跑：新增失败（P5-01 执行基线之外、且非已知 flaky 的复跑可绿者）必须为 0；已知 flaky 须单跑复验并在报告中逐条注明复跑结果，不得静默放过。
- **总管裁决（2026-11-08 · r9 契约冲突）**：`tests/test_reincarnation_inheritance.py::test_r9_server_integration` 在本分支失败（shadow_count 期望 1、实际 4），根因为契约冲突而非实现缺陷：出身初始关系是经 `shift_attitude` 落入态度账的真实态度，死亡结算时按 v0.3.0 既有继承规则（|v|≥30、top 6）合法结转入影——此行为与方案 §4a 的设计意图一致（影子是下一世主线的一号种子来源；本 Spec §4.4 死亡幕回望亦以 trace.shadow 含出身关系为前提）。裁决：**接受新契约「出身恩怨随影入轮回」**，r9 的 `==1` 断言编码的是前出身世界假设，由 QA 岗按新契约修订该断言（修订口径：期望影子集合应由结算时态度账按既有继承规则推导，不得硬编码计数、不得削弱对影子衰减值与对象的校验）；修订后 r9 转绿即销账，本项不计新增失败。不取「出身关系排除出影子」（与方案种子优先级冲突）与「压低出身值域」（与 §3.6 写死值域冲突）两案。
- **总管裁决（2026-11-08 · 全量 6 条基线外失败归因）**：QA 全量（1204 passed / 13 failed）中 6 条不在 P5-01 基线名单内，经归因岗逐条亲跑定性（分支单跑 + 基线 `90ce9c8` 单跑对照 + DB 终态核查，日志 `/tmp/attrib-logs/`），**6 条全部为甲类合法契约变更**，根因统一为出身生成器（`ac5f46d`/`b99ddda`）推翻方案 §8 明文废止的「白纸开局」旧假设，无一实现缺陷，与评审 MF-1 无关：① `test_account_death.py::test_web_login_dead_no_auto_rebirth_and_explicit_reincarnate` 与 ② `test_account_death.py::test_cli_death_settlement_and_rebirth_guidance`、⑤ `test_qa_account_death_acceptance.py::test_qa5_dual_end_wallet_and_login_reincarnate`、⑥ `test_qa_account_death_acceptance.py::test_qa6_legacy_ascension_new_birth_unchanged`——新角灵石断言 `==150` 被 §3.5/§3.10 新契约取代，实测四角灵石均与各自 `origin.stones_final` 逐字相等且 ∈[80,260]（A6 对账成立）；③ `test_farm.py::test_world_handle_meditation_gate`——出生地落点新契约（§3.3/§3.6），约 21% 概率落「落霞山灵泉」非安全地使 `/开辟` 被既有门禁拒（分支 8 跑 2 红、红因由角色行 origin 字段完全解释，非状态敏感）；④ `test_qa2_dual_end.py::test_promise_server_make_engine_fulfil_once`——双通道同根因：出身债诺占 `PROMISE_MAX_OPEN` 1 额度（§3.5 明示，DB 实证 debt 条）+ 出生地使立诺异地被既有同场门禁拒。裁决：**接受新契约**，由 QA 岗按归因报告口径修订断言/夹具（灵石期望一律由 `new.origin["stones_final"]` 推导并补 bounds 断言，连带下游推导值同步改；「钱包不自动划转」意图由钱包余额断言独立承载不得删；③ 修订夹具先迁安全地、门禁断言不动；④ 同场化夹具 + plist 按 `kind=="arrive"` 过滤断言、尾段 KEPT 查过滤后条目）；修订复跑转绿即销账，不计新增失败。附带乙类轻微项：`server/world.py` 转世返回文案仍写死「新角随身 150 灵石不变」，与实际到账不符——派后端返工岗改为动态实际值（CLI 侧已动态化为口径参照），QA 随之收紧 ⑤ 的文案断言为实际 `stones_final` 值；该文案项非阻塞但须随本轮返工一并交付。
- **评审 must-fix 返工单（2026-11-08 · 总管批准）**：评审岗 3 条 must-fix 全部成立，派后端返工：**MF-1** 入局拼装陈旧覆写——`build_entry` 内 `KarmaChainEngine.advance_for` 以另一实例自读自存兑现落账，join 末尾以拼装前对象整行无条件回存（`CharacterRepository.save` 无版本校验）致兑现的灵石/修为/功德被静默回滚且链已终态永不重发；修法口径：② 后 ③ 前重读角色行继续拼装与回存，或回存时仅合并增量到最新行，修复后以「链到期 + 诺言到期同登录」构造做落账对账复验（V-1/P1-01）。**MF-2** 仪式命格 choices 错位——`core/ceremony.py` 呈现 `pending[-1]` 候选而唯一选择函数 `apply_fate_choice` 只认 `pending[0]`（FIFO 写死不改），已有一抽未选时再突破仪式内选择 100% 被拒；修法：仪式改呈现 `pending[0]` 并明示尚有新抽待选，补「已有一抽未选 + 再突破」对照（V-5/P3-03）。**MF-3** 未竟之志 kind 映射缺失——`core/legacy.py _prop_kind` 仅对 fate 源做 check→命题 kind 映射，origin 源 failed 短期目标的未竟 kind 为判定式原名，`select_fate_proposition` 未竟分支永不命中；修法：origin 源复用同一映射表（promise_settled→debt_clear、npc_attitude_at_least→foe_reckoning、item 类→lost_relic、stones_at_least→family_revive、sect_joined→sect_inner、realm_at_least→stand_firm），补 P2-07 型正/负例。顺带批准：**S-2** 后端侧把 `entry.proactive` 由 list 改为单对象 `{text, npc}`（无来访时为 null），与双端前端既有取值口径（string 或 `{text}`）对齐，前端零改动；**S-1** `breakthrough.py` 注释与代码不符仅改注释。评审其余建议 S-3/S-4/S-6/S-7 只记录不修。另补记账：`origin.fate_kind` 为 origin 块内只增键（生成器写入、供 legacy 命题映射读取），列入下行新字段总表。
- **总管裁决（2026-11-08 · farm_chain 同根补裁）**：最终全量（HEAD `0f206b2`，新鲜 DB，1217 passed / 8 failed）名单外 1 条 `tests/test_farm.py::test_world_handle_farm_chain`，经 QA 单跑 7 次（4 绿 3 红）定性：3 红全部由新角出生地落「落霞山灵泉」（非安全地）使 `/开辟` 被既有安全地门禁拒、角色行 `origin.birthplace` 完全解释，与上条裁决 #3（`test_world_handle_meditation_gate`）同根同源——出身出生地新契约（§3.3/§3.6）的甲类夹具问题，非实现缺陷；其全量内失败点为已过 `/开辟` 后 `/播种` 的瞬态 sqlite 锁争用（非断言失败，与本定性无关）。裁决：**接受新契约，按 #3 同式修订该夹具**（join 后直设 `char.location = "青云坊市客栈"` 再 save，链路断言一字不动），连跑 3 次全绿即销账，不计新增失败。至此最终全量失败集 = 7 条有效基线逐字对应，2 条已知 flaky 本轮全绿，交付口径（P5-01/P5-02）达标。
- **P5-03（回归口径）** 既有契约不回退专项：`tests/test_login_latency_fix.py`（登录去锁化）、`tests/test_mobile_web.py`（含预算断言——若 §9.1 豁免获总管批准，断言按新上限同步修订并注明出处，未批不得改）、`tests/test_gallery_frontend_contract.py`、`tests/test_reincarnation_inheritance.py`、`tests/test_promises.py`、`tests/test_karma_chains.py` 五组定向套件全绿（基线内既有失败除外并逐条注明）。

### 7.6 截图验收清单（双端，实现岗交付时随附）

桌面（web/index.html + workbench.js）：S-D1 登录后入局默认层（三线 + 队列 ≤3 高亮 + 折叠计数）；S-D2 「江湖无事」空队列态；S-D3 新号出身卡整卡（含前世曰行，转世样本）；S-D4 命盘出身折叠段 + 命格待选区；S-D5 突破仪式三段（成功含三选一）；S-D6 死亡仪式回望→墓碑→余韵；S-D7 命盘关系动态近 5 条 + 同场抽屉箭头同屏对照。
移动（web/mobile.html + mobile.js）：S-M1 feed 置顶入局卡 + 默认落点；S-M2 出身卡全屏；S-M3 突破仪式全屏卡；S-M4 命盘关系动态段；S-M5 world 分区 NPC 子卡近变箭头；S-M6 转世仪式 aftermath 的新角出身摘要。
每张截图须对应一条上文验收编号，缺图即该条未验。

---

## §8 · Out of Scope（逐项点名，本轮不做、不顺手做）

1. `fate_threads` 表与 `core/fate_thread.py`、命途主线章节本体（立命/经营/冲突/高潮/暮年章状态机）、导演提名生成章节、中期目标与章节的完整绑定。
2. 世仇家系强制植入新出身初始关系（第二期；一期 foe 只来自新随机 + 影子合并）。
3. 出身包收编进 FateThread.origin（第二期随主线同批）。
4. 主动戏剧五类（求助/示好/挑衅/背叛/牵连）与传闻玩家事迹写入口（§4d 其余部分）；交谈弹窗「旧账」行。
5. 得宝幕、器灵认主幕、天劫独立幕（第三期）；仪式文案与出身文案、评语的 AI 润色（评语一期纯模板）。
6. v0.3.7 复审建议项 **S-1～S-7 本轮全部不处理**，逐项点名（出处：`~/workspace/reviews/gallery-gameplay-rereview-20261107.md`）：S-1 /assets 路径拼装注释与字面口径；S-2 寻宝链买路成本被单链惩罚顶截断的一致性；S-3 寻宝链修为日顶在修为已满时虚耗；S-4 奇遇频控时钟不可注入 now；S-5 event_chains 配图未透出呈现层；S-6 移动端行囊以名字含「图」误判宝图的呈现噪声；S-7 §15 预算增量基准措辞。另：桌面命盘 `[object Object]` 观察项（v0.3.7 交付时一处未深究的显示异常）本轮不处理、不顺手修。
7. 图库扩图（约 140 张）与 NPC 单人图/高境界立绘补齐（并行线，不属本轮）；品阶命名统一；命令目录既有缺项补齐（/议政 /典当等）。
8. 影子施加路径（apply_karma_shadow）的 RELATION 留痕补齐；`shift_attitude` 既有 ATTITUDE 行的存量数据迁移/清理。
9. place 类路径开关的 closed 形态（F6，无既有门槛可挂，第二期若立旅行门槛再议）。

---

## §9 · 风险与预算

### 9.1 移动端预算实测与豁免申请（口径 K4）

实测（本 Spec 定稿时，worktree 基线 90ce9c8）：`web/mobile.css` = **25566B**，现行上限 25702B（gallery-gameplay §15 第二次豁免），**余量 136B**；`web/mobile.js` = **1358 行**，现行断言口径为「文件行数 − 1172 ≤ 190」即上限 1362 行，**余量 4 行**；`web/mobile.html` 余量未测满（feed pane 增一个置顶容器约 +2 行，在其 +60 行口径内，不申请）。本轮移动端新增面：入局置顶卡渲染、出身全屏卡、仪式全屏卡（与桌面共用结构、移动单独渲染函数）、命盘关系动态段、world 子卡箭头——保守估算 JS +180~220 行、CSS（全 token 化）+1300~1700B，余量必然击穿。

**豁免申请（须总管批准后实现岗才可动 mobile 文件，批准记录回填本节）**：`mobile.css` 上限 25702B → **27400B**（+1698B）；`mobile.js` 净增上限 190 行 → **390 行**（即文件 ≤1562 行，+200 行）。token 纪律（no_bare_hex）**不在豁免内**，新增 CSS 必须全量 var() 引用（昼夜双 token 表）。桌面端 workbench.js/css 无行数/字节预算约束（仓内现状），但只许增量追加，不许重构既有渲染函数。

**总管批准记录（2026-11-08）**：批准上述豁免——mobile.css 上限 27400B、mobile.js 文件 ≤1562 行，自本记录起生效；前端岗可据此同步修订 `tests/test_mobile_web.py` 的预算断言（断言处须注明出处为本节）。token 纪律不豁免照旧。另总管确认接受本 Spec 的两处对方案字面的施工修正并记账：F5（命格数值改挂 `calculate_power` 乘子链 + `FATE_BOON_POWER` config 表，理由为局内会话生效点结构上无法承载跨会话命格；数值小额、封顶 1.15、P3-06 守无命格零漂移）与新增命令 `/命格` 1 条（命格待选在仪式外可达的必需接口，B4 按 100 条验收）。

### 9.2 登录耗时 B2 的测法（与 P1-03 对应，写死防口径漂移）

基线与本轮必须同机、同法、同角色状态各测一遍并留原始输出：① 拼装层——脚本直调 `build_entry(char, since, allow_proactive=False)` 与 `briefing(char)` 各 20 次取中位数；② 链路层——服务起于测试 GAME_ENV，先以同账号登录一次（吃掉 proactive 90 秒冷却与 first-night 等一次性项），再连测 10 次 /login 取中位数比对。通过线见 P1-03。禁止用「tick 锁忙时段的单次最大值」冒充中位数劣化（v0.3.5 已证锁忙走回退快照口径，回退路 entry 为 null 不拼装）。

### 9.3 其余风险与兜底

| 风险 | 兜底（已写入设计何处） |
|---|---|
| origin 生成在 join 锁外段失败拖垮建角 | 生成全程 try/except、失败留空 origin 照常建角（§3.10）；reincarnate 内生成失败同理不阻断转世 |
| checked 目标与 ensure_goals 的上限/过期互踩 | 两源豁免口径写死四点契约（§3.7），回归专项含 goals 既有测试 |
| 债务诺占用 PROMISE_MAX_OPEN 引玩家误解 | 出身卡与诺言面板文案明示旧债占一条未结诺；生成时新角未结诺恒 0，无冲突 |
| fate_pending 在 attempt_breakthrough 内的新增写入影响既有突破测试断言（返回 dict/角色行逐字段比对类） | 抽定只写两个新字段、不改 attempt 任何既有返回键与数值；逐字段快照类测试若命中，按「只增字段」惯例更新断言并逐条在实现报告列明，不得削弱数值断言 |
| RELATION 写放大（shift_attitude 高频调用） | delta=0/无变化不写（§5.2）；新增为每次数值变化 +1 行 SQLite 插入，与既有 ATTITUDE 行同量级 |
| 200 包批量生成验收到 ROSTER 播种依赖 | A6 批量验收在已播种花名册的测试 DB 上直调生成器，不依赖服务进程 |

---
