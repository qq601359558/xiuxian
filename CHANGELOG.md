# 更新日志

## v0.3.16-gray.23（2026-11-11）— token/command 报错玩家化

定位：体验修复轮（Martinez 本人 2026-11-10 17:48 撞到的 bug——tick 长锁窗口内登录返回 token 为空的「假成功」HTTP 200 ok:true，随后点任何动作把后端原文「需要 token 与 command」弹给玩家）。上一稳定点 v0.3.15-gray.22（03ae2bd）。分支 `feat/action-error-ux`（修复 `ac8170d` → 合并 `ad6a47b` → 预算补齐 `939bf2f`/`abf75b2`）。

### 变更
- 登录忙时有界重试与诚实报错：登录遇 tick 长锁窗口不再返回 ok:true + 空 token 的「假成功」；忙回退带 `code: "WORLD_BUSY"`，忙时人话提示并自动重试一次，重试仍无 token 则留门待用户手动重试
- token 缺失前端拦截：双端 `sendCmd`/`api()` 双重守卫，无 token 不发请求，界面提示「登录已失效，请重新登录」并回到登录门；命令输入框空串时发送按钮禁用、提交不发请求
- 后端 `/action` 缺参只增 `code`（`AUTH_REQUIRED` / `EMPTY_COMMAND`），状态码与 `error` 文案不变；前端按 code 映射玩家安全文案，后端原文只出现在 console/日志，不再弹给玩家
- 合并解法（9 冲突点，双边语义全保留）：双端 `api()` 同时保留 `code`/`rawError`（分支）与 `serverMessage`/`status`（块一 B1-1，另补分支遗漏的 `err.status`）；交谈失败显示用人话映射 + 保留清输入框（B1-3）；doAuth 503 仍走后端诚实文案、其余走人话映射
- 预算第七次豁免：mobile.js 合并 2130 行，文件上限 2100 → 2160、净增上限 928 → 988（CT04、phase1、FE-03、mobile_web、command-panels 五处断言收口；CSS 与 token 纪律不变）

### 测试
- 定向 `tests/test_action_error_ux.py` 20/20；交谈/登录/移动套件 122 过，仅 2 败均为基线旧账
- 合并态全量回归（新鲜 DB）三轮：1533/13、1537/9、1537/9——最终轮失败集 = v0.3.15 基线 7 项全在（鉴权 join、死亡验收 join、status_dict×2、natural_omen、karma 链 flaky、workbench 活服务器冒烟）+ living_jianghu 与 dr01 两项顺序依赖 flaky（均在合并态新鲜库隔离单跑通过；world_director 仅第一轮出现、后两轮未复现）；归因新增失败 **0**；第三轮中途被环境 SIGTERM 截断一次（51%），清库重跑后完整通过

## v0.3.15-gray.22（2026-11-10）— 块一·玩不下去先清零

定位：可玩性清障轮（依据模拟玩家本地实测清单 S1–S8，Martinez 2026-11-09 批准按清单开修）。上一稳定点 v0.3.14-gray.21（fed5332）。分支 `feat/playability-block1`（spec `d3cf67a` → 三路实现合并 `5c36291` → 评审修复 `93b2f42` → 复审修复 `83c791a` → 复测再修 `7f3f0b6` → 修复轮 3 与 MF-1 `50e0b90` → C4 修复 `a0da422` → 出生地修复 `c2846fc`）。

### 变更
- B1-1 注册兜底：tick/AI 卡顿窗口内注册不再 500；忙碌走 503 `SERVER_BUSY` 真话文案（双端分流显示），永不误报「请确认服务已启动」
- B1-2 tick 持锁根治：NPC agenda / WorldDirector 的 AI 调用移出世界锁（三段式 + CAS + 陈旧判定），/转世 改有界锁、director 竞态收口；存储层集中 `_connect` 启用 WAL + `synchronous=NORMAL`（commit 不再逐次 fsync，耐久口径见 spec 决策记录）；实测 tick hold 由约 20s 降至稳态 2.6–4.0s
- B1-3 交谈清扫：玩家面错误出口类级清扫，运维原文（CC Switch、.env、LLM_API_*、server.log 路径等）永不下发给玩家；AI 故障兜底改为三句结构性格化模板池（承题 + 态度 + 邀续，持久轮换），不再只回「嗯。」；交谈发送失败清输入框并给可重试状态
- B1-4 目标给路 + 完成语义（Martinez 2026-11-10 拍板）：命途目标卡下发 `current_target`——同场明说「就在此处」并给交谈直达按钮，异场给地点与前往入口；带 `npc_id` 的「去见某人」类章节完成条件改为**到访 + 在场 + 真正交谈一轮**（决策记录见 `docs/compose/spec/playability-block1.md`，game-feel-phase2 §3.5 同步修订，ft03/ft06/ui02 旧契约以 superseded 记录保留）；交谈证据按（玩家，NPC）对持久留存、不被切换会话覆盖；出生地即目标地时，当前所在地视为已到访（求值 C 口径，零写入）
- B1-5 「修炼」正名：/修炼 为一等入口直达现行闭关实现，双端快捷芯片、命令表与 /帮助 同步，不再回「未知指令」
- B1-6 行情原码清零：市场行构建器统一以游戏内名称显示、按 id 去重，玩家面不再出现 `equip_*`/`pill_*`/`mat_*` 内部 ID，且有新人买得起的低价货（原 D-QA1 销项）
- B1-7 降噪与误读：入局卡只展示已相识 NPC 的态度变化；命盘「神通图」等图鉴区明确标注未习得口径，不再像已习得技能栏
- 复测追加修复（C4）：「想打听些消息」曾被意图分类器单字「打」误判为 attack、被新手庇护拦截并吞掉整轮 NPC 回复；良性复合词（打听/打探/打量/打招呼等）在分类前先行剔除，AI 分类同口径纠偏，敌意动作的庇护拦截语义不变

### 测试
- 全量回归（新鲜 DB，最终头 `c2846fc`）：**1519 passed / 7 failed**——失败集与 v0.3.14 基线集完全一致（鉴权 join、死亡验收 join、status_dict×2、natural_omen、karma 链 flaky、workbench 活服务器冒烟），块一归因新增失败 **0**（总数 1526 = 基线口径 + 块一新增测试）
- 独立复审：修复轮 3 复审除 MF-1（/说 动作分支补写交谈对标记）外全过，MF-1 修复并补 ft03c 回归后转 PASS；合谋熔断 half_open 口径经复审裁决维持「非 closed 不发」
- 模拟玩家复测（本地实例，390×844 移动视口）：R1 目标卡与新完成语义（抵达不完成 / 交谈后完成 / 出生地同场原地谈成）、R2 断 AI 兜底（三句结构、运维词 0 命中、发送后输入清空）、R3 持锁量测（n=5，hold_ms 最大 4042 / 中位 3547；/action 最长 1311ms；窗口内 HTTP 5xx = 0）、C1 双注册、C2 /修炼、C3 /行情、C4 交谈弹窗与打听句——全过；证据存 `~/workspace/projects/xiuxian-simtest/simtest-shots-block1/` 与 `simtest-shots-block1-r2/`
- 注记：全量回归期间运行环境多次重启，前两跑（脱管进程 I/O 干扰）的大面积 sqlite 失败已定性为环境问题，最终数字以托管前台在新鲜库上重跑的结果为准；NAS 存档未受任何影响

## v0.3.14-gray.21（2026-11-09）— 交谈结构化与手机端交谈弹窗

定位：体验修复轮（兑现 Martinez「与 NPC 交谈为什么不是弹窗了，而且 AI 回复格式有点乱」）。上一稳定点 v0.3.13-gray.20（2082c40）。分支 `feat/chat-structure`（`aa13a00` → 评审 MF-1/MF-2 修复 `c66b777` → finalize `aca741d`）。

