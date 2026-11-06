---
feature: chase-locations-ring-gold
status: delivered
updated: 2026-09-17
branch: (no-git-in-place)
commits: n/a
---

# 追查物化地点 + 宗门日环灵石奖

## Report

**What was built** — `/追查 <听闻地点>`：花 30 灵石、每日 3 次，成功写入 `WORLD_LOCATIONS` 后可 `/go`；失败不退钱。GM `/名物 物化 <token> <名>` 强制。宗门日环完成 **灵石+15**，连环 3/7 日再 **+40/+120**。

**Verification** — `test_chase_ring`+`name_guard` 8 passed；全量 **197 passed**（`test_events_ai` PRE-EXISTING 偶发）。

## [S1] Problem

听闻名物不能 `/go`；玩家缺稳定小额灵石。

## [S2] Design

### 2.1 `/追查 <名>`（方案 B）

- 目标：`name_registry` 中 type=location 的 **heard** 条目  
- 代价：**30 灵石**；每人每日最多 3 次（防刷）  
- 成功率：`0.45 + 0.02*tier`，夹在 0.25~0.85  
- **成功**：写入 `WORLD_LOCATIONS`（子场景，`is_safe` 默认 True，父地用 registry.parent 或玩家当前安全区）；registry 状态 `located`；世界频道 major；此后可 `/go`  
- **失败**：只回「未见其门」，灵石不退  
- GM：`/名物 物化 <名>` 强制成功  

### 2.2 宗门日环灵石

完成主题环时除贡献外：

| 连环 | 灵石 |
|---|---|
| 每次完成 | +15 |
| 连环 3 日额外 | +40 |
| 连环 7 日额外 | +120 |

写入 `sync_ring` 返回文案。

## [S3] Out of Scope

- 追查 NPC/物品物化；野外危险子场景战斗表。

## Tasks

- [x] T1 追查引擎 + /追查 + /名物 物化
- [x] T2 日环灵石
- [x] T3 测试 + 全量
