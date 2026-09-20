---
feature: player-echo
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: (landed via feat/world-director)
---

# M4 玩家回写 PlayerEcho

## Report

**What was built** — `core/player_echo.py`：玩家击杀/业力/突破/除凶的持久回写档案；区域 danger/panic 与热度；坊市恐慌买卖倍率（钳制）；除凶池功德加成；同场 NPC 态度与议程偏置；连斩惊动导演；`/望气` `/望气 己`；`/look`/`/profile`/世情/天道/除凶榜可见。安全区规则不变。

**Verification** — `test_player_echo` + faction + director 相关通过；全量见交付。

**Journey log**
- 回写是「世界因你而变」的结构层，不是再加一条击杀播报。
- 恐慌价有硬钳，避免经济崩坏。
- 安全区/庇护不在 M4 范围内削弱。

## [S1] Problem

M1–M3 之后，玩家重大行为（连杀/重业/突破）对**世界结构**的改写仍偏弱：区域不「变凶」、坊市不「恐慌」、除凶池无压力、望气不可感。创作者要求 M4 模块 100%，禁止偷懒。

权限：**规则回写权威**；AI 只叙事/导演提案，不直接改价。

## [S2] Design

### 2.1 状态 `world_state["player_echo"]`

- `echoes[char_id]`：连斩窗、累计斩、业力峰、名气、地点热点、标签
- `region[loc]`：danger / kill_24h / panic / top_actor
- `market`：buy_mult / sell_mult / panic / reason（钳 1.0–1.35 / 0.75–1.0）
- `bounty`：n_marked / pool_bonus / hunt_heat
- `mood`：blood_index / fear_index
- `stats` / `log`

### 2.2 回写事件

| 事件 | 世界效果 |
|---|---|
| 玩家击杀 | 区域 danger↑、连斩、名气+3、同场 NPC 态度↓、频道望气、连斩≥3 或业力≥80 惊动导演 |
| 业力飙升 ≥40 | 区域 danger/panic↑、频道；sin≥120 强制导演 |
| 大境界突破 | 名气+5 |
| 玩家进入除凶榜 | bounty.n_marked↑ → 池功德加成、hunt_heat |

### 2.3 系统消费

- **坊市**：`buy_from_guild` 单价×buy_mult；`sell_to_guild` 回收×sell_mult
- **热度**：`region_heat` 合入 `location_heat_for` 与江湖战力
- **NPC**：高危区 survive/patrol；对 top_actor 仇视→revenge
- **除凶**：榜面显示压力；`settle_kill` 功德 + `hunt_merit_bonus`（≤30）
- **可见**：`/望气` `/望气 己`；`/look` 凶名与区域；`/profile` echo 字段；世情/天道摘要
- **tick**：`decay_echoes` 危险衰减、恐慌回落

### 2.4 边界（模块 100% 的「不做」）

- **不关闭**安全区/庇护/三护栏（规则不变）
- 不做 M5 传说改写下一纪元导演权重
- 不做复杂物流/全服经济模型
- AI 不直接改灵石与胜负

## Tasks

- [x] T1: Spec
- [x] T2: `core/player_echo.py` 状态与回写 API
- [x] T3: 坊市/热度/NPC/除凶/导演/look 接线
- [x] T4: 测试 + 回归
