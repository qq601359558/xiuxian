# Spec: 丹药全元数据大目录扩充与耐药衰减/丹毒经济闭环循环

> 状态：**已完成 (Completed)**  
> 对应 Backlog：P0-B #11（丹药耐药衰减与经济循环）  
> 涉及模块：`core/catalogs/pills.py`, `core/models.py`, `core/market.py`, `core/breakthrough.py`, `core/alchemy.py`, `tests/test_pills_catalog.py`

---

## 1. 核心问题与痛点 (Problem)

1. **丹药元数据匮乏与断层**：原系统仅有 20 种骨架级丹药，化神期无仙品大丹，且配方中曾出现不在材料库中的虚构素材（如「三阶金丹兽核」）。
2. **服丹硬锁死导致道具贬值（严重经济断裂）**：原逻辑在服用 `聚气丹`、`玄元聚气丹` 等达到上限后直接抛错阻断（`【本世已服过，再服无益】`），导致玩家背包内积累大量低阶或达标丹药沦为死物品，失去了流通与持有价值。
3. **丹毒机制缺失**：虽有 `toxicity` 属性，但未在角色属性与突破天劫中实质起效，无法体现修仙界「是药三分毒、丹毒噬脉」的核心沉浸感。
4. **缺少丹道回收循环**：多余或抗药封顶的丹药无合理化解通道（既不能当药吃，也无法分解重炼）。

---

## 2. 方案设计 (Architecture & Design)

### 2.1 丹药全元数据总纲 (`core/catalogs/pills.py`)
- **规模与覆盖**：扩充至 61 种原味修仙丹药，61 种丹方配方，双键双向索引（中文名与英文 ID 检索）。
- **五阶境界贯通**：
  - 一阶·凡品（练气期，12颗）：聚气散、聚气生元丹、回春露、延年草还丹、辟毒散、明目清心丸、洗髓散等；
  - 二阶·灵品（筑基期，12颗）：筑基丹、凝元固本丹、玄元聚气丹、灵液化元丹、生生造化丹、培元延寿丹、紫府涤魂丸、清心破障丹、血煞狂暴散等；
  - 三阶·宝品（金丹期，14颗）：降尘丹、结金真丹、辟劫玉髓丹、九转凝灵丹、金元纯阳丹、三转还魂丹、甲子长青丹、太乙凝魂丹、赤阳融煞丹等；
  - 四阶·极品（元婴期，13颗）：破婴化神丹、九幽破障丹、元婴聚顶圣丹、紫府化灵天丹、涅槃再生丹、万寿延年宝丹、太虚涤神丹、补天涤灵丹、纯阳净体金丹、天罡焚血金丹等；
  - 五阶·仙品（化神期，10颗）：太虚造化圣丹、九转飞升金丹、鸿蒙太清丹、混沌一气神丹、造化还天仙丹、天地同寿金丹、大罗开悟天丹、混沌补天圣丹、太初无垢仙丹、无极逆天狂神丹。
- **八大功能流派**：
  1. `breakthrough`（突破破境）
  2. `cultivation`（修为进境）
  3. `recovery`（气血/真元回复）
  4. `lifespan`（延寿益算）
  5. `soul_purity`（神魂淬炼/心魔抵抗）
  6. `root_purify`（灵根吸收效率洗炼）
  7. `detox`（涤毒清髓）
  8. `combat_buff`（斗法狂暴爆发）
- **零虚构材料保障**：61 种丹方所使用的全部药材与灵材，100% 在 `MATERIAL_CATALOG` 中严格校验存在。

### 2.2 耐药衰减软上限算法 (`core/market.py`)
- 废弃原先的硬错误拦截，引入科学耐药衰减模型：
  ```python
  if current_intake < max_life_intake:
      efficiency = 1.0
  else:
      over = current_intake - max_life_intake + 1
      efficiency = max(min_decay_floor, round(1.0 - over * decay_rate, 2))
  ```
- 药力超限时提示：`【耐药渐生】此丹本世已服食 x 次，肉身经脉渐生抗性，药力发挥 xx%（软上限衰减中，最低保底 xx%）。`
- 丹药永不沦为废物品，玩家在极限状态下仍可享受保底滋养。
- 若服用带有闭关加成的丹药且前一丹药加成未消耗（`user.pill_exp_mult > 0`），拦截并提示先行闭关吐纳，防止无序重叠滥用。

### 2.3 丹毒累加与天劫反噬 (`core/models.py`, `core/breakthrough.py`)
- 角色模型扩展 `pill_toxicity`、`pill_intake_counts`、`pill_breakthrough_prep`、`pill_combat_buffs` 四大核心字段。
- 服用有毒丹药时累积 `pill_toxicity`。
- 大境界天劫渡劫判定时，若 `pill_toxicity > 20`，超出部分腐蚀经脉，最高削减 30% 突破成功率（`toxicity_penalty = min(0.30, (toxicity - 20) * 0.005)`）。
- 服用辟毒散、清心破障丹、纯阳净体金丹、太初无垢仙丹等可洗涤丹毒。

### 2.4 造化神炉丹药回炉分解 (`core/alchemy.py`)
- 新增 `recycle_pill(c: Character, pill_name: str, qty: int = 1) -> Dict[str, Any]`。
- 将耐药封顶或闲置丹药投入丹炉回炉分解：
  - 100% 返还基准价 50% 灵石；
  - 50% 概率萃取提炼出相应品阶的纯净药引灵砂（如灰岩灵砂、轻灵砂、庚金砂、纯阳玉髓、天道造化神水）；
  - 形成「炼丹 → 服用/封顶 → 回炉萃取灵石与灵砂 → 再炼高级丹」的完整正向闭环。

---

## 3. 验收与回归验证 (Verification)

1. **新测例覆盖 (`tests/test_pills_catalog.py`)**：
   - `test_pill_catalog_integrity`: 61 种丹药、61 种丹方、双键索引、8 大流派、5 大品阶元数据校验全部通过；
   - `test_pill_recipes_materials_integrity`: 100% 丹方素材真实性校验通过；
   - `test_pill_resistance_decay_soft_cap`: 软上限衰减梯次验证（100% -> 50% -> 20% 保底），连续服药不抛错；
   - `test_pill_toxicity_accumulation_and_detox`: 丹毒累加与涤毒归零校验通过；
   - `test_breakthrough_prep_and_toxicity_penalty`: 破境蓄力与高丹毒天劫扣减机制校验通过；
   - `test_pill_multi_stream_effects`: 灵根洗炼、神识淬炼、回春、狂暴战力各流派生效校验通过；
   - `test_pill_recycle_closed_loop`: 丹药回炉扣减、灵石返还与药引灵砂产出全流程通过。
2. **全局关联回归 (`pytest`)**：
   - 33 项核心回归测试（装备大目录、闭关加成、宝图神兵灵丹流、坊市寄售）全部 100% 通过（耗时 80.81s）。
