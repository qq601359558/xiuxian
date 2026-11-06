## PROX-16｜后端架构视角设计自查评审

**结论：不通过当前评审输入。** 已采纳的 DAO_NAME + 字面 GLOB + 部分唯一索引 + 双向保留名门禁 + 跨仓储事务路线可行，不推翻选型；但错误码、转世输入解析、完整事务入口、迁移准入与回滚仍有四个阻断项。本文是方案作者的自查意见，不是第三方独立验收，也不宣布方案定稿。

- 日期：2026-11-03；任务：PROX-16；上游：PROX-12。
- 分支：`feat/character-integrity-and-audit-rules`；勘察 HEAD：`41c64ef8e871631cf3a25db0d913249c8bd2c487`；没有新增 commit 或 PR。
- 依据：启动评论 `01a1a072-65db-7a19-8220-2ce3eecc6920` 的三份 v2 附件，以及 PROX-12 最新负责人裁定。三个附件与根工作树对应文档的 SHA256 均一致；旧 v1 不采用。
- 已关闭决策：`/login`、`/join` 缺角色均 HTTP 409 `CHARACTER_MISSING`；玩家文案删除“归一”；2–12 字、不截断、已死续玩沿旧名、真实库迁移单独审批均不重新询问。

## 一、真正需求与五步推演

- 问题：保证身份比较、命令输入、数据库约束和失败副作用使用同一行为契约，不只是禁止同字符串。
- 本轮行为契约：只评审七个后端点及两个前后端错误契约点；给出位置、严重度、修订建议、责任方和可观察证据。
- 边界：沿用现有 Python/Pydantic、SQLite、标准库 HTTP 服务和原生 JS；不引入新框架、ORM、构建链或持久 name_key。
- 本轮验收：依据最新裁定完成源码与机制核查，提交问题清单与新增证据要求，交负责人汇总；功能验收仍由负责人派发。
- 明确不做：不修改业务/UI/迁移代码，不写应用测试，不执行真实迁移或备份，不删除存档，不提交推送，不操作现有服务。

五步结论：
1. 解构本质：重名拒绝必须与账号、角色、道统、过去世和会话的原子性一起成立。
2. 可行性：现有技术栈支持连接级排序与 SQLite 写事务；当前只读快照为 1040 行，不需要引入第二姓名真源。
3. 盲区：命令层先截词、事务前死亡补标和会话 touch、NUL UID、静态保留名更新、归一扩张后的迁移长度、备份恢复顺序。
4. 举一反三：判定影响 NPC 画像/同场/榜单；投影影响多设备和重启续玩；更新保留名也会影响普通 save。NPC 分身同名消歧仍不在范围内。
5. 推荐路径：保留已采纳方案，先修订规格缺口，再由负责人定稿派发实现；实现期先红测、隔离验证、独立 Review/QA，真实库执行另批。

## 二、七个评审点的答复

| 评审点 | 自查结论 |
| --- | --- |
| 所有 SQLite 连接 | 工厂路线正确，源码为仓储 51 处直连、测试 4 文件共 10 处；当前未实施安装，文本计数不等于覆盖率。应用/后台/迁移/夹具必须同工厂或同一纯安装器，检查算法和 Unicode 版本；外部遗漏规则的拒写范围不能夸大，见 R5。 |
| Python 与 GLOB 等价 | 无 NUL 的 27 个合成例子一致；NULL 由现有 NOT NULL 排除。但 4 个 NUL 例子有 3 个不一致，不能宣称所有 Python str 严格等价，见 R6。 |
| 索引与保留名触发器 | 玩家唯一索引与玩家/NPC 双向触发器互补，NPC-NPC 同名可保留；需覆盖静态保留表更新和正确自排除，见 R7。数据库写锁而非单进程 World 锁负责跨连接竞态。 |
| 注册跨仓储事务 | 单连接、外层唯一 commit/rollback/close 可行；必须包含 helper 隐式写、会话裁剪和提交后发布。审计与版本递增在深副本上执行，见 R3。 |
| 转世结算回滚 | 现有“先结算/扣点后新角色保存”尚未消除。设计应使全部持久副作用一次提交；只改 reincarnate 内部不足以覆盖外层入口，见 R2/R3。 |
| 102 候选迁移 | 102 为历史快照，不是执行名单。分组保留与全局键预占路线正确；当前行数、归一后后缀长度、维护审计例外、完整恢复和二次零变更需闭环，见 R4/R9。 |
| 性能与预计算 | 不要求持久 name_key 或缓存。归一比较线性、玩家索引为 B-tree；NPC 查询和不满足部分索引谓词的查询仍可能扫描。当前真实查询计划为 SCAN，目标性能未验证，见 R10。 |

