## PROX-12：道号唯一与一号一角色（已采纳、待全员评审）

- Status: adopted-awaiting-stage2-and-stage3-not-approved-for-implementation
- Date: 2026-11-03
- Issue: PROX-12 / 01a186c2-cfbb-7e6f-ac1a-54c2064307d8
- Branch: `feat/character-integrity-and-audit-rules`
- Base SHA: `4bf5a4c35386c56b2e9809724d08af8aa8511a2e`
- Working HEAD: `41c64ef8e871631cf3a25db0d913249c8bd2c487`（新增前端提交，不改变本单后端设计基线）
- 本轮只交付需求细化、架构和契约；未实施业务代码、迁移或取得 QA 准出。

## Problem / 真正需求

账号负责认证，道号负责显示和查找。非 NPC 道号按统一比较规则唯一，并避开静态与库内 NPC 名。冲突显式失败，不留下孤立账号、额外角色或道统消费。一号最多一角色由既有 `user_id UNIQUE NOT NULL` 兜底。

产品已确定 R1–R6；负责人于 2026-11-02 在评论 `01a19bc9-a612-7855-b0cd-113c149eec1c` 采纳排序规则、事务和 102 行迁移范围，并裁定长度、缺角色和已死续玩边界。不重新询问已定产品规则；采纳只允许进入评审，不代表全员定稿或实现派工。

## Requirement Evaluation / 五步推演

1. **解构本质**：消除玩家身份歧义，不只是禁止相同字符串。注册、转世、续玩和存档使用同一规则；冲突不改变账号、角色、会话、道统或历史。
2. **可行性**：沿用 Python 3.11、SQLite 3.38.4、World 锁和 Repository。归一为线性成本，部分唯一索引为 B-tree 路径；自定义排序会增加 Python 比较调用，20 线程验收测量，不承诺未经测试的 QPS。
3. **盲区**：NOCASE 不支持 NFKC/空白；原 SQL 的 ai_npc_ 条件缺 ESCAPE；LIKE 与 Python 大小写语义不同；账号先提交造成半注册；转世先结算/扣点后存角色；单例也有 NPC 撞名；登录已死/缺角色仍采用客户端 name。
4. **举一反三**：NPC 判定影响名册、同场、交谈、画像、榜单和动态生成；未来 NPC 创建也要避开玩家名。唯一化不解决 NPC 分身间同名歧义，不能宣称所有交谈歧义自然消失。
5. **完善方案**：统一比较与部分索引、数据库保留名门禁、跨仓储事务。只读预检后进行隔离红测、迁移演练、回归、独立 Review/QA，再申请真实库迁移。

## Workspace / 门禁

- 任务指定单一 in-place 工作树，采用现有非 main/master 分支；保留已有 AGENTS、web 和其它未提交产物，不切分支、不提交、不推送。
- 已执行 multica repo checkout，返回嵌套副本 xiuxian/，不替代指定工作树、不在其中实施、不删除它。
- PROX-9 已由负责人关单，本地 HEAD 包含其提交。尚未找到 PROX-12 全员设计评审定稿记录。
- 架构与库表 → 前端确认 gateMsg 交互 → 全员评审 → 负责人正式派发后端与前端实现，本轮禁止越序编码。
- 当前技能无 compose-next；实现时遵守项目 Spec → 红测 → Implement → Verify → 独立 Review → Report 契约，不安装不明技能。

## Design / 已采纳方案（待全员评审）

### 姓名与 NPC 判定

- 登记输入按 NFKC、折叠 Unicode 空白、去首尾空白校验；保留显示大小写，不做繁简转换。排序规则仅计算 casefold 比较键，不把比较键写回显示名，已有存档不因索引或查询被改名；不建立第二 name_key 真源。
- 仅注册与显式转世接收新名。注册缺省 name 可取 username，显式空白名不得回退；归一后必须为 2–12 字，不足或超长一律 INVALID_NAME，不截断、不静默改名；历史短名及超长名不回溯修正。
- 字面、大小写敏感 UID 规则：npc_ 或 ai_npc_ 前缀、或 _npc 后缀。Python 使用单一 is_npc_uid，SQL 使用等价 GLOB；不把 np_/ch_ 等测试前缀推定为 NPC。
- 保留名为 ROSTER 全部静态名 + 全部库内 NPC 行（含死亡态），使用相同比较键。

### 数据库约束

推荐保留 characters.name 显示值，注册确定性 DAO_NAME 排序规则（比较归一键），经连接工厂安装到每个 SQLite 连接，不能只在启动连接注册。外部 SQLite 写工具未注册时应拒绝相关写入，维护文档说明兼容成本。

