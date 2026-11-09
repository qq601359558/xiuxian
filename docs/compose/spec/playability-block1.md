# Spec：块一 · 玩不下去先清零（playability-block1）

> 依据：模拟玩家首玩实测报告（~/workspace/projects/xiuxian-simtest/simtest-shots/ + *-log.json）S1–S8；
> 代码侦察锚点（main @ 2082c40 / v0.3.13，2026-11-09 总管侦察轮）。
> 基线：v0.3.14-gray.21（交谈结构化已并入）。分支：feat/playability-block1。

## Problem

新玩家首玩在五处被挡死：①注册在 tick/AI 卡顿窗口内 500 且前端误报「服务未启动」；
②世界 tick 持锁 19.9–20.7s（锁内跑 AI），窗口期一切请求排队 17–21s，是①与交谈报错的总根；
③AI 网关故障时交谈把运维原文（CC Switch/.env/LLM_API_*）弹给玩家，本地兜底只回「嗯。」；
④命途第 1 章目标 NPC 就在同场，界面却说「前往其所在之地」，目标卡无地点、无按钮、无下一步；
⑤修仙游戏没有 /修炼（回「未知指令」），真入口叫闭关且带租金与锁状态；
⑥/行情 整表并排裸露 mat_*/equip_*/pill_* 内部 ID 且同物重复（约 276 行）；
⑦入局卡首屏塞未谋面 NPC 的「态度变化」（实为出身生成时植入的 origin 留痕），命盘「神通图」把全图鉴摆得像已习得技能。

## Design

### B1-1 注册永不 500 误报（对应清单 1）
- 根治在 B1-2（tick 锁外 AI）缩小争用窗口；兜底再加一层：`server/app.py` acct_register 与 `WORLD.join`
  路径把 DB 争用类异常（sqlite3.OperationalError: database is locked 等）转成既有 `WorldBusyError`
  语义 → `_busy_response` 503（`SERVER_BUSY` + 「世界正在演化，请稍后重试」），绝不裸 500。
  既有回滚补偿（app.py:487-493）与重试安全性不动。
- 前端（workbench.js:484 / mobile.js:178 附近）：文案按状态分流——HTTP 503 显示后端诚实文案
  （繁忙/重试）；仅 fetch 真抛错（网络层失败）才显示「无法感应阵枢灵脉（请确认服务已启动）」；
  400 显示后端 error 原文。不得把 503 误报为服务未启动。

### B1-2 tick 持锁根治（对应清单 2，总根）
- 现状锚点：`server/world.py:155-243` `_tick_once`，`:181` 起整轮持 RLock 跑 8 阶段；
  AI 在 agenda（`core/npc_agenda.py:194` 逐 NPC `ai_invoke`，经 `:382` tick_world）与
  director（`core/world_director.py:613`，timeout=LLM_TIMEOUT_SECONDS 默认 12s，config.py:895-911）。
- 改法：agenda 与 director 两阶段改为「锁内取快照 → 锁外调 AI → 锁内校验落盘」三段式：
  - agenda：锁内收集每 NPC 的决策输入快照（DTO，不持角色对象引用跨锁），锁外逐个 ai_invoke，
    锁内 apply 时复验角色仍存在/存活/未迁徙到不适用状态，陈旧结果丢弃并 log。
  - director：`run_cycle` 读快照后锁外跑 AI；`_save`（core/world_director.py:43-80）加 CAS：
    world_state 行加 revision（或以既有 updated 字段比对），保存前重读比对，被并发写过则
    以最新状态为底重新并入本轮 delta 后再存，禁止旧快照整体覆盖 `record_player_event`
    （:930-953）等并发写。角色侧 `save_if_unchanged`（:1092-1100）为既有先例，口径对齐。
  - 其余 6 阶段维持锁内（纯规则结算，无 AI）。
- /转世无界锁：`handle()`（world.py:1172-1173）全局改锁不在本轮；仅 /转世 分发路径改走
  有界获取（复用 `_bounded_lock`/`LOCK_ACQUIRE_TIMEOUT_SECONDS` 口径，world.py:99/311-329），
  超时回 503 诚实文案（写路径 SERVER_BUSY 既有口径），不许无界等待。