## 三、问题清单

### R1 · 阻断 · /action 的失败码没有稳定契约

- 位置：`server/app.py:347`、`server/app.py:377`、`server/world.py:324`、`server/world.py:327`、`server/world.py:405`；API 表 `docs/compose/spec/unique-player-names.md:83`。
- 问题：API 原样返回 World 结果；会话无效、活人转世、生死/被擒/闭关门禁等仅有 error。静态 AST 核查 handle/reincarnate 中有 112 个 `ok:false` 字面返回未带 code，这是源码清单，不是已执行用例。新增 NAME_TAKEN/INVALID_NAME 不能靠前端识别句子。
- 建议：命名失败显式给专用 code；行动响应边界为其余未分类业务失败补稳定通用 code（如 ACTION_REJECTED，待契约收录），保留已有 code/error/text 和原 HTTP 约定。其它 IntegrityError、SQLITE_BUSY、缺排序规则或服务异常不得伪装成 NAME_TAKEN。
- 责任方：后端架构作者、后端实现负责人；前端按 code 分类，不新增字符串匹配规则。

### R2 · 阻断 · 转世解析会静默改变候选道号

- 位置：`server/world.py:407`、`server/world.py:651`；姓名规则 `docs/compose/spec/unique-player-names.md:37`；前端 A6/A8。
- 问题：注册支持内部空白比较，但行动先 split，只取首个非加成/非数字词。例如 `/转世 Alice Bob` 变为 Alice，余词被丢弃；现有双引号也被拆开，纯数字被当作加成序号。只删除 reincarnate 的切片/“·转”不能消除这个入口。
- 建议：补无损的带空白道号/加成语法和错误优先级。推荐明确引号/转义，拒绝多余或不完整输入，禁止静默截词或退回旧名；保留裸命令和既有加成用法。完整候选再交同一姓名校验器，两个别名一致。
- 责任方：后端架构作者提出语法，负责人裁定后由后端实现；前端按定稿语法保留草稿。

### R3 · 阻断 · 事务边界遗漏入口级写入

- 位置：`server/world.py:539`、`server/world.py:276`、`server/world.py:329`、`server/world.py:253`；`storage/db.py:392`、`storage/db.py:497`、`storage/db.py:1079`、`storage/db.py:1108`、`storage/db.py:1156`；事务材料 `docs/compose/report/unique-player-names-review-preparation.md:79`。
- 问题：handle 在 reincarnate 前保存寿尽但未标 DEAD 的角色；冷 token 的 get 独立提交 last_seen，并发布内存 Session。账号创建、道统 get_or_create、settle、Chronicle 独立提交；会话 save 还删超过 5 条的旧 token。SQL 回滚后入口写入、审计自愈、version 或内存投影仍可能改变。
- 建议：成文确定注册协调入口及转世整链事务所有者，认证解析用只读 peek。死亡补标、结算/扣点、账号/角色/道统/纪事、会话更新与裁剪同一 BEGIN IMMEDIATE；借用连接的仓储/helper 不 commit/close，不吞其它约束。RAISE(ABORT) 只撤销当前 SQL，外层必须整体 rollback，不能捕获后返回导致上下文提交。六大审计继续经过 save，在完整深副本执行；commit 后才发布所有该 uid 内存会话及首夜/任务副作用。
- 边界：推荐失败不 touch 会话投影或时间戳；若访问时间允许例外，必须单列字段与验收起点，不能继续写“会话全不变”。迁移例外不用于普通 save。
- 责任方：后端架构作者、后端实现负责人；负责人派发独立故障注入验收。

### R4 · 阻断 · 迁移准入、完整性证明与恢复未闭合

