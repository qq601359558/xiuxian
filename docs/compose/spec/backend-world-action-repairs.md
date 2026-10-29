# PROX-8：在线指令接线修复

- Status: incremental-implemented-reviewed-awaiting-qa
- Date: 2026-10-28
- Updated: 2026-10-29
- Branch: `feat/character-integrity-and-audit-rules`
- Base SHA: `e6a4d5a071df69c387dfd8c2052605f6819d47f7`

## Problem / 真正需求

在线入口存在四处已复现的接线断裂：自由言行调用不存在的方法、玩家可见探险名称无法解析、击杀未接通悬赏兑付、挖宝收益字段被响应丢弃。恢复既有引擎与网页端的行为契约，不重新设计游戏规则。

父任务 PROX-6 在用户同意后正式派发 PROX-8，明确“无前置依赖，可立即开工”，四项为已确定故障而非新产品设计。本次据此不再发起产品决策确认；实现范围只以任务书与以下验收契约为依据。

## Requirement Evaluation / 五步细化

1. **解构本质**：保证玩家通过 `World.handle` 和 `POST /action` 得到合法、可观察且已入库的结果；直接调引擎的单测不能替代在线入口回归。
2. **可行性评估**：Python 标准库 HTTP、SQLite 和已有领域引擎足以修复。沿用 World 锁内串行处理和 Repository 保存，不增加依赖、表结构或后台任务。悬赏只在确认击杀后查询目标告示。
3. **不足与盲区**：保留造物拒绝、同场事实、NPC 落盘、宝图自由破阵、空白分隔与命令别名。拒绝不能当成功。探险别名不得改变目标收益。过期、未击杀和重复攻击不得额外兑付。无收益挖宝给零，异常不泄露令牌、原始言行和内部错误。
4. **举一反三**：在线与 CLI 共用领域引擎，但各入口承担持久化和响应映射。本次建立可复用的 World 层回归写法，保留既有别名与存档语义，不顺手修改其他指令。
5. **完善方案**：合并重复自由言行路由、接通 `resolve` 返回契约、在现有击杀点调用悬赏结算并保存、透传挖宝收益、增加有限的 HTTP 异常边界；先红后绿，全量回归和独立评审后交 QA 准出。

## Workspace / 流程覆盖项

- 按任务书明确指定的单一 in-place 目录实施，不建或切换分支。初轮未改 Git 索引；2026-10-29 负责人明确授权本轮只提交并推送下列六个 PROX-8 文件，保留其他工作区改动。
- 保留已有 `AGENTS.md`、`web/` 改动和 AI 边界文档，不覆盖、不纳入本次 diff。
- 已调用 `multica repo checkout`，守护进程返回 `repo checkout workdir is not owned by the active task`。不使用 `--fresh` 或绕过限制；以已有代码及明确指定的 in-place 路径实施。
- 当前可用技能无 `compose-next`，依照项目明示契约执行 Spec → 实现 → 验证 → 独立评审 → Report，不安装不明技能或修改全局配置。
- 原测试直接写默认数据库。全量验证使用复制本次源码的隔离快照，执行同一 `pytest tests`；不复制真实 `data/` 或 `.env`。新 World 用例使用临时数据库，关闭定时推进和外部 AI。

## Design / 行为契约

### D-1 自由言行

- `/做`、`/do`、`/act`、`/言行` 使用一个权威分支，接受不同空白分隔。
- 存活/空闲门禁在所有自由言行之前。有宝图且身在目标节点时优先进入自由破阵，破阵叙事提及名物不视为凭空造物；其余自由言行仍执行原造物门禁，不修改其正则或 AI 白名单。
- 自由破阵只由既有 `TreasureEngine` 决定白名单产出；文本或 AI 额外奖励字段不得注入物品、品质、数量或灵石。相同受控裁定下对比普通与注入叙事的实际落库奖励。
- 正常路径调用 `FreeActionEngine.resolve(..., others=...)`，按 `ok/error/text/intent/outcome/spawned` 映射结果。
- 仅成功结果保存角色和生成的 NPC，不丢失引擎文本。沿用存活、忙碌前置门禁，保存统一通过 `CharacterRepository.save`。

### D-2 探险名称

- 接受网页默认名称“野外山原”，保留无参、`野外`、`山野`、`wild`，归一至原野外目标。
- 内部 ID、收益、地点及秘境解析规则不变；未知目标继续拒绝。
- 服务端无参本来返回探险告示板，保持该行为；网页无参转换为“野外山原”，由新增别名恢复。

### D-6 悬赏兑付

- 在线 `/斗法` 只有 `target_died` 成立才查询目标告示并调用既有 `BountyEngine.settle_on_kill`。
- 保存更新告示与获赏角色，将现有领赏消息附加到战斗文本。
- `_fight` 成功响应在结算与保存之后返回 `status: self._status_dict(c)`，使顶栏灵石与最新存档一致；不改状态 DTO 或失败响应。
- 无悬赏、未击杀、已完成、过期或重复攻击不得额外兑付；不扩展现有“谁杀谁领”等规则。