- 度量：用 tick_end 日志 hold_ms（world.py:241-243）在本地实例同口径对比改造前后
  （含 agenda 的 tick），目标：持锁 p/max 回到秒级以内（AI 时长不再计入持锁），报告给实测数。

### B1-3 交谈错误玩家不可见 + 兜底像人话（对应清单 3）
- 主出口 `core/npc_mind.py:516-524`：删除「ai_available 且非 local 时直接返回运维 error」分支；
  talk() 统一为：AI 可用则走 AI；任何失败/不可用 → 本地兜底（_local_line / npc_chat 池），
  运维细节只进 log_event。原「不静默假冒 AI」意图由产品决策（Martinez 2026-11-09 清单）明确放弃，
  在 spec 与代码注释各留一句记录。
- 类级清扫（玩家可见文本零运维词）：config.py:974-977 `ai_unavailable_message()` 改世界观内文案
  （内部细节另走 log）；server/world.py:1948-1949 `/ai` 自检面板去 CC Switch 指引；
  server/world.py:4633 `/自创功法` error 去 USE_CCSWITCH；ai/gateway.py:241 探测 error 同步。
  新增锁定测试：AI 强制关闭下对 /交谈、/自创功法、/ai 等出口断言响应不含
  `CC Switch`、`USE_CCSWITCH`、`LLM_API`、`.env`、`server.log` 字样。
  涉及 test_ai_required 等既有契约测试的，同步更新为新契约并在 spec 记录。
- 兜底像人话：`core/npc_chat.py:501-525` local_hangup_or_reply 按性格扩充回复池——每种性格
  ≥3 条在场短回复（淡泊/清高不再固定「嗯。」：给「嗯，此事吾已知之。」量级的有内容短句，
  按态度/场景微调），复用 `core/npc_mind.py:592` `_local_line` 的分类（客套/打听/买卖/秘境…）；
  NAMED 人设静虚真人的「嗯。」（core/npc_personas.py:179）为有意设定，不动。
  红线：模板只叙情性，不碰任何数值/结算。
- 前端：交谈发送失败时清输入框并给可重试状态（与 v0.3.14 弹窗口径对齐：sys 行提示 + 输入清空），
  双端一致（workbench handleChatData / mobile openChatM 路径）。

### B1-4 目标给路（对应清单 4）
- 服务端 `core/fate_thread.py:908-947` thread_status_dict：chapters_out 透传章内 `check`
  {kind, ref, npc_id}（存在时）；新增顶层 `current_target`：取第一个 active 且 visit 类 check 的章，
  现查目标 NPC（id 来自 check.npc_id）得 {npc_id, npc_name, npc_location, same_location}
  （same_location = npc.location == char.location，现查不存快照）；非 visit 类/无目标时为 null。
- `core/briefing.py:322-351` lines.fate 文案补一句：同场→「<NPC> 正在此处（<地点>），可直接上前交谈」；
  异场→「<NPC> 在<地点>」。纯文本端同步受益。
- 前端双端（入局卡 renderEntry/renderEntryM + 命途段 fateThreadHtml/fateThreadHtmlM）：
  current_target 在场→渲染「就在此处 · <地点>」+ 直达按钮 data-cmd="/交谈 <npc_name>"；
  异场→「在<地点>」+ 前往按钮（data-cmd 用 command_catalog 现行注册的地点迁跃命令，
  实现时核对并在验收中实点到达；无直达命令时降级为打开世界页的 view 跳转）。
  目标卡（入局卡命途行）补齐地点与下一步动作，与命盘口径一致。

### B1-5 「修炼」正名（对应清单 5）
- 决策：/修炼 为一等入口，别名直达现行闭关实现（_meditate，world.py:5524-5540 → core/clock.py），
  不新增数值体系。理由：块一是可玩性清障轮，修炼的玩家预期（入定修行、随时间得修为）与闭关
  语义完全一致；另起轻量修炼动作等于新开数值系统，超出本轮范围且触碰规则裁决面。
