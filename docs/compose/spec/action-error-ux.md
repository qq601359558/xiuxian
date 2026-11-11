# Spec：操作报错不再出现后端原文（action-error-ux）

状态：实现完成，待全量回归收尾 · 分支 `feat/action-error-ux`（worktree `.worktrees/action-error-ux`，自 `main` 切出）
基线说明：任务书称 main = 2082c40，实际切出时 main 已是 fed5332（交谈结构化
修复版，已发布部署）。本分支基于 fed5332；回归基线以此为准重测，任务书所引
1442 passed / 8 failed 为旧定版数字，仅作对照参考。
版本说明（总管 2026-11-10 纠正）：本分支不写死任何目标版本号，不碰
VERSION/CHANGELOG——发版号由发版岗在合并时定。合并前先同步最新 main：
块一流水线（feat/playability-block1）正在推下一版，若它先落地，本分支
rebase/merge 到其上再发版，版本号取届时下一个空号（预计下一空号，
不自行写死）。若本分支先就绪而块一未落地，停在「分支就绪 + 报告交总管」，
不自行合并、不部署 NAS，由总管统一排合并与部署顺序。

## 实现记录（2026-11-10）

- 改动：`server/app.py`（/action 缺参加 code）、`server/world.py`
  （活角/死者回退快照加 `code: "WORLD_BUSY"`）、`web/mobile.js`（净增 +114 行，
  2083 行）、`web/workbench.js`（净增 +125 行）、新增
  `tests/test_action_error_ux.py`（20 测试，含 MF-1/MF-2 锁定项）与本 Spec。
- 先红后绿：新测试初跑 10 failed / 3 passed（随后补 4 项登录回退测试，
  14 failed / 3 passed），实现后 17 passed。
- 隔离服真机复现（`/tmp/aeu_repro.py`，端口 18765，数据 /tmp/aeu-iso）：
  持锁登录 1.75s 返回 token None + WORLD_BUSY；松锁登录正常发 token；
  /action 缺 token → 400 AUTH_REQUIRED、缺 command → 400 EMPTY_COMMAND、
  正常 /look 200。ALL PASS。
- 相关套件：新测试 + CT-01 + CT-04 + test_login_latency_fix 全绿（64 passed）。
- 全量回归：基线（fed5332 干净态启动，但中途被本实现编辑污染，见下）
  1453 passed / 10 failed，31 分钟；改动后全量 1465 passed / 15 failed，
  39 分 39 秒（日志 `~/workspace/action-error-ux-after.log`，含新增 17 测试
  全绿）。15 失败逐条定性（均非本改动导致）：
  ① 与基线重合 8 条：其中 7 条在干净主仓单跑复现（pre-existing）；
  另 1 条 lan_feed 在两轮全量皆挂、但主仓/我分支新鲜库下单跑皆过，
  属 DB 残留抖动（见③）。
  ② 新增 7 条：vd03、hunt_state×2 在干净主仓单跑复现（pre-existing）；
  revenge、ledger_write、npc_tick 3 条是 worktree `data/tiandao.db`
  测试残留所致——新鲜库下我分支单跑全过、陈旧库下复现全挂（双向验证，
  残留库已删除，QA 重跑不受影响）；rm02 在我分支单跑通过（全量内抖动）。
  ③ 机制：`init_db()` 直连仓库 `data/tiandao.db`（非 tmp），多次全量
  累积同名测试角色，`get_by_name` 命中陈旧角色致模拟结果漂移；与本
  改动（只增 code 字段 + 前端呈现层）无交集。另：基线中 CT-01 的失败
  已证实为污染所致——基线跑到一半时本分支中间态注释里含字面 `data.code`，
  触发 CT-01 死键漂移；该注释已改写，主仓干净态 CT-01/CT-04 复测通过，
  本分支改动后 CT-01 亦绿。基线 10 失败集：test_auth_hardening::test_world_join_requires_explicit_nonempty_authenticated_uid、
  test_contract_audit::test_CT01_bidirectional_diff、
  test_karma_chains::test_kill_and_bounty_single_chain、
  test_living_jianghu::test_lan_feed_endpoint_contract、
  test_natural_omen::test_initial_character_and_config、
  test_pawn::test_world_handle_pawn_chain、
  test_qa_account_death_acceptance::test_qa2_join_dead_http_and_anonymous_unchanged、
  test_status_dict_gray::test_status_dict_includes_bag_and_marks、
  test_status_dict_gray::test_status_dict_follows_real_equip_flow、
  test_workbench_api::test_login_then_look_here。
  改动后 15 失败集：基线集减 CT-01、减 pawn，加 game_feel_phase2_drama::test_rm02_chain_resolved_rumor_single_point_both_paths、
  game_feel_phase2_fate::test_vd03_degrade_dead_and_overtier_and_none、
  hunt_state::test_issue_threshold_and_dedup、hunt_state::test_no_orders_kv_legacy_flow、
  jianghu_sim::test_revenge_same_loc_can_kill_and_cascade、
  living_jianghu::test_jianghu_ledger_write_and_project、
  living_jianghu::test_npc_tick_without_ai_writes_jianghu。
