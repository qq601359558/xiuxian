---
feature: faction-director
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: (landed via feat/world-director)
---

# M3 势力操盘 FactionDirector

## Report

**What was built** — `core/faction.py`：宗门关系分状态机（初始格局+tick衰减+STATUS）；宗门令 open/accept/complete（patrol/hunt/boycott/siege 规则验收→贡献）；宗门围剿（NPC 自动接除凶+epic 广播+敌对再降）；敌对战力×1.10、敌坛热度×1.25；导师 `faction_order`/`sect_siege` 与 `sect_tension` 同步；弧宗门危机决算联动；`/势力` `/宗门令` `/接宗门令` `/交宗门令`；`/宗门势`/世情/天道展示。

**Verification** — `tests/test_faction.py` + director + arc **31 passed**；全量见交付记录。

**Journey log**
- 势力是 M1/M2 态势的「真落账层」，不是再加一块文案。
- AI/导师只提案；关系分、令奖励、围剿名单全规则。
- 完整「宗门攻城」仍 out of scope，以围剿+令+关系代表 LAN 文字版势力战争。

## [S1] Problem

M1/M2 之后，宗门「紧张」多半仍是文案与 NPC 偏置，没有：
- 可持久的**宗门关系分**（敌对/结盟）
- **宗门令**（任务）开/接/验/贡献
- **宗门围剿**（号令 + NPC 自动接除凶）
- 敌对区/敌对宗门对**战力与热度**的规则修正
- 导师/世界弧对势力的**真落账**

创作者要求 M3 按模块 100% 做完，禁止偷懒。权限仍为 **AI/导师提案 + 规则宪章**。

## [S2] Design

### 2.1 数据 `world_state["faction_state"]`

- `relations`：`a|b` → `{score, status, note, updated_at}`；score∈[-100,100]
- `status`：hostile / tense / neutral / warm / allied（规则映射）
- `missions`：宗门令（patrol|hunt|boycott|siege），open/done/expired
- `sieges`：宗门围剿
- `log` / `stats`

初始格局：青云×九幽敌对、万剑×九幽紧张、商会偏正道等。tick 向中立衰减。

### 2.2 关系驱动的规则效果

| 效果 | 规则 |
|---|---|
| 敌对交手 | 进攻方战力 ×1.10（tense ×1.05） |
| 敌对总坛/洞府 | 外人 `location_faction_heat` ×1.25 |
| NPC 议程 | 围剿目标→revenge；敌境→patrol/social；同场敌门→revenge/patrol |
| 斩杀跨宗 | 关系 -6 |
| 导师 sect_tension | 关系 -12，可能自动开抵制令 |
| 弧 sect_crisis 决算 | 应劫 +8 / 否则 -8；敌对加深时可触发宗门围剿 |

### 2.3 导师指令

- `faction_order`：effects.sect + order_kind + target_sect/target_name → 开令
- `sect_siege`：effects.sect + target_name → 校验血煞后 `open_siege`
- admit 白名单保留上述键；数值键仍剥离

### 2.4 围剿

`open_siege`：写 siege + 门下 NPC 自动 `/接除凶` 目标（上限 FACTION_SIEGE_NPC_MAX）+ 同步宗门令 + 频道 epic + 若目标属敌对宗门则关系再降。

### 2.5 宗门令验收（规则可观测）

- patrol：在指定地点/总坛
- hunt：已接该目标除凶或目标已死
- boycott：不在敌坛
- siege：接对应除凶或目标已死  
奖励入 `sect_contribution`。

### 2.6 玩家可见

`/势力` `/宗门令` `/接宗门令` `/交宗门令`；`/宗门势` 附势力摘要；`/世情` `/天道` 显示围剿与敌对。

### 2.7 Out of Scope

- M4 全量市场价/危险度 UI 回写  
- M5 传说改写导演权重  
- 真·宗门战数值攻城/驻地占领（LAN 文字版以围剿+令+关系为代表）  
- AI 直接改关系分/胜利  

## Tasks

- [x] T1: Spec (covers: S2)
- [x] T2: `core/faction.py` 关系/令/围剿/tick — acceptance: 状态机与规则效果可测 (covers: S2.1–S2.5)
- [x] T3: 导师/弧/战力/热度/NPC/指令接线 — acceptance: tension→关系；siege 指令；敌对加成 (covers: S2.2–S2.4)
- [x] T4: 服务器指令 + 面板 + 测试回归 — acceptance: `/势力` 等可用；pytest 全绿 (covers: S2.6)