- 落点：handle() 分发加 /修炼（与 /闭关 同一处理，参数口径一致）；core/command_catalog.py
  增 /修炼 条目（说明注明「即入定修行，与闭关同源，租金与禁忌见反馈」），/闭关 条目互指；
  /帮助（format_help）同步；双端命令表（workbench.js:8636 / mobile.js:1272）加 /修炼，
  快捷芯片双端各补一枚「修炼」（mobile.js:769 芯片行、workbench 洞府区 :2020-2028 附近）；
  闭关门禁白名单（world.py:1389-1435）把 /修炼 按 /闭关 同口径处理。
  验收硬线：输入 /修炼 绝不回「未知指令」；与 /炼体 修炼、/炼神 修炼 子命令无冲突（分发顺序核对）。

### B1-6 行情原码清零（对应清单 6，原 D-QA1）
- 根因：目录双键（core/catalogs/{materials,pills,equipments}.py 同时以中文名与 data["id"] 为键），
  行构建器以「键」作显示名。**不动 ITEM_CATALOG 本身**（购买/查价按 id 寻址依赖双键）。
- 修展示构建器（类级）：统一「显示名 = cfg.get('name') or 键；按 cfg['id']（无则按显示名）去重」：
  core/market.py:174-195 `_rows_for_region`（含 trade_board_data :221-237 / trade_board :240）；
  server/world.py:5815-5839 `_market` 所经 MarketEngine.catalog() 同源核对；
  core/trade.py:740-760 NPC 专柜行；core/chat_actions.py:315 `_shop_stock_preview` 去重口径改按解析后身份；
  core/npc_mind.py:427 goods_brief 与 :533 丹药兜底列表（喂 AI prompt，同法去重防原码经叙事泄漏）。
- 验收：/行情 文本与面板行集不含 `(mat|equip|pill)_` 前缀 ID、无同物重复行，行数回落到唯一物品量级；
  新增回归测试扫行集断言。

### B1-7 首屏降噪与误读修正（对应清单 7）
- 入局卡态度段：core/briefing.py:357-365 组装 lines.relations 时过滤 reason="origin" 的留痕
  （出身植入非玩家目击的变化）；只动 briefing/lines 层，relations_marks 同源口径（同场箭头
  workbench.js:892）与命盘 relations_recent 不动。过滤后无真实变化则整段不渲染（前端既有空段处理核对）。
- 神通图误读：后端 skills 与 spells_catalog 本为两字段（world.py:5111 / :5021-5030），纯前端 labeling：
  双端命盘把该段标题改「神通图鉴（全录）」；skills 芯片区标题保持「已习得法门」口径。
  **前提纠正（评审 MF-3，见文末 Finalize）**：原口径「catalog 每项按名与 skills[] 求交集标
  已习得/未习得」已撤销——status.skills 存的是功法名、spells_catalog 是 5 个神通名，
  全仓无「已习得神通」数据源，交集恒空、逐项标注恒为「未习得」，本身即误读来源。
  现行口径：图鉴段只作全录展示，不标任何习得态。

## Out of Scope
- handle() 全局锁改造（仅 /转世 有界化）；tick 其余阶段拆锁；AI 上游可用性本身；
  新修炼数值体系；命盘 relations 段过滤；交谈弹窗本体（v0.3.14 已交付）；
  块二（目标内容深化）、块三（事件密度）、块四（界面重做）。

## Acceptance（每项可观察证据）
1. 全量回归新鲜 DB 与 v0.3.14 基线失败集对照零新增（flaky 隔离复跑判定）。
2. tick hold_ms 本地实例前后实测：含 agenda 的 tick 持锁由 ~20s 回落秒级（报告实测数）；
   WorldDirector 并发写不被覆盖的回归测试（cycle 期间 record_player_event 存活）。
3. 模拟玩家复测（ui-shot Puppeteer，本地新版实例，390×844）逐条销项：
   连注册两号（含 tick 窗口）无 500/无误报；断 AI 下交谈得性格化兜底、无运维词、输入框清空；
   目标卡对同场 NPC 显示「就在此处」+ 交谈按钮且实点可达；/修炼 可用且有芯片；
   /行情 无原码无重复。截图存 simtest-shots-block1/。
