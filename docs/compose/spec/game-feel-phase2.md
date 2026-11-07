# Spec：游戏感改造第二期（game-feel-phase2）

- 基线：worktree `.worktrees/game-feel-phase2`，分支 `feat/game-feel-phase2`，基线 main `c4c4571` = v0.3.8-gray.15（一期已合入并发版）。
- 状态：**待实现**（本文件为唯一产出；本轮不写任何业务代码）。
- 定稿依据：`~/workspace/天道因果录-游戏感改造方案.md`（下称「方案」）§4a、§4d、§7 第二期、§9 已定口径；`docs/compose/spec/game-feel-phase1.md`（下称「一期 Spec」）全部裁决记录；`~/workspace/天道因果录-内容与玩法盘点.md`（下称「盘点」）第三节。**口径冲突时以方案为准；方案与代码现状冲突时按 §0.2 的实测口径施工并逐条记账。**
- 红线（全 Spec 通用，沿一期）：寿元是硬通货（规则一字不改）、规则引擎裁决数值、LLM 只叙事/言行；登录路径零新增 AI 调用（唯一例外仍是方案明列的 `NpcProactiveEngine.maybe_engage` 既有预算闸）；零新增 tick 扫描；涉及角色数据遵循 `AGENTS.md` 道体合规守恒律（写路径统一 `CharacterRepository.save`）。
- 本轮两条线（定死，不扩不缩）：**线一**＝命途主线全量（§2–§8：S-4 收紧前置、fate_threads 状态机、世仇强制植入、NPC 主动戏剧五类、传闻写入口补全、一生评语 AI 润色可选路径、呈现契约）；**线二**＝图库扩充至 139 张（§9）。Out of Scope 见 §13。

---

## §0 · 五步推演结论摘要（requirement-evaluator）与代码事实纠正

### 0.1 五步推演（方案已定稿、Martinez 已全权授权；本推演只收敛派生口径，不重开方向）

**第一步 · 解构本质。** 表层需求是「建主线状态机 + 扩戏剧 + 扩图」；本质是把方案 §1.2 的后两条标准补齐：一世有头有尾（立命→经营→冲突→高潮→暮年，结局写进墓碑且两世不雷同）、NPC 会找上门把旧账演出来、世界记得玩家的事（传闻入池可被引用）；图库线则是给第二期戏剧与既有仪式补「脸」——NPC 单人图优先于一切。验收本质不是「多了张表/多了百张图」，而是：主线模块自身零数值（A5 对账）、判定式可离线复算（A7 全量）、世仇三处一致（§4）、戏剧零数值发放（D 系列对账）、资产三方一致（37 uid ↔ 37 键 ↔ 37 文件）。

**第二步 · 可行性评估。** 可行，但落点与方案/任务简报的文字描述有 10 处偏差（§0.2），全部按实测改口径后才可施工。成本画像：新表 1 张（`fate_threads`，照 `karma_chains` 仓储先例）；新模块 1 个（`core/fate_thread.py`，含世仇选人与主线引擎）；既有模块扩展 8 处（`core/goals.py` 幂等键+新 kind、`core/origin.py` 世仇 foe 入参、`core/legacy.py` 评语分段字段与 thread 封存分支、`core/briefing.py` 入局主线/戏剧指针、`core/npc_proactive.py` 戏剧层、`core/rumors.py` 写入口、`core/gallery_assets.py`/`core/gallery.py` 资产键与图鉴、`server/app.py` 托管正则闸）；新命令恰 2 条（`/命途`、`/回应`，见 §8.4）；`LifeTrace` 新增 4 个带默认值字段（评语分段三段 + polish 状态，§7）；移动端预算必然击穿，豁免申请见 §10（**未批准前实现岗不得动 mobile 文件**）。

**第三步 · 不足与盲区（均已在设计中堵住，标注落点）。**
1. 一期 S-4 遗留：`add_checked_goal` 幂等键太粗（source+kind+ref），中期目标同 kind+ref 不同章节必撞车 → §2 前置收紧，且必须先于任何 thread 目标落码。
2. `_status_dict` 的 `fate` 键已被一期命格占用（`core/ceremony.py fate_block`：boons/pending/power_bonus）→ 主线全量结构不能另起顶层 `fate`，§8.1 定为 `fate.thread` 子键只增。
3. `/assets/` 托管正则闸只认 `(portraits|artifacts|arts|maps)` 四个目录且文件名只许 `[a-z0-9-]`——NPC uid 带下划线（`npc_qy_01`）若直作键名必被正则拦死；新类目（pets/scenes 等）亦然 → §9.1 定 uid→键的去下划线映射，§9.9 定正则闸扩展为本轮契约变更项。
4. 方案 D4 称传闻应进「其他角色登录简报的世间段」，但简报世间段数据源是 `core/jianghu`（江湖事件账），不是传闻池；且 `rumors.pick_for_npc` 现状**无任何调用方**，真正在交谈链路被引用的取闻口是 `core/lorebook.lore_prompt_block`（内部走 `list_rumors`，已被 `core/npc_mind.py:428` 与 `server/world.py:3162` 调用）→ §6 按实测口径验收，不向 jianghu 账注水。
5. 图库总账算术缺口：任务口径内各类 caps 上限相加（NPC 37 + 玩家 8 + 灵宠 4 + 场景 15 + 法宝 10 + 功法 2 + 宝图 4）只有 118 张，达不到「总数 ≥130」→ §9.8 设最小补足包（奇遇专图 6 + 丹药分类图 8 + 材料分类图 7，均为盘点第三节实证的零覆盖类目、只做分类级不做按件级），总账 139 张，裁定理由写死在 §9.8。
6. 主线章节 check 若另起求值器会与一期求值点清单（E1–E6）分叉 → §3.5 定章节状态**派生自其 checked goal 的 status**（单一事实源仍是 goals 求值器），fate 引擎只做绑定、激活与派生，不做第二套判定。
7. 世仇选人若直用影子最强者，其境界可达化神（tier 5），硬塞进新角初始关系即违反一期 foe bounds（≤起始境界+1）→ §4 定「本人超界则降级为同门/后人」的选人链，bounds 是硬约束不让路。

**第四步 · 举一反三。** 横向：戏剧频控 KV 与入局队列是通用的「找上门」通道，第三期仪式/章节扩充可复用；图鉴分组改由后端 `GALLERY_GROUPS` 程序化构建（NPC 单人组由 ROSTER 生成），后续再扩图不改前端分组表。纵向：`FateThread.origin` 与一期 origin 块同形状（复制收编，一期 §3.2 已预埋）；评语分段字段（head/line/tail）为第三期仪式余韵复用同一评语提供结构。涟漪：`_status_dict` 只增 `fate.thread` 子键与 `location_image` 一键；登录响应只增 queue 新 kind 与 lines.fate 的取值优先级；既有前端忽略新键不报错（沿仓内只增惯例）。

**第五步 · 完善方案（收敛点，即本 Spec 的五个定死口径）。**
- **K1 · S-4 新键**：幂等键 = `(source, kind, ref, instance)`，`instance` 落 `check.instance`，存量无 instance 目标以 `""` 回退（旧行为逐字不变）。见 §2。
- **K2 · 章节=goal 派生**：每章激活时以 `instance=<thread_id>:c<idx>` 挂一条 source=`thread` 的 checked goal，章节 status 由该 goal 的 status 派生；终局命题复用一期 source=`fate` 目标并回填其 instance 为 `:c5`。见 §3.5。
- **K3 · 世仇植入通道**：世仇不新开落账路径——由转世编排先算出 `vendetta_npc_id`，经 `OriginEngine.generate_for_new_life` 的新入参进出身包 foe 名额（bounds/态度/KarmaLink 种子边全走一期既有通道），主线种子再引用同一人。见 §4。
- **K4 · 戏剧零状态机**：戏剧事件只落两处 KV（待回应队列 `drama_pending:{char_id}`、频控 `drama_quota:{char_id}`），评估只挂登录入局与迁跃落点两个既有触发点；回应走单一新命令 `/回应`，后果只许经既有系统入口落账（机会目标/态度账/斗法/诺言与因果链既有结算/因果链引擎钳制内的发酵微调）。见 §5。
- **K5 · 图库总账 139**：38 + 新增 101 = 139（逐项见 §9.9 总表）；唯一事实源仍是 `GALLERY_ASSET_KEYS`，托管正则闸扩展与 REALM 映射变更均单列契约变更（§9.2、§9.9）。

### 0.2 代码事实纠正表（与方案/任务简报描述不符者，一律按实测施工）

| # | 描述出处 | 实测现状 | 本 Spec 口径 |
|---|---|---|---|
| F1 | 任务简报称 `_status_dict` 可只增 `fate` 全量结构 | `fate` 键一期已被命格占用：`server/world.py` 的 `_status_dict` 以 `core/ceremony.py:139 fate_block()` 下发 `{boons, pending, power_bonus}`，前端与 `/命格` 均在用 | 主线结构挂 `fate.thread` 子键（§8.1），`fate` 既有三子键一字不动 |
| F2 | 方案 §4d 称 NPC 引用传闻走 `pick_for_npc`、D4 称事迹进他人简报「世间」段 | `pick_for_npc`（`core/rumors.py:84`）全仓无调用方；交谈上下文实际经 `lore_prompt_block`（`core/lorebook.py:90` 走 `list_rumors`）注入，已接线于 npc_mind 与 world 交谈路径；简报「世间」段数据源为 `core/jianghu.list_recent`，与传闻池无关 | §6 写入口只写传闻池；引用验收以 `lore_prompt_block` 实际注入 + `pick_for_npc` 函数级命中双口为准；**不**往 jianghu 账写传闻（防污染「与你何干」投影） |
| F3 | 任务简报示例键 `portraits/npc-npc_qy_01` | `/assets/` 正则闸（`server/app.py:208`）文件名只许 `[a-z0-9-]+`，下划线必 404；且闸只认 portraits/artifacts/arts/maps 四目录 | NPC 单人键定为 `portraits/npc-<uid 去 npc_ 前缀且 _ 换 ->`（§9.1）；新目录 pets/scenes/omen/goods 须同步扩正则闸（§9.9 契约变更） |
| F4 | 盘点/方案称法宝 cauldron/gourd 两键「预留」 | 实测 66 件目录装备命中分布（本 Spec 定稿时以 `artifact_key_for_equip_name` 全量跑）：sword 18 / mirror 14 / fan 9 / orb 8 / seal 7 / pagoda 7 / banner 2 / bell 1 / cauldron 0 / gourd 0——零命中是因为目录里根本没有名字含鼎/炉/葫芦的装备，关键字规则本身无误 | §9.5 明说：不靠改映射硬凑命中；cauldron/gourd（及改映射后同样归零的 mirror/pagoda）定为「关键字保留键」，只由天工造化等生成器物的名字命中，验收以合成名直测解析函数为准 |
| F5 | 方案 §4a 章节结构称「经营章×2」等 5–7 章 | 一期已落：每世恰 1 条 origin 短期目标 + 1 条 fate 命题目标，`CHECKED_SOURCES=("origin","fate")`，求值器只认这两源 | §3 定新源 `thread` 并入 `CHECKED_SOURCES`/`KINDS`/`NON_REJECTABLE`（契约变更三点，§3.5）；章节骨架定死 6 章（立命/经营×2/冲突/高潮/暮年），不再浮动 |
| F6 | 方案 §4a 种子优先级只列四类 | 一期 §3.10 已定：未竟之志是转世后命题头号候选；路线 C（方案 §8）另定世仇家系强制植入——三者（未竟之志/世仇/影子最强）对「一号种子」的竞争方案未写死 | §3.3 定五级优先级并写死未竟之志的「种子/命题二居其一」判定规则；§4 定世仇与未竟之志的先后 |
| F7 | 任务简报称图库各类 caps 相加可达 ≥130 | 按任务 caps 上限逐项相加 = 38+37+8+4+15+10+2+4 = **118**，数学上达不到 130 | §9.8 补足包（奇遇 6 + 丹药分类 8 + 材料分类 7 = 21，全为盘点实证零覆盖类目），总账 139；补足包优先级 P2（核心类目先行），但总账验收按 139 验 |
| F8 | 一期 Spec §3.7 称求值点「禁止新增」 | 二期主线推进必须有章节求值时机；既有 E1–E6 中 E1（入局拼装）/E3（突破）/E6（sync_progress）已覆盖多数事件，缺口只有奇遇完成与迁跃落点（visit 类 check） | §3.6 定 fate 求值只**搭载**既有 E 点 + 两个既有动作的返回点（奇遇结算返回、迁跃落点，与 proactive 同点），仍零 tick 扫描、零登录新增耗时源 |
| F9 | 方案 §4d 背叛触发含「合谋（collusion）事件命中」 | collusion 的产物即 KarmaLink 边（`core/collusion.py ensure_link`），无独立事件流可订阅 | §5 背叛触发改以可读账表达：未了诺言 + 态度阈值，或 KarmaLink「仇」边 strength ≥3 + 未了诺言（见 §5.2 表） |
| F10 | 盘点称地点 10 处 | `config.WORLD_LOCATIONS` 12 键去重 10 处（落霞山灵泉、黑风绝渊各有变体键）；`world_grid.DEFAULT_TOPOLOGY_NODES` 仅 7 节点；秘境 `SECRET_REALMS` 7 处、副本锁妖古窟 1 座 | §9.4 场景键以 WORLD_LOCATIONS 去重 10 处为地点组（变体键同图），秘境组取 5 处代表 + 古窟入口 = 15 键，映射表逐项写死 |

### 0.3 任务边界与方案的衔接记录

- 方案 §7 第二期范围 = fate_threads 全量 + 主动戏剧五类 + 传闻写入口；评语 AI 润色在一期拆分线中明列随二期（方案 §7 第一期「不进一期」清单），本轮按任务简报 §6 做**可选路径**（模板永远兜底）。
- 一期 Spec §8 Out of Scope 点名移交二期的四条——① fate_threads 与章节本体、② 世仇强制植入、③ 出身包收编 FateThread.origin、④ 交谈「旧账」行——本轮全部收口：①§3、②§4、③§3.8、④§8.3（做，理由见该节）。
- 一期遗留 S-4（add_checked_goal 幂等）在评审记录中为「只记录不修」，本轮按任务简报列为前置项收紧（§2），且其验收包含一期 origin/fate 目标行为不回归。

---

## §1 · Problem

一期交付了入局、简版出身、两幕仪式与关系可见化，但「一世」仍没有故事骨架：终局命题只是一条挂在目标栏的判定式，没有章节、没有对手的正面登场、没有暮年收束；转世继承的影子与未竟之志已能回流，却没有世仇——上世的血债在新世里无人认领；NPC 主动引擎仍只会寒暄，欠你的、恨你的、想求你的人都不会找上门；玩家的大事（突破/链了结/弧决算）不进传闻池，世界记不住玩家；图库 38 张里 NPC 37 人只有 4 张原型脸（单人覆盖 11%）、法宝两大部位整类借代、灵宠与地点零图——第二期戏剧要「人找上门」，首先得有脸。

**真正需求条目（收敛结论，实现与验收的唯一依据）：**