- 评审 must-fix（2026-11-10，报告 `~/workspace/reviews/action-error-ux-review.md`）：
  MF-1 双端 doAuth 重试定时器句柄存入 `state.loginRetryTimer`，新增
  `clearLoginRetryTimer()`，手动提交/成功登录/非忙无 token 三处清掉，
  仅无挂起定时器时调度；MF-2 桌面 Ctrl+K 预填 `/` 后补
  `syncCmdGoDisabled()`；Spec §4 workbench 净增更正为实测 +125 行，
  验收列表重复编号修正为 1–10。复跑：新测试 20 项全绿，CT-01 全套
  （与新测试合计 50 passed），`node --check` 双端通过。
- 注意：中途运行环境重启过一次（/tmp 被清空，第一次改动后全量跑到约 57%
  被杀、日志丢失），本次 1465/15 是重启后等块一全量跑完、重新起的干净
  全量；新测试 + 相关套件在重启后复测仍 64 绿。

## Problem

玩家在界面上能直接看到后端校验原文「需要 token 与 command」：

- `server/app.py` POST `/action`：token 或 command 为空 → 400
  `{"ok": false, "error": "需要 token 与 command"}`。这是给程序看的校验错误。
- `web/mobile.js` `api()`（约 164–190 行）把 HTTP 错误体的 `j.error` 原样包进
  `Error.message`；`sendCmd` 的 catch 分支原样 `pushFeed("敕令失败：" + e.message)`
  并 `toast(e.message)`。`sendCmd` 约 1418 行的 `ok:false` 分支亦原样
  `pushFeed("敕令失败：" + data.error)`。
- `sendCmd` 只有空 command 守卫（`if (!c) return`），token 为空时仍发请求。
- 同型原样渲染遍布桌面端 `web/workbench.js`（`data.error` / `res.error` /
  `e.message` 直接进 feed / toast / 聊天泡 / 弹窗）。

真正需求：玩家在任何情况下都不应在界面上看到「需要 token 与 command」或其它
后端报错原文；无 token 时不发请求、给人话提示并引导重新登录；空指令的 UI
路径堵住；已知错误映射成人话，未知错误给通用兜底 + 原文只进 console/日志。

## 触发路径定位（NAS 日志实锤，2026-11-10 补充修正）

> 修正：初版按「刷新丢 token」推测的触发链已撤回。以下为总管据 NAS
> `server.log` 逐项查实的真正触发链，非推测。

Martinez 本人 2026-11-10 17:48 登录（qq601359558）时正好撞上世界 tick 410
持锁 67.8 秒（agenda 阶段 51.8 秒）。代码链：

1. 登录拿不到 2 秒有界锁 → `WORLD.join` → `_join_fallback` →
   `_live_fallback_snapshot` 返回 `{"token": None, "lock_fallback": True}`，
   HTTP 仍 200、`ok: true`（`server/world.py` 约 363–390 行；
   `_join_fallback` 约 393–426 行）。
2. 双端 `doAuth` 只判 `payload.ok`、不校验 token，直接 `showApp()` 进游戏
   （mobile.js 约 1600–1630 行；workbench.js 约 8830–8860 行）。
3. 他点「观照己身」（/look）→ POST `/action` 时 token 为空 →
   `server/app.py:561` 返回 400「需要 token 与 command」；前端 `api()`
   把 error 原文抛给玩家。NAS 日志佐证：17:48:31 登录返回、17:48:38
   `/action` 400。
