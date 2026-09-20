---
feature: chat-actions
status: delivered
updated: 2026-09-27
branch: (no-git-in-place)
commits: n/a
---

# 会话内动作交互 + 挂断只读

## Report

**What was built** — 会话窗自由文本可发起赠礼/攻击/偷窃/擒拿/交易，AI+本地关键词分类，规则引擎落账（物品、灵石、态度、业力、CAPTURED 状态）。新增 `/释放`。NPC 挂断后前端不再自动关窗，输入禁用，玩家手动 × 关闭。

**Verification** — `.venv\Scripts\python.exe -m pytest tests/` → **216 passed**（含新增 `test_chat_actions.py` 10 项）。`test_events_ai` 曾有一次随机失败，复跑通过，判定 PRE-EXISTING flaky。

**Journey log**
- 评审指出交易 `min(ask,bid)` 可 1 灵石买任意货 → 改为压价拒绝
- `do_kidnap` 收 `{}` 导致意愿条件死代码 → `execute_chat_action` 透传 live session
- 行窃/擒拿失败转攻击若再被安全区拒绝，原先会话仍开 → 强制 ended
- 仓库无 Git，未开 worktree，原地交付

## [S1] Problem

当前 NPC 会话窗只能纯对话（`/说`）。玩家希望在交谈中直接用自然语言发起动作（赠礼、攻击、偷窃、绑人、交易），由 AI/规则给出响应并真正落账；另外 NPC 不愿再聊时前端会自动关窗，玩家来不及看清最后回应与结束原因。

用户已确认：
1. 输入方式：自由文本 + AI 判意图
2. 落账范围：全量硬核（物品/战斗/状态/态度均改）
3. 挂断后：只读历史，只能关窗

## [S2] Design

### S2.1 意图分类

会话中玩家输入仍走 `/说 <文本>`。后端在现有发言链路前增加意图分类：

| intent | 触发示例 | 本地关键词兜底 |
|---|---|---|
| `dialogue` | 寒暄、提问 | 默认 |
| `gift` | 「递上聚气丹」「送你灵石」 | 递上/送给/赠/孝敬/奉上 |
| `attack` | 「一掌拍过去」「动手杀你」 | 拍/打/杀/动手/偷袭/伏击/斩 |
| `steal` | 「顺走他的储物袋」 | 偷/摸/顺走/窃取 |
| `kidnap` | 「一把擒住」「绑起来带走」 | 擒/绑/掳/挟持/拿下 |
| `trade` | 「用一百灵石买你的丹」 | 买/卖/换/交易/出价 |

- AI 可用时：短 prompt 分类，输出 JSON `{"intent":"...","target_item":"...","stones":N}`
- 无 AI / 超时：本地关键词，长词优先
- 分类失败或不在白名单 → `dialogue`

### S2.2 动作契约

所有动作共用前提：会话 open、双方同场、目标存活、玩家非闭关。动作结果写入会话消息流，由 AI/本地模板生成对方台词；数值由规则引擎落账。

#### gift 赠礼
- 从玩家 `inventory` 扣除 1 件命名物品（文本模糊匹配唯一命中；歧义或无货则拒绝）
- NPC 不设独立背包展示；态度 `shift_attitude(+3~+8)`，意愿 +5
- 可选：文本含「灵石 N」则额外转 N 块随身灵石（N≤玩家持有，N>0）
- 不结束会话

#### attack 攻击
- 调用 `CombatFateEngine.resolve_ambush(player, npc, context=text)`
- 安全区/新手庇护等失败原因原样返回，会话保持 open（玩家可撤回重说）
- 成功发起（返回 success）后关闭会话（`ended_by=system`），原因「话不投机，当场动手」
- 报告全文进聊天流

#### steal 偷窃
- 成功率：`0.35 + 0.08*(attacker.tier - defender.tier)`，钳制在 `[0.1, 0.85]`；玩家 `stealth_active` 时 +0.15
- 成功：夺走 NPC 随身灵石的 20%~40%（至少 1，NPC 为 0 则失败），态度 -15，会话保持 open（对方可能装作不知或点破）
- 失败：态度 -25，意愿 -30；50% 概率对方当场翻脸 → 转 attack 同链路并结束会话；否则以「发觉你在摸他」结束会话
- 禁止：安全区内不可偷（与交易同区逻辑）