### 变更
- 交谈结构化：服务端交谈响应新增 `chat_lines`（系统行与 NPC 正文分离下发），旧 `text` 字段保留兼容、CLI 不受影响；双端按结构化字段渲染，不再靠正则逐行猜分类
- 手机端交谈弹窗：补与桌面「神识交谈玉简」同构的移动弹窗（`openChatM`/`renderChatHeadM`，会话留在弹窗内、底部输入、消费服务端 `avatar`），NPC 交谈与器灵灵语同一容器；桌面弹窗行为不变
- AI 正文呈现清洗：仅呈现层剥离 markdown 残留标记、统一段落/换行呈现，不改叙事生成与任何数值结算
- 契约：CT01 定稿更新为服务端 174 / 三端读 137 / 未读 45 / 死键 8（`avatar` 由移动端交谈弹窗消费转已读；`chat_lines` 按 CA-002 先例入 `SERVER_TOP_KEYS_EXTRA` 静态补集；请求体写入别名 `to` 不入读键集）
- 预算第六次豁免（chat-structure D2）：mobile.css 上限 29200B → 32000B（实测 31324B）、mobile.js 上限统一 2100 行（实测 1969 行），手机端交谈弹窗 CSS/JS 增量；`test_mobile_web` js 净增断言对齐 D1 已裁定的 928（落码遗漏修正）

### 测试
- 全量回归（新鲜 DB）：**1452 passed / 11 failed**——失败集定性：7 项为 v0.3.13 基线集成员（鉴权 join、死亡验收 join、status_dict×2、natural_omen、karma 链 flaky、workbench 活服务器冒烟），4 项为仓内残留旧 worktree 副本（baseline-0643434 / head-check）触发的全仓静态扫描误报，清理后复跑 4/4 绿；交谈改动归因的新失败 **0**（总数 1463 = 基线 1450 + 交谈新增 13）
- 定向：预算 5 项 + CT01 共 6 绿；契约审计全量 + chat 相关 7 文件 155 绿
- 注记：全量回归首跑因运行环境重启中断（日志与本地开发库备份置于 /tmp 被清，本地开发库遗失、已由回归新库接替），改以持久化日志重跑完成；NAS 存档未受任何影响

## v0.3.13-gray.20（2026-11-09）— 命令回复面板化

定位：玩法呈现轮（兑现 Martinez「查看个人信息出来的是纯文字，很乱，应该是类似游戏面板那种效果，还有很多其他的命令回复」的承诺）。上一稳定点 v0.3.12-gray.19（2285d37）。分支 `feat/command-panels`（Spec `67bc9a9` → 后端合并 `1f1638d` → 前端合并 `c9c024b` → 集成修复 `965ee12` → 返工 `855a827`/`999c346` → M4 截图 `97ef67e` → 小修轮 `ca8f9ad`/`539419c`/`5a73334`/`4e6f989` → R1 返修 `97e8659`）。

### 变更
- 通用面板渲染层：桌面 `web/workbench.js` 与移动 `web/mobile.js` 各新增命令面板块（CP-00），`buildCommandPanel(cmd, data)` / `buildCommandPanelM` + 字段映射表（桌面 63 builder / 移动 65 builder，117 token 别名），`sendCmd` 面板优先分支（有面板 → `pushFeedHtml`，无面板 → 原 `pushFeed(data.text)` 不变）；数值口径缺失 → `—`、零值 → `0`（`??` 不用 `||`）、非整数 2 位小数、`rem_years` 复用 `fmtRemYears`；>12 行/>800 字折叠；空行集不出空卡、回落纯文本；不解析 `data.text` 拼面板（K2 静态扫描锁定）、不本地捏造
- 覆盖：目录 108 条主命令全量清册（(a) 10 + (b) 47 + (c) 51）+ 附录 B 目录外 18 项 + gated 7 项（CP-35/39/40/41/64/65/66 均已真实非空抓取定稿），P0 /profile、/look 首优先；后端附录 A 登记 39 键（35 个全新顶层键 + `director`/`arcs`/`trade`/`recipe` 4 个补齐），只增键、文本逐字不变、数值语义零改动
- 截图验收：`docs/compose/command-panels-shots/` 186 页（HTML + PNG 各一，桌面 1280 / 手机 390，含深色抽查 24 页、空态 11 页、每波代表合页），逐张目视 + 横向溢出扫描 0/186
- 预算（D1 豁免内）：mobile.js 1777 行（≤2100，余 323）、mobile.css 28454B（≤29200B，余 746B）、mobile.html 155 行（净增 +0）；workbench.js 9333 行（桌面无硬线）；双端 CP 段零裸 hex（token 化）
- 契约：CT-01 双向差集定稿 173/135/46/8（服务端 173、三端读 135、未读 46、死键 8）；(c) 类文本对照 17 项逐字锁定；D2 已确认（2026-11-09，总管裁决）：feed 内嵌卡替代该条纯文本块
- 评审返工：首审 must-fix M1–M6（/宗门 `rules_tip` 补渲染、桌面零裸 hex、/近况 `origin`→「出身牵连」、186 页截图、CP15/16/31/65 隔离、(c) 类 17 项对照）→ 返工兑现；小修轮 5 项清单 + 14 处同类内部码映射（`*_cn` 优先模式）；复审第二轮唯一 must-fix R1（势力 status 映射缺 `warm`、`allied` 应为「结盟」且无视后端 `status_cn`）→ 前端 4 处 + /世情后端补 `status_cn` 修完，夹具 CP-70 与 `test_fixup_director_faction_status_cn` 锁定
- 残留（不阻塞，另立工单）：D-QA1（低严重度，预存）——`/行情` 面板与 `/坊市`·`/行情` 文本渲染 276 行 `mat_*` 原码行名，根因 `core/market.py` 行构建层以 `ITEM_CATALOG` 键为名、目录含中文名键与 id 键重复条目；修法为 id→中文名回落 + 同物去重，文本与面板同源修复

### 测试
- QA 全量回归（新鲜 DB，连跑两次）：两次均为 **1442 passed / 8 failed**——失败集与基线 8 项逐一相同（鉴权、因果链、LAN feed、奇遇、死亡验收、status_dict×2、workbench API），新增失败 0；1442 = 1387（基线）+ 40（后端）+ 7（前端）+ 2（§12.3 声称 1436 的开发侧计数差）+ 5（小修轮 fixup 测试）+ 1（R1 新增测试）
- 定向：node fixture **2015 passed / 0 failed**；目标套件 `test_command_panels.py + test_contract_audit.py + test_game_feel_phase3_frontend.py + test_mobile_web.py + test_command_catalog.py` 脏库 **109 passed**
- 对账抽查：P0 /profile、/look 真实渲染双端通过；7 组面板数字 vs 文本同源全部一致；stage 2 真实渲染 33/33；12 张截图目视通过
- 独立评审：首审 M1–M6 → 返工 → 复审 R1 唯一 must-fix → R1 返修 `97e8659` → QA 独立验证放行 GO（`~/workspace/reviews/command-panels-QA报告.md`）

## v0.3.12-gray.19（2026-11-08）— 前后端数据口径全量核查

定位：缺陷修复轮（兑现「真人试玩之前先把服务端返回与前端渲染的口径全量核查一遍、扫清同类不一致再汇报」的承诺）。上一稳定点 v0.3.11-gray.18（af4d689）。分支 `feat/contract-audit`（Spec `cfcc878` → 台账初稿 `391a47b` → 总管裁决回写 `25fdd0e`/`05992c1`/`ab5ca4f` → 修复 `f2b8c41` → 返工 `1b9e2b6`）。

