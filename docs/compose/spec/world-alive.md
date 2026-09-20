---
feature: world-alive
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 世界自己活：传闻池 · NPC 关系网 · 合谋事件

## Report

**What was built** — `core/rumors.py` 传闻池（击杀/成交/拍卖/大劫规则写入，FIFO 上限 40，7 日过期）；`core/collusion.py` 关系边（复用 KarmaLink，击杀记仇+同宗扩散）与同场合谋事件（规则定结局，AI 宁少而准写 80 字叙事，效果仅态度微调）；`/传闻` `/关系` 指令；tick 顺带合谋。

**Verification** — `tests/test_world_alive.py` 5 passed；全量 **142 passed**（`test_events_ai` 危机空 effects 为 PRE-EXISTING 偶发，单测可过）。

**Journey log**
- 传闻零 AI 成本，是 LLM 主导感最便宜的放大器。
- 合谋必须先有关系边，否则 tick 全空转烧预算。
- 冷却 30 分钟/对写入 world_state，防刷。

## [S1] Problem

世界虽有 NPC 心智/议程/主动搭话，但是**孤岛**：无跨 NPC 关系合谋、重大事件不进入坊间传闻、无玩家时世界几乎不推进。

创作者拍板：AI **宁少而准**。

## [S2] Design

### 2.1 传闻池（RumorPool）

- `world_state["rumor_pool"]`：`[{id, text, origin, tags[], created_at, truth, heat}]`
- 写入：击杀、当面成交、拍卖落槌、大劫
- `/传闻 [n]`；上限 40；TTL 7 日

### 2.2 NPC 关系网

- `KarmaLink`：仇/恩/师徒/宗门/盟；击杀记仇 + 同宗扩散
- `/关系 [道号]`

### 2.3 合谋事件

- tick 时同场有边 NPC 对，35% 概率、冷却 30 分钟/对
- 结局类型规则选定；AI 只写叙事；态度 ±5 门禁
- 回流传闻 + 大事记

## [S3] Out of Scope

- 玩家谣言战；完整势力版图；宗门战。

## Tasks

- [x] T1: `core/rumors.py` — acceptance: 写入/列表/过期/上限
- [x] T2: 关系边 + `/关系` — acceptance: 杀后仇边可查
- [x] T3: 同场合谋 + 传闻回流 — acceptance: 有边同场可落账
- [x] T4: 事件钩子 + `/传闻` — acceptance: 指令与事件写入
- [x] T5: 测试 + 回归 — acceptance: pytest 全绿