4. 同型放大器：死者登录的锁外回退 `_dead_fallback_snapshot`
   （world.py 约 908–922 行）同样返回 token None + lock_fallback True，
   正常死者路径则会发 token（供 `/转世` 用）。故规则须统一：
   **任何登录/入世响应无非空 token，一律不得进游戏**（无论活角/死者）。
   ——变体核查结论（总管补充要求，2026-11-10）：该变体经核查**确实会产出
   无 token 的登录响应**，不是假设。证据：① 既有
   `tests/test_login_latency_fix.py` 持锁死者测试（HTTP 级）：持锁登录返回
   200、`dead` True、token None、`lock_fallback` True、
   `settlement_pending` True、`settled` False；② 本分支新增
   `tests/test_action_error_ux.py::test_login_dead_lock_fallback_snapshot_has_world_busy_code`
   （HTTP 级，持锁 POST /login）：同上 + `code` 为 `WORLD_BUSY`，松锁后
   再登录发 token 且不带该 code。实现上该变体与活角走同一校验：服务端
   `_dead_payload_dict` 仅 lock_fallback 路加 `code`，前端 `doAuth` 的
   token 校验是 payload 通用的（不分活角/死者），死者无 token 时同样留门
   并按忙回退自动重试一次（重试成功后死者带 token 进游戏，`/转世` 可用）。

tick 长占锁本身的根治不在本轮（在块一流水线里）；本轮只修
「占锁窗口里登录被无声放行成无 token 会话」这个放大器。

### token 生命周期（双端同构）

- 登录写入：`doAuth` 成功后 `state.token = payload.token` 并写
  `localStorage["wb.token"]`（mobile.js 约 1610 行；workbench.js 约 8836 行）。
- 刷新恢复：启动时 `state.token = localStorage.getItem("wb.token") || ""`
  （mobile.js 约 43 行；workbench.js 约 296 行）；`tryRestore` 用
  `api("/action", {token, command: "/look"})` 探活，失败则清 token 并
  `showGate("昔日会话已逝，请重新踏入大世界。")`（mobile.js 约 1749–1767 行；
  workbench.js 约 8960–8980 行）——恢复路径本身已是人话，无需新造。
- 失效清理：退出登录清 `wb.token`（mobile.js 约 1862 行；workbench.js 约 9050 行）；
  服务端重启后内存会话丢失，旧 token 调 `WORLD.handle` 返回 200
  `{"ok": false, "error": "会话无效"}`（`server/world.py` 约 1004/1037 行）或
  `会话无效，请用账号密匙重新 /login`（约 1204 行）。
- 缺口：① `doAuth` 不校验 token，无 token 的 200 ok:true 响应直接放行进游戏
  （主因，NAS 日志实锤）；② `sendCmd` 及各直调 `/action` 的调用点都不检查
  `state.token`；③ token 只在 `localStorage` 被清 / 另一标签页退出 /
  服务端重启失效时才变空或失效，界面不感知，照常发请求；④ `api()` 把后端
  `error` 原文包进 `Error` 后沿 `catch → toast/feed` 原样上屏。

### `/action` 调用点枚举（行号以 fed5332 实测为准）

| 位置 | 调用点 | 无 token / 空 command 时能否发出请求 |
|---|---|---|
| mobile.js:1372 | `chatSendM` 器灵灵语 `/灵语` | 能：只判 `state.chat.spirit`，不判 token |
| mobile.js:1404 | `sendCmd` 通用 | 能：仅 `if (!c) return`；token 空照发 |
| mobile.js:1550/1554 | `refreshAll` `/look` `/here` | 能（刷新探活；失败静默 catch，见残留） |
| mobile.js:1757 | `tryRestore` `/look` 探活 | 有意为之：会话探针，失败已用人话引导重登 |
| workbench.js:1352 | 灵鹤归巢 `/灵鹤 <dest>` | 能：无 `.catch`，失败直接成未处理 rejection |
| workbench.js:1449 | 灵鹤领取 `/灵鹤 领取` | 能：失败分支 `toast(res.error)` 原样 |
| workbench.js:2972 | 探险 `/探险 <target>` | 能：catch 用 `err.message` 作叙事 |
| workbench.js:5026/5052 | 穿戴/卸下 | 能：catch `toast("…神识受阻：" + err.message)` |
| workbench.js:5344 | 挖宝 `/挖宝 <1/2>` | 能：catch `errMsg = "挖宝神识受阻：" + err.message` |
| workbench.js:6580 | 挂断 `/挂断` | 已守卫：`state.token` 判空 + `.catch(()=>{})` |
| workbench.js:6849 | `syncOmenOnBoot` `/奇遇` | 能：`catch(()=>{})` 静默，但仍发无效请求 |
| workbench.js:8214 | `sendCmd` 通用 | 能：仅 `if (!c) return`；token 空照发 |
| workbench.js:8766/8771 | `refreshAll` `/look` `/here` | 已守卫：前置 `if (!state.token) return` |
| workbench.js:8970 | `tryRestore` `/look` 探活 | 有意为之：同 mobile tryRestore |
| workbench.js:9126 | 同场点人 `/交谈 <name>` | 能：catch `chatMsg("无法连通神识：" + err.message)` |

