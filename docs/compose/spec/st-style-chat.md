---
feature: st-style-chat
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: (landed via feat/world-director)
---

# ST 式交谈：角色卡 · Lorebook · 会话摘要

## Report

**What was built** — 角色卡 few-shot（`character_card_block` + examples）；玩家简卡；`core/lorebook.py` 关键词注入世界态/史笔/秘境/宗门；会话关闭写入摘要记忆，下次开口注入；`npc_talk_prompt` 全槽位。**续作**：`core/scene_banter.py` 同场旁听插话（性格加权、冷却、AI 可选一句）；`summarize_session_ai` 长会话 AI 摘要（失败回退规则摘要）；`/说`/`/挂断` 返回插话与记忆。规则权威不变。

**Verification** — `test_st_chat` + `test_scene_banter` + npc_chat/personas/talk_context **15+ passed**；全量见交付。

## [S1] Problem

NPC 交谈已有 persona/态度/近账，但口吻不稳、不谈世界大事、下次见面不记得上次聊过什么。参考 SillyTavern 的角色卡 / WorldInfo / 记忆思路，**只借结构，不开放无规则叙事**。

## [S2] Design

### 角色卡
- `npc_personas`：职分/具名补充 `examples` 示例台词
- `character_card_block(npc)`：人设 + 示例 few-shot
- `player_persona_block(player)`：宗籍/凶名/名气简卡

### Lorebook（`core/lorebook.py`）
- 关键词命中：宗门/秘境/地点 + 世界态（导演/弧/势力/望气/史笔/传闻）
- `lore_prompt_block` 注入「坊间与天机」；禁止当铁证

### 会话摘要
- 关闭会话时规则摘要写入 `world_state["npc_chat_memory"]`
- 下次 `/说` 注入「上次交谈记忆」；`/会话` 面板可显示

### 权限
AI 只台词与态度倾向；数值/交易仍走既有规则。

## Tasks
- [x] T1: lorebook + card API
- [x] T2: npc_chat 记忆 + prompt 注入
- [x] T3: 测试
