---
feature: play-prompts
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 玩法 Prompt 库：机缘/斗法/突破/心魔/言行/世界事件等

## Report

**What was built** — `ai/play_prompts.py` 集中 **27 个玩法 Prompt Builder**（斗法/天劫/世界事件/心魔/言行/探险/功法/复仇/造化/奇遇三段/日环/师门/传闻/围剿/出师/合谋/NPC×3 + **当面交易旁白、NPC 议价、拍卖喊价、落槌判词、商会买卖**）。统一「角色 + 硬约束 + 输出 schema」；已接入 `gateway`、`ai_flavor`、`trade`、`market`，schema 与门禁兼容。

**Verification** — `test_play_prompts` + trade/flavor 相关 22 passed；全量 **180 passed** 全绿。

**Journey log** — 改 Prompt 只动库文件；gateway 留 try/except 兜底原文；schema 必须与 `gate.admit` 一致。

## [S1] Problem

AI 调用 prompt 散落各处，口径不一、难维护。

## [S2] Design

见 `ai/play_prompts.py` 与 `PROMPT_BUILDERS` 注册表。原则：规则数值权威；prompt 只约束叙事与 JSON 输出形状。

## [S3] Out of Scope

- 动态 Few-shot 检索；多模型路由。

## Tasks

- [x] T1: play_prompts 全量 builder
- [x] T2: gateway / ai_flavor / forge 接入
- [x] T3: 测试 + 全量
