# F12 飞升榜 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F12）。基线：8692ca8（F01–F11 已合，全量 436 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：跨世/跨纪元榜单，按历世最高境界、道统点、坐化年龄综合排序，数据来自 player_legacy；/飞升榜 与网页入口；区别于现有单世天机榜。
- **本质意图**：游戏的核心循环是「一世终结 → 道统结算 → 转世」，但已坐化的前世只躺在个人道统账里（/道统 自看），天下无人可见——一世的成就感在死亡瞬间蒸发。飞升榜把历世记录做成全服纪念碑：给「活得高、活得久」一个跨纪元的公共名次，让死亡结算多一层荣誉产出（不发任何数值奖励，纯荣衔，防刷口径与六榜一致）。
- **关键目标**：榜单口径定死可复算（公式+算例+确定性 tie-break）；收录范围与 legacy 落账时点严格一致（只有已结算的前世入榜，现世永不入）；与现世六榜数据互不污染；纯只读零写盘零 AI。

## 现状盘点（实测，2026-11-04）
- **player_legacy 表**：`storage/db.py` 建表 `(user_id TEXT PK, data_json, updated_at)`，存的是**账号级** `LegacyAccount` JSON（`core/legacy.py`），非一行一世：`points`（当前道统点余额）、`total_lives`、`total_points_earned`、`death_times`（近 20 次）、`past_lives: List[PastLife]`（**只保留最近 10 世**，超出即被结算逻辑截断——榜单口径受此限，见边界）。
- **PastLife 字段**：`name`（该世道号）、`realm`（境界**全名**字符串，如「金丹期圆满」= REALM_NAMES[tier]+SUB_TIER_NAMES[sub]）、`cause`（死因原文，自由文本）、`lifespan_lived`（约活了多少岁 = birth_base + accumulated_gain 近似值）、`sin`/`merit`、`points_gained`（该世结算入账的道统点，已扣自杀惩罚）、`died_at`（Unix 时间戳，旧档缺省 0.0）。**无 tier 数值、无 season/纪元字段**——tier/小阶须从 realm 全名反解（REALM_NAMES/SUB_TIER_NAMES 均在 config，是 Realm.name 的唯一生成口径，反解可靠）；纪元须由 died_at 经赛季时钟推导（下条）。
- **落账时点**：`LegacyEngine.settle_death` 是唯一写入 past_lives 的路径，server 在 `World._settle_if_needed`、CLI 在死亡流程中各调用一次并 save。即「入 player_legacy.past_lives」⇔「该世已终结结算」，收录范围天然与落账一致，无需额外状态判断。现世角色在 characters 表，与 legacy 两套数据，天然隔离。
- **NPC 口径**：NPC 角色 user_id 以 `npc_`/`ai_npc_` 开头（leaderboard._is_player 另把 `t_` 前缀判为非玩家）。NPC 死亡是否走 legacy 结算不影响本榜：榜侧一律按账号 user_id 前缀过滤，只收玩家账号（npc_/ai_npc_/t_ 排除），与六榜同口径。
- **现世六榜**（`core/leaderboard.py`，即题面的「天机榜」类榜单）：境界/战力/凶名/道行/传奇/资产，数据源是 `CharacterRepository.list_all_alive()` 的**现世存活角色**，走 `/榜`。飞升榜与之正交：数据源 legacy 已落账前世、含已死者、跨纪元。
- **既有缺口（只记录，不在本项修）**：CLI 端**没有** /榜 处理器（server 有）；server 闭关白名单 med_ok 也未含 /榜。本项只保证 /飞升榜 自身双端一致 + 闭关口径（见决策 4），不顺手改六榜。
- **纪元推导**：`core/season.py::season_info(now)` 是赛季时钟单点（epoch 存 data/season_epoch.txt，SEASON_DAYS=84），返回含 `season_number` 与 `epoch`。任意时刻的纪元号 = season_info(该时刻)["season_number"]， died_at>0 时可推导，不需要给 legacy 加字段、更不改表。
- **仓储缺口**：`LegacyRepository` 只有 save/get_or_create，无全量读。本项加一个**只读** `list_all()`（跳过损坏行），不改表结构。

## 关键设计决策
1. **新引擎单点 `core/ascension.py`**：`AscensionEngine` 纯只读——展开全部玩家账号的 past_lives 为榜条目 → 规则计分 → 确定性排序 → 文本面板。server/cli 只调 `panel_text(char, arg)`，同引擎同口径（F09 /版图 先例）。零写盘、零 AI import。
2. **综合分公式（常量在 ascension.py，tier 严格主导）**：
   `score = tier*1000 + sub_tier*100 + points_gained*10 + min(lifespan_lived, 300)*0.5`
   （ASCEND_W_TIER/SUB/POINTS/AGE、ASCEND_AGE_CAP_YEARS=300）。量级自检：低一档境界的理论最高分 = 1000 阶差 −(小阶 300 + 道统点 250 + 寿龄 150) = 仍差 300，故**境界档位严格决定名次带宽**，道统点/寿龄只在同档内分高下——符合「最高境界为大头、道统点次之、坐化年龄小权重」的题面公式。
   算例：金丹期圆满（tier3/sub3)、points 25、享寿 120 → 3000+300+250+60 = **3610**；筑基期初期（tier2/sub0)、points 20、享寿 80 → 2000+0+200+40 = **2240**；凡人（tier0/sub0）拉满 points 25 + 享寿 300 → 400，仍低于练气期初期白板（1000)。