- RQ-1（S-4 前置）：`add_checked_goal` 幂等键收紧为含目标实例标识，新旧数据兼容，一期行为不回归，中期目标接入后同 kind+ref 不同实例可并存。**本项是线一其余各节的落码前置**（实现顺序写死：§2 → §3 起）。
- RQ-2（主线）：新表 `fate_threads` + `core/fate_thread.py`；每角色同时 1 条 active 主线，6 章骨架（立命/经营×2/冲突/高潮/暮年），三层目标完整绑定为 checked goals（instance 用 §2 新键）；种子五级优先级；推进只搭既有事件钩子，AI 零参与判定；主线可搁置（不删不罚）；主线模块自身零数值（A5）。
- RQ-3（世仇）：转世时按玩家杀伐记录（影子 + KarmaLink 孤儿行 + 上世 xue 链）选定世仇家系一人，强制植入新出身 foe 名额（bounds 沿一期），并成为主线一号种子候选（与未竟之志的优先级 §3.3 写死）；植入者态度/链接/种子引用三处一致可对账。
- RQ-4（戏剧）：`NpcProactiveEngine` 扩五类戏剧（求助/示好/挑衅/背叛/牵连），类型判定与后果 100% 规则，频控三闸（每玩家每现实日 ≤3 件合计、示好不占额；同 NPC 同玩家 1 游戏日 ≤1 次；只在登录入局与迁跃落点评估）；戏剧本身零数值发放（示好的赠礼是 NPC 自有灵石的**转移**，非发放，见 §5.3）。
- RQ-5（传闻）：`core/rumors.py` 补玩家事迹写入口（大境界突破/因果链了结/世界弧决算参与/避战），truth 沿先例，NPC 引用走既有取闻口（F2 口径）。
- RQ-6（评语润色）：AI 可用时在**锁外、非登录路径**异步润色评语定性句（≤60 字），输入只许规则汇总数据；失败/超时/异常静默降级模板版，数值与三落点不变。
- RQ-7（呈现）：`_status_dict` 只增 `fate.thread` 子键与 `location_image`；入局 queue 只增 `fate_chapter`/`drama` 两 kind；交谈「旧账」行本轮做（§8.3）；新命令恰 2 条（`/命途`、`/回应`）。
- RQ-8（图库）：资产键唯一事实源仍为 `GALLERY_ASSET_KEYS`，扩至 139 键；NPC 37 单人图逐人对号、玩家立绘补满 20 组合、灵宠 4、场景 15、法宝器型补齐至 20、功法 10、宝图 8、奇遇专图 6、丹药/材料分类图 15；图鉴全集同步扩展，点亮规则沿既有口径；资产逐张目检。

---

## §2 · 线一前置：S-4 幂等键收紧（core/goals.py）

### 2.1 现状锚点（实测）

`GoalEngine.add_checked_goal`（`core/goals.py`，一期 §3.7 落码）现幂等逻辑：遍历 `character.goals`，对 `status=="active"` 且 `source` 相同者，比较其 `check.kind == 新 check.kind` 且 `check.ref == 新 check.ref`，命中即返回既有项不重复挂。问题：二期同一玩家可同时有两条 `chain_resolved + ref=<同一NPC相关链>` 或两条 `npc_attitude_at_least + ref=""`（check 中 ref 键缺失时 `gc.get("ref")` 为 None，两条无 ref 目标直接互撞）类的章节目标——现键下第二条永远挂不上，且调用方拿到的是第一条的返回值，静默错账。

### 2.2 新键形状（写死）

- `check` 新增可选字段 **`instance: str`**，语义 = 目标实例标识，格式 `<owner>:<slot>`：主线目标为 `<thread_id>:c<chapter_idx>`（如 `ft_3f9a1c2e:c2`）；一期 origin/fate 目标**不回填**（见兼容口径）。
- 幂等键改为四元组：`(source, check.kind, check.ref, check.instance)`，其中缺失的 `ref`/`instance` 一律以 `""` 归一后比较（`str(gc.get("ref") or "")`、`str(gc.get("instance") or "")`）。
- `add_checked_goal` 签名只增关键字参数 `instance: Optional[str] = None`：非 None 时写入 `chk["instance"] = instance`（在 `deadline_days` 的 setdefault 之前，与既有 chk 拷贝口径一致）；为 None 时不写该键（一期调用方零改动、零行为变化）。
- 目标项顶层不另存 instance（单一事实源在 check 内）；`evaluate_checked_goals`/`_eval_check` 不读 instance（求值语义不变），instance 只参与幂等与 §3 的章节派生映射（派生映射读 `check.instance` 解析 `<thread_id>:c<idx>`）。

### 2.3 旧数据兼容口径（写死）

- 存量 active 目标（全部一期 origin/fate 目标、线上老角色）无 `instance` → 归一为 `""`。于是：同 source+kind+ref 的存量目标与一条同样无 instance 的新目标仍互斥（**一期行为逐字不变**，生成重入防线不破）；存量目标与一条带 instance 的新目标**不互斥**（二期目标可正常挂上，老目标不受影响、不被吞并）。
- 不做任何存量数据迁移/回填：回填会改变存量目标的幂等身份，且 fate 命题目标的 instance 由 §3.8 的主线收编动作在建线时单点回填（那是新行为，不是迁移）。
- `add_checked_goal` 的既有返回值契约不变（命中幂等返回既有项、新挂返回新项）。

### 2.4 验收

- **S4-01** 幂等新键：同角色以同 source/kind/ref、不同 instance（`:c1`/`:c2`）连挂两条，两条均 active 且 id 不同；再以 `:c1` 重挂，返回首条既有项、目标总数不增。
- **S4-02** 旧数据兼容：手工构造无 instance 的 active origin 目标（同 kind+ref），以无 instance 重挂 → 返回既有项不新增（一期行为）；以带 instance 重挂 → 新增成功且旧项仍 active。
- **S4-03** 无 ref 撞车修复：两条 check 均无 `ref` 键、同 kind 不同 instance 可并存（修复 §2.1 的 None 撞车）；两条均无 ref 且均无 instance 仍互斥。
- **S4-04** 一期不回归：一期验收 P2-01/P2-04/P2-07 所涉生成路径（origin 短期目标、fate 命题、`select_fate_proposition` 重实例化）复跑全绿；`tests/test_game_feel_phase1_backend.py`、`test_game_feel_phase1_rework*.py` 中 goals 相关用例全绿（基线名单内者除外，§11）。
- **S4-05** 求值不串扰：S4-01 的两条同 kind+ref 目标各挂不同 deadline，`evaluate_checked_goals` 到期只翻转到期者，另一条保持 active（instance 不参与求值的负例断言）。

---

## §3 · 线一之一：fate_threads 命途主线全量

### 3.1 现状锚点（实测）

| 对象 | 现状 |
|---|---|
| 仓储先例 | `karma_chains` 表（`storage/db.py`）：`id/data_json/status/player_id/counterparty_id/created_at` 六列，`CREATE TABLE IF NOT EXISTS`；`KarmaChainRepository` 有 save/get/list_all/list_by_player/list_active_global/find_pair/delete 全套按列查询 |
| 弧语义 | `core/world_arc.py`：`STAGES=("prophesy","escalate","climax")`、到期强制决算防挂死（`prune_arcs` 超时决算）、`participants` 名单（`{who, choice}`）——本节只借语义（阶段推进+到期不挂死），不共用其 WorldState KV 存储 |
| 导演 | `core/world_director.py`：`DIRECTOR_MIN_INTERVAL_SECONDS=480`、`DIRECTOR_MAX_ACTIVE=3`、类型白名单 `DIRECTOR_TYPES`（含 sect_tension）、数值键剥离表 `DIRECTOR_STRIP_EFFECT_KEYS`（config，含 stones/exp/lifespan 等 13 键） |
| 影子 | `core/legacy.py _snapshot_shadow`：LifeTrace.shadow 按 \|value\| 降序截 6（`SHADOW_MAX_ENTRIES`），态度与 KarmaLink 折算合并、同 NPC 取绝对值大者；`core/inheritance.py applied_shadow_entries` 为施加口径（×0.4 衰减、±25 封顶、\|v\|<8 不落账） |
| 因果链子顶 | config `KARMA_CHAIN_EFFECT_CAPS`（stones +60/−40、exp +120/−60、sin ≤15、merit ≤10、dao_heart ≤5、attitude ≤20、lifespan 恒 0）与日顶（每玩家每现实日兑现 ≤2 条、链灵石 ≤120）——A5 对账的「原系统口径」即此 |
| 一期目标 | origin 短期目标（deadline 7/10/15/20 游戏日四档）与 fate 命题目标已挂 `Character.goals`；求值点 E1–E6（一期 §3.7）；`SECONDS_PER_GAME_DAY=240.0`（config） |

### 3.2 数据模型（写死）

新表（置 `storage/db.py` 的建表段，照 karma_chains 先例，旧存档零迁移）：

```sql
CREATE TABLE IF NOT EXISTS fate_threads (
    id TEXT PRIMARY KEY, data_json TEXT NOT NULL,
    status TEXT NOT NULL,          -- active|shelved|completed|broken|inherited
    player_id TEXT NOT NULL,       -- 角色 id（一世一线）
    created_at REAL NOT NULL
);
```

新仓储 `FateThreadRepository`（置 `storage/db.py`，照 `KarmaChainRepository` 写法）：`save / get_by_id / list_by_player(player_id) / list_by_user(user_id)`——注意跨世防重与世仇要按**账户**查前世线，故 data_json 内含 `user_id`，`list_by_user` 以 data_json 内的 user_id 匹配实现（建表列不增，查询为 Python 侧过滤 `list_all` 后筛 user_id——主线表量级为每账户每世 1 行、全服低千量级，许此一处全表读并在代码注释标明量级依据；其余查询一律走 player_id 列）。

Pydantic 模型 `FateThread`（新文件 `core/fate_thread.py`，引擎 `FateThreadEngine` 同文件）：

```jsonc
{
  "id": "ft_<12hex>", "player_id": "<char_id>", "user_id": "<account user_id>",
  "life_no": 1,                       // 取 LegacyAccount.total_lives+1 口径（建线时）
  "status": "active",                 // active|shelved|completed|broken|inherited
  "seed_source": "karma_shadow",      // unfinished|vendetta|karma_shadow|blood_feud|sect|origin
  "seed_ref": "<chain id|npc id|arc/directive id|promise id>",
  "seed_npc_id": "", "title": "",
  "antagonist_npc_id": "", "antagonist_name": "",
  "patron_npc_id": "", "patron_name": "",
  "origin": { /* 一期 origin 块逐字复制，见 §3.8；老角色为 {} */ },
  "final_proposition": {"text": "", "check": {/* 与 fate 目标 check 同体 */}, "status": "active"},
  "chapters": [ /* §3.4，每章一节 */ ],
  "current_chapter": 0,
  "signature": "<seed_source>|<antagonist>|<kind 序列>",
  "visited": [],                      // visit_location 求值材料：到访过的地点名（去重保序，截 20）
  "shelved_at": 0.0,
  "created_at": 0.0, "sealed_at": 0.0,
  "unfinished_note": ""               // 死亡封存时未了结一句话（§3.8）
}
```

章节对象：`{idx, group(setup|manage|conflict|climax|finale), kind(visit|feud|treasure|choice|sect|climax|finale), tier(short|mid|final), title, goal_text, check_template, check（激活时绑定）, goal_id（激活后回填）, trigger_type, trigger_ref, status(locked|active|done|failed), summary, activated_at, resolved_at}`。

新 config 常量（置 config.py 命途段，数值写死）：`FATE_THREAD_MAX_ACTIVE = 1`；`FATE_CHAPTER_WINDOW_DAYS = {"setup": 15, "manage": 20, "conflict": 21, "climax": 30, "finale": 0}`（finale 无期限、随命题与死亡终判）；`FATE_THREAD_SKELETON = 6`（章数定死）。

### 3.3 种子优先级（写死，F6 收口）

建线时按下列顺序扫描，**首个命中即定种子**，全程纯规则、只读既有账：

| 优先级 | seed_source | 命中条件（可复算） | seed_ref / 对手 |
|---|---|---|---|
| P0 | `unfinished` | 上一世 `traces[-1].unfinished_prop` 非空且可重实例化（判定规则见下） | ref=上世 thread id 或 unfinished.check 的 ref；对手优先取 unfinished 关联 NPC（影子同名优先复用） |
| P1 | `vendetta` | §4 世仇选人成功且已植入本世出身 foe 名额 | ref=植入者 npc_id；对手=植入者 |
| P2 | `karma_shadow` | `traces[-1].shadow` 中 \|value\| 最大者（并列取 shadow 列表序首位）对应的 NPC 在世 | ref=该 npc_id；对手（负值）或引路人（正值）按符号定 |
| P3 | `blood_feud` | 本世已有 kind=`xue` 的 active/fermenting 因果链（取 created_at 最新一条） | ref=chain id；对手=链 counterparty |
| P4 | `sect` | `active_directives()` 中有 type=`sect_tension` 且（sect==角色 sect 或 location==角色 location），或 `active_arcs()` 中有 kind=`sect_crisis` 且 sect 关联角色 | ref=directive/arc id（取 updated 最新者）；对手取弧/指令关联 NPC，无则对手为空、引路人为本宗门 rank 最高在世者 |
| P5 | `origin` | 以上皆无（兜底恒命中） | 有 origin 时 ref=old_story.npc_id，对手/引路人按旧事绑定（foe→对手、kin→引路人）；无 origin（老角色首线）时按灵根属性+当前地点从 ROSTER 按 agenda ∈ {treasure, revenge}、地点相近序选一人为引路人，ref=`roster:<uid>` |

**未竟之志「二居其一」判定规则（与方案 §4a 衔接口径对齐）**：未竟之志同时是主线一号种子与终局命题头号候选的候选源，二者只居其一——
- 若 unfinished 的 check 可在本世重绑定为**章节判定式**（其 kind ∈ §3.5 白名单且绑定对象在本世存在：debt 类需本世有债、foe 类需本世有该 NPC 或其世仇植入者、item 类恒可绑）→ 未竟之志占**种子位**（seed_source=`unfinished`），终局命题按一期 `select_fate_proposition` 的常规优先级另行定盘（unfinished 入参传空，避免双挂）；
- 否则（check 不可重绑，如 debt_clear 而本世无债）→ 未竟之志占**命题位**：终局命题沿一期口径由 `select_fate_proposition(unfinished=…)` 选取（其内部优先级不变），种子位顺延 P1 起扫描。
- 一期 P2-07 的既有行为（未竟 kind 可重实例化时命题取之）因此**变更一处**：debt/foe 两类未竟在对象存在时改走种子位、命题位让给常规优先级——此变更在 §11 回归口径中列为合法契约变更，P2-07 用例须由 QA 岗按本节口径修订（修订口径：断言「未竟不双挂」——要么 seed_source=unfinished 且命题 kind ≠ 未竟 kind，要么命题 kind == 未竟 kind 且 seed_source ≠ unfinished，二者必居其一）。

**导演提名门禁**：本轮主线**不新增任何导演调用**（种子扫描纯规则）。导演与主线的唯一交点是 P4 读取已落账的 `active_directives/active_arcs`（合法集合 = 上述两类）。若后续轮次接导演提案，其提案 dict 只许含 `{seed_source, npc_id, location, chapter_kind}` 四键且取值须 ∈ 本节合法集合，数值类键一律按 `DIRECTOR_STRIP_EFFECT_KEYS` 剥离后丢弃——此门禁先行写入本 Spec 作为契约，`FateThreadEngine` 对任何外部传入的种子建议统一走 `validate_seed_hint()` 校验（本轮无调用方，函数与测试先行）。

### 3.4 章节骨架（写死 6 章）

骨架恒 6 章，`kind` 按种子类型查下表定（防轮换规则见 §3.7）；`tier` 与分层目标对齐（方案 §4a：短期住立命/经营前段、中期住经营后段/冲突、终局住高潮/暮年）：

| idx | group | tier | kind（按 seed_source） | trigger_type（激活/推进事件） |
|---|---|---|---|---|
| 0 | setup 立命 | short | unfinished/vendetta/karma_shadow→`visit`；blood_feud→`feud`；sect→`sect`；origin→`visit` | 建线即激活 |
| 1 | manage 经营·一 | short | `treasure`（种子为 shadow/origin）/ `visit`（其余） | 上章 done/failed |
| 2 | manage 经营·二 | mid | `choice`（恒） | 上章 done/failed |
| 3 | conflict 冲突 | mid | `feud`（对手线）/ `sect`（sect 种子）/ `treasure`（无对手机缘线） | 上章 done/failed |
| 4 | climax 高潮 | final | `climax`（恒） | 上章 done/failed |
| 5 | finale 暮年 | final | `finale`（恒） | idx4 进入终态（done/failed）后激活；或大限预警（剩余寿元 ≤3 游戏年）提前激活 |

章节标题与 goal_text 由本地模板按 kind×seed 拼装（变量只取真实数据：人名/地名/物名/金额），模板族每 kind ≥2 条、确定性选句（`zlib.crc32(f"{thread_id}:{idx}") % len`，沿一期评语的稳定哈希先例）；AI 润色标题/开场白为可选路径（沿方案 §4a 分工：失败用模板原句，标注 source 口径同导演 local 降级，**润色调用不得进建线/求值的同步路径**——建线只落模板文案，润色若实现走 §7 同款锁外异步回填，本轮不强制）。

### 3.5 check 绑定与求值（K2：章节状态派生自 goal）