- 位置：`docs/compose/spec/unique-player-names.md:101`、`docs/compose/spec/unique-player-names.md:106`、`docs/compose/spec/unique-player-names.md:120`；PROX-12 2026-11-03 最新裁定。
- 问题：真实只读快照现为 1040 行，不能用硬编码 1041/13/8/102 执行或验收。方案有备份和 quick_check，却没有完整恢复；quick_check 不替代唯一约束、索引/表对应关系和排序语义验证。
- 建议：历史数字只放事实基线；T6 用获批执行快照总行数、候选及受保护行指纹。停止全部写入者后预检/批准计划，SQLite backup API 制作一致备份并记录 SHA256；一次事务做姓名/JSON/所有 uid 会话同步与 schema 安装验证，避免 executescript 隐式提交破坏外层事务。增加 DAO_NAME 下的 integrity_check、归一冲突查询和 sqlite_master 定义核对。
- 恢复：SQL 失败整体回滚；提交后恢复先离线停止全部写入者，以核验备份恢复完整库及匹配 schema/比较算法，处理可能的 WAL/SHM，不运行中覆盖主文件。先在隔离副本演练恢复，核对受保护原始行、角色/会话计数和 schema。若会丢提交后的新增数据，另请负责人批准，不盲恢复。本文未执行备份/恢复。
- 审计例外：记录批准标识、备份/计划指纹、允许字段、版本/审计例外理由和前后校验；直接维护只许 name、data_json.name、auth_sessions.name，不能借 save 自愈、增 version、更新时间或裁剪会话。
- 责任方：后端架构作者、迁移实现负责人；负责人审批真实执行，QA 独立复核由负责人派发。

### R5 · 重要 · 连接工厂与外部拒写范围必须分开证明

- 位置：`docs/compose/spec/unique-player-names.md:44`、`docs/compose/report/unique-player-names-review-preparation.md:23`、`docs/compose/report/unique-player-names-review-preparation.md:51`；现有工厂目标 `storage/db.py:21`。
- 问题：51/10 是文本直连数，非安装完成或运行覆盖。纯内存机制诊断中，无 DAO_NAME 的连接对玩家 INSERT、NPC INSERT、name UPDATE 都报 OperationalError，但 status-only、data_json-only UPDATE 仍可成功；部分索引不是“整个数据库禁止未注册连接写入”的屏障。诊断仅建内存示例表/索引，未安装业务触发器或修改真实库；计划中的 UPDATE(name/user_id) 触发器也不覆盖其它写列。
- 建议：应用/后台统一动态解析 DB_PATH 的工厂，借入连接也验证排序规则；迁移、备份检查和四个直连夹具共用纯安装器，禁止导入 WORLD。记录比较算法及 Unicode 版本并在不兼容时明确失败，不能无声 REINDEX 或退回 BINARY。若承诺所有受保护角色写拒绝遗漏规则，UPDATE 门禁必须覆盖其它列并依赖该规则，或维护入口在任何写前强制验证；维护文档明确保护范围，不能称任何外部 SQL 都会自动拒绝。缺规则错误不映射成 NAME_TAKEN。
- 责任方：后端架构作者、数据层/维护工具实现负责人；负责人确认最终门禁表述。

### R6 · 重要 · UID 谓词的等价域没有排除 NUL

- 位置：`docs/compose/spec/unique-player-names.md:39`、`docs/compose/spec/unique-player-names.md:49`；散落判定 `core/npc_mind.py:40`、`core/jianghu_sim.py:29`。
- 问题：SQLite GLOB 在 NUL 处停止，Python startswith/endswith 仍看完整字符串；目前 user_id NOT NULL 不排除 NUL。新诊断无 NUL 的 27 例一致，4 个 NUL 例有 3 个不一致；真实只读库 NUL UID 数为 0，因此不是现存脏数据结论。
- 建议：成文限定 UID 为非空、合法字符串且不含 NUL，在应用、维护预检和数据库写门禁一致拒绝，不能靠调整 GLOB 已定选型绕开。NULL 已由现有 NOT NULL 拒绝；空串的两侧分类都为非 NPC，但身份有效性仍应前置拒绝。全部散落身份判定统一，不能只替换名索引而保留画像/同场少了 _npc 后缀的判断。
- 责任方：后端架构作者、身份判定/数据门禁实现负责人。

