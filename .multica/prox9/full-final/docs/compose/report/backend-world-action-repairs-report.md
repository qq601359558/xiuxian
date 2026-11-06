# PROX-8 后端接线修复交付报告

- Date: 2026-10-29
- Status: 初轮 QA 结论经负责人确认有效；F2/F3 增量实现、自测与独立代码评审完成，等待独立增量 QA，不自行宣布最终验收或关单。
- Branch: `feat/character-integrity-and-audit-rules`
- Initial Base SHA: `e6a4d5a071df69c387dfd8c2052605f6819d47f7`
- Delivery form: 负责人本轮授权六文件定向提交并推送现有分支；本报告与其余五文件同一提交交付，实际 SHA、推送及工作区清洁确认见最终 issue 评论和 Git 回执，不将自引用 SHA 写进其所属提交。
- Spec: `docs/compose/spec/backend-world-action-repairs.md`

## 修复范围与行为契约

| 缺陷 | 实现 | 可观察自测证据 |
| --- | --- | --- |
| D-1 自由言行崩溃 | `/做`、`/do`、`/act`、`/言行` 合并至 `FreeActionEngine.resolve`；保留非法造物拒绝、同场事实、宝图分流及角色/NPC 保存 | `tests/test_world_action_regressions.py:78`；同文件含拒绝、NPC 保存和宝图分流用例 |
| D-2 可见探险名不匹配 | 服务端接受“野外山原”，保留旧别名、内部目标和无参告示板 | `tests/test_world_action_regressions.py:222`；同文件含无参和未知目标用例 |
| D-6 击杀不兑付 | 仅确认击杀后调用既有悬赏结算并保存告示及猎人；附加领赏文本 | `tests/test_world_action_regressions.py:299`；同文件含未击杀、过期及重复请求用例 |
| D-8 挖宝收益丢失 | 透传引擎 `stone_gain`，无收益时返回零，不重算奖励或扣费净额 | `tests/test_world_action_regressions.py:244`；同文件含无奖励用例 |
| HTTP 异常边界 | `/action` 未预期异常返回结构化 HTTP 500 / `ACTION_FAILED`；不暴露内部错误；后续请求可继续成功 | `tests/test_world_action_regressions.py:391`；同文件含空白、拒绝隐私和状态兼容用例 |
| F2 领赏后状态滞后 | `_fight` 成功响应在所有结算和保存之后补最新 `status`，不改状态 DTO/失败响应 | `tests/test_world_action_regressions.py:315` |
| F3 破阵叙事误拒 | 存活/空闲门禁仍在最前，宝图目标节点破阵优先于普通造物门禁；奖励仍由真实引擎决定 | `tests/test_world_action_regressions.py:168`；同文件覆盖名物叙事、无宝图及非目标节点门禁 |

源码影响面仅为 `core/adventure.py`、`server/world.py`、`server/app.py`，另新增回归用例和交付文档。沿用角色存活/忙碌门禁、Repository 保存、锁内串行处理及既有悬赏规则，不增加依赖或存档迁移。

未修改 `core/models.py`、`core/character_integrity.py`、经济守恒、鉴权、静态托管、前端展示或其他指令。已有 `AGENTS.md`、`web/` 与 AI 边界文档改动保持原样，不纳入交付包。

## 初轮自测口径与输出

环境为 Windows、Python 3.11.0、pytest 9.1.1；使用项目 `.venv` 解释器，`ALLOW_LOCAL_AI=1`、`AI_REQUIRED=0`、`USE_CCSWITCH=0`，LLM Key 为空，不调用外部 AI。

全量及相关测试在不含 `.env`、`.git`、真实 `data/` 的源码副本中运行。新回归文件在初始化 World 前绑定临时数据库和日志，禁止后台推进；6 条 HTTP 场景使用真实的临时 HTTP 服务，测试结束同步关闭。不可直接在真实存档目录运行现有全量测试。

| 阶段 | 命令/口径 | 实际输出 | 交付包内证据 |
| --- | --- | --- | --- |
| 改动前基线 | 隔离副本内 `python -m pytest tests -q --tb=short` | 446 passed / 2 failed，132.05s | `evidence/baseline-pytest.txt` |
| 缺陷先红 | 初版 23 条 World/HTTP 回归 | 16 failed / 7 passed，19.31s | `evidence/red-world-pytest.txt` |
| 隐私先红 | 自由首词、未知斜杠首词及拒绝回显 | 捕获原 P2 的日志泄露 | `evidence/privacy-red-pytest.txt`、`evidence/privacy-gate-red-pytest.txt` |
| 交付前重验 | `python -m pytest tests/test_world_action_regressions.py -q --tb=short` | 26 passed，16.42s | `evidence/handoff-world-pytest.txt`、`evidence/handoff-world-results.xml` |
| 相关回归 | free_action/adventure/bounty/integrity/treasure/combat 与新用例 | 71 passed，15.87s | `evidence/related-delivery-pytest.txt`、`evidence/related-delivery-results.xml` |
| 交付版全量 | 新鲜隔离副本内 `python -m pytest tests -q --tb=short` | 472 passed / 2 failed，135.16s | `evidence/delivery-full-pytest.txt`、`evidence/delivery-results.xml` |

26 条新增用例包含 20 条 World 入口场景及 6 条真实 HTTP 场景。原 448 条加新增 26 条合计 474 条，因此成功数为 472，不应仍固定为 446。两条剩余失败性质与基线相同，均标记 PRE-EXISTING：

- `tests/test_cli_parity.py::test_cli_parity_commands`：`/寄售` 无参断言与已有告示板行为漂移。
- `tests/test_workbench_api.py::test_login_then_look_here`：测试依赖 `127.0.0.1:8765` 常驻服务，未启动时连接拒绝。

