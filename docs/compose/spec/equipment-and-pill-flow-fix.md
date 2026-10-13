# 规格说明：法宝装备同槽替换流转与动态灵丹化纳修复 (equipment-and-pill-flow-fix)

## 1. 痛点问题 (Problem)
- **装备同槽替换原物消失**：当道友身上已佩戴法宝装备，自藏宝图或纳戒中选择同槽位的新神兵进行佩戴替换后，原有的旧法宝装备离奇消失，且百宝纳戒中的道具也会偶尔错乱丢失。
  - *根因*：`core/loot_equip.py` 中的 `EquipEngine.equip` 仅在旧版纯文本 `c.inventory` 中追加了装备名，未将旧装备回退至 Core-V2 `c.items` 实体列表中；且藏宝图挖出的神兵仅在前端本地伪造，服务端未真实落盘。前端一旦接收服务端同步，未入库的新法宝和卸下的旧装备被瞬间覆盖抹除。
- **灵丹展示“服用”按钮却提示不可服用**：百宝纳戒中对灵露（如玄冰玉露）、高级丹药（如九转还魂真丹）展示了「服食灵丹 (周天化纳)」按钮，但点击后服务端硬核抛出「不是可服用的丹药」。
  - *根因*：`core/market.py` 中的 `MarketEngine.use_pill` 仅查询硬编码静态字典 `ITEM_CATALOG`。所有由洞府灵泉产出的灵露、藏宝图挖出的仙丹、炼丹系统动态合成的丹药均不在硬编码字典中，导致判定直接失败；且服用扣除未同步操作实体背包。
- **服务端状态投影遗漏装备信息**：服务端 `_status_dict` 未返回 `equipped` 列表，导致前端与服务端真实穿戴状态长期割裂。

## 2. 总体设计方案 (Design)
1. **Core-V2 实体道具与装备三槽双向流转闭环 (`core/loot_equip.py`)**：
   - 彻底将 `EquipEngine.equip` 与 `unequip` 升级为面向 `c.items` 实体的权威控制器；
   - 佩戴装备时：定位实体、核验槽位（武器 weapon、道袍 armor、灵佩 trinket）；
   - 同槽替换时：如果该槽位已有旧法宝，从 `c.equipped` 移除并确保其对应实体完好留在 `c.items` 纳戒中；新装备名称加入 `c.equipped`；
   - 卸下装备时：从 `c.equipped` 移除，实体依然安然保存在纳戒中；
   - 保证 `c.items` 与 `c.equipped` 数据结构严丝合缝，绝不吞物。

2. **藏宝图破阵出宝服务端权威落账 (`core/treasure_system.py`)**：
   - 在 `TreasureEngine.dig` 中，当破阵启封成功时，服务端权威生成对应的神兵法宝 `ItemEntity`（根据藏宝图品阶生成斩龙古剑、太乙玄天戈等绝世神兵，附带词缀属性），连同仙丹一并添加至 `c.add_item_entity(...)`；
   - 前端不再在本地孤立伪造未同步的数据，完全消费服务端的权威响应，杜绝换装时被旧快照抹除。

3. **动态丹道化纳通用引擎 (`core/market.py`)**：
   - 重构 `MarketEngine.use_pill`：优先通过 `c.find_item(item_name)` 检索 `c.items` 实体道具；
   - 判定规则：只要实体 `kind in (ItemKind.PILL, ItemKind.CONSUMABLE)` 或物品名包含丹/露/丸/液，即为合法灵丹；
   - 药力化纳：根据丹药品阶（凡品/人品/地品/天品/仙品）与属性，动态结算周天真元增长（如 +200~1000 真元）、闭关加成倍率或寿元温养；
   - 原子消费：实体数量减 1（若为 0 则从 `c.items` 与 `c.inventory` 彻底移除），并安全记入 `c.used_pills`。

