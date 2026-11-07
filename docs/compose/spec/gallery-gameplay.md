# Spec：AI 图库与视觉接入 + 三条玩法线（gallery-gameplay）

- 基线：worktree `.worktrees/gallery-gameplay`，分支 `feat/gallery-gameplay`，HEAD `12332f0`（含登录延迟修复，未含其发版文档改动）
- 状态：**已实现，收尾中**——四段实现与首轮评审（MF-1/SF-1 已修复）完成；2026-11-07 由收尾总管 rebase 至 main `cc92fab`（v0.3.6-gray.13），见 §15 补记；待 rebase 后独立复审、全量回归、截图验收与发版 v0.3.7-gray.14
- 版本号说明：**本 Spec 不写死目标版本号**，合并时按届时 `main` 的 `config.py` 顺延，由发布岗定版
- 用户需求原话（Martinez 已拍板全做）：「页面图片（人物图男女、法宝图、功法图、藏宝图）需要丰富下，玩法需要丰富下，目前没有吸引人的玩法」
- 两块构成：① AI 图库与视觉接入（人物/法宝/功法/藏宝图 + 图鉴）；② 三条玩法线（寻宝线索链、法宝器灵、奇遇抉择事件）
- 红线（全 Spec 通用）：规则引擎裁决数值、LLM 只叙事/言行、AI 不可用本地降级；新功能涉及角色数据必须遵循 `AGENTS.md` 道体合规守恒律（前置门禁 `assert_alive/assert_idle/assert_currency/assert_bag_space`、后置审计 `CharacterRepository.save`），逐条落点见 §11
- 相关 Spec：`karma-event-chains.md`（ caps 子顶惯例、双端同源文本先例）、`mobile-web.md`（双端与静态托管口径）、`web-static-hosting.md`（白名单托管）、`treasure-map-direction-guide.md`（宝图双阶段现状）

---

## §0 · 盘点核查结论（写 Spec 前已逐个核读代码，任务前提有 9 处纠正/补充）

本节是本轮最重要产出：任务简报多处前提与仓库现状不符，设计一律按**实测现状**为准，开发岗不得按简报字面理解开工。

### C1 —— 角色与 NPC 都没有性别字段：男女人物图无现成数据源（纠正简报隐含前提）

| 位置 | 实测现状 |
|---|---|
| `core/models.py` `Character`（442 行全量核读） | 无 `gender` / 性别 / 男相女相 任何字段；`core/clock.py:54` `create_new_character` 只随机灵根与寿元 |
| `server/world.py` `World.join`（:281） | 建角只收道号（+ 已认证 `user_id`），无性别参数；HTTP `/register`、`/login` 同理 |
| `core/npc_roster.py` `ROSTER`（37 名 NPC） | 字段只有 uid/name/tier/sub/loc/sect/rank/sin/merit/stones/personality/agenda/note，**无性别字段**；`core/npc_personas.py` 的人设也不带性别字段 |
| 结论 | 男女各 6 境界的人物图（§3）**无法从存量数据自动选图**。本 Spec 的解法（§3.3）：角色新增带默认值的 `gender` 字段 + `/定相` 命令自选（不改注册/登录接口契约）；NPC 头像按 §3.4 的**显式名单 + 角色规则**映射到 4 个原型，禁止按名字猜性别 |

### C2 —— 藏宝图挖宝是「单步直达结算」，不存在可挂接的线索/会话状态（纠正简报隐含前提）

| 位置 | 实测现状 |
|---|---|
| `core/items.py:180` `ItemFactory.create_treasure_map` | 实体图：`template_id="treasure_map_entity"`，空间绑定在 `custom_metadata = {target_node_id, target_node_name, archetype, riddle_text, is_active, puzzle_data: {}}`；`puzzle_data` **至今无人读写** |
| `core/treasure_system.py` `TreasureEngine`（792 行） | `generate_treasure_map`（:146，随机非安全区节点 + 三原型 combat/element_puzzle/ruin_hazard）、`read_map`（:278，含旧字符串「藏宝图」自动升实体 tier=2）、`get_directional_guide`（:200，AI 谶语 + 八卦模板双轨）、`dig`（:348）、`resolve_free_action`（:686，`/做` 自由破局，AI DM 裁决 + 本地保底） |
| `dig` 流程 | **无状态机、无会话**：未到目标节点 → 返回方位指引、不耗图；已到目标 → element_puzzle 首次返回 `need_choice`（不耗图）、带 `choice_id` 再调才耗图结算；combat / ruin_hazard **首次到达即耗图结算**。服务端入口 `server/world.py:1765` `/挖宝`、`:1755` `/宝图`；旧桥 `core/loot_equip.py` `DigEngine.dig` 只是转发 `TreasureEngine.dig`（legacy 字符串图走另一套旧表，见 C3） |
| 结论 | 「寻宝线索链」（§5）必须是**新增的前置阶段状态**，落点现成：写进该图实体的 `custom_metadata["clue_chain"]`（随图走、无新表、旧图缺省即未激活，向后兼容）。终局开匣仍走现有 `dig` 结算，不得另起第二套开匣 |

### C3 —— 现有挖宝奖励远超 `EVENT_EFFECT_CAPS`，且无任何每日上限（经济事实，必须先摆上桌）

- `TreasureEngine.dig` 现行结算（tier=图品阶）：element_puzzle 巧破 灵石 `200+tier*80`（最高 520）+ 修为 `120+tier*50` + 装备 1 + 丹 1；combat 胜 灵石 `300+tier*100`（最高 700）；ruin_hazard 灵石 `500+tier*150`（tier 4 即 **1100**）+ 修为 `250+tier*80` + 业力 +20 + 世界疤痕；combat 败 **燃寿 0.5 岁**；`resolve_free_action` 成功 灵石 +350。
- 对照 `config.py:704` `EVENT_EFFECT_CAPS`：`stones_gain 300 / exp 800 / lifespan_gain 15 / lifespan_burn 8`——现行挖宝灵石单笔最高是 caps 的 3.7 倍；legacy `DigEngine` 旧表另有灵石 `80~400+tier*80` 一套。
- 宝图来源本身稀缺：`core/adventure.py` 探险掉率 8%~40%（首探保底 100%）、`config.py` 目录价 300 且 `npc_sell: False`（商会不可售，仅玩家间交易）。
- **裁定**：本轮**不改**现有挖宝结算数值与掉率（改经济数值须 Martinez 另行拍板，见 §14 待裁决 D-1）；新线索链层自身的奖励/惩罚**单独设账、严于 caps**（§5.5/§9），且在 Spec 中把「终局开匣沿用现行大表」明写为已知现状而非新设额度。

### C4 —— 法宝有两套品阶口径，「凡/人/地/天」只对一半（纠正简报品阶口径）

| 口径 | 出处 | 取值 |
|---|---|---|
| 实体道具 `ItemEntity.tier` | `core/items.py:32` `TIER_NAMES` | 1 凡品 / 2 人品 / 3 地品 / 4 天品 / **5 仙品**（共 5 档，简报漏了仙品） |
| 装备目录 `EQUIPMENT_CATALOG`（132 件） | `core/catalogs/equipments.py`（`grade_name` 实测分布） | 凡品 24 / **灵品** 26 / **宝品** 28 / **极品** 28 / 仙品 26 —— 是「凡/灵/宝/极/仙」，与实体口径完全不同源 |
| 命盘下发 | `server/world.py` `_status_dict` | 实体优先取 `it.tier_name`（凡/人/地/天/仙），目录回退 `eq_cfg["grade_name"]`（凡/灵/宝/极/仙），再兜底写死「灵品」——**同一面板两种品阶词并存是现状** |
| 功法品阶 | `core/art.py:11` `ART_RANKS` | MORTAL/EARTH/MYSTIC/HEAVEN/IMMORTAL → 凡品/人品/地品/天品/仙品（与实体口径同词） |
| 结论 | 本轮**不统一品阶词**（属存量语义，统一须另立工单）；§3.6 的图框/光效只认**数值 tier（1~5）**，不认中文词，两套口径在呈现层自动收敛 |

### C5 —— 法宝的「器型」在目录 `subtype` 里（中文），不在简报的 10 类里；目录无鼎/镜/葫芦/扇/塔

- `EQUIPMENT_CATALOG` 132 件、`subtype` 实测 27 种：飞剑 10、法剑 2、重剑 4、战刃 8、灵刺 2、长戈 2、长枪 2、法杖 4、剑匣 6、灵幡 4、宝珠 10、骨戒 2、宝铃 2、灵佩 12、护身符 2、飞舟 4、巨舰 2、破空梭 6、木鸢 2、重铠 14、道袍 10、软甲 2、护腕 2、草履 2、灵靴 8、战靴 6、破虚神履 2。
- 槽位 5 种（`core/models.py:236` `EquipmentSlots` + 目录）：weapon / armor / trinket / boots / `flying_treasure`（本命法宝/御空法具，`core/loot_equip.py:128` 槽位名映射同此）。实体 `ItemEntity.slot` 只写 weapon/armor/trinket 三值，boots/flying_treasure 只在目录与 `_status_dict` 推断中出现。
- 结论：10 个法宝图键（§3.5）与 27 种 subtype **不是一一对应**，必须定一张确定性的「关键字优先 → subtype → 槽位兜底」映射表并写进 Spec（§3.5 已定稿）；其中 mirror/cauldron/gourd/fan 在目录中**零命中**，它们的用途是覆盖 AI 生成/锻造出的含「镜/鼎/葫芦/扇」字样的器物名，不得因此删键。

### C6 —— 功法没有「流派/五行」字段：自创功法只有品阶 + 正/魔/中立 + 神通效果类型（纠正简报口径）

| 对象 | 实测字段 |
|---|---|
| 已习得功法 `Character.skills: List[str]` | 纯名字字符串列表（出厂 `["吐纳术", "御剑术"]`，`core/models.py:301`），无任何结构 |
| 自创功法 `Character.custom_arts`（DSL dict） | `core/art.py`：`rank`（五档）、`nature`（ORTHODOX/EVIL/NEUTRAL → 正道/魔道/中立）、`spells[].effect_type`（DAMAGE/BUFF/HEAL/CONTROL）、倍率/燃寿/天劫加成——**无 element、无 school** |
| 心法槽位 | `core/art_slots.py`：主修 1 + 辅修 2，变更冷却 3600s，加成与功法图无关 |
| 真正带五行的 | `core/spells.py` `SPELL_CATALOG` 5 门基础神通（metal/wood/water/fire/earth 各 1）与 `core/models.py` `Element`（金木水火土 + 风/雷/冰变异灵根） |
| 结论 | 8 个功法图键（metal/wood/water/fire/earth/thunder/sword/ice）只能靠 §3.7 的**确定性推图规则**（名字关键字 → 灵根兜底）落到每门功法头上；不得要求后端给功法新造 element 字段（那会改自创功法 DSL 语义，Out of Scope） |

### C7 —— 奇遇已有两套引擎，且其一推进路径无调用点；频控常量定义了却没执行（纠正简报隐含前提）

| 系统 | 实测现状 |
|---|---|
| `core/omen_scene.py`（现役主系统） | 节点图剧本 `SCRIPTS` **6 部**（black_market / orphan_trust / spring_dispute / stele / escort_deal / inn_whisper），每部多节点、选项 + 自由言行边（`edges`，意图分类）、AI 剧本可注入（`ingest_ai_script`，效果过 `_clamp`）；服务端 `/奇遇`（`server/world.py:1633`）走的正是它（`start_scene/choose/say/abandon/get_scene`）；状态存 WorldState KV；桌面有内联奇遇芯片条（`web/workbench.js` `renderInlineOmenBar` 一带，:5785 起） |
| `core/event_chains.py`（半孤儿） | 模板 `EVENT_CHAIN_TEMPLATES` **23 条**（`core/content_pack.py`，2~3 步选项链）、`EVENT_CHAIN_TRIGGER_TRAVEL=0.08 / ADVENTURE=0.10`、全服 active ≤8、单人 ≤1、超时 30 分钟、效果经 `_clamp_effects`（复用 `EVENT_EFFECT_CAPS`，其中 dao_heart 硬钳 ±10、lifespan 硬钳 ±5）；**但 `choose/view_text/abandon` 在 server 与 CLI 均无调用点**——只有 `maybe_start` 被 `world.py:4433`（迁跃）与 `core/adventure.py:516`（探险）调用，即「能开启、没入口推进」是合并遗留现状 |
| `core/events.py` `EventEngine` | 单步世界事件（fortune/crisis/omen），AI 提案 + `EventValidator` 钳制 + 本地模板；触发率 `EVENT_TRIGGER_CHANCE` = `OMEN_CHANCE_*` |
| `core/world_director.py` | 世界导演通道：`DIRECTOR_TICK_INTERVAL_SECONDS=600` tick 门禁、`admit_directive` 去重/类型白名单——管的是**世界态势指令**，不是玩家个人奇遇频控，不得拿它当奇遇频控 |
| 频控缺口 | `config.py:687` `OMEN_COOLDOWN_SECONDS=600` **只定义、无人执行**：`core/omen_scene.py:997` 只写 `c.last_omen_at`，全仓无任何地方读它做拦截。自然奇遇实际频控只剩概率（生产 `omen_chance()=1%` / 测试 30%）+ 「已有进行中场景则不启新场景」（`maybe_trigger_natural_omen` 的 `get_scene` 守卫） |
| 结论 | §7 的奇遇线**不新建第三套引擎**：给现役 `omen_scene` 补配图 + 后果接链，并把已定义未执行的 600s 冷却正式生效；`event_chains` 只做「开启时配图下发」，其推进孤儿问题列待裁决（§14 D-2），本轮不修不扩 |

