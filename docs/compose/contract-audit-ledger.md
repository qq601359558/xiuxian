# 前后端数据口径全量核查台账（contract-audit）

- 基线：worktree `.worktrees/contract-audit`，分支 `feat/contract-audit`，基线提交 `cfcc878`（main `af4d689` = v0.3.11-gray.18）。
- Spec：`docs/compose/spec/contract-audit.md`（§0–§12；冲突时以 Spec 为准）。
- 台账状态：**初稿**（K2：先于任何 P0/P1 修复提交；本岗只审计不修）。
- 抓取证据：`docs/compose/contract-audit-captures/`（261 个真实响应文件 + `index.json` 清单；抓取脚本 `scripts/contract_audit_capture.py`，新鲜 DB 可重跑；随机种子 20261108）。
- 服务端静态清册：`docs/compose/contract-audit-server-census.md`（189 分支逐分支 + `_status_dict` 77 键 + 非命令出口）。

## 统计摘要

| 面 | 行数 | 不一致 | 前端兜底捏造 | 格式问题 | 一致 | P0 | P1 | P2 | P3 | P4 |
|---|---|---|---|---|---|---|---|---|---|---|
| A · 桌面 workbench.js | 35 | 22 | 1 | 2 | 10 | 4 | 1 | 10 | 10 | 10 |
| B · 移动 mobile.js | 8 | 2 | 0 | 0 | 6 | 0 | 0 | 1 | 1 | 6 |
| C · 遗留 app.js | 7 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 7 |
| D · CLI | 7 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 7 |
| E · 状态/入局 payload | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 6 |
| F · 只读呈现面 | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 3 |
| G · Demo 本地捏造 | 4 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 4 |
| **合计** | **70** | **24** | **1** | **2** | **43** | **4** | **1** | **11** | **11** | **43** |

注：CA-006（merit/sin 缺省捏造数）计入「前端兜底捏造」列；CA-004（静态捏造）是另一类捏造，结论记为「不一致」（静态值无服务端来源，见行内说明）。P0 共 4 项（CA-001~CA-004），其中 CA-002 已有预批处置（§6.1 只增 `stone_loss`），CA-001/CA-003/CA-004 待修复岗。标红停手项：**0 条**（见末尾「标红清单」节）。

## 方法学（§2.1/§2.2/§2.6 落点）

- **别名清册先行**：见附录 A。响应对象别名：`res`/`data`/`payload`/`j`/`b`（已解析 JSON）/`r`（移动端）；状态对象别名：`st`（`applyStatus(st)` 入参）、`s`（`= state.status`）、`dg`（`= state.status?.dungeon`）、`stW`（移动端）；`res.status` 在 `api()` 层是 fetch Response（`status/statusText`）还是游戏响应，须按调用点区分——本台账凡称 `res.status` 皆指游戏响应 `status` 键，已逐点核对。
- **grep 模式命中**（三文件全量跑，0 命中的模式已注明）：G1 响应顶层键读：workbench 66 / app.js 73 / mobile 41（去重后 distinct，含嵌套行对象读——已逐键核对接收者是否为响应本体，嵌套读不计死键）；G2 状态键读：workbench 50 / app.js 35 / mobile 44；G3 模板插值：workbench 791 / app.js 73 / mobile 0（移动端用字符串拼接，无模板字面量）；G4 通用渲染：workbench 3 处（:878/:4516/:5550）、app.js 1 处（:100）、mobile 1 处（:1045）；G5 `?.`：workbench 17；G6 数值格式化：`toFixed` workbench 2 / mobile 2 / app.js 4、`toLocaleString` 12（workbench 时间类）；G7 `state.demo`（严格匹配）：workbench 48 / app.js **0** / mobile 10（早期宽松统计把 `heart_demon` 里的 `demo` 子串误计为 app.js 5 处，已纠正）；G8 写死中文 stat 键：workbench 4 处命中皆为 `treasurePanelStatLine` 的标签表（合法映射表，非 `stats['中文键']` 读法）；G9 仪式：workbench ceremony 26 / ceremony_next 9 / result_ref 3；G10 入局/出身/图鉴/奇遇：见各面行；G11 CLI：`render_*` 20 个函数，`res.get`/`result.get`/`char.*` 71 处。
- **分组规则**：一行 = 一个文件 × 一条键路径（同一键路径多处同结论的行合并，行内列出行号区间与处数）；服务端来源按「端点 × 分支」登记，不按键名合行（§2.3）。
- **证据约定**：`captures/<file>` = `docs/compose/contract-audit-captures/<file>`；`静态` = 代码位置 + 既有测试名（无抓取时）；`—` = 该字段无值并注明原因。
- **双向差集结论**（§2.6-1）：服务端顶层响应键 110 个 vs 三端引用键——前端读、服务端从不下发的**顶层**键只剩本台账已登记的死键（CA-007/008/009/010/011/012/036 及其嵌套澄清）；其余候选经逐点核对皆为嵌套行对象读（`/here` 行、ceremony beat、origin.relations、boon、sweep 行、shadow 条目等），已在各行写明。服务端下发、前端从不读的键见「未消费键清单」（附录 B）。
- **分支覆盖**（§2.6-2）：189/189 分支有真实响应抓取或真实崩溃记录（261 抓取 + 4 崩溃，同一根因）；子结局未覆盖见末尾「未覆盖端点清单」（分支级为 0，子结局级 5 项）。