```sql
CREATE UNIQUE INDEX idx_char_player_name
ON characters(name COLLATE DAO_NAME)
WHERE user_id NOT GLOB 'npc_*'
  AND user_id NOT GLOB 'ai_npc_*'
  AND user_id NOT GLOB '*_npc';
```

- 非 NPC INSERT/UPDATE 都由索引阻断归一重名；同 uid upsert 保持一行，禁止 REPLACE 夺取另一角色。
- 建议静态保留名表从 ROSTER 幂等同步；触发器对玩家 INSERT/UPDATE 检查静态表和 NPC 行，对 NPC INSERT/UPDATE 反查玩家占用。RAISE(ABORT, NAME_TAKEN) 防止先查后写竞态。
- NPC-NPC 同名允许；动态 NPC 撞玩家名拒绝生成/落盘，不改玩家名，覆盖其失败调用链。
- 只把姓名索引/保留名门禁的 IntegrityError 映射为 NAME_TAKEN；用户名冲突保留既有 400，其它约束错误不伪装。
- 负责人已否决持久 name_key 列与原 NOCASE 索引；不再将它们列为待选方案。

### 事务与守恒

- 注册：校验、哈希 → 同一写事务创建账号、通过 CharacterRepository.save 创建角色、写必要道统/会话 → 一次提交。撞名全部回滚，不残留占用用户名的孤立账号。
- 仓储支持同一事务连接，默认独立调用保持；所有普通角色存档仍走 save 和六大不变式审计。首夜 AI/新手任务等在成功提交后运行；失败不签发新会话。
- 转世先验证会话、死亡条件、新名和消费条件；结算、道统、角色、持久会话同事务，唯一冲突全部回滚。死亡态、道统点、过去世不变。
- 提交后才更新全部该 uid 内存会话的 character_id，持久 auth_sessions.name/character_id 同步。
- 其它角色操作继续遵守 assert_alive/assert_idle、灵石与背包门禁，不借本单改数值机制。

### 登录边界

- login/join 所有分支忽略客户端 name/uid。存活角色按认证 uid 恢复，新 token 不增加角色行。
- PROX-9 的已死自动下一世默认不删，但仅沿用存档旧名；测试道统结算性质不变。
- 缺角色旧账号返回显式 CHARACTER_MISSING，不借 login/join 建角色或采用客户端 name；login HTTP 409，action 沿用 ok:false。受影响账号数必须由 PROX-19 服务端测试工程师按 accounts 左连接 characters 独立复核，不能由“104 行账号角色”推断为零；发现真实受影响账号先交负责人处理。

## API Contract / 草案

沿用现有标准库 HTTP、响应字段和认证方式，不新增端点。

| 路由 | 请求与成功 | 失败 |
|---|---|---|
| POST /register | username/password/可选 name；200 保留 ok/username/token/角色字段 | 409 `{ok:false,code:NAME_TAKEN,error:此道号已被占用，请另取一名}`；INVALID_NAME 400；用户名重复保持既有 400 与文案 |
| POST /login | username/password，忽略 name；200 原角色与新 token | 认证失败沿用 401 AUTH_FAILED；缺角色 409 CHARACTER_MISSING，不签发新会话 |
| POST /join | token 或账号凭据，忽略 name/uid；200 同 uid 续玩 | 保留 AUTH_REQUIRED/AUTH_FAILED；缺角色 CHARACTER_MISSING 不建号，HTTP 映射纳入阶段三签字项 |
| POST /action | token，command 为 `/转世 新道号`；成功字段不变 | 保持 action 传输约定，业务 `{ok:false,code:NAME_TAKEN,error:此道号已被占用，请另取一名}`；不把注册 409 推广到其它路由 |

前端保留错误 code，注册门庭复用 gateMsg 展示文案；由前端工程师在用户未提交改动上实施，后端本轮不改页面。

## Migration / 方案（未执行）

### 历史基线与已批准设计范围

2026-11-02 只读实测：1041 角色行、104 账号角色；统一 UID 判定 NPC 109、非 NPC 932。全表重名 28 组/158 行，非 NPC 只有 13 组/107 行，去重需改 94 行。另有 8 个非 NPC 与 NPC 保留名冲突，不在这 94 行中；共 102 个候选，真实账号不在其中。该数字为历史快照，不是对执行时数据的保证。

需求的 1040/103 是旧快照；父线程记录后来新增的指定 smoke 测试账号/角色。本单不删任何行，不把“删除测试数据”扩大成清理全部前缀；负责人另行清理后重新预检。

- 负责人已确认 8 行 NPC 撞名一并重命名，不动 NPC 或真实账号；不允许将历史撞名作为永久例外。真实库执行仍另获批准。
- 全表 28 组包括 NPC 分身，不能将它写作非 NPC 28 → 0 的验收。
- 2026-11-03 当前库 SHA256 已不同于上述历史快照；执行前必须重取统计、候选和受保护行指纹，交 QA 与负责人签字。本轮不重用旧快照冒充当前数据、不执行迁移。

