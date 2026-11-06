# PROX-12 设计核查报告

- Date: 2026-11-02
- Status: design-draft-only; implementation-blocked-on-review-and-scope
- Environment: Windows / Python 3.11.0 / SQLite 3.38.4
- Branch: `feat/character-integrity-and-audit-rules`
- SHA: `4bf5a4c35386c56b2e9809724d08af8aa8511a2e`

## 结论

核实 PROX-9 done 与本地提交，完成五步细化与设计契约。未找到全员评审定稿；原 SQL/迁移验收存在缺口。按门禁未修改业务、UI 或存档。

## 新鲜证据（不是应用验收）

以前台 `.venv/Scripts/python.exe` 诊断，只读 URI `?mode=ro` 打开真实 SQLite，直接 SELECT、不导入应用；静态 ROSTER 通过 AST 读取。仅输出汇总，不含账号凭据、token 或真实玩家名字。

| 指标 | 本轮结果 |
|---|---|
| 角色总行 | 1041 |
| npc_/ai_npc_ 前缀与 _npc 后缀判定 NPC | 109 |
| 非 NPC | 932 |
| 账号对应角色 | 104 |
| 全表原始重名 | 28 组 / 158 行 |
| 非 NPC 原始及归一重名 | 13 组 / 107 行 |
| 重复改名候选 | 94 |
| 玩家与 NPC 保留名冲突 | 8 |
| 推荐两者候选并集 | 102 |
| ROSTER 条目 | 37 |
| 账号归一重名/NPC 撞名/列与 JSON 姓名不一致/进入重复组 | 均 0 |
| 角色索引 | 仅主键和 user_id 两个自动索引 |

前后 SHA256 均为 `9c5a672a247a745a29351d6751005d64dd0230bccb42c043530b72866ba04336`。1041/104 与父线程额外 smoke 数据记录一致；本轮不删除。

### 原需求 SQL 内存实验

在 :memory: 新建 characters 和原样索引后 INSERT，exit 0 的真实输出：

```text
p1 / Alice          ACCEPTED
p2 / 全角 alice     ACCEPTED
p3 / 空格 Alice     ACCEPTED
ai_npc_probe/Alice  REJECTED
```

全角/空白同名放行，ai_npc_ 因缺 ESCAPE 错误纳入约束，原 SQL 不足以覆盖 R1/R6 与 NPC 豁免。

### 推荐排序规则与 GLOB 实验

在 :memory: 注册 DAO_NAME（NFKC → Unicode 空白折叠 → casefold）并创建 Spec 部分索引，exit 0 输出：

```text
p1 / Alice           ACCEPTED
p2 / ALICE           REJECTED
p3 / 全角 alice      REJECTED
p4 / 空格 Alice      REJECTED
npc_probe/Alice      ACCEPTED
ai_npc_probe/Alice   ACCEPTED
sect_probe_npc/Alice ACCEPTED
```

仅证明推荐索引可行，不证明保留名触发器、事务、迁移或应用并发已实现。

诊断初稿遇到 ROSTER 工厂调用不可 literal_eval，以及 PowerShell 反斜杠传输造成 ESCAPE 构造异常；改为读取静态 _n 第二实参和字符码构造实验反斜杠后重跑。以上仅引用最终成功输出，不把诊断失败当产品回归。

## 代码事实与影响面

- `core/account.py:24`、`storage/db.py:1156`：账号独立提交，角色冲突会半注册。
- `server/app.py:294`：register 后 WORLD.join；login/join 在已死/缺角色分支仍使用客户端名。
- `server/world.py:192`：join 含已死/缺角色新建分支，不能只测存活角色。
- `server/world.py:319`：先结算，再静默后缀，Legacy 先于角色保存；只删后缀不能保证零副作用。
- `storage/db.py:392`：复用角色 save 审计和 user_id upsert，增加事务支持，不另写普通角色落盘。
- `core/npc_mind.py:40`、`core/scene_banter.py:58` 等只查前缀，梳理后缀影响。
- `web/workbench.js:6572`：已有 gateMsg；该文件有用户未提交改动，后端不覆写。

## 未执行与交接

本轮产物验证 exit 0：两份文档 UTF-8 解码/末尾换行/无尾空白通过；Spec 必要章节 8/8；真实库 SHA256 再次保持不变；git status 仅新增两份设计文档，原有业务/UI 未提交状态不变。git diff --check exit 0，未跟踪文档另由上述逐行检查覆盖。

- 未跑注册/转世失败测试、20 线程、迁移演练或 pytest；未创建备份、写数据库、删除 smoke。
- 未获独立 Review/服务端 QA/前端 QA，不宣称实现完成或验收。
- 请负责人审核两道决策门，组织前端确认与全员评审，再派发实现。本单整体仍未交付，应 blocked，不能将草案等同实现准出。
