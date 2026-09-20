---
feature: living-jianghu
status: delivered
updated: 2026-10-13
branch: (no-git-in-place)
commits: n/a
---

# 服务器江湖 · AI 中台 · 因果账 · 规则仿真

## Report

**What was built** —  
**Phase A（中台 + 账 + 投影）**：`ai/registry|quota|router` 统一 AI 入口；`core/jianghu.py` + `jianghu_events` 因果账；CLI `/近况` `/目标`、LAN `/world/feed` `/world/briefing` `/who` 投影；GoalEngine 保留 phase1 契约并接江湖目标。  

**Phase B（加深：会改世界的仿真，非文案）** — `core/jianghu_sim.py`：
- 议程 **规则权威结算**：寻仇（仇边选目标→追击/安全区对峙/野外斗法→杀/伤/逃）、夺宝（盯梢/坊市窃取/拦路抢劫）、闭关（圆满即 `BreakthroughEngine` 天劫，可突破可陨落）、巡守（血煞目标→围杀/扑空）、避劫（遁入坊市/破财消业/敛息）。
- **级联** `cascade_kill`：同门记仇 + NPC 议程改写为寻仇、除凶榜、世界频道血雨、因果账 cascade 字段；玩家击杀走 `combat_fate` 同一入口。
- **离线追赶** `simulate_offline`：按 `last_sim_ts` 每约 30 分钟一波，批量结算 NPC 并落账；服务器启动与 `/世情` `/近况` 自动触发。
- **AI 降级为说书人**：`npc_agenda` prompt 只润色已裁定结局，禁止改 action/outcome；`source=rule` 或 `rule+ai`。
- 合谋：仇边同图非安全区时直接走 `resolve_agenda(revenge)`，不再只有「按剑未发」文案。

**Verification** —  
- `tests/test_jianghu_sim.py` **6 passed**（寻仇击杀+同门级联、闭关天劫、夺宝改灵石、离线追赶、巡守接敌、tick_one 走仿真）  
- 焦点：`test_npc_agenda` + `test_living_jianghu` + `test_jianghu_sim` **17 passed**  
- 全量 `tests/`（排除需外网 `test_ai_connection`/`test_events_ai`）：**229 passed**；`test_qi_pace::test_newbie_meditation_boost` 在污染库上 `exp_gained=123<150` — **PRE-EXISTING / 灵气稀释与库内高阶 NPC 有关**，本特性未改闭关公式  
- 独立评审（Phase A）：无 critical；中项已修  

**Journey log**
- 「活」不能靠再堆投影：必须让议程 **改状态**（灵石/生死/位置/议程/宗门仇恨）。
- AI 驱动数值会崩档且对不上账；正确拆分是 **规则结算 → AI 叙事**。
- 测试库同名角色会干扰 `find_alive_by_name`，仿真测试须用唯一道号。
- `GOAL_MAX_ACTIVE=6` 与 Spec 早期「≤3」冲突时以存档兼容为准。
- 仓库无 git，`branch: (no-git-in-place)` 原地交付。

## [S1] Problem

对标「网游小说服务器江湖」：世界在玩家不在时仍推进；人事有后果；AI 不是数值引擎。

## [S2] Design

### 2.0 架构

```
议程/离线波次/玩家动作
    → JianghuSimulator.resolve_agenda / cascade_kill / simulate_offline  （规则）
    → Character / NpcAgenda / KarmaLink 状态变更
    → jianghu.append_event（唯一公账）
    → AI 中台（可选）只润色 narrative
    → 投影：CLI / LAN / 目标 / 频道
```

### 2.1 仿真结算契约

| 议程 | 目标来源 | 可能结局（outcome） |
|------|----------|---------------------|
| revenge | 仇边/血煞相关 | pursue, stare, kill, wounded, escaped, snoop |
| treasure | 高灵石角色 | chase_loot, pickpocket, rob, rob_kill, rob_fail |
| seclusion | — | cultivate, breakthrough, tribulation_fail, tribulation_die |
| patrol | 血煞/重业 | patrol_deploy, patrol_watch, patrol_kill, patrol_fail |
| survive | — | flee_safe, bribe, hide |

安全区禁止动武；野外用 `CombatEngine.calculate_power` 比率掷骰。

### 2.2 级联

击杀 → 仇边、同门 NPC `agenda_type=revenge` 且 `target_hint=凶手名`、传闻、频道、除凶提示、账 `rule_result.cascade`。

### 2.3 离线

