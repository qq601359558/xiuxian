# PROX-9：静态托管与身份入口加固

- Status: implemented-self-tested-awaiting-independent-review-and-qa
- Date: 2026-10-29
- Branch: `feat/character-integrity-and-audit-rules`
- Base SHA: `5b93aae773d48ee8dcacb516db67b85a4a3007d5`

## Problem / 真正需求

关闭静态路由泄露密钥/数据库、裸道号或客户端 uid 接管角色、简报 uid 越权四条入口，同时保留账号注册登录、token 续玩、新一世和正常资源。
父任务 PROX-6 已获用户确认方案 B，负责人在确认线程发布落地契约并正式派发本单；不重新发起已确定的产品选择，道号保持非唯一。

## Requirement Evaluation / 五步细化

1. **解构本质**：公开道号和 uid 不能作为秘密；身份只来自服务端验证的账号凭据或会话。失败请求不得改写角色或签发会话。
2. **可行性评估**：沿用 Python 标准库 HTTP、PBKDF2 / `hmac.compare_digest`、SQLite Repository 和 World 锁；不加依赖/表结构。路径校验线性，密码计算成本不变。
3. **不足与盲区**：覆盖双重编码、Windows 分隔符、空段、非法扩展名、链接逃逸、无效/注销/重启 token、错误密码/未知账号、双凭据优先级、同名不同账号、无角色账号及死亡新一世；日志不记录密码/token。
4. **举一反三**：同时关闭 `/briefing` 别名旁路；登录与 join 共用失败文案；删除 World 按名找回以避免注册/登录间接串号；同步命令行、帮助、横幅及冒烟。
5. **完善方案**：先旧 SHA 红测，再白名单静态路径与认证 uid；隔离全量回归、独立 diff 评审后交服务端 QA，不自行宣称验收。

## Workspace / 流程覆盖

- 按任务明确指定的单一 in-place 工作树实施，现有分支非 main/master；不切分支、不提交、不推送。
- 保留既有 AGENTS、web 和其它未提交产物，仅修改本单文件。
- 平台 `multica repo checkout` 创建嵌套副本 `xiuxian/`，不是指定基线，不在其中实施，不删除/重置。
- 当前技能无 compose-next，按项目明示 Spec → 先红后绿 → Verify → 独立 Review → Report 契约执行，不安装不明技能。
- 使用 `git archive 5b93aae` 隔离快照，不复制真实 `.env` 或 `data/`；新增 HTTP 测试用临时 SQLite、模拟资源、动态端口，关闭外部 AI 与定时推进。

## Design / 行为契约

### 静态资源

- `/`、`/index.html`、`/web`、`/web/` 为显式首页入口例外。
- `/web/...` 仅限 web 根；兼容 `/images/...` 仅限 web/images。扩展名白名单 html/css/js/json/svg/jpg/jpeg/png/webp/gif。
- 原始路径和两轮 unquote 结果逐段拒绝点、双点、空段；拒绝反斜杠、NUL 和仍有编码的路径。解析目标不得逃出允许根，包括符号链接。
- 裸资源显式映射 workbench.css/workbench.js/app.css/app.js/style.css，优先 web 同名文件；根回退只能是显式白名单真实文件，不跟随链接读其它文件。
- 所有拒绝统一 404，无内部路径、存在性或文件内容泄露。

### 身份入口

- `/join` 缺凭据（包括仅 name/user_id）401 AUTH_REQUIRED；不查询道号，不建角色，不发 token。
- 非空 token 优先；无效时 401 AUTH_FAILED，即使有正确账号密码也不降级。有效 token 从持久化会话取 uid/默认道号。
- 无 token 时要求 username/password 字符串，调用 core.account.login；错误密码、未知账号、非法类型统一 401 AUTH_FAILED，文案「账号或密匙有误」，详细原因仅写服务端日志。
- `/login` 同样隐藏账号枚举；成功字段不变。payload user_id 永不决定身份；name 仅用于新角色显示名。注册、账号登录、token 续玩仅按认证 uid 取角色。
- `World.join(name, *, user_id)` 必须非空已认证 uid，删除按名找回和 lan_ 自动 uid。已死角色沿原结算与新一世规则；保存仍走 CharacterRepository.save。
- `/world/briefing` 和 `/briefing` 仅有效 Bearer 通过；缺失、裸 token、无效 token、仅 uid 参数均 401。
- 不新增玩法操作；续玩保留闭关/被擒状态，新一世为轮回例外，不改变合规守恒门禁。

### 玩家入口

- CLI `join <username>` 提示输入密匙，支持显式密码参数及 `join --token <token>`；裸道号不再登录。
- 冒烟先随机账号注册，再 token 续玩、look/who；结束前关闭 HTTP 服务及线程。
- 横幅引导 register/login，目录 join 说明 token 续玩/账号密匙登录；扫描 Markdown 修正裸 join 示例。

## Out of Scope

- 不做道号唯一化、账号归并、lan_ 认领、真实数据迁移/删除、同场重名社交消歧。
- 不改玩法、前端 UI、HTTPS、反向代理、速率限制、token 生命周期/缓存淘汰。
- 不修旧寄售断言或依赖未启动 8765 的用例；不轮换凭据，疑似泄露密钥由负责人安排。

## Tasks / 可观察验收

- [x] T1：新安全测试在 5b93aae 跑红，原全量基线记录。
- [x] T2：六条指定穿越及编码/Windows/链接变形均 404，无模拟密钥/SQLite 字节；正常首页/脚本/样式/图片 200。
- [x] T3：裸 name/有效 uid/失败凭据 401，角色行数/data_json/updated_at/会话数不变；无效 token 不降级。
- [x] T4：token 续玩与 action、账号跨设备同角色、无角色账号 uid、新同名账号不串号、已死新一世全部通过。
- [x] T5：简报仅有效 Bearer 通过，注销 token 不可续玩。
- [x] T6：CLI/帮助/横幅/文档一致，注册→续玩→行动冒烟通过。
- [ ] T7：隔离全量至少 477 passed，仅余原两条同性质失败；独立评审无未解决 critical，更新 Report，交 QA 准出。

## Evidence

见 `docs/compose/report/server-auth-hardening.md`；实现者自测与代码评审不等于 QA 验收准出。

全量自测达到 551 passed / 2 PRE-EXISTING；T7 的独立 Review/QA 仍未完成。只读 Codex 评审因服务令牌限流与超时未取得结论，交服务端测试工程师独立审查和回归，禁止据此声称已验收。
