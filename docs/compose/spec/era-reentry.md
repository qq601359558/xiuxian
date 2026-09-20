---
feature: era-reentry
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: (landed via feat/world-director)
---

# M5 纪元回流 EraReentry

## Report

**What was built** — `core/era_reentry.py`：传说 tags/weight → 导师类型 bias；大劫 `settle_apocalypse` 快照 `era_legacy` 并 epic 播报「纪元回流」；简报/`/天道`/`/传说`/`/纪元回流` 展示权重；local 导师按史笔出种子；AI 提案 `reorder_by_bias`，缺权重类型可补 `ai+era` 种子（仍过 admit）。门禁不绕过。

**Verification** — `test_era_reentry` **5 passed**；全量（除 events_ai AI 通道超时）**276 passed**。

**Journey log**
- 史笔必须「影响下一拍提什么」，否则只是档案馆。
- calamity bias 被钳制，且仍须大劫窗口门禁。
- 五件套 M1–M5 的「AI 主导」闭环到此在模块边界内齐了。

## [S1] Problem

M1–M4 已能让天道/势力/玩家改写世界，但 **上一纪的史笔几乎不改变下一刻导演拍什么**。传说库是死档案，不是「世界记忆」。

创作者要求 M5 模块 100%：传说/大劫 → 导师提案权重与可引用记忆。

## [S2] Design

### 2.1 状态 `world_state["era_legacy"]`

- `completed_eras[]`：每纪 `bias` / top legends / anchors
- `active_bias`：当前纪活跃导师类型权重
- `anchors`：从传说文本提取的地点
- `last_apocalypse_season` / `cited_count` / `log`

### 2.2 Tag → Director Type

| legend tags | 提案类型加权 |
|---|---|
| blood_feud / blood_tide / siege / hunt | `blood_tide` |
| sect_crisis / faction | `sect_tension` |
| realm_storm | `secret_realm_pressure` |
| apocalypse / calamity_arc | `calamity_forecast`（钳 ≤3，仍须大劫窗口门禁） |
| omen / player / highlight / answered | `omen` |

权重乘 `legend.weight`；与历史纪 snapshot 合并。

### 2.3 运行时接入

1. **大劫结算** `settle_apocalypse` → `on_apocalypse_settle(ended)` 写 snapshot + epic「纪元回流」+ 重建 bias  
2. **导演简报** 含「纪元回流权重」  
3. **local 导师** `seed_local_directives` 按 bias 吐种子  
4. **AI 提案** `reorder_by_bias`；缺 bias 类型时可补一条 `source=ai+era` 种子  
5. **`/天道` / `/传说` / `/纪元回流`** 可见  
6. **tick** 纪元号变化时重建  

### 2.4 边界（模块 100% 不做）

- 不绕过 admit 门禁 / 不直接改数值  
- 不做跨机器世界存档迁移  
- 不做「必刷某玩家」点名剧情  

## Tasks

- [x] T1: Spec
- [x] T2: `core/era_reentry.py`
- [x] T3: 大劫钩子 + 导师简报/种子/重排 + 指令
- [x] T4: 测试 + 回归
