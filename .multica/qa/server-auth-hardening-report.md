# PROX-9：服务端安全加固自测交接

- Status: implemented-self-tested-awaiting-independent-review-and-qa
- Date: 2026-10-29
- Branch: `feat/character-integrity-and-audit-rules`
- Base SHA: `5b93aae773d48ee8dcacb516db67b85a4a3007d5`
- Delivery: 本地未提交改动；未创建 PR、提交或推送，待负责人决定定向提交。
- Spec: `docs/compose/spec/server-auth-hardening.md`

## 交付范围

- D-4：静态托管仅 web 根/图片根和五个显式裸资源；原始路径及两轮解码逐段拒绝点、双点、空段、Windows 反斜杠、NUL、残留编码；限制扩展名及解析目标，拒绝统一 404。
- D-5 / D-5b：join 只接受 token 或账号密匙，忽略客户端 uid；World 不再按道号认领，不生成免认证 lan_ uid。错误凭据不建角色，现有存活号续玩、死亡开新一世不变。
- D-4b：world/briefing 与 briefing 别名仅有效 Bearer，通过持久化会话的字典字段解析账号，不接受 uid 查询旁路。
- login/join 失败统一 401 AUTH_FAILED「账号或密匙有误」，内部原因写服务端日志，不记录密码或 token。非 JSON 对象请求返回 400，而非抛内部异常。
- CLI 支持账号+交互密匙或 token；横幅、指令目录、CLAUDE、服务端 README、LAN 冒烟同步。未修改任何前端文件或玩法计算。

## 测试契约同步

新增 `tests/test_auth_hardening.py` 共 74 条用例，执行真实 HTTP 边界和 World/SQLite，使用临时库、动态端口、模拟私有内容，不读取真实密钥或存档。

覆盖指定六条穿越及额外编码/Windows/空段/私有扩展名、正常资源 MIME、显式根资源回退、解析目标逃逸；裸 name/真实账号 uid 的无副作用拒绝；错误密匙/未知账号/非法类型的统一拒绝；token 内存清空后恢复及 action；无效 token 不降级；账号无角色的新建、跨设备续玩、同名账号隔离、死亡新一世、简报 Bearer、注销失效、World 必填 uid 和 CLI。

解析目标逃逸用例通过替换 Path.resolve 模拟链接目标，验证策略边界，不声称已在 Windows 创建真实符号链接。资源正向另以 git archive 内真实文件执行 HTTP 探针。

旧测试对内部 World 的建号调用机械补显式测试 uid，位置包括坊市、CLI 对齐、闭关、奇遇、洞府、对谈及一世循环。按道号找回的旧用例改为验证同名不同账号不串号；保留旧 `/寄售` 断言，不为本单修旧失败。没有减少用例数或保留无凭据入口。

## 自测口径与真实输出

环境：Windows、Python 3.11.0、pytest 9.1.1，使用仓库现有 `.venv` 解释器。统一 `ALLOW_LOCAL_AI=1 / AI_REQUIRED=0 / USE_CCSWITCH=0 / LLM_API_KEY=空 / NPC_TICK_INTERVAL=0`；不调用外部 AI。

原基线与最终全量均使用 `git archive 5b93aae` 新鲜目录，最终仅覆盖本单源码和测试；不复制真实 `.env` 或 `data/`。首次全量尝试超时，最终证据取另建的新鲜 archive 的前台完整运行，不使用超时或旧输出。

| 阶段 | 命令/探针 | 实际输出 | 附件证据 |
| --- | --- | --- | --- |
| 旧版全量基线 | `python -m pytest tests -q` | 477 passed / 2 failed，117.05s | evidence/baseline.txt |
| 旧版安全红测 | `python -m pytest tests/test_auth_hardening.py -q` | 43 failed / 31 passed，53.31s | evidence/red.txt |
| 相关回归 | security + account_auth + account_persist + world_action_regressions + command_catalog | 112 passed，91.70s | evidence/green.txt |
| 新鲜最终全量 | `python -m pytest tests -q --junitxml=../full-final-results.xml` | 551 passed / 2 failed，220.56s | evidence/full-final.txt、full-final-results.xml |
| LAN 关键链路 | `python tests/test_lan_smoke.py` | health/register/token join/look/who OK；LAN smoke OK | evidence/smoke.txt |
| 真实静态资源 | 首页、index、样式、脚本、两种图片路由 | 六条均 200，正确 MIME 与非空文件 | evidence/static-assets.txt |
| 语法/差异检查 | `python -m compileall -q ...`、本单范围 `git diff --check` | exit 0 | 本 Report 及 evidence/source-manifest.json |

最终 553 条 = 旧版 479 条 + 新安全 74 条；成功 551 = 477 + 74，无新全量失败。剩余两条均 **PRE-EXISTING**，性质与旧版输出一致：

1. `tests/test_cli_parity.py::test_cli_parity_commands`：`/寄售` 无参实际为地摊概览，旧断言仍要求失败。
2. `tests/test_workbench_api.py::test_login_then_look_here`：固定 127.0.0.1:8765 服务未启动，WinError 10061。新 HTTP 用例与冒烟使用动态端口，不依赖该服务。

## 数据和影响面

真实 `data/tiandao.db` 的 SHA256 在改动前、相关自测后、最终自测后均为：

`A3AA7E5B13EE335947A4A72074F35AE1A41E2C24B34B52BCDAA31A0268129D80`

未迁移、认领或删除存档；未改 accounts/characters 表结构、道号唯一性、角色 Repository 审计、行动门禁、玩法和前端 UI。API 成功字段与正常资源类型不变，intentional 变化仅身份来源、认证失败状态/文案、非法 JSON 对象和静态拒绝。

## 独立 Review / QA 未完成

独立只读 Codex 评审已实际尝试：初次受 Windows 初始化权限限制，审批后关闭标准输入重试得到服务端 `stream disconnected before completion ... exceeded token rate limit`；后续低开销重试仍超时，未产出评审结论。所有尝试均前台调用，超时子进程已确认结束。

**没有独立 Review 通过证据，也没有 QA 准出，不宣称完成验收。** 请服务端测试工程师先独立审查附件 diff/Spec 与安全回归，再执行独立 HTTP/全量回归并给出准出；发现 critical 必须退回修复。实现者自测不能代替该步骤。

QA 重点：原始 HTTP 穿越不被客户端路径归一化掩盖；未认证请求前后比较角色 data_json/updated_at/会话行；验证真实 uid 无权声明身份、错误密码无新角色、token 与账号跨设备同角色、重名账号独立、死亡开新一世、简报只读自身、正常静态资源。

## 产物与收尾

附件包仅含本单 source、Spec/Report、定向 diff、源码哈希、真实红绿/全量/JUnit/静态/存档哈希证据，不含 `.env`、密钥、Git 配置、数据库或完整测试运行目录。
Spec T1–T6 已有自测证据，T7 保持未勾选，等待独立 Review/QA。issue 交付至 in_review，关单与定向提交/推送由产品负责人决定。

修复尚未部署到运行中的服务，部署后需重启服务；建议同步轮换可能已泄露的 LLM 服务密钥。回退只撤销本单列表，不重置整个工作树、不覆盖真实存档或其它任务改动。
