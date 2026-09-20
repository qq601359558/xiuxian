---
feature: pill-grades
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 丹药品阶与闭关吸收加成

## Report

**What was built** — 丹药三档：凡品+15%（聚气丹）、人品+30%（玄元聚气丹）、地品+50%（九转凝灵丹）；回春露+8%。均「下次闭关生效、出关耗尽」。货单/服用/坊市/观照显示品阶；掉落以凡品为主。

**Verification** — `test_pill_buff.py` / `test_loot_equip_apoc.py` PASS。

## [S1] Problem
要初期好体验，不要全局加速。

## [S2] Design
见品阶表；高阶贵且稀。

## Tasks
- [x] T1–T4 完成