### C8 —— `/assets/` 今天已能被「旁路」取到，托管设计必须收口而非新开（与 mobile-web Spec C3 同源问题）

- `server/app.py` 双轨现状（mobile-web Spec §0-C3 已实测，本轮复核一致）：`_serve_static`（`do_GET` 前段先行）含 `/web/<任意文件>` 前缀分支与 `/images/<任意文件>` 前缀分支（多轮 `unquote` + `..`/`\`/`%00` 拦截 + `resolve()` 后 `relative_to` 校验）；`_static_response`（末段）是 `_STATIC_PAGES` 精确路径表。`_STATIC_CONTENT_TYPES` 已含 `.webp → image/webp`。
- `web/assets/` 资产**已由生成岗并行产齐**：本 Spec 定稿时实测 `web/assets/` 下 38 个 `.webp` 与 §3.1 清单逐项吻合（portraits 16 / artifacts 10 / arts 8 / maps 4，工作区未提交状态，提交归属见 §14 D-3）——也就是说 `/web/assets/...` 今天经前缀分支即可达，但那正是 mobile-web Spec 明令「不许依赖的旁路」。
- 结论：§4 定稿 `/assets/` 一级路径的**专用分支**（正则 + 文件名常量集合双闸），前端只许用 `/assets/...`，不许用 `/web/assets/...`；既有 `/web/`、`/images/` 前缀口径本轮**不扩大、不修复、不删除**（与 mobile-web Spec 的 Out of Scope 衔接一致）。

### C9 —— 无现成图鉴；`atlas.py` 是宗门版图、`web/images/` 是场景图包（与简报一致，补实测清单）

- `core/atlas.py` 是 F09 宗门势力版图（区域影响力/九五折），与收集图鉴无关，确认无可复用图鉴代码；全仓无 gallery/atlas 收集类模块或表。
- `web/images/` 既有 11 个文件：`cultivator_meditating.png`、`jade_slip_frame.png`、`lifespan_compass.png`、`portrait.jpg`、`realm_1.jpg`~`realm_4.jpg`、`sanctum_bg.jpg`、`sanctum_bg_dark.jpg`、`sanctum_bg_dark.png`；桌面 `web/workbench.js:24-33` 以 `ASSETS` 常量引用（场景图/命盘装饰），**没有一件是按「人物/法宝/功法/宝图」分类的图库资产**，本轮不动它们、不改其引用。
- 命盘可挂点（`server/world.py` `_status_dict`，:3934）：顶层已有 name/realm/skills/arts{main,sub}/equipped（富对象列表）/items（富对象列表，含藏宝图的 targetNodeName/isAtTarget/riddle/clue 等专属字段）/spells_catalog 等；本轮只准**只增键**（§10.1），既有键一字不改。
- 同场/NPC 可挂点：`core/here.py` `list_here`（`_look` 用）、`World.others_at`、交谈入口 `core/npc_chat.py` `open_session`（:292）/ `player_say`（:379）/ `apply_npc_reply`（:448，含本地降级 `local_hangup_or_reply` :501）。

---

## §1 · 五步推演（requirement-evaluator 全文）

### 1.1 第一步 · 解构本质

- **表层需求**：给页面配四类图（人物男女、法宝、功法、藏宝图），再加三条玩法（寻宝线索链、法宝器灵、奇遇抉择），并配一个图鉴把图「收集」起来。
- **本质诉求**：Martinez 的原话后半句才是病灶——「目前没有吸引人的玩法」。结合此前设计评审的既有结论（「AI 主导」不
...[truncated 73794 chars]可感、日常循环薄、死亡纯惩罚无元进度」：玩家缺的不是更多系统，而是**看得见的目标感与跨会话的惦记**。图解决「看得见」，三条玩法线解决「惦记」：一张图有后续（一图多寻）、一件法宝有性格（器灵长线陪伴）、一次抉择有下文（后果接进既有因果/诺言账）。
- **伪需求排除**：①「把现有页面各处贴满图」是伪路径——没有收集目标与玩法回路的贴图，三天就看腻；必须有图鉴点亮做牵引。②「再造一套新寻宝/新奇遇引擎」是伪路径——仓库已有 `TreasureEngine` 与 `omen_scene` 两套能跑的引擎（C2/C7），新引擎只会制造第三套口径与存档。③「器灵做成第二个 NPC 系统」是伪路径——`npc_chat` 的会话/心智/议程全为 Character 实体设计，法宝不是 Character，硬套必炸；器灵只需借它的**对话形态与降级范式**，状态挂在器物实体上（C5/§6）。
- **关键目标**：(a) 38 张定稿图（§3）在双端 8 类页面位置可见可达，且每张图都有明确点亮路径；(b) 三条玩法线各自有「开始→推进→结算→留痕」闭环，且数值全部过 §9 经济账；(c) 旧存档、旧命令、旧结算数值零变化（除 §7.4 明列的冷却生效一项行为收紧）。
- **验收本质**：一名新玩家在一次 30~45 分钟会话内能：定相后在命盘看到自己境界的人物图；持图按线索走完一条寻宝链并开匣；给一件天品法宝唤灵、温养、说一句话；遇上一场带配图的奇遇并在事后查到它留下的因果/诺言痕迹；在图鉴页数清自己点亮了几张、还差哪几张。

### 1.2 第二步 · 可行性评估

- **技术可行性：高。** 全部落点都是既有扩展点：图状态挂 `ItemEntity.custom_metadata`（C2 的空字段就是现成槽位）；图鉴走 WorldState KV（`event_chains`/atlas 都有先例）；托管走 `server/app.py` 既有双轨加一条专用分支（C8）；奇遇配图与后果挂 `omen_scene` 既有 start/choose 出口；器灵对话借 `ai.gateway` 的 `_chat_json/_chat_text` + 本地模板双轨（与 `get_directional_guide`、`local_hangup_or_reply` 同范式）。
- **成本画像**：新模块至多 3 个（资产解析、器灵、图鉴，建议 §10.1 分工）；配置常量 2 组；`Character` 只增 1 个带默认值字段（`gender`，§3.3）；`_status_dict` 只增键；新命令 6 条（§10.2）；无新表、无迁移脚本、无新 API 端点（全部走既有 `/action` 命令通道，与 mobile-web Spec 的零新端点口径一致）。
- **性能**：图鉴合并是集合并运算（≤38 键），挂在既有 `_status_dict` 计算路径上无新增查询（KV 读写 1 次/次状态下发，与 `event_chains` 的 KV 读写同量级）；器灵心情惰性推导（读时按时间戳折算，不新增 tick）；托管分支是正则 + 集合查表，O(1)。
- **ROI**：图库资产由生成岗并行产出，本 Spec 的成本主要是「解析规则 + 接入点 + 三个小状态机」；换来的是把已沉淀的挖宝/奇遇/装备三套存量系统全部盘活——与因果链一轮「用 20% 新代码撬动 80% 沉淀」同型。

### 1.3 第三步 · 不足与盲区（逐条已在设计中堵住，标注落点）

1. **[无性别数据]** 男女人物图没有数据源（C1）→ §3.3 新增 `gender` 字段 + `/定相` 自选，未定相不猜、不默认，用既有修行图占位并给出定相入口。
2. **[NPC 性别不可猜]** 按名字猜 NPC 男女会猜错且不可验收 → §3.4 显式名单（7 名）+ 角色规则，全名单可枚举测试。
3. **[挖宝经济已失衡在先]** 现行挖宝大表远超 caps（C3）：新链层若再叠全额奖励就是雪上加霜 → §5.5 链层独立小账 + 每日上限；现行大表改不改列待裁决 D-1，本轮冻结。
4. **[图会跟图走还是跟人走]** 宝图可交易：线索进度若挂人，卖图即丢进度/买图白嫖进度 → §5.2 定为**挂图**（进度在图实体内），并写明交易后果与防刷（链奖励按完成者计日限）。
5. **[器灵随器物流转]** 法宝可交易/被夺：器灵状态挂人会产生「灵认旧主」的脏语义 → §6.2 定为**挂器**（随器走），面板明示；成长/心情是器物属性不是角色属性。
6. **[双引擎奇遇打架]** `omen_scene` 与 `event_chains` 可同时各挂一个进行中（现状即如此）→ §7 不合并它们，只统一配图字段口径；频控分别记账，互不占用名额（沿现状）。
7. **[冷却生效是行为变更]** `OMEN_COOLDOWN_SECONDS` 生效后测试服奇遇体感会变稀（测试概率 30% 本是为验收调高的）→ §7.4 明列为本轮唯一有意行为收紧，并给 force 路径（首挖 100% 等）留豁免，验收 E-6 专门断言。
8. **[AI 剧本注入面]** `omen_scene.ingest_ai_script` 能注入新剧本：新剧本若带 `consequence` 字段可伪造因果后果 → §7.3 定：AI 剧本一律剥离后果字段，后果只认仓库内 6 部预置剧本的标注。
9. **[图鉴刷点亮]** 若按「每次打开状态页」重复触发外部钩子可刷计数 → §8 图鉴只记**集合**（点亮过没有），不记次数奖励；点亮本身零数值（§8.4），刷之无利。
10. **[图片缺失/生成未齐]** 38 张图由生成岗并行产出，可能晚于代码或个别缺失 → §3.8/§4 定缺失降级：`<img onerror>` 隐藏容器、后端不因图缺失报错；验收 G-8 覆盖缺图场景。
11. **[存量脏数据]** 旧图实体无 `clue_chain` 键、旧角色无 `gender`、旧法宝无 `spirit` 键 → 全部按「缺省即未激活」惰性读取（Pydantic 默认值/KV 缺省/ metadata 缺省三例都有仓内先例），禁止写迁移脚本扫库。
12. **[寿元红线]** 三条玩法线任何路径不得增减寿元：链层惩罚、器灵、奇遇新后果一律 `lifespan = 0` 写死（§9 总表）；注意现行 dig 的 combat 败燃寿 0.5 是**存量结算**，不在新层、 本轮不改（C3 裁定）。

### 1.4 第四步 · 举一反三

- **横向（同类资产）**：人物/法宝/功法/宝图四类图都走同一套「资产键 → 解析规则 → 接入点 → 图鉴点亮」四段式（§3 总表），将来第五类图（如灵宠图、场景图）照此扩展，不再逐类发明规则。
- **横向（其他系统）**：①器灵的「惰性推导 + 读时折算」与心魔 `DemonStateEngine` 同范式；②图鉴 KV 与 atlas 的 `sect_atlas_cap` 日限 KV 同范式；③寻宝链的日限计数与 karma_chains 的现实日预算同口径（`KARMA_CHAIN_DAILY_*` 先例）。
- **纵向（演进）**：①图鉴是账户级元进度，与转世继承（LegacyAccount 留痕）方向一致——本轮选 KV 而非 LegacyAccount 字段，是为零模型改动；将来图鉴若要长出「跨世称号生效」再迁不迟（§8.2 写明迁移路径）。②器灵成长三阶（萌生/通灵/化形）给未来「器灵主动技能」留了阶梯，本轮只兑现到战力小加成 + 对话深度（Out of Scope 明列不做主动技能）。
- **涟漪**：①`_status_dict` 增键 → 前端契约测试（`tests/test_qa2_frontend_contract.py` 一类）须同步增断言，既有断言不许削弱；②新命令进 `core/command_catalog.py` → 双端 `/commands` 目录与前端命令联想自动受益，但命令目录测试须覆盖新条目；③`omen_scene` 冷却生效 → `tests/test_omen_scene.py`/`test_natural_omen.py` 中依赖连发触发的用例可能需改用 force/注入时刻，属预期内测试维护，须在实现报告中逐条列明（不得静默改测试）；④图框 CSS 类名（§3.6）双端共用同一命名表，`workbench.css` 与 `mobile.css` 各自实现，禁止一端自创类名。

### 1.5 第五步 · 完善方案（收敛为 §3~§10 的设计）

- **推荐方案**：图库「四段式」（§3）+ `/assets/` 双闸托管（§4）+ 寻宝链挂图实体（§5）+ 器灵挂器物实体（§6）+ 奇遇只补强现役引擎（§7）+ 图鉴账户级 KV（§8）+ 经济账一页总表（§9）+ 双端接入清单（§10）。
- **备选 A（已否决）**：图鉴/线索/器灵各建新表。否决：三套状态量级都极小（图鉴 ≤38 键、链随图、器灵随器），建表引入迁移与仓储样板，违背仓内「小状态走 KV/实体 metadata」的既有惯例（event_chains、atlas、omen_scene 三例）。
- **备选 B（已否决）**：性别在注册时必填、写进 `/register` 契约。否决：改动登录/注册接口形状与双端门庭表单，回归面远大于收益；`/定相` 命令通道零接口变更且可随时改相（§3.3）。
- **备选 C（已否决）**：奇遇线顺手修复 `event_chains` 推进孤儿（给它接 `/奇遇` 子命令）。否决：`/奇遇` 已被 omen_scene 占用，双引擎抢命令必然产生语义分叉；该问题真实存在但应单独立项裁决（§14 D-2），本轮只保证配图字段不给它挖坑。
- **分阶段建议（供总管排工参考，非拆 Spec）**：第一段 图库托管 + 解析 + 双端接入 + 图鉴（G/C 组验收）；第二段 寻宝链（T 组）；第三段 器灵（S 组）；第四段 奇遇补强（E 组）。四段共用同一分支顺序合入，每段各自过验收后再进下一段。

---

## §2 · 真正需求条目（收敛结论，开发与验收的唯一依据）

- **RQ-1（图库）**：38 张定稿资产（§3.1）以 `/assets/...` 一级路径可取（§4），每张图有且仅有一个确定性解析规则把它挂到具体人物/器物/功法/宝图上（§3.3~§3.7），规则可枚举测试，不依赖 AI、不依赖猜测。
- **RQ-2（呈现）**：双端 8 类位置（命盘人物图、NPC 头像、法宝图、功法图、宝图图、奇遇配图、图鉴页、品阶图框）按 §10 清单接入；桌面既有页面与 `web/images/` 引用零改动，移动端不新增 CDN/外链。
- **RQ-3（寻宝链）**：持实体宝图者可激活一条 2~3 步线索链（§5），逐步赴节点抉择推进，终局仍走现行 `dig` 开匣；链层奖励/惩罚独立小账并有每日上限（§5.5），重复操作不重复发奖（§5.6）。
- **RQ-4（器灵）**：tier≥4 的已穿戴 equip 可唤灵（§6），器灵有名字/性格/心情/成长四维状态（挂器物实体），可对话（LLM 只出词、规则定数值、本地模板降级）、可温养（明价、每日一次、成长封顶），战力加成 ≤+3% 且心情低时不生效。
- **RQ-5（奇遇）**：现役 6 部奇遇剧本全配图（§7.2），指定剧本的指定抉择产生可查的因果/诺言后果（§7.3）；已定义未执行的 600s 自然奇遇冷却正式生效并新增每日开启上限（§7.4）；AI 注入剧本不得携带后果。
- **RQ-6（图鉴）**：账户级图鉴记录 38 键点亮集合（§8），点亮来源可枚举（§8.3），只给展示称号不给任何数值（§8.4）；双端可看（桌面独立视图 + 移动操作分区 + 双端 `/图鉴` 文本）。
- **RQ-7（守恒）**：本轮全部新动作按 §11 对照表过道体守恒律门禁并以 `CharacterRepository.save` 落盘；旧存档零迁移可读；除 §7.4 外不改变任何既有结算数值与命令语义。
- **RQ-8（降级）**：AI 全不可用时，三条玩法线与图库/图鉴全部功能可用（叙事走本地模板），验收各组均含断网/AI 关断用例。

---

## §3 · 图库定稿（资产键约定追认 + 解析规则）

### 3.1 资产清单（总管与生成岗约定，本 Spec 追认；共 38 张，`.webp`，统一水墨仙侠风）

| 类 | 路径模板 | 键数 | 键清单 |
|---|---|---|---|
| 人物·男相 | `web/assets/portraits/male-{realm}.webp` | 6 | male-lianqi / male-zhuji / male-jindan / male-yuanying / male-huashen / male-lianxu |
| 人物·女相 | `web/assets/portraits/female-{realm}.webp` | 6 | female-lianqi / female-zhuji / female-jindan / female-yuanying / female-huashen / female-lianxu |
| 人物·NPC 原型 | `web/assets/portraits/npc-{archetype}.webp` | 4 | npc-laodao（老道）/ npc-shanggu（商贾）/ npc-nvxiu（女修）/ npc-shaonian（少年） |
| 法宝 | `web/assets/artifacts/{kind}.webp` | 10 | sword / cauldron / banner / orb / mirror / bell / pagoda / gourd / fan / seal |
| 功法 | `web/assets/arts/{school}.webp` | 8 | metal / wood / water / fire / earth / thunder / sword / ice |
| 藏宝图 | `web/assets/maps/map-{rarity}.webp` | 4 | map-common / map-fine / map-rare / map-ancient |
| **合计** | | **38** | 前端引用一律写作 `/assets/...`（见 §4），**禁止**写 `/web/assets/...` |

**增删裁定**：本轮不增不删。生成岗若发现某键无法产出（如某境界男女图难分），回主策岗改 Spec 后再动，不得在实现里私自合并/改名；前端与图鉴的键集合以本表为唯一事实源，后端须有一份同表常量（建议名 `GALLERY_ASSET_KEYS`，共 38 项）供托管白名单（§4）与图鉴总数（§8）共用，三处（本表/后端常量/生成岗产出文件）不一致即验收 G-1 不过。

### 3.2 境界键映射（人物图与境界的唯一对照）

`realm key = ["lianqi","zhuji","jindan","yuanying","huashen","lianxu"][clamp(tier,1,6)-1]`，依据 `config.py:266` `REALM_NAMES`（tier 1 练气 ~ 6 炼虚）：tier 0（凡人）按 lianqi 取图；tier ≥7（炼虚以上，仓内 `REALM_EXP_REQUIRED` 只定到 6）一律封顶 lianxu。sub_tier（初/中/后/圆满）不分图。

### 3.3 玩家人物图与 `gender` 字段（C1 的解法）

- `Character` 新增字段 `gender: str = ""`（取值 `""` 未定相 / `"male"` / `"female"`）。Pydantic 默认值保证旧存档零迁移可读（仓内先例：`main_art`、`inspiration` 等均为此法新增）。
- 新命令 `/定相 男|女`（别名 `/gender`）：写 `gender` 并 `CharacterRepository.save`；可重复改相（纯外观、零数值、零成本，不设冷却——防恶意刷的唯一面是存盘次数，随 `/action` 既有节律即可，不另设闸）。门禁：`assert_alive`（§11）；闭关/被擒不拦（外观自选非重行为，不调 `assert_idle`，理由同「查体类」豁免精神，在此明写）。
- 选图规则：`gender` 非空 → `/assets/portraits/{male|female}-{realm_key}.webp`；`gender` 为空 → **不猜**：命盘人物图位显示既有 `/images/cultivator_meditating.png` 占位 + 一行定相引导（文案含 `/定相 男|女` 指引）。
- `_status_dict` 只增两键：`gender`（原值）、`portrait`（解析后的完整路径或占位路径，前端直接用，不在前端拼路径——与「前端不得自造后端语义」的前端岗禁令一致，路径拼装收口后端一处）。

### 3.4 NPC 头像映射（C1/C9：显式名单 + 角色规则，顺序即优先级）

对任一 NPC（`Character`，user_id 以 `npc_`/`ai_npc_` 开头），头像键按下列顺序判定，命中即停：

1. **女修名单**（`ROSTER` 中身份可考为女修者，显式 7 名）：苏婉清、青萝、骨姬、毒娘子、柳三娘、海娘子、小环 → `npc-nvxiu`。
2. **商贾**：所属宗门为「四海散修商会」（`npc.sect == "四海散修商会"`）→ `npc-shanggu`。
3. **老道**：`sect_rank` 或花名册 rank 含 掌门/宗主/太上/长老/护法 任一，或 `realm.tier ≥ 4` → `npc-laodao`。
4. **少年**（兜底）：其余全部 → `npc-shaonian`。

纪律：① 动态生成/召唤的 NPC（不在 `ROSTER`）只走 2~4 条规则，**永不进 nvxiu**（无性别事实源）；② 名单外出现疑似女修名（如 白霜、小雀儿）一律按规则走 2~4，**禁止实现岗按名字语感扩名单**——扩名单须回主策岗改本节；③ 解析函数须可对 `ROSTER` 全 37 人枚举出确定结果并写进单测（G-4）。

### 3.5 法宝图映射（C5：关键字 → subtype → 槽位兜底，三级确定性规则）

输入：器物名 `name`、目录 `subtype`（有则）、槽位 `slot`（§C5 五值）。按顺序命中即停：

**一级·名字关键字**（对 `name` 做包含匹配，按此序）：镜→mirror；鼎/炉→cauldron；葫芦→gourd；扇→fan；塔→pagoda；铃/钟→bell；幡/旗→banner；印/玺→seal；珠/戒→orb；剑/刃/戈/枪/刺/匣/刀→sword。

**二级·目录 subtype**：飞剑/法剑/重剑/战刃/灵刺/长戈/长枪/剑匣→sword；法杖→orb（杖头镶珠意象）；灵幡→banner；宝珠/骨戒→orb；宝铃→bell；灵佩/护身符→seal（佩印意象）。

**三级·槽位兜底**：weapon→sword；trinket→orb；flying_treasure→pagoda（楼船宝塔意象，飞舟/巨舰/破空梭/木鸢归此）；armor→mirror（护心镜意象）；boots→fan（御风意象）。

说明：三级兜底是**意象借代裁定**（armor/boots 本无对应器型图），验收只断言「任意器物恰得一键且同输入同输出」，不断言借代的语义贴切度；无 slot 无 subtype 的野器物（如 legacy 字符串升级件）最终兜底 sword。实体 `ItemEntity`（slot 只三值）与目录器物共用同一解析函数，输入缺项按缺项跳级。

### 3.6 品阶图框（C4：只认数值 tier，呈现层区分品阶——追认简报口径并定稿）

法宝图本身不按品阶分图（10 键无品阶维），品阶差异一律由 CSS 图框/光效区分，双端口径一致：

| tier | 边框类（定名） | 呈现 |
|---|---|---|
| 1 凡品 | `frame-tier-1` | 灰木细框，无光效 |
| 2 人品/灵品* | `frame-tier-2` | 铜色框 |
| 3 地品/宝品* | `frame-tier-3` | 银色框 |
| 4 天品/极品* | `frame-tier-4` | 金色框 + 静光晕 |
| 5 仙品 | `frame-tier-5` | 紫金框 + 动态流光（CSS 动画，移动端须可随 `prefers-reduced-motion` 关闭） |

\* 两套中文品阶词（C4）在数值 tier 上同值合并——这正是「只认数值」的用意：目录灵品器物（tier 数值按目录档位 2）与实体人品器物同框，前端**禁止**按中文词选框。tier 缺失/非法 → 按 1 处理。宝图图（§3.7）同理可用框区分 rarity，但不强制（宝图键本身已含 rarity）。

### 3.7 功法图与宝图图的解析

**功法图**（C6 的确定性推图，命中即停）：
1. 名字关键字（按此序）：雷/霆→thunder；冰/寒/霜→ice；剑→sword；金/庚→metal；木/青/长生→wood；水/泉→water；火/炎/焚→fire；土/岳/罡→earth。
2. 灵根兜底：取修士灵根首元素（`SpiritualRoot.elements[0]`）：金→metal、木→wood、水→water、火→fire、土→earth、雷→thunder、冰→ice、风→sword（风无专图，御风近剑，裁定归 sword）。
3. 仍无（灵根信息缺失）→ earth（吐纳中宫意象）。
注：「玄冰」类名字先中 ice（序在 water 前）是刻意裁定；「玄元聚气丹」类丹药名不适用本规则（本规则只用于功法/神通呈现：`skills`、`custom_arts`、命盘 `spells_catalog` 五门基础神通按其 `element` 字段直取 metal/wood/water/fire/earth）。

**宝图图**：按图实体 `tier` 直取：1→map-common、2→map-fine、3→map-rare、≥4→map-ancient。legacy 字符串「藏宝图」在被 `read_map/dig` 自动升实体前无 tier，呈现按 tier=2（map-fine）与现行升级口径一致。

### 3.8 缺图降级（全图库通用）

任一 `<img>` 加载失败（文件缺失/未生成/404）：前端 `onerror` 隐藏该图容器并保留文字信息，**不得**出现破图图标占位、不得报错弹窗、不得影响该卡片任何功能按钮；后端任何接口不得因图文件不存在而失败（托管层对白名单内但文件缺失的路径返回 404，见 §4）。

---

## §4 · `/assets/` 静态托管安全设计（C8：双闸收口，不动既有口径）

### 4.1 机制（主策裁定）

在 `server/app.py` 的 `_serve_static` 内、既有分支**之前**新增 `/assets/` 专用分支（`_serve_static` 本就在 `do_GET` 前段先行，此位置使其优先于 `/web/` 前缀分支与 `_STATIC_PAGES` 精确表）；`_STATIC_PAGES` 与 `_ROOT_STATIC_FILES` **不加** assets 条目（38 条逐条入表既臃肿又容易与 §3.1 常量漂移）。

放行须**同时**过两闸：

1. **正则闸**：请求路径（先经与既有分支相同的多轮 `unquote` + `..`/`\`/`%00`/空段拦截处理）完整匹配 `^/assets/(portraits|artifacts|arts|maps)/[a-z0-9-]+\.webp$`；
2. **常量闸**：相对路径（如 `portraits/male-lianqi.webp`）必须 ∈ 后端常量集合 `GALLERY_ASSET_KEYS`（§3.1 的 38 项，与图鉴共用同一事实源）。

过闸后文件路径由**常量相对路径**拼 `web/` 目录（绝不直接用请求串拼路径），再走既有 `resolve()` + `relative_to(web/assets)` 校验后读文件。任一闸不过 → 返回 False 落回既有流程（最终 404），不得返回 403/500 以免形成探测预言机差异（与既有 `_serve_static` 失败即 False 的口径一致）。

### 4.2 响应头

- `Content-Type: image/webp`（`_STATIC_CONTENT_TYPES` 已有 `.webp`，不扩展该表）；
- `Cache-Control: public, max-age=3600`——与页面类 `no-cache` **刻意不同**：图库是版本内不变的静态资产，1 小时缓存兼顾灰度期换图生效速度；理由在此明写，验收 G-6 断言此值，防止实现岗顺手抄 `no-cache` 或写成长缓存；
- `Content-Length`、`Access-Control-Allow-Origin: *` 与既有静态响应一致。

### 4.3 安全不变量（不得削弱的既有口径）

- 不新增任何其他前缀映射；不开放目录浏览；`prototype.html` 仍不可达；`/web/`、`/images/` 两条既有前缀分支的判定逻辑一字不改；
- 穿越变体（`/../`、`%2e%2e`、双重编码、反斜杠、空字节、大小写后缀 `.WEBP`、白名单外文件名、子目录再嵌套）一律不得取到文件——验收 G-7 以 ≥8 种变体断言，其中「正则合法但不在常量集合」的文件名（如 `portraits/male-foo.webp`，即使磁盘上存在同名文件）必须 404，这是双闸区别于单闸的关键断言；
- 新增路径与既有 API 路径零冲突（`/assets` 不与 `/action`、`/health` 等同名），`tests/test_web_hosting.py` 既有断言一字不改、只增不断言削弱（与 mobile-web Spec M-17 同规矩）。

---

## §5 · 玩法线一：寻宝线索链（T 组）

### 5.1 玩法结构（在现行「读图→赴点→开匣」之间插入线索阶段）

```
持实体宝图 ──/宝图──► 链激活（写 clue_chain，生成全部线索节点与谶语）
   每条线索：谶语指引中间节点 ──赴该节点──► /寻宝 抉择（守卫/陷阱/谜题，三选一，全规则裁决）
   抉择结算（小账，§5.5）─► 下一条线索 … ─► 全部走完：链置 awaiting_chest
   赴宝图目标节点 ──/挖宝──► 现行 TreasureEngine.dig 开匣结算（原样）+ 链完成奖励（小账）─► 链 completed