`world_state["jianghu_sim_last_ts"]`；波次 `elapsed // 30min`，上限 8 波 / 20 次行动；`force=True` 至少一波。

## [S3] Out of Scope

- 真跨进程分布式仿真；完整宗门战；AI 直接改 status/realm。
- 批量清洗历史测试角色。

## Tasks

- [x] T1–T8 Phase A：中台 / 账 / LAN / 目标 / CLI（见上一版验收）
- [x] T10: `core/jianghu_sim.py` 规则结算各议程 — acceptance: test_jianghu_sim 覆盖 revenge/seclusion/treasure/patrol
- [x] T11: `cascade_kill` + combat_fate/同门议程改写 — acceptance: 寻仇测试中同门级联可断言
- [x] T12: `simulate_offline` + 服务器/CLI 接入 — acceptance: 伪 3h 离线后 waves≥1 且 format 可读
- [x] T13: AI 仅叙事（play_prompts npc_agenda）+ tick_one source=rule(+ai) — acceptance: test_tick_one_uses_simulator
- [x] T14: 回归 — acceptance: 焦点套件绿；全量 229 passed（1 项 qi PRE-EXISTING）
**已确认决策**：

| 决策点 | 拍板 |
|--------|------|
| 主路径 | 先 R1 离线人事 + R2 因果账 + R5 AI 绑事实；再 R3 目标 / R4 近况投影 |
| 服务器感 | **NPC 仿真江湖 + 真人 LAN** 首期同时具备 |
| AI 中台深度 | **先重构中台，再接业务**（Prompt 注册、场景路由、成本配额、评测；再叠江湖） |
| Workspace | 仓库无 git；沿用既有 Spec 的 `branch: (no-git-in-place)` **原地**交付 |

细化后的真正需求：

| ID | 问题 | 行为契约 | 验收标准 | 明确不做 |
|----|------|----------|----------|----------|
| R1 | 无玩家时世界不动 | NPC 按议程产生可查事件（结仇/夺宝/闭关/调动），预算与冷却可控 | 冷启动/强制 tick 后：因果账与频道出现 ≥1 条可追溯到 NPC + 规则结果的事件；单轮 tick 有事件数上限 | 不做全 NPC 每 tick 全行动；AI 不得直接改寿元/境界 |
| R2 | 事实分散 | 江湖因果账为唯一事实源；频道/世情/角色档案/目标均为投影 | 同一 event id 在账、频道、档案中可对上；写入口径唯一 | 不重做整套 UI 皮肤 |
| R3 | 无世间目标 | 从因果账/恩怨/宗门生成 1–3 条可追踪目标 | 玩家能看到与自己相关的目标，且依赖世界状态完成 | 不做任务编辑器/通行证 |
| R4 | 登录像功能表 | 进入游戏先见「世间近况 + 与你何干」 | 主路径接口/CLI 提供近况与目标摘要 | 不在本轮重做视觉 |
| R5 | AI 脱离事实 | 一切中台调用：事实包 → Prompt 注册表 → 校验/GATE → 落账或拒绝 | 未注册 scene / requires_facts 无包 / 配额超限 → 明确拒绝；GATE **剥离**未知 `ref_ids`（不是整单拒绝）；无 KEY 返回可预期错误/本地降级 | 不放开数值钳制 |
| P0 | 中台未收口 | 场景路由、Prompt 注册、配额、调用审计、最小评测集先就位 | 单元测试覆盖注册表/路由/配额；业务改走统一入口 | 不引入外部中台产品 |

## [S2] Design

### 2.0 架构总则

```
业务指令 / NPC 议程 / tick / LAN 请求
        │
        ▼
┌─────────────────────────────────────┐
│  AI 中台（先建）                      │
│  registry · router · facts · gate   │
│  validator · audit · quota · probe  │
└──────────────┬──────────────────────┘
               │ 提案 / 叙事（JSON，可拒）
               ▼
┌─────────────────────────────────────┐
│  规则引擎（数值权威）                  │
│  结算 → 因果账 event_id              │
└──────────────┬──────────────────────┘
               │ 投影（只读）
        ┌──────┼──────┐
        ▼      ▼      ▼
     频道/世情  档案   LAN /who·/feed·目标
```

- **规则定生死，AI 定人心与说书**；AI 永不直接写 `status`/`realm`/`lifespan` 等权威字段。
- **先中台后业务**：业务改造不得再散落拼 HTTP/私有 prompt。
- **NPC 与 LAN 同读因果账**：真人联机看到的江湖，与离线 NPC 推进的是同一本账。

