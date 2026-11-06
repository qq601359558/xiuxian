---
feature: npc-talk-context
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 交谈 AI 上下文（人设/地点/时间/货单）

## Report

**What was built** — `/交谈` 调 AI 时必带：职分+花名册备注、性格、小传、对玩家态度、对方境界/灵石/行囊、所在地点+安全+商会货单摘要、时令、近日见闻、原话。`ensure_bio` 会在旧小传缺职分时重写。无 AI 时掌柜谈丹药会报架上丹药。`USE_CCSWITCH` 走本机代理。

**Verification** — `test_npc_talk_context.py` / `test_npc_talk_words.py` / `test_talk_world_link.py` PASS。

**Journey log**
- 根因：prompt 缺职分/货单/时间，AI 不知柳三娘是丹铺掌柜。
- 旧 bio 已落库不重写 → 增加缺职分自动 refresh。
- 本地兜底误用未定义变量 `w` → 改为 `words`。

## [S1] Problem

与 NPC 交谈时 AI 缺关键基础参数，导致「丹铺掌柜」否认卖丹、把坊市说成客栈。

## [S2] Design

### Prompt 必含字段
道号/境界、职分+ROSTER.note、性格、小传、对玩家态度、对方境界/灵石/行囊、地点+安全+货单、时令、近日见闻、原话。

### 其它
- `ai_available()`（含 CC Switch）才调 AI；失败且未开本地降级则报错。
- bio 缺职分自动重写。

## [S3] Out of Scope
- 多轮对话 UI；NPC 私有库存。

## Tasks
- [x] T1: talk prompt 补全字段
- [x] T2: ensure_bio 补职分/备注
- [x] T3: 本地掌柜兜底
- [x] T4: 回归测试
- [x] T5: Review（套件通过；无 critical）
