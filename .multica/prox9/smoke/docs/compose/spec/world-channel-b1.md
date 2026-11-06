---
feature: world-channel-b1
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# B1 · 世界频道 + 大事件即时消息 + 事件链 + 纪元传说

> **本稿仅设计，待创作者审阅后再开发。**

## Report

**What was built** — 世界频道 `core/world_channel.py`（major/epic/gm/system，60s 去重 + 每分钟限流，SQLite `world_messages`）；击杀/突破成败/大额成交/落槌/秘境开启（30 分钟冷却）/大劫钩子自动播报；`/频道` `/公告` `/gm <token> <文案>`；`GET /world/messages` 增量；网页「世界」流 + 未读角标 + epic/gm toast 与自动切页；通用奇遇链 6 模板 2 步（`/奇遇`，迁跃 8%/探险 10%/`/机缘` force）；纪元传说 `/传说` 与 NPC 事实包一行史载。

**Verification** — `tests/test_world_channel_b1.py` 7 passed；全量 **149 passed**（`test_events_ai` 危机空 effects 为 PRE-EXISTING 偶发）。评审 major（角标 lastSeen、channel SQL 下推、突破失败播报、模板数、/机缘 force、秘境刷屏）已修。

**Journey log**
- 频道/传闻/大事记/传说四层分工，避免互相覆盖。
- 未读角标：轮询用独立 `pollCursor`，仅世界页可见时推进 `lastSeenTs`。
- `/公告` 必须把 channel 过滤下推到 SQL，否则被 world 消息挤空。
- 秘境 major 播报按秘境 30 分钟冷却，防 LAN 刷屏。

## [S1] Problem

1. **消息孤岛**：击杀/大劫/拍卖/合谋等只回写给操作者本人或进传闻池；全服玩家**无法及时看到**「世界上刚发生了什么」。网页有「世间」页签（`worldBody`），但只在手动 `/榜` `/宗门` 等指令时填充，**没有推送流**。
2. **无 GM/系统公告通道**：无法发维护提示、活动预告、全服补偿说明。
3. **事件仍是单发**：`EventEngine.fire` 一次一则；秘境链仅限探索步进，没有「遇怪→选择→分支结局」的通用 2–3 步链。
4. **世界不记得你**：大劫 `settle_apocalypse` 只重开纪元，上纪元高光无法被下一纪检索与复述。

创作者拍板（2026-09-17）：AI **宁少而准**；大事件要**及时消息**展示在世界频道。

---

## [S2] Design

### 2.0 总览

```
规则引擎结算
    │
    ├─► WorldChannel.post(level, kind, text)     ← 即时世界消息
    ├─► rumors.add_rumor(...)                    ← 坊间传闻（已有，可复述/扭曲）
    ├─► ChronicleRepository.record(...)          ← 大事记（已有，考古用）
    └─► Legends.write(...)                       ← 纪元传说（新，跨大劫存活）

网页/CLI 轮询或随 /action 捎带
    └─► 最近 N 条未读频道消息 + 角标
```

**分层原则**（避免三套账本互相打架）：

| 层 | 用途 | 生命周期 | 玩家入口 |
|---|---|---|---|
| **世界频道 WorldChannel** | 刚发生的、要立刻看到的 | 短（默认 2h / 200 条） | 网页「世界」页签自动流；`/频道` |
| **传闻 Rumor** | 可被 NPC 复述、可半真半假 | 7 日 | `/传闻`；NPC 交谈注入 |
| **大事记 Chronicle** | 完整结构化考古 | 永久 | `/大事记` |
| **纪元传说 Legend** | 跨大劫的「史书条目」 | 永久（按纪元归档） | `/传说`；下一纪 NPC 可引 |

一条重大事件可同时写多层（频道立刻播 + 传闻可闲话 + 传说可入史）。

---

### 2.1 世界频道（WorldChannel）

#### 2.1.1 消息模型