### 变更
- 全量台账：`docs/compose/contract-audit-ledger.md` 70 行（P0×4、P1×1、P2×11、P3×11、P4×43；不一致 24、前端兜底捏造 1、格式问题 2、一致 43；标红停手 0）。证据：261 个真实响应抓取（`docs/compose/contract-audit-captures/` + `index.json`，随机种子 20261108）+ 4 条真实崩溃记录，189/189 分发分支有抓取或崩溃记录；双向差集定稿：服务端顶层响应键 138 个 vs 三端引用键（附录 B.2，138/80/65/7）；`_status_dict` 78 键（CA-011 补 `custom_arts` 后 77→78）
- P0×4 修复：CA-001 `/悟丹` 系恒崩溃——`server/world.py:handle()` 内 3 处 `import random`（:3783/:4066/:4143）使模块顶层 `random` 在整个 `handle` 作用域内成局部变量，执行到 :2716 本地回退 `random.choice(cand)` 时抛 `UnboundLocalError`，`/悟丹`、`/悟器`、`/生成丹药`、`/生成法宝` 在离线/AI 关配置下恒 500；修复为删除 handle 内 3 处 import 仅留模块顶层 :11，全仓 AST 扫查无同型遮蔽；CA-002 `stone_loss`——brute_force 实扣 40 灵石而面板显示「发掘灵石 +0」：引擎 `core/treasure_system.py` 13 个返回分支如实填 `stone_loss`（brute_force 40，其余 0，扣款行一字不动），`/挖宝` 分发只增透传 `stone_loss: res.get("stone_loss", 0)`（无硬编码 40），前端宝图面板改读 `stone_loss`（>0 显「灵石损耗 −40」，=0 整行省略）；CA-003 遗物分支结算面板不可达——得宝幕弹出即移除宝图 dialog，结算 HTML 写入已 detached 的 `#treasureStageBox` 永不重现：修面限于面板/仪式叠演顺序，得宝幕仍按 GF3-QA-01 立即转交，结算 HTML 落袋后暂存 `state.pendingTreasureDialog`（仅真弹幕时），关闭得宝幕（略过/✕/背景）后恢复重开含遗物行，自动略过时不暂存；CA-004 洞府捏造——`renderSanctum` 删 3 处静态写死展示值（神识感召 4,850 步、宗门道勋太上长老、九天碧玉太虚剑/剑灵觉醒/锋芒 9,880），改读真实 `status.rank` / `status.equipped` / 器灵数据
- P1×1、P2 修复×8 + 定性×3：寿元口径统一 `fmtRemYears`（CA-005）、地牢 debuff 通用 chips（CA-013）、写分支补 `status` 透传（CA-014/015/016/017/021）、移动端透传覆盖（CA-037）；定性不修 CA-018/019/020（代码与抓取均已透传，以锁定测试固化）
- CA-011 补键（总管裁决②）：`_status_dict` 只增 `custom_arts` 只读回显字段，数据源为角色行上已存储的自创功法，不新增计算、不新增存储语义、不改任何既有键
- CA-023 勘误（总管裁决③④）：`/omen` 别名落于 `/望气` 条目 aliases（`/echo`、`/天象`、`/omen`），确认此形态，不另立 `/天象` 条目（另立会使命令数 108→109 触既有断言）；分发 :1959 一字不动，:2058 元组中已不可达的 `/omen` 死代码删除
- CA-006 勘误/返工（总管裁决⑥）：命盘功德/业力格 `s.merit || 3650` / `s.sin || 120` 的 falsy-零陷阱使新角色（初值 0）命盘显示「+3650 / -120」，改 `??` 判空（缺失显「—」，0 渲染 0），live 洞府回退种子 3650/120→0/0，demo 种子不动；`rem_years` 缺失态整串显「—」不带单位（新 `remYearsUnit(v)` 后缀 helper，调用点保持 `fmtRemYears(s.rem_years)` 形态，既有字面断言不动）
- CA-007 勘误/锁定（总管裁决⑤⑧）：台账「从不下发 adventure 键」的前提不成立——`/探险` 成功路径真实下发 `"adventure": res`（抓取 151 号采的是无参看板路径），前端结构分支正确保留未删，补锁定测试断言成功路径下发与渲染对应
- CA-070 只评估（结论见台账）；评审 must-fix M1–M4 返工：M1 缺失态整串「—」、M2 六组合结算不丢且 ✕ 不顺延、M3 全仓坏模式扫描补齐且变异可红、M4 键数 78 三方一致
- 契约层：新增 `tests/test_contract_audit.py` 30 用例（CT-01 三类断言：双向差集、全仓坏模式扫描、真实 payload 渲染执行），评审人实跑 30 passed；V2 先红后绿留档见 `~/workspace/reviews/contract-audit-rework-V2-failfirst.md`

### 测试
- QA 全量回归（新鲜 DB，连跑两次）：run2 1387 passed / 8 failed——失败集与操作基线逐项一致（auth join、karma kill_and_bounty、lan_feed、natural_omen、qa2 join_dead_http、status_dict×2、workbench smoke），新增失败 0；run1 1386/9，多出 1 条为既有日期依赖型 pawn flake（`test_pawn.py::test_world_handle_pawn_chain`，市价 md5 日种子波动致断言 `s0 + 20` 得 21，返工 diff 不触 pawn/market 任一文件）
- 定向 RG-03 套件 100 passed
- 独立评审：首审 must-fix M1–M4 → 返工 `1b9e2b6` → 复审结论「通过（可发版）」，9/9 核销无 must-fix（`~/workspace/reviews/contract-audit-rereview.md`）；红线零触碰：新增响应键仅预批的 `stone_loss` 与 `custom_arts` 两只增只读键，数值语义零改动，mobile.js/css 零改动（1645 行 / 27395B，硬线 ≤1660 行 / ≤27455B 未触），`core/ceremony.py` / `core/breakthrough.py` 零改动，既有断言修订 0 条

## v0.3.11-gray.18（2026-11-08）— 宝图开箱面板「攻伐 +undefined」修复

定位：缺陷修复轮。上一稳定点 v0.3.10-gray.17（c0d7b98）。分支 `feat/treasure-panel-stats-fix`（`9d5c585` + `a4a5636`）。

### 变更
- 根因：联机 `/挖宝` 返回的 `equipment.stats` 是引擎键（武器掉落恒为 `{power: N}`，如 tier3 为 198），面板却写死渲染 `stats['攻伐威能']`——该键服务端不存在（只存在于 `web/workbench.js` 两个本地对象），联机开箱恒显示「攻伐 +undefined」
- 修复口径（`web/workbench.js` +87/-35，净 +52 行；纯呈现层，未动服务端数值与规则）：新增纯函数 `treasurePanelStatLine`，按优先序 power（攻伐）> phys_atk（物攻）> spell_atk（法攻）> defense（防御）> max_hp（气血）> max_mp（真元）> speed（身法）> phys_def（物防）> spell_def（法防）> crit_rate（暴击）> crit_damage（暴伤）> sense_range/divine_sense（神识）> illusion_resist（幻抗）> pierce（破甲）> lifesteal（汲取）> mind_guard（护心）> charm（魅力）取首个存在且 >0 的数值键，浮点截断至两位小数去零；无可用键（遗物 `stats={}`、零值、非数值、缺失）时整行省略，永不渲染 undefined/NaN；未知旧中文键直接忽略
- 同面板审计：词缀改渲染 payload 实际 `affixes`（服务端随机抽取），无词缀整行省略；字段缺省（name 缺省「无名法宝」、slotCn 缺省「法宝」、lore 缺省「天地造化所钟之奇珍。」、tierName 缺省空；glyph 按 slot 取值）；brute_force/combat_victory/scar_created 无 pill、brute_force 无 stone_gain 且实为扣灵石、combat_defeat 无装备/丹药/灵石——此前三处本地推断在联机模式下凭空捏造战利品，现仅限 Demo 模式，联机无装备时面板改为「破阵而出 · 未得机缘」+ 未得法宝占位卡，灵石按服务端实返显示，toast/feed 与「立即佩戴」按钮同步按有无装备分支；两处本地 fallback stats 改为真实引擎键（演示剑 `{power:160, pierce:45}`、开箱推断 `{power: tier>=3?180:90}`）；桌面其它路径全仓仅此一处写死引用，移动端无开箱面板、无须改动
- 删除根目录三份旧副本 `index.html` / `workbench.css` / `workbench.js`（最后实质改动 2026-09-24 / 2026-10-13，web/ 对应文件为 2026-11-06~08；根 `workbench.js:2571/:3015/:3077` 仍含本缺陷）：`server/app.py:254-259` 在 web/ 缺失时兜底服务根目录同名文件，Dockerfile 只 COPY web/，线上虽不受影响，缺陷仍以可达 fallback 形式留在仓内；删除前全仓复核无任何代码引用根目录副本（启动脚本、Dockerfile、docs、tools 皆指 web/），故删除三文件、`server/app.py` 不改，缺失时兜底只会 404，不会复活旧缺陷

