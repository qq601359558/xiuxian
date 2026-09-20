---
feature: wave2-deep-world
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 第二波 · 世界深度：师徒结拜 · 宗门贡献日环 · 除凶围剿 · 世情日程

## Report

**What was built** — 师徒/结拜（`core/social_bonds.py`：双向收徒帖、出师门槛 strength≥3 或境界相近、绝交记业力、传功礼金减半、同场结拜斗法 +5% 已接入 combat_fate）；宗门贡献与日环（`sect_contrib.py`：上交/兑换/三类日环自动 sync、`/宗门势` 实力条）；除凶令与围剿（`hunt.py`：血煞榜、接令结算功德、同场 1.15 系数）；`/世情` 日程（议程+血煞+秘境+近闻）。

**Verification** — `tests/test_wave2.py` 6 passed；全量 **155 passed**（`test_events_ai` PRE-EXISTING 偶发）。评审 major（结拜未接战、出师无门槛、确认不复查存活、收徒只映射确认）已修。

**Journey log** — pending 流确认时必须二次校验存活；规则函数写完必须 grep 战斗/指令调用点；出师用 strength/境界门槛防一键刷功德。

## [S1] Problem

世界已能播报大事件、NPC 会合谋，但玩家侧仍缺：
1. **社会契约**——无师徒/结拜指令，传功无名分；
2. **宗门深度**——俸禄白给，无贡献与日环；
3. **天道自衡可玩**——血煞只被动挨打，无主动除凶与围剿；
4. **世界可见**——`/世情` 与 tick 同义，看不到 NPC 在干什么。

## [S2] Design

### 2.1 师徒 / 结拜（`core/social_bonds.py`）

复用 `KarmaLink`：`link_type ∈ {师徒, 结拜}`。

| 指令 | 规则 |
|---|---|
| `/拜师 <名>` | 对方境界须 **高于** 自己 ≥1 大阶；对方在线/在世；双方已有「恩」或态度非敌对；成功写「师徒」边 |
| `/收徒 <名>` | 对方主动 `/拜师` 前也可由高境界者发起，对方下次 `/确认拜师` 同意 |
| `/确认拜师` | 处理待确认 |
| `/出师` | 师徒边 strength≥3 或弟子境界≥师父-1 可出师；写「恩」 |
| `/结拜 <名>` | 双方同地+安全区；互相 `/结拜同意`；写「结拜」 |
| `/结拜同意` | 双方都同意才成 |
| `/绝交 <名>` | 断师徒/结拜；记业力 5 |

**效果（规则）**：
- 师徒：`transmit_teaching` 费用减半；师父传功功德 +8（原 +5）
- 结拜：同场斗法 power +5%（有边则生效）
- 出师：双方功德 +10，写世界频道 info

进程内 `pending_bonds` 超时 10 分钟自动清。

### 2.2 宗门贡献 + 日环（`core/sect_contrib.py`）

**字段**：`Character.sect_contribution: int = 0`

**上交** `/上交 <货名> [数量]`：须已拜入；从 inventory 扣；贡献 = 商会回收价/10（至少 1）。

**兑换** `/兑换` 列表 · `/兑换 <名>`：

| 货 | 贡献价 |
|---|---|
| 聚气丹 | 8 |
| 回春露 | 5 |
| 一阶青木迷踪阵 | 40 |
| 玄铁护腕 | 35 |

**日环** `/宗门环`：
- 每现实日（按日期字符串）刷新 3 条，存 `world_state["sect_ring"][user_id]`
- 类型：`explore`（完成 1 次探险成功）· `donate`（上交任意 1 件）· `visit`（迁跃到本宗总坛）
- 完成一条 +6 贡献 +2 功德；三条全完额外 +10 贡献
- 进度在对应动作后自动 `sync_ring`

### 2.3 除凶令 + 围剿（`core/hunt.py`）

**除凶榜** `/除凶`：列出 `sin≥80` 或 `blood_marked` 的在世角色（含 NPC），显示境界/地点/业力。

**接令** `/接除凶 <名>`：记 `world_state["hunts"][hunter_id] = target_id`；目标死亡且凶手为 hunter → 功德 +40，业力 -20，世界频道 major；否则失败不惩罚（可 `/弃除凶`）。

**围剿**：斗法前若同场（同 location）另有 ≥1 名非目标角色与 attacker 同接此除凶令，或目标 blood_marked 且同场 ≥2 名玩家——`CombatEngine.calculate_power` 侧在 `combat_fate` 加 `siege_mult = 1.15`。

实现：`combat_fate.resolve_ambush` 开头算 `hunt.siege_multiplier(attacker, defender)`。

### 2.4 世情日程（`core/schedule.py` + 改 `/世情`）

`/世情` 不再只 tick，改为：

```
【世情】
· NPC：X 人有议程（列表最多 12：道号 · 议程 · 所在）
· 血煞：Y 人天道标记（前 5）
· 秘境开启中：Z 处
· 近闻：最近 3 条世界频道 major
（附带仍跑 1 次轻量 tick，文案合并）
```

`/议程` 保持原 list_agendas。

### 2.5 钩子

- 探险成功 → `sect_contrib.sync_ring(explore)`
- `/上交` → sync donate
- `/go` 到宗门总坛 → sync visit
- 斗法杀 blood_marked 且接了除凶 → hunt 结算

## [S3] Out of Scope

- 宗门战/灵田/长老议政（第 3 波）
- 师徒任务链 AI 叙事
- 除凶跨服推送

## Tasks

- [x] T1: models.sect_contribution + social_bonds + 指令 — acceptance: 拜师/结拜/出师/绝交可测
- [x] T2: sect_contrib 上交/兑换/日环 — acceptance: 上交加贡献，日环三类可完成
- [x] T3: hunt 除凶榜/接令/围剿系数 — acceptance: blood_marked 可接；同场加成
- [x] T4: schedule `/世情` 重写 — acceptance: 输出议程+血煞+秘境+近闻
- [x] T5: 测试 + 全量回归 + Review + Finalize