**对 `core/goals.py` 的契约变更（仅此四点，余皆不动）**：① `CHECKED_SOURCES` 增 `"thread"`；② `KINDS` 增 `"thread": "命途"`；③ `NON_REJECTABLE` 增 `"thread"`（章节目标不可单独弃，搁置走 §3.9 的线级开关）；④ 求值器 `_eval_check` 的 kind 白名单增 3 个新 kind（下表）。一期四点契约（过期豁免/上限豁免等）对 `thread` 源自动同等适用（其实现以 `CHECKED_SOURCES` 为判据，天然覆盖）。

**章节 check 在激活时绑定**（locked 章只存 `check_template` 的 kind 与参数策略，参数在激活瞬间按当时事实绑定，避免建线时绑定到尚不存在的链/物）：

| 章 | check kind（绑定规则按序取首个可绑者） | 参数 |
|---|---|---|
| 0 立命 | `visit_location`（种子 NPC 当前地点）→ 若种子 NPC 无固定地点则 `npc_attitude_at_least` | `{ref: <地点名>, npc_id}` / `{npc_id, value: -10}`（到访或照面即推进） |
| 1 经营·一 | `promise_kept_count`（新 kind）→ `stones_at_least` | `{count: 1}` / `{amount: 200}` |
| 2 经营·二 | `chain_resolved`（与对手/引路人之间任一链）→ `item_in_bag`（旧事遗物或种子关联物）→ `npc_attitude_at_least` | `{npc_id, outcome: "any"}` / `{item_ref}` / `{npc_id, value: 15}` |
| 3 冲突 | `chain_resolved`（对手链，outcome any）→ `npc_attitude_at_least`（对手） | `{npc_id}` / `{npc_id, value: 0}` |
| 4 高潮 | 按 seed 查专表：unfinished/vendetta/blood_feud→`chain_resolved{xue 或对手链}`，无链时 `npc_attitude_at_least{对手, 0}`；karma_shadow→`npc_attitude_at_least{种子NPC, 符号对应阈值（正值 60 / 负值 0）}`；sect→`sect_joined{本宗门}` 或已入宗时 `realm_at_least{tier: 当前+1}`；origin→`item_in_bag_at_death` 不用（那是命题式），用 `item_in_bag{遗物}` 或 `realm_at_least{tier:2}` | 见左 |
| 5 暮年 | = 终局命题 check 原样（与 fate 目标同体，见下） | — |

**新 kind 求值口径（只读既有账，AI 零参与）**：
- `visit_location {ref, npc_id?}`：`ref ∈ thread.visited`（§3.6 的迁跃落点记录）即 done；带 npc_id 时还须该 NPC 当前 location == ref（到访时人在场才算照面）。求值器需读 thread——经 `FateThreadRepository.list_by_player(character.id)` 取 active 线的 visited（求值器以 try/except 包裹，读不到按 pending）。
- `promise_kept_count {count}`：`PromiseEngine._involving(character.id)` 中 status==KEPT 的条数 ≥ count 即 done（与 `promise_settled` 同数据源）。
- `chain_resolved {ref?, npc_id?, outcome}`：ref 非空时查该 chain id 的 status ∈ 终态（resolved/dissipated 等仓储终态口径以 `KarmaChain` 模型 status 枚举为准）；ref 为空时查 `list_by_player` 中 counterparty==npc_id 且 status ∈ 终态的任一链。outcome="any" 不限 polarity；outcome 指明 en/chou 时按链 kind 匹配。
- `thread_climax {ref: <thread_id>}`：该线 idx4 章 status==done 即 done。**只许出现在 fate 命题目标上**，且只由 §3.6 的 fate 求值序在章节派生**之后**求值（先派生章节、再求值目标，顺序写死，防自引用死锁）；E5 终判时同序。

**绑定与派生流程（`FateThreadEngine.evaluate_for(char, now, *, final=False)`，写死）**：
1. 取 active/shelved 线（shelved 时只做第 4 步的死亡封存预备、余皆跳过，§3.9）；
2. 对当前章的 goal 调 `GoalEngine.evaluate_checked_goals` 的同一求值路径（实现上： fate 引擎不自写判定，只调 goals 求值器对全角色求值——E 点本来就会调，fate 引擎在 E 点尾部做派生）；
3. 派生：按 `check.instance == f"{thread.id}:c{idx}"` 找到当前章 goal，其 status 为 done/failed → 章 status 同步、写 summary 与 resolved_at；随后激活下一章（绑 check + `add_checked_goal(source="thread", instance=…, deadline_days=FATE_CHAPTER_WINDOW_DAYS[group])` + 回填 goal_id）；idx4 派生完成后激活 finale 并把 fate 命题目标的 instance 回填为 `:c5`（若尚未回填）；
4. fate 命题目标 status 派生 `final_proposition.status`；命题 done 或 idx4 done → 线可转 completed（finale 章 done 后线 status=completed）；
5. 引擎自身只写 fate_threads 仓储与 goals 内存项，落盘归调用方既有 save 路径（沿一期求值器「从不自行落盘」纪律，fate_threads 的 save 是其自有仓储的唯一例外——派生有变更时引擎即刻 `FateThreadRepository.save`，因为 thread 不在角色行上、无既有 save 载体）。

### 3.6 触发点清单（F8：只搭既有点，零 tick 扫描）

`evaluate_for` 的调用点（全部为既有动作的锁外段/返回组装点，try/except 包裹、失败不炸主流程）：
- **T1 = E1** 登录入局拼装（`build_entry` 步骤 ③ 之后新增 ③.5 步，§8.2）；
- **T2 = E3** 突破成功两出口（`on_breakthrough_major` 同位）；
- **T3 = E6** `sync_progress` 尾部（briefing/近况路径兜底）；
- **T4** 奇遇完成：`omen_scene`/事件链结算返回组装点（server handle 中奇遇选项结算后）；
- **T5** 迁跃落点：`/go` 成功返回组装点，先把落点地点名 append 进 thread.visited（去重、截 20）再 evaluate_for——与 `maybe_engage` 的迁跃触发同点同段；
- **T6 = E5** 死亡终判（`settle_death` 内、§3.8）。
链了结/诺言结算/态度移位不单设点：它们分别由 T1/T3 的 advance_for/settle_due/E4 既有链路兜底（与一期 E2/E4 的「迟到一次登录必达」口径一致，明示接受）。

### 3.7 窗口与改道、防套路化（写死）

- **章节窗口**：章节 goal 的 deadline = 激活时刻 + `FATE_CHAPTER_WINDOW_DAYS[group]` 游戏日（`deadline_days` 经 add_checked_goal 既有换算落 `deadline_at`）。到期未达成 → goal failed → 章 failed（派生）→ **主线改道**：下一章照常激活，其 summary 首行记「因「{上章标题}」未成改道」，上章的 check 对象（NPC/链/物）写入线级 `unfinished_note` 候选（死亡封存时取最后一条未成章，见 §3.8）。主线永不因单章失败而 broken；`broken` 只用于 finale 之后命题 failed 的终态标记（线 status=broken 与 completed 二选一在封存时定，见 §3.8）。
- **与既有「14 日类窗口」的关系**：因果链兑现窗口 `KARMA_CHAIN_WINDOW_DAYS=14` 游戏日不变；章节 check 若绑 `chain_resolved`，其有效窗口 = min（章节窗口， 链自身窗口+发酵期）——即章节等链的节奏，不另给链续期；链在章节窗口内未了结而章节先到期者，按上条改道（链本身继续按其时钟走，玩家仍可事后了结，只是主线已改道）。
- **防套路化（同账户防重）**：线指纹 `signature = f"{seed_source}|{antagonist_npc_id or patron_npc_id}|{'/'.join(chapter kinds)}"`。建线时与同 user 最近 3 条线（`list_by_user` 按 created_at 倒序取 3，含 inherited）比对：signature 全等 → 对 kind 序列做**确定性轮换**：将 idx1 与 idx3 的 kind 在其候选集内各换一档（treasure↔visit、feud↔sect 中取未用者），重组后仍全等（种子与对手都同且 kind 无可换）则接受并记 `signature_forced: true`（世仇/未竟类种子天然可能连世同人，不强拆）。轮换只改 kind 与其 check 绑定策略，不改种子与对手。

### 3.8 死亡衔接与出身收编（写死）

- **建线时机**：`FateThreadEngine.ensure_thread(char, account, now)` 幂等（已有 active/shelved 线即返回既有线）。调用点两处：① `World.join` 锁外收尾段、origin 生成**之后**（新号/老号登录均在此首次建线，老号以 P3–P5 扫描）；② `World.reincarnate` 内、`OriginEngine.generate_for_new_life` 之后、统一 save 之前（纯本地规则+既有仓储写，毫秒级，沿一期 origin 在 reincarnate 锁内的同口径）。建线失败（异常）吞掉、角色照常游玩（主线是增益层，不是登录/转世门禁）。
- **出身收编**：建线时若 `char.origin` 非空，`thread.origin = deepcopy(char.origin)` 逐字复制（同形状，一期 §3.2 预埋口径）；`char.origin` 本体**冻结为快照不删不改**（出身卡/命盘出身段仍读角色行，一期呈现零改动）。此后主线侧只读 thread.origin，角色行侧只读 char.origin，两处不一致时以 thread.origin 为主线事实、char.origin 为出身卡事实（构造上同源同时点复制，不应不一致；验收 FT-09 断言建线瞬间逐字相等）。老角色（origin 为空）thread.origin = `{}`，呈现层按一期回退口径。
- **命题收编**：建线时若角色已有 active 的 fate 命题目标（一期生成），thread.final_proposition 直接取其 text/check，finale 激活时回填其 instance（§3.5）；无 fate 目标者（老角色），建线时以种子为据按一期命题模板族补挂一条 fate 目标（文案/check 模板沿一期 §3.7 命题表，kind 按种子映射：vendetta/unfinished→foe_reckoning 形、sect→sect_inner、origin→stand_firm 兜底）。
- **死亡封存**：`LegacyEngine.settle_death` 内、一期 `_fate_fields` 生成**之后**追加 thread 分支（try/except 包裹，异常不阻断结算，沿 §3.9 一期纪律）：
  1. 取本世线（list_by_player(char.id) 最新一条未封存者），置 `status = "completed"`（finale done 或命题 done）或 `"broken"`（命题 failed），其余情形置 `"inherited"`（带着未竟封存）；写 `sealed_at`、`unfinished_note`（最后一条 failed/未激活章的一句话：`「{章标题}」未成：{goal_text}`，无未成章时取当前章）；
  2. `trace.fate_summary` 改写为：`命途「{title}」{done 章数}/{总章数} 章了结，{结局词（功成|留憾|中道崩殂）}；` + 一期 fate_summary 原文（一期拼装逻辑不改，thread 段为前缀拼接）；
  3. `trace.unfinished_prop` 的取值优先级变更：**thread 未竟优先**——线未 completed 且 unfinished_note 非空时，unfinished_prop = `{kind: <由未成章 check kind 经一期 _CHECK_TO_PROP_KIND 映射，thread_climax/chain_resolved 映射为 foe_reckoning>, text: unfinished_note, check: <未成章已绑定 check 原样>}`；线已 completed 或无未竟时回退一期 goal 口径（一期逻辑不删）。此变更使 §3.3 的 P0 在下一世有真实输入；
  4. 线行保留不删（防重与世仇的跨世查询靠它）。

### 3.9 主线可搁置口径（方案风险表已定：不删不罚）

- 线 status `active ↔ shelved` 由 `/命途 搁置` / `/命途 续` 切换（§8.4）。搁置中：`evaluate_for` 跳过章节派生与到期判定（章节 goal 的 deadline 在恢复时顺延：`goal.deadline_at += (now - shelved_at)`，只顺延当前章 goal 一条，写死）；入局 queue 不出 fate_chapter 项、lines.fate 追加「（已搁置）」标记；戏剧/链/诺言等其余系统照常（搁置的只是主线，不是世界）。
- 搁置不设次数/时长上限，不扣任何数值，不影响死亡封存（封存口径 §3.8 对 shelved 线同等适用，status 先按结局改写 completed/broken/inherited）。

### 3.10 验收

- **FT-01（方案 A1）** 新角色降生后首次登录响应内已建线：`fate_threads` 有行、status=active、6 章齐全（idx0 active、余 locked）、`_status_dict.fate.thread` 可见标题与当前章目标。
- **FT-02（方案 A2）** 六级种子各构造一次（P0 未竟/P1 世仇见 §4/P2 影子最强/P3 本世 xue 链/P4 宗门/P5 出身兜底——P0 与 P1 的构造在转世场景下完成），生成线的 seed_source 与事实逐个一致；同场构造影子最强为负值与 xue 链并存时取 P2（优先级断言）；未竟「二居其一」正/负例各一（§3.3 规则）。
- **FT-03（方案 A3）** 打完一章：触发其 trigger 事件（如 T5 到访地点）后，章 status=done、下一章激活且其 checked goal 以 instance=`<tid>:c<idx>` 挂入 goals、入局 queue 出现 fate_chapter 项；全程断网/无 Key 环境复测一遍结论不变。
- **FT-04（方案 A4）** 死亡封存：角色死亡后线 status ∈ {completed, broken, inherited} 与结局事实一致，LifeTrace.fate_summary 含命途前缀段、unfinished_prop 按 §3.8 优先级取 thread 未竟；转世后新线种子/命题与未竟之志的对应符合 §3.3（同一 NPC 被复用为对手/引路人的断言在 P0/P1 场景下成立）。
- **FT-05（方案 A5）** 数值对账（红线）：构造「章节了结（含一条 chain_resolved 章）」全流程，逐项对账——主线相关全部数值变动（灵石/修为/业力/功德/道心/态度/寿元）与**同一事实在无线对照组**（线 shelved 全程）下原系统落账逐项相等；静态检索证明 `core/fate_thread.py` 不 import 任何数值发放/扣减入口（钱包/灵石/修为写函数），其写操作只有 fate_threads 仓储与 goals 挂载。
- **FT-06（方案 A7 全量）** 章节判定式复算：短/中/终局三层各构造 2 个 check（含新 kind 各 1），用既有账数据离线重算与线上 evaluate 结果逐个一致；新 kind 三个（visit_location/promise_kept_count/chain_resolved）各有正/负例；thread_climax 只在章节派生后求值的顺序断言（构造 idx4 done 而命题未判的中间态，单步求值后命题翻 done）。
- **FT-07** 窗口改道：把当前章 goal 的 deadline_at 拨到过去，求值后章 failed、下一章激活且 summary 含改道记、unfinished_note 候选已记；主线 status 仍 active（不 broken）。
- **FT-08** 搁置口径：`/命途 搁置` 后越过原 deadline 求值，章节不 failed；`/命途 续` 后 deadline 已顺延搁置时长（数值断言）；搁置中入局 queue 无 fate_chapter 项、lines.fate 带「（已搁置）」。
- **FT-09** 收编一致：建线瞬间 `thread.origin == char.origin` 逐字相等（有 origin 者）；老角色（origin 空）建线后 thread.origin == {} 且种子走 P3–P5；ensure_thread 连调两次只一行线（幂等）。
- **FT-10** 防重：同账户构造连续两世同种子同对手，第二次的 kind 序列与第一次不同（轮换生效）或带 `signature_forced: true` 标记（无可换时的诚实降级，二者必居其一）。
- **FT-11** 导演门禁：`validate_seed_hint()` 对含数值键（stones/exp 等）的建议 dict 剥离后只剩合法四键；npc_id 不在册/location 不在 WORLD_LOCATIONS 者被拒（函数级正/负例）。
- **FT-12** 零 tick 扫描：静态检索证明 fate 引擎无 tick/定时调用点（调用点只在 §3.6 清单内）；tick 跑满一个导演周期（480s 等价模拟）后，未经任何 T 点的角色其章节状态不变（负例）。

---

## §4 · 线一之二：世仇强制植入

### 4.1 现状锚点（实测）

