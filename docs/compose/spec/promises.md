# F14 诺言账闭环 Spec

> 总纲：docs/compose/spec/feature-completion.md · F14
> 路径：requirement-evaluator 五步细化 → 本 spec → worktree 实现 → 全量回归 → 独立评审 → 合并

## 一、需求本质解构

- **表层需求**：补 /许诺 指令——对 NPC/玩家立诺，条件达成自动核验或到期判违约，因果账落账（接 karma_links），履约得功德、违约沾业力并入世情播报。
- **本质诉求**：游戏里已有「恩/仇」因果链（karma_links）与功德/业力账（KarmaLedger），但玩家口头承诺无任何约束与留痕；需要一条「言出法随」的规则闭环：诺言只能由指令立、只能凭既有事实核验、结算只能走既有功德/业力通道，让承诺成为可信的社交资产而非聊天文本。
- **系统定位**：新增 `core/promises.py` 引擎单点 + `promises` 新表；核验钩子挂在四个既有事实落账点（赠礼/迁跃/委托完成/斗法出手）；双端（server/cli）同引擎同口径；网页同场卡加入口。

### 现状盘点（实测结论）

1. **功德/业力唯一账本** = `Character.karma`（KarmaLedger，core/models.py）：`add_merit(v)`（功德 +v 且业力消解 v//2）、`add_sin(v, now)`（业力 +v 且按全仓既有口径沾血煞 3 游戏年）。禁止新造第二套功德数——诺言结算只调用这两个方法。单次 caps 对照 `EVENT_EFFECT_CAPS`：merit 40 / sin 40；既有量级：委托完成 merit +5、除凶 +40~60、杀人 sin +25~40 量级。
2. **karma_links** = `KarmaLink`（core/bounty.py，字段 a/b 双方 + link_type 仇/恩/师徒/宗门 + strength + note），`KarmaLinkRepository` 落账，/因果 面板展示（未知 link_type 默认样式可正常渲染）。诺言结算是「因果账落账」点：终态时写一条 link_type=「诺」的因果链，note 记明践诺/违约与诺目内容。
3. **NPC 态度唯一通道** = `core.npc_mind.shift_attitude(npc, other_id, delta, reason)`（F07 委托完成 +8 先例，内部钳制）。
4. **既有事实点（核验只认这些）**：
   - 赠礼：`core/chat_actions.py::do_gift`（玩家→NPC 会话赠礼，全仓唯一纯赠予结算点；玩家间只有 /交易 出价交换，无纯赠予事实）；
   - 迁跃：server `World._go` 与 cli `/前往` 两处落点后（与 sect_contrib「visit」环钩同位）；
   - 委托整链完成：`QuestEngine.deliver` 完成落账段（与 F09 版图、F11 灵感钩子同段，结构性恰一次）；
   - 斗法出手：`CombatFateEngine.resolve_ambush`（server /斗法、cli /斗法、会话动手三端唯一漏斗；硬前置——安全区/已死/新手庇护/归隐/AI 未就绪——全数拦截后、mark_combat 处，出手即成事实，被拦截的未遂不算出手）。
5. **死亡收尾**：server `World._settle_if_needed` 与 cli `settle_and_reincarnate` 均有 on_owner_death 钩子排（F01 灵宠 / F06 灵田 / F07 委托），诺言同排加入。
6. **世情播报**：`core.jianghu.append_event(kind=..., ...)`（F07/F11 既有口径，尽力而为不炸主流程）。

## 二、行为契约（真正需求）

### 2.1 诺言类型（规则模板池，禁止自由文本判定）

| kind | 指令式 | 对象 | 期限（现实秒） | 核验事实（唯一） |
|---|---|---|---|---|
| gift 赠物 | `/许诺 <NPC名> 赠物 <物品名>` | 仅 NPC | 3 日 = 259200 | 期限内经 do_gift 真赠出同名物品给该 NPC |
| arrive 抵达 | `/许诺 <对象名> 抵达 <地点名>` | NPC/玩家 | 3 日 = 259200 | 期限内迁跃落点 == 目标地点（全名） |
| quest 委托 | `/许诺 <对象名> 委托` | NPC/玩家 | 3 日 = 259200 | 期限内整链委托完成（deliver 完成段） |
| no_attack 不攻 | `/许诺 <对象名> 不攻` | NPC/玩家 | 7 日 = 604800 | 期限内未对该对象出手（出手钩子即时判破）；到期未出手即履约 |

- 地点名子串匹配解析为 WORLD_LOCATIONS 全名（与 /go 同口径），解析不到拒绝立诺；赠物物品名不预检行囊（可先立诺后寻物，与委托寻物环同理），仅要求非空。
- 一人同时未结诺上限 `PROMISE_MAX_OPEN = 3`（PENDING + ACTIVE 合计，按立诺者计）；同一「对象 + 类型」已有未结诺则拒绝重立（防叠诺刷功德）。

### 2.2 成立方式（防单方面陷阱）

- **对 NPC 立诺**：当面（同场）立诺即成立（ACTIVE），NPC 为见证受诺人，天道记账。
- **对玩家立诺**：先入 PENDING（待应诺）；对象在 24 小时（`PROMISE_ACCEPT_TTL_SECONDS = 86400`）内以 `/应诺 [立诺者名]` 应下才转 ACTIVE，**期限自应诺时刻起算**（待应诺不吃期限）；逾期未应 → DISSOLVED（未成之诺，无功无过）。义务只落在立诺者身上，应诺方不承担任何义务——应诺只是「我听见了」，防的是立诺者对不知情者单方面造账。
- 成立条件（双方）：立诺者存活、对象存活、对象与立诺者同场（location 全等）、对象非自己；立诺者处于 DEAD 拒绝。闭关中四指令全部锁门（指令层，见 2.5）。

### 2.3 状态机与结算（幂等）

状态：`PENDING → ACTIVE → KEPT / BROKEN / DISSOLVED`，终态不可逆。`_settle()` 是唯一写终态入口：**先落终态存库（幂等锚），再发效果**（与 F07「先清链后发奖」同构）；已是终态的诺重复触发直接短路，同一诺绝不重复结算。

核验/结算触发点（惰性推进，无新线程）：
- 事实钩子即时结算：赠出命中 → KEPT；抵达命中 → KEPT；委托完成 → KEPT；对受诺人出手 → BROKEN（当场）。
- 惰性结算 `settle_due(char)`：打开 /诺言 面
...[truncated 2405 chars]