4. **服务端状态投影完整化与前端对齐 (`server/world.py`, `web/workbench.js`)**：
   - `_status_dict(c)` 输出权威的 `"equipped": list(getattr(c, "equipped", []))`；
   - 前端 `applyStatus` 接收并更新 `state.equipped`；
   - 前端挖宝与装备处理对接服务端的真实实体流转。

## 3. 不在本次范围 (Out of Scope)
- 装备持久度与修理大阵系统（维持当前法宝无损磨损设定）。

## 4. 可独立验收的任务列表 (Tasks & Acceptance Criteria)
- [x] **Task 1: 服务端装备同槽替换与实体道具双向无损流转 (`core/loot_equip.py`, `core/models.py`)**
  - **验收标准**：穿戴、同槽替换、卸下装备时，原装备实体完好留存于 `c.items`，纳戒与已穿戴列表完全对应。
  - **证据**：`test_equipment_same_slot_replace_preserves_entities` 通过；斩龙古剑替换为太乙玄天戈后，旧剑 UID 与全部词缀完好留驻纳戒。
- [x] **Task 2: 藏宝图挖宝神兵法宝服务端权威生成与入戒 (`core/treasure_system.py`)**
  - **验收标准**：`/挖宝` 成功时服务端权威生成神兵实体并入 `c.items`，前端不再凭空生成脱节数据。
  - **证据**：`test_treasure_dig_generates_authoritative_equipment_and_pill` 通过；权威神兵（带攻伐词缀）与极品丹药落账入戒。
- [x] **Task 3: 丹药通用化纳引擎与 Core-V2 实体动态兼容 (`core/market.py`)**
  - **验收标准**：玄冰玉露、九转还魂真丹等未在静态表中的灵丹均可正常服食，真元/寿元生效，实体原子扣减。
  - **证据**：`test_dynamic_pill_consumption_xuanbing_yulu` 与 `test_dynamic_pill_consumption_jiuzhuan_huanhun` 通过；真元+250、道心+5、寿元+3.0，实体原子出库。
- [x] **Task 4: 服务端状态投影补充 `equipped` 与前端纳戒装备同步 (`server/world.py`, `web/workbench.js`)**
  - **验收标准**：`_status_dict` 输出 `equipped`；前端纳戒与已装备卡片动态同步，换装不丢失。
  - **证据**：`test_status_dict_includes_equipped_and_filters_unworn` 通过；`st.equipped` 返回完整法宝槽位数据，纳戒 `st.items` 自动过滤身上已戴神兵。
- [x] **Task 5: 装备替换与丹药服用单元回归测试套件 (`tests/test_equipment_and_pill_flow.py`)**
  - **验收标准**：编写并全部通过同槽替换实体不丢、挖宝神兵入戒、动态丹药化纳的测试用例。
  - **证据**：`tests/test_equipment_and_pill_flow.py` 6 个用例 100% 全部 PASSED。
- [x] **Task 6: 全链路回归与端到端验证 (`tests/`, `web/workbench.js`)**
  - **验收标准**：全库相关测试 100% 通过，无回归破坏。
  - **证据**：`tests/test_equipment_and_pill_flow.py`、`tests/test_loot_equip_apoc.py`、`tests/test_core_v2_treasure.py`、`tests/test_core_v2_items.py`、`tests/test_market.py`、`tests/test_pill_buff.py` 合计 35 个测试用例全部 PASSED (2.22s)。

## 5. 验收报告 (Report)
- **修复效果**：
  1. 彻底解决了用户痛点：“身上穿了装备，藏宝图出装备佩戴后原装备消失，戒指内物品消失”。服务端权威落账 + 纳戒与装备双轨无损流转，换装时旧神兵词缀属性 100% 保留。
  2. 彻底解决了用户痛点：“部分灵丹点击后提示不可服用”。重构了通用灵药化纳引擎，洞府灵泉【玄冰玉露】、藏宝图【九转还魂真丹】等动态实体丹药均能完美服食，真元、道心与寿元温养即时生效，无损原子扣减。
  3. 服务端 `_status_dict` 增加权威 `equipped` 输出，前端实时同步状态，根除了前后端状态割裂。
