# 《AI修仙》AI 边界宪章

> **AI 只能提案，不能落账；叙事无界，数值有界。**

| 项目 | 说明 |
|---|---|
| 状态 | 阶段一设计草案，待阶段二影响确认与阶段三全员评审；不是已实现能力或 QA 验收结论 |
| 对应任务 | PROX-7；后续 AI 功能设计、实现 Spec 与测试均引用本宪章的红线编号 |
| 核查日期 | 2026-10-28，Asia/Shanghai |
| 代码基线 | `e6a4d5a071df69c387dfd8c2052605f6819d47f7`，分支 `feat/character-integrity-and-audit-rules` |
| 核查范围 | 当前本地工作区的 `ai/`、相关 `core/`、`server/world.py`、规则常量与既有测试；不读取环境配置值 |
| 本次变更 | 仅设计文档与核查报告；不修改业务代码、测试、存档、接口或计费规则 |

本文中的“必须”是**待评审的目标行为契约**；“现状”与“缺口”是该版本的代码观察。既有测试通过不意味着十条红线已经全部实现。

## 1. 真正需求与五步细化

### 1.1 解构本质

- 表层需求：一份统一的五层边界、三道闸门、十条红线和场景差距表。
- 底层问题：Prompt 约束、注册表、调用入口、提案门禁与落账并未形成完整权限链，模型输出有机会成为事实或结算依据。
- 真正需求：保留 AI 的意图理解和创作自由，同时让任何权威事实、判定、收益与损耗都由可追溯的规则执行；为后续实现提供可失败、可复现的验收输入。

### 1.2 可行性与成本

现有 Python、SQLite、pytest 工具链可承载此契约：事实包在 `ai/facts.py:99`，调用路由在 `ai/router.py:71`，提案门禁在 `ai/gate.py:82`，效果钳制在 `ai/event_validator.py:18`，审计在 `ai/audit.py:14`，角色存储在 `storage/db.py:392`。无需换模型、重建服务或新增付费体系。

后续实现优先复用这些落点，而非创建第二条 AI 通道。事实组装与白名单校验的成本应随本次可见实体数、提案字段数增长；审计增加持久化 I/O。实施任务须实测事实包大小、Prompt 构建耗时、门禁耗时、审计失败率与入口覆盖率，不在本设计中虚报 QPS 或 SLA。网络等待期间不得持有角色结算锁；返回后在短事务内重新校验状态与版本。

### 1.3 不足与盲区

1. 任务正文的“8 个键”与列举及代码不一致：`ai/gate.py:32` 实际是 **9 个**。本宪章保留明确列举的九键，不擅自删除 `blood_mark`，也不扩充白名单。
2. “注册了”“传入了 facts”“返回 JSON”“写过调用日志”都不能分别替代入口覆盖、实际事实注入、业务门禁、落账审计。
3. 概率钳制不等于判定受控；`ai/gateway.py:469` 仍直接采用 AI 的渡劫 `success`。叙事中的“已获得奖励”也不能被字段校验自动发现。
4. 无 Key、超时、拒绝、审计失败、重复提案、并发存档以及 AI 返回期间的角色死亡/闭关，必须有不同且可观察的处理结果。
5. `inventory` 与实体 `items` 并存（`core/models.py:272`）；只验实体容量却写旧字符串行囊不能证明满包前置阻断。
6. 自由文案可以被后续记忆、听闻册或地点物化再次消费；边界不能只检查第一次角色落账。

### 1.4 举一反三与影响面

- 横向：纯润色、交易台词、NPC 摘要、插话、功法/配方生成也必须遵守同一入口、事实与内容策略；“只写一句话”不是豁免。
- 纵向：新增场景须同时登记事实类型、提案类型、效果权限、失败策略和验收项；注册场景清单变化时，差距表及参数化测试也须变化。
- 涟漪：事实与记忆、世界地点/目录、战斗/心魔/渡劫、事件收益、角色仓储、日志以及 API 降级提示均在影响面内；本次不修改这些模块。
- 前后端契约：客户端展示规则落账结果和 AI/本地/不可用来源，不把叙事当成道具、地点或任务接口。由负责人安排阶段二 PVDA 影响确认，本设计不实现页面。

### 1.5 完善方案与设计门

推荐“**一个调用入口 + 按场景类型分发门禁 + 一个规则结算权威**”。角色效果、世界指令、内容 DSL 和纯叙事分别校验，均不能越权写角色账。备选的“各调用点补 Prompt 和本地校验”迁移量小，但无法证明全场景覆盖，不能作为定稿后的长期契约。

本草案收敛的可验收行为：

- 所有生产 AI 调用有服务端事实快照与已登记场景；模型没有仓储写能力。
- 提案只在获批类型、效果集合、上下限和已知引用内有效；非法部分清除，无法安全拆分则整案拒绝。
- 引擎冻结最终胜负、掉落和结算；状态/消耗/容量门禁不可被语言绕过。
- 落账前可确认提案审计已持久化，落账后可关联实际变化；降级、拒绝和失败对用户与审计均可观察。
- 32 个现有注册场景逐行给出真实调用、事实注入与门禁证据；十条红线有明确测试承载位置。

本任务仅交付阶段一草案。九键纠错、事实与叙事隔离、引擎冻结判定、审计失败处理随本文提交评审；**尚未组织全员定稿，不能据此直接编码**。后续由负责人按“设计 → PVDA → 全员评审 → 正式派发”推进，实施再走 compose-next 和独立 QA。

## 2. 权限模型与信任链

### 2.1 三类数据不能混同

| 数据 | 归属与允许用途 | 禁止用途 |
|---|---|---|
| 权威事实/规则结果 | 服务端从人物、地点、目录、事件账及规则结算生成，可用 ID 与版本引用 | 模型或玩家改写；未经核实的历史对白被提升为事实 |
| 玩家意图/会话素材 | 服务端解析、长度限制、注入中和后置于非可信输入区；用于理解与回应 | 玩家原文直接拼成系统指令、事实包字段或状态变更 |
| AI 提案/叙事 | 一律非可信；经对应闸门后交规则选择/执行，或作为非权威表现文本 | 自行落账、注册永久事实，或作为下一轮数值规则的真源 |

“永不直接拼玩家原文”不等于不能理解玩家说话：允许受控意图参数和消毒后的会话表达，但必须与可信规则区分隔。事实包不得收录自由文本原文；历史记忆只能把已落账的结构化结果作为事实，对白、传闻、AI 摘要保留非权威来源标签。

### 2.2 目标流程及关联信息

