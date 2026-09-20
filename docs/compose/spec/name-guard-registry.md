---
feature: name-guard-registry
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 专名门禁与名物入册：玩家不可口述造物

## Report

**What was built** — `core/name_guard.py`：玩家 `/做` `/说` 命中「造物意图」（建城/命名/门派叫/师父叫/炼出未知名…）则**拒绝且不调 AI**；`/自创功法` 不在此拦。`core/name_registry.py`：仅 AI/GM 可 `review_and_register` 入「听闻册」；玩家来源直接拒；`/名物` 查看。GM 公告发帖后自动走名物司（无 AI 时规则抽候选）。

**Verification** — `test_name_guard` 5 passed；全量 **194 passed**（`test_events_ai` PRE-EXISTING 偶发）。

**Journey log** — 玩家说话永不建档；名物只 L1 听闻，不自动 `/go`。

## [S1] Problem

AI/NPC/GM 文案会带出未登记专名；玩家也可能用 `/做` `/说` 妄图口述创建地点/人物/物品。需：**玩家拒建；仅 AI/GM 可提案入册；`/自创功法` 例外保留。**

## [S2] Design

### 2.1 玩家口述门禁 `core/name_guard.py`

扫描玩家自由言行（`/做`）与会话发言（`/说`），命中「造物意图」则**拒绝且不调 AI**：

| 信号 | 示例 |
|---|---|
| 创建/命名 | 我建一座、命名为、取名、开创宗门、我门派叫 |
| 宣称新地点 | 我来到了幽谷（且幽谷不在 WORLD_LOCATIONS） |
| 宣称新人物 | 我师父/我道侣/我弟子叫 X（X 不在花名册） |
| 宣称新物 | 我炼出了/我得到了 YY（YY 不在货单且非已知配方产出） |

**例外**：`/自创功法 <理念>` 不走此门禁（已有 DSL+钳制）。

拒绝文案固定一句，说明「名物只由天道/AI 落册，可用已有地名/描述代替」。

### 2.2 名物入册（AI/GM）`core/name_registry.py`

- 存储 `world_state["name_registry"]`：L1 听闻实体（type/name/source/confidence/desc/parent）
- API：`register_heard(...)` / `list_heard(type=)` / `format_board()`
- `/名物` 查看听闻册
- **物化**不在本阶段：只登记听闻，不自动进 `WORLD_LOCATIONS`/花名册（防膨胀）；后续可加 `/追查`

### 2.3 AI/GM 出口钩子

提供 `review_and_register(text, source, author, …)`：

1. 规则抽候选（汉字专名粗抽 + 已知名过滤）  
2. 有 AI 则按名物司 Prompt（精简版）判定  
3. `should_register` 且 conf≥阈值 → `register_heard`  
4. 玩家来源：**不调用**

挂接：GM 公告、NPC 交谈回复后（可选、预算内）——本阶段 GM + 测试路径；NPC 默认关，配置 `NAME_REGISTRY_ON_NPC=0`。

### 2.4 Prompt

使用已定「天道名物司」精简版；`source` 区分 gm_broadcast / npc_talk / ai_event / ai_flavor。

## [S3] Out of Scope

- 听闻自动物化为可 `/go` 地点；玩家提交建名申请流。

## Tasks

- [x] T1 name_guard + 接入 /做 /说
- [x] T2 name_registry + /名物
- [x] T3 review_and_register + GM 钩子
- [x] T4 测试 + 全量