```python
class WorldMessage(BaseModel):
    id: str
    channel: str      # "world" | "gm" | "system"
    level: str        # "info" | "major" | "epic" | "gm"
    kind: str         # kill / breakthrough / auction / apocalypse / chain / gm / ...
    text: str         # 已渲染的一行/两行中文，≤120 字
    actor: str = ""   # 主角道号（可空）
    location: str = ""
    season: int = 0
    ts: float
```

#### 2.1.2 通道语义

| channel | 谁能发 | 用途 |
|---|---|---|
| `world` | 规则引擎钩子 | 玩家/NPC/世界大事件 |
| `gm` | GM 指令 | 运营公告、维护、活动 |
| `system` | 服务器 | 开服、纪元切换、AI 通道故障提示 |

`level` 只影响样式与是否顶栏 toast，不改存储结构：

| level | 网页样式建议 | 是否自动切到世界页 |
|---|---|---|
| `info` | 普通行 | 否 |
| `major` | 金色左边线 | 否，角标 +1 |
| `epic` | 高亮底 + 短 toast | 是（可配置，默认否以免打断） |
| `gm` | 紫色/置顶前缀 | toast 必出 |

#### 2.1.3 存储

- 表 `world_messages`：`id PRIMARY KEY, data_json, level, channel, ts`
- 或沿用 `world_state` JSON 列表——**推荐独立表**，便于按 ts 索引与清理。
- 保留策略：`WORLD_MSG_MAX = 200` 条或 `WORLD_MSG_TTL_H = 2` 小时，写入时裁剪。
- 重启可恢复（与 C2 一致）。

#### 2.1.4 API

```python
# core/world_channel.py
class WorldChannel:
    @staticmethod
    def post(kind, text, *, level="info", channel="world", actor="", location="") -> WorldMessage
    @staticmethod
    def recent(limit=20, since_ts=0.0, channels=None) -> List[WorldMessage]
    @staticmethod
    def format_board(limit=15) -> str          # CLI /频道
    @staticmethod
    def format_unread_for(player_last_seen: float, limit=10) -> str
```

#### 2.1.5 指令

| 指令 | 语义 |
|---|---|
| `/频道 [n]` | 最近 n 条世界消息（默认 15） |
| `/gm <文案>` | **仅 GM** 发公告（见 2.1.6） |
| `/公告` | 只看 `gm`+`system` |

#### 2.1.6 GM 权限（最小可行）

**已拍板（2026-09-17）：GM Token。**

- `.env`：`GM_TOKEN=<随机串>`
- `/gm <文案>` 时指令须为 `/gm <token> <文案>`，或网页提供「以 GM 身份发送」输入框（仅当本地配置了 token 时显示——LAN 简化：token 写在请求头/字段，由客户端本地保存）。
- 推荐服务端校验：`action` 解析出 token 与 `GM_TOKEN` 常量时间比较；不匹配则拒「天道未授你传讯之权」。
- **不**做多角色权限树；token 泄露即换 `.env` 重启。
- 可选：`GM_NAMES` 仍可作辅助白名单（本阶段可不做，仅 Token）。

#### 2.1.7 网页展示（index.html + app.js）

现状：中栏 tabs = 天道录 / 目标 / 世间；`worldBody` 仅手动指令填充。

**改造（已拍板：epic 自动切到世界页）**：

1. 「世间」页签改名为 **「世界」**，内容 = 频道流（自动刷新）+ 下方可折叠「查询结果」（榜/宗门等仍可手动指令写入）。
2. 轮询：复用现有 `pollTimer`（约在 `app.js:814`），每 15–20s 调一次轻量接口（见 2.1.8），拉取 `since=lastSeenTs` 的增量。
3. 未读角标：tab「世界」上显示未读 major+ 数量；点开清零（本地记 `lastSeenTs`）。
4. Toast：`level in (epic, gm)` 时在顶栏短提示 4s。
5. **`level==epic` 或 `gm`：自动 `switchTab("world")` 并滚到最新**（创作者拍板，宁可打断也要被看见）。
6. 样式：复用现有 CSS token；`major` 左边线金、`gm` 紫、`system` 灰、`epic` 高亮底。