首次全量曾暴露新测试 mock 与旧测试 `reload(ai.gateway)` 的类绑定冲突。仅把 mock 改为领域使用方的绑定，不改旧测试或业务引擎；强制重载压力回归为 23 passed，交付版全量新增用例全部通过。

`compileall` 与范围内 `git diff --check` 返回 0。初轮交付版源码 SHA256 与其全量测试版本一致；复审后重验仍未改变真实数据库哈希。初轮包的 `evidence/source-manifest.json` 记录当时的源码/测试哈希，`evidence/live-db-before.json` 仅含存档哈希，不含存档内容。

## 初轮独立代码评审

独立只读 Codex 初审发现一个 P2：将用户首词当作日志命令名，会泄露无前缀言行或未知斜杠输入。修复为可信指令目录的精确白名单与固定 `FREE_TEXT` / `UNKNOWN_COMMAND` 标记；拒绝诊断使用固定 `ACTION_REJECTED`，客户端原 HTTP 200 拒绝正文不变。异常日志仅保留类型和堆栈帧元数据，不记录消息、源码行、令牌或原始输入。

2026-10-29 初轮独立复审实际输出为 **Decision: PASS**，无阻塞发现；该时点 World/adventure 与其初审哈希一致。初轮评审证据为 `evidence/independent-review-initial.md` 和 `evidence/independent-review.md`。本轮 World 的 F2/F3 变化另经独立增量评审，不以旧评审代替。

## F2/F3 增量修复与验证

依据负责人评论 `01a18602-6495-7de2-a9f5-9f5bc08c040c`，F2 为 D-6 功能缺口、F3 为本次引入的行为回归，均在 PROX-8 内修复；F1 `攻伐 +undefined` 归 PROX-11，未触碰前端。

业务增量仅两处：把既有造物拒绝块移到宝图目标节点分流之后；在战斗/赏金保存完成后返回当前角色 `status`。没有改 `TreasureEngine`、掉落表、经济、72 小时庇护或状态 DTO。

新增白名单探针执行真实 `World.handle` 和 `TreasureEngine`，控制 AI 裁定、词缀随机与无关奇遇；普通叙事与注入“仙品毁天剑、一千万灵石”的叙事在同一成功/失败裁定下，完整非 UID 道具载荷、灵石、修为和道心增量完全一致。AI 的伪造奖励/数值字段不落库。

| 增量阶段 | 实际输出 | 本轮证据包内位置 |
| --- | --- | --- |
| 修复前基线 | 26 passed，13.74s | `evidence/incremental-baseline-pytest.txt` |
| F2/F3 先红 | 4 failed / 27 passed，16.74s | `evidence/incremental-red-pytest.txt`、`evidence/incremental-red-results.xml` |
| 修复后回归 | 31 passed，16.04s | `evidence/incremental-green-pytest.txt`、`evidence/incremental-green-results.xml` |
| 相关回归 | 76 passed，21.56s | `evidence/incremental-related-pytest.txt`、`evidence/incremental-related-results.xml` |
| 新鲜隔离全量 | 477 passed / 2 PRE-EXISTING，117.36s | `evidence/incremental-full-pytest.txt`、`evidence/incremental-full-results.xml` |
| 独立增量代码评审 | Decision: PASS，无阻塞发现 | `evidence/incremental-independent-review.md` |

新增文件现有 31 条用例（25 World / 6 HTTP），原 448 条加 31 条合计 479 条；无跳过、无新增全量失败，成功数 `477 = 446 + 31`。全量仍仅有 `/寄售` 断言漂移和未启动 8765 服务两条既有失败。

测试仍使用前述 Windows / Python / pytest 与隔离库口径，不用真实存档或外部 AI。交付源码与测试副本哈希一致；真实数据库及无关工作区文件前后哈希未变。独立评审未跑测试/浏览器，不是独立增量 QA 准出。

## QA 交接与未完成项

- 初轮服务端 QA 评论 `01a185fc-9043-7bc3-82be-9681a4c3c66a` 已提供独立回归和 Chromium 浏览器三步证据，负责人确认结论有效；本轮不重复初轮完整验收，也不据此跳过 F2/F3 增量复验。
- 增量 QA：复跑相关回归，核对全量成功数不少于 472；验证 F3 目标节点名物叙事优先、无宝图/非目标节点仍拒绝造物、成功/失败白名单探针不注入奖励。
- F2 浏览器证据：隔离库成熟猎手完成有赏击杀，`/斗法` 响应 `status.stones`、顶栏灵石和数据库立即一致，不再发送另一条状态指令掩盖刷新缺口。
- 72 小时庇护保留：可击杀验收只用隔离库内入世时间前推 4–5 天的受控角色或既有成熟角色，真正新号仍验证被保护；不得改真实存档。此统一口径已写进 Spec 的后续验收模板。
- 由名册已确认的服务端测试工程师独立增量准出，现任团队产品负责人决策最终验收/关单；实现者仅交付 `in_review`，不自行置 `done`，不再向不存在的历史 uid 派发。

## 交付包与回退边界

初轮 `prox8-backend-world-action-repairs.zip` 作为历史证据保留。本轮代码以现有分支的六文件定向提交交付，`prox8-f2-f3-incremental-evidence.zip` 提供增量红绿/相关/全量输出、JUnit、源码哈希、增量 diff、独立评审与 Git 回执；不含 `.env`、密钥、Git 配置、数据库、完整测试副本或原始评审运行日志。

没有存档迁移。需要回退时仅撤销本包的三个源码改动及新增回归/文档，保留其他并行任务的改动；不要重置整个工作区或覆盖真实存档。
