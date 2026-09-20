---
feature: pagegame-ui
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 页游化游戏界面（场景+行动盘）

## Report

**What was built** — 在可点原型 `web/prototype.html` 上补齐动效系统：灵尘漂浮、场景光晕呼吸、入世 stagger 入场、迁跃闪与地名滑入、行动盘悬停/涟漪、叙事淡入与金线扫过、数值 bump/条脉冲、闭关头像呼吸、转世弹层上浮；`prefers-reduced-motion` 全量降级。布局仍为现代仙侠三栏（命盘 / 场景+行动盘+天道录 / 目标同场）。

**Verification** — 内联 JS `node --check` PASS；动效 token（reduced-motion / mote-drift / scene-flash / msg-in / act-busy / stat-bump / portrait-med）齐全；独立 Review Spec/Correctness/Consistency 均 PASS，0 critical。评审非阻塞项已修：`render()` 后重打 `act.busy`、AI 金线改为 `::before` 扫过（去掉静态左边框）、reduce 下关掉 scene-name 等 transition。

**Journey log**
- 无 git → in-place 交付。
- 布局：现代仙侠 + 场景行动盘（非经典金红密框）。
- 动效第二轮增补；`render()` 全量重绘会吞瞬时 class，需 render 后重挂 busy。
- 下阶段：迁入 `index.html`/`app.js` 接 `/action`。

## [S1] Problem

当前 `web/` 客户端仍是「顶栏统计 + 侧栏按钮 + 中央文字流」的终端式布局，玩家反馈「还是文字式修仙」。需要参考页游/手游 MMO 的面板结构：角色卡、场景主视觉、大按钮行动盘、任务/同场侧栏，叙事不再是唯一主角。

用户二次反馈：布局可以了，但**太简洁、没有动效**——需要过场、环境粒子、按钮反馈、叙事入场。

约束：本仓库无 git，无法建 worktree；在项目内直接交付，路径覆盖记为 in-place。

## [S2] Design

### 视觉基调（已拍板）
- 保留「夜空墨青 × 金印 × 灵玉」现代仙侠气质，**不做**经典金红描边密框页游。
- 提高面板感：圆角卡片、层次分区、进度条、头像位；减少裸文字列表。

### 动效系统（本轮增补）
| 区域 | 行为 |
|---|---|
| 环境 | 灵尘粒子漂浮；场景安全/凶域光晕呼吸 |
| 入世 | 入世卡片与主壳 stagger 入场 |
| 迁跃 | 场景卡短闪 + 地名滑入；危险区切换色相 |
| 行动盘 | 按下缩放、悬停抬升、执行时按钮光晕 |
| 叙事流 | 消息自下淡入上滑；AI 长文左侧金线扫过 |
| 数值 | 进度条宽度过渡；关键数值变化时轻微高亮 |
| 闭关 | 头像缓慢呼吸；行动盘禁用态降饱和 |
| 转世 | 死亡弹层上浮；转世后命盘重置动画 |

约束：全部动画包在 `@media (prefers-reduced-motion: no-preference)` 或带 reduce 分支；单次动画 ≤400ms 为主，环境循环可长。

### 布局骨架（已拍板：场景 + 行动盘）
```
┌──────────────────────────────────────────────────────┐
│ 顶栏 HUD：品牌 · 境界/寿元/修为/灵石/灵气 · 暂离      │
├──────────┬───────────────────────────┬───────────────┤
│ 左：角色卡│  中：场景主视觉             │ 右：目标      │
│ 头像/境界 │  地点名·危险·灵气           │ 同场修士      │
│ 属性条    │  迁跃（实现放左栏列表）     │ 宗门/榜摘要   │
│ 状态 pill │───────────────────────────│               │
│          │  行动盘（网格大按钮）       │               │
│          │  闭关/出关/突破/机缘…       │               │
│          ├───────────────────────────┤               │
│          │  叙事流（可折叠，默认开）    │               │
└──────────┴───────────────────────────┴───────────────┘
```

实现偏差（已接受）：迁跃在左栏垂直列表而非场景下芯片条；行动盘 4 列网格（响应式 4→3→2）。

### 交付阶段
1. **本阶段：可点原型 + 动效** `web/prototype.html`（自包含 mock，不依赖服）。
2. 下阶段：把布局迁入 `index.html` + `app.js`，接 `/action` 真数据。
3. 再下阶段：可选 `/snapshot` 聚合接口（非本 Spec 阻塞项）。

### 原型交互契约
- 点行动盘按钮 → 叙事区追加 mock 结果，并切换/刷新场景与状态摘要；有动效反馈。
- 点迁跃 → 场景名/危险度变化 + 过场闪烁。
- 点同场卡「斗法/交谈」→ 叙事追加；闭关中均拒绝。
- 死亡演示按钮可开转世弹层。
- 不调用网络；`data-mock="1"` 标明原型。

## [S3] Out of Scope
- 真实 API 对接、轮询、鉴权（下阶段）。
- 后端 `/snapshot` 新接口。
- 移动端触控重做（仅保证 ≥375px 不横向溢出）。
- 美术资源位图立绘（用 CSS/SVG 占位）。
- WebGL/粒子引擎、音效。

## Tasks
- [x] T1: 产出 `docs/compose/spec/pagegame-ui.md` 本文件 — acceptance: 含 Problem/Design/Out of Scope/Tasks（covers: S1 S2）
- [x] T2: 实现 `web/prototype.html` 自包含可点原型 — acceptance: 浏览器打开可完成入世→看场景→点行动→看叙事闭环；无外部依赖（covers: S2; depends: T1）
- [x] T3: 原型交互自检清单 — acceptance: 迁跃/闭关/突破/机缘/目标切换均有可见反馈（covers: S2; depends: T2）
- [x] T4: 独立 Review（第一轮） — acceptance: 对照 S2/S3 无 critical（covers: S1 S2; depends: T2 T3）
- [x] T5: 动效系统落地 — acceptance: 入世/迁跃/行动/叙事/数值均有可见动效；reduced-motion 降级（covers: S2 动效系统; depends: T2）
- [x] T6: 动效 Review — acceptance: 无 critical（covers: S2; depends: T5）