4. 发版 v0.3.15-gray.22：四件套同步、部署 NAS（前备份）、/health 实测 +
   线上冒烟（注册/交谈/行情）通过。

## 任务分解（岗位）
- T1 后端·锁与注册：B1-1 服务端兜底、B1-2（tick 三段式 + director CAS + /转世 有界）+ 测试。
- T2 后端·内容面：B1-3 服务端（npc_mind/config/gateway/world 出口与兜底池）、B1-4 服务端字段、
  B1-5 分发与 catalog、B1-6 构建器、B1-7 briefing 过滤 + 测试。
- T3 前端双端：B1-1 文案分流、B1-3 发送失败态、B1-4 目标按钮、B1-5 芯片与命令表、B1-7 神通图 labeling。
- T4 独立评审：diff 全审（规格符合/契约/完整性守恒律——新入口须经既有 assert_alive/assert_idle 口径）。
- T5 QA：全量回归 + 模拟玩家复测 + 发版部署冒烟。

## Finalize

### 评审修复轮（2026-11-10，MF-1~MF-3 + SF-1/SF-2/SF-4）

- **MF-1 锁内 AI 点缀短超时**：tick 锁内两处纯叙事点缀改短超时 2s——合谋
  （`core/collusion.py` try_collude_pair 新增 ai_timeout=2.0 透传至 _chat_json）、
  世界弧阶段文案（`core/world_arc.py` _ai_stage_text 经 ai.router.invoke(timeout=2)）；
  超时/失败走既有本地句/模板兜底，规则结算未动。熔断记账：已给网关加干净接缝
  `_chat_json(..., count_failure=False)`（router.invoke 同名透传，仅默认网关生效），
  点缀失败改记 neutral 不计入主通道熔断（closed 态无副作用；半开探测时 neutral
  仍按既有口径重开，探测语义不被架空；成功仍记 record_success）。直测锁定该口径。
- **MF-2 /ai 面板去泄漏**：`server/world.py` /ai 的 mode 改中性表述（本机代理/云端直连）、
  删除「地址：{base}」行；回包 ai_data 副本同步脱敏（去 base、mode 改中性口径，
  world_state 存储原件不动）。新增 USE_CCSWITCH=1 口径锁定测试（整回包断言无
  CC Switch/CCSWITCH/USE_CCSWITCH/LLM_API/.env/server.log）。
- **MF-3 神通图习得标撤销**：前提纠正已同步 B1-7 段——skills 存功法名、spells_catalog
  为神通名、无已习得神通数据源、交集恒空。双端（workbench.js/mobile.js）删除逐项
  已习得/未习得标注与求交集代码，只保留段标题「神通图鉴（全录）」；T3 新增的
  learned/unlearned CSS（双端各 2 行）一并删除；新增前端契约测试锁定。
- **SF-1 director _merge_active 无 id 项**：无 id 项不再以 None 为键互相覆盖——
  不参与 id 合并，按内容相等作身份对齐（与 id 项同口径：各自保留、本轮明确移除
  丢弃、同一项多侧出现只留一份），补直测。
- **SF-2 agenda 无基线车道收窄**：段一取基线抛异常（baseline=None）时，段三落盘前
  重读该行——行已存在按陈旧丢弃（write_audit reason=baseline_missing_row_exists）；
  仅行确实不存在才沿原内存对象口径落盘。补双向测试。
- **SF-4 同类清扫**：`ai/gateway.py` ai_block_reason「已配置但探测失败」分支改世界观内
  文案（last_error 原文只进 log、不带自检指引）；`core/world_director.py` 质量自检
  detail「有 Key/CCSWITCH」改中性「已配置/未配置」。扩锁定测试覆盖该分支输出。
- **SF-3（跨 NPC 可见性取舍）记录**：本轮不改代码。取舍内容：agenda 三段式的段三
  复验只覆盖被 tick 的 NPC 本行基线（updated_at 比对），不做跨 NPC 行的一致性校验
  ——AI 窗口内其他 NPC/目标角色的并发变动不在本轮陈旧判定范围内。此为已知的
  可见性取舍（换取段三简单性与既有落盘口径），后续块如需跨行一致性另立 spec 评估。