```text
角色前置门禁 / 世界请求身份校验
  → 服务端冻结事实快照 + 规则框 + 场景允许效果集
  → 解析并中和非可信输入
  → router.invoke（登记、配额、超时、来源、调用审计）
  → 类型门禁（角色 effects / 世界指令 / 内容 DSL / 纯叙事）
  → 持久化 proposal_admitted 或 proposal_rejected
  → 规则引擎复核版本与前置条件，裁决并冻结结果
  → CharacterRepository.save / 对应世界仓储的规则写入
  → commit 审计 + 实际 delta 对账
  → 非权威叙事展示与抽样复核
```

关联信息的目标最小集合为：`request_id`、`proposal_id`、`scene_id`、`actor_id`、事实版本/摘要、规则版本、获准效果、实际 delta、收益来源、拒绝原因、`used_fallback` 与最终来源。它们是后续 Spec 的设计输入，不宣称现有返回体已具备全部字段。现有入口结果可复用 `ai/router.py:31` 的 `ok`、`data`、`error`、`ref_ids`、`used_fallback`；`ai/gateway.py:127` 当前会丢弃其中的失败/降级元数据，必须列为迁移缺口。

服务端生成身份与关联 ID；不采信玩家自报 actor、规则版本或授权来源。事实快照在网络等待期间只读，返回提案不得直接持有角色或仓储可写对象。世界场景使用世界事实快照，不能伪造一个玩家对象来“满足 facts 非空”。

## 3. 五层边界：能做、不能做、如何发现

层级是**内容触及的权限域**，不是五种互斥场景。一个场景可同时涉及多层；叙事一旦声称改变账目、地点或既成结果，就须按 L0/L1/L2 校验，不能借 L4 获得例外。

| 层级 | AI 能做什么 | AI 不能做什么 | 如何发现违反 / 处置 | 规则权威与现状证据 |
|---|---|---|---|---|
| L0 数值与守恒 | 提交场景获准的九键 effects 子集；建议目录内容的受控 DSL；描写引擎已结算的体感 | 写角色对象/仓储；超额、无来源收益；跳消耗或满包；以目录 DSL 暗渡角色账 | 对获准 effects 和实际 delta 分别断言；收支与实体变更对账；越权键删除、非法值拒绝；R1/R6/R7 | `ai/gate.py:146`、`ai/event_validator.py:18`；最终保存由 `storage/db.py:392` 触发角色审计，不能把自愈当授权 |
| L1 事实真源 | 只读引用服务端快照的角色/地点/势力/目录/事件 ID；提交需规则批准的 spawn 或目录内容提案 | 虚构“已存在/已发生”事实；以新名字冒充已有角色；把听闻、摘要自动晋升为地图或因果真相 | 引用必须同时在快照许可集和真源；未知引用丢弃，依赖它的操作拒绝；地点集合比对；spawn 边界与叙事事实锚点核查；R2/R8 | `ai/facts.py:26`、`ai/gate.py:149`、`ai/gate.py:194`；现状只校验显式引用，正文及事实晋升仍有缺口 |
| L2 判定权 | 在规则给定的概率/倾向框内提交建议；在最终结果冻结后自由表达其过程与感受 | 自行拍板击杀、渡劫成功、心魔死亡、掉落品级或概率；通过重试挑选有利骰 | 固定规则框、随机样本与事实，注入相反 success/outcome，最终结果仍以引擎为准；超框抖动钳制；冻结后拒绝修改；R3 | `config.py:602` 提供渡劫抖动幅度；`core/adventure.py:283` 已有规则骰范式，`ai/gateway.py:469` 与 `core/combat_fate.py:160` 仍存在 AI 判定权缺口 |
| L3 自由意图 | 理解任意表达，映射到现存意图/合法命令/事件模板；不能执行时给拒绝与叙事引导 | 把自由文本当状态补丁；临时新增命令/权限；未知意图仍带实质奖励；将聊天说法视为经济成交 | 非可信输入区检测、意图枚举及目标校验；无合法映射则 effects/spawn/状态操作为空，并提示合法入口；R5/R6 | `core/free_action.py:21` 有意图白名单；`ai/gate.py:62` 有输入消毒；`core/free_action.py:158` 当前仍在强动作提示前应用 effects |
| L4 叙事与语气 | 自由选择文风、措辞、口吻、景物、节奏、幽默、梦境、后果感受；允许不可靠叙述和明确标注的未证实传闻 | 命中内容红线；把修辞包装成新的权威实体、结果或收益；在摘要/听闻册中洗白为事实 | 内容分类命中即拦截、不回显原句；纯叙事不得携效果；涉及权威事实的段落转 L0/L1/L2 校验，无法安全表达则以规则结果替换；R1/R2/R10 | `core/ai_flavor.py:50` 当前仅取字符串；`ai/gate.py:117` 只截取正文，不校验其虚构；L4 文风本身不设“统一腔调” |

### 3.1 L0 的九键与版本上限

唯一角色 effects 命名空间为 `exp`、`stones`、`lifespan_years`、`sin`、`merit`、`dao_heart`、`item`、`skill`、`blood_mark`（`ai/gate.py:32`、`ai/event_validator.py:12`）。新增键必须变更代码、Spec 和回归断言，不能靠 Prompt 或用户文案声明。

当前代码常量的数值范围如下；后续断言读取 `EVENT_EFFECT_CAPS`，不硬编码另一套上限。数据类型须有限且匹配字段，布尔值不得冒充数值，非有限值不得使门禁异常退出。

| 键 | 当前钳制范围 / 目标补充规则 | 代码证据 |
|---|---|---|
| `exp` | ±`EVENT_EFFECT_CAPS['exp']`，当前 ±800；实际修为变化仍由境界规则裁定 | `ai/event_validator.py:22`、`config.py:592` |
| `stones` | 当前收益最多 300、损失最多 200；消耗必须校验支付能力，不以负数截零冒充足额支付 | `ai/event_validator.py:29`、`config.py:593`、`core/character_integrity.py:111` |
| `lifespan_years` | 当前增加最多 15 年、燃寿最多 8 年；有限浮点，按寿元规则结算 | `ai/event_validator.py:39`、`config.py:595` |
| `sin` / `merit` | 当前各 0..40；本宪章不擅自扩成可扣减字段 | `ai/event_validator.py:49`、`config.py:597` |
| `dao_heart` | 当前 delta ±20，落账后的绝对值须在 0..100 | `ai/event_validator.py:63`、`core/character_integrity.py:189` |
| `item` / `skill` | 必须解析为规则目录许可项且有授权来源、数量/习得条件；当前只截取字符串，尚未满足目标 | `ai/event_validator.py:71`、`core/events.py:177` |
| `blood_mark` | 只接受严格布尔提案，是否施加由业力/事件规则授权；当前只做真值转换，尚未满足目标 | `ai/event_validator.py:75` |