### 2.1 AI 中台重构（P0，先于江湖业务）

**目标**：演进现有 `ai/`（gateway/facts/gate/validator/audit/play_prompts），不做推倒重来，但收成中台契约。

**新增/调整模块（建议路径）**：

| 模块 | 职责 |
|------|------|
| `ai/registry.py` | 场景 Prompt 注册：`scene_id → {builder, schema_hint, max_tokens, requires_facts}` |
| `ai/router.py` | 统一入口 `invoke(scene_id, *, facts, payload, actor_id)`：拼 prompt → 配额 → gateway → schema 校验 → audit |
| `ai/quota.py` | 进程内/`world_state` 场景级配额（次/分钟、日预算），超限拒绝并返回可展示原因 |
| `ai/facts.py`（扩展） | FactPack 增加：因果账近 N 条、恩怨边、NPC 议程摘要、赛季；`known_ids` 含 event/npc id |
| `ai/play_prompts.py`（收口） | 现有 builder 挂到 registry；禁止业务再直接 `_chat_json`（迁移期允许，标 deprecated） |
| `ai/evalset.py` + `tests/test_ai_platform.py` | 最小评测：注册表完整性、无 known 拒绝、配额拒绝、路由降级路径 |

**统一 invoke 契约（行为）**：

1. `scene_id` 未注册 → 明确错误，不发起网络请求。
2. `requires_facts=True` 且无 FactPack → 拒绝。
3. 无 AI 通道：`local_ai_allowed` 时走该场景 `fallback`；否则返回 `ai_unavailable_message()`。
4. 所有成功/失败调用写 `calllog` + audit（scene_id, actor, ok, latency_ms）。
5. 返回值一律结构化：`{ok, scene_id, data|error, ref_ids}`。

**迁移顺序**：registry/router/quota/facts 扩展 → 将 `npc_agenda`、`combat_fate`、`world` 事件、`npc_mind` 交谈改为 `invoke` → 删除或降级散落调用为只读包装。

### 2.2 江湖因果账（R2）

**存储**：扩展现有 `EventLedgerRepository` / 新增 `JianghuEvent` 统一结构（优先复用，避免第二真相源）。

```python
# 行为契约字段（示意）
{
  "id": "ev_...",
  "kind": "npc_agenda|collusion|kill|trade|bounty|sect|player_action|lan",
  "actor_ids": ["..."],
  "target_ids": ["..."],
  "location": "青云坊市客栈",
  "rule_result": {},          # 规则结算快照
  "narrative": "...",         # AI 叙事，可空
  "ref_ids": ["..."],         # 引用的事实 id
  "created_at": 0.0,
  "season_day": 0,
  "visibility": "public|sect|private",
}
```

**写入口径**：仅规则引擎结算后 `append_jianghu_event(...)`；AI 只能附带 `narrative`/`ref_ids`，不能单独建账。

**投影**：

- `/世情`、世界频道、`/who` 附带近况
- LAN：`GET /world/feed?since=`（既有 messages 之上增加事件类型过滤）
- 角色档案：与我相关的账（actor/target/link）

### 2.3 离线 NPC 演化（R1）

**节流**：

- `NPC_TICK_INTERVAL_SECONDS`（已有）+ **每 tick 事件预算**（如 ≤3 条公共事件）
- 每 NPC 冷却沿用 `NPC_COOLDOWN_SECONDS`
- 无玩家在线时可跑「追赶 tick」：按现实经过时间折算，但仍有总预算上限

**议程 → 账**（规则优先，AI 叙事可选）：

| 议程 | 规则动作（示例） | 账 kind |
|------|------------------|---------|
| revenge | 目标在世且同图 → 尝试伏击/写仇边推进 | npc_agenda |
| treasure | 同图市场/野外 → 争夺或成交尝试 | trade / npc_agenda |
| seclusion | 进入闭关状态一段时间或突破尝试（成功率仍走规则） | npc_agenda |
| patrol | 同宗区域写巡守记录，低概率遇敌 | npc_agenda |
| social | 打探：概率刷新对目标的态度/传闻 | npc_agenda |
| survive | 撤离高危区或主动缴罚/投靠 | npc_agenda |

NPC 战斗/死亡仍走现有规则与 GATE；**禁止**中台直接 `character.status = DEAD`。

### 2.4 LAN 真人可见（首期包含）

