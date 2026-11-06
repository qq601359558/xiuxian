---
feature: item-grades-unify
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 装备 / 丹药 / 功法 品阶统一（网文惯例）

## Report

**What was built** — 网络检索不可用，按修仙网文通行「凡/人/地/天/仙」五档统一。装备三槽（武器/护甲/饰品）按品阶加战力：凡+2~3%、人+4~5%、地+6~8%、天+12%，总上限+20%；同槽自动替换；坊市/掉落分层。丹药与功法维持既有五档。

**Verification** — `test_loot_equip_apoc.py` / `test_pill_buff.py` PASS。

## [S1] Problem
装备无品阶；系统命名不一。

## [S2] Design
五档统一 + 三槽。

## Tasks
- [x] T1–T4 完成