### 测试
- 新增 `tests/test_treasure_panel_stats_contract.py` 7 条（静态契约：真实键 ⊆ 渲染口径、写死中文键/词缀芯片消失、fallback 键 ⊆ 真实键、捏造仅限 Demo、根目录旧副本删除守卫；node 执行渲染断言：tier3 武器 power 198 →「攻伐 +198」、遗物 `{}`→省略、phys/spell/defense/max_hp/crit_rate 回退、零值/非数值/旧中文键→省略，全程无 undefined/NaN）
- 全量回归（新鲜 DB）：1357 passed / 8 failed——7 条基线失败全部复现（无新增确定性失败）+ 1 条既有 flake（`test_living_jianghu::test_lan_feed_endpoint_contract`，全量顺序下失败、删库单跑全绿）；零新增失败
- 桌面真实 UI 截图验收通过（`~/workspace/ui-shots/treasure-panel-fix/`）：T1 主正例 tier3 五行破阵「攻伐 +198」无 undefined；T2 凶地守卫胜利「攻伐 +77」；T4 战败「破阵而出 · 未得机缘」无 undefined；T3 遗物分支结算面板被得宝仪式覆盖不可达（GF3 双幕协议既有行为，本分支未碰仪式/队列/z-index，不阻塞放行，另立工单）；首挖奇遇条遮挡结算面板页脚约 25px（既有布局问题，不阻塞放行，另立工单）
- 跟进（本轮不做）：S-3 brute_force 面板灵石 +0 与服务端实扣 40 不一致，需服务端 stone_loss 字段，另立跟进

## v0.3.10-gray.17（2026-11-08）— 游戏感改造第三期（仪式补全三幕 + 入局待回应最新优先修复）

定位：游戏感改造第三期。上一稳定点 v0.3.9-gray.16（76310b4）。规格：docs/compose/spec/game-feel-phase3.md。

### 变更
- 仪式补全三幕（方案 §4c 六幕全集收官）：`core/ceremony.py` 新增 3 个只读 builder + 1 个门槛谓词——得宝幕（`build_loot_ceremony`，谓词 `(equip ∧ tier≥4) ∨ (relic ∧ tier≥3)`，挂点仅藏宝图开匣与盲匣捡漏两处真实落账点，result_ref 以开匣 equipment dict 逐项对账）、器灵认主幕（`build_spirit_ceremony`，唯一信号 = `ArtifactSpiritEngine.awaken` 的 `changed=True`，台词走本地性格台词池、零 AI）、天劫独立幕（`build_tribulation_ceremony`，与突破同一次结算拆双幕呈现）；三幕均为既有落账的只读呈现，零新增结算/数值/状态机，仪式路径零新增 AI 调用
- 双幕协议（只增不改）：突破两出口响应 `ceremony` 改挂天劫幕（第一幕），新增只增键 `ceremony_next` 承载突破幕（builder 与 beats 一字未改，命格三选一 choices 只留在第二幕）；致死时只有天劫幕、`ceremony_next` 为 null，死亡幕仍走 dead_payload 既有口径
- 服务端挂点（`server/world.py` 四处，只增键）：`/挖宝`、`/捡漏` 分发 return 只增 `ceremony`（得宝幕）、`/器灵` 唤分支 return 只增 `ceremony`（认主幕）、突破两出口改挂双幕；桌面宝图流转交得宝幕、捡漏 gamble 面板达幕时不叠开（QA GF3-QA-01）
- 双端呈现：桌面与移动端 kind 文案表各原地补 loot / spirit / tribulation 三项、自动略过名单原地扩三 kind、桌面标题图标补 loot/spirit；双幕队列呈现（第一幕跳过/看完后第二幕自动呈上，两幕略过互不吞没）；移动端预算内施工，未申请豁免
- briefing ⑤.6 待回应戏剧最新优先修复（二期复审 S-1/S-2/S-4）：`core/briefing.py` `build_entry` ⑤.6 段改为最新→最旧逆序迭代补列（至多 2 条未入队项），待回应 ≥3 件时刷新版 entry 的 queue 必含最新一条；补列项 id 同步登记 `_queued_refs`（S-2 一行防御）；注释口径与新语义对齐（S-4）；`DramaEngine.list_pending` 本体、queue 的 priority/sort/截断口径一律未动
- 零变更清单：`core/breakthrough.py`、`core/npc_proactive.py`、`core/artifact_spirit.py`、`core/treasure_system.py`、`core/fate_thread.py` 未改；无新表、无新模型字段、无新 config、无新命令、无新资产（配图复用既有 139 张图库资产键）

### 测试
- 本轮新测试：test_game_feel_phase3_backend.py + test_game_feel_phase3_frontend.py 共 39 条（LT-01~07 得宝 / SP-01~06 器灵 / TR-01~08 天劫双幕 / BR-01~05 briefing 修复 / FE-01~03 双端呈现），分支尖端实测全绿（39 passed）
- 独立评审通过、must-fix 为零；QA 复验销账 GF3-QA-01（桌面宝图流转交得宝幕 + 捡漏 gamble 面板达幕不叠开，尖端 0d8e8c0）
- 合并后在 main 上复跑定向套件（phase3 后端/前端 + phase1 后端 + mobile_web）确认全绿后打 tag 发布

## v0.3.9-gray.16（2026-11-08）— 游戏感改造第二期（命途主线全量 + 主动戏剧五类 + 世仇植入 + 图库扩充至 139 张）

定位：游戏感改造第二期。上一稳定点 v0.3.8-gray.15（c4c4571）。规格：docs/compose/spec/game-feel-phase2.md。

### 变更
- 命途主线全量：新表 fate_threads + 新模块 core/fate_thread.py——种子六级优先级（未竟之志 / 世仇 / 影子最强 / 本世血仇 / 宗门大势 / 出身兜底）、6 章骨架（立命 / 经营×2 / 冲突 / 高潮 / 暮年）、章节状态派生自 checked goal（新增 check kind：visit_location / promise_kept_count / chain_resolved）、窗口到期改道不断线、/命途 搁置与续（不删不罚、顺延窗口）、死亡封存（结局入 LifeTrace、未竟之志回流下世）；主线模块自身零数值（静态检索 + 无线对照组逐项对账双证）、零 tick 扫描
- 前置收紧 S-4：goals 幂等键由 (source, kind, ref) 收紧为 (source, kind, ref, instance)，存量无 instance 目标归一回退，一期 origin/fate 目标行为不回归
- 世仇强制植入：转世时按三来源（上世血仇链 / KarmaLink 仇孤儿行 / 负值影子）选人，经 origin 既有通道植入（foe bounds 硬校验、超界降级同门/后人、影子覆盖者不叠加态度），出身关系、态度账、KarmaLink 仇边、主线种子四处一致对账
- NPC 主动戏剧五类：DramaEngine（背叛 / 挑衅 / 牵连 / 求助 / 示好）扩 NpcProactiveEngine，频控三闸（总闸 3 件/日、同人同日 1 件、示好不占总闸），待回应队列常驻入局 + 新命令 /回应 单一分发落账；后果全走既有系统（斗法 / 态度账 / 诺言与因果链结算 / 钳制内发酵微调），戏剧本身零数值发放
- 传闻写入口补全：突破 / 因果链了结 / 世界弧参与 / 避战四入口（引擎单点 + 去重），玩家事迹经 lore_prompt_block 进入 NPC 交谈上下文，他人可引用
- 一生评语 AI 润色（可选路径）：评语分段（head / line / tail）落 LifeTrace 新字段，润色只替换定性段，请求 payload 数值白名单、违规输出逐字保留模板，死亡流程锁外异步单次调用、失败不阻塞结算与转世
- 呈现契约（双端，只增不改）：_status_dict 增 fate.thread 与 location_image、入局 queue 增 fate_chapter / drama 两 kind、交谈开启响应增旧账行（未了诺言 / 发酵中因果 / 最近关系变化）；新命令 /命途、/回应（命令目录 106 → 108）
- 图库扩充 38 → 139 张：NPC 单人图 37 张（uid ↔ 资产键 ↔ 文件三方一致）、玩家立绘补满 20 组合（合体 / 大乘 / 渡劫专图不再借图）、灵宠 4、地点与秘境场景 15、法宝器型 10 → 20 键、功法 8 → 10、藏宝图 4 → 8、补足包 21（奇遇剧本专图 6 + 丹药分类 8 + 材料分类 7）；图鉴分组程序化扩至 139 与五档称号；/assets 托管闸扩展新目录（pets / scenes / omen / goods）
- 移动端预算豁免（Spec §10 总管批准）：mobile.js 上限 1562 → 1892 行、mobile.css 上限 27400B → 28800B；token 纪律不豁免