判别例（前缀大小写敏感，候选里的 %/_ 为字面字符；NUL 用转义显示）：

| UID | Python / GLOB | 结论 |
| --- | --- | --- |
| npc_、npc_01、ai_npc_01、hero_npc、_npc | 真 / 真 | 合法域 NPC |
| NPC_01、AI_NPC_01、hero_NPC | 假 / 假 | 不做 UID casefold |
| np_01、ch_01、npcX01、aiXnpc_01 | 假 / 假 | 不把测试前缀或 LIKE 伪匹配推定成 NPC |
| npc_%、npc__、foo%_npc、foo__npc | 真 / 真 | %/_ 不成为 GLOB 模式通配符 |
| npc_修士、修士_npc、全角 ｎｐｃ_01 | 真 / 真、真 / 真、假 / 假 | UID 不做姓名归一 |
| 空串 | 假 / 假 | 分类一致但需身份有效性门禁 |
| hero\x00_npc | 真 / 假 | 必须拒绝 NUL |
| hero_npc\x00tail、hero_npc\x00 | 假 / 真 | 必须拒绝 NUL |
| npc_\x00tail | 真 / 真 | 即便分类一致仍拒绝 NUL |

### R7 · 重要 · 静态保留名更新可能与普通 save 互相拆台

- 位置：`docs/compose/spec/unique-player-names.md:55`、`docs/compose/report/unique-player-names-review-preparation.md:50`。
- 问题：角色双向 INSERT/UPDATE 触发器不拦截静态保留表自身的 INSERT/UPDATE。ROSTER 新增一个已被玩家占用的名时，可能先把冲突写进保留表；部分唯一索引仍放行，玩家下次普通 upsert 却被保留触发器拒绝。初始化幂等不等于保留集更新安全。
- 建议：静态同步在同一写事务反查玩家（同样 COLLATE DAO_NAME），或有静态表反向门禁；冲突拒绝同步并上报，不自动改玩家名。角色 INSERT/upsert 按同 uid 自排除，不按可能替换的 id；UPDATE 若允许 uid 变化应排除 OLD 行，或明确 uid 不可变，不能让身份类别切换绕过门禁。NPC-NPC 继续允许同名。
- 锁窗口：查询在触发器所属写语句/事务执行，BEGIN IMMEDIATE 序列化写入者；不能在另一已关闭连接预查后单独落盘。NPC 冲突须拒绝生成，玩家不动，后续画像/议程/事件不能被记作生成成功。NPC 和玩家不同连接先后抢同一比较键，两种顺序均须验证。
- 责任方：后端架构作者、保留名/动态 NPC 实现负责人。

### R8 · 重要 · INVALID_NAME 的文案尚无一致唯一真源

- 位置：`docs/compose/spec/unique-player-names.md:80`、`docs/compose/spec/unique-player-names.md:82`、`docs/compose/report/unique-player-names-frontend-design.md:55`、`docs/compose/report/unique-player-names-frontend-design.md:56`。
- 问题：NAME_TAKEN 规划基础句在两份文档一致，均为“此道号已被占用，请另取一名”，但现有 /register 未实现 409/code。Spec 的 INVALID_NAME 只有状态而没有完整 error 基础句；前端表、标签和图仍使用已被产品要求删除的“归一”。因此当前两份文档不能整体宣称唯一真源。/join 仍写待签字也已过时。
- 建议：把两种注册错误的完整状态/code/error 定在 Spec，前端共享基础映射严格对齐；转世只做已定义的场景包装。INVALID_NAME 建议写为“道号须为 2–12 个字（首尾空格不计），请修改后重试。”，按已裁定措辞同步标签/布局图/走查断言。将 /join 写实为 409 CHARACTER_MISSING，不再请求签字。
- 校验口径：明确长度取 NFKC/空白折叠后的显示规范化值，不取 JS UTF-16 长度或 casefold 扩张后的比较键；比较归一不回填显示名，避免以“保留大小写”替代“显示原样”的契约说明。
- 责任方：后端架构作者更新 Spec；前端工艺工程师同步文案提案；负责人汇总确认，不修改 UI。

### R9 · 重要 · 历史后缀按原始长度截断仍可能越过 12 字

