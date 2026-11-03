# F02 心法槽位 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F02）。基线：a65e737（全量 264 passed，含 F01 灵宠）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：把现有 skills/自创功法收进槽位制：主修 1 + 辅修 2，装配/卸下有指令，切换有冷却。
- **本质意图**：功法目前「学会即全生效、无取舍」——自创功法按最高倍率自动生效（闭关），
  玩家对功法没有经营决策。槽位制引入「专注取舍」：选哪门主修冲修炼、哪两门辅修撑斗法，
  是玩家可感知、可调整的构筑选择，且切换成本（冷却）防临场刷加成。
- **关键目标**：槽位数据落角色字段；双端指令闭环；加成全部规则系数且封顶；
  未装配时与旧行为逐字一致（回归基线不破）。

## 现状盘点（实测，2026-11-04）
- `Character.skills: List[str]` 默认 `["吐纳术", "御剑术"]`；来源：事件授予（events apply_effects）、
  道统遗产（legacy）、自创功法成功后追加名字（server/world.py、cli/main.py 双端）。
  「筑基丹药力(待渡劫)」是写进 skills 的临时标记（market.py），不是功法——槽位校验须容忍
  skills 中存在非功法字符串（玩家选了也只是占槽，无额外数据，属自担，无需黑名单）。
- `Character.custom_arts` 存自创功法 DSL；其固有效果**当前全部自动生效**：
  闭关取最高 `exp_gain_multiplier`（core/art.best_exp_multiplier，上限 2.5）与最高燃寿；
  斗法 `art_combat_bonus` 取最佳神通倍率（core/loot_equip，上限 +20%）。
- `/功法`（server）只列自创功法 DSL 卡片；普通 skills 无独立面板。
- 战力入口：`CombatEngine.calculate_power` 已依次乘 sect ×1.2（万剑）、EquipEngine.power_bonus
  （内部封顶 +20%）、art_combat_bonus（≤+20%）、PetEngine.power_bonus（≤+10%，F01）。
- 修炼入口：`WorldClock.settle_meditation` 的 raw_gain 连乘 灵根×地点×灵气稀释×art_mult×新手×丹药。

## 可行性诊断与系统影响
- **技术可行性**：高。槽位是角色新字段（pydantic 默认值兼容旧档）；
  两个加成接入点均为单行连乘/独立 try 块，照 F01 灵宠模式接入互不覆盖。
- **系统影响面**：core/models.py（3 新字段）、core/art_slots.py（新引擎+常量）、
  core/clock.py（闭关连乘加 slot 因子）、core/combat.py（战力加 Pet 块后追加 Art 块）、
  server/world.py（4 指令 + med 门禁 view 白名单 + _status_dict arts 字段 + 帮助行）、
  cli/main.py（4 指令 + 闭关白名单 + 帮助）、web（按钮 + 法门行主修展示）。
  不动表结构、不动既有数值常量、不动自创功法 AI 路径。

## 关键设计决策（与备选对比）
1. **槽位加成与自创功法固有效果的关系**：
   - 备选 A「装配才生效」：主修决定哪门自创功法倍率生效。**否决**——会让未装配的老玩家/
     老测试直接丢失现有倍率，违反任务硬约束「未装配时与旧行为完全一致」。
   - **采用 B「专注加成独立结算」**：自创功法固有效果（最高倍率/燃寿/神通）保持原样自动生效；
     槽位提供一层新的、小幅的「专注」加成（见下）。未装配 → 新因子恒为 1.0 → 旧行为逐字不变。
2. **旧档迁移**：**留空待玩家自选**（main_art 默认 ""、sub_arts 默认 []）。
   理由：① 与决策 1 自洽——自动装配等于给全体存量角色无声发放 +10%/+6%，是未经宣告的平衡变更；
   ② skills[0] 对所有人都是默认「吐纳术」，自动主修无构筑意义；③ 槽位的玩法价值就在自选，
   /心法 面板会明确引导。代价：老玩家需手动装配一次才吃到新加成，可接受。
3. **冷却范围**：主修/辅修/卸功任一**成功**的槽位变更都刷新冷却并进入冷却
   （ART_SLOT_COOLDOWN_SECONDS=3600 现实秒）；首次装配（从未变更过）不受冷却。
   备选「仅装配冷却、卸下免费」否决：卸下免费+装配冷却仍可先卸后装绕开意图，统一口径最防刷。
4. **闭关态**：/心法 查看进双端闭关白名单（只读观照，与 /灵宠 同例）；
   主修/辅修/卸功闭关中一律被既有门禁拦截（防闭关结算前临场换主修吃加成）。

## 完善后的规则闭环（行为契约）
### 数据（core/models.py，带默认值）
- `main_art: str = ""`（主修功法名，须 ∈ skills）
- `sub_arts: List[str] = []`（辅修功法名，最多 2，互不重复且 ≠ main_art）
- `art_slot_changed_at: float = 0.0`（上次成功变更槽位的现实时间戳；0 = 从未变更）

### 常量（core/art_slots.py）
- `ART_SUB_MAX = 2`
- `ART_SLOT_COOLDOWN_SECONDS = 3600.0`（1 现实小时）
- `ART_MAIN_MEDITATION_BONUS = 0.10`：主修装配后闭关修为 ×1.10（专注加成）
- `ART_SUB_POWER_BONUS_EACH = 0.03`、`ART_SUB_POWER_BONUS_CAP = 0.06`：
  每门**有效**辅修斗法战力 +3%，两门封顶 +6%