### 安全与幂等

1. 停服务/隔离写入，用 SQLite backup API 制作时间戳备份，核对 quick_check、SHA256；发布实际备份位置和副本演练前后统计，请负责人批准真实库执行。本轮没有创建或宣称已有备份。
2. 预检全表、账号/NPC 快照、规范化冲突、JSON。任何真实账号进入改名候选、非法 JSON 或快照漂移立即停止，不自行抢救/删除。
3. 按比较键分组，最近 updated_at 保留原名，时间相同按 id 稳定排序；NPC 保留名组不保留玩家原名。先保留全部不改名行的键。
4. 生成 `原名·旧N`，N 从 2 起，按后缀实际长度截断原名，总长不超 12；避开全部原有键、已分配键、NPC 保留名，冲突递增 N。
5. 一次事务更新 characters.name、data_json.name、该 uid 全部 auth_sessions.name；其它 JSON 与 id/uid/status/created_at/updated_at 不改。迁移为专门维护，须明确记录其对普通 save 审计/版本递增的例外，不用于普通角色落盘。
6. 同一事务创建并验证索引和保留名门禁；核对行数守恒、账号原始 name/data_json 全字节不变、NPC 不变、冲突归零后提交。
7. 第二次输出零变更，保存匿名计数。init_db 不得未经批准遇到冲突就自动修改真实存档；授权前明确失败并提示离线迁移。

## Acceptance Tasks / 独立验收

实现项均未执行；以下为后续验收依据，计数以批准的运行快照更新。

| 任务 | 观察证据 |
|---|---|
| T1 比较与身份 | Unicode 首尾/内部空白、Alice/ALICE/全角、拉丁扩展、UID 前后缀/大小写单测；Python 与 SQL 一致 |
| T2 数据约束 | 非 NPC INSERT/UPDATE 归一冲突抛指定 IntegrityError；NPC 分身可同名；玩家/NPC 双向占用拒绝；同 uid 最多一行 |
| T3 注册 | 第二同名账号 409，accounts/characters/sessions 无残留；NPC 静态/库内名 409；INVALID_NAME 400；用户名重复保持 400 |
| T4 续玩 | 不同客户端名、跨设备 token、已死/缺角色边界按批准契约；认证失败无写入；同 uid 一行 |
| T5 转世 | 撞名失败死亡态/道统/历史/会话不变；失败注入覆盖先查后竞态；成功释放旧名；无参数沿旧名；各设备会话同步 |
| T6 迁移 | 真实库备份副本行数不变、非 NPC 13 组降至 0、按批准范围 NPC 撞名降至 0；受保护账号/NPC 不变；列/JSON/session 一致；第二次零变更 |
| T7 并发 | 20 线程不同用户名同时注册同一比较键：1 成功、19 NAME_TAKEN、0 个 500；仅一新角色，无孤立账号 |
| T8 回归 | 新鲜隔离基线/最终 pytest 输出，既有失败标 PRE-EXISTING 且性质不变；至少既有 551 通过能力不减；独立 Review、服务端和前端 QA 分别出证据 |

## Verify / 本阶段

- 仅运行只读统计与内存 SQLite 实验，见 Report；未跑应用 pytest、迁移演练或应用并发。
- 不把 PROX-9 的 551 passed / 2 PRE-EXISTING 当本轮结果。
- 实现前 git archive 指定基线做隔离副本，不复制真实 .env/data；重定向 DB_PATH/AI 日志/World 定时器，API 用动态回环端口，LAN 冒烟不碰真实服务。

## Out of Scope

- 不做自助改名、繁简归一、合并账号、调整用户名、NPC 命名重构或分身消歧。
- 不删历史行、不清理任意测试前缀、不实施父线程的定向删除。
- 不覆写用户未提交 web、不新增组件、不修无关测试/安全入口。
- 本轮不实施、不迁移、不提交推送、不自行宣称验收或关闭任务。

## Review Gate / 阶段与剩余签字项

- 产品决策已采纳，不重复发起选型或迁移范围问题。
- PROX-15 阶段二方案仍 todo，尚无交付；PROX-16–19 阶段三评审仍 backlog。该阶段任务由负责人恢复/提升，后端不越权重派前端或唤醒 QA。
- 连接覆盖、UID 判定等价、触发器自排除/反向门禁、跨仓储提交与内存回滚、迁移审计例外以及 join 缺角色 HTTP 映射需要阶段三签字，详见补充评审材料。
- 真实库快照已漂移，受影响账号/迁移候选须按执行快照重新复核；真实库写入仍独立审批。
- 全员清空问题后负责人定稿并正式派发阶段四实现；本单整体仍 in_progress，不以设计补充转 in_review/done。