```

- 线索步数由宝图 rarity 定：common/fine **2 步**、rare/ancient **3 步**（§3.7 的 tier→rarity 映射同源）。
- 中间节点：从世界图谱节点中按既有 `WorldGridEngine` 口径选取（非安全区优先、排除宝图目标节点本身、与玩家当前节点不同），选取随机源须以「图 uid + 步序」播种保证同图同链可复现（见 §5.6 幂等）。
- 每条线索的呈现 = 谶语（本地模板必达；AI 可用时经 `ai.gateway` 润色一句，失败/不可用走模板——与 `get_directional_guide` 双轨同范式）+ 方位指引（复用现行八卦方位计算口径，不新造）。

### 5.2 数据模型（挂图实体，不建新表）

落点：该图 `ItemEntity.custom_metadata["clue_chain"]`（C2 的现成槽位旁位；`puzzle_data` 字段本轮**不用**，避免与未知旧语义纠缠，明写）：

```python
clue_chain = {
  "version": 1,
  "status": "active",          # active | awaiting_chest | completed | abandoned
  "seed": "<图uid>",            # 随机播种源（节点/抉择/奖励支判定的唯一随机源）
  "steps": [                    # 激活时一次性生成完毕，之后只改 settled
    {"node_id": "...", "node_name": "...", "kind": "guardian",  # guardian|trap|riddle
     "riddle_text": "...", "settled": False, "outcome": ""},   # outcome: win|bypass|fail_forward
    ...
  ],
  "step_index": 0,              # 当前步（单调递增，幂等锚）
  "activated_at": 0.0, "activated_by": "<char_id>",
  "completed_at": 0.0,
  "bonus_branch": "stones",     # stones|exp，激活时由 hash(seed) 定（§5.5），生成后不可变
  "bonus_paid": False,          # 完成奖励一次性闸门（先置 True 落盘再发奖，§5.6）
  "penalties": {"stones": 0, "exp": 0, "dao_heart": 0, "sin": 0},  # 本链累计惩罚（对 §5.5 链内子顶对账）
}
```

- 归属裁定：链**挂图不挂人**——图被交易/赠予/寄售后链随图走，接手者可续走（`activated_by` 只记首激活者，不做归属校验）；完成奖励的日限按**完成者**计（§5.5）。图被消耗（开匣/蛮力等现行耗图路径）即链随图消亡，未走完不补偿。
- 旧图（无 `clue_chain` 键）一律视为未激活，惰性兼容；同图重复 `/宝图` 只读不重建（已激活返回当前进度）。

### 5.3 触发与推进（命令面）

- **激活**：`/宝图`（现行 `read_map` 路径）在图未激活且玩家当日激活数未达上限（§5.5）时顺带激活并在原返回文本后追加链段（当前线索谶语 + 进度 `第 x/y 线索`）；已达上限时只读图、不激活、明示原因。激活不耗图、不收费。
- **推进**：新命令 `/寻宝`（别名 `/clue`）：无参 = 查看当前步（须持图且在本步节点或任意地点可查谶语）；`/寻宝 1|2|3` = 在**当前步所指节点**作出抉择（不在该节点 → 返回方位指引、不结算、不推进，与 dig 的 wrong_location 同范式）；`/寻宝 弃` = 放弃链（status=abandoned，图保留、可再激活新链？——裁定：弃后该图**不可再激活**，防刷谶语/节点重抽；图本身仍可直赴目标 `/挖宝` 开匣，走无链路径）。
- **抉择三类（全规则裁决，LLM 只写结算叙事一句）**：
  - `guardian` 守卫：选项「斗」（战力检定：`CombatEngine.calculate_power` 对守卫战力 `60+tier*45`，与现行 combat 原型同公式）/「避」（灵石 20 买路，过 `assert_currency`，不足则该选项不可选并明示）/「退」（不结算、不推进、无惩罚，当日可再来）；
  - `trap` 陷阱：选项「破阵」（按玩家灵根首元素与陷阱五行生克判定：克陷阱元素=win、被克=fail_forward、其余=bypass）/「硬闯」（bypass，必付小额惩罚下限）/「退」；
  - `riddle` 谜题：呈现谶语三选一（正确项由 seed 定序），「答对」=win、「答错」=fail_forward（每步只许答一次，答错即以 fail_forward 结算该步，不可重试刷）。
- **终局衔接**：链 `awaiting_chest` 后，玩家赴目标节点 `/挖宝`：现行 dig 全流程原样执行；dig 返回成功 outcome（perfect_solve/brute_force/combat_victory/scar_created/free_action_success）时，由链层发放完成奖励并置 completed（挂接点在服务端 `/挖宝` 与 `/做` 两个现行结算出口之后，引擎层提供统一的「开匣后钩子」供两处调用，不改 dig 内部结算一分一毫）。无链/链未走完直接挖宝 = 现行行为，零变化（链是增益层不是门禁层——**不得**把开匣改成必须先走完链）。

### 5.4 门禁（道体守恒律落点，详见 §11）

- 激活：`assert_alive`（查图类轻动作，不调 `assert_idle`——读图现行亦无 idle 门禁，保持一致）；推进抉择：`assert_alive` + `assert_idle`（赴险行为）；选「避」买路：`assert_currency(20)`/`deduct_currency`；终局开匣的背包门禁沿用 dig 内部既有 `assert_bag_space`（链层发放的完成奖励只有数值无道具，不新增背包占用）。全部写路径以 `CharacterRepository.save(char)` 收尾（图实体在角色行内，随角色行一并落盘）。

### 5.5 防刷与经济账（写死数字；与 §9 总表同源）

| 项 | 定额 | 依据/对照 |
|---|---|---|
| 每玩家每日（现实日）激活上限 | **3 条链** | 宝图本身稀缺（C3），3 条已宽于正常供给；计数落 WorldState KV `treasure_chain_daily:{char_id}` = `{date, starts, bonus_stones, bonus_exp}`（atlas 日限 KV 先例） |
| 单步抉择奖励 | **0**（步骤只推进不发数值奖；win 只免惩罚） | 防「刷步」：收益全部压到终局完成一次性发放 |
| 单步惩罚子顶（每步） | 灵石 -20 / 修为 -30 / 道心 -3 / 业力 +5，**寿元恒 0** | 均严于 `EVENT_EFFECT_CAPS` 与链内累计顶（下行） |
| 单链累计惩罚子顶 | 灵石 -40 / 修为 -60 / 道心 -5 / 业力 +10（落账前按 `penalties` 累计校验，超顶截断） | 对照 karma 子顶（stones_lose 40 / exp_lose 60 / dao_heart 5）逐项对齐 |
| 完成奖励（二选一，激活时 hash 定支） | 灵石支：`15 × tier`（15/30/45/60，天品封顶 60）**或** 修为支：`30 × tier`（30/60/90/120，地品起递增、天品封顶 120） | 对照 `KARMA_CHAIN_EFFECT_CAPS`（stones_gain 60 / exp_gain 120）逐项对齐；XOR 口径与因果链同范式（hash 不可操纵） |
| 每玩家每日完成奖励子顶 | 灵石 ≤**120** / 修为 ≤**240**（两支分别计，超顶当日后续完成只置 completed 不发奖并明示） | 灵石对齐 `KARMA_CHAIN_DAILY_STONES_MAX=120`；修为为其 2 倍（修为非硬通货，宽于灵石一档，理由在此明写） |
| 终局开匣结算 | **现行 dig 大表原样，不归本账**（C3） | 本轮冻结；是否收紧列待裁决 D-1 |

### 5.6 幂等与防重放

1. **生成幂等**：节点序列/抉择正解/奖励支全部由 `seed=图uid` 确定性生成，重复激活（已 active）只读返回，永不重抽。
2. **推进幂等**：每步 `settled` 为一次性闸门——结算先写 `settled=True + outcome + penalties 累计` 并随角色行落盘，**再**发叙事/写外部通道；同一步重复 `/寻宝 n` 返回已结算结果摘要，不二次扣罚。崩溃在落盘后 → 至多丢叙事；落盘前 → 重演同 seed 同结果。
3. **完成奖励一次性**：`bonus_paid` 先置 True 落盘再发奖（promises/因果链「先落终态锚再发效果」同范式，at-most-once）；dig 成功但链钩子异常时，奖励丢失不补发双份（下次任意 `/宝图` 查询时若 status 仍 awaiting_chest 且 dig 已耗图——图已不存在则链无从挂靠，此极端角落接受丢奖，理由：图已消耗、链载体消亡，与 C2 的载体裁定一致，在此明写不另设补偿通道）。
4. **重复查图/重复抵达**不产生任何数值副作用（纯读路径）。

---

## §6 · 玩法线二：法宝器灵（S 组）

### 6.1 资格与唤灵

- **资格**：`kind == equip` 且 `tier ≥ 4`（天品/仙品，数值 tier 口径 §C4）的器物，且处于**已穿戴**状态（`equipped` 名单内或任一 `equip_slots` 槽位，含 flying_treasure 本命法宝）。未穿戴的高阶器物不唤灵（防行囊批量刷灵）。
- **唤灵**：新命令 `/器灵` 查看已穿戴器灵面板；对符合资格且未唤灵的已穿戴器物，面板给「唤灵」入口，玩家以 `/器灵 唤 <器物名>` 唤灵：一次性、无费用、当场生成器灵四维（§6.2）并写 chronicle 一条 + 图鉴相关点亮（§8.3）。唤灵门禁：`assert_alive` + `assert_idle`（祭炼属重行为）。
- 每件器物一生只唤灵一次（`spirit.awakened` 为闸门）；卸下/再穿戴不重置；器物被毁/消耗则器灵随器消亡（不迁移到同名新器物——uid 不同即不同器灵，明写）。

### 6.2 数据模型（挂器物实体，不建 Character、不进 npc_chat 会话表）

落点：`ItemEntity.custom_metadata["spirit"]`：

```python
spirit = {
  "awakened": True,
  "name": "<器灵名>",            # 由 hash(uid) 在名字池中定（如「霜儿/烬奴/小璇…」按性格池分列，实现岗按 §6.3 池表落字）
  "personality": "lingli",       # lingli 凌厉 | wenrun 温润 | jiaohua 狡黠 | chenwen 沉稳 | zhiji 稚气 | cangsang 沧桑（hash(uid)%6 定，生成后不可变）
  "growth": 0,                   # 成长值（§6.4 封顶）
  "stage": 0,                    # 0 萌生 | 1 通灵 | 2 化形（由 growth 推导，不单独落账防不一致；落盘只存 growth）
  "mood": 60,                    # 心情 0~100（落盘值 + last_touch 推导，§6.4）
  "last_touch_at": 0.0,          # 上次温养/对话/穿戴任一互动时刻（心情衰减锚）
  "last_nourish_date": "",       # 现实日（温养日限闸门）
  "last_talk_date": "",          # 现实日（对话成长闸门）
  "nourish_count": 0, "talk_count": 0,
}
```

归属裁定：器灵**挂器不挂人**（§1.3-5）——器物交易后器灵随行，新主可继续温养/对话，面板明示「此灵曾随旧主」一句（取 `awakened_by_name` 字段记首唤灵者道号，唤灵时写入）。

### 6.3 对话（借 npc_chat 形态，不进其会话系统）

- 命令 `/灵语 <话>`：对象 = 当前已穿戴且已唤灵的器灵中 tier 最高者（并列取穿戴序在先者）；指定对象用 `/灵语 <器物名> · <话>`（分隔符裁定为「·」或首个空格前的已知器物名，实现岗二选一并在命令目录写清）。无已唤灵器灵 → 明示先唤灵。
- 引擎契约：输入（器灵四维、器物名/品阶/图键、玩家近 6 轮灵语上下文——上下文存 WorldState KV `spirit_chat:{char_id}:{item_uid}`，只存最近 6 轮文本、随器物消亡成孤儿键可接受、不得另建表）→ AI 路径经 `ai.gateway` 生成一句回复 + 一个**心情基调枚举**（pleased/calm/teasing/sullen 四值白名单）；**规则层**据枚举与当日闸门定数值（§6.4），LLM 给出的任何数字一律丢弃（gateway 侧只取 line 与 tone 两字段，其余字段忽略——与 EventValidator 的「提案清洗」同精神）。
- 本地降级：AI 不可用/超时/返回非法 → 按 personality × stage 的本地台词池出句（每性格至少 4 句、化形阶另加 2 句），tone 恒 calm；功能与成长结算不受影响（RQ-8）。
- 对话不占 npc_chat 的会话名额、不写 npc_minds 态度（器灵不是 NPC，心情就是它的态度账，不另设第二本账）。

### 6.4 温养、成长与心情（写死数字）

| 项 | 定额 |
|---|---|
| 温养命令 | `/温养 [器物名]`（缺省同 /灵语 的默认对象规则） |
| 温养成本 | tier 4：**30 灵石/次**；tier 5：**50 灵石/次**（`assert_currency`/`deduct_currency`，不足明示拒绝、零副作用）；若该器物目录条目有 `repair_materials`，另耗对应材料 ×1（背包无此材料时只扣灵石并明示「缺材温养，效力减半」：成长 +5 而非 +10——规则在引擎、文案明示，不暗扣） |
| 温养收益 | 成长 **+10**（缺材 +5）、心情 **+8**（钳 100） |
| 温养日限 | 每器 **1 次/现实日**（`last_nourish_date` 闸门，重复调用明示今日已温养、零扣费） |
| 对话成长 | 每日首次 `/灵语` 成长 **+2**、心情 **+3**；当日后续对话只叙事不涨（`last_talk_date` 闸门） |
| 成长封顶 | tier 4：**100**；tier 5：**150**。阶段：growth <50 萌生（0）/ 50~99 通灵（1）/ ≥100 化形（2，仅 tier 5 可达 100 以上，tier 4 封顶即通灵满阶——明写此不对称是品阶天花板，非 bug） |
| 心情衰减 | 距 `last_touch_at` 每满 1 现实日 **-5**，惰性推导（读面板/对话/结算加成时按当前时刻折算并回写，下限 0）；温养/对话/穿戴该器物均刷新 `last_touch_at` |
| 战力加成 | 已穿戴且心情 ≥40 时：通灵阶战力 **+2%**、化形阶 **+3%**，萌生阶 0；心情 <40 加成为 0（「器灵怠工」，面板明示）。加成接入点为装备战力汇总的既有口径（与 art_slots 的乘子加成同层叠加方式，多件已穿戴器灵**只取最高一件**的加成，不叠加——防全套高阶刷百分比） |
| 心情事件 | 阶段晋升（跨 50/100）时：chronicle 一条 + 面板/动态流一句叙事，**无数值发放**；心情跌破 20 时面板警示一句，无惩罚数值 |

门禁：温养 `assert_alive` + `assert_currency`（温养为轻行为，不调 `assert_idle`，与服丹类轻动作同档——在此明写裁定）；对话 `assert_alive` 即可（交谈先例不拦闭关？——**裁定从严**：对话调 `assert_idle`，因器灵对话属言行互动，与 `/交谈` 被擒/闭关口径对齐时以引擎实现报告为准，但 Spec 默认写死 `assert_idle`，实现岗不得放宽）。

更正上句含糊处（主策自校）：器灵对话门禁**定死**为 `assert_alive` + `assert_idle`，无裁量空间。

### 6.5 呈现

- 命盘 `equipped` 富对象只增 `spirit` 键：`null` 或 `{name, personality_cn, stage_cn, mood, growth, img}`（img 为 §3.5 解析的法宝图路径，equipped 与 items 两处富对象都增 `img` 键，见 §10.1）。
- 桌面行囊/穿戴卡显示器灵名 + 阶段 + 心情条；传音弹窗形态的灵语对话复用桌面 chatModal 的视觉容器但走 `/灵语` 命令通道（不新开弹窗系统）；移动端在行囊分区点已穿戴器物进详情卡（温养/灵语按钮即命令）。

---

## §7 · 玩法线三：奇遇抉择事件（E 组）——只补强现役 `omen_scene`

### 7.1 边界（先划清，防第三套引擎）

- 本线只动 `core/omen_scene.py` 这一套现役系统（6 部节点图剧本 + 交谈奇遇模板 + AI 剧本注入通道）；`core/event_chains.py`（23 模板）本轮**只加一件事**：`maybe_start` 成功开启时，其返回/呈现文本所对应的模板按下表 §7.2 末行规则带一张配图键（供前端渲染），引擎逻辑、触发率、caps 一字不改；`core/events.py` 单步事件不动。
- 抉择结构（节点/选项/自由言行边）、效果钳制（`_clamp_effects` 复用 `EVENT_EFFECT_CAPS`，dao_heart ±10、lifespan ±5 硬钳）全部沿现行，本线新增的只有：配图字段、后果字段、频控执行（§7.4）。

### 7.2 配图（illustrated：每部剧本定稿一图，取自 38 键，不新增图片）

| 剧本 | 配图键 | 理由 |
|---|---|---|
| black_market 黑市兜售 | `portraits/npc-shanggu` | 黑市商贩 |
| orphan_trust 旧友托孤 | `portraits/npc-shaonian` | 托孤少年 |
| spring_dispute 灵泉争饮 | `arts/water` | 灵泉水象 |
| stele 残碑悟道 | `maps/map-ancient` | 残碑古卷 |
| escort_deal 商队护卫 | `artifacts/banner` | 镖队旗幡 |
| inn_whisper 客栈夜话 | `portraits/npc-laodao` | 夜话老者 |

- AI 注入剧本（`ingest_ai_script`）：配图按剧本标题关键字走 §3.7 功法图同序关键字规则兜底（命中关键字取 arts 键；未命中取 `maps/map-common`）；此配图仅呈现，不点亮图鉴（§8.3 只认上表 6 部预置剧本的配图点亮，防 AI 剧本刷点亮）。
- `event_chains` 23 模板配图：按模板 `kind`/标题关键字走同一兜底规则（opportunity 类多为悟道/机缘，缺省 `maps/map-fine`）。
- 下发口径：场景开启/推进的服务端返回只增 `omen_image` 键（完整 `/assets/...` 路径）；桌面内联奇遇芯片条上方渲染该图（§10），移动端动态流奇遇卡同渲染；自由言行（`/奇遇说`）推进不换图（仍用本场开启图）。

### 7.3 后果接链（抉择有下文：因果链 / 诺言 / 江湖痕迹）

预置剧本的**指定终局节点**新增可选后果标注（数据在剧本定义内、引擎统一执行；每场至多触发一条后果，防叠账）：

| 剧本/抉择 | 后果 | 落点（全部既有引擎） |
|---|---|---|
| orphan_trust 接受托孤 | 立一条真实诺言（quest 型，对象为剧本内具名 NPC 角色；该 NPC 须为场景生成的临时 NPC 或同场既有 NPC，由剧本定义指明，取不到角色实体则降级为仅江湖痕迹） | `PromiseEngine` 既有 `make_promise` 通道，ttl 沿 promises 既有口径（3~7 游戏年档） |
| escort_deal 接受护卫 | 同上（arrive/quest 型，目的地为剧本指定节点） | 同上 |
| black_market 举报黑市 / spring_dispute 夺泉伤人 | 与涉事 NPC 结一条因果边（恩/仇按抉择极性）+ 态度移位 | `collusion.ensure_link`（strength +1，既有 upsert）+ `npc_mind.shift_attitude`（**±10 子顶**，见下） |
| 其余终局（全部剧本通用） | 江湖痕迹一条：`jianghu.append_event`（kind 用新值 `"omen_encounter"`，public 同步 chronicle 沿既有）+ EventLedger 角色账一条 | 既有写入口，不新建通道 |

- 子顶（新后果层独立小账）：态度移位 **|Δ| ≤ 10/场**；KarmaLink 只 +1 strength 且经 ensure_link 既有语义（达阈后是否起因果链由 karma_chains 的 S2 规则自然决定，本线不直调因果链引擎——两线解耦）；寿元 **恒 0**；不直接发灵石/修为（数值仍只走既有 `_clamp_effects` 的抉择效果）。
- 幂等：后果以场景实例 id 为键记入场景存档的 `consequence_done: true`（先置位随场景落盘、再执行后果；场景终局处理重入时短路——与 §5.6 同范式）。承诺创建失败（如对方已死）→ 降级江湖痕迹，不重试、不报错断场。
- AI 剧本**一律剥离**后果标注（注入清洗时删除 `consequence` 键及其同义字段），后果只认上表预置剧本（§1.3-8）。
- 与因果链的边界：本线写 KarmaLink/态度后，因果链 S1/S2 是否起链是 karma_chains 自己的规则（跨阈才起，±10 单场通常不起链）——这是刻意设计：奇遇是「因」，因果链是「果」的延迟兑现，两线只经事实账连接，不互相直调。

### 7.4 频控（把已定义未执行的冷却正式生效 + 每日上限）

| 项 | 定额 | 说明 |
|---|---|---|
| 自然触发冷却 | **`OMEN_COOLDOWN_SECONDS=600`（现实秒）正式生效**：距上次自然奇遇开启 <600s 时 `maybe_trigger_natural_omen`（非 force 路径）不开启新场景 | C7 缺口修复；`last_omen_at` 现行只写不读，本轮在触发器内补读判。**这是本轮唯一有意收紧的既有行为**，须写入实现报告与灰度手册 |
| 豁免 | force 路径（首挖 100% 奇遇、命令直开 `/奇遇` 查看/推进既有场、交谈内奇遇分支）不受冷却与日限约束 | 保住首图体验与既有命令语义 |
| 每日开启上限 | 每玩家 **5 场/现实日**（自然触发计，计数落 omen 场景存档同 KV 的日计数键，口径同 §5.5 日限 KV 先例）；达限后当日至多呈现无数值叙事？——裁定：达限直接不开启（返回 None，同未触发），不搞「空壳场」 | 与概率（生产 1%）叠加后实际远低于此顶，此顶是防测试服 30% 概率与脚本连刷的硬闸 |
| 进行中上限 | 沿现行：已有进行中场景不启新场（`get_scene` 守卫）；`event_chains` 侧沿现行（单人 1 条、全服 8 条） | 不合并、不互占（§1.3-6） |
| 导演通道 | `world_director` 的 600s tick 门禁与本线无关，不动 | C7 已划清 |

### 7.5 门禁与降级

- 场景开启/抉择沿 omen_scene 现行状态判定（DEAD 不触发等），本线新后果执行前加 `assert_alive` 复核（后果写账属角色数据写路径）；抉择效果落账沿现行 `CharacterRepository.save` 出口（server `/奇遇` 分支既有），不新增落盘点。
- AI 全不可用：预置 6 部剧本纯本地可跑（现行即如此），配图/后果/频控全为规则层，零影响（RQ-8）。

---

## §8 · 图鉴（C 组）：账户级收集，KV 落点定稿

### 8.1 落点裁定（主策定：WorldState KV，不用角色字段、不用 LegacyAccount 字段）

- 键：`gallery_atlas:{user_id}`，值：`{"unlocked": {"<asset_key>": <首次点亮时间戳>, ...}, "titles": ["<已获称号>", ...]}`。asset_key 用 §3.1 的相对键（如 `portraits/male-lianqi`），总数以 `GALLERY_ASSET_KEYS`（38）为全集。
- 选 KV 的理由：① 图鉴是**账户级**元进度（跨角色/跨世保留——玩家转世后图鉴不灭，这正是「死亡不再纯惩罚」的元进度补强，与转世继承的设计方向一致）；② 零模型改动、零迁移：`Character` 与 `LegacyAccount` 都不动，旧账户读时缺省空图鉴；③ 仓内先例充分（event_chains 的 KV 状态、atlas 的日限 KV）；④ 数据量极小（≤38 键 + 称号数组），KV 整值读改写的并发面可控：服务端写路径在 `World.handle` 锁内（与 event_chains 同环境），CLI 为单进程——明写此并发口径与 event_chains 现状一致，不新造锁。
- 否决角色字段：图鉴挂 `Character` 会随死亡/转世语义纠缠（留还是不留都要动转世结算），且同账户多角色各一份图鉴自相矛盾。否决 LegacyAccount 字段：需改账户模型与道统结算读路径，回归面大于 KV 方案；将来若要图鉴称号产生跨世生效效果，迁移路径 = 把 KV 值整体搬进 LegacyAccount 新字段（数据形状已按此预留：unlocked 字典 + titles 数组可直接平移），本轮不做。

### 8.2 读写口径

- **合并式点亮（唯一写入口）**：一个统一的图鉴服务函数（建议名口径：`gallery.unlock(user_id, keys, now)` / `gallery.merge_from_status(user_id, status_snapshot)`，名字由实现岗定、语义按本节）：入参一组键，与存量取并集，只增不减；返回本次**新点亮**的键列表（供前端 toast「图鉴新点亮：法宝·镇海塔」与称号判定）。
- **派生型点亮（防漏钩）**：凡能从命盘快照直接推导的类别，不在各业务引擎里散埋钩子，统一在 `_status_dict` 组装完成后做一次合并——快照里已有的事实：本境界及以下全部境界的本人性别图（§8.3-1）、当前行囊+穿戴中每件器物的法宝图、已习得功法（含 spells_catalog 五门）的功法图、持有宝图的宝图图。这样探险掉宝、交易得宝、挖宝得装备等**全部入包路径天然覆盖**，不需要逐个 loot 点埋钩（埋钩必漏，派生必全——这是本节核心裁定）。
- **事件型点亮**：无法从快照推导的（NPC 原型、奇遇配图）走事件钩子：交谈开启成功、同场列表组装、奇遇开启三处（§8.3），钩子一律 try/except 包裹，失败不影响主流程（照仓内一切呈现钩子惯例）。

### 8.3 点亮口径（逐类写死；「看见即点亮」与「拥有即点亮」的分界）

| 类 | 点亮条件 | 类型 |
|---|---|---|
| 本人人物图（12 键中本性别 6 键） | 已定相后，`realm.tier` 达到该境界即点亮**当前及以下全部境界**的本性别图（例：金丹玩家点亮 lianqi/zhuji/jindan 三张本性别图）；对方性别 6 键**永不**经此路径点亮（须靠 NPC/奇遇等其他呈现？——裁定：对方性别图只能由 §8.3 NPC 行的同原型呈现间接触及不到，故对方性别 6 键的点亮路径定为：**同场/交谈遇到的玩家角色**（异性玩家的人物图在同场列表呈现时按其 gender+realm 点亮）——玩家↔玩家呈现同样走 §3.3 选图规则 | 派生（本人）+ 事件（同场玩家） |
| NPC 原型图（4 键） | 与任一映射到该原型的 NPC **交谈开启成功**（`open_session` 成功）**或**该 NPC 出现在同场列表组装结果中 | 事件 |
| 法宝图（10 键） | 器物进入行囊或穿戴（以命盘快照中出现为准，含交易/掉落/锻造/挖宝所得） | 派生 |
| 功法图（8 键） | 功法出现在已习得列表/自创功法/主修辅修中（以快照推导为准）；基础五神通按 spells_catalog 呈现即点亮其五行键 | 派生 |
| 宝图图（4 键） | 持有对应 rarity 的宝图（快照 items 中出现 TREASURE_MAP 且 tier 命中） | 派生 |
| 奇遇配图（复用上述键） | 6 部预置剧本任一场开启成功，点亮其 §7.2 配图键（该键同时也在上行各类中，属同一键的不同点亮路径，不重复计数） | 事件 |

- 计数口径：图鉴总数恒 38；进度 = |unlocked ∩ GALLERY_ASSET_KEYS| / 38；unlocked 中出现全集外的键（脏数据/AI 污染）一律忽略不计且合并时清除。

### 8.4 奖励口径（定死：只给展示称号，零数值）

- 里程碑：点亮数达 **10 / 20 / 30 / 38** 时各得一个图鉴称号：`初窥门径`（10）/ `博览群真`（20）/ `洞鉴乾坤`（30）/ `图录大成`（38）。称号只出现在：图鉴页、命盘「图鉴」行（展示当前最高称号 + 进度 x/38）、里程碑达成时一条 chronicle + 动态流贺词。
- **不给**灵石/修为/寿元/功德/业力/道心/物品/战力中的任何一项；称号不写入 `SocialProfile.dao_title`（不与既有尊号系统抢位）、不产生任何加成。理由：图鉴点亮靠「看见/拥有」被动达成（含交易可得），一旦挂数值即成可刷经济源（§1.3-9）；展示+称号已足够形成收集牵引。若未来要给数值，须另立 Spec 过经济账——本轮明写禁止实现岗顺手加奖。

### 8.5 呈现与命令

- 桌面：新增第 6 主境视图「图鉴」（§10.2），按四类分组的网格：已点亮显图（带 §3.6 图框类）、未点亮显剪影占位（CSS 滤镜/暗图）+ 点亮条件一句（如「结丹后点亮」「与商贾交谈或同场」）；顶部进度与称号。
- 移动：不新增底部导航项（5 项已满，mobile-web Spec 定稿不动），图鉴放「操作」分区内的整页分区段 + 命盘分区底部进度行入口。
- 命令：`/图鉴`（别名 `/gallery`）双端同源文本（引擎层出文本，server 与 CLI 各接一分支——照 /因果链、/墓碑先例）：分组列出已点亮/未点亮与进度、最高称号。读命令无门禁（查体类，死亡可查自己图鉴——图鉴是账户资产，角色死亡不冻结，明写）。

---

## §9 · 经济账总表（本轮全部新数值，一页对清；QA 按此对账）

| 来源 | 灵石 | 修为 | 寿元 | 业力/功德/道心 | 其他 | 上限锚 |
|---|---|---|---|---|---|---|
| 寻宝链·单步抉择 | -20..0/步 | -30..0/步 | **0** | 道心 -3/步、业力 +5/步 | 「避」买路 -20 灵石（计入灵石惩罚顶） | 单链累计：灵石 -40、修为 -60、道心 -5、业力 +10 |
| 寻宝链·完成奖励 | +15×tier（≤60）**或** 0 | 0 **或** +30×tier（≤120） | **0** | 0 | XOR 二选一（hash 定支） | 每日：灵石 +120、修为 +240 分别封顶；激活 ≤3 条/日 |
| 寻宝链·终局开匣 | 现行 dig 大表（冻结，不归本账，C3/D-1） | 同左 | 现行（combat 败 -0.5 为存量） | 现行 | 现行装备/丹掉落 | — |
| 器灵·温养 | -30（tier4）/ -50（tier5）/次 | 0 | **0** | 0 | 材料 ×1（有目录配方时；缺材效力减半） | 1 次/器/日；成长封顶 100/150 |
| 器灵·对话 | 0 | 0 | **0** | 0 | 成长 +2（每日首次）、心情 +3 | 成长总封顶同上 |
| 器灵·战力加成 | — | — | — | — | 战力 +2%（通灵）/+3%（化形），多灵取最高一件，心情 ≥40 才生效 | 参照 art_slots 辅修 +3%/门、封顶 6% 的同量级 |
| 奇遇·新后果层 | 0（直接数值） | 0 | **0** | 态度 ±10/场、KarmaLink +1 strength | 可立真实诺言（走 promises 既有账） | 冷却 600s、日开启 ≤5（自然触发） |
| 奇遇·抉择效果 | 沿现行 `_clamp_effects`（caps 300/200） | 沿现行（caps 800） | 沿现行硬钳 ±5 | 沿现行（dao_heart ±10 等） | — | 存量口径，不动 |
| 图鉴 | **0** | **0** | **0** | **0** | 仅展示称号 ×4 | 结构性零（§8.4） |
| 定相 | 0 | 0 | 0 | 0 | 纯外观 | 无冷却 |

对账要点（QA 必查）：① 新层全部灵石正流入只有寻宝完成奖励一条，日顶 120 与因果链日顶同值；② 器灵是净流出（温养付费）+ 百分比加成，其加成与 art_slots/套装加成的叠加方式须在实现报告中给出实际汇总公式位置，QA 按「单灵取最高」断言不叠加；③ 寿元列除存量 dig 一格外全 0，任何新代码路径出现 lifespan 写操作即 must-fix。

---

## §10 · 双端接入点清单（桌面 workbench + 移动 mobile + 后端字段 + 命令）

### 10.1 后端字段（`_status_dict` 只增不改，既有键一字不动）

| 增键 | 位置 | 内容 |
|---|---|---|
| `gender` / `portrait` | 顶层 | §3.3（原值 / 解析后路径） |
| `img` | `items[]` 与 `equipped[]` 每项 | 按 kind 分发：equip→§3.5、treasure_map→§3.7、其余 kind→空串（前端空串不渲染图位） |
| `spirit` | `equipped[]` 每项 | §6.5（未唤灵/不符合资格为 null） |
| `gallery` | 顶层 | `{unlocked: [<相对键>...], count, total: 38, title: "<最高称号或空>", newly: [<本次新点亮键>]}`（newly 只在发生合并点亮的那次下发中非空，其余次为空数组——前端据此 toast 后即弃，不持久化） |
| `omen_image` | `/奇遇` 系列与一切携带 omen 字段的 `/action` 返回 | §7.2（本场配图完整路径；无场为空串） |
| `clue_chain` | `items[]` 中宝图项 | `{status, step, total_steps, current_node_name}` 摘要（未激活为 null；详情走 `/寻宝` 文本，不把全链塞进命盘） |

### 10.2 命令面（全部走既有 `/action` 通道；`core/command_catalog.py` 各加一条目录）

| 命令 | 别名 | 落点 | 双端 |
|---|---|---|---|
| `/定相 男\|女` | `/gender` | server `World.handle` 新分支（照 /因果链 分支同段）+ CLI 同名分支 | 双端（引擎出文本） |
| `/寻宝 [n\|弃]` | `/clue` | server 新分支；CLI 同名分支调同一引擎 | 双端 |
| `/器灵 [唤 <名>]` | `/spirit` | 同上 | 双端（面板文本同源） |
| `/温养 [名]` | `/nourish` | 同上 | 双端 |
| `/灵语 <话>` | `/spirit_say` | server 新分支（需 AI 编排时在 server 层调 gateway，照 npc 交谈的 server 编排先例）；CLI 端 AI 不可用时直接走本地台词路径 | 双端（降级口径不同属可接受，数值一致） |
| `/图鉴` | `/gallery` | 同 /因果链 先例 | 双端 |

注：CLI 侧多条命令现为「局域网专有」（cli/main.py 帮助文案口径）；本轮 6 条命令的引擎全部落在 `core/`，CLI 接入成本只是分支转发——**要求双端都接**，不得以「LAN 专有」为由只做 server（ /因果链 先例即双端）。

### 10.3 桌面端（web/index.html + web/workbench.js + web/workbench.css）

1. 顶栏主境导航新增第 6 项「图鉴」（`data-view="gallery"`），新视图渲染函数（建议名 `renderGallery`）读 `status.gallery` + 全集常量（前端持一份 38 键展示表：分组/中文名/点亮条件文案——展示文案可前端持有，**点亮事实只认后端 unlocked**）。
2. 命盘（`renderSanctum`）：洞府主视觉区加人物图（`status.portrait`，含图框外沿，不改既有背景图引用与布局骨架）；心法/功法列表每项加功法图缩略（§3.7，前端按后端下发——功法图路径须由后端在 arts 相关结构中增 `img` 键下发，或前端持与 §3.7 同规则的镜像实现？——**裁定：后端下发**。`skills` 现为纯字符串列表不便挂键，故在 `arts` 结构旁只增 `art_images: {<功法名>: <路径>}` 一键，覆盖 skills + custom_arts 全部功法名；spells_catalog 每项只增 `img` 键）。
3. 行囊/穿戴（`renderInventory`）：器物卡加图（`it.img` + §3.6 图框类）；已穿戴卡加器灵行（`it.spirit`）；宝图卡加宝图图 + 线索链进度行（`it.clue_chain`）与「寻宝」入口按钮（发 `/寻宝`）。
4. 宝图详情（现行 `handleTreasureAction` 双阶段弹窗 :4293）：未抵达态加宝图图与当前线索谶语段；抵达开匣态不变。
5. 交谈弹窗（`#chatModal` / `renderChat`）：对方头像（按 §3.4 解析——头像路径由后端在交谈开启/同场结构中增 `avatar` 键下发，前端不自算原型）；同场修士列表（神识抽屉）每人头像同理（玩家按 §3.3、NPC 按 §3.4，后端在同场结构增 `avatar` 键）。
6. 奇遇内联芯片条（`renderInlineOmenBar`）：标题行上方加配图位（`omen_image`），图缺失按 §3.8 隐藏图位。
7. 灵语：复用 chatModal 容器开「器灵」会话样式（标题为器灵名+头像位=法宝图），消息走 `/灵语` 命令，不复用 NPC 会话的状态机。