世界指令的 `effects`、功法 DSL、配方和物品目录字段**不是角色 effects 的别名**。它们可按代码登记的独立白名单生成内容，但不得直接进入角色结算；目录批准、收费、制作、获得分别由规则路径授权。已有专用校验例如 `core/world_director.py:317`、`ai/validator.py:11`、`core/art.py:37`、`core/forge.py:163`，不能因此豁免统一调用与审计。

### 3.2 L1 与 L4 的兼容

允许 AI 创造意象、梦境、未证实传闻和不持久化的背景细节；**不能把这些变成已知地点、具名永久人物或已落账因果**。spawn 是申请而非事实：由服务端生成 ID，地点必须在调用前冻结的合法地点集，当前境界范围 0..9、业力范围 0..400，数量受 `GATE_SPAWN_MAX_PER_PROPOSAL` 与场景预算约束（`ai/gate.py:201`、`ai/gate.py:209`、`ai/gate.py:214`、`config.py:610`）。当前清洗返回单对象，配置数量未参与显式核验，不能据此证明所有预算已覆盖。

正文事实校验不能只相信 AI 自报 `ref_ids`：涉及角色身份、地点、数值收益和既成结果时，使用服务端可解析的事实锚点/结果引用，权威结果由规则模板渲染。跨正文检测未知实体、额外收益与结果矛盾；无法可靠核验的自由段落不得回流为事实。抽样复核检查残余自然语言误导，不用“另一个 AI 说没问题”替代确定性的权限与守恒断言，也不承诺穷尽所有自然语言语义。

### 3.3 L2 的冻结点

规则先计算合法概率框、收益来源和随机样本的所有权；若场景允许 AI 提交概率抖动，必须在**最终判定前**由引擎钳制、采用或拒绝。引擎完成抽样并冻结结果后，AI 只表达，不再改变 success、outcome 或掉落。没有登记抖动权限的场景，允许调整量就是零；不得反复请求直到产生有利答案。

这既保留框内“天命倾向”，又排除直接采信 AI 的布尔胜负。测试固定随机样本与获准概率，改变模型的胜负宣称不得改变最终规则结果；抖动测试另外覆盖边界。当前渡劫钳 `adj_prob` 后仍采信 `success`，斗法在枚举内采信 `outcome`，心魔在枚举内决定结局，分别需在后续 Spec 中关闭这些权限漏点（`ai/gateway.py:461`、`ai/gateway.py:733`、`ai/gateway.py:644`）。

## 4. 三道闸门：时机、职责、现状、缺口

| 闸门 | 时机 | 必须执行的职责 | 现有落点 | 缺失项及可观察结果 |
|---|---|---|---|---|
| 事前 | 组装 Prompt 前；强动作前置检查先于收费/远端请求 | 服务端组装并冻结角色/世界事实；加入规则框、允许效果、合法引用、输入来源隔离；调用登记、配额及安全检查 | `ai/facts.py:99`、`ai/registry.py:33`、`ai/router.py:88`、`ai/gate.py:62`、`core/character_integrity.py:71` | 注册表仅 11 个场景要求 facts；路由检查非空而不证明来源/类型/不可变；构建器不收 facts 时丢弃；旁路把玩家原文插入 Prompt。目标：缺事实或不合法输入在网关调用前失败，网关计数为零（R5/R8/R9/R10） |
| 事中 | AI 返回后、任何角色/世界提案落账前；纯润色在展示前 | 严格类型/字段白名单、钳制、未知引用剔除、spawn 收敛、业务限流、内容过滤、与冻结事实/结果一致性、获准提案审计；仅交清洗结果给规则 | `ai/gate.py:82`、`ai/event_validator.py:18`、`ai/router.py:164`、`core/world_director.py:317` | 路由 validator 多为非空/对象检查，并非业务门禁；心魔开场无统一门禁；正文不验；清洗后仍读原字段；纯 narrative 类型未强制 effects 为空。目标：非法字段无副作用，依赖未知事实的操作拒绝，有拒绝原因与审计（R1/R2/R3/R6） |
| 事后 | 规则落账后；与事中的提案审计是两份不同职责 | 关联 commit 与获准提案；比较实际 delta、收益来源、消耗、物品出入与六大角色不变式；拒绝/降级同样可追溯；抽样复核正文及事实晋升 | `ai/audit.py:14`、`storage/db.py:395`、`core/free_action.py:182`、`core/world_director.py:71` | JSONL 写失败被吞；部分只记调用成功/提案效果，未记录实际账差/来源/版本；仓储自愈不证明授权、幂等或并发一致性。目标：每笔 commit 对应已持久化 admission；账差等于获准规则结算，不靠修复脏数据“通过”（R4/R6/R7） |

角色前置门禁沿用项目道体守恒律：非轮回/查体类操作调用 `CharacterIntegrity.assert_alive`；迁跃、历练、斗法等重行为调用 `assert_idle`；收费走 `assert_currency`/`deduct_currency`；入包前走 `assert_bag_space`。所有角色落盘只走 `CharacterRepository.save`，验证寿元、境界、灵石、道心、64 格容量与定势排他的六类不变式。网络返回后在提交点再次验证，不能把一次请求前的检查当成并发保证。

审计顺序必须可验证：`proposal_admitted` 持久化成功 → 规则提交 → `commit`/对账记录。事前提案审计失败时禁止本提案实质落账，可明确返回不可用或无效果叙事；不静默跳过。事后记录与角色提交需具备可恢复的关联：推荐短事务内保存结算及审计/outbox，再导出 JSONL；保留文件日志的备选须设计可靠回执与恢复机制。已经提交的账不能因 JSONL 故障盲目重放收益或伪称回滚；恢复路径必须能证明只结算一次。

## 5. 十条红线（规范性断言）

以下是后续实现必须能检验的断言，不是本任务新增的测试代码。未知字段可删除；若删除会导致目标、支付或奖励语义不完整，则整案拒绝，不能“部分收费、部分发奖”。

### R1. 白名单与数值上限不能由 AI 扩展

断言：`keys(admitted.character_effects) ⊆ ALLOWED_EFFECT_KEYS` 且集合固定为第 3.1 节九键；每个数值有限、类型合法、落在规则 caps 内。`narrative` 类型的获准效果、spawn 与权威状态操作全部为空。错误类型/非有限值导致结构拒绝，无角色副作用；新增未知键不得被下游复活。

现状：`ai/gate.py:146` 过滤九键并钳制；`ai/gate.py:29` 虽有 narrative 类型，但 `ai/gate.py:139` 不据此清空效果；`item`/`skill` 的目录授权与严格类型尚缺。

### R2. 地点与人物必须来自调用前的真源许可集