### 测试
- 最终全量回归（新鲜 DB，分支尖端复跑定版）：1311 passed / 8 failed——失败集与 v0.3.8 基线（1217 passed / 8 failed）逐条相同，新增失败 0（基线 8 条 = 裁决遗留 ×2、status_dict rich-object ×2、natural_omen 出厂背包 ×1、karma C-1 分歧 ×1、karma resolution_traces ×1、workbench live-server smoke ×1）
- 本轮新测试：test_game_feel_phase2_fate.py 35 条（S4 / FT / VD / EP / UI 组）、test_game_feel_phase2_drama.py 27 条（DR / RM 组）、test_game_feel_phase2_gallery.py 31 条（GL-01 ~ GL-14），全绿
- 独立评审：主体 must-fix 2 条（M-1 章节求值补搁置豁免、M-2 图鉴旧总数文案）已修复销账；截图验收问题 2 条（待回应戏剧常驻列出、桌面交谈旧账行重渲染）与示好排除出身植入关系 1 条均已修复，尖端形态经收尾独立复审通过、无 must-fix
- 截图验收 15 张（~/workspace/ui-shots/game-feel-phase2/，桌面 S-D1 ~ D7 + 移动 S-M1 ~ M6 + 补充 2 张）

## v0.3.8-gray.15（2026-11-08）— 游戏感改造第一期（入局主界面 + 简版人生开局 + 仪式两幕 + 关系可见化）

定位：游戏感改造第一期。上一稳定点 v0.3.7-gray.14（90ce9c8）。规格：docs/compose/spec/game-feel-phase1.md（派生自《游戏感改造方案》第一期）。

### 变更
- 入口重做：登录后先入局——结构化入局（今日局势三线 + 事件队列 ≤3 高亮、其余折叠，每件是指向既有玩法的指针）；工作台/命令/敕令栏退为工具层，行为零阉割；双端默认动线同步；登录路径零新增 AI 调用，登录耗时双口径实测不劣化（拼装 ratio 0.66 / 链路 ratio 1.09）
- 简版人生开局：新模块 core/origin.py（纯规则、零 AI）——五维模板出身包全随机 + bounds 钳制（灵石 ∈[80,260]、债 ∈[0,120] 落诺言账旧债、亲近 +25..+55 / 敌视 −45..−15 且敌视者境界 ≤ 起始 +1、关系 NPC ≤4、路径关闭 ≤1 且生存主干恒开），与本账户最近 3 世防重，极端坏命附逆袭机缘种子；落账全走既有设施（shift_attitude 唯一写入口、诺言账、钱包、KarmaLink 种子边），不建 fate_threads 表
- 分层目标简版：短期判定式目标 + 终局命题定盘，到期未达成转未竟之志（下世命题头号候选）；一生评语模板版与 LifeTrace 同次生成，落墓碑/死亡转世仪式/下一世出身卡「前世曰」三处；出身卡双端呈现。第一世全生成，转世只做未竟之志 + 影子合并（世仇强制植入属第二期）
- 仪式演出两幕：突破幕（命格三选一只走既有道途赐福/词缀通道，战力乘子封顶 1.15）+ 死亡/转世合并幕；先结算后演出、只读 ceremony 结构、不落库、可跳过可设自动略过、零新增 AI、零锁内耗时增长；新命令 /命格 1 条（命令总数 99 → 100）
- 关系可见化：shift_attitude 唯一写入口挂 RELATION 留痕（变化原因与幅度可查），双端展示关系与最近变化
- 移动端预算豁免（spec §9.1 批准）：mobile.css 上限 25702B → 27400B（实测 26599B）、mobile.js ≤1562 行（实测 1561 行）；token 纪律不豁免

### 测试
- 最终全量回归（新鲜 DB，HEAD 0f206b2）：1217 passed / 8 failed——其中 7 条为既有有效基线逐字对应（join 裁决遗留 ×2、status_dict rich-object ×2、natural_omen 出厂背包 ×1、workbench live-server smoke ×1、karma C-1 分歧 ×1），2 条已知 flaky 本轮全绿；第 8 条 farm_chain 经裁决为出身出生地新契约的同根夹具问题（与 meditation_gate 同源），按 Spec §7.5 补裁同式修订夹具后连跑 3 次全绿、test_farm.py 全文件 22 passed
- 契约变更裁决（Spec §7.5）：r9「出身恩怨随影入轮回」+ 6 条旧断言按出身新契约修订（灵石期望由 origin.stones_final 推导），全部转绿
- 本轮新测试：后端验收 23 条 + 双端前端契约 + 返工回归 rework 6 条 / rework2 2 条全过；出身 200 包对账（bounds 失败 0、死局样本 0）
- 独立评审 must-fix 4 条（入局拼装陈旧覆写、仪式命格 choices 错位、未竟之志 kind 映射缺失、MF-1 修复引入的 briefing 面 fate 行回归 MF-R1）全部修复并逐条复审/QA 销账
- 截图验收 13 张全过（~/workspace/ui-shots/game-feel-phase1/，桌面 7 + 移动 6）

## v0.3.7-gray.14（2026-11-08）— 图库与玩法丰富版（AI 图库 + 寻宝线索链 / 法宝器灵 / 奇遇补强 + 图鉴）

定位：图库与玩法丰富版。上一稳定点 v0.3.6-gray.13（cc92fab）。

### 变更
- AI 图库：38 张统一水墨修仙风图片（人物男女×6 境界 + NPC 原型 4 / 法宝 10 / 功法 8 / 藏宝图 4）经 `/assets` 双闸托管上线
- 视觉接入（双端）：定相与人物图、NPC 头像、法宝图 + 五档品阶图框、功法图、宝图图，桌面端与移动端同步接入
- 寻宝线索链：挂图实体状态机、独立小账、日限；终局开匣仍走现有挖宝结算
- 法宝器灵：tier≥4 已穿戴法宝可唤灵，温养 / 灵语、心情与战力加成
- 奇遇补强：六剧本配图、后果接因果 / 诺言 / 江湖痕迹；600s 冷却与日限 5 正式生效，交谈内奇遇分支豁免频控
- 图鉴：账户级 KV、38 键点亮、只给展示称号零数值，双端上线
- 移动端图库 CSS 全量 token 化适配设计系统；R-21 体积预算第二次豁免（CSS ≤25.1KB、js 净增 ≤190，spec gallery-gameplay §15 记录）