### 10.4 移动端（web/mobile.html + web/mobile.js + web/mobile.css）

1. 命盘分区（`sanctum`）：顶部加人物图卡（`status.portrait`），下方加图鉴进度行（x/38 + 最高称号，点击跳操作分区的图鉴段）。
2. 行囊分区（`bag`）：器物行加缩略图（`img` + 图框类，图框类名与桌面同名表，mobile.css 自行实现样式）；已穿戴器物详情卡加器灵段（温养/灵语按钮即命令）；宝图行加宝图图与线索进度、「寻宝」按钮。
3. 世界分区（`world`）：同场列表每人头像（`avatar` 键）。
4. 操作分区（`ops`）：新增图鉴段（四类分组列表，点亮显图、未点亮显条件文案；不做网格大图，移动端以紧凑列表为定稿形态）+ 定相入口（两按钮发 `/定相`）。
5. 动态分区（`feed`）：奇遇卡加配图（`omen_image`）；图鉴新点亮 toast 沿移动端既有 toast 通道。
6. 纪律：不新增底部导航项、不新增 CDN/字体、图片一律 `/assets/...` 或后端下发路径、触控目标 ≥44px 与字号口径沿 mobile-web Spec D2-⑥。

### 10.5 前端共同纪律

- 前端**不拼**资产路径、不自算解析规则：portrait/img/avatar/omen_image/art_images 全部由后端下发完整路径（§10.1/§10.3-2 的裁定）；前端唯一持有的图库知识是图鉴页的 38 键展示表（分组与文案），且其键集合须与后端常量逐项一致（契约测试断言，G-9）。
- 既有 `ASSETS` 常量（`web/images/` 场景图）一字不改；新图不进 `web/images/`。

