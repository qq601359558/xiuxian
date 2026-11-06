# PROX-8 后端接线修复交付报告

- Date: 2026-10-29
- Status: 实现、自测与独立代码评审已完成；等待服务端测试工程师独立回归及浏览器准出，不构成“已验收”。
- Branch: `feat/character-integrity-and-audit-rules`
- Base/HEAD SHA: `e6a4d5a071df69c387dfd8c2052605f6819d47f7`
- Delivery form: 该 SHA 上的未提交工作区改动；未提交、推送、切分支或修改 Git 索引。
- Spec: `docs/compose/spec/backend-world-action-repairs.md`

## 修复范围与行为契约

| 缺陷 | 实现 | 可观察自测证据 |
| --- | --- | --- |
| D-1 自由言行崩溃 | `/做`、`/do`、`/act`、`/言行` 合并至 `FreeActionEngine.resolve`；保留非法造物拒绝、同场事实、宝图分流及角色/NPC 保存 | `tests/test_world_action_regressions.py:78`；同文件含拒绝、NPC 保存和宝图分流用例 |
| D-2 可见探险名不匹配 | 服务端接受“野外山原”，保留旧别名、内部目标和无参告示板 | `tests/test_world_action_regressions.py:147`；同文件含无参和未知目标用例 |
| D-6 击杀不兑付 | 仅确认击杀后调用既有悬赏结算并保存告示及猎人；附加领赏文本 | `tests/test_world_action_regressions.py:224`；同文件含未击杀、过期及重复请求用例 |
| D-8 挖宝收益丢失 | 透传引擎 `stone_gain`，无收益时返回零，不重算奖励或扣费净额 | `tests/test_world_action_regressions.py:169`；同文件含无奖励用例 |
| HTTP 异常边界 | `/action` 未预期异常返回结构化 HTTP 500 / `ACTION_FAILED`；不暴露内部错误；后续请求可继续成功 | `tests/test_world_action_regressions.py:304`；同文件含空白、拒绝隐私和状态兼容用例 |

源码影响面仅为 `core/adventure.py`、`server/world.py`、`server/app.py`，另新增回归用例和交付文档。沿用角色存活/忙碌门禁、Repository 保存、锁内串行处理及既有悬赏规则，不增加依赖或存档迁移。

未修改 `core/models.py`、`core/character_integrity.py`、经济守恒、鉴权、静态托管、前端展示或其他指令。已有 `AGENTS.md`、`web/` 与 AI 边界文档改动保持原样，不纳入交付包。

## 自测口径与输出

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

`compileall` 与范围内 `git diff --check` 返回 0。交付版源码 SHA256 与全量测试版本一致；复审后重验仍未改变真实数据库哈希。`evidence/source-manifest.json` 记录四个交付源码/测试文件的哈希，`evidence/live-db-before.json` 仅含存档哈希，不含存档内容。

## 独立代码评审

独立只读 Codex 初审发现一个 P2：将用户首词当作日志命令名，会泄露无前缀言行或未知斜杠输入。修复为可信指令目录的精确白名单与固定 `FREE_TEXT` / `UNKNOWN_COMMAND` 标记；拒绝诊断使用固定 `ACTION_REJECTED`，客户端原 HTTP 200 拒绝正文不变。异常日志仅保留类型和堆栈帧元数据，不记录消息、源码行、令牌或原始输入。

2026-10-29 独立复审实际输出为 **Decision: PASS**，无阻塞发现。World/adventure 自初审后未改变，已通过哈希核对。评审证据为 `evidence/independent-review-initial.md` 和 `evidence/independent-review.md`。复审未执行测试或浏览器操作，不替代独立 QA 准出。

## QA 交接与未完成项

- 服务端测试工程师需独立复跑新增/相关回归，并核对两条既有失败性质、HTTP 500 恢复、别名兼容、重复或过期悬赏不再支付。
- 网页端连续“新号入世 → 大荒探险 → 挖宝 → 完成悬赏”尚未手工验证，需 QA 记录实际浏览器证据。准备真实宝图及成熟目标，或在隔离数据库中明确记录测试时钟/预置条件。
- 双方 72 小时新手庇护仍有效，刚建号不能立即击杀完成悬赏；自动测试只在临时数据库中将角色入世时间置于四天前。禁止为即时通关删除庇护规则或改真实存档，此验收条件需负责人和 QA 对齐。
- 由现任团队产品负责人复核范围、跟进 QA 并决策关单；实现者仅交付到 `in_review`，不自行置为 `done`。当前名册未见规范指定的历史“产品与团队规划负责人”，交接同步路由现任负责人，不能假定历史提及能够触发运行。

## 交付包与回退边界

`prox8-backend-world-action-repairs.zip` 包含四个目标源码/测试文件、Spec、Report、三个既有源码文件的 Git diff 及上述测试/评审证据；不含 `.env`、密钥、Git 配置、数据库、完整测试副本或原始评审运行日志。

没有存档迁移。需要回退时仅撤销本包的三个源码改动及新增回归/文档，保留其他并行任务的改动；不要重置整个工作区或覆盖真实存档。