### 测试
- 最终全量回归：1188 collected / **1179 passed / 9 failed**——有效失败为既有基线 7 条（join 裁决遗留 ×2、status_dict rich-object ×2、natural_omen 出厂背包口径 ×1、workbench live-server smoke ×1、karma C-1 既有分歧 ×1），另 2 条抖动（faction/farm）单独重跑通过，新增失败 0
- 本轮新测试 81 例（G/T/S/E/C 五组）全过
- 独立复审 1 条 must-fix（奇遇冷却误拦交谈分支）已修复并复审销账
- 截图验收 15 张全过（`~/workspace/ui-shots/gallery-v037/`）

## v0.3.6-gray.13（2026-11-07）— 移动版视觉与体验重做（设计系统双天象、字阶、组件规范、坞区整治）

定位：移动端视觉重做版，无新玩法、无数值口径变更、无接口变更。上一稳定点 v0.3.5-gray.12（57540c8）。

### 变更
- 设计系统：双列 token——昼·翡翠宣纸（沿用实际桌面家族）/ 夜·深墨蓝描金（取 `style.css` token）；字阶、间距/圆角、组件规范统一
- 导航：五图标改为内联 SVG，去除文本符号；选中态金色 + 顶线 + 底色三重信号
- 门庭仪式感：夜空背景 + 双环印章 + 分段页签；坞区总高预算 ≤164px（导航 56 + 命令坞 ≤60 + 快捷条 ≤48）
- 根治 M-10 脆弱模式：行内按钮铁律（flex 行内按钮 `flex: none`、`min-width: 76px`），回归断言 R-13
- `mobile.js` 仅最小结构配合，逻辑零变化；`server/app.py`、桌面三件套、`core/` 零改动；无外部字体/CDN、无新增静态文件、无新增图片请求

### 测试
- 合并后 main 全量回归（1106 collected，31 分钟）：**1096 passed / 10 failed**；
  其中 8 项与 v0.3.5 失败清单逐项相同（6 基线 + 2 flaky），另 2 项
  （`test_settle_pass_effects_and_idempotent`、`test_tick_budget_limits_public_events`）
  为全量顺序/状态依赖（本轮跑在 lived-DB 工作区），独立重跑通过；新增失败 0
- 终验 QA（新鲜 DB，worktree）：8 failed / 1053 passed vs 基线 8 failed / 1047 passed，新增失败 0
- 契约测试：`tests/test_mobile_web.py` + `tests/test_qa2_frontend_contract.py` 16 passed（rebase 后复跑）

## v0.3.5-gray.12（2026-11-06）— NAS 注册/登录很慢修复（超时收紧、去锁化、计时日志、熔断器）

定位：登录/注册延迟修复版，无新玩法、无数值口径变更。上一稳定点 v0.3.4-gray.11（0643434）。

### 变更
- LLM 默认超时 30→12 秒（`.env` 的 `LLM_TIMEOUT_SECONDS` 可调，区间 5–120）；CC Switch 分支 `max(timeout, 30)` 下限与 `_chat_json` 非 200 二次尝试、director/gateway 写死 `timeout=25` 一并收紧；单次 AI 最坏耗时从约 66 秒压到约 15 秒
- 登录/注册去锁化：读路径走锁外 DB 快照，写路径有界获取（2 秒界内拿不到锁返回 503 `SERVER_BUSY` 可重试，繁忙即未写）；`join` 内判定/收养/结算/建角/发 token 仍在短临界区内串行，语义不变
- 计时日志：HTTP 请求 method/path/status/duration_ms 与 tick 分阶段计时（`log_event` JSONL），不记请求体/token/密码
- 熔断器：AI 中继连续失败达阈值后快速失败、半开探测恢复；叙事降级为已接受 trade-off，本地模板兜底全覆盖
- MF-1：首夜陈旧写回收——first-night 写回改为有界获取，拿不到则跳过
- MF-3：`login` 只验密不写 `last_login`，写操作只在 app 层实际发会话后发生

### 测试
- 合并后 main 全量回归（干净库口径，1100 collected）：**1092 passed / 8 failed**，
  23 分钟。复审口径 1083 passed / 7 failed（1090 collected，不含手机端测试）；
  合并后多出的 10 个测试全为手机端新增（`test_mobile_web.py` 7 + `test_web_hosting.py` 3），
  全部通过；无新增失败
- 8 项失败全为既有：6 项稳定失败与基线一致（独立重跑复现）——
  `test_world_join_requires_explicit_nonempty_authenticated_uid`、
  `test_qa2_join_dead_http_and_anonymous_unchanged`（join 匿名语义裁决遗留）、
  `test_status_dict_includes_bag_and_marks`、`test_status_dict_follows_real_equip_flow`
  （status_dict rich-object 裁决遗留）、`test_initial_character_and_config`
  （natural_omen 碰撞牺牲项）、`test_login_then_look_here`（workbench live-server
  smoke，HTTP 401）
- 另 2 项为顺序/状态依赖抖动（独立重跑通过）：`test_kill_and_bounty_single_chain`
  （C-1 bounty divergence 既有）、`test_local_director_run_persists_and_channel`；
  `test_qi_pace` 与 `test_lan_feed_endpoint_contract` 本轮全量通过

## v0.3.4-gray.11（2026-11-06）— 手机端独立页面（单列+底部导航，自动分流）

定位：移动端体验版，无新玩法、无数值口径变更。上一稳定点 v0.3.3-gray.10（0b43abf）。

### 变更
- 手机端独立页面 `web/mobile.html` + `mobile.js` + `mobile.css`：单列布局、底部导航
  （命盘/行囊/坊市/世界/聊天等视图映射桌面端）、顶部状态条、常驻命令区
- 根地址手机 UA 自动进移动版，桌面 UA 停留桌面版；双向切换按钮并记住选择；
  `?view=mobile|desktop` 仅本次生效（逃生口）
- 游戏服白名单新增 `/mobile.html`、`/mobile.js`、`/mobile.css`（与既有托管一致，no-cache）
- 文档同步：`docs/gray-runbook.md` 与 `web/README.md` 增加移动版入口说明；
  spec `docs/compose/spec/mobile-web.md` 状态更新为已发布

### 测试
- 目标测试 23 passed（`test_mobile_web.py` 7 passed + `test_web_hosting.py` 16 passed，
  合并后 main 上重跑确认）
- 独立评审通过，无 must-fix；QA 有条件通过后 M-10 缺陷已修并经独立复测通过

## v0.3.3-gray.10（2026-11-06）— 登录页去掉宗门阵枢输入框，同源直连

定位：部署体验收尾版，无新玩法、无数值口径变更。上一稳定点 v0.3.2-gray.9（218b5aa）。

### 变更
- 登录页去掉宗门阵枢（服务器地址）输入框：页面同源直连游戏服，玩家打开
  `http://<地址>:8765/` 一个网址即是登录页，不再需要填服务器地址
  （spec：docs/compose/spec/remove-server-input.md）
- 默认阵枢改为 NAS 公网域名 `mn.20230803.xyz:8765`（需求变更，见 spec 内记录）：
  含宗门阵枢默认地址两提交 `2626704`（登录页不再默认 127.0.0.1，远端打开时
  忽略存下的本机地址）与 `218b5aa`（默认地址改为 NAS 域名）
- 收尾改动：spec 与 web/README.md 玩家指引同步改为 NAS 域名
- 已披露例外（评审裁定接受，不改）：本机回落分支（workbench.js:147 与
  app.js:18 的 localhost/file: 回落 127.0.0.1:8765）保留

### 测试
- 全量回归 1036 passed / 9 failed（基线 1034 passed / 9 failed，+2 为
  2626704 与 218b5aa 各新增的 1 条托管测试，无新增失败）；契约 + 托管 16 passed
- 独立评审通过，无 must-fix

## v0.3.2-gray.9（2026-11-06）— 游戏服托管网页（一个网址即玩）

定位：部署体验修复版，无新玩法、无数值口径变更。