---

## §11 · 道体合规守恒律对照表（AGENTS.md 强制，逐动作落点）

| 新动作 | assert_alive | assert_idle | assert_currency / deduct | assert_bag_space | 落盘 |
|---|---|---|---|---|---|
| `/定相` | ✔ | —（§3.3 裁定） | — | — | `CharacterRepository.save` |
| `/宝图` 激活链 | ✔ | —（读图轻动作，与现行一致） | — | — | 同上 |
| `/寻宝` 抉择 | ✔ | ✔ | 选「避」时 ✔（20） | —（链层无道具产出） | 同上 |
| `/挖宝` 终局（存量） | 沿 dig 内部既有门禁（含 bag_space）不改 | | | | 沿既有 |
| `/器灵 唤` | ✔ | ✔ | — | — | 同上 |
| `/温养` | ✔ | —（§6.4 裁定） | ✔（30/50） | — | 同上 |
| `/灵语` | ✔ | ✔（§6.4 定死） | — | — | 同上（对话上下文 KV 不属角色行，另存 §6.3） |
| 奇遇后果写账 | ✔（执行前复核，§7.5） | 沿 omen 现行 | 沿 omen 现行（INSUFFICIENT_STONES 语义） | — | 沿 server /奇遇 既有 save 出口 |
| `/图鉴` / 各面板查询 | —（只读查体类，§8.5） | — | — | — | 图鉴合并写 KV（非角色行；角色行不因查询而 save） |

