---
feature: npc-personas
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# NPC 人设描述包：按职责注入 AI Prompt

## Report

**What was built** — `core/npc_personas.py`：**具名 NPC 人设 35+**（三宗+商会+野外核心）与 **职分模板 13**（掌门/长老/执事/掌柜/镖头/牙人/伙计/弟子/散修/妖修/魔修等）；`persona_prompt_block` ≤200 字注入；`ensure_persona_bio` 短 bio 时落库。已接入 **交谈 / 议程 tick / 主动搭话 / 合谋** 四处 AI prompt。

**Verification** — `test_npc_personas` 5 passed；全量 **175 passed** 全绿。

**Journey log** — 人设只约束口吻与话题，数值/态度仍规则；无名 NPC 走职分兜底。

## [S1] Problem

NPC 调 AI 时只有「性格四字 + 花名册一行 note」，人设单薄：掌柜不会像掌柜说话，魔宗宗主与正道掌门口吻接近。

## [S2] Design

### 2.1 `core/npc_personas.py`

1. **具名 NPC 全文人设**（与 `npc_roster` 同名键）：身份、口吻、价值观、禁忌、口头禅、可谈话题。
2. **职分模板兜底**：`掌门/长老/执事/掌柜/镖头/牙人/伙计/散修/妖修/魔修…` 按 rank/note 推断。
3. **API**：
   - `get_persona(npc) -> dict`
   - `persona_prompt_block(npc) -> str`（≤180 字，供拼进 system/user prompt）
   - `speech_hints(npc) -> str`（一句口吻约束）

### 2.2 接入点

| 调用处 | 注入 |
|---|---|
| `npc_mind` 交谈 | 「你是…」段增加 persona 块 |
| `npc_agenda` tick | 行动描述 prompt 增加口吻 |
| `npc_proactive` 开场 | 同上 |
| `collusion` 合谋 | 双方 persona 各一行 |

数值/态度仍由规则，persona 只约束「怎么说」。

### 2.3 持久化

首次 `ensure_persona_bio(npc)`：把「身份+口吻+禁忌」写入 `CharacterBioRepository`（覆盖过短 bio），交谈 facts 已读 bio，形成双保险。

## [S3] Out of Scope

- 动态人格演化；玩家自定义 NPC；每 NPC 独立 LLM 会话。

## Tasks

- [x] T1: personas 数据 + API — acceptance: 具名与模板可取出
- [x] T2: 接入 mind/agenda/proactive/collusion — acceptance: prompt 含 persona 关键词
- [x] T3: ensure_persona_bio — acceptance: 库中有 bio
- [x] T4: 测试 + 全量 + Review + Finalize