### 变更
- 游戏服直接托管玩家页面：`GET /` 与 `/index.html`、`/app.js`、`/style.css`、`/ailog.html`
  由 server 按精确白名单发出（text/html、text/javascript、text/css，均带 charset=utf-8
  与 Cache-Control: no-cache）；玩家打开 `http://<地址>:8765/` 一个网址即是登录页，
  页面自动连同源服，不再需要单独打开 web/index.html 文件、不用填服务器地址
  （输入框保留，可手动连别的服）
- 白名单外路径维持现状：全部 API 路由形状不变，`/prototype.html` 不对外，
  路径穿越在构造上不可能（文件名全是代码常量，不拼用户输入）
- 部署文档对齐：docs/nas-deploy.md 改为一个网址玩法为首选，本地文件法降为备用，
  单入口代理降为可选；公网路线只转发 8765 即可

### 测试
- 新增真实 HTTP 测试 11 例（静态 5 路径逐字节一致、响应头、穿越 8 变体全拒、
  /health 与 /ailog JSON 不回归）；全量基线 719 → 730
- 隔离服实证：页面自服地址同源加载，桌面宽截图确认登录页渲染正常

## v0.3.1-gray.8（2026-11-05）— AI 天道事件链

定位：新玩法版（spec：docs/compose/spec/karma-event-chains.md）。上一稳定点 v0.3.0-gray.7。

### 内容
- AI 天道事件链——五源起链：态度跨阈 / 关系边 / 诺言终态 / 击杀血仇 / 悬赏续链，五类源头自动起链。
- 发酵与兑现：发酵迁移与兑现结算受子顶与每日预算约束（单链兑现子顶、每玩家每日兑现数与灵石子顶、单轮 tick 预算），寿元恒零（链兑现不改寿元）。
- /因果链 双端面板：CLI 与 Web 双端可查因果链状态、发酵进度与近史。
- 死亡随旧世消散与转世衔接：角色死亡时因果链随旧世消散，与转世继承衔接，不跨世残留。
- 赠礼态度计价改革（评审返工）：赠礼/人情的 attitude 增量按实付灵石 + 所赠物品目录价计价，废弃旧固定增量；态度从 0 冲到 60 的最低灵石成本恒 ≥300。

### 评审与 QA
- 独立评审 must-fix 5 条 + OBS-1/2 经复审全部销账。
- QA 全量回归 719 passed 0 failed；隔离冒烟 + AI 实测通过。

## v0.3.0-gray.7（2026-11-05）— 转世继承玩法

定位：新玩法版（spec：docs/compose/spec/reincarnation-inheritance.md）。上一稳定点 v0.2.4-gray.6。

### 内容
- 前世留痕：墓碑 / 编年史 / 传闻，前世事迹在世界中留痕，新角与世人可查可闻。
- 因果影子衰减继承：前世 NPC 态度以衰减系数继承为因果影子（基准保留 40%、上限 25、门槛与条数上限见 config SHADOW_*），不全量带入新世。
- 继承抉择新增三选：遗物留存（heirloom，5 点，每世限 1 件）、前世心法（art_memory，4 点，每世限 1 门）、旧缘重续（bond_echo，3 点，影子衰减减弱至保留 75%、上限 50）；既有四项抉择顺序与数值不变，新键只追加在末尾。

### 评审与 QA
- 评审 must-fix 全部修复并销账。
- QA 全量回归 689 passed 0 failed；QA 冒烟通过。


## v0.2.4-gray.6（2026-11-05）— UI 修复第二轮：首屏舞台空白与手机端左栏挤压

定位：纯前端修复版（仅 web/app.js、web/style.css + 新增 Spec），无游戏规则、无 API 契约、无数值口径变更。上一稳定点 v0.2.3-gray.5。

### 内容（Spec：docs/compose/spec/ui-fix-round2.md）
- 修复注册首屏舞台空白：确诊为入世区页签污染舞台页签切换——入世区页签绑定误伤舞台页签状态，致首屏舞台区空白；采用双保险修法（绑定隔离 + 切换兜底），注册后首屏舞台正常呈现。
- 修复 ≤780px 左栏横排挤压：窄屏下左栏改为纵向单列 + 栏内纵滚，消除命盘/行囊横排挤压与右侧裁切。

### 评审与 QA
- 独立评审无 must-fix。
- QA 全量回归 674 passed 0 failed，与基线持平；契约测试 3 passed；动态验收全过、冒烟全 200。
- 真机截图验收通过（v0.2.3-gray.5 目视检查发现的两处缺陷——首屏舞台空白、手机端左栏挤压——已修复确认）。

## v0.2.3-gray.5（2026-11-05）— web UI 优化

定位：纯前端优化版（仅 web/app.js、web/index.html、web/style.css + 新增 Spec），无游戏规则、无 API 契约、无数值口径变更。

### 内容（Spec：docs/compose/spec/ui-polish.md）
- 视觉语言统一：修仙美学打磨，界面风格一致。
- 寿元/因果/势力可视化：核心数值与关系以可视化形式呈现。
- 流程打磨：登录/命盘/行囊/死亡转世流程优化。
- 移动端与无障碍底线：移动端布局与无障碍基线保障。

### 评审与 QA
- 评审 must-fix 已全部销账通过。
- QA 全量回归 674 passed，与基线持平；唯一缺陷 D1 经复核为误报（.demon-opts button 早已有 min-height:44px，无需改动）。

### 已知残留
- 真浏览器目视未做（QA 已做过隔离冒烟，目视检查仍待补）。

## v0.2.2-gray.4（2026-11-04）— 账户层死亡资金归集与死后建角 + 一人公司技能

定位：一人公司编制首个完整执行轮次——先落技能文件（7 岗编制与协作规矩），再按编制完成账户/死亡重建改造。核心不变：寿元硬通货、规则引擎裁决数值、LLM 只叙事/NPC 言行；价格/费率/抽成/道统公式/出生灵石 150 全部零变更。

### 新增（一人公司技能）
- `.agents/skills/one-person-company/SKILL.md` 与 `.claude/skills/one-person-company/SKILL.md`（内容一致）：总管、主策/需求官、后端/规则工程师、前端工程师、测试工程师、评审官、发布/运维 7 岗专属描述，协作规矩（spec 契约先行、worktree 隔离、谁写谁不审、评审只审不改、测试不过不合并）与 8 步标准流程；与 requirement-evaluator 无冲突（组织层与方法层关系）。

### 新增（账户/死亡重建，spec：docs/compose/spec/account-death-rework.md）
- 账户钱包：`LegacyAccount` 扩展 `wallet_stones` + 50 条流水；角色死亡后随身灵石与寄存灵石归集入账户钱包，仍挂原玩家名称；新角出生随身 150 不变，钱包须经 `/钱包提取` 显式划转（零手续费），不自动划转。
- 死亡挂起三项定案（此前 QA 遗留）：死者寄售成交款按 `seller_user_id` 路由入钱包（旧单回填、不可考拒售且买家不扣款）；死者拍卖冻结出价死亡时退钱包、拍品回起拍，死后落槌净额入钱包，落槌兜底防钱物双得；未结算议政票作废，已结算快照不变。
- 登录与建角：Web `/login` 死者不再静默建角，返回 dead payload（死因、享寿、道统、钱包、归集明细），建角须显式 `/转世`；带 `user_id` 的 `/join` 死者同款处理，匿名 `/join` 不变；CLI 结算页与建角引导同步；同账户新角不得买回自己旧世寄售单/拍品。
- Web 界面三处：死亡结算页（归集明细表、钱包余额、显式转世入口）、命盘钱包行（余额、流水、提取入口）、建角引导三要素。
- 迁移：`tools/migrate_account_death.py` 演练脚本（只跑演练库，拒绝真实数据目录）+ 补扫（已结算旧行首次触达时幂等补扫）；已转世覆盖的旧行金额无结构化记录，不可追回、不捏造补发。

