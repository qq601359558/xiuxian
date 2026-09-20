---
feature: outdoor-adventure
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 外出探险（打怪升级 + AI 结算）

## Report

**What was built** — `/探险` 列表与 `/探险 <目标>`：野外或秘境。规则算成功率（危险度/境界/战力），扣盘缠与冷却；成功得修为+灵石，失败亏修为；掉落独立掷骰：草药 35%、丹药 25%、装备 18%、**藏宝图 6%**，至多 2 件。AI 写叙事与 0~1 条随机事件（态度/业力功德有 caps），**不能改规则成败与掉落**。新增秘境：剑冢残碑、荒古兽巢、幽冥鬼市、灵药残圃。物品：青锋剑、玄铁护腕、藏宝图。

**Verification** — `test_adventure.py` PASS（目标/本地结算/藏宝图命中率≈5.3%/门禁）。

**Journey log**
- 成败必须以规则骰为准，AI 只服从事先结果，防刷。
- 掉落不由 AI 输出，避免无限掉落。

## [S1] Problem
缺梦幻西游式单次外出探险与更多秘境。

## [S2] Design
见正文设计表；`ADVENTURE_*` 可调。

## [S3] Out of Scope
挖宝使用链、穿戴属性、多回合战棋。

## Tasks
- [x] T1–T5 完成