## 面 A · 桌面（web/workbench.js，7898 行）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-001 | workbench.js sendCmd 通用路径（经 `/action`） | `/悟丹`、`/悟器`、`/生成丹药`、`/生成法宝` 四命令的响应整体 | `server/world.py:2667` `/悟丹`、`/悟器`、`/forge`、`/天工`合一分支；`:2716` 本地回退 `recipe = random.choice(cand)` | 不一致 | P0 | 修复 | 抓取失败记录 `index.json` failures（4 条同根因）；静态 `server/world.py:2716`；`random` 在模块顶层已 `import`（:11），但 `handle()` 内另有两处 `import random`（:3783、:4066），使 `random` 在整个 `handle` 作用域内成为局部变量——执行到 :2716 时尚未绑定即抛 `UnboundLocalError`，`handle` 直接 raise；`/action` 层捕获后返回 HTTP 500 `{ok: false, code: "ACTION_FAILED", error: "行动处理异常，请稍后重试。"}`（`server/app.py:558-590`），前端收不到任何业务响应。`/生成丹药`、`/生成法宝`（:2733、:2736）转调 `handle('/悟丹 …')`、`/悟器 …'` 同路崩溃。离线/AI 关时本地回退必走此路，即该命令在当前配置下**恒崩溃**。修复方向：把 `import random` 移出 `handle` 或在分支内先绑定（修复岗定夺；不改数值语义——恢复既有设计意图的本地抽配方） |
| CA-002 | workbench.js 宝图面板石数行（:5245 `if (res.stone_gain)` 取值；面板渲染「发掘灵石 +N」） | `res.stone_gain`（brute_force 分支） | `/挖宝` 分发 `server/world.py:2246`：`"stone_gain": res.get("stone_gain", 0)`；引擎 `core/treasure_system.py:547-549`：`loss_stones = 40`，`c.spirit_stones -= 40`，但 brute_force 返回 dict **无 `stone_gain` 键**（§6.1/F2） | 不一致 | P0 | 修复（§6.1 已批：服务端只增 `stone_loss`，分发层只透传引擎值；前端扣款 >0 显「灵石 −40」，=0 整行省略，不得再以 `stone_gain === 0` 推断无扣款） | `captures/102-dig-brute-force.json`：`stone_gain = 0`，文本「受反震损耗灵石 40」， harness 实测随身灵石 100000 → 99960（−40）；对照 `101-dig-element-clever.json`（`stone_gain = 360` = 文本「灵石 +360」）、`103-dig-scar-created.json`（800 = 文本 +800）、`104-dig-combat.json`（500 = 文本 +500）。扣款行 `core/treasure_system.py:547-549` |
| CA-003 | workbench.js 宝图结算面板（`#treasureStageBox` 内结算 HTML，:5330 起） | `res.equipment`（遗物 `纯阳离火印`）、`res.stone_gain`（800）、`res.ceremony`（loot 幕） | `/挖宝` 分发 `:2206`、`:2236-2246`；引擎 scar_created `core/treasure_system.py:683-708`；`loot_ceremony_candidate`（relic tier≥3 达幕） | 不一致 | P0 | 修复（§6.2②：修面限于面板/仪式叠演顺序，不得改结算本体） | `captures/103-dig-scar-created.json`：scar_created 真实响应含 `ceremony`（kind `loot`，3 beats，`result_ref` 含遗物名/kind/tier）+ `equipment`（relic，`stats: {}`）+ `stone_gain: 800`。复现链（静态 + 真实响应）：① 挖宝流在宝图 dialog 内（`openJadeDialog`，`#treasureStageBox`）调 `/挖宝`；② `:5236` `res.ceremony` 交 `maybeShowCeremonyQueue`；③ `openJadeDialog` 首行即 `closeJadeDialog()`（:1075，单 overlay、无栈）——得宝幕弹出即**移除**宝图 dialog；④ 结算 HTML 随后写入已 detached 的 `boxEl`，永不重现；⑤ `closeCeremonyDialog`（:902）只关幕 + 演 `ceremony_next`，不恢复宝图 dialog。关闭得宝幕后结算面板**不可达**（遗物行、800 石数行皆不可见；遗物仅在得宝幕 `result_ref` 灰字行与 feed 文本、纳戒中可见）。结论：**复现证实不可达 → 修**。移动端无宝图结算面板（CA-040），盲匣流 `:6129` 注释已明言此单例语义 |
| CA-004 | workbench.js 洞府（sanctum，默认视图）命盘左栏 `renderSanctum`（:2079 起） | 写死展示值：`神识感召 4,850步`（:2410）、`宗门道勋 太上长老`（:2411）、`九天碧玉太虚剑` / `剑灵觉醒：太虚玄青雀` / `锋芒 9,880`（:2425-2431） | 服务端从不下发（全仓无此三值来源；`_status_dict` 有真实 `rank`、`equipped`、`art_images` 可用而未用） | 不一致 | P0 | 修复（去掉静态捏造，改读真实 `status.rank` / `status.equipped` / 器灵数据；若产品定性为装饰占位，须改为不带数值/品阶断言的文案并经总管确认——修复岗不得自行把占位写成数值） | 静态 `web/workbench.js:2410-2411, 2425-2431`（`renderSanctum`，live 视图，非 demo 门内）；`_status_dict` 快照 `captures/253-status-snapshot.json`（`rank`、`equipped`、`art_images` 皆在场）。按 §2.3 定义「联机捏造」= P0 |
| CA-005 | workbench.js 寿元两处：罗盘（:2191）与命盘格（:2409） | `status.rem_years` | `_status_dict`：`round(lifespan.get_remaining_years(), 2)`（唯一口径，2 位小数） | 格式问题 | P2 | 修复（统一定死：正常值 `toFixed(1)` + 单位「载」；缺失显「—」，不得用 100/145 等假缺省——见「口径裁决」） | 静态：`:2191` `Number(s.rem_years \|\| 100).toFixed(1)` vs `:2409` `Number(s.rem_years \|\| 145).toFixed(0)`——同一字段两处缺省值不同（100 vs 145）、小数位不同（1 vs 0）。服务端恒下发该键，缺省平时不触发，但口径已分叉 |
| CA-006 | workbench.js 命盘功德/业力格（:2403-2406） | `status.merit`、`status.sin` | `_status_dict`：`merit`、`sin` 恒下发（快照证实） | 前端兜底捏造 | P3 | 修复（缺省改显「—」，删 3650/120 假数） | 静态：`+${s.merit \|\| 3650}`、`-${s.sin \|\| 120}`。服务端恒下发，平时不触发；一旦缺失即显示捏造数。移动端同类位置用 `!= null` 判空（mobile.js:382 系），桌面应同口径 |
| CA-007 | workbench.js 探险结果分支（:2861-2866） | `res.adventure.combat_success` / `.exp_delta` / `.stones_delta` / `.narrative` / `.loot` | `/探险` 分发 `server/world.py:2615`：全部返回只含 `{ok, text, error, status}`，从不下发 `adventure` 键 | 不一致 | P3 | 修复（删前端结构分支，走既有 else 路 `isWin = !!res.ok` + `res.text`；按 §4 服务端是真相，不得要求服务端补 `adventure` 键） | `captures/151-adventure.json`：顶层键仅 `ok/text`（无 `status`，见 CA-016）。静态 `server/world.py:2615-2647` 全部分支返回无 `adventure`。安全 else 兜底，无可见异常 |
| CA-008 | workbench.js 突破 fallback  dialog（:6772-6774，仅 `!data.ceremony && !data.ceremony_next` 时） | `data.tribulation.fatal` / `data.tribulation.new_realm` / `data.new_realm` | `_breakthrough`（`server/world.py:5322-5417`）返回 `{ok, text, success, fatal, death, status, legacy, sweep, death_cause, ceremony, ceremony_next}`，无 `tribulation`、`new_realm` 键（`tribulation{success,fatal,new_realm}` 只由心魔前置路径 :1280 下发，不走此 handler） | 不一致 | P3 | 修复（删死键读，`newR` 只取 `status.realm`） | `captures/118-breakthrough.json`：顶层键无 `tribulation`/`new_realm`。安全 fallback（`status.realm` 兜底），无可见异常 |
| CA-009 | workbench.js 登录后处理（:7394） | `payload.entry_pending` | join payload（`_join_locked` :587 + snap）从不下发 `entry_pending`（抓取 `001-join.json` 键表证实） | 不一致 | P3 | 修复（删该读与 `setView` 入口条件中的 `state.entryPending` 分支，或服务端补键须回主策岗裁决——X4） | `captures/001-join.json`；静态 `web/workbench.js:7394`（`!== undefined` 守卫，永不触发）。同型见移动端 CA-036 |
| CA-010 | workbench.js 挖宝/寻宝定位（:5492） | `state.status.current_node` | `_status_dict` 只有 `location`，无 `current_node` | 不一致 | P3 | 修复（删 `current_node` 候选，只读 `location`） | 静态 `web/workbench.js:5492`（`location \|\| current_node`，后者永假）。`_status_dict` 77 键清册见服务端清册 §3 |
| CA-011 | workbench.js 洞府功法图（:2154） | `s.custom_arts[].name` | `_status_dict` 无 `custom_arts` 键（`arts: {main, sub}` 只含主修/辅修；自创功法只在 `c.custom_arts` 模型字段与 `/功法` 文本中） | 不一致 | P3 | 待裁决（回主策岗：要么 `_status_dict` 补 `custom_arts` 键——新增响应键须 X4 裁决；要么前端改读 `/功法` 的 `arts` 返回。**不得顺手加键**。注释称「art_images 覆盖 skills+custom_arts」——`art_images` 确以功法名为键含自创功法图，但 `artNames` 缺名故不出 chip，自创功法在洞府功法行无图） | 静态 `web/workbench.js:2153-2154`；`server/world.py:4765`（`art_images` 以 `c.custom_arts` 建键）、`:4900`（`arts: {main, sub}`）；`captures/253-status-snapshot.json`（无 `custom_arts`） |
| CA-012 | workbench.js 入局戏剧行（:933-934、:998、:6314 `dramaRowHtml`） | `pv.drama_id`（entry.proactive / entry.queue 项） | `build_entry`（`core/briefing.py:57`）：queue 项形如 `{kind, priority, title, text, ref_id, target, options?}`，`proactive` 形如 `{text, npc}`——皆无 `drama_id` 键（戏剧 id 在 `ref_id`） | 不一致 | P3 | 修复（删 `drama_id` 快捷分支；戏剧行走通用 queue 路 `:964` `item.kind === "drama"` + `item.options`，已验证可用） | 静态 `core/briefing.py:413-430`（`_item("drama", …)` + `options`）、`web/workbench.js:964`（通用渲染读 `ref_id`/`options`）。安全守卫（`!pv.drama_id` 即返空串），无可见异常 |
| CA-013 | workbench.js 地牢战斗负面状态行（:4516-4524） | `m.status_effects` 未知键（`poison` / `weaken` / `bleed`） | `core/spells.py:18-25` `DEBUFF_NAMES` 共 7 键：`burn/freeze/chill/poison/weaken/bleed/stun`（`stun` 由 `:416` 置入）；怪物 `status_effects` 可含其中任意键 | 格式问题 | P2 | 修复（未知 effect 通用渲染——如 `DEBUFF_NAMES[k] || k` + 回合数，不得只判空；或补齐三枚 chip） | 静态 `web/workbench.js:4516`（`Object.keys(m.status_effects \|\| {}).length === 0 ? '无异常'`）+ 仅 `burn/freeze/chill/stun` 四枚 chip。怪物仅带 `poison/weaken/bleed` 时：长度 >0（不显「无异常」）但无 chip，渲染一行空白「负面因果:」 |
| CA-014 | workbench.js HUD 状态区（sendCmd：`if (data.status) applyStatus(...)`，无 status 即保留旧值） | `status.*`（`/卸下` 后） | `/unequip` 分发 `server/world.py:2324`：返回 `{ok, text, error}`，**不透传 status** | 不一致 | P2 | 修复（分发层透传 `status`——服务端是真相、前端不补调；或 sendCmd 对写分支补一次 `/look` 刷新，修复岗定夺） | `captures/113-equip-remove.json`：`ok: true`，顶层键 `ok/text`，无 `status`。卸下后 HUD 装备/战力陈旧，直至下一次带 status 的响应 |
| CA-015 | 同上（HUD 状态区） | `status.*`（`/上拍` 后） | `/auction_list` 分发 `:4320`：返回 `{ok, text, error}`，不透传 status | 不一致 | P2 | 修复（同 CA-014） | `captures/121-auction-list.json`：`ok: true`，无 `status` |
| CA-016 | 同上（HUD 状态区） | `status.*`（`/探险` 后） | `/adventure` 分发 `:2615`：返回 `{ok, text, error}`，不透传 status（另见 CA-007） | 不一致 | P2 | 修复（同 CA-014） | `captures/151-adventure.json`：`ok: true`，顶层键 `ok/text`，无 `status` |
| CA-017 | 同上（HUD 状态区） | `status.*`（`/自创功法` 后） | `/create_art` 分发 `:4389`：返回 `{ok, text, art, error}`，不透传 status | 不一致 | P2 | 修复（同 CA-014） | `captures/156-create-art.json`：`ok: true`，无 `status`。自创功法写入 `c.custom_arts`，但 status 不同步，洞府功法行（CA-011）亦不同步 |
| CA-018 | 同上（HUD 状态区） | `status.*`（`/采药` 后） | `/草园`、`/herbs` 分发 `:3702`：成功返回不透传 status（抓取实测） | 不一致 | P2 | 修复（同 CA-014） | `captures/157-herbs.json`：`ok: true`，无 `status` |
| CA-019 | 同上（HUD 状态区） | `status.*`（`/汲取` 后） | `/灵泉` 分发 `:3683`：成功返回不透传 status（抓取实测） | 不一致 | P2 | 修复（同 CA-014） | `captures/159-spring.json`：`ok: true`，无 `status` |
| CA-020 | 同上（HUD 状态区） | `status.*`（`/探路` 后） | `/灵鹤` 分发 `:3727`：成功返回不透传 status（抓取实测） | 不一致 | P2 | 修复（同 CA-014） | `captures/160-crane.json`：`ok: true`，无 `status` |
| CA-021 | 同上（HUD 状态区） | `status.*`（`/出售` 后） | `/sell` 分发 `:3641`：成功返回 `{ok, text}`，不透传 status | 不一致 | P2 | 修复（同 CA-014） | `captures/257-sell-success.json`：`ok: true`，顶层键 `ok/text`，无 `status`。对照：`/买寄售` 成功返回带 `status`（`261-buy-listing-success.json`），同类写分支口径分叉 |
| CA-022 | workbench.js `/help`（经 `/action`） | `/help` 分支整体 | `server/world.py:4435` 第二个 `/help`、`/帮助`、`/指令` 分支，与 `:1938` 别名集合完全相同、无守卫，elif 链先到先得故**不可达**（死分支） | 不一致 | P3 | 定性不修（死分支零行为影响；删除属清理，另立轮次，本轮不动） | 静态 `server/world.py:1938` vs `:4435`；`captures/247-alias-help.json`（`/help` 走 :1938，`commands` 键在场） |
| CA-023 | workbench.js `/omen`（经 `/action`；目录亦展示） | `/omen` 的路由归属 | 分发 `:1959`（`/omen`、`/天象` → 纪元天象）先于 `:2058`（`/omen`、`/奇遇` → 奇遇场景）；目录 `core/command_catalog.py:76` 称 `/omen` 是 `/奇遇` 的别名 | 不一致 | P1 | 修复（分发与目录二选一对齐：要么把 `:1959` 的 `/omen` 移到 `:2058`，要么改目录。**路由改动牵连 `/天象` 的既有行为**，修复岗须先与总管确认取向，不得自行改目录或分发） | `captures/244-alias-omen.json`：`/omen` 返回天象文本（`season_theme` 键），非奇遇；`captures/221-omen-scene-start.json`（`/奇遇` 返回 `omen_image/omen_inline/omen_open`）。静态 `core/command_catalog.py:76` |
| CA-024 | workbench.js `/天象`（经 `/action`） | `/天象` 的路由归属 | 分发 `:1959`（天象）先于 `:3065`（`/望气`、`/echo`、`/天象` → 望气），`:3065` 的 `/天象` 别名项死亡 | 不一致 | P3 | 定性不修（`/天象` 本体功能正常——:1959 即天象 handler；死别名项随 :3065 分支清理时一并处理） | `captures/245-alias-tianxiang.json`（`/天象` 返回 `season_theme`，功能正常） |
| CA-025 | workbench.js `/release`（经 `/action`） | `/release` 的路由归属 | 分发 `:2375`（`/放生`、`/release` → 灵宠放生）先于 `:3570`（`/释放`、`/release` → 释放被擒）；目录未载 `/放生`、`/释放` 无英文别名（`core/command_catalog.py:159` 仅 `/释放` 本体） | 不一致 | P3 | 修复（目录补 `/放生` 词条并注明 `/release` 归属，或给 `/释放` 另设别名；路由本身不动——`/释放` 中文可用，`/release` 现指灵宠放生是既有行为） | `captures/246-alias-release.json`：`/release` 返回「用法：/放生 <宠名>」。静态 `server/world.py:2375` vs `:3570` |
| CA-026 | workbench.js `/接令`（经 `/action`） | `/接令` 的路由归属 | 分发 `:3126` 带守卫 `and not _is_bounty_claim`（非数字 → 除凶接令），`:3887`（数字编号 → 悬赏接令）——有意消歧 | 一致 | P4 | — | `captures/242-claim-bounty-numeric.json`（`/接令 1` → 「告示编号不存在」，:3887）、`243-accept-hunt-name.json`（`/接令 不存在的道号` → 「未寻得」，:3126） |
| CA-027 | workbench.js `/trade`（经 `/action`） | `/trade`、`/交易` 的路由归属 | 分发 `:4222` 带守卫 `len(parts) >= 2`（带参发起），`:4229`（无参查进行中交易）——有意分流 | 一致 | P4 | — | `captures/248-trade-bare.json`（无参 → 「当前无进行中的当面交易」）、`249-trade-with-arg.json`（带参 → 「当面交易须同地」） |
| CA-028 | workbench.js 仪式呈现（:859-892 `maybeShowCeremony`） | `ceremony.beats[].stage/asset_key/choices/text`、`ceremony.result_ref` | `core/ceremony.py`：beats 恒含 `stage/text/asset_key/choices`（:220-234、:402-432 等）；`result_ref` 为标量映射 | 一致 | P4 | — | `captures/103-dig-scar-created.json`（loot 幕 3 beats + `result_ref{uid,name,kind,tier,tier_name,slot,source,affixes_text}`）；通用渲染按 §2.4：`Object.entries(result_ref).filter(v != null && typeof v !== 'object')`，未知键原样呈现、对象值省略——合格 |
| CA-029 | workbench.js 宝图面板 stat 行（:374-393 `treasurePanelStatLine`） | `equipment.stats`（`power/defense/phys_atk/spell_atk/...`） | `core/items.py:150-152`（weapon 恒 `{power: N}`，armor/trinket 另含 `defense`）；遗物 `stats: {}`（`core/treasure_system.py:683-698`） | 一致 | P4 | — | v0.3.11 契约延续（`tests/test_treasure_panel_stats_contract.py`）；抓取 `101/102/103/104-dig-*.json`（`power` 或 `{}`）。优先序取首个 >0 数值键，2 位小数截断（`Math.round(v*100)/100`），无可用键整行省略，永不 undefined/NaN |
| CA-030 | workbench.js 纳戒检视器（:5550） | `sel.stats`（`Object.entries`） | 同 CA-029（装备 `stats` 恒为 `{power[, defense]}` 或 `{}`） | 一致 | P4 | — | 静态 `:5550`：`Object.entries(sel.stats \|\| {}).map(([k,v]) => …${esc(k)}…+${v})`——未知键原样呈现键名，不经标签表，无 undefined；§2.4 合格 |
| CA-031 | workbench.js 奇遇条（:6651-6663 `applyOmenPayload`） | `data.omen_ended` / `data.omen_inline` / `data.omen_choices[].id/label` / `data.omen_title` / `data.omen_image` | `/挖宝` 下发 `omen_inline/title/choices`（无 `omen_image`，前端以 `""` 处理）；`/奇遇` 下发 `omen_image/omen_inline/omen_open`；`omen_ended` 由 `:2075`、`:2099`、`:2156`（奇遇推进/终局）下发 | 一致 | P4 | — | `captures/101-dig-element-clever.json`（`omen_choices: [{id,label}×3]`、`omen_title: 客栈夜话`）、`221-omen-scene-start.json`（`omen_image: ""`，空串无图不崩）。`omen_choices` 逐项判 `id != null`，缺失即空条 |
| CA-032 | workbench.js 入局/出身/图鉴/命途只读面（:618-660、:754、:2148-2156、:6311） | `entry.lines.fate/chains/relations`、`entry.queue[].kind/options/ref_id`、`entry.proactive{text,npc}`、`origin_card.just_created`、`origin.relations[].npc_name/role/init_value/vendetta/vendetta_for`、`status.gallery{count,total,title}`、`status.fate{boons,pending,power_bonus}`、`status.relations_recent[].delta/after_cn/summary` | `build_entry`（`core/briefing.py:460-478`）；`origin` 模型（`core/origin.py:281-309`，relations 含 `vendetta/vendetta_for`）；`gallery.summary`（`core/gallery.py`）；`relations_recent_and_marks`（`core/relations.py:57-78`，项含 `delta/after_cn/summary/npc_name`）；`_fate_block`（`server/world.py:4802-4809`） | 一致 | P4 | — | `captures/001-join.json`（`entry`、`origin_card`）、`253-status-snapshot.json`（`gallery{count:19,total:139}`、`fate`、`origin.relations`）。`entry` 缺失时前端降级（setView 回退洞府，:7399） |
| CA-033 | workbench.js 同场/关系行（:6328-6344、:838-846） | `/here` 行：`attitude_cn/blood_marked/is_npc/personality/rank/sect`；`relations_marks[].delta` | `core/here.py:52-96`（行含 `id/name/realm/is_npc/sect/rank/blood_marked/avatar/attitude_cn/personality/agenda…`）；`relations_marks`（`core/relations.py:75-77`，`{delta, ts}`） | 一致 | P4 | — | `captures/098-here-after-go.json`（文本含 NPC 行）；静态 `core/here.py:70-84`（`attitude_cn` 由 `ATTITUDE_LABELS` 映射，恒有值） |
| CA-034 | workbench.js 错误提示（:442） | `j.message`（`j.error \|\| j.message \|\| msg`） | 服务端错误形恒为 `{ok: false, error}`，从不下发 `message` | 一致 | P4 | 定性不修（兜底链无害，`message` 永假；记录备查） | 静态 `:442`；全部抓取 error 响应皆 `{ok, error}`（如 `212-invalid-token.json`） |
| CA-035 | workbench.js 首挖奇遇条遮挡页脚（F9） | — | 既有报告「遮挡约 25px」，本轮**未实测量测**（无真机/截图） | 一致 | P4 | 记账不修（§11-3 Out of Scope；审计未复现——子代理无 live browser，本项须真机截图复核后另立行） | 相关机制在场：`/挖宝` 透传 `omen_inline/title/choices`（:2246），桌面 omen bar `:6597-6623` |