- 杀伐记录的现查口径（一期/继承轮先例）：`LegacyEngine._snapshot_shadow` 在死亡时把态度账（|value|≥30）与 KarmaLink 折算（恩/师徒/结拜→+，仇/怨→−，strength×10 钳 [10,40]）合并成 trace.shadow；玩家间旧缘由 `core/inheritance.py` 按旧角色 id **现查 KarmaLink 孤儿行**（link 的一端是已死旧角色 id、行仍在 `karma_links` 表）。因果链在死亡时消散未了结者（karma 轮口径），已 resolved 的 xue 链行保留在 `karma_chains` 表（player_id=旧角色 id 可查）。
- 一期 origin 的 foe 通道：`OriginEngine._build_package` 的 `pick("foe")` 硬校验在世 + `realm.tier ≤ char.realm.tier + 1`；foe 态度 [−45,−15] 经 `shift_attitude(reason="origin")` 落账 + `ensure_link(仇, strength=1)` 种子边（不起链）；影子覆盖者（covered_ids）在选人时排除，影子优先（一期 §3.10）。

### 4.2 选人算法（新函数 `FateThreadEngine.select_vendetta(account, new_char, now) -> Optional[dict]`，写死）

输入：`account.traces[-1]`（无 trace → 返回 None）。候选来源按序取**首个有候选**的来源：
1. **上世 xue 链**：`KarmaChainRepository.list_by_player(traces[-1].character_id)` 中 kind=`xue` 的行（任何 status），取 created_at 最新一条，其 counterparty_id 为「血仇关联 NPC」；
2. **KarmaLink 孤儿行**：`KarmaLinkRepository` 现查一端为旧角色 id、另一端为 NPC（user_id 以 npc_/ai_npc_ 开头）且 link_type ∈ {仇， 怨} 的行，取 strength 最大一条的 NPC 端；
3. **负值影子**：trace.shadow 中 value ≤ −30（`SHADOW_MIN_ABS`）者按 |value| 降序。