通则：凡上表标 ✔ 的写路径，任一门禁失败必须**零副作用**返回明示文案（照 `TreasureEngine.dig` 的 try/except 门禁范式）；全部角色行写盘只走 `CharacterRepository.save`（其内置 6 大不变式审计），禁止直写 DB 或绕过仓储改角色字段后不落盘。

---

## §12 · Out of Scope（明确不做，出现即超纲）

1. 不改现行挖宝结算数值/掉率/原型结构（C3），不改 legacy `DigEngine` 旧表；不统一两套品阶中文词（C4）。
2. 不新建第三套奇遇引擎；不修复 `event_chains` 推进孤儿（D-2 待裁决）；不改 `events.py` 单步事件与 `world_director` 导演通道。
3. 不给功法新造 element/school 字段、不改自创功法 DSL 语义；不给 NPC 补性别字段（头像只走 §3.4 名单+规则）。
4. 器灵不做：主动技能/自动战斗托管、器灵间互动、器灵夺舍/反噬剧情线、把器灵接入 npc_mind/npc_agenda；器灵战力加成不做多件叠加。
5. 图鉴不给任何数值奖励/加成（§8.4）；不做图鉴交易、不做全服图鉴排行。
6. 不做图片上传/玩家自定义头像/图片审核；不做 PWA/离线图片缓存策略（§4 的 HTTP 缓存头除外）。
7. 不动 `web/images/` 既有 11 图与桌面既有引用；不动 mobile-web 的分流与导航结构（图鉴不占第 6 个底部导航位）。
8. 不新增 API 端点、不改 `/register`/`/login`/`/action` 接口形状（只增 `_status_dict` 与命令返回的只增键）。

