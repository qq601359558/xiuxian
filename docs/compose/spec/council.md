# F08 长老议政 Spec

> 上位文档：docs/compose/spec/feature-completion.md（F08）。基线：be4219a（F01–F07 已合，全量 364 passed）。
> 创作者已授权「直接改、无需逐项确认」，本 spec 即阶段一细化结论（requirement-evaluator 五步收敛）。

## 需求本质与核心诉求
- **表层需求**：宗门内定期开议（开矿/开战/祭典等议题），长老 NPC 按 agenda/性情表态，
  本宗玩家可投票、可花灵石游说长老，截止后按多数决结算，效果落到宗门状态并入世情播报。
- **本质意图**：宗门目前对玩家只是「领俸/晋升/日环」的单向福利机，长老 NPC 纯属布景。
  议政让宗门第一次成为**有集体决策的组织**：NPC 长老按自己的议程与性情站队，玩家用票与灵石
  影响宗门走向，决策后果（金库/声望/士气）全宗可见。是旧系统（宗门编制 + NPC 心智/议程 +
  世情播报）的编排层，不新造组织系统。
- **关键目标**：议题轮转开启→立场确定性推导→投票/游说→惰性结算的闭环可玩通且全程规则可复算；
  结算幂等（重复触发不重复落账）；游说有成本递增与双重上限防刷；效果封顶写常量且真实落到宗门状态。

## 现状盘点（实测，2026-11-04）
- **宗门体系**：`config.SECTS_CONFIG` 固定 4 宗门（青云宗/万剑仙门/九幽天魔宗/四海散修商会），
  只有静态配置（总坛/月俸/门规），**无任何持久化宗门状态**（无金库/声望字段）。
  玩家侧：`Character.sect / sect_rank / sect_contribution`；晋升链 外门→内门→执事→长老（core/sect.py）。
  宗门周期行为：月俸（现实 2h，WorldClock.claim_sect_salary）、宗门日环（core/sect_contrib，world_state KV 先例）。
- **长老 NPC 标识**：NPC 是普通 Character（user_id 以 `npc_`/`ai_npc_` 开头），编制在 core/npc_roster.ROSTER。
  以「sect_rank 含『长老』或 rank ∈ {掌门， 宗主， 会长}」为长老席位口径，各宗在册席位：
  青云宗 4（掌门玄清子、太上长老静虚真人、执法长老云鹤道人、丹殿长老丹霞子）、
  万剑仙门 2（掌门独孤败、大长老断岳剑尊）、九幽天魔宗 2（宗主幽冥老祖、外门长老血刀老祖）、
  四海散修商会 1（会长金满堂）。玩家晋升的「长老」不占席位（席位只认 NPC 编制，玩家用投票参与）。
- **立场原料（既有口径，不新造）**：`core/npc_agenda.ensure_agenda(npc)` → agenda_type
  （revenge/treasure/patrol/social/seclusion/survive 六类，确定性默认）；`core/npc_mind.ensure_mind(npc)`
  → personality（8 种）+ traits{greed/caution/wrath ∈ 0.2–0.8}（确定性生成、落库复用）。
- **持久化先例**：sect_contrib 的宗门环走 `WorldStateRepository` KV（`sect_ring`），
  jianghu 世情走 `core/jianghu.append_event`（/世情 可见）。议政照此办理，不建表、不改 models。
- **数值带**：月俸 25–35/2h、宗门环完成 +50 灵石、聚气丹 40、EVENT_EFFECT_CAPS stones_gain 上限 300。

## 关键设计决策（与备选对比）
1. **状态存 world_state 两键（不建表、不改 models）**：
   `sect_council:{sect}` = 当前议政会话；`sect_state:{sect}` = 宗门状态 {vault 金库， prestige 声望， morale 士气}。
   备选给 Character 加字段否决：议政是宗门级而非个人级状态；备选新表否决：KV 先例足够且天然跨进程。
   sect_state 只存宗门内务三维，**不含区域/版图键**——F09 版图自建其表，不与本键提前耦合。