对来源给定的关联 NPC（记为「仇源」），定植入者：
- 仇源在世且 `tier ≤ new_char.realm.tier + 1` → 植入者 = 仇源本人；
- 否则（仇源已死/不在册/超界）→ **同门/后人**：ROSTER 中 sect == 仇源 sect（仇源无 sect 时改走与仇源有 KarmaLink「师徒/结拜」边的在世 NPC）、在世、`tier ≤ new_char.realm.tier + 1` 者，按 (agenda==revenge 优先， tier 升序， uid 序）取首位；仇源本人以 `vendetta_for` 身份只记引用不植入；
- 同门/后人亦无 → 降级：取来源 3 的首位在世且合 bounds 者为植入者（仇源记为该人）；
- 全部落空 → 返回 None（本世无世仇，origin foe 走一期随机，seed 顺延 P2——诚实降级，不硬造人）。

植入者不得是影子已覆盖者（covered_ids，与 origin 同口径）；若选定者恰在 covered_ids 内，则在同来源内顺延下一候选，无下一候选则按上一条降级链继续，全空返回 None。

### 4.3 植入口径（走 origin 既有通道，K3）

- 转世编排（`World.reincarnate`）顺序变更一处：在 `apply_karma_shadow` 之后、`OriginEngine.generate_for_new_life` 之前调 `select_vendetta`，结果以新入参 `vendetta={"npc_id":…, "for_name":…, "for_id":…}` 传入生成器（新入参缺省 None，一期调用方零改动）。
- 生成器内：`_build_package` 的 foe 选人改为**先试 vendetta 植入者**——其通过既有硬校验（在世/bounds/未被 covered）时直接定为 foe（占 foe 名额，pattern 中其余 foe 位不再另抽），不通过则丢弃 vendetta 走原随机（并在 origin 块记 `vendetta_dropped: true` 与原因键）。植入者的 init_value 在 foe 值域内取深半区：`rng.randint(-45, -30)`（仍在 [−45,−15] bounds 内，A6 复验不破）。
- origin 块 relations 中该条只增两键：`"vendetta": true, "vendetta_for": "<仇源名>"`；KarmaLink 种子边 note 改为 `世仇：替{仇源名}讨前世血债`（仇源即本人时为 `世仇：前世血债未清`）；signature 的 primary 仍取 foe（与一期口径一致，世仇世的 signature 天然带植入者 id）。
- 主线引用：ensure_thread 的 P1 判定 = origin.relations 中存在 `vendetta: true` 条目（单一事实源，不另查），seed_ref 与 antagonist 均取该条 npc_id；§3.3 的 P0 判定先于 P1——未竟之志占种子位时，世仇植入者仍在出身关系里（foe 照常），只是主线种子顺延，此时 antagonist 取未竟关联人，世仇者在冲突章 trigger 绑定的 npc 候选里优先（§3.5 表 idx3 的 npc_id 绑定序：未竟关联人 > 世仇植入者 > 种子 NPC，写死）。

### 4.4 验收

- **VD-01** 三来源各构造一次（上世 xue 链/KarmaLink 仇孤儿行/负值影子），转世后 origin.relations 均含 `vendetta: true` 条目且 npc_id 与来源推导一致。
- **VD-02（三处一致对账）** 同一世仇：relations 条目的 npc_id == 态度账中该 NPC 对新角的现值所属人且值 ∈ [−45,−30] == KarmaLink 仇边的对端 == thread.seed_ref（seed_source=vendetta 时）；三处任一不一致即不过。
- **VD-03（降级口径）** 仇源已死场景：植入者为其同 sect 合 bounds 者且 `vendetta_for` == 仇源名；仇源超界（化神）在世场景：不植入本人、改植同门低阶者；无同门且无影子候选场景：vendetta 为 None、origin foe 为普通随机且块内无 vendetta 条目。
- **VD-04（bounds 不破）** 世仇世批量转世 50 次：全部植入者满足一期 foe bounds（tier ≤ 起始+1、值域、relations ≤4、总分中位带），一期 A6 口径（P2-02）复跑仍全过。
- **VD-05** 影子优先不冲突：植入候选与影子覆盖者同人时顺延/降级按 §4.2 末段执行，该 NPC 的态度以影子值为准、origin 不对其调 shift_attitude（一期 P4-03 同源断言扩展）。

---

## §5 · 线一之三：NPC 主动戏剧扩展（NpcProactiveEngine 扩五类）

### 5.1 现状锚点（实测）

`core/npc_proactive.py NpcProactiveEngine.maybe_engage`：按态度概率开口（hostile 0.55 / ally 0.50 / friendly 0.40 / wary 0.35 / neutral 0.22）、进程内 90 秒冷却、AI 预算闸（5 分钟窗口，`NPC_PROACTIVE_AI_BUDGET_PER_TICK=3`）、AI/本地双路与 source 标注、开口可带 ±5 内 attitude delta（经 shift_attitude）。现状只寒暄不办事、无戏剧类型、无待回应状态。本节**只加戏剧层**（类型判定+待回应+回应落账），不改 maybe_engage 的节流骨架与寒暄行为。

### 5.2 五类戏剧定义（触发全部读既有账，数值写死；F9 口径）

新增 `DramaEngine`（置 `core/npc_proactive.py` 同文件）：`evaluate(player, *, trigger, now) -> List[drama_event]`，trigger ∈ {"login", "travel"}。每评估点**至多新建 1 件**（示好亦然）；多类同时可触发时按优先级取首位：**背叛 > 挑衅 > 牵连 > 求助 > 示好**，同类多候选时取态度极值最大者（背叛/挑衅取最负、求助/示好取最正、牵连取链 strength 最大）。

| 类型 key | 触发条件（AND 全部满足，阈值写死） | 通道 | 回应选项 |
|---|---|---|---|
| `betrayal` 背叛 | 玩家对某 NPC 有未了诺言（promiser=玩家、promisee=该 NPC、status ∈ {PENDING, ACTIVE}）且该 NPC 对玩家态度 ≤ −15（wary 及以下）；**或** 玩家与该 NPC 有 KarmaLink「仇」边 strength ≥3 且有未了诺言 | 队列（不当面，先兆） | `confront` 摊牌 |
| `provoke` 挑衅 | NPC 对玩家态度 ≤ −40（hostile）且同场；**或** 与玩家有 fermenting 的 chou/xue 链（counterparty=该 NPC，不限同场） | 同场当面 + 队列；异地仅队列 | `fight` 应战 / `avoid` 避走 |
| `involvement` 牵连 | 有 fermenting 因果链，其 counterparty 的**同 sect 者**或与 counterparty 有 KarmaLink「师徒/结拜」边者（第三方，在世、≠counterparty）对玩家态度 ≥ −15 | 队列 + 同场当面 | `mediate` 劝和 / `harden` 硬顶 |
| `help` 求助 | NPC 对玩家态度 ≥ +15（friendly 及以上）、其 ROSTER agenda ∈ {treasure, survive}、`npc.realm.tier ≤ player.realm.tier`、同场 | 同场当面 + 队列 | `accept` 接取 / `decline` 婉拒 |
| `favor` 示好 | (a) kind=en 的因果链与该 NPC 在最近 1 游戏日内 resolved（resolved_at ≥ now − SECONDS_PER_GAME_DAY）；**或** (b) 最近 1 游戏日内有一条 RELATION 留痕（actor=该 NPC、target=玩家、delta>0、after_label ∈ {friendly, ally}）且该留痕 ts 未被示好消费过（消费标记记 quota KV） | 当面（同场时）或队列 | 无（自动落账，`ack` 知晓仅销项） |

### 5.3 后果落点（全部既有系统，戏剧本身零数值发放）

| 类型/选项 | 落账（逐项写死） |
|---|---|
| help / accept | `GoalEngine.add_opportunity(player, <模板标题>, <模板详情>)` 挂机缘目标一条（标题/详情由 NPC agenda 与地点拼装）；目标本身无奖励数值（目标系统既有口径） |
| help / decline | `shift_attitude(npc, player.id, -2, reason="戏剧·求助被拒")`（既有 shift 口径内，RELATION 留痕自动产生） |
| favor（自动） | NPC 以自有灵石赠礼：`amount = min(20, npc.spirit_stones)`，npc.spirit_stones −= amount、player.spirit_stones += amount（**转移非发放**，双方以 CharacterRepository.save 落盘）；`shift_attitude(npc, player.id, +3, reason="戏剧·示好")`。npc 灵石为 0 时只落态度 +3 与台词 |
| provoke / fight | 转调既有斗法入口（server handle 的 `/斗法 <npc名>` 同一分发路径，CLI 同口径）；胜负与一切数值由战斗/因果系统裁决，戏剧层不预设结果 |
| provoke / avoid | `rumors.note_avoid_fight(player.name, npc.name)`（§6，truth 0.85）；无态度变化、无任何数值惩罚 |
| betrayal / confront | 两步：① 呈现时已先兆——`rumors.add_rumor` 一条风闻（truth 0.85，tags=["betrayal", npc名]，文本模板见 §5.5）+ 若玩家与该 NPC 有 kind=nuo 的 fermenting 链，经 `KarmaChainEngine.nudge_ferment(chain_id, days=-2)` 加速发酵（§5.3 的唯一链写口）；② 回应摊牌只做呈现转向（队列项 target 指交谈，打开与该 NPC 的既有交谈），诺言/链的结算仍走其既有到期与结算路径，戏剧不提前结算、不额外扣数值 |
| involvement / mediate | 第三方态度 ≥ +15 时劝和成功：涉事链为 en 时 `nudge_ferment(days=-3)`（加速讨恩），为 chou/xue 时 `nudge_strength(delta=-1)`（下限 1）；`shift_attitude(第三方, player.id, +3, reason="戏剧·牵连劝和")`。第三方态度 < +15 时劝和不成：仅台词与 +0 落账（如实呈现「没劝动」） |
| involvement / harden | `shift_attitude(第三方, player.id, -3, reason="戏剧·牵连硬顶")`；涉事链为 chou/xue 时 `nudge_strength(delta=+1)`（走因果链既有续链规则）；en 链不受影响 |

**因果链微调口（本轮唯一新增链写口，钳制写死）**：`KarmaChainEngine.nudge_ferment(chain_id, *, days)` 只改 ferment_until：新值 ∈ [now, 原 ferment_until]（只许提前不许延后，days ∈ [−3, 0]）；`nudge_strength(chain_id, *, delta)`：delta ∈ {−1, +1}，结果钳 [1, `KARMA_CHAIN_STRENGTH_CAP`=8]。两函数只许被 DramaEngine 调用（代码注释与测试断言调用面），每次调用写一条 Chronicle 留痕（actor=戏剧，文本含 chain id 与前后值）供对账。

### 5.4 频控三闸与状态（K4，数值写死）

- **总闸**：每玩家每**现实日**（本地日期，沿 rumors ambient 的日期口径）戏剧事件 ≤3 件，计件类型 = {help, provoke, betrayal, involvement}（**示好不占额**）；计件时点 = 事件**新建**时（回应与否不退额）。
- **同人闸**：同一 NPC 对同一玩家 1 **游戏日**（`floor(now / SECONDS_PER_GAME_DAY)`）内至多新建 1 件（**含示好**）。
- **触发点闸**：只在两个既有触发点评估——登录入局（`build_entry` 步骤 ⑤.5，`allow_proactive=True` 时，位于 maybe_engage 之后）与迁跃落点（`/go` 成功段，与 maybe_engage 同段）。**零新增 tick 扫描**；评估本身纯读既有账 + 至多新建 1 件，毫秒级。
- 状态两处 KV（WorldStateRepository，沿图鉴/预算先例）：`drama_quota:{char_id}` = `{day: "YYYY-MM-DD", count: int, npc_game_day: {npc_id: <game_day int>}, favor_consumed_ts: [float]}`；`drama_pending:{char_id}` = 待回应事件列表，事件形状 `{id: "dr_<10hex>", type, npc_id, npc_name, chain_id, promise_id, text, source, options: [{key, label}], created_at, expires_at}`，`expires_at = created_at + 86400`（1 现实日），过期事件在下次评估/回应时惰性清除（过期无任何后果）。
- 当面通道的呈现：迁跃落点新建的同场事件，其 text 同时经既有 proactive 返回通道下发（opening 形状 `{npc, line, source, drama_id, drama_type}` 只增字段）；登录通道只进队列（§8.2）。

### 5.5 AI 与本地模板分工（沿方案 §4d）

类型判定、触发、后果数值 **100% 规则**。台词：AI 可用时走既有 `npc_proactive` scene（payload 只增 `drama_type` 与事实字段：诺言 desc/链 kind/第三方关系名——全部既有账数据），不可用/超预算走本地模板：每类型 × 态度档（hostile/wary/friendly+）各备 ≥1 条定稿模板（实现岗按本节事实字段拼装，变量只取人名/地点/诺言与链的既有文本）。AI 全挂时五类照常触发、台词为模板、后果无缺失（D5）。

### 5.6 验收

- **DR-01（方案 D2）** 构造 hostile NPC 同场：挑衅在频控内触发（事件进 pending + 队列）；连评 4 次评估点，总闸断言当日计件 ≤3；同 NPC 同游戏日第二次评估不再新建（同人闸）。
- **DR-02（方案 D2）** 挑衅回应：`fight` 实际进入既有斗法分发（以斗法结算记录断言）；另一构造走 `avoid`：角色全部数值字段逐项不变、传闻池新增 truth=0.85 的避战条目。
- **DR-03（方案 D3）** 恩链了结后 1 游戏日内示好触发：赠礼 amount == 玩家灵石增量 == NPC 灵石减量（转移对账）、态度增量 == +3 且 RELATION 留痕 reason 为「戏剧·示好」；示好不占总闸额（同日再构造 3 件计件戏剧仍可触发）。
- **DR-04** 背叛：未了诺言 + 态度 ≤−15 构造下背叛事件新建，传闻池出现其先兆条目，nuo 链 ferment_until 恰提前 2 游戏日（nudge 钳制断言：不得早于 now）；摊牌回应不改变诺言 status（结算仍走既有路径的负例断言）。
- **DR-05** 牵连：构造 fermenting 仇链 + 其 counterparty 同门第三方，牵连事件新建且 actor 为第三方；`mediate`（第三方态度 ≥15）后链 strength −1（chou）或 ferment −3 日（en），`harden` 后第三方态度 −3 且 chou 链 strength +1（钳顶 8 的边界用例）。
- **DR-06** 求助：`accept` 后 goals 新增一条 source=omen 的机缘目标且标题与 NPC/地点对应；`decline` 后态度恰 −2、RELATION 留痕 reason 为「戏剧·求助被拒」；NPC 境界高于玩家时不触发（负例）。
- **DR-07（方案 D5）** AI 全关（无 Key）环境五类各触发一次：台词全部为本地模板（source=local）、后果落账逐项与 DR-02~DR-06 同口径无缺失；待回应事件过期（拨 expires_at 到过去）后惰性清除且无任何落账。

---

## §6 · 线一之四：传闻玩家事迹写入口补全（core/rumors.py）

### 6.1 现状锚点（实测，F2）

传闻池：`add_rumor(text, origin, tags, truth)`（上限 40、TTL 7 现实日、heat 机制）；既有规则写入口 5 个：`note_kill`（truth 0.95）、`note_trade`（0.85）、`note_auction`（0.9）、`note_collusion`（0.65）、`note_apocalypse`（1.0），另死亡传闻在 `settle_death` 内直调 `add_rumor`（truth 1.0）。引用口实测：`pick_for_npc` 无调用方（保留为函数级取闻口）；`lorebook.lore_prompt_block` 走 `list_rumors` 注入交谈上下文（已接线 npc_mind/world 两处）。

### 6.2 新增写入口（写死，全部 try/except 包裹、失败不炸主流程，沿既有 note_* 纪律）

| 函数 | truth | tags | 调用点（单一漏斗） | 文本模板（变量为事实） |
|---|---|---|---|---|
| `note_breakthrough(name, realm_name, location)` | 1.0（天道昭告类，同 apocalypse 先例） | `["breakthrough", name]` | 大境界突破**成功**的两服务端出口（`World._breakthrough` 与心魔后继段）在 attempt 返回 is_major 且 success 后同位调用；CLI 同名突破路径同口径 | 「听闻于{location}突破至{realm_name}，天象为之一动。」 |
| `note_chain_resolved(player_name, npc_name, kind_cn, polarity)` | 0.9（系统裁决事实的转述，同 auction 先例） | `["chain", player_name]` | `KarmaChainEngine` 兑现落账的引擎内单点（status 转 resolved 的同一函数内，含 tick 与惰性 advance 两路） | 「听说与的一桩{kind_cn}因果已了——{恩怨两清/梁子更深}。」（polarity 决定尾句） |
| `note_arc_participation(name, arc_title, choice)` | 0.85（转述类） | `["arc", name]` | `core/world_arc._settle_climax` 内，对 participants 前 3 名逐人调用 | 「决算之时，曾{应劫/避祸}，江湖记下了这一笔。」 |
| `note_avoid_fight(name, npc_name)` | 0.85 | `["avoid", name]` | §5 provoke/avoid 回应点 | 「遇挑衅，避而不战，有人说他怯，也有人说他稳。」 |

去重口径（新函数共用 `_note_once` 辅助）：同 tags 关键键 + 同文本已在池中（未过期）时不重复 append，只给既有条目 heat+1（沿 pick 的 heat 机制）。

### 6.3 验收

- **RM-01（方案 D4 改造口径，F2）** 大境界突破后传闻池出现 truth=1.0 的突破条目；另一角色经 `pick_for_npc` 可命中该条（函数级）、且其交谈上下文的 `lore_prompt_block` 输出含该条文本（接线级）。
- **RM-02** 因果链经 tick 与惰性 advance 两路各了结一条，均只产生一条 resolved 传闻（引擎单点 + 去重断言，连调两次 advance 不重复）。
- **RM-03** 世界弧决算后，participants 前 3 名各有一条 truth=0.85 的参与传闻，choice 文案与参与事实一致；未参与者无条目（负例）。
- **RM-04** 既有五入口行为不回归（note_kill/trade/auction/collusion/apocalypse 的 truth 与文本逐字复测）；传闻池上限/TTL 口径不变。

---

## §7 · 线一之五：一生评语 AI 润色（可选路径）

### 7.1 现状锚点（实测）

一期评语在 `LegacyEngine._fate_fields`（`core/legacy.py`）内同次生成：`life_epitaph = 汇总句（compressed） + 定性句（模板选句） + 尾句（死因类）` 三段拼接为**单个字符串**，AI 无从只润色中间段；生成点在 `settle_death` 的 `_build_trace` 内（结算路径，可能持锁）。方案口径：润色只许动定性句、≤60 字、输入只许规则汇总数据、落点不变。

### 7.2 分段字段与润色契约（写死）

- `LifeTrace` 新增 4 字段（默认值保旧档零迁移）：`epitaph_head: str = ""`（汇总句）、`epitaph_line: str = ""`（定性句）、`epitaph_tail: str = ""`（尾句）、`epitaph_polish: str = ""`（`""` 未试 / `"done"` / `"failed"` / `"skipped"`）。一期 `_fate_fields` 改为同时返回三段，`life_epitaph` 恒 = head+line+tail 拼接（既有三落点读 life_epitaph 一字不改）；老 trace 三段为空、polish 视为 skipped（不回填、不润色）。
- 润色函数 `LegacyEngine.try_polish_epitaph(account, *, now=None) -> bool`（新逻辑可置 `core/legacy.py` 同文件）：只处理 `account.traces[-1]` 且其 character_id 对应本世、head/line 非空、polish == "" 者。输入 payload **只许**规则汇总定性字段：`{family_text, proposition_kind, proposition_done: bool, realm_name, cause_category, old_story_kind}`——**禁止**携带任何数值字段（灵石/修为/寿元数值/态度数值）与玩家自由文本。经 `ai.router.invoke` 以新 scene 名 `epitaph_polish` 调用（scene 注册与 prompt 模板由实现岗在 ai 层按既有 scene 先例补，prompt 须明示只回一句 ≤60 字定性句）。
- 输出校验（全过才采纳）：str、去空白后 1–60 字、不含数字与「灵石/修为/寿元/功德/业力」等数值词（正则黑名单写死于实现）、不含换行。采纳时：trace.epitaph_line = 润色句、trace.life_epitaph = head+新line+tail、polish="done"，经账户仓储既有 save 路径落盘；任一校验不过或 AI 不可用/超时/异常 → polish="failed"、三段与 life_epitaph **逐字不变**。超时口径沿 v0.3.5 的 LLM 超时（12 秒），不在润色路径另设重试（单次尝试，circuit breaker 既有口径自动覆盖）。
- **调用点红线**：只许在死亡结算**完成落盘之后、锁外**由服务端死亡流程以单飞守护线程异步触发一次（先例：一期 first-night 的锁外异步单飞调度）；**禁止**出现在 `settle_death`/`_build_trace` 同步路径、任何登录路径（含 dead_payload 组装——它只读当时的 life_epitaph，是模板还是润色版取决于异步是否已完成，诚实呈现）、任何 tick 路径。CLI 死亡路径不触发（polish 留 ""，评语为模板版，口径明示）。

### 7.3 验收

- **EP-01（方案 A8 扩展）** AI 可用（mock 返回合规句）时：异步完成后 trace.life_epitaph 的定性段被替换、head/tail 逐字不变、墓碑文本含润色后评语、三落点（墓碑/仪式余韵/下一世出身卡「前世曰」）读到的都是润色版；polish="done"。
- **EP-02** AI 返回违规句（超 60 字 / 含数字 / 含数值词）与抛异常/超时各一次：life_epitaph 与模板版逐字相同、polish="failed"、结算与转世流程无任何阻塞或重试（调用次数断言 = 1）。
- **EP-03** 输入面审计：mock 捕获 invoke 的 payload，断言键集恰为 §7.2 白名单、无任何数值型 value。
- **EP-04** 红线静态断言：`try_polish_epitaph` 的调用点只在死亡流程锁外异步一处；登录/dead_payload/tick 路径无调用（检索断言）；老 trace（四字段为空）调用时直接 skipped 不发 AI 请求。

---

## §8 · 线一呈现契约（给前端岗的接口）

### 8.1 `_status_dict` 只增清单（F1 口径）

| 键 | 形状 | 说明 |
|---|---|---|
| `fate.thread`（`fate` 既有键内只增子键） | 无线时 `null`；有线时见下 | 既有 `boons/pending/power_bonus` 三子键一字不动 |
| `location_image`（顶层只增一键） | `"/assets/scenes/<slug>.webp"` 或 `""` | 当前地点场景图（§9.4 映射），无映射为空串、前端不渲染图位 |

`fate.thread` 全量结构（定稿）：

```jsonc
{
"id": "ft_…", "title": "…", "status": "active|shelved|completed|broken|inherited",
"seed_source": "vendetta", "seed_ref": "<npc_id>",
"antagonist": {"id": "…", "name": "…"} | null,
"patron": {"id": "…", "name": "…"} | null,
"final_proposition": {"text": "…", "status": "active|done|failed"},
"current_chapter": 2,
"chapters": [{"idx": 0, "group": "setup", "kind": "visit", "tier": "short",
"title": "…", "goal_text": "…", "status": "done|active|locked|failed",
"deadline_at": 0.0}],
"shelvable": true, // status==active 时 true
"origin_present": true
}
```

下发实现：`core/ceremony.py fate_block()` 只增 `thread` 子键（数据来自 `FateThreadRepository.list_by_player` 最新未封存线或刚封存线——角色死亡后 status 视图以 dead_payload/legacy 为准，`_status_dict` 对死者不下发 thread 不是问题，明示）；无新表查询进热路径的顾虑：list_by_player 走 player_id 列查询（§3.2），与 karma_chains status 块同量级。

### 8.2 入局（build_entry）只增清单

- 拼装顺序只增两步（沿一期 §2.2 的写死顺序）：③.5 `FateThreadEngine.evaluate_for`（在 ③ 求值之后、④ 组装之前；其新激活章/新翻转章各成一条 queue 项）；⑤.5 `DramaEngine.evaluate(trigger="login")`（在 ⑤ maybe_engage 之后；新建事件成一条 queue 项）。
- queue 新 kind 两类（priority 写死，沿一期 priority 表插入）：`fate_chapter` priority=2（与 goal_flip 同级，排其后——拼装追加顺序即同级序）、target=`{"view": "sanctum"}`（命盘命途段）；`drama` priority=2（排 fate_chapter 之后）、target=`{"command": "/回应 <drama_id>"}`，drama 项只增 `options: [{key, label}]` 字段供前端渲染回应按钮（其余 kind 无此字段，前端缺失即不渲染按钮）。
- `lines.fate` 取值优先级变更：有线时 = `命途「{title}」：{当前章 title}（{状态}）· 命题：{final_proposition.text}（{状态}）`（shelved 时章状态位显「已搁置」）；无线时回退一期口径（一期拼装逻辑保留为回退分支）。lines 其余两线、queue 截断 8 条/highlight ≤3/rest_count/empty 口径全部不变。
- 拼装耗时口径：③.5 与 ⑤.5 均为纯本地账读 + 至多各 1 次仓储写，计入一期 P1-03 的拼装层测法复测（阈值不变，见 §11）。

### 8.3 交谈「旧账」行（本轮做，定稿）

**做。** 理由：一期 §8 第 4 条点名移交二期；方案 §4d 明列为关系可见化第三处；数据全部现成（诺言 `_involving`、链 status_summary、RELATION 最近一条），成本为一次只读拼装，不引入新状态。契约：
- 交谈开启的服务端返回（server handle 的交谈开启路径与 CLI 同源文本）只增 `old_account` 字段：`{open_promises: int, fermenting_chains: int, nearest_chain_game_days: float|null, last_relation: "<summary>"}`，数据源：与该 NPC 相关的未了诺言数（promiser/promosee 任一端为该 NPC 且 status ∈ {PENDING, ACTIVE}）、玩家全部发酵中链数（`KarmaChainEngine.status_summary` 既有口径，其中与该 NPC 相关者另计 `chains_with_npc: int` 一并下发）、最近一条 actor=该 NPC 的 RELATION summary。
- 前端呈现：交谈弹窗/交谈页顶部一行「旧账：未了诺言 N · 与他发酵中因果 M · 最近：{summary}」（桌面与移动同文案，移动计入 §10 预算）；CLI 交谈文本在开启行后加同一行。字段缺失（老前端/异常）即不渲染，沿降级惯例。

### 8.4 新命令（恰 2 条，命令目录 100 → 102）

| 命令 | 语义 | 落点 |
|---|---|---|
| `/命途`（别名 `/fate_thread`） | 无参 = 主线面板文本（标题/种子来源/章节列表/命题/搁置状态，CLI 与 server 同源）；`/命途 搁置`、`/命途 续` = §3.9 切换（assert_alive 门禁，沿道体守恒律） | `core/fate_thread.py` 提供 panel_text 与 shelve/resume；server 与 cli 双端分发 |
| `/回应` | 无参 = 列待回应戏剧（id/类型/NPC/选项）；`/回应 <drama_id> <option_key>` = 按 §5.3 落账并销项（事件不存在/已过期/选项非法均明确报错且零落账） | `core/npc_proactive.py` DramaEngine.respond()；双端分发 |

### 8.5 验收

- **UI-01** `_status_dict` 只增断言：既有键集不缺失（沿 test_status_dict 既有口径），`fate` 既有三子键逐字不变，`fate.thread` 形状与 §8.1 定稿逐键一致（无线角色为 null）。
- **UI-02** 入局：构造章节激活与戏剧新建各一次，登录响应 queue 含 fate_chapter 与 drama 两项（priority 与 target 形状合 §8.2）、highlight 仍 ≤3；无线无戏剧的老角色登录响应与一期逐键一致（entry 其余字段回归）。
- **UI-03** 旧账行：构造与某 NPC 的未了诺言 1 条 + 发酵链 1 条 + RELATION 1 条，交谈开启返回 old_account 四值与账面一致、双端交谈页实际渲染该行（截图 S-D3/S-M3）。
- **UI-04** 命令可达：命令目录全量（100 既有 + 新增 2 = 102 条）逐条可达性回归通过（沿一期 P1-05 口径）；`/命途` 面板文本与 fate.thread 下发数据一致（同源断言）。
- **UI-05** `location_image`：在 10 个地点间迁跃，status 的 location_image 与 §9.4 映射表逐地一致；变体地点名（落霞山灵泉(野外)）映射同图；无映射地点为空串。

---

## §9 · 线二：图库扩充到 139 张

总原则沿图库轮：唯一事实源仍为 `core/gallery_assets.py` 的 `GALLERY_ASSET_KEYS`（本轮由 38 扩至 **139**）；托管双闸（正则 + 常量）与图鉴全集共用同一集合；解析函数全部纯函数、确定性、不依赖 AI、**不按名字猜性别**；资产统一水墨仙侠风、webp、约 640px、单张 ≤120KB（现有 38 张实测均值约 67KB、最大约 183KB——存量最大张超标为既有事实，本轮**新增**资产以 ≤120KB 为验收线，存量不追溯，见 §9.11）。

### 9.1 NPC 单人图 37 张（本轮第一优先，方案 §9 口径 9）

**键名定稿**：`portraits/npc-<slug>`，其中 `slug = uid 去掉 "npc_" 前缀后把 "_" 换为 "-"`（如 `npc_qy_01` → `portraits/npc-qy-01`）。理由（F3）：① uid 是 ROSTER 的稳定主键，按 uid 对号可机器断言（37 uid ↔ 37 键 ↔ 37 文件三方一致）；② uid 原样含下划线会被 `/assets/` 正则闸（`[a-z0-9-]+`）拦死，去下划线映射是满足现行正则的最小变更（正则闸本轮只扩目录段，不动文件名段，见 §9.9）；③ 映射双向确定：`key → uid = "npc_" + slug.replace("-", "_")`，解析函数 `npc_single_key_for_uid(uid)` 与 `npc_uid_for_single_key(key)` 互为逆运算，测试可全量往返断言。

**解析优先级（`npc_avatar_key_for_character` 变更，写死）**：角色名命中 ROSTER（沿现行按名查册逻辑）→ 返回其 uid 的单人键；未命中（动态/无名 NPC）→ 回退现行原型解析（`resolve_npc_archetype` 四原型键保留作兜底，规则一字不改）。`note_npc_encounter` 点亮口径随之变更：命中 ROSTER 者点亮单人键（不再点亮原型键），动态 NPC 仍点亮原型键。

**37 键全表（uid ↔ 键 ↔ 人名，定稿）**：

| uid | 键 | 人名 | uid | 键 | 人名 |
|---|---|---|---|---|---|
| npc_qy_01 | portraits/npc-qy-01 | 玄清子 | npc_jy_02 | portraits/npc-jy-02 | 血衣侯 |
| npc_qy_02 | portraits/npc-qy-02 | 静虚真人 | npc_jy_03 | portraits/npc-jy-03 | 厉无锋 |
| npc_qy_03 | portraits/npc-qy-03 | 云鹤道人 | npc_jy_04 | portraits/npc-jy-04 | 骨姬 |
| npc_qy_04 | portraits/npc-qy-04 | 丹霞子 | npc_jy_05 | portraits/npc-jy-05 | 血刀老祖 |
| npc_qy_05 | portraits/npc-qy-05 | 林惊羽 | npc_jy_06 | portraits/npc-jy-06 | 毒娘子 |
| npc_qy_06 | portraits/npc-qy-06 | 苏婉清 | npc_jy_07 | portraits/npc-jy-07 | 阿骨 |
| npc_qy_07 | portraits/npc-qy-07 | 石猛 | npc_sh_01 | portraits/npc-sh-01 | 金满堂 |
| npc_qy_08 | portraits/npc-qy-08 | 赵小满 | npc_sh_02 | portraits/npc-sh-02 | 铁算盘 |
| npc_qy_09 | portraits/npc-qy-09 | 青萝 | npc_sh_03 | portraits/npc-sh-03 | 柳三娘 |
| npc_wj_01 | portraits/npc-wj-01 | 剑圣·独孤败 | npc_sh_04 | portraits/npc-sh-04 | 陆仁贾 |
| npc_wj_02 | portraits/npc-wj-02 | 断岳剑尊 | npc_sh_05 | portraits/npc-sh-05 | 驼爷 |
| npc_wj_03 | portraits/npc-wj-03 | 白霜 | npc_sh_06 | portraits/npc-sh-06 | 小雀儿 |
| npc_wj_04 | portraits/npc-wj-04 | 赤霄 | npc_wd_01 | portraits/npc-wd-01 | 采药翁 |
| npc_wj_05 | portraits/npc-wj-05 | 墨离 | npc_wd_02 | portraits/npc-wd-02 | 赤练子 |
| npc_wj_06 | portraits/npc-wj-06 | 剑奴阿七 | npc_wd_03 | portraits/npc-wd-03 | 山君 |
| npc_wj_07 | portraits/npc-wj-07 | 小环 | npc_wd_04 | portraits/npc-wd-04 | 蜃楼客 |
| npc_jy_01 | portraits/npc-jy-01 | 幽冥老祖 | npc_wd_05 | portraits/npc-wd-05 | 海娘子 |
| | | | npc_wd_06 | portraits/npc-wd-06 | 盲眼琴师 |
| | | | npc_wd_07 | portraits/npc-wd-07 | 盗墓贼·孙九 |
| | | | npc_wd_08 | portraits/npc-wd-08 | 青州游侠·燕十三 |

出图依据与逐人要点见**附录 A**（37 人逐行：性别口径/年龄段/宗门服色/气质关键词，性别判定只用 `NPC_FEMALE_NAMES` 名单 + `npc_personas.py` 档案两处显式口径）。

### 9.2 玩家立绘补满 20 组合（契约变更，单列）

**键名定稿**：`REALM_KEYS` 由 6 扩为 10：`["fanren", "lianqi", "zhuji", "jindan", "yuanying", "huashen", "lianxu", "heti", "dacheng", "dujie"]`，新增 8 键 = `portraits/{male,female}-fanren`、`{male,female}-heti`、`{male,female}-dacheng`、`{male,female}-dujie`。玩家立绘总组合 = 10 境界 × 2 性别 = 20（补满）。
**`realm_key_for_tier` 映射变更（写死）**：tier 0 → `fanren`（不再借 lianqi）；tier 1–9 逐档直取；tier >9 钳 `dujie`；非法值回退沿现状（t=1 → lianqi）。
**图鉴派生联动**：`core/gallery.py derive_keys_from_character` 的本人图点亮由 `range(1, min(6, tier)+1)` 改为：已定相即含 `fanren` + tier 1..min(9, tier) 的本性别键（异性不点亮口径不变）；`GALLERY_GROUPS` 的人物两组由 REALM_KEYS 程序化生成（自动变 10），`KEY_CN` 的境界中文元组扩为（凡人/练气/筑基/金丹/元婴/化神/炼虚/合体/大乘/渡劫）。

**契约变更与既有测试影响（本小节为定稿口径，QA 岗按此修订断言）**：
| 既有断言 | 现状 | 变更后 | 理由 |
|---|---|---|---|
| `test_gallery_assets.py` G-3：`player_portrait_path("male", 0) == male-lianqi` | tier0 借练气 | 改断言 `male-fanren` | 本节定稿：凡人有专图，不再借图 |
| G-3：`player_portrait_path("female", 7) == female-lianxu` | tier≥7 封顶借炼虚 | 改断言 `female-heti`（另补 tier 8/9/10+ 三例） | 合体起逐档专图 |
| G-1：`len(GALLERY_ASSET_KEYS) == 38` 及三方一致 | 38 | 改 139（三方一致口径不变） | §9.9 总账 |
| `test_gallery_atlas.py` C-3：tier3 点亮集合断言 | 含 lianqi/zhuji/jindan | 集合另含 `fanren`（本性别） | 派生口径变更（见上） |
| C-4：`note_npc_encounter(金满堂) == ["portraits/npc-shanggu"]` | 点亮原型键 | 改断言 `["portraits/npc-sh-01"]`（金满堂命中 ROSTER） | §9.1 解析优先级变更 |
| C-5 / 前端契约：称号四档（10/20/30/38）与「图录大成」@38 | 四档 | 按 §9.10 新五档修订 | 全集扩大，阈值重标定 |
| G-5：`artifact_key_for("无名物", slot="armor") == mirror`、`(slot="boots") == fan`、subtype 法杖 → orb | 借代口径 | 按 §9.5 改断言 armor/boots/staff | 器型补齐的定稿映射 |
| `test_art_and_map_key_resolution`：`map_key_for_tier(5) == map-ancient` | tier≥4 同图 | 改断言 `map-celestial`（tier4 仍 ancient 不变） | §9.7 tier5 独立键 |
| 同上：风灵根 `art_key_for("吐纳术", 风根) == arts/sword`（注释「风无专图归 sword」） | 风归剑图 | 改断言 `arts/wind` | §9.6 风属性专图 |

其余既有图库断言（G-2 全图可取、G-6 缓存头、G-7 托管安全、原型枚举 `roster_archetype_table` 本身）口径不变、按新全集自动扩展覆盖面。

### 9.3 灵宠图 4 张

键按物种定稿（`core/pets.py PET_SPECIES` 的键即物种名，slug 为显式映射表 `PET_ASSET_SLUGS`，置 gallery_assets，禁止运行时拼音推导）：

| 物种（PET_SPECIES 键） | 倾向 | 键 |
|---|---|---|
| 青鳞蟒 | attack | `pets/pet-qinglinmang` |
| 疾风隼 | attack | `pets/pet-jifengxun` |
| 玄甲龟 | guard | `pets/pet-xuanjiagui` |
| 寻宝鼠 | treasure | `pets/pet-xunbaoshu` |

解析：新函数 `pet_key_for_species(species) -> str`（物种不在表内返回 `""`，AI 生成物种不配图不报错）。呈现挂点：灵宠面板/命盘 pet 块只增 `img` 字段（出战宠优先、无出战取首只活宠，沿 _status_dict 的 pet 块既有形状只增键）。点亮：`derive_keys_from_character` 增——名下活宠（state != dead）的物种键全部派生点亮（契约/喂养等既有流程经 unlock_from_character 自然覆盖，不新埋钩子）。

### 9.4 地点场景图 15 张

键规则 `scenes/<slug>`，slug 为下表定稿英文短名；映射表 `LOCATION_SCENE_KEYS`（地点名 → 键）与 `REALM_SCENE_KEYS`（秘境名 → 键）置 gallery_assets 为唯一事实源。地点组取 WORLD_LOCATIONS 去重 10 处（变体键映射同图：`落霞山灵泉(野外)` → luoxia-spring、`黑风绝渊(大凶)` → heifeng-abyss）；秘境组取代表 5 处（7 秘境中落霞古洞/剑冢残碑/万星遗迹/幽冥鬼市 4 处 + 副本锁妖古窟入口 1 处；黑风绝渊裂隙与灵药残圃、荒古兽巢不单出图，其所在地点图即代表，口径明示）：

| # | 地点/场景 | 键 | # | 地点/场景 | 键 |
|---|---|---|---|---|---|
| 1 | 青云坊市客栈 | scenes/market-inn | 9 | 黑风绝渊 | scenes/heifeng-abyss |
| 2 | 青云宗外门山门 | scenes/qingyun-gate | 10 | 万星古岛 | scenes/wanxing-isle |
| 3 | 宗门玄元洞府 | scenes/xuanyuan-cave | 11 | 秘境·落霞古洞 | scenes/realm-luoxia-cave |
| 4 | 落霞山灵泉 | scenes/luoxia-spring | 12 | 秘境·剑冢残碑 | scenes/realm-sword-tomb |
| 5 | 黑水沼泽 | scenes/heishui-swamp | 13 | 秘境·万星遗迹残址 | scenes/realm-wanxing-ruins |
| 6 | 万剑仙门峰 | scenes/wanjian-peak | 14 | 秘境·幽冥鬼市 | scenes/realm-ghost-market |
| 7 | 洗剑池洞天 | scenes/xijian-pool | 15 | 副本·锁妖古窟 | scenes/dungeon-entrance |
| 8 | 九幽天魔宗坛 | scenes/jiuyou-altar | | | |

呈现挂点（最小口径，写死）：① `_status_dict.location_image`（§8.1）——双端世界/动态呈现当前地点图幅各一处（桌面 world 视图头图、移动 world 分区头图，计入 §10 预算）；② 秘境进入/副本进入的既有返回只增 `scene_image` 完整路径字段（前端有则渲染、无则不渲染）。本轮不做全界面地点图改造（Out of Scope §13）。点亮：迁跃落点（§3.6 的 T5 同点）对落点地点键调 `gallery.unlock`（事件型点亮新钩子 `note_location_visit(char, location)`）；秘境/副本图在其进入返回组装时以同一 unlock 入口点亮。

### 9.5 法宝器型补齐（10 → 20 键）

**新增 10 键（逐个列名，定稿）**：`artifacts/armor`（甲胄正图)、`artifacts/boots`（靴履正图)、`artifacts/staff`（法杖)、`artifacts/vessel`（舟舰御空）、`artifacts/blade`（刀/战刃)、`artifacts/spear`（戈枪)、`artifacts/case`（剑匣)、`artifacts/needle`（灵刺)、`artifacts/shuttle`（破空梭)、`artifacts/talisman`（符箓护符）。

