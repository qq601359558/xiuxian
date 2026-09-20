---
feature: world-director
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: 6f9be93..feat/world-director (see git log)
---

# M1 天道导演 WorldDirector

## Report

**What was built** — 运行时世界导演层：`core/world_director.py` 收集全服简报后由 AI（或标注 `local` 的降级）提案 `directives[]`；规则门禁 admit（类型白名单、effects 剥离数值权威键、大劫窗口、冷却/并发）；落账写入 `world_state["director"]`、世界频道、可拒绝机缘目标、秘境提前开启（`is_open = now-last >= interval`）。玩家可用 `/天道` 查看、`/天道 推演` 强制一轮；世情与 CLI 显示天道态势；NPC tick 与大境界突破可触发（仍受冷却）。

**Verification** — `tests/test_world_director.py` **9 passed**；相关套件（channel/alive/phase1/ai_platform/command_fixes/cli_parity）通过；全量 `tests/` **249 passed**。`tests/test_events_ai.py::test_crisis_can_burn_lifespan_or_stones` 在全量并发下偶发空 effects，**单跑通过**，属 **PRE-EXISTING** 间歇（world-alive 报告已记录），非本模块引入。

**Journey log**
- 不建 worktree：会话安全钩禁止 `git worktree add`；用户授权原地 `feat/world-director`。
- 秘境「提前开启」语义是 cooldown 可用窗口，须写 `now-interval` 而非 `now`。
- Review major：`stats.runs` 不得在冷却跳过时自增；无 AI 测试必须强制清 Key，否则会空洞通过。
- AI 可主导「世界发生什么」，不可主导胜负数值——提案协议是后续 M2–M5 的扩展点。

## [S1] Problem

创作者目标是「网游小说里 AI 主导游戏走向」，不是再堆旁白。现状是规则骨架完整，但世界走向几乎由静态规则与模板决定：AI 只解释结果，不提案「这个世界下一刻往哪走」。玩家感知不到天道/主脑在控局。

决策（已确认）：
- 首模块：**M1 天道导演 + `/天道` 可见**
- 权限：**AI 提案 + 规则宪章**（不直接改胜负/寿元/掉落公式）
- 节奏：**周期 tick + 事件触发**
- 流程：compose-next；workspace 覆盖为 **原地 `feat/world-director` 分支**（用户授权，不建 `.worktrees`）

后续模块（M2 世界弧 / M3 势力 / M4 玩家回写 / M5 纪元回流）不在本 Spec 落地，但指令协议要能扩展类型。

## [S2] Design

### 2.1 角色定位

`WorldDirector` 是运行时「世界走向提案者」：

1. 收集世界简报（存活/境界/血煞/秘境/赛季/传闻摘要）
2. AI（或测试本地降级）输出 `directives[]`
3. **规则门禁** admit：类型白名单、效果键白名单、冷却、并发上限、赛季窗口
4. 落账：`world_state["director"]` + `WorldChannel` + 可选机缘目标 + 秘境提前开启 + 世情展示
5. 玩家用 `/天道` 查看；后台 tick 与大境界突破可触发

**原则**：AI 决定「世界发生什么类型的事」；数值权威仍在规则。提案必须真实写入世界态，否则仍是旁白。

### 2.2 数据：`world_state["director"]`

```json
{
  "last_run_ts": 0,
  "last_trigger": "timer|breakthrough|command|test",
  "last_source": "ai|local|error|skipped",
  "last_error": "",
  "last_accepted": 0,
  "active": ["<directive>"],
  "history": ["<最近 20 条摘要>"],
  "stats": {"runs": 0, "accepted": 0, "rejected": 0}
}
```

Directive：

```json
{
  "id": "d_xxxxxxxx",
  "type": "omen|secret_realm_pressure|blood_tide|sect_tension|calamity_forecast",
  "title": "≤40 字",
  "narrative": "≤160 字",
  "location": "",
  "priority": 1,
  "duration_sec": 3600,
  "effects": {},
  "source": "ai|local",
  "created_at": 0,
  "expires_at": 0,
  "applied": {"channel": true, "goals": 0, "realm": "", "flags": []}
}
```

### 2.3 类型与效果门禁（规则宪章）

| type | 含义 | effects 允许键 | 落账行为 |
|---|---|---|---|
| `omen` | 预兆/机缘风声 | `goal_title`, `goal_detail`, `whisper` | 频道 major；对最多 `DIRECTOR_GOAL_FANOUT` 名在线活人 `GoalEngine.add_opportunity`（可拒） |
| `secret_realm_pressure` | 秘境潮/禁制松动 | `realm_id`（须在 `SECRET_REALMS`）, `force_open`(bool), `goal_title`, `goal_detail` | `force_open=true` 时导演提前开启该秘境；频道 major/epic |
| `blood_tide` | 血煞异动 | `location`（须在 `WORLD_LOCATIONS` 或空）, `whisper` | 频道 major；director.active 记血煞态势；**不点名「必杀某人」** |
| `sect_tension` | 宗门紧张 | `sect_a`, `sect_b`, `location`, `whisper` | 频道 major；只写态势，**不改宗门数值表** |
| `calamity_forecast` | 大劫预兆 | `whisper` | 仅当 `season_info.is_final_week` 或剩余天 ≤ `SEASON_WARN_DAYS`；频道 epic |

