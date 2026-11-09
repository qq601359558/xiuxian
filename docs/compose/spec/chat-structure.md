# Spec：NPC 交谈弹窗与回复结构化（chat-structure）

- 版本目标：v0.3.14-gray.21
- 分支：feat/chat-structure（worktree.worktrees/chat-structure，基线 main 2082c40 / v0.3.13-gray.20）
- 触发：Martinez 反馈「与 npc 交谈为什么不是弹窗了，而且 ai 回复格式有点乱」

## Problem（根因复核结论，代码证据）

1. **手机端没有交谈弹窗（迁移遗漏）**：桌面 web/index.html 有 #chatModal（神识交谈玉简），
web/workbench.js 有 openChat/renderChat/handleChatData 完整实现；手机 web/mobile.html 无任何
交谈层元素，web/mobile.js 中 NPC 交谈只有世界分区的「传音」输入对
（chatName/chatText → sendCmd("/交谈 …")）与同场/人物卡的 data-fill/data-cmd 芯片，
sendCmd 对交谈响应无任何分流，回复连同 old_account 行一起倒进动态 feed 当普通命令输出。
v0.3.4 移动页上线自动分流后，手机用户即失去弹窗——非设计决定。
2. **回复格式乱（前端正则猜行）**：交谈响应 text 是多行拼装，来源至少四处：
- /交谈 开启：greet 两行（…/用 /说…）+（可开口…）；
- /交谈 带话：greet + NpcDialogueEngine 文本（`` 头行 + `「line」` + 同场插话行）；
- /说：apply_npc_reply.message（line 本体；结束时 +end_reason+提示行）+ banter 追加行；
- /挂断：行 + 多行；/灵语：头 + line + 成长/阶段注记行。
桌面 handleChatData 靠正则 /会话开始|可开口|挂断|同场】|会话记忆|直接打字|天机偶发/ 逐行猜 sys、
其余剥「」当 NPC 行：引擎头行 `` 不命中正则被误当 NPC 气泡、
AI 正文格式稍变即错分混排。手机端整段原样进 feed。AI 叙事带 markdown 残留（**、##、`）时无人清洗。
3. **桌面手打 /交谈 现状（D 项实测结论）**：/action 提交路径对 chat_open/chat_ended 响应统一调用
handleChatData（workbench.js 提交处理），手打 /交谈、/说、/挂断 的响应本就进弹窗——成立，不需改；
本轮将其纳入结构化渲染后行为不变，仅渲染来源由 text 猜行改为 chat_lines 字段。

## Design

### B. 交谈回复结构化（服务端只增字段 `chat_lines`）

交谈相关响应新增顶层键 `chat_lines`：数组，元素 `{"who": str, "cls": "sys"|"npc"|"me", "text": str}`，
语义 = 本次响应要在交谈视图新增呈现的行（有序）。规则：

- 前端（双端）收到非空 chat_lines 时**只按字段渲染**，禁止再解析 text 猜行；
无 chat_lines 时回落既有呈现（桌面旧拆行逻辑仅作 demo/兼容回落，服务端正常响应恒带 chat_lines）。
- `text` 字段一字不改（CLI 与 feed 兼容）；`messages`（开启历史）口径不变；
玩家自己的话由前端本地回显（双端既有行为），不进 chat_lines。
- 各产出点拼装口径（server/world.py 交谈分支 + 引擎回传值，只增不改）：
1. /交谈 开启（无话）：greet 逐行 → sys 行。
2. /交谈 带话 · NPC：greet 逐行 → sys；引擎头行 `` → sys；
引擎 line（清洗后）→ npc 行（who=目标名）；bystanders[] 逐条 → npc 行（who=插话者，text=其 line 清洗后）。
NpcDialogueEngine.talk 回传新增 `line` 已有、另增 `header` 字段供拼装（text 不动）。
3. /交谈 带话 · 真人：greet 逐行 → sys；确认行 → sys。
4. /说 · NPC 对话：reply line（清洗后）→ npc 行；bystanders 同 2；
会话结束时追加 sys 行：end_reason、（继续发送将不会得到回应；可重新 /交谈）。
apply_npc_reply 回传另增 `end_reason` 字段供拼装（message 不动）。
5. /说 · 会话内动作（chat_actions）：act.text 逐行 → npc 行（who=NPC 名，逐行清洗）；
动作致结束时不再另拼 sys（缘由已在 act.text 内）。
6. /说 · 真人：确认行 → sys。
7. /挂断：行 + 会话记忆逐行 → sys。
8. /灵语 成功：器灵 line（清洗后）→ npc 行（who=灵名）；成长注记与阶段/心情注记逐条 → sys。
ArtifactSpiritEngine.talk 回传另增 `notes` 数组（growth_note 与 notes 的原始条目，message 不动）。
/灵语 响应不加 chat_open（桌面命令框 /灵语 维持 feed 呈现不变；弹窗内灵语走前端 spiritMode 既有分流）。
9. 奇遇并入（omen_chat）：_append_natural_omen 在 in_chat_npc 且 payload 已有 chat_lines 时，
追加 sys 行 = omen text（清洗后整体一行块，内部换行保留）；text 拼接口径不变。
- /会话（/chatpanel）是会话察看面板（无 chat_open/ended），不在本轮结构化范围，维持文本呈现。

### C. AI 交谈正文呈现清洗（仅呈现层）