### D-8 挖宝收益

- 响应传递引擎的 `stone_gain`，没有该收益时返回 `0`，不重算或虚构奖励。
- 原装备、丹药、状态、方向及奇遇响应保持兼容。

### `/action` 异常边界

- 未预期处理异常返回 HTTP 500、`ok: false`、稳定错误码和通用中文提示。
- 记录 `ERROR` 事件、命令动词、异常类型和诊断堆栈，不记录 token 或原始输入，不回传内部错误内容。
- API 诊断日志只记录统一指令目录中的名称；自由文本和未登记斜杠命令分别使用固定 `FREE_TEXT`、`UNKNOWN_COMMAND` 标记，不能把用户首词当动词记录。
- API 拒绝日志使用固定 `ACTION_REJECTED`，避免人类错误文案回显输入；客户端原 HTTP 200 拒绝正文保持不变。
- 既有输入错误仍为 HTTP 400，World 业务拒绝继续为 HTTP 200；后续请求可继续处理。

## Tasks / 可独立验收

- [x] T1：至少五条 World 层回归，四项缺陷各自先红；HTTP 异常边界另有回归证据。
- [x] T2：自由言行正常、非法造物拒绝、别名、引擎拒绝、NPC 保存和宝图分流可观察。
- [x] T3：可见目标、旧别名及无参告示板正常，未知目标拒绝。
- [x] T4：挂赏 → 接令 → 击杀 → 兑付全程走 `World.handle`；数据库赏金及告示状态一致，重复请求不重复领奖。
- [x] T5：奖励路径 `/挖宝 1` 的 `stone_gain` 与角色真实灵石增量一致，无奖励返回零；该字段沿用引擎奖励口径，不重算其他路径的扣费净额。
- [x] T6：真实 HTTP 请求的异常得到结构化 500 和日志，随后正常请求继续成功。
- [x] T7：记录基线、针对性测试和全量真实输出；原 448 条中两条失败性质不变。新增 26 条全绿后为 `472 passed / 2 failed`，不能仍固定 446。
- [x] T8：独立 diff 评审 PASS；更新 Report 并提供交 QA 所需的源码、测试证据及隔离运行口径。
- [x] T9（初轮 QA）：服务端测试工程师已独立回归并给出浏览器证据；负责人确认初轮 QA 结论有效、成熟受控角色的三步验收已满足，但 F2/F3 与提交规整完成前不关单。
- [x] T10（F2）：World 层先红后绿证明击杀兑付响应 `status.stones` 等于实际落库灵石，顶栏可即时刷新；实际浏览器刷新由 T15 独立 QA 复验。
- [x] T11（F3 顺序）：提及名物的破阵叙事在宝图目标节点可正常破阵；无宝图或非目标节点仍拒绝凭空造物。
- [x] T12（F3 白名单）：真实 `TreasureEngine` 在受控成功/失败裁定下，普通与注入叙事的奖励快照一致，额外奖励字段不能改变掉落。
- [x] T13：相关回归 76 passed、全量 477 passed / 2 PRE-EXISTING，独立增量代码评审 PASS，真实存档哈希不变。
- [x] T14（定向交付）：提交范围限定为 `core/adventure.py`、`server/app.py`、`server/world.py`、`tests/test_world_action_regressions.py`、本 Spec 及对应 Report；实际 commit SHA、推送及六文件清洁检查结果由最终交付评论和 Git 回执记录，避免文档自引用其所属 SHA。
- [ ] T15（增量 QA 准出）：独立 QA 补 F2 顶栏刷新浏览器证据、复验 F3 门禁顺序及白名单探针，负责人决定最终验收与关单。

## 2026-10-29 增量需求细化 / 产品裁定

依据负责人评论 `01a18602-6495-7de2-a9f5-9f5bc08c040c`，F2 为本次 D-6 功能缺口、F3 为本次引入的行为回归，均为阻塞项，已正式派发具体修法；无需重复产品方案确认。

1. **本质**：恢复响应与存档一致性，以及宝图场景原有的自由叙事能力，不重设计战斗、悬赏或造物规则。
2. **可行性**：复用现有 `_status_dict`；仅移动 World 分流后的造物门禁。无新依赖、表结构、额外结算或经济规则变更。
3. **盲区**：状态快照必须在领赏保存后；存活/空闲校验不得随门禁后移；携宝图但不在目标节点仍受造物限制。自由文本和 AI 返回字段只能影响受控裁定/叙事，不可成为任意奖励后门。
4. **举一反三**：成功指令响应应反映当前存档；场景特定叙事与普通造物意图区分职责。新增探针覆盖真实入口、真实奖励引擎和最终存档，而不是 mock 奖励后自证。
5. **完善路径**：先补失败回归，再执行上述两处最小修复；相关/全量回归、独立增量评审、六文件定向提交推送、交独立 QA 增量复验。F1 前端 `攻伐 +undefined` 仍归 PROX-11，不纳入本轮。