**不做**：WebSocket 实时推送（LAN 轮询足够）；私聊频道。

#### 2.1.8 HTTP 接口（server/app.py）

新增只读：

```
GET /world/messages?since=<ts>&limit=20
→ { ok, messages: [WorldMessage...], server_time }
```

- 无需登录即可读公开频道（LAN 信任模型与 `/action` 一致；若已有 session 校验则沿用）。
- `/action` 响应可**捎带** `world_msgs`（最近 3 条 major+），减少一次请求——可选优化，非阻塞。

---

### 2.2 大事件 → 频道 钩子表（规则写死，AI 不改）

| 事件 | level | kind | 文案示例（规则拼，AI 仅在已有叙事时截一句） |
|---|---|---|---|
| 玩家/NPC 击杀（受害者 tier≥3 或血煞） | major | kill | `【血雨】{killer} 于 {loc} 斩 {victim}，天机显影。` |
| 大境界突破成功（≥筑基） | major | breakthrough | `【雷音】{name} 渡劫功成，晋 {realm}。` |
| 突破失败重伤/死亡 | major | tribulation | `{name} 天劫反噬…` |
| 拍卖落槌（价 ≥500 或地品+） | major | auction | `【落槌】{item} 归 {winner}，{price} 灵石。` |
| 当面成交（双方合计 ≥800） | info→major | trade | 大额才 major |
| NPC 合谋（kind=寻仇未遂/分赃不均） | info | collusion | 默认只进传闻；**不**刷频道（防噪） |
| 秘境开启（世界级） | major | realm | `【天机】{realm} 禁制松动，限时开启。` |
| 天地大劫结算 | epic | apocalypse | `【大劫】第 N 纪元终了…` |
| 通用事件链结局（高光） | major | chain | `【奇遇】{name} …` |
| 服务器启动 / 纪元重开 | system | boot / season | |
| `/gm` | gm | gm | 原文 |
| AI 通道连续失败 | system | ai_down | 降级提示（与 C1 联动） |

阈值进 `config.py`：`CHANNEL_KILL_MIN_TIER=3`、`CHANNEL_AUCTION_MIN_PRICE=500` 等，可调。

**防噪**：同一 `kind+actor` 在 60s 内去重；每分钟最多 6 条 world 级消息（超出丢弃并记 log）。

---

### 2.3 通用事件链（2–3 步）

#### 2.3.1 模型

```python
class EventChain(BaseModel):
    id: str
    kind: str                 # opportunity | crisis | realm_ext | quest
    title: str
    actor_id: str             # 玩家或主 NPC
    step: int
    max_steps: int            # 2 或 3
    steps: List[dict]         # 每步：{prompt, choices[], state}
    location: str
    created_at: float
    status: str               # active | done | abandoned | expired
    season: int
```

与秘境链关系：秘境链**保留**为专用快路径；通用链用于「迁跃后/探险后/目标机缘」的叙事分叉。秘境可逐步改为「kind=realm 的链」——**本阶段不强制合并**，避免回归。

#### 2.3.2 步进契约

每步：

1. **规则**给出 2–3 个选项（id + 短标签），附带**预生成的效果草稿**（钳制后）。
2. **AI**（可选）润色叙事与选项说明；**不得**改效果数值。
3. 玩家 `/奇遇` 查看并 `/奇遇 <1|2|3>` 选择；超时 30 分钟自动 `abandoned`（无惩罚，与秘境一致）。
4. 最后一步结算：修为/灵石/寿元/业力按表落账；`level=major` 进频道；高光写传闻。

#### 2.3.3 触发（宁少而准；**已拍板**）

| 触发点 | 概率/条件 | 预算 |
|---|---|---|
| 迁跃到野外/秘境入口 | **8%** | 无玩家已有事件链时不触发 |
| 探险成功 | **10%** | |
| `/机缘` force | 100% | 已有 force 语义 |
| 世界 tick | 关闭（本阶段） | 降低噪音 |

