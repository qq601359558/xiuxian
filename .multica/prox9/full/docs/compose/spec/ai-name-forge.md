---
feature: ai-name-forge
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# AI 生成丹药 / 法宝 / 妖兽（去重落库）

## Report

**What was built** — `/生成丹药|法宝|妖兽`：AI 起名与属性；排除集=货单+秘境+NPC+已生成；落库 `generated_names`；丹药/法宝并入运行时货单可买卖穿戴。无 AI 时本地词根生成仍去重落库。

**Verification** — `test_forge.py` PASS。

## [S1] Problem
内容手写、易撞名。

## [S2] Design
见 Spec；数值钳制区间见 forge.py。

## Tasks
- [x] T1–T4 完成
