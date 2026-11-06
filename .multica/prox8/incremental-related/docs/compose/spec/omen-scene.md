---
feature: omen-scene
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 奇遇弹窗 v1：多轮过程 · 强制散场 · 状态同步

## Report

**What was built** — `core/omen_scene.py` 六幕模板 + **AI 现编剧本**（`omen_script_prompt` → `ingest_ai_script` 钳制入 `SCRIPTS`）；群聊 speakers、`@名字`；`/奇遇` `/奇遇说`；强制散场；每响应 `status` 命盘；网页 `omenModal`。

**Verification** — `test_omen_scene` 7 passed；全量 **205 passed** 全绿。

**Journey log** — 跳向 success 时须先落 edge effects 再结幕。

## [S1] Problem

旧奇遇两步点选立刻结束；要「演戏式」多轮、可强制散场、独立弹窗，且灵石/修为等与命盘同步。

## [S2] Design

### 2.1 会话 `core/omen_scene.py`

- 每玩家一场 `OmenScene`：`id/title/participants/messages/node_id/turns/max_turns/goal/status/choices`
- **节点图**（规则）：`nodes[node] = {prompt, choices[], edges[], success?, fail?}`
- 选项 `choice_id` → 直接走 `to` 节点并 `effects` 落账（钳制同旧链）
- 自由句 `/奇遇说`：规则关键词 → `intent` → 匹配 `edges`；无效则 NPC 拒 + `invalid++`
- `invalid≥3` 或 `turns≥max` → **强制散场** `status=forced`，按 `fail_effects` 或空
- 成功节点 → `status=success`，写频道/落账

### 2.2 v1 剧本（≥4 幕，单 NPC 或旁白）

黑市兜售 / 旧友托孤 / 灵泉争饮 / 残碑悟道 —— 每幕 3～5 节点。

### 2.3 指令与同步

| 指令 | 语义 |
|---|---|
| `/奇遇` | 打开/续看当前幕；无幕则按旧逻辑可能新开 |
| `/奇遇说 <话>` | 窗内发言（网页不显示命令感） |
| `/奇遇 <1\|2\|3>` | 快捷选项 |
| `/奇遇 弃` | 主动散场 |

**每条响应带 `status` 命盘**（world `_status_dict`），网页 `applyStatus` 刷新灵石/修为/寿元。

### 2.4 网页

`omenModal`：场景、历史、芯片选项、输入框；`omen_open` 时自动打开；结束显示散场原因后关窗。

## [S3] Out of Scope

- 群聊 @、多 NPC 意愿（第二刀）；AI 自由编节点。

## Tasks

- [x] T1 omen_scene 引擎 + 剧本
- [x] T2 指令 + status 回传
- [x] T3 网页弹窗
- [x] T4 测试 + 全量