### 叠加与封顶口径（防战力膨胀，总纲约束）
- 斗法 calculate_power 连乘链（乘法叠加，各自封顶）：
  宗门 ×1.20（万剑）× 装备 ≤×1.20 × 自创神通 ≤×1.20 × 灵宠 ≤×1.10 × **心法辅修 ≤×1.06**。
  心法是全链最小一环（+6%），全乘极值约 ×2.02（F02 前约 ×1.90），增幅可控。
- 闭关 raw_gain 连乘链：既有 art_mult（≤2.5）之后新增 slot 因子 ≤×1.10，
  极值 2.5×1.10=2.75；主修不改变燃寿口径（燃寿仍取自创功法最高值，与槽位无关）。

### 引擎（core/art_slots.py · ArtSlotEngine，照 PetEngine 模式）
- 名称解析：对 skills 做精确 → 子串模糊匹配（与 /穿戴、灵宠同惯例）；多义时报错列候选。
- `set_main(c, name, now=None)`：拒绝 死亡 / 未习得（含查无此功法）/ 已是当前主修（无操作）；
  冷却中拒绝并报剩余分钟；若该功法在 sub_arts 中，先移出辅修再入主修（槽位互斥，单点维护）；
  成功写 main_art + changed_at。
- `add_sub(c, name, now=None)`：拒绝 死亡 / 未习得 / 已是主修 / 已在辅修 / 辅修已满 2 / 冷却中；
  成功追加 + changed_at。
- `remove(c, name, now=None)`：从主修或辅修中卸下（模糊匹配已装配项）；未装配报错；
  冷却中拒绝；成功清空/移除 + changed_at。
- `meditation_mult(c)`：main_art 非空且 ∈ skills → 1.10，否则 1.0（防御性校验，防脏数据白嫖）。
- `power_bonus(c)`：1 + min(0.06, 0.03 × 有效辅修数)，有效 = sub_arts 中仍 ∈ skills 且 ≠ main_art 的去重计数。
- `panel_text(c)`：槽位现状（主修/辅修/空位）、冷却剩余、已习得候选列表与当前加成说明。
- 引擎只在成功时改角色（失败零副作用）；落库由双端 handler 在 success 时 save（F01 惯例）。

### 指令（server 与 cli 双端一致）
- `/心法`（xinfa）：面板。
- `/主修 <功法名>`（main_art）：设主修。
- `/辅修 <功法名>`（sub_art）：加辅修。
- `/卸功 <功法名>`（remove_art）：卸下主修或辅修。
- 死亡角色：server 通用死亡门禁与引擎双重拒绝；闭关中仅 /心法 可用（门禁层）。

### 接入
- 闭关：settle_meditation 的 raw_gain 连乘追加 `slot_mult`（try 包裹，异常回 1.0，与 art_mult 同风格）。
- 斗法：calculate_power 在 PetEngine 块之后追加 ArtSlotEngine.power_bonus 连乘（try 包裹）。
- status：_status_dict 新增 `arts: {"main": str, "sub": [..]}`（纯新增字段）。
- 网页：仙门·坊市卡加按钮 心法（data-cmd=/心法）、主修…/辅修…/卸功…（data-prompt）+ app.js 提示；
  行囊法门行（bagArts）在 applyStatus 渲染时附「主修：X」。

### AI 边界
零新增 AI 调用；自创功法 AI 生成/钳制路径一字不动；无 AI 模式完整可玩。

## 潜在不足、盲区与风险（部分已内化进契约）
1. **[重复装配刷冷却]** 设同一主修 → 判无操作不刷新冷却（契约已定）。
2. **[技能消失]** skills 现行机制从不移除功法；power/meditation 仍做 ∈ skills 防御校验，脏数据不白嫖。
3. **[冷却时钟]** 用现实时间戳 time.time()，与寿元/俸禄等既有冷却同源；测试注入 now 参数，不 sleep。
4. **[CLI/LAN 存档互通]** 同一 CharacterRepository，字段随角色 JSON 走，双端天然一致。
5. **[status 旧前端]** arts 为新增字段，旧前端忽略；bagArts 渲染对 st.arts 缺失做空守卫。

## Out of Scope
- 槽位按功法品阶/性质差异化加成（自创功法倍率差异已由固有效果承载，槽位只做统一专注加成）。
- 功法遗忘/洗功法、槽位随境界扩增（主修恒 1、辅修恒 2）。
- 心法与宗门/师徒联动（传功不自动装配）。
- 网页独立心法面板页（按钮 + 法门行展示即最小闭环）。

## 验收标准
1. tests/test_arts.py 覆盖：旧档反序列化默认空槽、装配未习得被拒、主修唯一（含辅修转主修互斥）、
   辅修上限 2 与重复/主修冲突、冷却拦截与冷却后可改、卸功（主修/辅修/未装配报错）、
   修炼效率加成生效数值断言（settle 同条件对比 ×1.10）、斗法加成接入与 +6% 封顶、
   未装配时 power 与闭关产出与旧行为一致、server handle 与 CLI 引擎全链路至少各 1 条。
2. 全量 pytest 0 失败（基线 264 + 新增）。
3. 网页按钮与 status arts 字段存在，app.js 语法自检通过。

## 状态
- [x] 阶段一细化（本文）
- [ ] Implement
- [ ] Verify
- [ ] 独立 Review
- [ ] Finalize（合并与打版由总纲统一收尾，本分支不自行合并）