- 位置：`docs/compose/spec/unique-player-names.md:103`、`docs/compose/spec/unique-player-names.md:104`。
- 问题：历史名可超长且 NFKC 可扩张。合成例中原名为 12 个 ﬃ，取 9 个再加“·旧2”，原始长度为 12，显示归一后却是 30。只按原字符串和后缀长度算切片不闭合新名长度规则。跨组迭代顺序也会影响同前缀候选拿到的 N。
- 建议：只对需改名候选，按实际后缀长度寻找使最终显示规范化长度在 2–12 的前缀；最终完整候选再次校验比较键。沿用已规定的全部原有键、已分配键、静态/全部动态 NPC 键预占并递增 N，不能截断整个成品而丢后缀。补确定的组/候选排序与 id 同时刻方向；N 变两位以上、后缀无可用空间或找不到合法唯一名时明确中止，不无限循环。历史不改名行不回溯修长度。
- 责任方：后端架构作者、迁移实现负责人；验收由负责人派发。

### R10 · 建议 · 查询谓词与性能证据对齐，不提前加缓存

- 位置：`storage/db.py:428`、`storage/db.py:431`；索引设计 `docs/compose/spec/unique-player-names.md:47`。
- 问题：当前 get_by_name 为 BINARY 等值且无 NPC 部分谓词；真实 EXPLAIN QUERY PLAN 为 SCAN characters。创建 DAO_NAME 部分索引不会自动让这个查询使用归一比较或部分索引。当前库还没有该姓名索引，这是未实现状态，不计实现失败。
- 建议：查重/玩家身份查找使用显式 COLLATE DAO_NAME 与匹配的玩家谓词；保留 NPC 分身查询的既有边界。约千行不要求预计算或缓存。玩家路径预计 O(L log P)，NPC 保留名检查若无合适索引可能 O(NL)，且在写锁内，应测计划与锁等待。
- 演进：若增长后有实测热点，优先评估非唯一 DAO_NAME 姓名索引或有界纯函数缓存；二者不落持久 name_key、不引第二真源。缓存不作为占名裁决，不缓存动态 NPC“可用”判断；算法版本不兼容先停机维护。没有测量不加缓存、不承诺 QPS；首夜 AI 不在数据库写事务内。
- 责任方：后端架构作者、仓储实现负责人；优化前记录规模、计划、比较次数/锁等待及端到端延迟。

## 四、实际证据与未验证项

环境：Windows；Python 3.11.0；SQLite 3.38.4；Unicode 14.0.0。源码/规则通过 UTF-8 读取；诊断以 `@'…'@ | .\.venv\Scripts\python.exe -` 前台执行，仅导入标准库，不导入应用。

| 命令/诊断 | 实际输出摘要 | 证据附件 |
| --- | --- | --- |
| `multica issue get` + roots summary + 有关 thread tail 30 | 已读 PROX-16 最新三份 v2 与 PROX-12 当前裁定；无新增实现授权 | 本报告依据章节 |
| `rg -n 'sqlite3\.connect' storage/db.py`、`rg -n 'sqlite3\.connect' tests`，加 AST 清点 | 仓储 51、测试 10（4 文件）；handle/reincarnate 112 个字面业务失败无 code | static-inventory.txt |
| readonly URI `mode=ro` + `PRAGMA query_only=ON` + 只读事务 | query_only=1；journal_mode=delete；characters=1040；NUL UID=0；仅 id/uid 自动索引，无姓名索引/触发器 | readonly-diagnostics.txt |
| 同次读取前后 SHA256 | 均为 `ae9411e33228a416e835e4528ed0d25e8ceed5c8c5b995da3c15b72ac08fbf8c` | readonly-diagnostics.txt |
| 合成 UID GLOB/字符串比较、姓名归一、后缀长度诊断 | 普通 UID 27/27 一致；NUL 4 例中 3 例不一致；8 组姓名比较；后缀成品 raw=12、normalized=30 | readonly-diagnostics.txt |
| 无排序规则连接的纯内存部分索引诊断 | 3 类命名写拒绝，2 类非索引列写允许；均非真实库 | sqlite-constraint-diagnostics.txt |
| `git branch --show-current`、`git rev-parse HEAD`、`git diff --name-only` | 分支/HEAD 如首页；原有 AGENTS.md diff 未动，本轮仅新增评审输入/产物/日志 | 本报告 |
| 应用 pytest/API/迁移/并发/恢复演练 | **未执行，应用测试用例数 0**；设计阶段门禁，不是测试通过 | 未验证 |