2. **议题池轮转开启（确定性）**：议题模板池 COUNCIL_TOPICS 固定 5 种（见下），
   会话序号 session_no 自增，议题 = 池[session_no % 5]，保证全池周期覆盖、无随机漂移。
3. **周期与惰性推进**：投票窗口 COUNCIL_VOTE_WINDOW_SECONDS=7200（现实 2h，与月俸同节律），
   场次间隔 COUNCIL_INTERVAL_SECONDS=3600（结算后 1h 开下一场）。
   `advance(sect, now)` 惰性推进：无会话→开场；已结算且 now≥next_open_at→开新场；
   进行中且 now≥closes_at→结算。任一议政指令触发，**不新造线程、不挂 tick**（F07 settle 同模式）。
4. **立场推导（纯函数、确定性）**：`stance_score(topic_id, agenda_type, traits)` =
   议题×议程亲和（COUNCIL_TOPIC_AGENDA，每议题一张六维表）+ 议题×性情修正
   （COUNCIL_TOPIC_TRAITS，每议题声明若干条 {trait, 阈值 0.7, 分值}）。
   score ≥1 支持、≤-1 反对、其余中立。无随机、无时间、无 AI——同输入必同输出（测试钉住）。
   长老发言为本地模板池（按议题×立场选句、长老 id 哈希定句），零 AI 依赖。
5. **虚席兜底**：某宗在册长老席位为 0（如长老尽数陨落）时启用 3 名虚席
   （值年虚席·甲/乙/丙），固定以 patrol/social/seclusion 三种议程查亲和表定立场，无 traits 修正。
   虚席不可被游说（无其人）。席位 ≥1 时只用真实长老，不混虚席。
6. **玩家投票**：仅本宗成员；一人一票（会话 votes 以 char.id 为键），**截止前可改票**（覆盖写）；
   截止后 advance 先结算，投票报「本场已结算」。计票 = 长老有效立场（含游说位移）+ 玩家票，
   支持与反对对等计；**支持 > 反对 → 通过；反对 ≥ 支持 → 否决**（平局否决，保守口径：
   议而不决不如不行）。中立/弃权不入分母。
7. **游说（只为本场议题拉支持票，口径单一）**：仅真实长老 NPC 可被游说；目标已是支持→拒绝不扣费；
   目标原始 score ≤ COUNCIL_LOBBY_RESIST_SCORE(-2) → 铁杆反对，拒绝不扣费不计次。
   否则扣灵石并计次：成本 = COUNCIL_LOBBY_BASE_COST(60) ×（该长老本场已被游说次数 + 1），递增；
   成功使立场向支持位移 1 档（反对→中立→支持，位移存 lobby_steps，上限 1 档/次、总位移钳制到支持）。
   防刷双上限：每长老本场被游说 ≤ COUNCIL_LOBBY_MAX_PER_ELDER(2) 次（全宗合计），
   每玩家本场游说 ≤ COUNCIL_LOBBY_MAX_PER_PLAYER(3) 次。达上限明确拒绝。
   备选「游说可拉向任一方向」否决：双向游说使计票博弈复杂化，灰度先取单向，反对靠投票表达。
8. **结算与效果（封顶、幂等、必落账）**：效果表 COUNCIL_TOPIC_EFFECTS（每议题 pass/fail 两组
   {vault, prestige, morale} 增量），结算时逐项按 COUNCIL_EFFECT_CAPS {vault:400, prestige:15, morale:15}
   再钳一次（防改表越界）；vault 下限 0，prestige/morale 钳 0..100。宗门状态默认
   {vault:1000, prestige:50, morale:50}。结算把 result 快照（结果/票数/效果增量/结算时刻）写回会话并置
   settled=True；settle/advance 重入直接返回快照、**绝不重复落账**（测试钉住：连调 3 次状态只变一次）。
   结算同时 `jianghu.append_event(kind="sect_council", ...)` 入世情（低频，enforce_budget=False 保证必达），
   开场不播报防刷屏。播报时刻取真实墙钟，会话逻辑时刻只存 result.settled_at——否则测试注入的
   逻辑时刻会污染世情「最新」排序（全量回归实测教训，test_lan_feed_endpoint_contract）。