增量基线：实际目录、临时库执行 `pytest tests/test_world_action_regressions.py` → **26 passed**, 13.74s；真实存档哈希与初轮一致。

## 庇护相关验收模板 / 负责人统一口径

- 全部验收使用隔离库与受控角色，禁止改真实 `data/tiandao.db`，记录真实库前后哈希。
- 可击杀路径：隔离库新建角色，将入世时间前推 4–5 天，或使用已有成熟角色；保留 72 小时规则。
- 保护路径：真正新号互斗应被 72 小时庇护阻断，单独验证保护仍生效。
- 浏览器证据需记录隔离服务、角色/时钟前置条件、请求响应、顶栏与数据库一致性。此模板适用于后续庇护/入世时间相关验收，不再以关闭保护作为前置条件。

## Out of Scope

- 不修改 `core/models.py`、`core/character_integrity.py` 或经济守恒（PROX-10）。
- 不改鉴权、静态托管、`/join`（PROX-9），不改前端展示或已有 `web/` 改动（PROX-11）。
- 不修未启动服务的 API 测试与 `/寄售` 断言漂移，不把既有失败伪装成本次修复。
- 不删除、覆盖、迁移真实存档；除本轮授权的六文件定向提交推送外不改 Git 工作区/索引归属；不自行宣称增量 QA 验收通过或关闭 issue。

## Verification

- Baseline: isolated source snapshot, `.venv/Scripts/python.exe -m pytest tests -q --tb=short` → **446 passed / 2 failed**, 132.05s.
- PRE-EXISTING: `test_cli_parity_commands` 的 `/寄售` 无参断言漂移；`test_login_then_look_here` 的 `127.0.0.1:8765` 连接拒绝。
- Test environment: Windows, Python 3.11.0, pytest 9.1.1; `ALLOW_LOCAL_AI=1`, `AI_REQUIRED=0`, `USE_CCSWITCH=0`, 空 LLM Key，无外部 AI 调用。
- Red: `tests/test_world_action_regressions.py` → **16 failed / 7 passed**, 19.31s；四个缺陷和 HTTP 断连接均被捕获。
- New regressions: 初版 23 条通过；补齐日志隐私场景后，实际项目目录执行同一文件 → **26 passed**, 14.04s；其中 20 条 World 入口场景、6 条真实 HTTP 场景。
- Handoff recheck: 独立复审后在实际项目目录重新执行新增回归 → **26 passed**, 16.42s；临时 HTTP 服务已关闭，真实数据库哈希仍与基线一致。
- Related regressions: free_action / adventure / bounty / integrity / treasure / combat 及交付版新增用例 → **71 passed**, 15.87s。
- Isolation diagnosis: 首次全量的三条新增失败来自旧测试收集阶段 `reload(ai.gateway)`，生产模块保留旧类绑定，mock 最新类没有生效。只把新测试 mock 改为使用方绑定，不修改旧测试或领域引擎。
- Reload stress: 故意先重载 AI 模块再执行新增用例 → **23 passed**, 8.18s。
- Final full regression: 交付版新鲜隔离快照执行 `pytest tests` → **472 passed / 2 failed**, 135.16s；失败仍仅为 `/寄售` 断言漂移和未启动服务的连接拒绝。
- Syntax / whitespace: `compileall` 与范围内 `git diff --check` 返回 0；源码快照 SHA256 与实际工作区一致，真实数据库哈希未变。
- Independent code review: 初审发现 P2，自由文本/未知命令首词会进入日志。新增失败测试确认两种首词泄露及拒绝文案回显；白名单与固定标记修复后全部回归通过。2026-10-29 独立只读复审给出 **Decision: PASS**，无阻塞发现；World/adventure 与初审版本哈希一致。代码评审不等于 QA 验收。
- Report: `docs/compose/report/backend-world-action-repairs-report.md`。交付包只包含本任务源码、规格、报告及测试/评审证据，不包含真实存档、环境配置或原始评审运行日志。
- QA/browser: 初轮独立 QA 评论 `01a185fc-9043-7bc3-82be-9681a4c3c66a` 提供完整浏览器证据与独立回归。负责人确认 72 小时庇护保留，成熟受控角色三步验收已满足；本轮 F2/F3 增量 QA 仍 pending。
- Incremental red: F2/F3 新回归在修复前为 **4 failed / 27 passed**, 16.74s；缺失 `status` 与三条破阵门禁断言准确变红。
- Incremental green: 修复后新增回归文件 **31 passed**, 16.04s；25 条 World 场景、6 条真实 HTTP 场景，普通造物门禁额外覆盖携宝图但不在目标节点。
- Incremental related: 同一相关范围 **76 passed**, 21.56s。
- Incremental full: 新鲜隔离副本执行 `pytest tests` → **477 passed / 2 failed**, 117.36s；合计 479 条、无跳过，两条既有失败性质不变。
- Incremental review: 独立只读评审实际输出 **Decision: PASS**，无阻塞发现；不替代 F2 浏览器证据或独立增量 QA。源码与测试副本哈希一致，真实数据库及其他工作区文件哈希未变。