3. **tie-break 确定性**：同分按 ① died_at 升序（先坐化者居前，died_at=0 的无戳记录视为最晚）→ ② 道号名升序 → ③ user_id 升序 → ④ 死因/道统点/享寿兜底（评审 S1 补强，逼近严格全序；list_all 亦按 rowid 定序）。无随机，同数据多次查询结果逐字一致（有测试钉死）。
4. **收录范围**：只收玩家账号（过滤 npc_/ai_npc_/t_ 前缀）past_lives 中**已落账**的记录；现世角色永不入榜（数据面天然隔离 + 测试断言）；同一账号多世可同时在榜（榜纪的是「世」不是「人」）。NPC 的 legacy 无论是否存在一律不入。
5. **纪元维度**：条目纪元号由 died_at 经 `season_info` 推导（died_at≤0 → 纪元不详，展示「纪元不详」、不入任何纪元过滤）。`/飞升榜 本纪元` 只列当前纪元落账者（名次在过滤集内重排，并注明「本纪元名次」）。推导不落库、不改表。
6. **死因大类**：cause 原文按关键词规则归类展示——含「劫」→渡劫陨落；含「魔」→心魔入魔；含 杀/斩/斗/战/仇/凶 →陨于斗法；含 寿/坐化/老 →寿尽坐化；其余→道陨身死。面板只展示大类；cause 原文保留在条目数据内（评审 S6 对齐：面板不附注原文）。
7. **自查与查名**：`/飞升榜 我|自己` 或参数等于查看者当前道号 → 本人视角：列出自己各前世的**全局名次**与最佳一世，无落账时友好文案。其余参数按道号查名：精确匹配优先、子串兜底，命中取最高名次者并示其全局名次；未命中友好文案。自查名次用全局榜序（过滤视图不改全局名次口径，自查恒查全局）。
8. **双端与闭关/死亡口径**：/飞升榜 是纯只读观照——server 加入 med_ok 白名单、CLI 加入闭关豁免名单（与 F09 /版图、F03 /行情 同口径：只读观照闭关放行）；死亡口径不特判（server/CLI 既有死亡流程对查询指令的全局口径自然适用，引擎本身对查看者生死无要求，char 可为 None 时退化为无视角查询）。别名 `/ascend` 双端一致。
9. **展示**：默认前 ASCEND_TOP_N=20 名。每行：名次、道号、境界全名、综合分、享寿、死因大类、纪元（第N纪元/纪元不详）。榜头写定位语「历世纪念碑 · 只录已坐化落账之前世；现世人物看 /榜 六榜」，与六榜互指区分。空榜友好文案。网页在世情卡六榜按钮旁加「飞升榜」按钮（data-cmd="/飞升榜"，app.js 既有 /榜/ 正则已覆盖面板路由）。

## 行为契约
- `/飞升榜`（server + cli)：全局榜前 20。
- `/飞升榜 本纪元`：当前纪元过滤榜。
- `/飞升榜 我` / `/飞升榜 <道号>`：自查 / 查名（见决策 7）。
- 引擎 API：`collect_entries(accounts=None)`（可注入账号集便于测试）→ 已排序带 rank 的条目；`ranked(season=None, accounts=None)`；`panel_text(viewer, arg=None)`；`score_of(tier, sub, points, lived)` 纯函数。
- `LegacyRepository.list_all()`：只读全量，损坏 JSON 行跳过不崩。
- 任何路径零写盘、零 AI 调用；查询不改变任何状态（含不刷新 season epoch 文件的语义——season_info 读 epoch 时若文件缺失会按既有行为创建，与 /纪元 指令同口径）。

## 边界
- past_lives 每账号只保留最近 10 世（legacy 既有截断）：榜单只能纪存量内的世，更早的世已不在数据中，属既有数据保留策略，本项不改。
- lifespan_lived 是近似享寿（birth_base + accumulated_gain），面板按「享寿约」语义展示，不冒充精确死亡年龄。
- realm 全名反解失败（未知字符串）→ tier/sub 按 0 计、仍收录展示，不丢记录。
- 同一道号可被不同账号/不同世复用：榜条目以（user_id, died_at, name）为身份，查名命中多条时取最高名次并注明同名世数。
- 跨进程口径：纯只读，无并发写问题。

## 验收标准
- [ ] 公式算例与 tier 严格主导有数值断言测试。
- [ ] tie-break 确定性：同分多条按 died_at→名→user_id 排序，两次查询逐字一致。
- [ ] 收录范围：现世存活角色不入榜、已落账前世入榜、NPC/t_ 账号 legacy 不入榜。
- [ ] 纪元过滤：构造跨纪元 died_at，本纪元榜只含本纪元条目且名次重排。
- [ ] 自查：有落账者示全局名次、无落账者友好文案；查名精确/子串/未命中三路。
- [ ] 空榜文案；损坏 legacy 行不崩榜；旧档 PastLife 缺省字段（died_at=0）展示纪元不详。
- [ ] 与六榜互不污染：同数据下现世角色只在六榜、前世只在飞升榜。
- [ ] 双端：server handle /飞升榜 通路 + 闭关白名单放行；CLI 同引擎直调 + 源码对齐（处理器/豁免名单/帮助行在位）。
- [ ] 全量回归 0 失败（基线 436 + 新增）。

## Out of Scope
- 六榜的 CLI 缺失与闭关白名单缺口修复（既有问题，只记录）。
- 飞升榜发奖/称号/转世加成联动（纯荣衔，与六榜防刷口径一致）。
- 按纪元编号任意查（如 /飞升榜 第3纪元）、历史纪元归档页。
- past_lives 保留上限调整、legacy 表结构变更。
- NPC 名人堂、宗门维度的历世聚合榜。