其余入口（命令输入框、快捷条、`data-cmd` 芯片、奇遇芯片、命格选择、`/go`、
`/钱包提取` 等）全部汇入双端 `sendCmd`，守卫 `sendCmd` 即覆盖。
空 command：唯一可达路径是命令输入框提交空/空白串（双端 `cmdForm` submit
直接调 `sendCmd(value)`；`sendCmd` 的 `if (!c) return` 已挡住，但触发点
本身无禁用/空态，属“发送层兜底”，需在触发点补禁用）。

### 复现（隔离服，勿连 NAS）

1. 起隔离服：`no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1`
   下用全新 `data/` 启动本 worktree 的 `server/`（或跑
   `tests/test_action_error_ux.py` 的 in-process 夹具）。
2. `curl -X POST 127.0.0.1:<port>/action -d '{"token":"","command":"/look"}'` →
   改动前 400 `{"ok": false, "error": "需要 token 与 command"}`（无 code）。
3. 浏览器复现（QA 用）：登录后清 `localStorage` 的 `wb.token`（或等服务端重启
   使 token 失效），再点任意操作按钮/输指令 → 改动前 feed/toast 出现
   「敕令失败：需要 token 与 command」（无 token）或「会话无效」（失效 token）。

## Design

体验层修复，不动 `/action` 的校验语义：空 token/command 仍 400，`error` 文案不变。

### 1. 服务端：只增 `code` 字段（决定：做）

- `/action` 400 分支：缺 token（含两者皆缺，token 先判）→
  `{"ok": false, "code": "AUTH_REQUIRED", "error": "需要 token 与 command"}`；
  有 token 缺 command → `{"ok": false, "code": "EMPTY_COMMAND", "error": "需要 token 与 command"}`。
- 状态码与 `error` 文案不变；500 分支已有 `code: "ACTION_FAILED"` 先例。
- 做 code 的理由：前端按 `error` 文本映射脆弱（文案一改即失配，且
  「需要 token 与 command」一句对应两种缺参）；code 让映射稳定、可测试，
  且与 `/login` 401 已有的 `AUTH_REQUIRED` 同名。代价极小（两行 + 契约测试）。
- `/chat` 缺 token 的 400 不动（范围外；前端映射兜底已覆盖其文本）。

### 1b. 服务端加固（登录回退快照带可区分标记，决定：做，只增字段，评审可 veto）

- `_live_fallback_snapshot`（world.py 约 363 行）与死者回退
  `_dead_fallback_snapshot`（经 `_dead_payload_dict`，仅 lock_fallback 路）
  增加 `"code": "WORLD_BUSY"`；正常发 token 的路径不带此键。
- 只增不改：既有字段语义、状态码、`ok` 值均不动；
  `test_login_latency_fix.py` 的回退快照断言（`.get()` 口径）不受影响。
- 取舍：前端识别无 token 回退本来就可凭 `!token && lock_fallback` 做到，
  code 只是让识别不依赖“缺字段”这种脆弱推断，且与 503 `SERVER_BUSY`
  同义、与 `/action` 的 `AUTH_REQUIRED` 区分开（忙 vs 未登录是两种
  处理：忙可重试，未登录须重登）。前端以 token 缺失为第一判据、code
  为第二判据，故即使评审 veto 这三行服务端改动，前端修复依然成立。
- 约束：CT-01 冻结计数（`tests/test_contract_audit.py`：服务端顶层键 174、
  三端读 137、未读 45、死键 8）——新 `code` 键不得以 `data.code` /
  `payload.code` / `res.code` / `j.code` 点记法出现在前端 JS 中，否则
  “死键”差集漂移变红。前端一律用括号记法（`x["code"]`）或非别名参数
  （helper 形参 `e` 的 `e.code`）读取；如将来确需点记法，须同步更新
  契约审计台账与 CT-01 计数。

### 1c. 根修在登录链（双端 `doAuth` 必须校验 token）

- `doAuth` 成功分支：`payload.ok === false` 或 `!payload.token` 时一律
  不进游戏（不 `showApp`、不写 `localStorage["wb.token"]`、不 `toast("已入世")`）。