#### kidnap 绑人
- 新增状态 `CharacterStatus.CAPTURED`（中文「被擒」）
- 前置：非安全区；玩家境界 tier ≥ 对方 tier + 1，或对方 `willingness` 已 < 20（聊崩）
- 成功率：`0.25 + 0.12*(tier差)`，钳制 `[0.1, 0.75]`
- 成功：
  - NPC `status=CAPTURED`，`captor_id=player.id`，`location` 不变
  - 玩家业力 +40
  - 关闭会话，原因「你将其擒住」
- 失败：态度 -40，转 attack 一次（若 attack 也失败则仅关闭会话）
- 被擒者：不可 `/前往`、不可被 `/交谈` 开新会话（提示已被擒）
- 新增 `/释放 [道号]`：同场且 `captor_id=自己` 时恢复 `IDLE`，清空 captor；态度 +5

#### trade 与 NPC 以物易物
- 解析：`target_item`（想得到的）+ `stones`（出价）或 `give_item`（以物换）
- 校验：NPC 名下要有可交易物？——简化：NPC 不持有独立货架；交易落为「玩家出灵石/物品，换取态度与一句成交/拒绝台词 + 若 target_item 在商会 CATALOG 则扣玩家灵石并入包」
- **更简且可验收的契约**：会话内 trade = 玩家向 NPC 出价购买其「身份可售物」不落地；改为 **玩家支付灵石或物品，换取态度提升与 AI 成交旁白**；若文本明确「买 X」且 `X in ITEM_CATALOG`，则按目录价（可被态度折扣 0.85~1.1）从玩家扣灵石、入玩家 inventory
- NPC 态度 ≥ 冷淡才可能成交；敌对直接拒
- 成交态度 +5；拒绝态度 -2；均不强制关窗

### S2.3 挂断只读（前端）

- `handleChatPayload`：`chat_ended === true` 时 **不再** `setTimeout(closeChat)`
- 进入 `state.chatEnded = true`：输入框禁用、发送钮禁用；系统行展示结束原因
- 关闭钮：若后端会话仍 open 则发 `/挂断`，然后本地关窗；若已 ended 仅本地关窗
- 重新 `/交谈` 成功时重置 `chatEnded`

### S2.4 接口

`/说` 成功响应增加/沿用字段：

```
{
  ok, text, chat_open, chat_ended, npc,
  action: "dialogue"|"gift"|"attack"|"steal"|"kidnap"|"trade",  # 新增
  source: "ai"|"local"
}
```

失败（安全区拒绝等）`ok=false` + `error`，`chat_open=true`（若会话未关）。

### S2.5 模块

| 模块 | 职责 |
|---|---|
| `core/chat_actions.py` | 分类、执行 gift/steal/kidnap/trade；attack 委托 combat_fate |
| `core/models.py` | 增加 `CAPTURED` 与 STATUS_CN |
| `server/world.py` | `/说` 接入分类；新增 `/释放` |
| `web/app.js` | 挂断不自动关窗、chatEnded 禁用输入 |
| `web/style.css` | 若需 ended 态样式（禁用即可） |
| `cli/main.py` | 帮助文案补充 `/释放` |

## [S3] Out of Scope

- 绑架后的押送、赎回、囚牢地点
- NPC 对玩家的主动绑架
- 会话窗内可视化按钮/物品选择器（保持自由文本）
- 多目标同时动作
- 改 `/做` 自由动作引擎（仅会话内）

## Tasks

- [x] T1: `CAPTURED` 状态与模型字段 — acceptance: 模型可序列化 CAPTURED，status_cn 可读 (covers: S2.2)
- [x] T2: `core/chat_actions.py` 分类 + gift/trade/steal/kidnap — acceptance: 单测覆盖各 intent 成功/拒绝/边界 (covers: S2.1 S2.2)
- [x] T3: attack 委托 combat_fate 并结束会话 — acceptance: 安全区拒绝时会话仍 open；动手成功后 session closed (covers: S2.2)
- [x] T4: `server/world.py` `/说` 接入 + `/释放` — acceptance: 会话内动作返回 action 字段；/释放 可放人 (covers: S2.2 S2.4)
- [x] T5: 前端挂断只读 — acceptance: chat_ended 后窗不自动关、输入禁用；手动关闭可用 (covers: S2.3)
- [x] T6: CLI 帮助与回归 — acceptance: 相关 pytest 通过，旧 `/说` 对话不回归 (covers: S2.4)
