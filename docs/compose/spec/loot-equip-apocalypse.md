---
feature: loot-equip-apocalypse
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 挖宝 / 装备 / 大劫结算 / 功法战力

## Report

**What was built** — `/挖宝` 消耗藏宝图（机缘/空图/杀劫）；`/穿戴` `/卸下` 装备并加战力（+5%/件，上限15%）；功法神通进战力（最高+20%）；`/大劫` 结算：纪元终了全员应劫、道统、纪元重开（大乘+高功德可飞升）；新号入世三步引导。季末最后一小时判定为 `is_ended`（修原来几乎到不了终局的 bug）。

**Verification** — `test_loot_equip_apoc.py` / `test_adventure.py` PASS。

## [S1] Problem
图与装备无用；大劫无结算；功法不进斗法。

## [S2] Design
见实现；战力系数有硬顶。

## [S3] Out of Scope
坐标挖宝 UI；套装共鸣。

## Tasks
- [x] T1–T5 完成