全局：同时最多 1 条 active 链/玩家；全服同时 active 链 ≤ 8。

#### 2.3.4 指令

| 指令 | 语义 |
|---|---|
| `/奇遇` | 查看当前链叙事+选项 |
| `/奇遇 <n>` | 选择 |
| `/奇遇 弃` | 放弃 |

#### 2.3.5 预置链模板（规则池，无 AI 也能玩）

至少 6 条模板，字段：标题、步选项、效果表（钳制在 `EVENT_EFFECT_CAPS` 内）。示例：

1. **残碑悟道**：观碑 / 拓印 / 离开 → 修为 / 燃寿 / 无事  
2. **黑市兜售**：买下 / 报官 / 作罢 → 获物+业力 / 功德 / 无  
3. **旧友托孤**：应下 / 婉拒 / 谋其财 → 后续步「护送/黑吃黑」  

AI 有则改写 narrative；无则模板句。

---

### 2.4 纪元传说库（Legends）

#### 2.4.1 模型

```python
class Legend(BaseModel):
    id: str
    season: int
    title: str          # 短标题
    text: str           # ≤80 字史笔
    tags: List[str]     # player / npc / sect / apocalypse / first ...
    actor: str = ""
    created_at: float
    weight: int = 1     # 被引用次数
```

#### 2.4.2 写入时机

| 时机 | 条件 | 示例 |
|---|---|---|
| 大劫结算 | 必写一条总述 | `第3纪元终了，未飞升者X人应劫。` |
| 大劫结算时个人高光 | 本纪元击杀数/最高境界/最大单笔交易 Top | `【幽冥老祖】第3纪元化神，斩敌七人。` |
| 首次飞升（若将来有） | epic | |
| `/gm 史笔 <文案>` | GM 手动补史 | 运营写活动结果 |
| 事件链结局 weight≥major 且 season 末快照 | 可选，本阶段可只加大劫快照 |

`settle_apocalypse` 流程扩展：

1. 结算个人 → 写 Legends（≥1 总述 + 可选高光）  
2. WorldChannel epic 播报  
3. 传闻 `note_apocalypse`（已有）  
4. `set_epoch` 新纪元  
5. **不清空** Legends；只清/归档当前纪元频道消息（可选保留最后 20 条作「上纪元余音」）

#### 2.4.3 指令与检索

| 指令 | 语义 |
|---|---|
| `/传说 [纪元]` | 不带参：当前纪元 + 上一纪；带参：指定纪元 |
| `/典籍` | 同 `/传说` 别名 |

#### 2.4.4 下一纪回流（AI 宁少而准）

- NPC 交谈 prompt 增加一行：`上纪元传说：{1条随机高 weight}`（已有 facts 包模式）  
- 新手入世 feed 可附一条：`史载：上纪元…`  
- **不**为每条传说单独调 AI

#### 2.4.5 存储

- `world_state["legends"]` 列表，上限 80 条（按 weight+ts 淘汰）  
- 或表 `legends`——列表足够 LAN 规模；若已开 `world_messages` 表，可同构再加一张。

---

### 2.5 模块与文件落点

| 模块 | 职责 |
|---|---|
| `core/world_channel.py` | 频道读写、去重、限流、format |
| `core/event_chains.py` | 通用 2–3 步链引擎 + 模板池 |
| `core/legends.py` | 传说读写、大劫快照 |
| `storage/db.py` | `world_messages` 表 + Repository |
| `config.py` | 阈值、TTL、GM_NAMES、限流参数 |
| `server/world.py` | `/频道` `/gm` `/奇遇` `/传说`；钩子调用 |
| `server/app.py` | `GET /world/messages` |
| `core/combat_fate.py` `season.py` `trade.py` `secret_realm.py` `events.py` | 按 2.2 表 post |
| `web/index.html` `app.js` `style.css` | 世界流、角标、toast |
| `core/npc_mind.py` 或 `ai/facts.py` | 传说注入 prompt（一行） |