- 无 token 时区分两种人话：
  - `payload["code"] === "WORLD_BUSY"` 或 `payload.lock_fallback` 为真 →
    「服务器正忙，正在重试…」，自动重试一次（3 秒后重调同一 `doAuth`，
    复用登录表单里已填的账号密匙，不新造会话机制；重试计数只活一次，
    用户再次点提交可再得一次重试机会）；
  - 重试后仍无 token → 「服务器正忙，请稍后再试，或点「踏入大千世界」重试」，
    留在登录门，提交按钮恢复可用。
  - 无 token 且非 lock_fallback（如服务端异常回包）→ 通用人话
    「入世受阻，请检查账号密匙后重试」，不进游戏。
- 死者登录同规则：死者回退快照 token 为空时也不进游戏（否则 `/转世` 无 token
  可用）；死者正常路径带 token 的，不受影响。

### 2. 前端：双端同构 `action-error-ux`  helper（各文件内联，沿用双端各自
### 复刻 helper 的既有惯例，不新建共享模块）

置于 `api()` 附近，`toast`/`showGate` 之后可用：

- `api()`：`!res.ok` 时把解析到的 `code` 挂到抛出的 `Error` 上
  （`err.code = j.code`，另存 `err.rawError = j.error` 供日志）；`message`
  仍为后端文本，但只作日志用途，不再直接上界面。
- `api()` 内集中守卫：`path` 为 `/action` 或 `/chat` 且 body 带 `token` 为空、
  且非 demo 模式时，不发请求，直接抛 `code === "AUTH_REQUIRED"` 的 Error。
  此为第二道防线，覆盖所有直调点；`tryRestore`/`refreshAll` 的会话探针
  不受影响（探针只在有 token 时调；无 token 时 `refreshAll` 已前置返回，
  `tryRestore` 已前置返回）。
- `humanizeActionError(err, fallback)`：入参为 Error（含 `.code`）、响应对象
  （含 `.code`/`.error`/`.message`）或字符串；code 优先，文本映射兜底。
  映射表：
  - `AUTH_REQUIRED` / 文本「需要 token」「需要 token 与 command」
    （无 token 时）/「需要 token 或账号与密匙」「会话无效」
    「会话无效，请用账号密匙重新 /login」「会话无效，请用账号密匙登录」
    → 「登录已失效，请重新登录」
  - `EMPTY_COMMAND` / 空指令 → 「指令为空，请重新输入」（防御性，UI 不应送达）
  - `ACTION_FAILED` / 「行动处理异常，请稍后重试。」→ 保持原文（已是人话）
  - `AUTH_FAILED` → 「账号或密匙有误」（已是人话）
  - 网络错误「无法感应阵枢灵脉（请确认服务已启动）」→ 保持原文（已是人话）
  - 未知 → `fallback`（各调用点给场景文案，如「操作失败，请重试」/
    「传音失败，请重试」/「入世受阻，请检查账号密匙后重试」），
    原文只 `console.error("[action-error]", raw)`。
- `isAuthError(err)`：code 为 `AUTH_REQUIRED` 或映射后文本为重登提示时为真。
- `requireActionToken()`：demo 放行；有 token 放行；否则
  `toast("登录已失效，请重新登录", "bad")` + `showGate("登录已失效，请重新登录")`
  并返回 false。复用既有登录/会话恢复路径（`showGate` + `doAuth`），不新造。

### 3. 调用点改动

- 双端 `sendCmd`：空 command 守卫保留；其后加 `requireActionToken()` 守卫，
  失败返回 `{ok: false, code: "AUTH_REQUIRED"}`；`ok:false` 分支与 `catch`
  分支一律 `humanizeActionError`，auth 错误时另调 `showGate` 引导重登。
- 双端 `doAuth`：`ok:false` 的 `throw new Error(payload.error)` 改为
  `humanizeActionError(payload, "入世受阻，请检查账号密匙后重试")`；
  catch 里 `gateMsg`/`toast` 同样走映射（`payload.error` 不再原样上屏）；
  另按 §1c，`!payload.token` 时不进游戏（忙则自动重试一次）。
