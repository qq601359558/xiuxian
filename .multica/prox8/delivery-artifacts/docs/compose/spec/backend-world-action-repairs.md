# PROX-8：在线指令接线修复

- Status: implemented-reviewed-awaiting-qa
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

- 按任务书明确指定的单一 in-place 目录实施，不建或切换分支，不改 Git 索引。
- 保留已有 `AGENTS.md`、`web/` 改动和 AI 边界文档，不覆盖、不纳入本次 diff。
- 已调用 `multica repo checkout`，守护进程返回 `repo checkout workdir is not owned by the active task`。不使用 `--fresh` 或绕过限制；以已有代码及明确指定的 in-place 路径实施。
- 当前可用技能无 `compose-next`，依照项目明示契约执行 Spec → 实现 → 验证 → 独立评审 → Report，不安装不明技能或修改全局配置。
- 原测试直接写默认数据库。全量验证使用复制本次源码的隔离快照，执行同一 `pytest tests`；不复制真实 `data/` 或 `.env`。新 World 用例使用临时数据库，关闭定时推进和外部 AI。

## Design / 行为契约

### D-1 自由言行

- `/做`、`/do`、`/act`、`/言行` 使用一个权威分支，接受不同空白分隔。
- 保留造物门禁和宝图当前位置的自由破局分流，不修改 AI 白名单或门禁规则。
- 正常路径调用 `FreeActionEngine.resolve(..., others=...)`，按 `ok/error/text/intent/outcome/spawned` 映射结果。
- 仅成功结果保存角色和生成的 NPC，不丢失引擎文本。沿用存活、忙碌前置门禁，保存统一通过 `CharacterRepository.save`。

### D-2 探险名称

- 接受网页默认名称“野外山原”，保留无参、`野外`、`山野`、`wild`，归一至原野外目标。
- 内部 ID、收益、地点及秘境解析规则不变；未知目标继续拒绝。
- 服务端无参本来返回探险告示板，保持该行为；网页无参转换为“野外山原”，由新增别名恢复。

### D-6 悬赏兑付

- 在线 `/斗法` 只有 `target_died` 成立才查询目标告示并调用既有 `BountyEngine.settle_on_kill`。
- 保存更新告示与获赏角色，将现有领赏消息附加到战斗文本。
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
- [ ] T9（QA 准出）：服务端测试工程师独立回归，出具网页新号“探险 → 挖宝 → 悬赏”的实际浏览器证据及准出结论。此项从原 T8 拆出以区分实现交付与独立验收，验收范围不变。

## Out of Scope

- 不修改 `core/models.py`、`core/character_integrity.py` 或经济守恒（PROX-10）。
- 不改鉴权、静态托管、`/join`（PROX-9），不改前端展示或已有 `web/` 改动（PROX-11）。
- 不修未启动服务的 API 测试与 `/寄售` 断言漂移，不把既有失败伪装成本次修复。
- 不删除、覆盖、迁移真实存档；不提交或推送；不自行宣称 QA 验收通过或关闭 issue。

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
- QA/browser: pending。悬赏真实击杀有双方 72 小时新手庇护；测试仅在临时数据库中将角色入世时间置于四天前。浏览器验收应记录测试时钟/隔离角色预置，不得为即时通关删除庇护规则或修改真实存档。
