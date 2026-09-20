---
feature: content-pack
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 内容灌量：奇遇模板 · 日环主题 · 师门任务 · 兑换表 · 环境传闻

## Report

**What was built** — `core/content_pack.py` 集中内容包：奇遇模板 **22** 条、日环主题 **16**、师门任务 **9**、结义 **4**、兑换 **12+5**、环境传闻 **24**；`event_chains`/`sect_contrib`/`social_bonds` 改为从包导入；`rumors.maybe_ambient_tick` 零 AI 闲话（tick 12% / `/世情` 10%，每日上限 5）。

**Verification** — `test_content_pack` 5 passed；全量 **167 passed** 全绿。

**Journey log** — 内容与逻辑分文件，后续加模板只改 content_pack。

## [S1] Problem

系统闭环已通，但内容池太小：奇遇 6 条、日环主题 5 条、师门任务 3 条、兑换 4+2，一周内重复感强；传闻几乎只靠玩家触发。

## [S2] Design

### 2.1 内容包模块 `core/content_pack.py`

集中存放纯数据，避免散落各引擎：

| 池 | 目标量 | 消费方 |
|---|---|---|
| `EVENT_CHAIN_TEMPLATES` | **≥20** | `event_chains.TEMPLATES` |
| `THEME_POOL` | **≥15** | `sect_contrib.THEME_POOL` |
| `MASTER_TASKS` | **≥8** | `social_bonds.MASTER_TASKS` |
| `SWORN_TASKS` | **≥4** | `social_bonds.SWORN_TASKS` |
| `EXCHANGE_SHOP` | **≥10** | `sect_contrib.EXCHANGE_SHOP` |
| `RARE_SHOP` | **≥4** | `sect_contrib.RARE_SHOP` |
| `AMBIENT_RUMORS` | **≥20** | 环境传闻 |

效果字段必须落在 `EVENT_EFFECT_CAPS` 内（exp/stones/lifespan/sin/merit/dao_heart）。

### 2.2 环境传闻（零 AI）

`rumors.maybe_ambient_tick()`：
- 概率 15%/次 tick（或 `/世情` 时 10%）
- 从 `AMBIENT_RUMORS` 抽 1 条，填入随机地名/NPC 名，truth 0.5–0.75
- 限流：同一天最多 5 条 ambient

接线：`npc_agenda.tick_world` 末尾；`/世情` 开头。

### 2.3 不做

- 不改 AI 预算；不做玩家投稿；不做多语言。

## Tasks

- [x] T1: content_pack 全量数据 — acceptance: 各池长度达标
- [x] T2: 引擎改从 content_pack 导入 — acceptance: 原测试仍过
- [x] T3: ambient 传闻 tick — acceptance: 可写入池
- [x] T4: 测试 + 全量 + Review + Finalize