本文未读取或发布账号密码、token、实际 UID 名单或玩家姓名；仅发布聚合计数与合成判别例。旧 551 passed 等结果不算本轮证据。真实缺角色账号、执行候选与受保护行指纹仍需 PROX-19 独立复核。

## 五、只增补必要的可观察验收

1. **T1/T2 连接及判定**：列出所有直连替换/借入连接安装证据；遗漏规则的 INSERT、NPC INSERT、各类 UPDATE 按已明确保护范围拒绝且快照不变，缺规则不变 NAME_TAKEN。NUL/NULL/空串按身份域拒绝；大小写、%/_、Unicode、_npc 后缀两侧一致；算法/Unicode 版本不兼容启动明确失败。
2. **T2/T7 保留名和竞态**：静态表新增/更新撞玩家名被拒绝，玩家原始行不动；同 uid 新 id upsert 正常、NPC-NPC 同名允许；uid 类别切换不可绕过。不同连接 NPC/玩家两种写入顺序均恰好允许合法先占者，后者显式失败；记录锁等待/忙错误，不把忙或其它约束伪装成撞名。保留原 20 线程 1 成功/19 NAME_TAKEN/0 个 500 验收。
3. **T3/T5 错误与语法**：注册 409 NAME_TAKEN/400 INVALID_NAME 的状态、code、error 与定稿唯一基础句逐字一致；/action 业务失败稳定带 code，只有 code/error 没有 text 时也可分类。两个转世别名覆盖带内部空白/引号、数字或加成歧义、多余尾词、不完整输入、裸命令，完整候选不被截词/截断/退成旧名；失败无消费。
4. **T3/T4/T5 全链故障注入**：覆盖冷 token、寿尽未标 DEAD、death_settled=false，以及账号/道统/角色审计后/会话裁剪后/纪事写后/commit 失败。比对 accounts、characters 原始行与 version/death_settled、完整 legacy/past_lives、全部持久/内存会话、纪事；无残留 token、无首夜/任务调用。允许的访问时间戳例外须逐字段列明；成功同步所有设备并重启续玩，普通 save 六大不变式回归不能跳过。
5. **T6 迁移与恢复**：删掉硬编码执行数字，按获批当前快照验行数守恒、非 NPC 重名/NPC 保留冲突归零、账号/NPC 原始行字节不变、候选其它字段和 version/时间戳不变、该 uid 所有 sessions.name 同步。覆盖 NFKC 扩张、两位后缀、跨组截断碰撞、同时间 id 排序、输入顺序变化计划相同。验证 integrity_check、schema 定义、失败整体回滚、备份恢复副本，以及二次零数据/零 schema 变更；保存维护审计例外与批准记录。
6. **T8 回归与交接**：实现期在隔离副本记录新鲜基线、相关 pytest/关键 API、最终回归和独立 Review/QA 输出；既有失败仅按新输出标 PRE-EXISTING。若声称姓名性能改善，补目标查询计划及实际规模/比较/锁等待/延迟，不用本轮 SCAN 或内存机制诊断代替实现性能验收。

## 六、未决项与交接

- 请负责人裁定带内部空白道号与既有加成的无损转世语法；推荐明确引号/转义、额外输入显式拒绝，不通过禁止所有空白名来缩小已定比较规则。
- 转世失败是否自动切到玄阁洞府仍待阶段三裁定。后端建议把它限定为已明确 NAME_TAKEN/INVALID_NAME 的纯 UI 导航，不能发迁跃/login/join 或暗示角色变更；具体视觉方案由前端与负责人决定。
- /join 409、删除“归一”、迁移范围与姓名选型不是未决项；只是文档必须同步。外部拒写保护范围也须在规格明确，不能把部分索引冒充全面数据库权限控制。
- 本评审交付后 PROX-16 进入 in_review，PROX-12 保持其原状态。请负责人汇总各视角、安排修订/复审、清空问题后宣布定稿并正式派发阶段四；本轮不自行唤醒 QA 或关单。