---

## §13 · 验收（G/T/S/E/C 五组，每条须有可观察证据）

约定：数值类验收一律以角色行/KV/链存档的**落盘值**对账，不以文案为准；AI 类验收须各跑一遍「AI 可用」与「AI 关断（`ai_ready()=False`）」两态；双端命令验收 server 与 CLI 各一份证据（§10.2）。

### G 组 · 图库与托管

| # | 条目 | 检查方法 |
|---|---|---|
| G-1 | 38 键三处一致 | 后端常量 `GALLERY_ASSET_KEYS`、`web/assets/` 磁盘文件集、本 Spec §3.1 表三方逐项比对（脚本枚举 diff 为空）；缺图时该项记 PRE-EXISTING-ASSET 并单独列明（不许用改常量删键的方式对齐） |
| G-2 | 全图可取 | 对 38 个 `/assets/...` 路径逐一 GET：200 + `Content-Type: image/webp` + 字节与磁盘一致（文件缺失的键按 G-1 名单除外并明示） |
| G-3 | 人物图解析 | 造 tier=1..6 × gender=male/female 角色读命盘：`portrait` 依次为对应 12 键路径；tier 0 按 lianqi、tier 7 按 lianxu；未定相角色 `portrait` 为占位图路径且页面出现定相引导 |
| G-4 | NPC 原型解析枚举 | 对 `ROSTER` 全 37 人跑解析函数：每人恰得一键；7 名女修名单全中 nvxiu；商会成员（非女修名单者）全中 shanggu；输出全名单结果存实现报告备查 |
| G-5 | 法宝图解析枚举 | 对 `EQUIPMENT_CATALOG` 全 132 件跑解析：每件恰得 10 键之一、同输入重复调用结果一致；另造含 镜/鼎/葫芦/扇 的器物名各一，分别命中 mirror/cauldron/gourd/fan |
| G-6 | 缓存头 | GET 任一 assets 路径断言 `Cache-Control: public, max-age=3600`；GET `/` 与 `/mobile.html` 仍为 `no-cache`（既有口径未被误改） |
| G-7 | 托管安全 | ≥8 种变体均非 200：`/assets/../config.py`、`/assets/%2e%2e/config.py`、`/assets/portraits/%2e%2e%2fconfig.py`、`/assets/portraits/male-foo.webp`（磁盘预置同名文件仍须 404）、`/assets/portraits/male-lianqi.WEBP`、`/assets/portraits//male-lianqi.webp`、`/assets\portraits\male-lianqi.webp`、`/assets/portraits/male-lianqi.webp/extra`；且 `/prototype.html` 仍 404、`tests/test_web_hosting.py` 既有断言全过 |
| G-8 | 缺图降级 | 临时移走任一一张已接入图：双端对应页面功能全通、无破图图标、无报错弹窗（截图或 DOM 断言） |
| G-9 | 双端契约 | 前端契约测试断言：双端源码中不出现 `/web/assets/` 字样；图鉴展示表键集 == 后端常量键集；`_status_dict` 既有键集合不缺失（只增断言） |

### T 组 · 寻宝线索链

