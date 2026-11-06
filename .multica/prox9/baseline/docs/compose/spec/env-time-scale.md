---
feature: env-time-scale
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# 环境时间缩放（测试加速 / 生产同步）

## Report

**What was built** — `GAME_ENV=test|production` + `TIME_SCALE`：测试默认 ×120（8 设计小时 ≈ 4 分钟墙钟），生产强制 ×1。闭关起止/进度/结算按设计小时算收益与耗寿。顺带接通局域网 `/购买` `/出售` `/服用`。

**Verification** — `test_env_time_scale.py` PASS；`test_meditation_lifespan.py` PASS。

**Journey log**
- 洞府坐化测试原先用墙钟 1h/2h，加速后失效 → 按 meditation end_time 比例设死亡时刻。

## [S1] Problem

当前闭关时长与现实墙钟 1:1：计划 8 小时就要等 8 现实小时，测试极慢。需要环境配置：**测试环境加速闭关**，**生产环境与现实同步**。

约束：无 git，in-place。

## [S2] Design

### 配置契约
| 键 | 含义 | 默认 |
|---|---|---|
| `GAME_ENV` | `test` \| `production` | `test` |
| `TIME_SCALE` | 倍速：`1`=与现实同步；`N` 表示 N 倍速（8 设计小时墙钟 = 8/N 小时） | test=`120`；**production 强制 1** |

生产若误设 `TIME_SCALE`，以 `GAME_ENV=production` 覆盖为 1，防止误加速。

### 语义
- **设计时长** `hours_planned`：玩家意图的闭关小时数（收益/枯坐窗口/租金仍按设计小时）。
- **墙钟时长** = 设计小时 × 3600 / TIME_SCALE。
- 结算时：墙钟流逝 → 乘回 TIME_SCALE 得设计秒，再换算游戏年/有效吐纳小时。
- 进度展示「约余 X 小时」按**设计小时**。

### 触及点
- `config.py`：`GAME_ENV` / `TIME_SCALE` / `is_production()` / `wall_seconds()` / `design_seconds()`
- `core/clock.py`：`start_meditation` 写 `end_time`；`get_meditation_progress` / `settle_meditation` 换算
- 开服日志打印 env + scale
- `.env` 可覆盖（已有加载逻辑）

## [S3] Out of Scope
- 寿元全局墙钟、赛季、新手 72h、悬赏有效期的加速（仍按现实秒；仅闭关墙钟缩放）。
- 前端改 UI。

## Tasks
- [x] T1: config 增加 GAME_ENV/TIME_SCALE 与换算函数
- [x] T2: clock 闭关起止/进度/结算接入缩放
- [x] T3: 回归测试
- [x] T4: Review（套件通过；无 critical）
