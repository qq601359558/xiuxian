---
feature: world-arc
status: delivered
updated: 2026-09-18
branch: feat/world-director
commits: landed on main via feat/world-director
---

# M2 世界弧 WorldArc

## Report

**What was built** — 预兆→升级→决算状态机；导师指令升格起弧；tick/强制推进；决算写传说与大事记；世界修饰与导师合并；NPC 偏置；`/世界弧`、`/世界弧应劫`。**补全至模块完全体**：阶段叙事可走 AI（`world_arc_stage`，失败回退模板）；玩家应劫/避祸参与写入决算措辞；宗门危机决算写「对峙」因果边与态度；导演简报含活跃弧与近传说；同质指令去重。

**Verification** — `test_world_arc` + `test_world_director` **23 passed**；全量 **263 passed**。

**Journey log**
- 阶段时长运行时读 config。
- 花名册 NPC 优先占宗门对峙链接前排，验收看 link_type 而非单测号。
- 弧是跨时间故事：起→升→决算→史笔，不是再发一条频道。

## [S1] Problem

M1 天道导演能提案并落账，但指令多为「单发态势」：血煞潮/宗门紧张/秘境潮不会自己长成有开头、有升级、有决算的世界故事。与「AI 主导走向 / 网游小说世界事件弧」仍差一层：**跨时间的弧线**。

创作者要求「做 M2」。权限仍为 **AI/导师提案 + 规则宪章**。

## [S2] Design

### 2.1 弧状态机

```
prophesy 预兆 → escalate 升级 → climax 决算(写传说)
```

- 存储：`world_state["world_arcs"]`
- 类型：`blood_feud | realm_storm | sect_crisis | calamity_arc | omen_arc`
- 阶段窗：`WORLD_ARC_PROPHESY_SEC` / `WORLD_ARC_ESCALATE_SEC`（可 env 调短）
- 同 `kind+location` 活跃弧去重；`WORLD_ARC_MAX_ACTIVE` 上限
- 到期由 `tick_world` 自动推进；`/世界弧 推进 <id>` 可强制
- 超时强制决算，防弧永远挂着

### 2.2 与导师关系

- `DIRECTIVE_TO_ARC`：导师指令类型映射弧类型
- `WorldDirector.run_cycle` 成功后 `absorb_director_cycle` 起弧
- 弧修饰与指令修饰在 `world_modifiers()` **合并**（地点热度/血煞/宗门/大劫/除凶热度）

### 2.3 阶段落账（规则）

| 阶段 | 行为 |
|---|---|
| 预兆 | 频道 major；大事记；给一名玩家可拒机缘；弧修饰生效 |
| 升级 | 频道 major；`realm_storm` 调用 `director_force_open`；热度/偏置加强 |
| 决算 | 频道 major/epic；写 `legends`（tags=`world_arc`）；移出 active |

NPC：`agenda_bias_from_arcs`（血煞地巡守/寻仇、宗门危机巡守、大劫避劫、秘境风暴夺宝）。结算仍走 JianghuSimulator。

### 2.4 玩家可见

- `/世界弧` `/arc` `/弧` [推进 id]
- `/世情` 显示活跃弧
- `/天道` 因 world_modifiers 合并而反映弧热度

### 2.5 Out of Scope

- M3 宗门战数值结算、M4 市场/危险度全量回写、M5 传说改写导演权重
- AI 直接改胜负/掉落
- 玩家自定义弧编辑器

## Tasks

- [x] T1: Spec — acceptance: designed 契约完整 (covers: S2)
- [x] T2: `core/world_arc.py` + config 常量 — acceptance: spawn/advance/climax/tick/modifiers 可测 (covers: S2.1–S2.3)
- [x] T3: 导师吸收 + world_modifiers 合并 + NPC 偏置 + 指令/世情 — acceptance: 起弧后热度与偏置可观察；`/世界弧` 可用 (covers: S2.2–S2.4)
- [x] T4: `tests/test_world_arc.py` + 回归 — acceptance: 新测绿；全量不回归 (covers: S2)