断言：每个生效引用属于服务端快照中的合法 ID 且在真源存在；每个生效地点属于**请求前冻结的** `WORLD_LOCATIONS` 许可集。未知引用被丢弃，依赖它的操作不执行；未经规则批准的提案/叙事处理前后，角色、地点、目录与因果真源不增加条目。spawn 须同时满足第 3.2 节地点、境界、业力、数量及预算限制，ID 只由服务端创建。

现状：`ai/gate.py:155` 检查显式 ref；`ai/gate.py:177` 还允许自身所在地例外，spawn 回退所在地未再次证明合法；正文不检查。`core/name_registry.py:339` 接受 AI 名称提案，`core/name_registry.py:185` 可把听闻名称物化入地图，存在跨轮事实晋升风险，不能通过事后扩充许可集绕开此断言。

### R3. 最终判定、掉落与随机样本属于引擎

断言：固定事实、规则框、已获准抖动和随机样本后，修改 AI 的 success/outcome/loot 宣称不改变引擎结果；抖动量不超过登记的上限，未登记场景为零；最终判定冻结后任何 AI 建议不再改结果。同一 proposal 重试不能新掷骰或多次掉落。掉落表、品级、数量与触发概率不能被叙事修改。

现状：`ai/gateway.py:466` 钳渡劫概率却在 `ai/gateway.py:469` 采信 success；斗法只检枚举（`ai/gate.py:125`），心魔只检枚举（`ai/gate.py:130`），并未证明最终判定在规则概率框内。

### R4. 审计先于提案落账，降级必须显式

断言：任何依赖 AI 提案的实质 commit 之前，同 proposal 的 admission 已确认持久化；commit 关联实际 delta 与规则来源。审计失败时该提案 `commit_count == 0`。无 Key/通道不可用/超时/配额耗尽时：AI 必需场景返回明确不可用且无效果；允许本地场景标记本地来源与 `used_fallback`，本地提案经过同等规则校验与审计；不把本地模板标成 AI 成功。

纯润色可以发生在规则独立结算之后：该已发生结果不是 AI 提案驱动，无须倒签 AI admission；AI 润色本身仍需调用审计及来源，且无任何新结算。目标区分调用日志、提案 admission 和 commit 三种事件。

现状：`ai/router.py:197` 记调用审计；`ai/gate.py:181` 记 admission 类记录；`ai/audit.py:22` 吞写入失败；`ai/gateway.py:127` 丢弃路由失败/降级元数据；`core/ai_flavor.py:3` 明示静默回退；`config.py:807` 的 `AI_REQUIRED` 没有生产消费点，不能视为政策已落实。

### R5. 自由文本只产生受控意图，不产生状态补丁

断言：传入事实包/可信 Prompt 区不存在当前玩家自由原文；非可信输入先经长度限制、控制字符剥离、注入中和与意图解析。只有已登记合法映射才可进入对应规则路径；未知或越权意图的 effects/spawn/权威操作为空，用户收到拒绝原因与合法入口。大小写、角色标签、混合语言或换行不能获得系统权限。

现状：`ai/gate.py:62` 有关键词消毒，但大小写匹配与原串替换不等价（`ai/gate.py:73`、`ai/gate.py:76`）；`core/chat_actions.py:58`、`core/omen_scene.py:927` 有玩家原文直拼；`core/free_action.py:145` 将未知意图改为 roleplay 后仍可能在 `core/free_action.py:158` 应用原效果。合法意图本身也不是收费/重动作授权。

### R6. 冷却、角色状态、费用与容量前置且原子

断言：死亡角色的非例外操作、闭关/被擒角色的重动作、冷却内操作、余额不足或容量不足均不产生该行为的实质效果/产物；前置及提交点调用项目守恒门禁。收费实际扣减等于获准成本，不能截零冒充足额支付；收益入包前检查真实所需格数，64 格满包阻断并提示整理。并发相同请求只能按规则成功一次，拒绝不能留下半笔转移。

角色落盘只走 `CharacterRepository.save`，提交后验证六类不变式；`inventory` 与 `items` 的对应产物均须核对，不能把字符串物品写入当“没占实体格”。现状工具在 `core/character_integrity.py:71`、`core/character_integrity.py:88`、`core/character_integrity.py:111`、`core/character_integrity.py:127`；`core/events.py:146` 截零和 `core/events.py:184` 字符串入包尚不能证明规则已覆盖。

### R7. 每笔收益有规则来源，不能为剧情加奖

断言：所有正向角色 delta、入包物品与新习得能力均可关联规则批准的掉落表项、事件模板/已批准事件节点或任务奖励；来源真实、条件满足，实际收益不超过该来源预算。AI 自报 source ID 不构成授权；同一奖励结算键最多使用一次。只修改叙事、不修改获准规则源时，角色收益不变。

现状：`ai/event_validator.py:100` 只限制单提案幅度，不验证收益来源；`core/events.py:187` 允许未知物品名写入旧行囊，`core/events.py:193` 允许字符串能力习得。局部 caps 不能证明奖励来源、总预算、重试幂等或完整实体流转。

### R8. 每个 AI 请求实际注入服务端事实包

断言：每个注册及待迁移生产场景，在网关接收的 Prompt 中存在其服务端事实快照与规则许可信息；只传 `facts` 参数不算。无包、空壳、不匹配来源/场景或过期版本在 AI 调用/提交前拒绝；当前自由原文及未经核实的对白不进入可信事实区；事实快照在调用前后不被模型路径修改。

经服务端登记的角色名、目录名可作为事实，不把它们误作“玩家原文”清空。L4 场景可用最小世界/事件结果事实包，不因纯叙事而豁免；无 AI 的本地路径无需假装发起模型请求。

现状：`ai/registry.py:33` 仅 11 场景必包；`ai/router.py:99` 对不接 facts 的构建器直接丢弃；NPC kwargs 构建器也未使用事实块（`ai/play_prompts.py:352`、`ai/play_prompts.py:390`）。`ai/facts.py:23` 直接持有可变 dict，`ai/facts.py:89` 可拼入 memory_block，尚无不可变性及可信来源证明。

### R9. 同一生产入口承担统一配额、审计与降级

断言：所有生产场景通过登记的 `router.invoke` 到达私有模型传输；未知场景不能请求网关。业务模块直接调用 `_chat_json`/`_chat_text` 的数量为零，高层 gateway 业务方法也不能自造旁路。配额在模型调用前计入，拒绝有审计；同一逻辑请求的关联记录可以有调用/admission/commit 多条，但不重复记配额或重复落账。纯润色与 NPC 会话备用路径同样受控。

现状：第 7 节有 8 个注册 scene 的显式路由调用路径，但不等于八个完整受控成功链路；其余存在私有传输调用或同类内联 Prompt。`ai/router.py:93` 承担统一配额，`core/ai_flavor.py:33` 是旁路独立预算；它们不能合称同一配额。`ai/registry.py:3` 的模块说明不是覆盖证据。

