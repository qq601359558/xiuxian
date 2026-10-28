---
feature: natural-omen
status: completed
updated: 2026-10-15
branch: feat/character-integrity-and-audit-rules
---

# 奇遇自然化与首张藏宝图 100% 必出奇遇 (Natural Omen & First Dig Guarantee)

## 1. 需求与核心目标 (Problem & Goals)
- **痛点**：旧版奇遇需要玩家反复主动输入 `/奇遇` 或点击「推演天机」进行强刷，缺乏修仙世界“机缘天定、偶然而至”的代入感；且新玩家入世初期缺乏引导与惊喜。
- **目标**：
  1. **首张藏宝图 100% 奇遇**：新修士入世自带 1 张藏宝图，首次 `/挖宝` 100% 必定触发奇遇，建立新手心流。
  2. **日常行为自然偶发**：在日常交谈、言行、迁跃、探险、出关及后续挖宝中，按概率（生产 1%，测试 30%）自然降临机缘。
  3. **去强刷化**：当无奇遇进行中时，禁止玩家通过 `/奇遇` 或 `/机缘` 强制刷出新奇遇，提示「【天机渺茫】机缘天定，不可强求……」。
  4. **主界面内联芯片与散场保护**：告别突兀的大弹窗，采用天道录内联日志 + 底部应对芯片；玩家迁跃或闭关时自动以擦肩而过散场。
  5. **NPC 交谈就地触发**：与 NPC 交谈中偶发奇遇时，直接在聊天窗口内原地推进，不打断交谈。

## 2. 详细设计 (Design & Contracts)
- **配置层 (`config.py`)**：新增 `OMEN_CHANCE_PROD` (0.01), `OMEN_CHANCE_TEST` (0.30), `OMEN_COOLDOWN_SECONDS` (600.0), `omen_chance()`。
- **模型层 (`core/models.py`)**：`Character` 增加 `first_dig_omen_done: bool = False`, `last_omen_at: float = 0.0`。
- **入世初始 (`core/clock.py`)**：初始修士 `inventory` 自带 1 张 `藏宝图`。
- **触发器与 AI 匹配 (`core/omen_scene.py`)**：
  - `maybe_trigger_natural_omen(c, context, force=False, in_chat_npc=None)`
  - `current_choices(player_id)`
  - `dismiss_on_leave(c, action_label)`
  - `_ai_match_edge(c, scene, node, player_text)`
- **挖宝系统 (`core/loot_equip.py` & `core/treasure_system.py`)**：
  - 支持首图必得机缘与 100% 奇遇绑定。
  - 维持 Core-V2 空间拓扑与寻龙八卦校验的完整兼容性。
- **服务分发 (`server/world.py`)**：
  - `_append_natural_omen` 辅助方法挂载至 `/探险`、`/说`、`/做`、`_go`、`_emerge`。
  - `/奇遇` 与 `/机缘` 去强刷化。
  - `_go` 与 `_meditate` 迁跃或闭关前调用 `dismiss_on_leave` 优雅散场。
- **前端交互 (`web/app.js` & `web/index.html`)**：
  - 移除独立 `omenModal`，由 `renderInlineOmenBar` 渲染主界面内联芯片。
  - 输入框在奇遇激活态下自动路由为 `/奇遇说 <内容>`。

## 3. 验收任务 (Acceptance Tasks)
- [x] T1: 初始人物带藏宝图，`first_dig_omen_done` 默认为 False。
- [x] T2: 首次挖宝 100% 触发奇遇并置 `first_dig_omen_done = True`。
- [x] T3: 日常动作按 `omen_chance()` 概率自然偶发。
- [x] T4: NPC 对话中触发奇遇就地在聊天窗结算，不弹出遮罩。
- [x] T5: 迁跃或闭关时自动调用 `dismiss_on_leave` 散场。
- [x] T6: `/奇遇` 与 `/机缘` 空会话时返回「天机渺茫」不可强求。
- [x] T7: 通过 `test_natural_omen.py`、`test_omen_scene.py`、`test_loot_equip_apoc.py` 全量测试。