**`artifact_key_for` 映射规则修正（写死，顺序仍为名字关键字 → subtype → 槽位兜底）**：
- 槽位兜底改二处：`armor → armor`（原 mirror）、`boots → boots`（原 fan）；weapon/trinket/flying_treasure 兜底不变（sword/orb/pagoda）。
- subtype 规则增改：重铠/道袍/软甲/护腕 → armor；灵靴/战靴/草履/破虚神履 → boots；法杖 → staff（原 orb）；飞舟/巨舰/木鸢 → vessel；战刃 → blade；长戈/长枪 → spear；剑匣 → case（原 sword）；灵刺 → needle（原 sword）；破空梭 → shuttle；护身符 → talisman（原 seal）。未列 subtype 沿现行（飞剑/法剑/重剑 → sword 等不变）。
- 名字关键字增改：新增 （杖）→staff、（刀）→blade、（梭）→shuttle、（舟/舰/鸢）→vessel、（匣）→case、（符）→talisman；原 （戈/枪/刺/匣/刀） 从 sword 关键字组中移除（改归 spear/needle/case/blade）；关键字组间顺序按「专器优先」定稿为：镜 > 鼎/炉 > 葫芦 > 塔 > 铃/钟 > 幡/旗 > 印/玺 > 珠/戒 > 扇 > 杖 > 刀 > 梭 > 舟/舰/鸢 > 匣 > 符 > 剑/刃/枪（刃留 sword 组尾作生成器物兜底——目录内「血刃/惊神刃」以 subtype 战刃先行命中 blade，不受影响）。
- **鼎/葫芦命中口径（F4）**：目录 66 件中无任何含鼎/炉/葫芦之名的装备，改任何映射都凑不出真命中——定稿为关键字规则原样保留（鼎/炉 → cauldron、葫芦 → gourd 本已在首位组），命中面 = 天工造化（`core/forge.py`）等目录外生成器物与未来内容；同理改映射后 mirror（镜）与 pagoda（塔）的目录命中归零，与 cauldron/gourd 一并定为「关键字保留键」四席。验收以合成名直测（`artifact_key_for("九转炼丹鼎") == artifacts/cauldron` 等，既有 G-5 已有此式）+ 生成器物实体走 `artifact_key_for_item` 各一例为准，**不以目录命中数验收这四键**。
- 改后目录 66 件预期分布（实现岗以全量枚举复核）：armor 14 / boots 9 / sword 9（飞剑 5+法剑 1+重剑 2+灵蜂刺外剑类…以枚举实测为准，Spec 只锁三条硬断言：armor == 14、boots == 9、cauldron == 0 且 gourd == 0、每件恰得一键且 ∈ 全集）。

### 9.6 功法图补强（8 → 10 键）

- 新增 `arts/wind`（风属性专图）：`_ELEMENT_TO_ART` 的「风」与 `"wind"` 由 sword 改指 wind；名字关键字新增 （风/岚）→ wind，置于剑组之前（「御剑术」不含风字不受影响；含「风剑」二字者先中风组——定稿口径，写明防争议）。
- 自选补强 1 张定为 `arts/spirit`（神魂专图）：名字关键字新增 （魂/神念）→ spirit（置于金组之前；注意「摄魂幡」类是器物名不走 art 解析，无交叉）；神魂类自创功法（炼神/养魂向）自此有专图。法术 5 门仍按五行直取（无风/魂法术，不受影响）。

### 9.7 藏宝图补满（4 → 8 键）

- 新增 `maps/map-celestial`（tier 5 仙档独立键）：`map_key_for_tier` 改为 1 common / 2 fine / 3 rare / 4 ancient / ≥5 celestial（tier 4 口径不变）。
- 新增原型差异 3 键：`maps/arch-puzzle`（五行解谜 ELEMENT_PUZZLE）、`maps/arch-combat`（凶地守护 COMBAT）、`maps/arch-hazard`（遗迹涉险 RUIN_HAZARD），枚举源 `core/treasure_system.TreasureArchetype`（三值定稿）。
- 解析口径（`map_key_for(tier, archetype=None)` 新函数，`map_key_for_tier` 保留为其 archetype=None 的兼容壳）：**行囊/命盘的宝图 img 恒走稀有度键**（一件一图、稳定）；**读图/线索链/开匣呈现走原型键**（archetype 已知时），回退链写死：原型键 ∉ 全集 → 稀有度键 → `maps/map-common`。点亮：持有宝图派生点亮稀有度键（既有 derive 口径扩 tier5）；读图动作（treasure_system 的读图/激活路径）在既有返回组装点调 `gallery.unlock` 点亮其原型键（事件型钩子 `note_map_read(user_id, tier, archetype)`）。

### 9.8 补足包（F7 裁定：最小补足，分类级，P2 优先级）

任务 caps 内各类目上限合计 118 张，与总账下限 130 的缺口 12+ 张，只能由盘点实证的其余零覆盖类目补足。本节三类均为**分类级**（不按件/按人），与 §9.1–9.7 的核心类目分开排产：资产岗先交核心 80 张新增，补足包 21 张后交；总账验收按 139 全量验（缺补足包即总账不过，明示）。