- 空指令触发点堵住：双端 `cmdForm` submit 处理先判空直接返回；输入框
  `input` 事件同步切换发送按钮 `cmdGo.disabled = !value.trim()`
  （mobile.html:138 / index.html:307 的 `#cmdGo`；CSS 预算不动，沿用浏览器
  默认 disabled 样式，不新增样式规则）。程序写值点（联想补全 `applySug`、
  `data-fill` 填入、寄售/聚焦预填）须同步调 `syncCmdGoDisabled()`，
  否则按钮会在有内容时仍禁用；`busy()` 切换后亦同步（空输入时保持禁用）。
  `sendCmd` 的 `if (!c) return` 作为最后一道保留。
- 交谈：mobile `routeChatDataM` / `openChatWithM` / `chatSendM`（含 catch）
  与 workbench `sendChat` / `handleChatData`（`data.text || data.error`
  改为 `data.text || humanizeActionError(data)`）一律走映射；
  `chatSendM`/`openChatWithM` 入口加 `requireActionToken()`。
- 诊断卡 `cpAi`（双端）：`a.error || "未就绪"` 改为固定「未就绪」，
  原文只进 `console.warn`（诊断卡亦属玩家可见界面，不例外）。
- 桌面直调点逐项处置（见实现报告清扫清单）：灵鹤归巢补 `.catch` + `ok:false`
  无文本时人话 toast；灵鹤领取 / 穿戴 / 卸下 / 挖宝 / 探险的 catch 与
  `res.error` 分支走映射；渡劫弹窗 `data.error || data.text` 改为
  `data.text` 优先、否则映射；`syncOmenOnBoot` 加无 token 早退；同场点人
  catch 走映射；`/挂断` 与 `refreshAll` 已守卫，不动；`tryRestore` 探针不动。

### 4. 预算

- mobile.js 现行 1969 行（任务书称约 1777 行，实测 fed5332 已 1969 行；
  豁免上限 2100 行）——本次实测终态 2083 行，净增 +114 行，在预算内（余 17 行）。
- mobile.css 约 31324B；上限为 chat-structure D2 豁免后的 32000B
  （任务书所引 29200B 为 D1 旧上限，已过期），本次零 CSS 改动，不新增规则。
- workbench.js 无行数预算记录，本次实测净增 +125 行（`git diff --numstat` 终态：+149/−24），增量合理，不构成超限。

## Out of Scope

- `/action` 校验语义、状态码、`error` 文案：不动。
- CLI（`server/client.py`）行为：不动。
- 数值/玩法规则、`WORLD.handle` 的 `ok:false` 文案：不动（只映射呈现层）。
- `/chat` 服务端缺参 code：不动。
- `data.text` 叙事文本：属服务端设计的玩家可见叙事，不当作“后端报错原文”处理。
- `refreshAll`/`tryRestore` 的会话探针：保留，其失败路径已是人话。
- 真机截图验收：由 QA 岗做（复现方法见上）。

## 验收任务列表

1. `POST /action` 缺 token → 400 + `code: "AUTH_REQUIRED"`，`error` 文案不变。
2. `POST /action` 有 token 缺 command → 400 + `code: "EMPTY_COMMAND"`，`error` 文案不变。
3. `POST /action` 两者皆缺 → 400 + `code: "AUTH_REQUIRED"`。
4. 登录回退快照（活角 `_live_fallback_snapshot` 与死者
   `_dead_fallback_snapshot`）带 `"code": "WORLD_BUSY"`，只增字段；
   正常发 token 路径不带此键。死者变体 HTTP 级已验证确实产出无 token
   响应（见上“变体核查结论”）。
5. 双端 `doAuth`：token 为空的登录响应不得进游戏（不 `showApp`、不写
   `wb.token`）；忙回退时人话提示并自动重试一次，重试仍无 token 则留门
   待用户手动重试；契约测试锁定此回归点。
6. 双端 `sendCmd` 无 token 时不发请求（`api()` 守卫 + `sendCmd` 守卫双重），
   界面出现「登录已失效，请重新登录」并回到登录门（`showGate`）。
7. 双端命令输入框空串时发送按钮禁用、提交不发请求；`sendCmd("")` 仍静默返回。
8. 已知错误（会话失效/未登录/空指令）映射成人话；未知错误显示场景通用兜底，
   后端原文只出现在 console/日志，不出现在 feed/toast/聊天泡/弹窗。
9. `grep` 清扫：双端不再有 `data.error` / `res.error` / `e.message`
   原样渲染到界面的位置（`api()` 内提取与 `console` 日志除外）。
10. `node --check` 双端 JS 语法通过；新增 `tests/test_action_error_ux.py`
   全绿；全量回归新鲜 DB 口径无新增失败（对照基线）。