## 面 B · 移动（web/mobile.js，1645 行）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-036 | mobile.js 登录后处理（:1312） | `payload.entry_pending` | 同 CA-009：join 从不下发 | 不一致 | P3 | 修复（同 CA-009，删读） | `captures/001-join.json`；静态 `web/mobile.js:1312`（`!== undefined` 守卫） |
| CA-037 | mobile.js HUD 状态区（sendCmdM：`if (data.status) applyStatus(...)`） | `status.*`（写分支后） | 同 CA-014~CA-021 的 8 个写分支（`/卸下`、`/上拍`、`/探险`、`/自创功法`、`/采药`、`/汲取`、`/探路`、`/出售`）皆不透传 status；移动端 `refreshAll`（:1238）只在切页（:851）、回单（:1334、:1457）、可见性恢复（:1633）时触发，不补 sendCmd | 不一致 | P2 | 修复（同 CA-014，服务端透传为默认方向；移动端修复须在硬线内原地改，见 CA-043） | 抓取同 CA-014~CA-021；静态 `web/mobile.js:1107-1130`（sendCmdM） |
| CA-038 | mobile.js 仪式全屏卡（:1033-1060 `maybeShowCeremonyM`） | `ceremony.beats[]`、`ceremony.result_ref`、`ceremony_next` | 同 CA-028（`core/ceremony.py`） | 一致 | P4 | — | `captures/103-dig-scar-created.json`；静态 `:1045` `Object.keys(cer.result_ref)`（§2.4：只读键名，未知键不经标签表） |
| CA-039 | mobile.js 寿元两处（:236、:382） | `status.rem_years` | `_status_dict`（2 位小数） | 一致 | P4 | — | 静态：两处皆 `!= null ? Number(...).toFixed(1) : "—"`，口径统一（与桌面 CA-005 分叉对照：移动端已是正确口径） |
| CA-040 | mobile.js 挖宝流（:623-625 仅入口 chip + 通用 sendCmd） | （无宝图结算面板） | `/挖宝` 响应经通用 sendCmd：feed 文本 + 得宝幕，无专用结算面板 | 一致 | P4 | — | §6.2 遗物面板问题**不适用移动端**（移动端无此消费面；SC-03 以本行注明）。静态 `web/mobile.js:623`、`1107-1130` |
| CA-041 | mobile.js 状态读取面（全文件 `st.*`） | `status_cn/karma_chains/max_bag_slots/past_life/art_images/dao_heart/lifespan_warning/sect_contribution/spells_catalog` 等 44 键 | `_status_dict` 77 键全含（见服务端清册 §3） | 一致 | P4 | — | 静态枚举 + `captures/253-status-snapshot.json`。移动端 G2 死键 **0** |
| CA-042 | mobile.js 错误提示（:184） | `j.message`（`j.error \|\| j.message \|\| msg`） | 同 CA-034：服务端只下发 `error` | 一致 | P4 | 定性不修（同 CA-034） | 静态 `:184` |
| CA-043 | mobile.js 预算（硬线） | — | — | 一致 | P4 | — | 实测：`mobile.js` 1645 行（硬线 ≤1660，余 15 行）、`mobile.css` 27395B（硬线 ≤27455B，余 60B）。**本岗零代码改动，未触预算**。审计结论中移动端修复量：CA-036（删 1 行级）、CA-037（服务端透传为主，移动端 0 行）——均在硬线内；若修复岗发现须超硬线，按 §7 停工回总管 |