9. **可用性口径（与同类宗门指令对齐）**：
   - server 闭关：三指令**均不进** med_ok 白名单（与 /领俸禄 /晋升 /宗门环 同口径——议政面板带惰性
     结算/开场等状态写，非纯只读观照，闭关锁门）。
   - CLI：与 CLI 既有宗门指令同口径不另设闭关门（CLI 无 med 白名单机制，F07 先例）。
   - 死亡：/议政 查看放行（遗容，含惰性结算，与 F07 面板同口径）；/投票 /游说 由引擎前置 DEAD
     拒绝（DEAD 校验在 advance 之前，死人指令零副作用，F04 S2 先例）。
   - 非成员：无宗籍→「散修无宗可议」；会话只按 char.sect 取，他宗成员结构上投不到别宗的票。

## 完善后的规则闭环（行为契约）
### 常量（core/council.py 模块常量）
- `COUNCIL_VOTE_WINDOW_SECONDS = 7200`、`COUNCIL_INTERVAL_SECONDS = 3600`
- `COUNCIL_LOBBY_BASE_COST = 60`、`COUNCIL_LOBBY_MAX_PER_ELDER = 2`、`COUNCIL_LOBBY_MAX_PER_PLAYER = 3`
- `COUNCIL_LOBBY_RESIST_SCORE = -2`
- `COUNCIL_EFFECT_CAPS = {"vault": 400, "prestige": 15, "morale": 15}`
- `COUNCIL_STATE_DEFAULTS = {"vault": 1000, "prestige": 50, "morale": 50}`（prestige/morale 钳 0..100，vault 下限 0）
- `COUNCIL_LEADER_RANKS = ("掌门", "宗主", "会长")` + rank 含「长老」
- `COUNCIL_TOPICS`（5）：mining 开矿增收 / war 对外开战 / festival 举办祭典 / recruit 广纳门徒 / array 修缮大阵，
  每条含 name、desc（本地文案）、agenda 亲和表、traits 修正、长老发言模板（support/oppose/neutral 各 1+ 句）。

### 效果表（增量，pass / fail）
| 议题 | 通过 | 否决 |
|---|---|---|
| 开矿增收 mining | vault +300, morale -5 | morale +2 |
| 对外开战 war | prestige +12, vault -150, morale +8 | prestige -3 |
| 举办祭典 festival | vault -120, morale +12, prestige +6 | morale -4 |
| 广纳门徒 recruit | prestige +8, morale +4, vault -60 | （无） |
| 修缮大阵 array | vault -200, prestige +5, morale +3 | morale -3 |

### 数据（world_state KV，均为普通 dict）
- `sect_council:{sect}`：{session_no, topic_id, opened_at, closes_at, next_open_at,
  votes: {char_id: "support"|"oppose"}, lobby_attempts: {elder_id: int}, lobby_steps: {elder_id: int},
  lobby_by_player: {char_id: int}, settled: bool, result: {passed, support, oppose, effects, settled_at} | None}
- `sect_state:{sect}`：{vault, prestige, morale}

### 引擎（core/council.py · CouncilEngine，规则单点）
- `get_sect_state(sect) -> dict`：读 KV 并与默认值合并钳制；`_save_sect_state` 内部写。
- `elder_seats(sect) -> List[dict]`：list_all_alive 过滤 NPC + 本宗 + 长老口径，按名排序（确定性）；
  每席 {id, name, rank, virtual: False, agenda_type（ensure_agenda）, traits（ensure_mind）}；空→虚席 3 名
  {id: f"virtual:{sect}:{i}", virtual: True, agenda_type ∈ patrol/social/seclusion}。
