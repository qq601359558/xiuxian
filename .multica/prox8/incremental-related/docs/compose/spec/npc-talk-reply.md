---
feature: npc-talk-reply
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 交谈回应修复

## Report

**What was built** — 交谈**优先走 LLM**：`.env` 有 Key 时必调 AI；Key 有效则台词由模型生成。Key 存在但鉴权/网络失败时**不再静默用本地模板冒充**，直接报「造化未应」并提示查 Key；仅当 `ALLOW_LOCAL_AI=1` 时才允许本地兜底。本地模板仅作无 Key 开发降级，并按原话关键词分支。

**Verification** — `test_talk_command_e2e.py` / `test_npc_talk_words.py` / `test_npc_mind.py` PASS。查无此人会给同场提示；闭关锁门文案明确「不可交谈」。

**Journey log**
- 根因1：本地 `_local_line` 忽略 words；根因2：网页只发道号。
- 根因3：无 AI 直接 error。
- 客套词分支曾盖过敌对态度 → 敌对优先。

## [S1] Problem

点「交谈」或 `/交谈 <道号> 话` 后，回应几乎总是同一句开场白。

## [S2] Design

- `/交谈 <道号> [话]`：有话必须进 prompt / 本地模板。
- 本地兜底：态度优先；按关键词分支；未命中回显原话。
- 无 AI → 本地，不硬拒。
- 网页：交谈按钮弹出输入框。

## [S3] Out of Scope
- 多轮对话 UI；语音。

## Tasks
- [x] T1: `_local_line` 使用 words 关键词分支
- [x] T2: 网页交谈弹层带话
- [x] T3: 回归测试
- [x] T4: Review（套件通过；无 critical）