## 面 C · 遗留 app.js（2462 行，在服、无入口页面，F4）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-044 | app.js 世界演变卡（:80-145 `renderEvolutionCard`，数据经 `:126-143` 的 `ev` 构造） | `data.updated_at/director/arcs/faction/echo/era/blood/realms_open/summary_lines/server_time` | `GET /world/director`（`server/app.py:418`）：`director_snapshot()`（含 `server_time`）+ `evolution`（`build_world_evolution`，含 `updated_at/arcs/faction/echo/era/blood/realms_open/summary_lines`） | 一致 | P4 | — | 静态 `server/app.py:418-430`、`core/schedule.py:41-56`、`core/world_director.py:1541-1543`。注意：`renderEvolutionCard` 读的是 `loadEvolutionCard` 现场构造的 `ev` 对象（键恒全），非原始响应直读；原始响应缺 `summary_lines` 时以 `evoSrc.summary_lines` 兜底 |
| CA-045 | app.js 登录/死亡处理（:1860-1960、:1340-1356） | `data.user_id/username/token/dead/resumed/settlement/consignment_open_count/newbie_feed` | join payload（`001-join.json`：`token/user_id/newbie_feed/resumed`，**无 `ok`、无 `username`**）与死者 payload（`206-join-dead.json`：`dead/settlement/consignment_open_count/username`，**无 `newbie_feed`**） | 一致 | P4 | — | `captures/001-join.json`、`206-join-dead.json`。两 payload 的键集合已逐项核对（join 17 键、dead 25 键） |
| CA-046 | app.js 命令后刷新判定（:1403-1404） | `data.spawned` / `data.target_died` | `spawned` 由自由行动结果下发（`core/free_action.py:195`，`spawned` 键在场）；`target_died` 由斗法路径下发（`server/world.py:5479`，`_fight` 返回含 `target_died`；`core/combat.py:208-392`） | 一致 | P4 | — | `captures/145-free-action.json`（`spawned` 键在场）、静态 `server/world.py:5479`。注：自由行动结果**无** `target_died` 键（`core/free_action.py:195`），该读只在斗法响应上为真——两路各取所需，无误读 |
| CA-047 | app.js 死亡结算行（:1551、:1560） | `settlement.auction_refunds[].lot_id/item/amount`、`settlement.pawn_forfeits[].ticket_id/item/redeem` | `core/wallet.py:384`（`{lot_id, item, amount}`）、`:416-421`（`{ticket_id, item, redeem}`） | 一致 | P4 | — | 静态 `core/wallet.py:384,416`。`r.item \|\| r.lot_id \|\| "拍品"` 三级兜底皆有真值来源 |
| CA-048 | app.js 状态读取面（全文件 `st.*` 35 键） | 全部 `st.*` | `_status_dict` 77 键全含——`st.npc_name`（:1653）除外：该处 `s` 是留痕 `shadow` 条目（`trace.shadow[]` 的 `{npc_name, value}`），非 status 对象，属 G2 正则误报，已澄清 | 一致 | P4 | — | 静态 `web/app.js:1648-1656`（`legacyTraceHtml`，`s` 为 shadow 条目）；`tests/test_qa2_frontend_contract.py` 方法（`st.*` ⊆ `_status_dict`）复核通过 |
| CA-049 | app.js 错误提示（:394） | `j.detail`（`j.error \|\| j.detail \|\| detail`） | 服务端错误形恒为 `{ok, error}`，无 `detail` | 一致 | P4 | 定性不修（兜底链无害，记录备查） | 静态 `:394` |
| CA-050 | app.js Demo 面 | （无） | app.js 全文 **0 处** `state.demo`，无 demo 模式、无本地捏造分支 | 一致 | P4 | — | 严格 grep `state.demo` 0 命中（早期宽松统计误把 `heart_demon` 子串计为 5 处，已纠正） |