- `stance_score(topic_id, agenda_type, traits) -> int`（纯函数）；`stance_of(topic_id, seat, steps=0) -> str`：
  基础立场由 score 阈值定档（-1/0/1），加 lobby steps 后钳到 [-1, 1] 再映射 support/oppose/neutral。
- `advance(sect, now=None) -> dict`：惰性开场/结算，返回当前会话（写 KV 才落盘，变更才写）。
- `settle(sect, session, now=None) -> dict`：幂等结算（已 settled 直接返回快照）；计票→效果钳制落
  sect_state→写 result→jianghu 播报。
- `panel_text(char, now=None) -> str`：无宗籍拒绝文案；否则 advance 后呈现：宗门状态三维、本场议题与
  截止倒计时、长老席位与有效立场（标注虚席/被游说位移）、长老发言、当前票数、玩家自己的票、
  已结算场次呈现 result 与下场开启倒计时。
- `vote(char, side, now=None) -> res`：DEAD 前置拒绝→无宗籍拒绝→advance→已结算拒绝→记票（可改票），
  res {success, message, dirty}（dirty=会话有变更，含 advance 结算）。
- `lobby(char, hint, now=None) -> res`：DEAD 前置拒绝→无宗籍拒绝→advance→已结算拒绝→按名子串在
  真实席位中定位（虚席/查无→拒绝）→已支持拒绝→铁杆拒绝→双上限拒绝→灵石不足拒绝→扣费计次位移。
  成功时 char.spirit_stones 变更，handle 须 save(char)。

### 指令（server/world.py 与 cli/main.py 双端一致）
- `/议政`（/council）：面板。`/投票 支持|反对`（/vote）：投票。`/游说 <长老名>`（/lobby）：游说。
- server 分支置于宗门环分支附近；成功或 dirty 时 save(char)（lobby 扣费在 char 上，vote/panel 的
  变更在 KV 已由引擎落盘，save 仅为口径统一且无害——遵 F07 CLI `success or dirty` 模式）。
- server `_help()` 宗门行加「/议政 /投票 /游说」；cli 帮助宗门段加三行；两端闭关/死亡口径见决策 9。

### 网页
- web/index.html 「仙门 · 坊市」卡 btn-grid 加：议政（data-cmd="/议政"）、
  投票支持（data-cmd="/投票 支持"）、投票反对（data-cmd="/投票 反对"）、
  游说…（data-prompt="游说"，prefix /游说，placeholder「长老名，如：丹霞子」）；
  web/app.js hints 加 游说 一条。议题与立场在文本面板呈现，前端零逻辑改动。

## 验收标准
- [ ] tests/test_council.py：议题轮转生成与周期推进（now 注入：窗口内不开新场、到点结算、间隔后开新场且
      议题轮转）、立场推导确定性（同输入重复调用同结果 + 亲和/性情各一条断言）、虚席兜底、
      投票计票与一人一票（含改票覆盖）、游说成功位移/铁杆拒绝/已支持拒绝/成本递增/双上限、
      多数决通过结算效果落账且不超封顶、否决路径、平局否决、结算幂等（连调不重复落账）、
      非成员拒绝、死亡拒绝投票/游说、无议题边界（间隔期面板呈现上场结果）、双端 handle 至少 1 条、
      旧档兼容（无 KV 的宗门首开自动建状态）。
- [ ] 全量回归 0 失败（基线 364 + 新增）。
- [ ] 独立评审过（重点：结算幂等、游说刷票、F09 接口不提前耦合）。

## Out of Scope（明确不做）
- F09 宗门势力版图（区域控制度/版图影响）——sect_state 不含区域维度，不预留版图接口。
- 玩家出任长老席位、掌门禅让、跨宗围观/投票、议题玩家自拟、AI 生成议题或发言。
- 不动月俸/晋升/宗门环/悬赏等既有宗门行为；不动 SECTS_CONFIG 静态配置。