| 类 | 键（定稿） | 数 | 解析/挂点 |
|---|---|---|---|
| 奇遇剧本专图 | `omen/black-market`、`omen/orphan-trust`、`omen/spring-dispute`、`omen/stele`、`omen/escort-deal`、`omen/inn-whisper`（slug = script_id 的 `_` 换 `-`） | 6 | `core/omen_scene.OMEN_SCRIPT_IMAGES` 六值改指专图键（现为借代键）；AI 剧本仍走既有关键字兜底不变。点亮走既有 `note_omen_image` |
| 丹药分类图 | `goods/pill-breakthrough`、`goods/pill-cultivation`、`goods/pill-recovery`、`goods/pill-lifespan`、`goods/pill-soul`、`goods/pill-detox`、`goods/pill-root`、`goods/pill-combat`（对应 `pill_type` 八值 breakthrough/cultivation/recovery/lifespan/soul_purity/detox/root_purify/combat_buff 的显式 slug 表） | 8 | `item_image_key` 扩：kind=pill 的实体按目录 pill_type 取键；查不到 pill_type（生成丹药）返回 "" 不配图（明示）。点亮由 derive 按行囊内丹药实体派生 |
| 材料分类图 | `goods/mat-herb`、`goods/mat-ore`、`goods/mat-metal`、`goods/mat-beast`、`goods/mat-liquid`、`goods/mat-wood`、`goods/mat-aura`（对应 materials category 七值 herb/ore/metal/beast/liquid/wood/aura） | 7 | 行囊材料多为名字字符串：解析经 `ITEM_CATALOG` 按名查 category 取键（新函数 `goods_key_for_name(name)`，查不到返回 ""）；呈现挂命盘 items 中材料项 img（后端拼装处既有目录查询口径内）；点亮由 derive 遍历行囊名（≤64 格，目录 O(1) 查）派生 |

### 9.9 总账与托管闸契约变更

**总表（定稿，验收按此逐项点数）**：

| 类 | 存量 | 新增 | 小计 | 新增明细 |
|---|---|---|---|---|
| 玩家立绘 portraits/{male,female}-* | 12 | 8 | 20 | fanren/heti/dacheng/dujie ×2 性别 |
| NPC 原型 | 4 | 0 | 4 | 保留兜底 |
| NPC 单人 | 0 | 37 | 37 | §9.1 全表 |
| 法宝 artifacts | 10 | 10 | 20 | §9.5 十键 |
| 功法 arts | 8 | 2 | 10 | wind + spirit |
| 藏宝图 maps | 4 | 4 | 8 | celestial + 原型 3 |
| 灵宠 pets | 0 | 4 | 4 | §9.3 |
| 场景 scenes | 0 | 15 | 15 | §9.4 |
| 奇遇 omen | 0 | 6 | 6 | §9.8 |
| 丹药/材料 goods | 0 | 15 | 15 | pill 8 + mat 7 |
| **合计** | **38** | **101** | **139** | ≥130 下限达标，落在 ~135–140 目标带 |

**托管闸契约变更（server/app.py）**：正则闸的目录段由 `(portraits|artifacts|arts|maps)` 扩为 `(portraits|artifacts|arts|maps|pets|scenes|omen|goods)`，文件名段 `[a-z0-9-]+` 与常量闸、路径拼装纪律（只许常量相对路径拼装）一字不改；G-7 式负例随之扩展（新目录下未登记键仍 404、穿越仍拦）。

### 9.10 图鉴扩展口径