| # | 条目 | 检查方法 |
|---|---|---|
| T-1 | 激活与步数 | tier 1/2/3/4 图各激活一条：步数依次 2/2/3/3；`clue_chain` 落盘字段完整（seed=图uid、bonus_branch 已定）；同图重复 `/宝图` 不重建（step_index 与 steps 不变） |
| T-2 | 日激活上限 | 同玩家同现实日激活第 4 条链被拒且明示；KV 日计数 starts=3；跨日（注入日期）可再激活 |
| T-3 | 推进与地点门禁 | 不在当前步节点 `/寻宝 1`：返回方位指引、零落盘变化（角色行与链字段逐项比对）；在本步节点抉择后 step_index+1 且该步 settled=true |
| T-4 | 三类抉择裁决 | guardian 斗（战力两侧各造一例：胜/败结果与 `60+tier*45` 公式一致）、避（扣 20 且灵石不足时不可选零副作用）、trap 五行生克三态（克/被克/无关各一例）、riddle 答错后该步以 fail_forward 结算且不可重答 |
| T-5 | 惩罚子顶 | 构造全步最差路径连走 3 条链：单链 penalties 累计不超过 灵石40/修为60/道心5/业力10；全程寿元字段逐值不变 |
| T-6 | 完成奖励与日顶 | 走完链并开匣（dig 成功 outcome）：奖励按 bonus_branch 单支发放且金额 = 公式值（两支各验一例）；同日多链完成累计达日顶后，后续完成只置 completed、奖励为 0 且有明示 |
| T-7 | 无链直挖零回归 | 未激活链的图直接 `/挖宝` 全流程与基线行为逐项一致（结算数值同公式、耗图时机同 C2）；弃链后图可直挖、不可再激活 |
| T-8 | 幂等 | 同步重复提交同一步抉择 ×3：只结算一次（penalties 与 step_index 只动一次）；完成奖励重复触发（模拟钩子重入）：只发一次（bonus_paid 闸门） |
| T-9 | 门禁 | 死亡角色激活/抉择被拒；闭关中抉择被拒（assert_idle）；两态均零副作用（落盘比对） |
| T-10 | AI 降级 | AI 关断态走完一条链：谶语走本地模板、抉择与结算数值与 AI 态同分布口径（同 seed 同结果） |

### S 组 · 法宝器灵

| # | 条目 | 检查方法 |
|---|---|---|
| S-1 | 资格与唤灵 | tier 3 已穿戴器物唤灵被拒；tier 4 未穿戴被拒；tier 4 已穿戴唤灵成功：spirit 落盘（personality ∈ 6 值、name 非空、awakened_by_name 正确）；重复唤灵不重置四维 |
| S-2 | 温养账 | tier4 温养：灵石 -30、growth +10、mood +8（钳顶验证）；同日第二次温养零扣费被拒；缺材料场景 growth +5 且文案明示；灵石不足零副作用；tier5 扣 50 |
| S-3 | 成长封顶与阶段 | 刷满：tier4 growth 止于 100 且阶段为通灵；tier5 止于 150、≥100 为化形；阶段晋升时 chronicle +1 条且无任何数值发放 |
| S-4 | 对话与降级 | AI 态对话：回复非空、LLM 返回中的数字字段不入账（构造含伪造数字的 mock 返回断言 growth/mood 只按规则动）；AI 关断态：本地台词按 personality 出句；每日首次对话 growth +2、第二次 +0 |
| S-5 | 心情衰减与加成 | 注入 last_touch_at 为 3 日前读面板：mood 按 -15 折算（钳 0）；心情 ≥40 且通灵：战力汇总含 +2% 且多件器灵只取最高（造两件通灵断言总加成 2% 非 4%）；心情 <40 时加成为 0 |
| S-6 | 随器流转 | 器物交易给另一角色：spirit 字段随器走、新主面板可见「曾随旧主」；器物销毁后无残留器灵状态可被同名新器物继承 |
| S-7 | 门禁 | 闭关中 `/灵语`、`/器灵 唤` 被拒；温养灵石不足被拒；均零副作用 |

### E 组 · 奇遇抉择

| # | 条目 | 检查方法 |
|---|---|---|
| E-1 | 六部配图 | 逐部开启 6 部预置剧本：返回 `omen_image` 与 §7.2 表逐项一致；双端奇遇呈现含该图（DOM 断言） |
| E-2 | 后果·诺言 | orphan_trust/escort_deal 走到指定抉择：`PromiseRepository` 新增对应诺言一条且字段（类型/对象/ttl）合 promises 既有口径；对方实体取不到时降级为江湖痕迹且场景正常终局 |
| E-3 | 后果·因果边 | black_market/spring_dispute 指定抉择：KarmaLink 对应边 strength +1、态度移位 |Δ|≤10 且方向与抉择极性一致；同场重演不重复记后果（consequence_done 闸门，模拟终局重入断言） |
| E-4 | 后果·痕迹 | 任一剧本任意终局：jianghu 新增 kind="omen_encounter" 一条（public 时 chronicle 同步 +1）、EventLedger 角色账 +1 |
| E-5 | AI 剧本剥离 | 注入带 consequence 字段的 AI 剧本并走完：无诺言/因果边/态度后果产生；其配图走兜底规则且不点亮图鉴 |
| E-6 | 冷却生效 | 非 force 自然触发开启一场后，600s 内（注入时刻）再次自然触发不开启；force 路径（首挖）仍可开；`/奇遇` 查看/推进既有场不受冷却影响 |
| E-7 | 日上限 | 注入时刻连开自然奇遇至第 6 场（跨冷却注入）：第 6 场不开启；次日恢复 |
| E-8 | 存量零回归 | 6 部剧本各走一条与基线相同的抉择路径：效果落账与基线逐值一致（`_clamp_effects` 口径未变）；event_chains 模板开启文本与基线一致、仅多配图键 |

### C 组 · 图鉴

| # | 条目 | 检查方法 |
|---|---|---|
| C-1 | KV 落点与兼容 | 老账户（无 KV 键）读图鉴为空集 0/38 不报错；点亮后 KV `gallery_atlas:{user_id}` 结构合 §8.1；Character/LegacyAccount 模型无新字段（除 Character.gender，git diff 断言） |
| C-2 | 派生点亮 | 给角色发放各 rarity 宝图/各图键法宝/习得功法后读一次命盘：对应键一次性齐点亮（逐类各验）；交易得来的法宝同样点亮（证派生非埋钩） |
| C-3 | 本人图点亮 | 定相 female 且 tier=3 的角色：female-lianqi/zhuji/jindan 点亮、female-yuanying 未点亮、male-* 全未点亮（同场异性玩家路径另验一例） |
| C-4 | 事件点亮 | 与商会 NPC 同场：npc-shanggu 点亮；开启 stele 奇遇：maps/map-ancient 点亮；AI 剧本开启不点亮（与 E-5 对照） |
| C-5 | 零数值奖励 | 点亮数跨过 10/20/30/38 四档前后逐项比对角色行与账户行：灵石/修为/寿元/功德/业力/道心/钱包全等；仅 titles 数组与 chronicle 变化；称号不出现在 dao_title |
| C-6 | 双端呈现 | 桌面图鉴视图：38 格分组齐全、已点亮显图未点亮显条件文案；移动操作分区图鉴段同内容；`/图鉴` 双端文本进度与 KV 一致 |
| C-7 | 跨世保留 | 角色死亡转世后以同账户新角色读图鉴：unlocked 集合不变（账户级断言） |
| C-8 | 脏键清理 | 手工往 KV 塞全集外键：读图鉴不计数、合并后该键被清除 |

---

## §14 · 待总管裁决项（主策不擅自定论者，仅此三项）

- **D-1（经济存量）**：现行挖宝大表单笔灵石最高 1100（caps 的 3.7 倍）且无日限（C3）。本 Spec 已冻结它（新链层另设小账），但真人试玩在即，这个存量口子是否要在本轮顺手收紧（如对齐 caps 或加日限）属产品/经济决策——主策建议**不在本轮动**（避免与本轮验收面纠缠），请总管决定是否另立经济校准工单。
- **D-2（event_chains 孤儿）**：23 条奇遇模板能开启、无入口推进（C7）。本轮只给它配图。是否另立工单把它的推进接回某个命令（如 `/机缘`）——涉及与 omen_scene 的命令面划分，主策不在本 Spec 内裁定。
- **D-3（图库资产提交归属）**：38 张图已由生成岗产齐在本 worktree 工作区（未提交，§0-C8 实测与 §3.1 清单逐项吻合），本 Spec 提交**不带**这批资产文件。请总管裁定资产由生成岗单独提交还是随第一段实现一并提交；G-1/G-2 验收以「资产已入仓」为前提，若届时个别图被替换/删减，须回主策岗同步 §3.1，不得静默改键。

（除以上三项外，本 Spec 内的一切口径——资产键、映射规则、托管双闸、三玩法数值、图鉴落点——均为已批准方向内的主策裁定，开发岗直接执行，遇 Spec 缺口按 one-person-company 规矩回主策岗修 Spec，不得边写边改契约。）

---

## 真正需求条目（收敛结论重述，开发与验收的唯一依据）

1. **问题**：页面无分类图库、玩法缺长线牵引（宝图单步开匣、法宝无灵、奇遇无下文），且仓库现状与简报前提有 9 处出入（§0）。
2. **行为契约**：38 张定稿图经 `/assets/` 双闸托管（§4），按 §3 确定性规则挂到人物/器物/功法/宝图；寻宝链挂图实体、器灵挂器物实体、奇遇只补强现役引擎、图鉴挂账户 KV（§5~§8）；全部新数值过 §9 总表；双端接入按 §10 清单；守恒律按 §11 对照表。
3. **边界**：不改存量结算与引擎语义（唯一例外：§7.4 冷却生效），不建新表、不加新 API、不动品阶中文词与功法 DSL，清单见 §12。
4. **验收标准**：G-1~G-9、T-1~T-10、S-1~S-7、E-1~E-8、C-1~C-8，共 42 条。
5. **不做范围**：§12 共 8 项；待裁决 3 项（§14）未裁前按本 Spec 的冻结口径执行。

---

## §15 · 收尾补记（2026-11-07，收尾总管）：rebase 与 mobile 预算豁免

- **Rebase**：本分支原基线 `12332f0`（v0.3.5 合并点），收尾时 rebase 至 main `cc92fab`（v0.3.6-gray.13，移动版设计重做）。13 个提交全部重放，仅「双端视觉接入」一个提交产生冲突，文件仅 `web/mobile.css`、`web/mobile.js`。解法口径：**设计重做的结构与设计语言优先**（卡片拆分、品阶 pill、display-row、toast token 版、坞区口径全部保留），图库增量（配图、图框缩略图、器灵块、线索链、定相、图鉴段）以嫁接方式并入对应渲染点；分支基于旧结构改写的行结构（如 eq-row/bag-row 的纯文本版）不采纳，只取其图库内容。
- **Token 纪律不豁免**：图库 CSS 块原稿使用裸 hex，触发设计重做契约 `test_mobile_redesign_tokens_and_no_bare_hex` 失败。收尾轮未申请纪律豁免，而是将图库块全量 token 化：同值/近值色映射既有 token（--jade-900/--on-jade/--line-gold/--grad-bar 等），品阶图框色新增 `--frame-1..5` 与光晕 `--frame-*-glow*`、器灵深色面板次级色 `--spirit-muted/--spirit-track`（昼夜 token 表各一组）。该测试现已通过。
- **体积预算第二次豁免（本节即裁定记录）**：R-21 预算原为设计重做轮自身体量所设（CSS ≤21094B、mobile.js 净增 ≤40 行；重做交付时余量仅 CSS 12B / JS 1 行）。图库接入是新增功能面（图鉴、立绘、器灵、线索链的移动端呈现），其实测增量为 CSS 图库块 + token 定义、JS 接入代码本体，非重做轮返修。收尾总管裁定：CSS 上限 21094B → **25702B（25.1KB，实测 25566B）**、mobile.js 净增上限 40 → **190 行（实测 +186）**；`tests/test_mobile_web.py::test_mobile_redesign_budgets` 的断言与 docstring 已同步修订并注明本节出处。此后任何轮次再增移动端体量，须另行申请豁免并留记录，不得静默改上限。
- **桌面端**：workbench.css/workbench.js/index.html 与 main 侧无重叠改动，rebase 自动合并，设计重做未触桌面端，无冲突、无豁免事项。