---

### 2.6 配置项（config.py）

```python
WORLD_MSG_MAX = 200
WORLD_MSG_TTL_H = 2.0
WORLD_MSG_PER_MIN = 6
CHANNEL_KILL_MIN_TIER = 3
CHANNEL_AUCTION_MIN_PRICE = 500
CHANNEL_TRADE_MIN_SUM = 800
GM_NAMES = []          # 从 .env GM_NAMES=a,b 解析
LEGEND_MAX = 80
EVENT_CHAIN_MAX_ACTIVE_GLOBAL = 8
EVENT_CHAIN_TIMEOUT_MIN = 30
EVENT_CHAIN_TRIGGER_TRAVEL = 0.08
EVENT_CHAIN_TRIGGER_ADVENTURE = 0.10
```

---

### 2.7 数据流示例

**玩家 A 斩杀金丹 NPC：**

1. `CombatFateEngine` 落账死亡、夺宝、因果（已有）  
2. `rumors.note_kill`（已有）  
3. `WorldChannel.post("kill", "【血雨】…", level="major")`（新）  
4. 网页轮询 → 「世界」页签顶部插入金线行 + 角标  

**大劫：**

1. `settle_apocalypse` 写 Legends + Channel epic + 传闻（已有/新）  
2. 所有在线客户端 toast  

**GM 维护：**

1. 管理号 `/gm 今夜子时秘境轮换`  
2. Channel gm 紫条 + toast  

---

### 2.8 测试边界

| 用例 | 断言 |
|---|---|
| post/recent/TTL 裁剪 | 条数与过期正确 |
| 60s 去重 + 每分钟限流 | 超限丢弃 |
| 击杀钩子 | tier≥3 进频道，低阶不进 |
| 大劫 | epic + legends ≥1，跨 settle 仍在 |
| `/gm` 非 GM 拒绝 | |
| 事件链：模板走完 2 步落账 | 效果在 CAPS 内 |
| 事件链：弃/超时 | 状态 abandoned，无惩罚 |
| HTTP `/world/messages` | since 增量正确 |
| 全量回归 | 不破坏既有 tests |

**不测**：真实浏览器像素；WebSocket。

---

### 2.9 实施任务拆分（开发时用）

- [x] T1: `world_messages` 表 + `core/world_channel.py` + 限流去重 — acceptance: 单测通过  
- [x] T2: 2.2 钩子接入击杀/突破/拍卖/大劫/秘境 — acceptance: 触发后 recent 可见  
- [x] T3: `/频道` `/gm` `/公告` + GM Token — acceptance: 非法 token 拒；GM 可见  
- [x] T4: HTTP `/world/messages` + 网页世界流/角标/toast — acceptance: 轮询有增量；epic 切页  
- [x] T5: `core/event_chains.py` 模板链 + `/奇遇` — acceptance: 2 步闭环落账  
- [x] T6: `core/legends.py` + 大劫快照 + `/传说` + NPC 一行回流 — acceptance: 跨纪元可读  
- [x] T7: 测试 + 全量回归 + Review + Finalize Spec  

---

## [S3] Out of Scope

- WebSocket/SSE 真推送；跨服频道；私聊/邮件；完整 GM 后台 UI  
- 把秘境链强制合并进通用链（可后续）  
- 玩家自定义频道订阅；消息撤回  
- 著书立说式长文 AI 生成史书（传说保持规则短句）

---

## [S4] 创作者已拍板（2026-09-17）

| 决策点 | 结论 |
|---|---|
| GM 授权 | **GM Token**（`.env GM_TOKEN`，`/gm <token> <文案>`） |
| epic/gm 是否抢屏 | **自动切到「世界」页签** + toast |
| 事件链触发 | 迁跃 **8%** / 探险 **10%** |
| 交付范围 | **CLI + HTTP + 网页流/角标/toast 全做** |
| 频道 TTL | 2h / 200 条（沿用稿内默认，可在 config 调） |

待用户说「开工」后按 T1→T7 实现。