新增纯函数 `core/dialogue_text.py::clean_dialogue_text(s)`：
- \r\n/\r → \n；逐行去尾随空白；连续 3+ 换行压为 2；
- 剥 markdown 残留：成对 ** 与 __、`行内代码` 反引号、行首 #{1,6}+空格、行首 "> "、[文字](url) → 文字；
- 不动中文标点与「」『』·：等叙事符号，不动数值、不动结算。
应用点（仅限 AI 生成的对话正文进入用户可见响应处）：NpcDialogueEngine 的 line（text 拼装与回传）、
/说 路径 AI/local line（入 apply_npc_reply 前）、器灵 generate_spirit_reply 的 line、
以及 chat_lines 拼装时对每条 npc 行文本的统一清洗（幂等）。本地模板台词经同一清洗无副作用（无 markdown 记号）。

### A. 手机端交谈弹窗（与桌面玉简同构）

- web/mobile.html 在 #app 内新增 #chatModalM：头部（头像 img#chatAvatarM、标题#chatTitleM、
副题#chatSubM、旧账行#chatOldAccountM、收束按钮）、日志#chatLogM、底部表单
（输入#chatInputM + 发送）、断开按钮#btnChatHangM。结构与桌面 #chatModal 对应。
- web/mobile.js 新增 state.chat {open, npc, isPlayer, spirit, spiritItem, lines} 与
openChatM/closeChatM/renderChatM/chatSendM/routeChatDataM：
- sendCmd 响应分流：data.chat_lines 非空、或 chat_open/chat_ended 在场 → routeChatDataM，
不再把该响应 text 倒进 feed（old_account 改渲染进弹窗头部行；chat_open 时打开弹窗）。
chat_ended 且弹窗未开时维持 feed 文本呈现（命令框手打 /挂断 等）。
- 打开入口：同场人物卡「传音」按钮与 /look 面板交谈芯片改为直接开弹窗
（data-chat-name / data-chat-player 属性）；世界分区「传音」输入对：填了对方名即开弹窗并
（有内容时）直接发出第一句；器灵块「灵语」芯片改为开灵语弹窗（data-spirit-item / data-spirit-name）。
- 弹窗内发送：NPC/真人走 /chat API（{token, text, to}，与桌面同一通道）；
灵语走 /action 的「/灵语 …」（响应 chat_lines 追加，spirit 模式本地状态维持）。
- 本地回显玩家行（cls=me）；NPC 回复未达时不伪造内容；出错以 sys 行呈现并 toast。
- 收束 = 仅收起弹窗（与桌面 data-close-chat 行为一致，不发 /挂断）；断开神识 = 收起并
对 NPC/真人会话补发 /挂断（灵语无挂断语义，仅收起）。
- 桌面端 workbench.js：handleChatData 的 NPC 分支与 chat_ended 分支、sendChat 灵语分流，
在 data.chat_lines 在场时按字段渲染；不在场回落现状逻辑。真人分支维持现状（messages 渲染）。
- web/mobile.css 新增.chatm-* 紧凑样式（复用既有色板 token 与.btn/.chip 视觉），
弹窗为底部升起的全宽层（max-height 82vh，日志区独立滚动，输入行吸底），双主题（[data-theme=dark]）适配。

### 预算豁免 D1（沿 command-panels §11-D1 先例，本 spec 内裁决）

- mobile.css 现 28454B / 预算 29200B，余量 746B 不足以承载交谈层样式；
本轮豁免上限至 31400B（实测成品 31324B、增量 2870B——初估 2.2KB 低估了底表头/日志/表单/气泡完整样式量），mobile.js 现 1777 行 / 预算 2100 行，余量内完成（预计 +≤260 行）。
- 豁免仅限本功能新增的 .chatm-*、--scrim 令牌与 state.chat/弹窗函数，不借机扩其他样式。

## Out of Scope

- 不改 AI 叙事生成（prompt、台词内容、人物设定）、不改任何数值/结算/会话状态机语义。
- 不改 /会话 面板、不改 CLI 呈现、不改桌面弹窗结构与样式（仅 handleChatData 渲染来源切字段）。
- 不改.env /.env.ai、不动 NAS 存档；部署仅代码（git pull + compose 重建）。

## Acceptance

1. 服务端：新增 tests 覆盖——/交谈 开启/带话（NPC 与真人）//说（含结束）//挂断//灵语 响应均带
chat_lines 且分型正确（头行与 greet 为 sys、正文为 npc、结束缘由为 sys、灵语注记为 sys）；
text 与基线逐字一致（除 C 的 line 清洗在 text 中的体现外）。
2. 清洗纯函数单测：**、##、`、链接、\r\n、空行折叠被处理；「」·与正常中文标点零损伤；
幂等（clean(clean(x)) == clean(x)）。
3. 双端 JS：node --check web/mobile.js web/workbench.js 通过；前端渲染只读 chat_lines
（代码评审确认 handleChatData 与 mobile routeChatDataM 无正则猜行残留于结构化路径）。
4. 截图验收（隔离服 + Puppeteer）：移动 390×844 与 390×667 各一张交谈弹窗
（含一段多行 AI 风格回复：头行 sys、正文 npc 气泡、段落换行正常、无 markdown 残留）、
桌面一张弹窗（同响应）；移动灵语弹窗一张。
5. 全量回归连跑两次，与 v0.3.13 基线失败集对照零新增（基线以本分支起点实跑为准）。
6. 发版 v0.3.14-gray.21：config.VERSION、README、CHANGELOG、docs/gray-runbook.md 同步，tag 推送核验。
7. NAS 部署：部署前备份（代码目录与 data），git pull + docker compose up -d --build，
/health 版本 = 0.3.14-gray.21；线上冒烟：新账号 /交谈 开启响应含 chat_lines、首页 200。