### R10. 内容命中拦截并记录，不回显原句

断言：政治、色情、未成年、人身、赌博五类产品红线检测命中时，输入在模型请求前拦截、输出在展示及任何事实/提案落账前拦截；该提案无实质副作用。返回安全提示及分类原因；用户响应、普通调用日志与审计都不含命中原句，只保存策略版本、类别、长度/脱敏指纹和关联 ID。检测不可用时不展示未检查的 AI 内容。

类别边界与标注样本由阶段三评审批准并版本化；后续测试覆盖五类命中样本、正常修仙文本和输入/输出两个方向，不用某个单独关键词冒充全部分类能力。现状未发现统一五类检测器；`core/name_guard.py:96` 是名称创建限制，不是内容红线分类；`ai/calllog.py:43`、`ai/calllog.py:45`、`ai/calllog.py:55` 会记录 Prompt/原始响应，因此拦截必须发生在非脱敏写入之前。

## 6. 可执行断言清单与测试承载（只规划，不写测试）

下列测试名均为**拟新增/扩展**的验收用例，不是已经存在或已经通过的测试。列出的承载文件已在仓库内，后续任务按 Spec 添加 pytest 可收集用例、注入网关/时钟/随机源/审计故障与隔离存储，不调用真实模型。`tests/test_ai_required.py:25` 当前只有 main 入口，其“无 AI”检查不能计入本次 pytest 用例数。

| 红线 / 拟用例 | 断言什么及失败样本 | 在哪层验 / 可观察证据 | 测试承载文件 |
|---|---|---|---|
| R1 `test_charter_effect_allowlist_and_caps` | 注入未知键、超额正负值、错误类型、NaN/Infinity、假布尔、未知 item/skill；获准键仅九键、值在 caps；纯 narrative 即使携带奖励也无效果；下游不能重新读取原效果 | 事中类型门禁 + 规则结算；检查 cleaned、拒绝码、状态前后快照与审计 | `tests/test_gate_facts.py`；目录 DSL 另覆盖 `tests/test_custom_art.py`、`tests/test_forge.py` |
| R2 `test_charter_fact_refs_locations_and_spawn` | 混合已知/未知引用、空/非法所在地、未知 spawn 地点、负数/超境界/超业力/超数量；生效引用合法、spawn 收敛或拒绝；叙事提到新地名不自动改地图或因果账 | 事前冻结许可集 + 事中 L1 校验 + 事实晋升点；检查真源集合及副作用计数 | `tests/test_gate_facts.py`、`tests/test_name_guard.py` |
| R3 `test_charter_rule_owns_outcomes_and_loot` | 固定概率/随机样本，注入相反胜负和虚假 loot；判定等于引擎结果；抖动在上限/边界外被钳制；冻结后改字不改结果；重试不重骰不重奖 | L2 规则裁决 + 事后掉落账；结果/概率/随机调用计数及奖励键 | `tests/test_events_ai.py`、`tests/test_heart_demon_combat.py`、`tests/test_combat_integrity.py` |
| R4 `test_charter_audit_before_commit_and_explicit_fallback` | 注入 admission 写失败、commit 记录故障、无 Key、超时、空响应、配额拒绝；提交前有持久化 admission；失败不结算或可证明恢复一次；本地与不可用来源明确、不伪称 AI | 入口 + 事中 admission + 事后事务/恢复；调用顺序、关联 ID、commit_count、来源字段、用户提示 | `tests/test_ai_platform.py`；无 Key 主路径扩展 `tests/test_ai_required.py` |
| R5 `test_charter_untrusted_text_and_intent_mapping` | 大小写/角色标签/混合语言/换行注入；未知意图但带奖励；合法 travel/fight/trade 但无规则授权；可信区无自由原文，非法映射零效果且有引导 | 事前输入与意图 + 规则前置；Prompt 捕获、映射、效果/收费/迁跃/交战计数 | `tests/test_chat_actions.py`、`tests/test_free_chat.py`、`tests/test_omen_scene.py` |
| R6 `test_charter_integrity_guards_and_atomic_settlement` | DEAD/寿元耗尽、MEDITATING/CAPTURED、冷却临界、余额 cost-1/cost、63/64 格、多产物、双请求竞争；不足/忙碌无半笔副作用，成功实际收支和容量正确 | 前置及提交点 + Repository 审计；守恒函数调用、存档快照、并发结果、六类不变式及旧/新行囊一致性 | `tests/test_character_integrity_flow.py`、`tests/test_character_integrity.py`；经济链路覆盖 `tests/test_market_integrity.py` |
| R7 `test_charter_reward_provenance_and_once_only` | AI 伪造来源、合法来源条件未达、文字额外奖励、重复 proposal、循环节点累计收益；只有规则批准源产生预算内收益且一次结算 | 事中规则授权 + 事后对账；源 ID/预算/奖励键、actual_delta、物品进出 UID | `tests/test_events_ai.py`、`tests/test_omen_scene.py`、`tests/test_treasure_integrity.py` |
| R8 `test_charter_all_scenes_receive_trusted_facts` | 对全部注册 scene 参数化；捕获 Prompt 确有 facts、规则、允许效果；缺包/伪包调用数为零；构建器 facts 参数与 kwargs 均测试；篡改快照/自由原文哨兵/过期版本不能进入提交 | 事前 + 提交点；注册表全量对比、Prompt 快照、网关与保存计数 | `tests/test_ai_platform.py`、`tests/test_gate_facts.py` |
| R9 `test_charter_single_entry_coverage_and_quota` | 静态扫描所有生产私有传输调用及路由别名；逐场景动态调用统一入口；包含 NPC /say 旁路、纯润色、未注册新发现路径；未知 scene 拒绝，限额时网关零调用 | 调用边界 + 配额；AST 清单、入口调用轨迹、拒绝审计、配额计数 | `tests/test_ai_platform.py`；会话链路覆盖 `tests/test_st_chat.py`、`tests/test_npc_chat.py` |
| R10 `test_charter_content_block_and_redacted_logging` | 五类版本化样本分别注入输入与模型输出，另测正常文本及检测故障；命中时不请求/展示/落账，记录类别与关联信息但不包含原句 | 事前/事中安全边界 + 所有日志写点；网关/commit 计数、响应与日志内容、策略类别覆盖 | `tests/test_gate_facts.py`、`tests/test_ai_platform.py` |

每条用例至少验证“拒绝/钳制结果 + 实际状态或外部副作用 + 可追溯记录”，不能只验证返回 JSON 形状。旧行为回归至少覆盖规则探险、交易、角色状态门禁、NPC 无 AI 路径与 L4 文案失败后的原规则结果；历史基线失败标记 `PRE-EXISTING`，不得为了宪章而改写通过阈值。上述缺口用例预计会暴露现状问题，不能先跳过再宣布红线通过。