## 面 D · CLI（cli/views.py + cli/main.py）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-051 | cli/views.py `render_meditation_summary`（:88-109） | `res.actual_real_hours / effective_hours / hours / is_fatal / died_in_cave / demon_eruption / event_desc / message / success / world_rumors / is_idle_sitting` | 调用方 `cli/main.py:557,564,589,1014` 直接传 `WorldClock.settle_meditation(player, ...)` 的返回 dict（**不**走 `/命令` 响应——`_emerge` 的 `ret` 另有 `{ok,text,death,status,legacy,sweep,death_cause}`，CLI 不读 `ret` 的闭关摘要键） | 一致 | P4 | — | `core/clock.py:492` 起的成功返回 dict 含 `success/is_fatal/died_in_cave/hours/actual_real_hours/effective_hours/after_years/exp_gained/event_desc/world_rumors/message/demon_eruption`；`is_idle_sitting` 只在摘要 dict 内另处出现（:281 判定、:355），不在 settle 返回中——`render_meditation_summary` 用 `res.get("is_idle_sitting")` 安全取，缺失即 False，无可见异常。失败路（:437）只含 `success/message`，`res.get` 全守卫 |
| CA-052 | cli/views.py `render_tribulation_result`（:110-131） | `result.message / result.success / result.new_realm / result.lifespan_gained / result.roll / result.prob_pct` | 调用方 `cli/main.py:1104-1111` 直接传 `BreakthroughEngine.attempt_breakthrough(player, ...)` 返回（`core/breakthrough.py` 全返回点皆含 `success/message`；成功含 `new_realm/lifespan_gained/roll/prob_pct`） | 一致 | P4 | — | `core/breakthrough.py:38,45,61,171,180,215,239`（各返回 dict 皆含 `success` + `message`）；`cli/main.py:1111` 另用 `res["new_realm"]`/`res["lifespan_gained"]`（成功路恒在） |
| CA-053 | cli/views.py `render_combat_result`（:132-149） | `result.report` / `result.target_died` | `_fight`（`server/world.py:5479`）返回含 `report/target_died`（`core/combat.py:208-392`） | 一致 | P4 | — | 静态 `server/world.py:5479`、`core/combat.py:208` |
| CA-054 | cli/views.py `render_free_action`（:150-166） | `result.intent / outcome / narrative / source / effects_summary / spawned` | `FreeAction` 返回（`core/free_action.py:195`）：`{ok, intent, outcome, narrative, effects_summary, spawned, source, event_id, text}` | 一致 | P4 | — | `core/free_action.py:195`；`captures/145-free-action.json`（`spawned` 在场） |
| CA-055 | cli/views.py `render_heart_demon_result`（:167-187） | `result.message / outcome / narrative / effects_summary / tribulation_mod / source / success` | `HeartDemonEngine.resolve`（`core/heart_demon.py:66,68`）：失败路含 `message`；成功路含 `narrative/outcome/effects_summary/tribulation_mod/source` | 一致 | P4 | — | `core/heart_demon.py:66,68` |
| CA-056 | cli/main.py `/talk`（:2075）与 `/here` 后的 `res.get("attitude_cn")` | `res.attitude_cn / res.personality / res.attitude_delta / res.source` | `:2075` 的 `res` 是 `NpcDialogueEngine.talk(...)`（`core/npc_mind.py:553` 返回含 `ok/npc/personality/attitude/attitude_cn/attitude_delta/line/source`）；`/here` 行亦含 `attitude_cn`（`core/here.py:70-84`） | 一致 | P4 | — | `core/npc_mind.py:553-560`；`captures/142-talk-npc.json`（`/交谈` 经 handle 返回的文本含态度标签）。注：`talk()` 的 `attitude_cn` 由 `ATTITUDE_LABELS` 映射，恒有值 |
| CA-057 | cli/views.py `render_character_sheet`（:31-87） | `char.realm / spirit_stones / items / spells / pills / qi / dao_heart / sect_rank / ...` | 角色模型属性（`Character`，非响应契约）——CLI 直读内存对象，无契约可断 | 一致 | P4 | — | 静态 `cli/views.py:31-87`。CLI 无仪式呈现面（ceremony 只在桌面/移动端消费） |