**强制剥离的 effects 键**（提案中出现只 strip，不整单拒绝，除非整条 type 非法）：
`exp`, `stones`, `lifespan_years`, `sin`, `merit`, `dao_heart`, `power`, `death`, `kill`, `target_player`, `item`, `skill`。

非法 `type` → 整条 reject + 审计/计数。`calamity_forecast` 在非大劫窗口 → reject。

### 2.4 调度

- 常量：`DIRECTOR_MIN_INTERVAL_SECONDS`（默认 480）、`DIRECTOR_MAX_ACTIVE`（默认 3）、`DIRECTOR_TTL_SECONDS`（默认 3600）、`DIRECTOR_GOAL_FANOUT`（默认 5）
- `WorldDirector.run_cycle(trigger, force=False, now=None)`
  - 非 force 且距 `last_run_ts` < min interval → `{ok:False, skipped:"cooldown"}`
  - 活跃 directive ≥ max 且未过期 → skip `max_active`
  - `force=True` 可越过冷却（`/天道 推演` 与测试）
- 触发：
  - `World._tick_loop`：每轮尝试 `run_cycle(trigger="timer")`（冷却控制实际频率；`DIRECTOR_TICK_INTERVAL_SECONDS` 作为 tick 侧更长的参考闸，避免每 2 分钟 NPC tick 都进导演逻辑——见 2.5）
  - `_breakthrough` 大境界成功 → `run_cycle(trigger="breakthrough")`（不 force，仍受冷却）
  - `/天道 推演` → `run_cycle(trigger="command", force=True)`

### 2.5 与世界 tick 集成

`NPC_TICK_INTERVAL` 仍控制 NPC；导演在 tick 循环中**先查墙钟**：距上次导演运行 < `DIRECTOR_TICK_INTERVAL_SECONDS`（默认 600）则直接 return skipped=`tick_gate`，避免与 NPC tick 耦合过密。测试通过 `force=True` 或调短 env/常量。

### 2.6 AI 通道

- Scene：`world_director`（`play_prompts.director_prompt` + registry + quota 限 6/min）
- Prompt 要求：只输出 `{"directives":[...]}`；类型/地点/秘境 id 只能来自简报；禁止 token/改数值权威
- 无 Key 且无 `ALLOW_LOCAL_AI`：`run_cycle` → `ok=False`, `last_source=error`, `last_error=ai_unavailable_message`；**不伪造「天道已裁」**
- `ALLOW_LOCAL_AI=1`：确定性本地预兆（`source=local`，历史与 `/天道` 标明 local）

### 2.7 玩家可见

- `/天道` / `/heaven`：导演面板（上次运行、来源、活跃指令、简要历史）
- `/天道 推演`：强制跑一轮（正式需 AI；local 测试可降级）
- `format_world_schedule`：增加【天道导演】一节列出活跃指令
- 帮助文案含 `/天道`

### 2.8 秘境提前开启

`core/secret_realm.py` 新增 `director_force_open(rid, now)`：校验 rid ∈ `SECRET_REALMS`。  
**语义**：`realm_status.is_open = (now - last_open_ts) >= interval`；因此「提前开启」将 `last_open_ts` 写为 `now - interval`（而非 `now`），使秘境立即进入可开启态；探索门槛与地点规则不绕过。导演仅当 effects 调用该 API。频道广播带 30 分钟冷却。

### 2.9 目标投射范围

Character 无 online 字段；机缘目标 fanout 近似为「存活且非 `npc_`/`ai_npc_` 前缀」的玩家，上限 `DIRECTOR_GOAL_FANOUT`。

### 2.10 审计与统计

- admit reject / apply 均写 `ai.audit`（`source=ai.world_director`；directive 上的 `source=local` 会体现在 apply 事件）。
- `stats.runs` 仅在进入实际提案阶段时 +1；冷却/tick 闸/max_active 跳过只 + `stats.attempts`，避免把 NPC tick 误计为导演拍板。

### 2.11 测试边界

- 单测注入 fake gateway / 本地降级，不依赖外网 Key；无 AI 路径强制清空 `LLM_API_KEY`/`USE_CCSWITCH`
- 频道限流在测试里 reset（沿用 `test_world_channel_b1` 模式）
- 不回归：NPC tick、世情文本结构仍可解析、目标系统既有测试

## [S3] Out of Scope

- M2 事件弧状态机（预兆→升级→决算）
- M3 宗门战/联盟数值、M4 全量玩家回写表、M5 传说改写 Director 权重
- AI 直接改寿元/战力/胜负/掉落
- 多端联机、付费额度 UI
- 网页专用面板（指令与世情文本足够；网页后续对齐）

## Tasks

- [x] T1: Spec 本文档 — acceptance: 状态 designed，契约完整 (covers: S2)
- [x] T2: config + prompt + quota scene `world_director` — acceptance: 常量存在；registry 可取 scene；quota 含限流 (covers: S2.6)
- [x] T3: `core/world_director.py` 门禁+调度+落账+format — acceptance: admit/strip/run_cycle/状态持久化可测 (covers: S2.2–S2.4, S2.6, S2.9–S2.10)
- [x] T4: `secret_realm.director_force_open` + schedule 天道节 + `world.py`/`cli` `/天道` 与 tick/突破钩子 — acceptance: 指令可查可推演；tick 有闸；突破可触发 (covers: S2.4–S2.8)
- [x] T5: `tests/test_world_director.py` + 相关回归 — acceptance: 新测全绿；相关旧测不回归 (covers: S2.11)