- 全集 = 新 `GALLERY_ASSET_KEYS`（139），`summary().total` 随常量自动变（前端不得写死 38/139 任一数字，沿既有读后端 total 口径）。
- `GALLERY_GROUPS` 增改（组序定稿）：人物·男相（10)/人物·女相（10)/人物·NPC 单人（37，**由 ROSTER 程序化生成**：键走 §9.1 映射、KEY_CN 取人名，禁止手抄 37 行防漂移）/人物·NPC 原型（4)/法宝（20)/功法（10)/藏宝图（8)/灵宠（4)/场景·地点（10)/场景·秘境（5)/奇遇（6)/丹药（8)/材料（7)。`KEY_CN` 新增键的中文名由实现岗按「类·名」既有格式补齐（NPC 单人组程序化生成时以 `NPC·{人名}` 为名）。
- 里程碑称号重标定（契约变更）：`GALLERY_TITLES` 改为五档 (10 初窥门径 / 40 博览群真 / 80 洞鉴乾坤 / 120 博物通览 / 139 图录大成）；称号仍只展示零数值、不入 dao_title（既有红线不变）。已按旧档获得称号的账户在新口径下按其点亮数重新派生（`get_atlas` 本就按 count 派生 titles，无存量迁移问题，明示）。
- 点亮规则总口径不变：派生型（本人图/行囊实体/灵宠/丹药材料）走 `derive_keys_from_character` + `unlock_from_character`；事件型（NPC 相遇/地点到访/读图/奇遇）走 `unlock` 同一合并入口；只增不减、全集外脏键清除，二者均沿 gallery 既有实现。

### 9.11 资产生产口径（资产岗验收）

统一水墨仙侠风（与存量 38 张同风格基准，以存量图为风格锚逐张比对）、webp、长边约 640px、新增资产单张 ≤120KB（超限压缩重出，不许改键凑数）；NPC 出图逐人按附录 A 要点表（性别/年龄段/服色/气质四项全符）；逐张目检三条：风格一致、无明显崩坏（手/脸/器物形制）、主体与键名相符（器型图不得张冠李戴）。资产文件与 `GALLERY_ASSET_KEYS` 的三方一致（常量/磁盘/Spec 清单）以脚本枚举 diff 为空为准（沿 G-1 口径）。

### 9.12 验收

- **GL-01** 三方一致：`len(GALLERY_ASSET_KEYS) == 139`、磁盘 webp 文件集 == 常量集 == §9.9 总表逐类计数（脚本枚举 diff 为空）。
- **GL-02（NPC 对号）** 37 uid ↔ 37 键 ↔ 37 文件：以 ROSTER 全量枚举断言 `npc_single_key_for_uid` 与逆映射往返一致、每键文件存在且 /assets/ 可取（200 + image/webp）；ROSTER 外动态 NPC 解析回退原型键（负例）。
- **GL-03** 解析优先级：任取 3 名 ROSTER NPC（不同原型类各一），`npc_avatar_key_for_character` 返回单人键；同场相遇点亮单人键而非原型键（C-4 修订口径）。
- **GL-04（玩家立绘）** 20 组合矩阵全断言：tier 0→fanren、1–9 逐档、10+→dujie、未定相仍占位图；仪式突破幕在 tier 7/8/9 构造时 asset_key 分别为 heti/dacheng/dujie（不再借 lianxu）。
- **GL-05（法宝）** 66 件全量枚举：每件恰得一键 ∈ 全集、armor == 14、boots == 9、cauldron/gourd 目录命中 == 0；合成名四例（鼎/葫芦/镜/塔）解析命中保留键；forge 生成器物实体一例走 item 解析命中其名字关键字键。
- **GL-06（功法）** 风灵根角色的无关键字功法名解析为 arts/wind（含「风」字功法名同断言）；「御剑术」仍为 arts/sword（负例）；神魂向功法名（含魂字）解析为 arts/spirit。
- **GL-07（宝图）** tier 1–5 稀有度键逐档断言（tier4 ancient、tier5 celestial）；三种 archetype 的读图呈现各得其原型键、archetype 未知时回退稀有度键；读图后原型键被点亮、未读图的同 tier 宝图不点亮原型键（负例）。
- **GL-08（灵宠）** 四物种键逐一断言；养宠角色 derive 含其物种键；命盘 pet 块 img 与出战宠物种一致。
- **GL-09（场景）** §9.4 映射表 15 键逐项断言（地点名/秘境名 → 键）；迁跃到新地点后该地点键被点亮且 status.location_image 切换；秘境进入返回含 scene_image 且对应键点亮。
- **GL-10（补足包）** 六奇遇剧本的 `script_image_key` 各返回其专图键；丹药八类、材料七类的解析函数各以一例实体/名字断言；生成丹药（无 pill_type）返回 "" 不报错（负例）。
- **GL-11（图鉴）** 分组计数与 §9.10 组序逐组相符、total == 139；称号五档边界各一例（9/10、39/40、79/80、119/120、138/139）；点亮全程零数值（沿 C-5 的 before/after 逐字段断言复跑）。
- **GL-12（托管）** 新目录各取一键 GET 200 + webp + 缓存头（沿 G-2）；新目录未登记键 404、穿越变体 ≥4 种仍非 200（沿 G-7 扩展）。
- **GL-13（资产目检）** 新增 101 张逐张目检记录（风格/崩坏/名实三项，资产岗交付清单逐张打勾）；单张 >120KB 的新增资产数为 0（脚本以文件大小断言）。
- **GL-14（既有契约修订销账）** §9.2 表列 9 处既有断言已按定稿口径修订且修订后全绿；未列入该表的图库既有断言（G-2/G-6/G-7/roster_archetype_table 等）逐字未动且全绿。

---

## §10 · 移动端预算豁免申请（单列；沿一期 §9.1 格式）

实测（本 Spec 定稿时，worktree 基线 `c4c4571`）：`web/mobile.js` = **1561 行**，现行上限 1562 行（`tests/test_mobile_web.py::test_mobile_redesign_budgets`：文件 ≤1562 行、净增 ≤390），**余量 1 行**；`web/mobile.css` = **26599B / 339 行**，现行上限 27400B，**余量 801B**；`web/mobile.html` = 155 行，现行口径净增 ≤60 行（基准 150，现 +5），余量 55 行。

本轮移动端新增面逐项估算（前端岗按此上限施工，桌面端 workbench.js/css 无行数/字节预算约束——仓内现状，只许增量追加不许重构既有渲染函数，沿一期口径）：

| 新增面 | mobile.js 估算 | mobile.css 估算 | 说明 |
|---|---|---|---|
| 命途呈现（命盘命途段全量渲染：章节列表/命题/状态 + 搁置/续按钮） | +130 行 | +380B | 数据来自 fate.thread，渲染为新函数，不改既有命盘函数 |
| 入局 fate_chapter/drama 两 kind 的标签与 drama 回应按钮组 | +80 行 | +180B | queue 通用渲染上加 kind 分支与 options 按钮 |
| 主动戏剧当面行（world 分区 proactive drama 行） | +30 行 | +60B | 复用 proactive 行结构 |
| 图鉴扩充分组（分组表跟随后端 GALLERY_GROUPS 的前端镜像更新 + pets/scenes/goods 组渲染） | +45 行 | +60B | 分组数据以后端为准，前端只加组名映射 |
| NPC 单人图挂点（世界同场/交谈头像 img） | +5 行 | +0B | 后端下发路径变更，前端仅沿既有 img 渲染 |
| 地点场景图挂点（world 分区头图幅） | +25 行 | +120B | location_image 一处渲染 |
| 交谈旧账行 | +15 行 | +40B | §8.3 一行渲染 |
| **合计** | **+330 行** | **+840B** | CSS 估算已超现余量 801B，JS 余量 1 行必然击穿 |

**豁免申请（须总管批准后实现岗才可动 mobile 文件；未批准前任何 mobile 文件改动不得落码）**：`mobile.js` 文件上限 1562 行 → **1892 行**（净增上限 390 → 720，申请 +330 行，含估算取整余量）；`mobile.css` 上限 27400B → **28800B**（申请 +1400B，覆盖估算 840B + 约 560B 机动）。`mobile.html` 预计 +6 行（world 头图容器等），在现行 +60 口径内，**不申请**。token 纪律（no_bare_hex、昼夜双 token 表）**不在豁免内**，新增 CSS 必须全量 var() 引用。

**总管批准记录（2026-11-08）**：批准上述豁免——`mobile.js` 文件上限 1562 行 → **1892 行**（净增上限 390 → 720）；`mobile.css` 上限 27400B → **28800B**，自本记录起生效；前端岗可据此同步修订 `tests/test_mobile_web.py` 的预算断言（断言处须注明出处为本节）。token 纪律（no_bare_hex、昼夜双 token 表）不在豁免内，新增 CSS 必须全量 var() 引用。另总管对 §0.2 冲突口径一并确认：F4 补足包 21 张（奇遇专图 6 + 丹药分类 8 + 材料分类 7，P2 排产、总账按 139 验）成立——任务口径各类 caps 相加仅 118 张，数学上达不到 ≥130 的硬指标，补足类目均为盘点实证的零覆盖类，不算缩水；F6 六级种子优先级（未竟 > 世仇 > 影子 > 血仇 > 宗门 > 出身）与 P2-07 契约变更按 §11 记账执行。

---

## §11 · 回归口径（写死）

- **RG-01（基线获取方法）** 基线 = v0.3.8-gray.15 最终全量实测 **1217 passed / 8 failed**（新鲜 DB）。名单获取方法写死：实现开工前，在 worktree 外或基线提交 `c4c4571` 上以**新鲜 DB** 全量实跑一次 `pytest tests/ -q` 并留档，其失败集即本轮**操作基线**；已知有效基线失败 7 条（沿一期 Spec §7.5 名单）：① `test_auth_hardening.py::test_world_join_requires_explicit_nonempty_authenticated_uid`；② `test_karma_chains.py::test_kill_and_bounty_single_chain`；③ `test_natural_omen.py::test_initial_character_and_config`；④ `test_qa_account_death_acceptance.py::test_qa2_join_dead_http_and_anonymous_unchanged`；⑤ `test_status_dict_gray.py::test_status_dict_includes_bag_and_marks`；⑥ `test_status_dict_gray.py::test_status_dict_follows_real_equip_flow`；⑦ `test_workbench_api.py::test_login_then_look_here`。交付跑中出现的名单外失败先单跑复验：复跑转绿且属一期已知的状态敏感/flaky 模式（farm/director 类）者按 flaky 记账说明，其余即新增失败。
- **RG-02（红线）** 本轮交付全量：**新增失败必须为 0**（交付失败集 ⊆ 操作基线失败集 ∪ 复跑可绿的已知 flaky）。合法契约变更引起的既有断言修订只许出现在三处并逐条列明出处：§3.3 的 P2-07（未竟二居其一）、§9.2 表列 9 处图库断言、命令目录 100→102 引起的可达性计数断言（一期 P1-05 的修订版 UI-04）；任何修订不得削弱数值/安全类断言。
- **RG-03（定向套件）** 下列套件全绿（基线内既有失败除外并逐条注明）：`test_game_feel_phase1_backend.py`、`test_game_feel_phase1_rework*.py`、`test_goals` 相关（goals/origin 用例所在文件）、`test_promises.py`、`test_karma_chains.py`、`test_reincarnation_inheritance.py`、`test_gallery_assets.py`、`test_gallery_atlas.py`、`test_gallery_frontend_contract.py`、`test_mobile_web.py`（预算断言以 §10 批准后的新上限为准，未批则以现行为准且 mobile 文件零改动）、`test_login_latency_fix.py`（登录耗时口径：一期 P1-03 测法复测，拼装层中位数阈值不变）。

**验收条目总计**：本 Spec 共 **59 条**（S4 5 + FT 12 + VD 5 + DR 7 + RM 4 + EP 4 + UI 5 + GL 14 + RG 3），逐条定义于各节末尾；方案验收映射见附录 B。

---

## §12 · 风险与兜底

| 风险 | 兜底（已写入设计何处） |
|---|---|
| S-4 收紧误伤一期目标（线上老角色 goals 里全是无 instance 目标） | 归一回退口径（§2.3）+ S4-02/S4-04 双向断言；收紧先行单独提交、先跑一期套件再进 §3 |
| fate_threads 与角色行双写不一致（thread 在新表、goals 在角色行） | 章节状态派生自 goal（单一事实源，§3.5）；thread save 只写自有仓储、goals 落盘归既有路径；崩溃后下个 T 点重派生可自愈（派生为幂等重算） |
| 世仇选人把高境界 NPC 塞进新角开局（死局） | bounds 硬校验在选人链每级复核（§4.2），超界只记引用不植入；VD-04 批量复验 A6 |
| 戏剧变成新的刷屏/数值面 | 三闸频控（§5.4）+ 后果全走既有系统（§5.3）+ nudge 双函数钳制与 Chronicle 留痕可审计 |
| 评语润色污染数值叙事（AI 编造数字） | payload 白名单无数值（EP-03）+ 输出数值词黑名单校验（§7.2）+ 失败逐字保留模板 |
| 图库 139 张资产生产延期拖住结构交付 | 核心 80 张与补足包 21 张分开排产（§9.8）；结构代码只依赖键常量，资产缺位时 G-1 式枚举会明确报缺哪几张，不静默缩集 |
| REALM_KEYS 扩展波及仪式/图鉴/前端多处引用 | §9.2 契约变更表逐处列明；REALM_KEYS 的既有引用方（gallery groups/derive）均为程序化生成，无手抄名单 |
| 移动端预算未批先行 | §10 写死未批不得动 mobile 文件；后端与 CLI 先行交付不阻塞（呈现可先在桌面/CLI 验收） |

---

## §13 · Out of Scope（逐项点名，本轮不做、不顺手做）

1. 第三期仪式补全：得宝幕、器灵认主幕、天劫独立幕（方案 §7 第三期）；主线章节类型扩充（宗门章接议政结果）同属第三期。
2. 品阶命名统一（装备/实体/材料三套品阶词并行问题，盘点附 2）——本轮图库只认数值 tier，不借扩图顺手统一。
3. 扩地点/NPC/剧本等**内容本体**：不新增地点、NPC、秘境、奇遇剧本（场景图只给既有地点配图；NPC 图只给既有 37 人配图）。
4. 丹药/材料**按件图**（61/69 张逐件图）：本轮只做分类级（§9.8），按件级不在本轮口径。
5. 主线编辑器、AI 自由编章节结构、玩家自选种子/重抽主线、支线与主线并行叙事（方案 §9 口径 5：每世一条主线）。
6. 全服统一宿敌 BOSS（方案口径 6 否决项）；世仇只走个人杀伐记录。
7. place 类路径开关的 closed 形态（一期 §8 第 9 条移交项，本轮复核仍无既有门槛可挂，继续不做）；影子施加路径的 RELATION 留痕补齐（一期 §8 第 8 条，本轮仍不做，其可见性仍由 karma_shadow 展示承担）。
8. v0.3.7 复审 S-1~S-7 遗留（寻宝链/奇遇呈现噪声等，一期 §8 第 6 条名单）本轮仍不处理；其中 S-6（移动端行囊以名字含「图」误判宝图）与本轮 §9.7/§9.8 的 img 解析相邻但不顺手改判图逻辑。
9. 桌面命盘 `[object Object]` 观察项（一期 §8 第 6 条）仍不处理。
10. 戏剧的 tick 主动上门（戏剧只在两个既有触发点评估，§5.4）、每日任务/签到类留存机制（方案明禁）。
11. 主线标题/开场白的 AI 润色落码（§3.4 只预留口径，本轮只做评语润色一条 AI 路径）。

---

## §14 · 截图验收清单（双端，实现岗交付时随附；每张对应验收编号）

桌面（1280 宽，web/index.html + workbench.js）：
- **S-D1** 入局队列含 fate_chapter 条目 + drama 条目（回应按钮可见）（UI-02）
- **S-D2** 命盘命途全量段：主线标题/种子来源/6 章列表/终局命题/搁置按钮（FT-01、UI-01）
- **S-D3** 世仇 NPC 交谈页：单人头像 + 旧账行 + 世仇 note 呈现（VD-02、UI-03、GL-03）
- **S-D4** 主动戏剧找上门一条：入局 drama 项展开（DR-01）
- **S-D5** 图鉴扩充后桌面全集：分组含 NPC 单人/灵宠/场景/goods（GL-11）
- **S-D6** 世界视图：同场 NPC 单人头像 + 当前地点场景头图同屏（GL-03、UI-05）
- **S-D7** 突破仪式在合体境界构造：立绘为 heti 专图（GL-04）

移动（390×844，web/mobile.html + mobile.js）：
- **S-M1** feed 入局卡含主线条目（fate_chapter）（UI-02）
- **S-M2** 命盘命途段（章节列表 + 命题 + 搁置）（FT-01）
- **S-M3** 交谈页：NPC 单人图 + 旧账行（UI-03、GL-03）
- **S-M4** 主动戏剧找上门一条（world 分区当面行或 feed 队列项）（DR-01）
- **S-M5** 图鉴移动端扩充后分组（GL-11）
- **S-M6** 转世出身卡：世仇行（vendetta 关系）+「前世曰」评语行同屏（VD-01、EP-01）

缺图即对应条目未验（沿一期 §7.6 口径）。

---

## 附录 A · NPC 37 人出图要点表（资产岗逐人依据）

口径说明：**性别列只用两处显式依据**——`core/gallery_assets.py NPC_FEMALE_NAMES` 名单（7 人：苏婉清/青萝/骨姬/毒娘子/柳三娘/海娘子/小环，标「女（名单）」）与 `core/npc_personas.py` 人设档案；名单外且档案无女修标记者一律标「未标女相」，出图按中性偏男相呈现、**禁止按名字猜女相**。年龄段由 ROSTER 的 rank/tier/note 推定（掌门/宗主/太上/老祖/翁/爷→中老年，长老/执事/掌柜/会长→中年，弟子/伙计→青年，新入门/丫头/跑堂→少年）。服色：青云宗=青白道袍云纹；万剑仙门=玄衣银纹剑纹；九幽天魔宗=黑紫魔袍血纹；四海散修商会=赭金商袍；散修/妖修按个人行装列。气质关键词 = ROSTER personality + personas identity/voice 摘词。

| # | 人名（uid） | 性别 | 年龄段 | 宗门服色 | 气质关键词 |
|---|---|---|---|---|---|
| 1 | 玄清子（npc_qy_01） | 未标女相 | 中老年 | 青云·青白道袍云纹 | 清高自持、元婴掌门、道法自然、淡而有威 |
| 2 | 静虚真人（npc_qy_02） | 未标女相 | 老年 | 青云·青白素袍 | 淡泊避世、金丹老宿、闭死关、话少 |
| 3 | 云鹤道人（npc_qy_03） | 未标女相 | 中年 | 青云·青白执法袍 | 清高自持、执法长老、嫉恶如仇、严厉 |
| 4 | 丹霞子（npc_qy_04） | 未标女相 | 中年 | 青云·青白丹袍 | 谨慎多疑、丹殿长老、炼丹如命、慢条斯理 |
| 5 | 林惊羽（npc_qy_05） | 未标女相 | 青年 | 青云·青白内门袍 | 豪爽仗义、内门大师兄、好打抱不平 |
| 6 | 苏婉清（npc_qy_06） | 女（名单） | 青年 | 青云·青白女修剑袍 | 淡泊避世、剑心通明、清冷短言 |
| 7 | 石猛（npc_qy_07） | 未标女相 | 壮年 | 青云·青白外门短打 | 豪爽仗义、守山弟子、好酒、大嗓门 |
| 8 | 赵小满（npc_qy_08） | 未标女相 | 少年 | 青云·青白外门袍 | 谨慎多疑、新入门、战战兢兢 |
| 9 | 青萝（npc_qy_09） | 女（名单） | 青年 | 青云·青白素裙 | 淡泊避世、洞府打杂、爱清净、轻声 |
| 10 | 剑圣·独孤败（npc_wj_01） | 未标女相 | 中老年 | 万剑·玄衣银剑纹 | 清高自持、化神剑修、孤高论剑 |
| 11 | 断岳剑尊（npc_wj_02） | 未标女相 | 中年壮年 | 万剑·玄衣刑罚剑纹 | 莽撞好斗、大长老、火爆短句 |
| 12 | 白霜（npc_wj_03） | 未标女相 | 青年 | 万剑·玄白洗剑袍 | 清高自持、洗剑池执事、剑意冰寒、冷淡精确 |
| 13 | 赤霄（npc_wj_04） | 未标女相 | 青年 | 万剑·玄红剑袍 | 莽撞好斗、内门首席、以战养战、挑衅 |
| 14 | 墨离（npc_wj_05） | 未标女相 | 青年 | 万剑·玄衣偏锋 | 阴鸷记仇、剑走偏锋、阴阳怪气 |
| 15 | 剑奴阿七（npc_wj_06） | 未标女相 | 少年 | 万剑·玄衣外门 | 莽撞好斗、剑痴、憨直兴奋 |
| 16 | 小环（npc_wj_07） | 女（名单） | 少女 | 万剑·玄衣杂役裙 | 豪爽仗义、剑冢扫地丫头、耳目灵通、叽喳 |
| 17 | 幽冥老祖（npc_jy_01） | 未标女相 | 老年 | 九幽·黑紫魔袍血纹 | 阴鸷记仇、化神宗主、喜怒无常、视人如蝼蚁 |
| 18 | 血衣侯（npc_jy_02） | 未标女相 | 中年 | 九幽·血红执法魔袍 | 阴鸷记仇、执法魔使、公事公办的残忍 |
| 19 | 厉无锋（npc_jy_03） | 未标女相 | 中年 | 九幽·黑紫护法袍 | 莽撞好斗、护法、护短蛮横 |
| 20 | 骨姬（npc_jy_04） | 女（名单） | 青年 | 九幽·黑紫执事裙 | 市侩圆滑、情报贩子、娇作要价 |
| 21 | 血刀老祖（npc_jy_05） | 未标女相 | 老年 | 九幽·暗红魔袍 | 阴鸷记仇、外门长老、血债累累、嘶哑 |
| 22 | 毒娘子（npc_jy_06） | 女（名单） | 青年 | 九幽·黑紫艳色魔裙 | 市侩圆滑、善用奇毒、甜里带毒 |
| 23 | 阿骨（npc_jy_07） | 未标女相 | 青年 | 九幽·黑紫外门袍 | 莽撞好斗、炼尸一脉、憨傻直愣 |
| 24 | 金满堂（npc_sh_01） | 未标女相 | 中年 | 商会·赭金商袍 | 市侩圆滑、会长、笑面虎、算盘响 |
| 25 | 铁算盘（npc_sh_02） | 未标女相 | 中年 | 商会·赭褐账房袍 | 贪财好利、大执事、只认灵石、干巴报数 |
| 26 | 柳三娘（npc_sh_03） | 女（名单） | 青年 | 商会·赭色丹铺掌柜裙 | 谨慎多疑、丹铺掌柜、怕惹祸、压低声音 |
| 27 | 陆仁贾（npc_sh_04） | 未标女相 | 中年 | 商会·赭色牙人袍 | 市侩圆滑、牙人、消息灵通、油滑 |
| 28 | 驼爷（npc_sh_05） | 未标女相 | 中老年 | 商会·赭褐镖行劲装 | 豪爽仗义、镖头、刀口舔血、沙哑 |
| 29 | 小雀儿（npc_sh_06） | 未标女相 | 少年 | 商会·赭色伙计短打 | 谨慎多疑、客栈跑堂、爱听墙角、快嘴 |
| 30 | 采药翁（npc_wd_01） | 未标女相 | 老年 | 散修·粗布采药装 | 谨慎多疑、独行采药、怕劫修、哆嗦 |
| 31 | 赤练子（npc_wd_02） | 未标女相 | 中年 | 散修·暗色旧袍 | 阴鸷记仇、道基被毁、咬牙切齿 |
| 32 | 山君（npc_wd_03） | 未标女相 | 壮年 | 妖修·虎纹袍（虎耳虎纹特征） | 莽撞好斗、虎妖化形、占山为王、低吼 |
| 33 | 蜃楼客（npc_wd_04） | 未标女相 | 中年 | 散修·海青长袍 | 淡泊避世、海外散人、寻遗宝、飘忽哑谜 |
| 34 | 海娘子（npc_wd_05） | 女（名单） | 青年 | 散修·海蓝劲装 | 市侩圆滑、女海盗、见风使舵、笑里藏刀 |
| 35 | 盲眼琴师（npc_wd_06） | 未标女相 | 中年 | 散修·素灰长袍抱琴 | 淡泊避世、盲眼、琴音乱心、来历成谜 |
| 36 | 盗墓贼·孙九（npc_wd_07） | 未标女相 | 青年 | 散修·灰褐夜行装 | 贪财好利、专刨无主洞府 |
| 37 | 青州游侠·燕十三（npc_wd_08） | 未标女相 | 青年 | 散修·青侠游侠装 | 豪爽仗义、行侠仗义、居无定所 |

注：无专属 personas 档案的 3 人（盲眼琴师/盗墓贼·孙九/青州游侠·燕十三）气质只取 ROSTER 的 personality 与 note（盘点口径：34 人有专属人设），不得为出图编造新档案。

---

## 附录 B · 方案验收映射表（A1–A9、D1–D5 → 本 Spec 验收条目）

| 方案条目 | 本 Spec 对应 | 备注 |
|---|---|---|
| A1 新角 10 分钟内生成主线、命盘可见 | FT-01（+截图 S-D2/S-M2） | 建线在首次登录响应内（比「10 分钟内」更严） |
| A2 四类种子优先级与事实一致 | FT-02（P0–P5 六级全验，含优先级断言） | 方案四类扩为六级系 F6 收口（未竟/世仇为方案 §4a 衔接与路线 C 的既定组成） |
| A3 打完一章、无 AI 环境复测 | FT-03 | |
| A4 死亡留痕、转世新线对应未竟、同 NPC 复用 | FT-04 | |
| A5 主线全程数值对账、主线模块自身不产生数值 | FT-05 | 含静态 import 检索 + 无线对照组双证 |
| A6 出身力学差异与 bounds（200 包） | 一期 P2-01/P2-02 复跑（RG-02/RG-03）+ VD-04（世仇世 50 次转世不破 bounds） | 二期全量口径：origin 生成器本体未改，只增 vendetta 入参 |
| A7 判定式可复算、到期转未竟、无 AI | FT-06 + FT-07 | 含二期新 kind 三个 |
| A8 一生评语三落点、未竟回流二居其一 | EP-01/EP-02（润色路径）+ FT-04 + 一期 P2-06 复跑 | 模板路径沿一期，润色为二期新增可选路径 |
| A9 不同出身开局差异 + 同账户防重 | 一期 P2-08 复跑（RG-02）+ FT-10（主线指纹防重） | 二期防重面扩至主线 signature |
| D1 关系动态留痕与双端一致 | 一期 P4-01~P4-03（已验，本轮回归 RG-03）+ UI-03（交谈旧账行，第三处呈现补齐）+ DR-03（示好留痕同源） | |
| D2 hostile 挑衅频控内触发、应战/避走 | DR-01 + DR-02 | |
| D3 恩链了结后示好、赠礼与态度对账 | DR-03 | 赠礼为 NPC 自有灵石转移（§5.3），对账口径更严于方案原述 |
| D4 突破传闻入池、他人可见、NPC 可引用 | RM-01（F2 改造口径：pick_for_npc 函数级 + lore_prompt_block 接线级）+ RM-02/RM-03 | 与方案字面差异已在 F2 记账：简报世间段数据源为 jianghu 而非传闻池，不注水 |
| D5 无 Key 环境五类戏剧全触发 | DR-07 | |

---

## 附录 C · 新增/变更总表（实现岗索引）

- **新表**：`fate_threads`（§3.2）。**新模块**：`core/fate_thread.py`（FateThread + FateThreadEngine，含 select_vendetta）。
- **新仓储**：`FateThreadRepository`（storage/db.py）。
- **新模型字段**：`LifeTrace.epitaph_head/epitaph_line/epitaph_tail/epitaph_polish`（§7.2，带默认值）。
- **新 config**：`FATE_THREAD_MAX_ACTIVE=1`、`FATE_CHAPTER_WINDOW_DAYS`（§3.2）、戏剧频控常量沿 §5.4 写死于 npc_proactive（或 config 同段，实现岗二选一并在代码注释标出处）。
- **既有契约变更清单**：goals 幂等键（§2）+ CHECKED_SOURCES/KINDS/NON_REJECTABLE 各增 thread + _eval_check 增 3 kind（§3.5）；origin 生成器增 vendetta 入参（§4.3）；legacy `_fate_fields` 增 thread 分支与评语分段（§3.8/§7.2）；briefing 拼装增 ③.5/⑤.5 两步（§8.2）；KarmaChainEngine 增 nudge_ferment/nudge_strength 两钳制函数（§5.3）；rumors 增 4 写入口（§6.2）；gallery_assets 键集 38→139 与多处解析变更（§9）；gallery 分组/称号/派生变更（§9.10）；server/app.py 托管正则目录段扩展（§9.9）；`fate_block` 增 thread 子键（§8.1）；命令目录 +2（§8.4）。
- **只增字段总表**：登录响应 entry.queue 增 fate_chapter/drama 两 kind、lines.fate 取值优先级（§8.2）；`_status_dict` 增 `fate.thread`、`location_image`（§8.1）；交谈开启响应增 `old_account`（§8.3）；命盘 pet 块增 `img`（§9.3）；秘境/副本进入响应增 `scene_image`（§9.4）；origin relations 条目增 `vendetta/vendetta_for` 两键（§4.3）。