## 面 E · 状态/入局 payload（服务端出口）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-058 | 桌面 + 移动 + app.js 状态面 | `_status_dict` 77 键全量（含 `profile/npc_roster...`） | `server/world.py:4551-5060`；快照 `captures/253-status-snapshot.json` | 一致 | P4 | — | 键集合近乎无条件全量下发，条件只体现在**值可空**：快照中值为 `null` 的键为 `pet/cave/next_rank/crane_pending_item/dungeon/quest`；唯一以 `if` 控制子键集合的是 `sect_ring`（:4665，仅 `sect_name` 在场时含 `day/accepted/done/themes` 子键）。三端 G2 计数之和 129（含跨端重叠），差集 0——三端读取的状态键皆在集合内 |
| CA-059 | 桌面登录判断（:7399-7400） | join 响应**无 `ok` 键** | `_join_locked`（:587-641）返回 `{**snap, newbie_feed, first_night, entry, origin_card}`，无 `ok` | 一致 | P4 | 定性不修（记录口径分叉：join 与 `/命令` 的 `{ok, ...}` 不统一；前端以 `data.token` 判定，未见异常。改口径牵连登录流，须主策岗裁决） | `captures/001-join.json`（顶层键无 `ok`） |
| CA-060 | 桌面/移动入局面 | `entry.version/since/generated_at/lines{fate,chains,relations}/queue[{kind,priority,title,text,ref_id,target,ts,options?}]/highlight/rest_count/empty/empty_text/proactive{text,npc}` | `build_entry`（`core/briefing.py:57`） | 一致 | P4 | — | `captures/001-join.json`（`entry` 键表与 `core/briefing.py:460-478` 逐项一致） |
| CA-061 | 桌面/移动出身面 | `origin_card.just_created` + `status.origin{...}`（`origin.relations[].npc_name/role/init_value/vendetta/vendetta_for`） | `core/origin.py:281-309`（`origin` 结构） | 一致 | P4 | — | `captures/001-join.json`、`253-status-snapshot.json` |
| CA-062 | 桌面死亡处理 | 死者 payload：`ok/dead/ceremony/token/user_id/username/character_id/name/realm/location/rem_years/legacy_points/lives/is_new_life/resumed/death_cause/legacy{points,lives,boosts,lifespan_lived,past_lives,trace}/wallet/settlement/consignment_open_count/lock_fallback/session_issued/settlement_pending/settled`（25 键） | `server/world.py:919-971`（`_join_locked` 死者分支） | 一致 | P4 | — | `captures/206-join-dead.json`（25 键与 :919-971 逐项一致；**无 `newbie_feed`**——该键只在活人 join payload 中） |
| CA-063 | 桌面转世处理 | `reincarnate` 返回 `{ok, text, karma_shadow, settle{points_gained,cause,past_life}, boosts_applied, legacy_points, wallet, sweep, name, realm, location, rem_years, origin_card, ceremony}`；`legacy_info` 返回 `{ok, points, lives, earned, past_lives, traces, karma_shadow, boosts, max_boosts, alive}` | `server/world.py:1004-1141`（`reincarnate`，返回 :1112-1140）；`legacy_info`（:973-1003） | 一致 | P4 | — | `captures/209-reincarnate.json`（14 键与返回 dict 一致；**无 `status`、无顶层 `legacy`**——转世后状态由客户端重取 `/look` 补齐）、`251-reborn-via-handle.json`（经 handle 的 `/转世` 亦同形） |

## 面 F · 只读呈现面（ceremony / 图鉴 / 奇遇）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-064 | 桌面 + 移动仪式呈现（workbench :859-892、mobile :1033-1060） | `ceremony{kind,beats[]/result_ref}`、`ceremony_next` | `core/ceremony.py`（beats 恒含 `stage/text/asset_key/choices`；`result_ref` 标量映射；`ceremony_next` 为下一幕 `{kind, text}`） | 一致 | P4 | — | `captures/103-dig-scar-created.json`（loot 幕）、`118-breakthrough.json`（`ceremony` + `ceremony_next` 双幕协议）；`tests/test_ceremony_contract.py` 另有契约覆盖 |
| CA-065 | 桌面图鉴页（:754 起 `renderGallery`） | `status.gallery{unlocked,count,total,title,newly}` | `core/gallery.py` `gallery.summary`（`{unlocked, count, total, title, newly}`） | 一致 | P4 | — | `captures/253-status-snapshot.json`（`gallery{count:19,total:139}`） |
| CA-066 | 桌面/移动奇遇条（workbench :6651-6663、mobile 同类） | `omen_image`（仅 `/奇遇`）、`omen_ended`、`/挖宝` 的 `omen_inline/title/choices` | `/奇遇`（:2058）下发 `omen_image/omen_inline/omen_open`；`omen_ended` 由 :2075（`/奇遇说` 终局）、:2099、:2156（推进）下发；`/挖宝`（:2246）只透传 `omen_inline/title/choices`，无 `omen_image` | 一致 | P4 | — | `captures/221-omen-scene-start.json`（`omen_image: ""`——空串，前端 `|| ""` 安全）、`222-omen-say.json`、`101-dig-element-clever.json`（挖宝 omen 三键齐全、无 `omen_image`） |

