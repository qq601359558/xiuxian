---
feature: alchemy-craft
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 炼丹 / 炼器：配方 + 材料制

## Report

**What was built** — 炼丹/炼器改为**配方+材料**制：`content_pack.RECIPES`（12 张）+ `core/alchemy.py`；`/配方` `/炼丹` `/炼器`；`/悟丹` `/悟器` 只习得新方（AI 设计配方，不发货），替代原 `/天工` 凭空生成；开炉扣材料与炉火，失败材料损半；默认会 5 张基础方，其余靠悟/探索。

**Verification** — `test_alchemy` 6 passed；全量 **186 passed** 全绿。

**Journey log** — 生成货必须走配方消耗；AI 可创新方但不能绕过材料。

## [S1] Problem

原「天工造化」AI 直接把新丹/新宝塞进货单，像凭空刷货，不符合修仙设定。应改为：**得配方 → 备材料 → 开炉/开炉炼器**，有成败与消耗。

## [S2] Design

### 2.1 配方书 `core/alchemy.py` + `content_pack.RECIPES`

| 字段 | 说明 |
|---|---|
| id / name | 配方名 |
| kind | pill \| equip |
| output | 产出物（须在 `ITEM_CATALOG` 或本次写入） |
| materials | `{百年灵芝:1, 妖兽内丹:1}` |
| stones_fee | 开炉灵石 |
| base_rate | 成功率 0~1（受道心/境界微调） |
| req_tier | 最低境界阶 |
| known_by_default | 是否开局就会 |

**开局默认会**：聚气丹、回春露、青锋剑、玄铁护腕。  
其余靠 **悟得**（见 2.3）。

### 2.2 指令

| 指令 | 语义 |
|---|---|
| `/配方` | 列出已会配方、材料是否齐全、成功率 |
| `/炼丹 <配方名>` | 扣材料+灵石 → 掷成功率 → 成功入包 / 失败材料损半 |
| `/炼器 <配方名>` | 同上，产装备 |
| `/悟丹 <理念>` `/悟器 <理念>` | **替代原 /天工**：AI 写一张**新配方**（不直接出货）；学会后仍要材料才能炼 |

`/自创功法` 不变（那是功法 DSL，不是货）。

### 2.3 悟配方（原 forge 改造）

- AI 输出：配方名、材料 2~3 种（从材料池选）、产出属性落在 caps、成功率
- 校验后写入玩家 `known_recipes` + 全局 `ITEM_CATALOG`（产出定义）
- **不扣材料、不直接给物品**；冷却 1 现实日/人
- 无 AI：从预置隐藏配方池抽一张「习得」

### 2.4 成功率

```
rate = base_rate + 0.03 * tier + 0.001 * (dao_heart - 50)
clamp 0.15 ~ 0.95
```

失败：材料扣 **一半**（向上取整），灵石费全扣，无产出。

### 2.5 持久化

`world_state["known_recipes"][user_id] = [recipe_id...]`  
`character.skills` 可记「炼丹·聚气丹」便于 /道身 展示（可选）。

### 2.6 接线

- `server/world.py`：新指令；`/forge` `/天工` 映射到 `/悟丹`/`/悟器` 或提示改用
- 探险/事件小概率 `learn_random_recipe`
- 贡献兑换可加「残方」（下阶段）

## [S3] Out of Scope

- 炼丹炉耐久、多炉火候小游戏、失败炸炉伤人（可后续）。

## Tasks

- [x] T1: RECIPES + alchemy 引擎 — acceptance: 有材料可炼成/失败可测
- [x] T2: 悟配方改写 forge 接口 — acceptance: 只写配方不发货
- [x] T3: world 指令 — acceptance: /配方 /炼丹 /炼器 /悟丹 /悟器
- [x] T4: 测试 + 全量 + Review