### 评审与 QA
- 独立评审有条件通过后修完 5 项 must-fix：sweep 后落入死行的钱（超价退款改道钱包 + 残差处理 + 双入口统一）、`/join` 死者绕过、旧世自买回流、T15 迁移缺失、sweep 异常吞没；同批修 T13 寄售单数/享寿/局内死亡明细等。
- QA 最终验收另抓 2 缺陷并修完：首笔 sweep 崩溃重放双记（breakdown 显式字段 + `death_settled` 门限重放判定）、归集报告毛额口径（只计实际入账）；残差同额误判等极窄边界已如实记入 spec §2.7 第 10 条。

### 测试与结论
- 新增测试 53 例（账户/死亡 36 + QA 验收 17），全量基线 621 → 674；最终验收连续 3 次全量 674 passed 0 failed。

## v0.2.1-gray.3（2026-11-04）— 跨功能 QA 修复版

定位：两轮独立跨功能审计（经济/寿元/战力/因果/宗门/状态机/双端契约/存档兼容
八域矩阵）的缺陷修复版，无新玩法、无数值口径变更（除订正文档）。

### 修复（除凶与因果账）
- QA-02（S1）：凶犯洗清后、除凶令在接令/悬赏板等访问点被 sweep 之前被击杀时，
  settle_kill 现于结算刻复核洗清——洗清成立则令 DISSOLVED、协剿不发功德；
  主诛者旧悬赏一并裁定不发（令消解「无奖惩」口径，见 hunt spec 裁定）
- QA-01（S2）：除凶结令业力消解去双路——删除 settle_kill 显式再减的一笔，
  总消解恰为功德语义 40//2=20，与 spec 与返回字段自述一致
- QA2-01 + S3：反悬赏清理补全三方向（键/hunter_id/target_id 指向死者），且覆盖
  非接令者击杀的提前返回路径（抽共用清理函数，主/早退路径同源）

### 修复（文档与 CLI）
- QA2-02：hunt spec 悬赏板功德订正为 15/令（与 BOUNTY_HUNTER_MERIT 一致），代码未动
- QA2-03：CLI 补全 19 个局域网专有指令的声明与专有提示派发（与 /探险 /秘境 同一口径）；
  评审另修 /AI自检 大小写规范化导致的提示不命中

### 修复（造化生成）
- 验收阶段抓到的产品缺陷：forge 本地回退命名「无名{kind}{随机两位数}」不查排除集、
  每类仅 90 个槽位，名字随运行累积必然撞名，且撞名时落库静默失败仍返回成功——
  改为顺序扫描首个未占用序号 + 落库前最终校验 + 未落库明确失败（守卫测试 3 例）
- 另修复两条测试对活库既有状态不密封的问题（排程 B1 假设、版图衰减墙钟漂移）

### 测试与结论
- 新增跨功能审计测试 70 例（两轮）+ forge 守卫 3 例，全量基线 548 → 621
- 第二轮复测的七个重点域（修复外溢/物品多通道/双端交替/时间边界/死亡组合/
  前端契约/数值极端）除上述 3 条 S3 外全部通过
- 第一轮「跨区跑商毛利包络 1.43」经第二轮双口径复测证伪（测试公式漏算双项钳制）：
  实际最坏毛利 ×1.035、端到端 ×1.03，在 F03 设计内，非缺陷结案
- 仍待产品裁定的设计项（spec 未定、行为已由测试钉死，资金与物品不丢不重）：
  死亡悬挂三项（寄售在售者死后成交款去向、拍卖死者出价退款去向、议政死者选票计入）

## v0.2.0-gray.2（2026-11-04）— 功能完善版
## v0.2.0-gray.2（2026-11-04）— 功能完善版

定位：在灰度 1 号的稳定性基础上把蓝图玩法补全。核心不变
（寿元硬通货、规则引擎裁决数值、LLM 只做叙事与 NPC 言行、一世循环 + 84 天赛季）。
总纲与逐项 spec 见 `docs/compose/spec/feature-completion.md` 及各功能 spec。

### 新增玩法（F01–F16）
- 灵宠（捕获/契约/喂养/助战）、心法槽位（主修 1 + 辅修 2、切换冷却）
- 区域价差跑商（区域系数 + 每日波动 + 量大价跌防套利）、典当行（五折当/限期赎/逾期入市）
- 拍卖专场状态机补全（系统专场 + NPC 规则出价）、灵田/洞府经营（开田/播种/墙钟生长/洞府闭关加成）
- NPC 委托链（2–4 环送信/寻物/除妖、当面核验、规则定价封顶）
- 长老议政（议题轮转、立场规则推导、投票/游说、多数决落账宗门状态）
- 宗门势力版图（成员活动累积影响力、衰减易主、主导区域坊市买入九五折）
- 炼体/炼神双修（各 10 层副修：战力/寿元微增、有效道心/神识，封顶不夺主修）
- 著书立说（燃寿 + 灵感成书、寄售流通、研读一次性收益、作者声望按本封顶）
- 飞升榜（历世已落账前世跨纪元综合榜，与单世天机榜区分）
- 纪元天象主题（6 主题按纪元轮转，单通道小幅修正：灵气/市价/事件权重）
- 诺言账闭环（/许诺 /应诺 /诺言 /毁诺，既有事实核验，履约功德/违约业力入因果账）
- 除凶令状态机收尾（令实体/接令登记/追凶区域情报/围剿协剿分账，与悬赏板去重）
- 心魔长期状态机（魔念三路播种、阶段推导、突破/闭关发作、镇魔服丹/静坐、入魔加重档）

### AI 通道（F17）
- LLM 主通道超时可配置：`.env` 的 `LLM_TIMEOUT_SECONDS`（默认 30、钳制 5–120、非法回退），
  慢中转不再频繁降级本地模板。

### 质量
- 每项功能均经独立评审后才合并；评审累计拦下并修复：已装备物品不可见、版图折扣 × NPC 商店
  跨通道套利、手稿逃逸通道致作者砖化、/接令 与悬赏板同名冲突、心魔入魔业力双计等真实缺陷。
- 测试基线：全量 548 用例，总验收连跑 3 遍 0 失败；真 AI 通道实测（世界事件/交谈/心魔）均有真实调用成功记录。

## v0.1.0-gray.1（2026-11-03）— 首个灰度版本

定位：局域网原型 → 可供小范围真实玩家试玩的灰度版。玩法核心不变
（寿元硬通货、规则引擎裁决、LLM 只做叙事与 NPC 言行、一世循环 + 84 天赛季）。
本版只补「可交付、可诊断、可回滚」，不新增玩法系统。运行手册见 `docs/gray-runbook.md`。

### 稳定性
- 修复 `test_events_ai` 危机事件用例随机失败（约 50%）：危机池含只改道心/业力的条目，
  旧断言只认灵石/寿元变化；改为全属性快照比对（寿元带墙钟容差）。游戏规则未动。
- 新增 `.env.example` 配置样例，房主照抄改 Key 即可。
- 测试基线：全量 240+ 用例，灰度门禁要求连续 3 遍 0 失败。

### 运维可见
- `GET /health` 新增 `version / ai_available / ai_required / allow_local_ai / online` 字段
  （旧字段保留），房主可自检 AI 通道与版本。
- `config.VERSION = 0.1.0-gray.1`，与 git tag `v0.1.0-gray.1` 对齐。

### 网页体验
- 新增「行囊」卡：物品合并计数、已穿戴标识、一键穿戴/卸下/服用，阵盘与法门只读展示。
  服务端 `_status_dict` 新增 `inventory / equipped / arrays` 下发字段（纯新增，向后兼容）。
- 命盘状态条新增「血煞缠身」（规则侧血煞标记）与「大限将至」（余寿跌破预警阈值）警示。

### 已知限制（灰度范围外，见运行手册）
- 局域网单进程 + SQLite，非公网架构；AI 为单通道，Key 未配时交互类指令不可用
  （或显式开启本地降级）；存档备份靠手动拷贝 `data/`。

## 历史
- 首版入库（2026-09-20）：《天道因果录》局域网原型。
- 开发基线准备（2026-11-03，f0fdab8）：补根 README 与 requirements.txt，去除写死的本机路径。
