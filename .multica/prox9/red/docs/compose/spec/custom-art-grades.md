---
feature: custom-art-grades
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 自创功法：品阶与功效说明

## Report

**What was built** — 五品阶（凡/人/地/天/仙）由修炼倍率反推；规则钳制高倍率必付代价；完整 DSL 存入 `custom_arts`；闭关按最高倍率加成并按功法额外燃寿；`/自创功法` 输出中文功效卡片，`/功法` 列表。

**Verification** — `test_custom_art.py` PASS。

**Journey log**
- 品阶以数值为准，AI 写 rank 可被覆盖。
- 多门功法取 max 倍率/燃寿，不叠加。

## [S1] Problem
只有名字看不懂功效，数值未生效。

## [S2] Design
凡1.0–1.2 / 人1.2–1.5 / 地1.5–1.8 / 天1.8–2.2 / 仙2.2–2.5（封顶）。

## [S3] Out of Scope
品阶升级、多功法切换。

## Tasks
- [x] T1–T5 完成
