---
feature: npc-chat-session
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# NPC 会话式聊天：窗口 · 连续对话 · 意愿挂断

## Report

**What was built** — `core/npc_chat.py` 会话态：`/交谈 <名>` 开窗，`/说` 连续聊，`/挂断` 结束；NPC 按态度给 **续聊意愿**，不愿则作别；**挂断后 `/说` 不再调 AI**。网页弹出聊天窗（`chatModal`）。无 AI 时本地性格句 + 越聊越不耐烦。

**Verification** — `test_npc_chat` 4 passed；全量 **190 passed** 全绿。

## [S1] Problem

原 `/交谈` 一问一答，无会话感，也无法「NPC 拒绝后再发消息」。

## [S2] Design

见 `core/npc_chat.py`；AI 输出 `line / will_continue / attitude_delta / hangup_reason`。

## Tasks

- [x] T1 会话引擎
- [x] T2 指令 /交谈 /说 /挂断
- [x] T3 网页聊天窗
- [x] T4 测试