## 面 G · Demo 本地捏造（workbench.js / mobile.js）

| ID | 消费面 | 消费字段 | 服务端来源 | 结论 | 严重级 | 处置 | 证据 |
|---|---|---|---|---|---|---|---|
| CA-067 | workbench.js demo 面（48 处 `state.demo`） | demo 分支捏造：假物品、假战利品、假数值（全部 `if (state.demo)` 门内） | —（本地捏造，联机不可达） | 一致 | P4 | — | 静态全量 grep：48 处 `state.demo` 皆有门；`ensureDefaultInventory` 的假物品在联机时经 `applyStatus` 的 `state.inventory = st.items.slice()` 覆盖。契约测试应锁死「联机时 `state.demo` 永假」 |
| CA-068 | workbench.js demo 假数据中文 stat 键 | 假道袍 `{"护身甲御": 90, "避火抗性": 50}`、仙鹤奖励 `{"纯阳火威": 50}`（:1295） | —（demo 内假数据） | 一致 | P4 | 记录（契约测试应锁死：若泄漏到联机渲染即复发 v0.3.11 同型「攻伐 +undefined」） | 静态 `web/workbench.js:1295` 及 `ensureDefaultInventory`。仅 demo 内，不改 |
| CA-069 | mobile.js demo 面（:1087 `demoResult`） | `demoResult` 门内只返回 `{ok, text, status}`，无捏造战利品 | —（本地） | 一致 | P4 | — | 静态 `web/mobile.js:1087` |
| CA-070 | workbench.js 仙鹤回调（:1252） | `state.inventory[0]` 兜底（`ensureDefaultInventory` 的假物品） | 联机时 `applyStatus` 覆盖 `state.inventory`，但依赖**时序假设**：若仙鹤回调先于首次 `applyStatus` 触发，兜底即 demo 假物品 | 一致 | P4 | 记录（修复岗评估：把兜底改为「无物品时不渲染」或确保登录后先 `applyStatus` 再绑回调；不得顺手改 demo 数据） | 静态 `web/workbench.js:1252` |

## 口径裁决（§4.3，按字段逐个定死）

- **枚举（中文）**：一律以服务端下发值为准；前端映射表（`DAO_BOON_CATALOG`、treasurePanelStatLine 标签表、`ATTITUDE_LABELS`）缺省时原值呈现，不得自造中文。服务端已下发 `attitude_cn`、`blood_marked` 等中文键的，前端不得再本地翻译。
- **比率/百分比**：结构化字段中**无比率型字段**在装备 stats 中出现——`crit_rate` 等从未下发；`root_eff`/`qi_mult` 服务端下发但三端均不渲染（见附录 B 未消费键）。`stone_gain` 为灵石数，非比率。
- **小数**：沿 `treasurePanelStatLine` 先例为全仓默认口径——**2 位小数截断**（`Math.round(v*100)/100`，非四舍五入到 1 位）、零值/非数值**整行省略**、不得以 `|| 0`/`|| 100` 补假数。`rem_years` 例外：见下条。
- **寿元（`rem_years`）**：全仓定死为 **`toFixed(1)` + 单位「载」**；缺失（`== null`）显「—」，不得用 100/145 等假缺省。移动端（mobile.js:236、:382）已是正确口径；桌面两处（:2191、:2409）须按此统一（CA-005）。
- **石数（`stone_gain` / `stone_loss`）**：整数灵石数；`stone_gain > 0` 显「发掘灵石 +N」，`stone_loss > 0` 显「灵石 −N」，两者皆为 0 时**整行省略**（不得显「+0」）；`stone_loss` 字段由 §6.1 新增（CA-002）。
- **时间戳**：沿既有豁免——`generated_at`、`ts`、`server_time` 等时间戳字段不做数值口径裁决，原样呈现。
- **`merit` / `sin`**：整数；缺失显「—」，不得用 3650/120 补（CA-006）。
- **地牢 `status_effects`**：未知 effect 键通用渲染 `DEBUFF_NAMES[k] || k` + 回合数，不得只判空（CA-013）。

## 文本抽查（§2.5，P0 级，单独成节）

本节只抽查**数值语义牵连**的文本数字（其余文本数字不逐句对账，见方法学边界）。

| 抽查项 | 文本数字 | 结构化字段 | 结论 |
|---|---|---|---|
| `/挖宝` 巧破（ELEMENT） | 「灵石 +360」 | `stone_gain = 360` | 一致（`101-dig-element-clever.json`） |
| `/挖宝` 遗物（scar_created） | 「灵石 +800」 | `stone_gain = 800` | 一致（`103-dig-scar-created.json`） |
| `/挖宝` 战利（combat） | 「灵石 +500」 | `stone_gain = 500` | 一致（`104-dig-combat.json`） |
| `/挖宝` 蛮力（brute_force） | 「受反震损耗灵石 40」 | `stone_gain = 0`，无 `stone_loss` | **矛盾，P0**（`102-dig-brute-force.json`；harness 实测灵石 100000 → 99960）——见 CA-002 |
| `/挖宝` 战斗败走（combat_defeat） | 「燃寿 0.5 岁」 | 文本-only，无对应结构化字段 | 一致（`255-dig-combat-defeat.json`；燃寿真实发生，字段缺失属文本-only，记备查） |
| `/捡漏` | 「消耗 80 灵石」 | 无字段 | 一致（`105-blind-box-1.json`；扣款真实：`server/world.py:4066` 起 `char.spirit_stones -= 80`） |
| `/服用` 成功 | 「灵力 +N」类文本 | `ok: true`，无数值字段 | 文本-only，一致（`259-pill-use-success.json`） |

## 标红清单（§4.2，数值语义牵连项）

**0 条。**

核查过程：逐行台账中凡「不一致」且改动会动数值语义者，均已按 §4.2 审过——

- CA-002（`stone_loss`）为 §6.1 **已批**的唯一新增键：只增字段、不动 `stone_gain` 语义、不动存档、不动既有测试，故**不标红**（处置见 CA-002）。
- CA-001（`/悟丹` 崩溃）修复恢复既有设计意图的本地抽配方，不改数值语义。
- CA-003（遗物面板不可达）修复限于面板/仪式叠演顺序，不改结算本体与数值。
- CA-004（静态捏造）修复为删静态值、改读真实 `status` 键，不改服务端数值。
- 其余不一致皆为渲染口径、死键、缺省态、路由别名，无数值语义牵连。

## 操作基线回归（§8 / RG-01）

