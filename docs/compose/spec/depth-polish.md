---
feature: depth-polish
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 加深：师徒结拜 → 宗门日环 → 除凶 → 世情可点

## Report

**What was built** — 师徒/结拜加深：拜师收徒 major 仪式、师门任务与交任务、叛师（怨+同门态度）、出师 credit（走通秘境）、结义任务；宗门日环改为主题 3 选 1 + 连环 streak（断日重置）+ 稀有兑换解锁；除凶限时 48h、NPC 逃亡、反悬赏、围剿须接令后宣告、`/look` 天道示警；世情编号 + `/追`（B 接令 / S 秘境引导 / NPC 同场交谈）。

**Verification** — `test_depth_polish`+`test_wave2` 12 passed；全量 **161 passed**（`test_events_ai` PRE-EXISTING 偶发）。评审 critical（credit 未进 graduate、bond_daily 键冲突）与 major（streak 重置、围剿须接令、结义防守接线、反悬赏清理）已修。

**Journey log** — 日环/任务必须按 kind 分键；streak 存 {n, day} 才能断日；pending 与 credit 都要进主路径校验。

## [S1] Problem

Wave2 四系统是「最短闭环」，完善度约四成：仪式感弱、日环像打卡、除凶无猎物博弈、世情只能看不能点。

## [S2] Design

### 2.1 加深 · 师徒结拜

| 项 | 行为 |
|---|---|
| **拜师/收徒仪式** | 礼成时世界频道 major；双方 feed 长叙事（频道已有 post） |
| **师门任务** | 弟子 `/师门任务`：每日 1 条（采药/巡山/寻仇线索）；完成 `/交师门` → 师父功德 +5、弟子贡献类功德 +3、link.strength+1 |
| **出师考核** | 保持 strength≥3 或境界差；另：走通任意秘境链一次可记 `graduate_credit`，立即满足出师 |
| **叛师** | `/叛师 <名>`：断师徒→「怨」；业力+15；同宗 NPC 对其态度 -20；频道 major |
| **结义共患难** | 结拜双方同场且任一方 blood_marked 时被攻击，另一方 power 额外 +5%（叠加围剿） |
| **结义任务** | `/结义任务`：同场完成 1 次探险或斗法胜利 → 双方功德 +8，link.strength+1 |

存：`world_state["bond_daily"]` 按日；`graduate_credit` 记在 link.note 或 world_state。

### 2.2 加深 · 宗门日环

| 项 | 行为 |
|---|---|
| **主题 3 选 1** | 每日刷新时从主题池抽 3 条主题（如「剑冢清剿」「药圃采收」「坊市护法」），玩家 `/接宗门环 <1\|2\|3>` 接一条主环；完成条件写在条目上（explore/donate/visit 仍为钩子） |
| **叙事一句** | 接环时输出执事委托一句（规则模板，可选 AI） |
| **连环奖励** | 连续完成日数 `streak`：3/7 日额外贡献 15/40，写频道 info |
| **稀有兑换** | streak≥3 解锁：`玄元聚气丹` 80 贡献、`赤霄剑` 200；`/兑换` 显示锁定状态 |

主题池（规则）：`explore`×2 不同文案、`donate`、`visit`、`hunt`（接一次除凶令）混抽。

### 2.3 加深 · 除凶

| 项 | 行为 |
|---|---|
| **限时令** | 接令起 **48 现实小时**；过期自动失败，功德不发；`/除凶` 显示剩余 |
| **目标逃亡** | 目标若为 NPC 且被接令：tick 时 25% 概率 `/go` 随机相邻安全/野外；写传闻 |
| **反悬赏** | 目标（玩家）知悉被除凶（`/除凶` 可见）可 `/反悬赏`：花 50 灵石挂「反杀猎人」；猎人被杀则目标得功德 20 |
| **察觉** | 接令后目标下次 `/look` 或上线 feed 提示「有人对你动了杀心」（info） |
| **围剿宣言** | `/围剿 <目标>` 同场且也接令者可宣告；全服 major 一句，系数仍 1.15 |

### 2.4 加深 · 世情可点

`/世情` 输出带 **编号**：

```
【世情】
NPC：
1. 柳三娘 · 结交 · 青云坊市客栈
…
血煞：
B1. 血煞客 · … @ …
近闻：…
```

| 指令 | 语义 |
|---|---|
| `/追 <编号>` | 对 NPC：同场则 `/交谈` 引导文案；异地提示 `/go`；对血煞：若未接令则自动 `/接除凶` |
| `/世情 简` | 仅近闻 3 条 |

实现：`format_world_schedule` 返回 text + `actions` 列表（type/name/loc）；world 模块缓存最近一次 actions 到 `world_state["last_schedule"][user_id]` 供 `/追`。

## [S3] Out of Scope

- 宗门战、灵田、师门 AI 长篇任务链、除凶跨图寻路 AI。

## Tasks

- [x] T1: 社交加深（仪式 major/师门任务/叛师/出师 credit/结义任务） — acceptance: 可测路径全绿
- [x] T2: 日环主题 3 选 1 + streak + 稀有兑换 — acceptance: 接环/完成/解锁
- [x] T3: 除凶限时/逃亡/反悬赏/围剿宣言 — acceptance: 过期失败；反悬赏可挂
- [x] T4: 世情编号 + `/追` — acceptance: 血煞可追成接令
- [x] T5: 测试 + 全量 + Review + Finalize