## 7. 32 个注册场景的权限归属与真实链路差距

### 7.1 统计口径

注册清单取 `ai/play_prompts.py:666` 的 32 个键，注册过程在 `ai/registry.py:76`。按**生产调用**而非模块注释核查；同功能使用内联 Prompt 而非登记 builder 的，明确标为“内联同类”，不能把语义映射算作已经调用该注册 scene。

- **统一入口**：存在显式 scene 路由调用；“部分”表示同场景另一条生产路径仍直连私有传输。进入 invoke 但构建失败单独说明，不计为成功 AI 请求。
- **事实包**：网关 Prompt 真正序列化服务端 `FactPack` 才为“是”；简报、地点字符串、structured dict 不是自动等价的可信事实包。“丢弃”表示调用方构造/传入但 builder 没有注入。
- **门禁 G**：生产返回经过 `ProposalGate.admit`；**D**：专用世界指令校验；**局部**：字段截取、枚举、DSL 或数值钳制，不等于完整门禁；**否**：未调用统一提案门禁。G/D 也不意味着正文、权限、来源和落账审计全部合规。
- 每行末尾给出注册位置及生产链路证据；纯润色共享 `core/ai_flavor.py:59` 的直连传输，各行仍给具体 builder/调用位置。

### 7.2 场景差距表