- 所有仿真事件与真人事件写入同一因果账。
- LAN 客户端/CLI：登录后优先展示「近况摘要 + 与我相关」。
- `GET /world/feed`、`/who` 返回带 `event_id` 的投影；多端同服看到同一江湖。
- 真人行动（击杀/成交/悬赏/闭关）写账 kind=`player_action` / 既有 kind，与 NPC 对称。

### 2.5 目标与近况（R3/R4，中台+账就绪后）

- `core/goals.py`：从账 + 恩怨 + 宗门 + 血煞 生成玩家目标（上限 3 条 active）。
- 登录摘要：`/世情` 强化或 `/近况`：事件流 + 目标进度。
- 目标完成只由规则判定，AI 可解释「为何这算扬名」，不直接发放数值。

### 2.6 错误与降级

| 情况 | 行为 |
|------|------|
| AI 无 Key / 探测失败 | 中台返回明确 reason；NPC 用确定性议程规则落账，叙事可空 |
| Prompt/schema 失败 | 该次提案丢弃，记 audit；不半写账 |
| 账写入失败 | tick 回滚该条，记 warning；不影响其它 NPC |
| 配额超限 | 业务展示「天道忙碌/预算用尽」；规则路径继续 |

### 2.7 存档兼容

- 不删改既有 `characters` 权威 JSON 字段语义。
- 新账新表或扩展列向后兼容；旧档角色无需迁移即可登录，仅近况从空账开始。
- 测试数据清理纪律：禁止非法 status 残留（见 `test_list_alive_resilience` finally 模式）。

### 2.8 测试边界

- 中台：registry/router/quota/facts 拒绝路径（无网可跑）。
- 因果账：写入投影 id 一致性。
- R1：mock/`ALLOW_LOCAL_AI=0` 下规则议程仍能落账（不依赖外网）。
- LAN：`test_lan_smoke` 类接口契约扩展后回归。
- 回归：`tests/` 全量相关模块；基线若已有失败标 `PRE-EXISTING`。

## [S3] Out of Scope

- 不引入外部「AI 中台产品」或新语言栈。
- 不在本轮做完整宗门战/跨服/赛季结算重做。
- 不把 R3/R4 做成任务编辑器或通行证。
- 不允许 AI 绕过 GATE 直接改权威数值。
- 不做大规模前端视觉重做（只保证 CLI/HTTP 投影可用）。
- 不删除现有联调角色数据；不强制清洗正式库历史测试档（非法 status 除外，已在韧性测试约束）。

## Tasks

> 依赖顺序：中台 → 账 → 离线演化/LAN 投影 → 目标近况。

- [x] T1: `ai/registry.py` + `ai/quota.py` + `ai/router.invoke` — acceptance: 单测覆盖：未注册 scene 拒绝；requires_facts 无包拒绝；配额超限拒绝；成功路径写 calllog（covers: S2.1, R5, P0）
- [x] T2: FactPack 扩展因果/恩怨/议程摘要 + `known_ids` 含 event/npc — acceptance: 单测 FactPack 含新增块且 known 含 id（covers: S2.1, R5）
- [x] T3: 现有关键 AI 调用点迁到 `router.invoke`（npc_agenda / npc_mind / npc_proactive / combat / world_event / tribulation）— acceptance: 业务主路径经中台；相关旧测试通过（covers: S2.1; depends: T1）
- [x] T4: 因果账 `core/jianghu.py` + `JianghuEventRepository` + 投影读取 — acceptance: 单测同一 id 出现在账与相关投影；kill/NPC tick 可写入（covers: S2.2, R2）
- [x] T5: NPC 议程 tick 接因果账 + 每 tick 事件预算 + 无 AI 时规则落账 — acceptance: 强制 tick 后账中出现可追溯 npc_agenda 事件；预算超限不再追加（covers: S2.3, R1; depends: T4）
- [x] T6: LAN `GET /world/feed` 与 `/world/briefing` — acceptance: 接口返回与账一致的近况/事件（covers: S2.4; depends: T4）
- [x] T7: `core/goals.py` GoalEngine（保留 dao/newbie/season 契约）+ 江湖投影目标 — acceptance: phase1 目标测试通过；add_opportunity 可挂机缘（covers: S2.5, R3; depends: T4）
- [x] T8: `/近况` `/目标` CLI + 世情附加因果账 — acceptance: CLI 输出含事件与目标（covers: S2.5, R4; depends: T6, T7）
- [x] T9: 回归与文档 — acceptance: 相关 pytest 通过并记录命令；Spec Report 填写验证证据（covers: S2.8; depends: T1–T8）