- 命令：`AI_REQUIRED=0 ~/workspace/projects/xiuxian/.venv/bin/python -m pytest tests/ -q`（工作区内新鲜 DB；`data/` 原本不存在，即隔离成立；系统 `python3` 无 pytest，必须用主仓 `.venv` 的 Python 3.12 / pytest 9.2.0）。
- 日志：`/tmp/contract-audit/regression-baseline.log`（后台进程跑完后归档）。
- 结果（2026-11-08 实跑，耗时 1515.17s）：**1357 passed, 8 failed**——与 CHANGELOG 记载的 1357 passed / 8 failed **完全一致**，本轮操作基线即此失败集：
  1. `tests/test_auth_hardening.py::test_world_join_requires_explicit_nonempty_authenticated_uid`
  2. `tests/test_karma_chains.py::test_kill_and_bounty_single_chain`
  3. `tests/test_living_jianghu.py::test_lan_feed_endpoint_contract`
  4. `tests/test_natural_omen.py::test_initial_character_and_config`
  5. `tests/test_qa_account_death_acceptance.py::test_qa2_join_dead_http_and_anonymous_unchanged`
  6. `tests/test_status_dict_gray.py::test_status_dict_includes_bag_and_marks`
  7. `tests/test_status_dict_gray.py::test_status_dict_follows_real_equip_flow`
  8. `tests/test_workbench_api.py::test_login_then_look_here`（`urllib.error.URLError: Connection refused`，见日志尾部）

  本轮修复岗须以该失败集为对照：新增失败即回归，上述 8 项为基线失败（PRE-EXISTING）。

## 未覆盖端点清单

### 分支级：0 项

189/189 个 `/命令` 分发分支全部有真实响应抓取或真实崩溃记录（261 抓取 + 4 崩溃，同一根因 CA-001）。

### 子结局级（未覆盖）：5 项

| # | 端点 / 子结局 | 未覆盖原因 | 替代证据 |
|---|---|---|---|
| U-1 | 心魔待决前置路径（`server/world.py:1186-1297`，`tribulation{success,fatal,new_realm}` 下发） | 需心魔会话状态（`_heart_demon_state`），harness 未构造该状态 | 静态返回 dict（:1208-1297）+ `core/heart_demon.py` + 既有测试 `tests/test_heart_demon*.py` |
| U-2 | `/悟丹` / `/悟器` / `/生成丹药` / `/生成法宝` 成功路径 | CA-001 崩溃使成功路径不可达；待修复后补抓 | 静态 `server/world.py:2667-2740` + 既有测试 `tests/test_world.py` 相关断言 |
| U-3 | `/挖宝` 其余子结局（除已抓的 5 种外：`need_choice` 的其他分支、scar_created 的非遗物变体） | 随机分支未穷举（种子固定 20261108 下只命中已抓结局） | 静态 `core/treasure_system.py` 分支表 + `tests/test_treasure*.py` |
| U-4 | `/斗法` 胜利/击杀子结局（`target_died = true`） | 需高战力差，harness 角色未达 | 静态 `server/world.py:5479` + `core/combat.py:208-392` + 既有测试 |
| U-5 | 闭关结算的死亡/心魔爆发子结局（`is_fatal` / `demon_eruption`） | 需长闭关 + 低道心，harness 未构造 | 静态 `core/clock.py:305` 返回 dict + `tests/test_meditation*.py` |

## 附录 A · 别名清册（三前端响应/状态对象别名）

### A.1 响应对象别名（`await res.json()` 的结果）

| 文件 | 别名 | 出现位置（代表） | 备注 |
|---|---|---|---|
| workbench.js | `res` | `:441`（`j = await res.json()` 后多处 `j.`）、`:7422` | `res` 在 `api()` 层先是 fetch Response（`res.status` = HTTP 状态码），解析后为 `j`；凡称 `res.status` 皆指游戏响应 `status` 键，已逐点核对 |
| workbench.js | `j` | `:441`、`:7422` | 解析后 JSON 本体 |
| workbench.js | `data` | `:5236`（`data.ceremony`）、`:6772`（`data.tribulation`） | sendCmd 回调入参 |
| workbench.js | `payload` | `:7394`（`payload.entry_pending`） | 登录响应 |
| workbench.js | `b` | `:5550`（`b = await res.json()`） | 纳戒检视器 |
| workbench.js | `cer` | `:859`（`cer = res.ceremony`） | 仪式对象 |
| mobile.js | `j` | `:183`、`:1348` | 解析后 JSON 本体 |
| mobile.js | `data` | `:1107`（sendCmdM 回调） | 同桌面 |
| mobile.js | `r` | `:623`（`r = await res.json()`） | 挖宝入口 |
| mobile.js | `cer` | `:1033` | 仪式对象 |
| app.js | `j` | `:393` | 解析后 JSON 本体 |
| app.js | `b` | `:100`（`b = await res.json()`） | 世界演变卡 |
| app.js | `data` | `:1403`（`data.spawned`） | 命令后刷新判定 |

### A.2 状态对象别名（`_status_dict` 的下发值）

| 文件 | 别名 | 出现位置（代表） | 备注 |
|---|---|---|---|
| workbench.js | `st` | `:479`（`applyStatus(st, reqEpoch)` 入参） | 状态本体 |
| workbench.js | `s` | 多处（`= state.status`） | 注意：`s.` 有歧义——`:2733` 的 `s = String(...)` 是局部字符串，非状态对象；已逐点排除 |
| workbench.js | `dg` | 多处（`= state.status?.dungeon`） | 地牢子对象 |
| workbench.js | `dgSess` | `:4516` | 地牢会话 |
| workbench.js | `sceneBanner` | `:838` | 同场横幅 |
| mobile.js | `st` | `:236`、`:382` | 状态本体 |
| mobile.js | `stW` | `:1107` | sendCmdM 内状态 |
| mobile.js | `state.status` | 多处 | 直接读 |
| app.js | `st` | `:1403`（`applyStatus(st)`） | 状态本体 |
| app.js | `s` | `:1653`（`s = shadow` 条目——**非**状态对象，见 CA-048） | 误报澄清 |

### A.3 枚举计数（G1–G11 落点）

- G1 响应顶层键读（去重）：workbench 66 / app.js 73 / mobile 41。
- G2 状态键读（去重）：workbench 50 / app.js 35 / mobile 44。
- G3 模板插值：workbench 791 / app.js 73 / mobile 0（字符串拼接）。
- G4 通用渲染：workbench 3（:878、:4516、:5550）、app.js 1（:100）、mobile 1（:1045）。
- G5 `?.`：workbench 17。
- G6 数值格式化：`toFixed` workbench 2 / mobile 2 / app.js 4；`toLocaleString` 12（workbench 时间类）。
- G7 `state.demo`（严格）：workbench 48 / app.js **0** / mobile 10。
- G8 写死中文 stat 键：workbench 4 处皆为 `treasurePanelStatLine` 标签表（合法）。
- G9 仪式：workbench ceremony 26 / ceremony_next 9 / result_ref 3。
- G10 入局/出身/图鉴/奇遇：见 CA-032、CA-060、CA-061、CA-065、CA-066。
- G11 CLI：`render_*` 20 个函数，`res.get`/`result.get`/`char.*` 71 处。

## 附录 B · 未消费键清单（备查）

### B.1 桌面不读的 `_status_dict` 键（部分为移动/app.js 读取）

`body_soul`、`books`、`cave`、`is_bag_full`、`professions`、`quest`、`root_eff`、`qi_mult`。

### B.2 服务端下发、三端皆不读的顶层响应键（初算，待最终差集表复核）

约 118 个候选（含大量 `_status_dict` 内键与嵌套键——按「顶层响应键」口径重算后以最终差集表为准；本台账的死键行（CA-007/008/009/010/011/012/036）已覆盖其中前端读、服务端不下发的反向集合）。

### B.3 抓取覆盖说明

261 个抓取文件覆盖 189 分支（含 join、join-dead、reincarnate、`/转世` 经 handle、双角色交易、死亡/转世两轮、`/挖宝 3`、combat_defeat、`/服用` 成功、跨号买卖成功）；4 条崩溃记录（CA-001 同根因）。抓取清单见 `docs/compose/contract-audit-captures/index.json`。