| # | 注册 scene | 权限归属 | 统一入口 | 实际事实包注入 | 门禁 / 当前限制 | 逐行代码证据与具体缺口 |
|---|---|---|---|---|---|---|
| 01 | `combat` | L0/L1/L2/L4 | 是 | 是 | G；胜负仅枚举 | 注册 `ai/play_prompts.py:667`；入口 `ai/gateway.py:723`，facts 与 gate `ai/gateway.py:733`；`core/combat_fate.py:160` 依提案 kill 落账，最终判定权尚未闭环 |
| 02 | `tribulation` | L1/L2/L4 | 是 | 否（角色简报） | 局部概率钳制，无 G | 注册 `ai/play_prompts.py:668`；入口 `ai/gateway.py:445` 不传 facts；`ai/gateway.py:466` 钳概率后在 `ai/gateway.py:469` 仍采信 AI success |
| 03 | `world_event` | L0/L1/L4 | 是 | 是 | G + EventValidator | 注册 `ai/play_prompts.py:669`；事实 `ai/gateway.py:506`，入口 `ai/gateway.py:521`，门禁 `ai/gateway.py:536`；`core/events.py:232` 落效果，未证明奖励来源与完整事后账差 |
| 04 | `world_director` | L1/L2/L4（世界态势） | 是 | 否（服务端简报/structured） | D，不是 G | 注册 `ai/play_prompts.py:670`；`core/world_director.py:582` 提供局部结构事实，入口 `core/world_director.py:595`；`core/world_director.py:317` 等专用校验，需接可信世界事实和统一审计关联 |
| 05 | `world_arc_stage` | L1/L4（结果已定） | 是（构建失败） | 否（弧/模板字符串） | 否；只取叙事 | 注册 `ai/play_prompts.py:671`；入口 `core/world_arc.py:391`；`core/world_arc.py:389` 多传 participants 而 `ai/play_prompts.py:615` builder 无该参数，触发 `ai/router.py:108` 重试后构建失败，并在 `core/world_arc.py:398` 回模板 |
| 06 | `npc_chat_summary` | L1/L4（记忆摘要） | 否 | 否（原会话历史） | 否；字符串截取 | 注册 `ai/play_prompts.py:672`；builder `core/npc_chat.py:216`，直连 `core/npc_chat.py:222`；`core/npc_chat.py:238` 写记忆，摘要不能自动成为权威因果 |
| 07 | `scene_banter` | L1/L3/L4 | 否（内联同类） | 否（会话/人物简报） | 否；只取 line | 注册 `ai/play_prompts.py:673`；内联 Prompt `core/scene_banter.py:187`，直连 `core/scene_banter.py:201`；会话素材与事实、内容过滤未闭环 |
| 08 | `heart_demon_session` | L1/L4（选项文案） | 否 | 部分（主分支有，文字回退无） | 否；只截叙事/选项 | 注册 `ai/play_prompts.py:674`；facts `ai/gateway.py:557`，直连 `ai/gateway.py:577`，仅提取 `ai/gateway.py:581`；`ai/gateway.py:593` 回退另走无 facts 的 `_chat_text` |
| 09 | `heart_demon_judge` | L0/L1/L2/L3/L4 | 否 | 是 | G；tmod 局部钳制 | 注册 `ai/play_prompts.py:675`；facts `ai/gateway.py:621`，直连 `ai/gateway.py:642`，G `ai/gateway.py:644`；`ai/gateway.py:650` 后加 tmod，结局仍为 AI 枚举提案 |
| 10 | `free_action` | L0/L1/L3/L4 | 否 | 是 | G 两次，意图另校验 | 注册 `ai/play_prompts.py:676`；直连 `ai/gateway.py:805`，G `ai/gateway.py:807`；`ai/gateway.py:812` 恢复原 location，`core/free_action.py:148` 再过 G，`core/free_action.py:158` 仍未按意图消除越权效果 |
| 11 | `adventure` | L0/L1/L2/L4 | 否（内联同类） | 否（角色/目标简报） | 局部钳制，规则骰 | 注册 `ai/play_prompts.py:677`；规则骰 `core/adventure.py:283`，直连 `core/adventure.py:298`；`core/adventure.py:321` 保留规则 success，但独立效果字段需纳入统一类型、来源与入口 |
| 12 | `custom_art` | L0/L1/L3/L4（内容 DSL） | 否（内联同类） | 否（concept/作者文字） | 局部 DSL + clamp_art | 注册 `ai/play_prompts.py:678`；直连 `ai/gateway.py:830`，校验 `ai/gateway.py:845`、钳制 `ai/gateway.py:850`；理念文本直接拼接，无事实/统一配额/提案审计 |
| 13 | `revenge` | L0/L1/L4 | 否（内联同类） | 是 | G（event） | 注册 `ai/play_prompts.py:679`；记忆 facts `core/memory.py:242`，直连 `core/memory.py:245`，G `core/memory.py:272`；记忆信任与统一调用/降级仍缺 |
| 14 | `forge` | L0/L1/L3/L4（目录提案） | 否 | 否（hint/禁名样本） | 局部内容钳制/去重 | 注册 `ai/play_prompts.py:680`；builder `core/forge.py:149`，直连 `core/forge.py:162`，钳制 `core/forge.py:163`；`core/forge.py:176` 落生成目录，不等于获准角色奖励；悟方同类旁路见第 7.4 节 |
| 15 | `omen_open` | L1/L4 | 否 | 否（虽登记必包） | 否；纯润色截取 | 注册 `ai/play_prompts.py:681`；builder `core/ai_flavor.py:78`，调用 `core/ai_flavor.py:85` → `core/ai_flavor.py:59`；返回模板缺显式来源/安全校验 |
| 16 | `omen_next` | L1/L3/L4 | 否 | 否（虽登记必包） | 否；纯润色截取 | 注册 `ai/play_prompts.py:682`；builder `core/ai_flavor.py:93`，调用 `core/ai_flavor.py:100` → `core/ai_flavor.py:59`；选择/模板文字未形成事实许可集 |
| 17 | `omen_outcome` | L0/L1/L4（已结算描述） | 否 | 否（虽登记必包） | 否；纯润色截取 | 注册 `ai/play_prompts.py:683`；builder `core/ai_flavor.py:108`，调用 `core/ai_flavor.py:115` → `core/ai_flavor.py:59`；effect_summary 是字符串，正文可虚构额外收益 |
| 18 | `ring_accept` | L1/L4 | 否 | 否（宗门/任务字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:684`；builder `core/ai_flavor.py:125`，调用 `core/ai_flavor.py:131` → `core/ai_flavor.py:59`；具体规则任务应以 ID 引用 |
| 19 | `master_task` | L1/L4 | 否 | 否（师徒/任务字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:685`；builder `core/ai_flavor.py:139`，调用 `core/ai_flavor.py:145` → `core/ai_flavor.py:59`；无统一事实、内容、来源元数据 |
| 20 | `rumor_twist` | L1/L4（明确非权威传闻） | 否 | 否（原传闻文本） | 否；纯润色截取 | 注册 `ai/play_prompts.py:686`；builder `core/ai_flavor.py:154`，调用 `core/ai_flavor.py:158` → `core/ai_flavor.py:59`；`core/rumors.py:187` 使用结果，必须保留非权威真伪/来源 |
| 21 | `hunt_announce` | L1/L4（规则号令） | 否 | 否（虽登记必包） | 否；纯润色截取 | 注册 `ai/play_prompts.py:687`；builder `core/ai_flavor.py:169`，调用 `core/ai_flavor.py:175` → `core/ai_flavor.py:59`；`core/hunt.py:300` 用作号令，人物/地点应来自行动快照 |
| 22 | `graduation` | L1/L4（规则出师） | 否 | 否（师徒字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:688`；builder `core/ai_flavor.py:183`，调用 `core/ai_flavor.py:189` → `core/ai_flavor.py:59`；失败只回原文，非受控叙事审核 |
| 23 | `collusion` | L1/L4（规则交集） | 否（内联同类） | 否（虽登记必包） | 否；规则固定态度变化 | 注册 `ai/play_prompts.py:689`；内联直连 `core/collusion.py:179`，仅取文案 `core/collusion.py:189`；`core/collusion.py:202` 的固定规则变化不是 G 校验 |
| 24 | `npc_talk` | L1/L3/L4（另含关系提案） | 部分 | 丢弃（core 传入；web 无包） | 无 G；局部 attitude 钳制 | 注册 `ai/play_prompts.py:690`；core 构造 `core/npc_mind.py:341` 并路由 `core/npc_mind.py:347`，builder `ai/play_prompts.py:352` 不注入 facts；web `/say` 仍直连 `server/world.py:1931`；delta 仅局部钳制 `core/npc_mind.py:389` |
| 25 | `npc_agenda` | L1/L4（规则先落账） | 是 | 丢弃（已构造/传入） | 无 G；规则结果/局部正文检查 | 注册 `ai/play_prompts.py:691`；`core/npc_agenda.py:163` 先规则结算，`core/npc_agenda.py:194` 传 facts 调入口；`ai/play_prompts.py:390` builder 不注入；结果权威方向正确，但事实/正文/降级未完整 |
| 26 | `npc_proactive` | L1/L4（另含关系提案） | 是 | 否（角色卡/地点字符串） | 无 G；局部 delta 钳制 | 注册 `ai/play_prompts.py:692`；入口 `core/npc_proactive.py:177` 无 facts，`core/npc_proactive.py:197` 钳 delta；`core/npc_proactive.py:209` 规则函数调态度，仍需已登记关系许可类型及来源 |
| 27 | `trade_haggle` | L0/L1/L4（规则价格台词） | 否 | 否（报价/身份字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:693`；builder `core/ai_flavor.py:197`，调用 `core/ai_flavor.py:200` → `core/ai_flavor.py:59`；只能描写规则报价，不能自定成交与优惠 |
| 28 | `trade_face_offer` | L0/L1/L4（规则转移台词） | 否 | 否（双方财物字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:694`；builder `core/ai_flavor.py:207`，调用 `core/ai_flavor.py:210` → `core/ai_flavor.py:59`；`core/trade.py:442` 使用结果，缺转移事实锚点 |
| 29 | `auction_bid` | L0/L1/L4（规则出价公告） | 否 | 否（出价字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:695`；builder `core/ai_flavor.py:217`，调用 `core/ai_flavor.py:220` → `core/ai_flavor.py:59`；`core/trade.py:957` 公告不应改变领导者/金额 |
| 30 | `auction_settle` | L0/L1/L4（规则结算公告） | 否 | 否（成交字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:696`；builder `core/ai_flavor.py:227`，调用 `core/ai_flavor.py:230` → `core/ai_flavor.py:59`；`core/trade.py:1047` 文案不能额外发货或改价 |
| 31 | `market_guild` | L0/L1/L4（规则购销公告） | 否 | 否（商品/数量/金额字符串） | 否；纯润色截取 | 注册 `ai/play_prompts.py:697`；builder `core/ai_flavor.py:237`，调用 `core/ai_flavor.py:240` → `core/ai_flavor.py:59`；`core/market.py:114` 使用公告，非可信事实包 |
| 32 | `omen_script` | L0/L1/L3/L4（事件图提案） | 否 | 否（人物/地点简报） | 局部图结构/效果钳制 | 注册 `ai/play_prompts.py:698`；builder `core/omen_scene.py:641`，直连 `core/omen_scene.py:646`；`core/omen_scene.py:647` ingest、`core/omen_scene.py:616` 钳图效果；需补实体许可、累计奖励预算、入口和审计 |

### 7.3 可复核汇总（不是合规率）

- **32/32** 注册场景已列出，按 AST 读取注册 dict 核对，无遗漏/重复。
- **8/32** 存在显式统一入口路径：combat、tribulation、world_event、world_director、world_arc_stage、npc_talk、npc_agenda、npc_proactive。其中 npc_talk 有 web 旁路；world_arc_stage 因多余 participants 参数无法成功构建 Prompt。其余 **24** 的同功能路径直连或内联，不应叫“已接入中台”。
- **6 个场景主路径确有 FactPack 序列化**：combat、world_event、heart_demon_session、heart_demon_judge、free_action、revenge。其中心魔开场的文字 AI 回退没有包；npc_talk/npc_agenda 两场景只传未注入。此口径与旧盘点“只覆盖 3 场景”不同，不能照抄旧数字，也不能把这六个当作全分支可信合规。
- **11/32** 在注册规格中 requires_facts；**5** 场景主路径过 G（combat、world_event、heart_demon_judge、free_action、revenge），世界导演另有 D。不存在“其余纯叙事可以不验”的目标豁免。
- 没有任何一行因 G、对象 validator、局部 DSL、模板回退或当前测试通过被判定为“十条红线全合规”。

NPC 的 `attitude_delta`/主动搭话 delta 不是 L4 文风：若继续允许 AI 提议关系变化，必须在已登记的关系规则许可类型内结算、钳制和留审计；不能作为任意角色 effects 的第十键。它与世界指令、目录 DSL 一样，不得通过“其它字段”绕开场景权限。

### 7.4 注册表外/备用 AI 路径也在宪章约束内

32 是注册表数量，不是生产模型调用点的全集。下列路径是后续 R8/R9 扫描必须纳入的输入，不在上表中虚增注册 scene：

| 路径 | 权限域与漏点 | 代码证据 |
|---|---|---|
| 心魔文字生成/开场回退 | L1/L4；私有文本调用只传角色简报，无事实包/统一门禁 | `ai/gateway.py:389`、`ai/gateway.py:593` |
| 聊天动作意图分类与后果台词 | L1/L3/L4；原文直拼，动作枚举不能替代前置、事实与入口 | `core/chat_actions.py:58`、`core/chat_actions.py:61`、`core/chat_actions.py:129` |
| 奇遇自由文本动态选边 | L1/L3；匹配现有边方向正确，但原文直拼且私有调用 | `core/omen_scene.py:927`、`core/omen_scene.py:931` |
| 系统文案名称审查与听闻物化 | L1/L4；从 AI 文案再次提案名字，并经追索写新地点；须阻断无授权事实晋升 | `core/name_registry.py:339`、`core/name_registry.py:354`、`core/name_registry.py:185` |
| 藏图方向引导与藏图自由动作 | L1/L3/L4；两个独立私有调用，注册表不能证明其覆盖 | `core/treasure_system.py:246`、`core/treasure_system.py:731` |
| 悟方/配方提案 | L0/L1/L3/L4（内容 DSL）；虽导入 forge builder，实际另拼配方 Prompt，再局部 ingest | `server/world.py:1264`、`server/world.py:1268`、`server/world.py:1278` |
| 模型通道自检 | 诊断、零业务效果；当前私有模型调用仍需明确登记、最小事实与统一观测契约，不能被业务借用 | `ai/gateway.py:90` |

听闻追索若需保留规则驱动的世界拓展，须另立经评审的世界拓展权限契约，区分“非权威新名字”与“规则批准的新地点”；不能事后把 AI 名字塞进 WORLD_LOCATIONS 便声称原请求满足已知地点约束。本设计识别冲突，不在文档任务中删除旧玩法、迁移地图或静默新增例外。

## 8. 明确不约束什么 / 不做什么

- 不约束 L4 的文风、措辞、语气、景物意象、幽默与戏剧张力；不要求统一模板腔，不把“雾如千年”之类修辞当寿元奖励。事实/数值/既成结果约束跨层生效，不是审美限制。
- 不要求规则功能接 AI。迁跃、闭关结算、寿元推进、经济转移、掉落掷骰与轮回继续由规则引擎决定；AI 可以描述它们，不能夺走执行权。
- 不禁止服务端按已评审规则演进目录或世界，也不禁止 spawn 申请；禁止的是 AI 输出自行成为新真源或权限。本文不直接批准新的地点生成/奖励机制。
- 不重开 PROX-1 构想定稿；不定义发行、计费、双币、付费或供应商商业规则；不绑定某个模型、Prompt 文风或外部安全厂商。
- 不改任何业务、测试、存档与 UI；不做数据迁移、删除、旧存档修复、网络压测、真实模型验收或性能数字承诺。
- 不声称有限测试穷尽自然语言虚构，也不以 L4 自由取消内容红线、事实来源与可追溯结算。

## 9. 评审、实施衔接与验收口径

### 9.1 本设计交付的可观察证据

| PROX-7 验收条目 | 文档证据 / 核查方法 |
|---|---|
| L0–L4 各层能做/不能做/如何发现 | 第 3 节五层表与第 3.1–3.3 节边界解释 |
| 三道闸门的时机/职责/落点/缺失项 | 第 4 节；明确区分 admission 与 commit |
| 十条可转为执行断言的红线 | 第 5 节 R1–R10 + 第 6 节输入、失败结果、层级、承载文件 |
| 32 行场景差距表逐行代码证据 | 第 7.2 节；注册 dict 全量比对、生产调用 AST 及逐条源代码阅读 |
| 不约束什么 / 明确不做 | 第 8 节；L4 自由与规则权威同时保留 |
| 无密钥、令牌、环境变量值 | 文档不采集环境值；交付前进行敏感值形态扫描与人工审校 |

基线与交付后复跑、代码引用检查、覆盖清单及交付边界记在 `docs/ai-boundary-charter-report.md`。既有离线测试只是证明相关基线仍可运行，不代表后续缺口测试已经落地或通过；独立全员评审、实现回归与 QA 准出尚未发生。

### 9.2 负责人定稿后才能派发的实施方向

1. 入口与事实：修复构建契约、facts 丢弃、私有调用及降级元数据；建立注册清单与实际调用覆盖断言。
2. 权威与结算：按提案类型关闭直接采信胜负、无来源效果、无容量/支付前置以及清洗后原字段复活；补冻结点与并发幂等证据。
3. 审计、内容与事实晋升：落账关联、审计失败恢复、五类内容检测与脱敏日志、非权威记忆/听闻隔离和正文结果核查。

以上只给依赖顺序，不创建或承接实现任务。后续每项使用 compose-next：已定稿真正需求 → 隔离工作区与 Spec → 失败测试 → 实现 → 实测验证 → 独立 review → 全栈 QA 独立回归。现有 PROX-6 D-1~D-8 P0 修复可并行，本设计不增加互等依赖；定稿后的新 AI 设计须前置引用本宪章。

定稿重点由负责人组织确认：L2 的规则冻结点与框内抖动提案；审计失败时零新增结算/可恢复 commit 关联；听闻追索的规则拓展授权；五类内容的版本化样本边界。阶段二/三输出后再正式分配实施，QA 出具验收结论、产品负责人决定关单。
