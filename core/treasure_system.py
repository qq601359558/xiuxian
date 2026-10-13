"""
Core-V2 新一代探险与藏宝系统 (Treasure & Adventure Engine V2)
涵盖：实体藏宝图生成、精准空间节点校验、五行天机阵解谜、凶地守护伏击、
世界疤痕环境异变、以及跑团 DM 级自由语（/做）裁决与 Fail Forward（向前失败）机制。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import ITEM_CATALOG
from core.models import Character, CharacterStatus
from core.items import ItemEntity, ItemKind, ItemFactory
from core.world_grid import WorldGridEngine, EnvironmentState
from core.combat import CombatEngine


class TreasureArchetype:
    COMBAT = "combat"                    # 凶地守护 / 邪修伏击
    ELEMENT_PUZZLE = "element_puzzle"    # 五行生克阵盘解谜
    RUIN_HAZARD = "ruin_hazard"          # 地渊坍塌 / 绝地涉险


class TreasureEngine:
    """新一代探险与藏宝裁决引擎"""

    @staticmethod
    def generate_treasure_map(
        c: Optional[Character] = None,
        tier: int = 2,
        preferred_target: Optional[str] = None,
    ) -> ItemEntity:
        """根据当前世界图谱，生成一张独一无二的实体藏宝图"""
        nodes = WorldGridEngine.list_nodes()
        # 尽量选择非安全区或距离较远的节点
        candidates = [n for n in nodes if not n.is_safe] or nodes
        if c:
            curr_node = WorldGridEngine.get_node(c.location)
            if curr_node and len(candidates) > 1:
                candidates = [n for n in candidates if n.id != curr_node.id]

        target_node = None
        if preferred_target:
            target_node = WorldGridEngine.get_node(preferred_target)
        if not target_node:
            target_node = random.choice(candidates)

        archetype = random.choice([
            TreasureArchetype.ELEMENT_PUZZLE,
            TreasureArchetype.COMBAT,
            TreasureArchetype.RUIN_HAZARD,
        ])

        riddles = {
            TreasureArchetype.ELEMENT_PUZZLE: (
                f"五行倒悬，阴阳同炉。阵眼匿于【{target_node.base_name}】灵穴最深处，"
                f"非晓生克之道者不可启。"
            ),
            TreasureArchetype.COMBAT: (
                f"剑冢埋骨，大妖盘踞。有古修坐化遗蜕于【{target_node.base_name}】，"
                f"煞气冲天，唯利刃方可破关。"
            ),
            TreasureArchetype.RUIN_HAZARD: (
                f"残垣断壁，地脉震颤。【{target_node.base_name}】地底有前朝残殿，"
                f"贪得无厌者恐遭幽闭长眠之祸。"
            ),
        }

        riddle = riddles.get(archetype, f"天道幽微，机缘隐现于【{target_node.base_name}】。")

        return ItemFactory.create_treasure_map(
            target_node_id=target_node.id,
            target_node_name=target_node.base_name,
            tier=tier,
            archetype=archetype,
            riddle=riddle,
            lore=f"此图自【{target_node.region}】风水脉络截取而出，纸帛上隐现星斗暗芒。",
        )

    @staticmethod
    def read_map(c: Character, map_query: Optional[str] = None) -> Dict[str, Any]:
        """查阅手中的实体藏宝图"""
        # 优先在 items 检索
        tmap = None
        maps = c.find_items_by_kind(ItemKind.TREASURE_MAP)
        if maps:
            if map_query:
                tmap = c.find_item(map_query)
            if not tmap:
                tmap = maps[0]

        # 兼容旧 inventory 中的字符串
        if not tmap and "藏宝图" in c.inventory:
            # 自动升级为实体藏宝图
            tmap = TreasureEngine.generate_treasure_map(c, tier=2)
            c.add_item_entity(tmap)
            # 移除旧字符串
            if "藏宝图" in c.inventory:
                c.inventory.remove("藏宝图")

        if not tmap:
            return {
                "success": False,
                "message": "行囊中并无藏宝图。可外出探险寻获或在坊市寄售购入。",
            }

        curr_node = WorldGridEngine.get_node(c.location)
        target_id = tmap.custom_metadata.get("target_node_id", "")
        target_node = WorldGridEngine.get_node(target_id)
        target_name = target_node.base_name if target_node else "未知秘境"

        distance_info = ""
        if curr_node and target_node:
            if curr_node.id == target_node.id:
                distance_info = "\n【勘测感应】你已身处宝图所指绝地！立即执行 /挖宝 开启勘探！"
            else:
                dist = WorldGridEngine.calculate_distance(curr_node.id, target_node.id)
                path = WorldGridEngine.find_shortest_hops(curr_node.id, target_node.id)
                hops = (len(path) - 1) if path else dist
                distance_info = (
                    f"\n【罗盘导引】当前位于【{curr_node.base_name}】，距宝藏地约 {hops} 处路程。"
                    f"请先 /前往 {target_name}。"
                )
        elif target_node:
            distance_info = f"\n【罗盘导引】宝图所示机缘深藏于【{target_name}】。请先 /前往 {target_name}。"


        return {
            "success": True,
            "item": tmap,
            "message": f"{tmap.format_tooltip()}{distance_info}",
        }

    @staticmethod
    def dig(
        c: Character,
        now: Optional[float] = None,
        choice_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在当前地点执行挖宝 / 勘探"""
        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，无力挖宝。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关打坐中不可勘探，请先 /出关。"}

        # 获取玩家身上的藏宝图
        maps = c.find_items_by_kind(ItemKind.TREASURE_MAP)
        tmap = maps[0] if maps else None

        # 兼容旧背包
        if not tmap and "藏宝图" in c.inventory:
            tmap = TreasureEngine.generate_treasure_map(c, tier=2)
            c.add_item_entity(tmap)
            if "藏宝图" in c.inventory:
                c.inventory.remove("藏宝图")

        if not tmap:
            return {"success": False, "message": "行囊中无藏宝图，无法勘探天机。"}

        curr_node = WorldGridEngine.get_node(c.location)
        target_id = tmap.custom_metadata.get("target_node_id", "")
        target_node = WorldGridEngine.get_node(target_id)

        # 核心校验：必须到达目标空间节点！
        if not curr_node or not target_node or curr_node.id != target_node.id:
            target_name = target_node.base_name if target_node else "未知"
            hops = 2
            if curr_node and target_node:
                path = WorldGridEngine.find_shortest_hops(curr_node.id, target_node.id)
                hops = (len(path) - 1) if path else 2
            return {
                "success": False,
                "wrong_location": True,
                "message": (
                    f"【罗盘狂颤】此地风水为【{curr_node.base_name if curr_node else c.location}】，"
                    f"与图中所指天机大相径庭！\n宝图暗指：【{target_name}】（相距约 {hops} 站路程）。"
                    f"请先 /前往 {target_name}，宝图未受损耗。"
                ),
            }

        # 玩家已在正确地点！进入对应玩法原型
        archetype = tmap.custom_metadata.get("archetype", TreasureArchetype.ELEMENT_PUZZLE)
        tier = tmap.tier

        # ==========================================
        # 原型 A：五行生克阵盘 (Element Puzzle)
        # ==========================================
        if archetype == TreasureArchetype.ELEMENT_PUZZLE:
            if not choice_id:
                return {
                    "success": True,
                    "need_choice": True,
                    "archetype": archetype,
                    "message": (
                        f"【古阵现世 · 五行天机】\n"
                        f"在【{target_node.base_name}】地底掘出一座青铜古门，门上嵌有流转阵盘：\n"
                        f"阵眼异象：【离火炽盛（火 80）】，玄水枯竭，暴烈火煞封死石门！\n"
                        f"----------------------------------------\n"
                        f"请选择破阵策略：\n"
                        f"1. 【以水克火】调运水系法宝或消耗水灵石，调和五行（巧破）\n"
                        f"2. 【蛮力强轰】祭出本命灵器强行破阵（耗损部分灵石与丹药）\n"
                        f"3. 【自由破局】输入 /做 <你的奇谋骚操作> 进行即兴破阵\n"
                        f"（输入 /挖宝 1 或 /挖宝 2 选择）"
                    ),
                }

            if choice_id == "3":
                return {
                    "success": False,
                    "message": "自由破局请直接输入：/做 <你的操作>，宝图未受损耗。",
                }

            if choice_id not in ("1", "2"):
                return {
                    "success": False,
                    "message": f"无效选项：{choice_id}。请输入 /挖宝 1 或 /挖宝 2，或输入 /做 <自由操作>。宝图未受损耗。",
                }

            # 仅在合法选项时消耗宝图
            c.remove_item_entity(tmap.uid)

            if choice_id == "1":
                # 巧破五行
                exp_gain = 120 + tier * 50
                stones_gain = 200 + tier * 80
                c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)
                c.spirit_stones += stones_gain
                drop_pill = ItemFactory.from_legacy_name("玄元聚气丹")
                c.add_item_entity(drop_pill)

                return {
                    "success": True,
                    "outcome": "perfect_solve",
                    "message": (
                        f"【妙算破阵 · 完好启封】\n"
                        f"你运起柔水法诀引动清泉注入生门，水火相济，阵纹白光一闪轰然洞开！\n"
                        f"洞内古修遗藏完好无损：修为 +{exp_gain}，灵石 +{stones_gain}，"
                        f"另收得极品【{drop_pill.display_name}】！"
                    ),
                }
            elif choice_id == "2":
                # 蛮力强攻
                loss_stones = 40
                exp_gain = 80 + tier * 30
                c.spirit_stones = max(0, c.spirit_stones - loss_stones)
                c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)
                # 蛮力轰击留下轻微震荡
                return {
                    "success": True,
                    "outcome": "brute_force",
                    "message": (
                        f"【蛮力轰门 · 震碎偏殿】\n"
                        f"你运起周身真力强行轰击阵眼，石门崩碎，但剧烈爆炸震毁了内部丹药！\n"
                        f"受反震损耗灵石 {loss_stones}，搜刮残余古卷得修为 +{exp_gain}。"
                    ),
                }


        # ==========================================
        # 原型 B：凶地守护与伏击 (Combat Ambush)
        # ==========================================
        elif archetype == TreasureArchetype.COMBAT:
            # 消耗宝图
            c.remove_item_entity(tmap.uid)

            # 战力检定
            player_power = CombatEngine.calculate_power(c)
            guardian_power = 60.0 + tier * 45.0

            if player_power >= guardian_power * 0.85:
                # 击杀守卫大胜
                exp_gain = 150 + tier * 60
                stones_gain = 300 + tier * 100
                c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)
                c.spirit_stones += stones_gain
                drop_weapon = ItemFactory.create_equip(
                    name="断魂幽煞剑",
                    tier=tier,
                    slot="weapon",
                    base_power=35.0,
                    lore="洞府守墓傀儡手中握着的古老战刃，煞气未消。",
                )
                c.add_item_entity(drop_weapon)
                return {
                    "success": True,
                    "outcome": "combat_victory",
                    "message": (
                        f"【剑荡妖氛 · 怒斩守卫】\n"
                        f"推开石棺，守墓巨傀狂啸扑出！你剑若奔雷，数合之内将其斩首！\n"
                        f"缴获战利：修为 +{exp_gain}，灵石 +{stones_gain}，"
                        f"缴获法宝【{drop_weapon.display_name}】！"
                    ),
                }
            else:
                # 负伤苦战逃遁
                c.lifespan.burn_lifespan(0.5)
                return {
                    "success": True,
                    "outcome": "combat_defeat",
                    "message": (
                        f"【凶煞噬体 · 败走遁出】\n"
                        f"守墓傀儡战力狂暴（战力约 {int(guardian_power)}），你护体罡气受创，"
                        f"燃寿 0.5 岁施展血遁脱险，所幸留得一命！"
                    ),
                }

        # ==========================================
        # 原型 C：地渊残迹与世界疤痕 (Ruin Hazard & Scars)
        # ==========================================
        elif archetype == TreasureArchetype.RUIN_HAZARD:
            # 消耗宝图
            c.remove_item_entity(tmap.uid)

            # 触发地脉引爆与世界疤痕回写！
            now_ts = time.time()
            scar = EnvironmentState(
                scar_id=f"scar_fire_{int(now_ts)}",
                scar_type="fire_sea",
                title="赤焰火海",
                hazard_desc=(
                    f"修士【{c.name}】于此掘宝时触发上古天火禁制，地脉岩浆喷涌百里！"
                ),
                caused_by=c.name,
                density_mult=0.6,
                danger_delta=0.4,
                environmental_damage=25,
                immune_item="辟火珠",
                expires_at=now_ts + 86400 * 3,  # 持续 3 游戏天
            )
            WorldGridEngine.apply_scar(target_node.id, scar, broadcast=True)

            # 结算：大收获但引爆灾变
            exp_gain = 250 + tier * 80
            stones_gain = 500 + tier * 150
            c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)
            c.spirit_stones += stones_gain
            c.karma.add_sin(20)  # 引爆地脉增添业力

            ancient_relic = ItemEntity(
                name="纯阳离火印",
                kind=ItemKind.RELIC,
                tier=3,
                lineage_lore="自崩塌火海中夺得的上古纯阳法印，散发毁天灭地的灼浪。",
            )
            c.add_item_entity(ancient_relic)

            return {
                "success": True,
                "outcome": "scar_created",
                "message": (
                    f"【地脉崩裂 · 劫波动天】\n"
                    f"你拔出封印古印的一刹那，整座地宫剧烈坍塌，炽热地火冲破地脉喷涌而出！\n"
                    f"你抢得至宝飞天遁走：修为 +{exp_gain}，灵石 +{stones_gain}，"
                    f"得稀世重宝【{ancient_relic.display_name}】！\n"
                    f"【天道警示】你引爆地脉殃及生灵，业力 +20！"
                    f"【{target_node.base_name}】地貌永久异变为【赤焰火海】！"
                ),
            }

        return {"success": False, "message": "未知谜题原型。"}

    @staticmethod
    def resolve_free_action(c: Character, free_text: str) -> Dict[str, Any]:
        """AI DM 跑团级自然语言自由语破局裁决（含 Fail Forward 机制）"""
        free_text = (free_text or "").strip()
        if not free_text:
            return {"success": False, "message": "请输入具体的自由破局行动，如：/做 我祭出引雷符导入湿泥。"}

        # 获取正在挖掘的目标
        maps = c.find_items_by_kind(ItemKind.TREASURE_MAP)
        tmap = maps[0] if maps else None
        if not tmap:
            return {"success": False, "message": "当前未在藏宝秘境中，无法执行破局动作。"}

        # 核心空间校验：玩家必须身处宝图所指的目标节点
        curr_node = WorldGridEngine.get_node(c.location)
        target_id = tmap.custom_metadata.get("target_node_id", "")
        target_node = WorldGridEngine.get_node(target_id)
        if not curr_node or not target_node or curr_node.id != target_node.id:
            target_name = target_node.base_name if target_node else "未知"
            return {
                "success": False,
                "not_at_ruin": True,
                "message": f"当前未在宝藏所在节点【{target_name}】，不可远程破局。请先前往该地执行 /挖宝。",
            }

        # 检查背包物品是否有呼应
        mentioned_items = [it for it in c.items if it.name in free_text]

        # 尝试调用 AI DM 进行意图与逻辑裁决
        ai_narrative = ""
        success_judgement = False
        try:
            from ai.gateway import ai_ready, _chat_json
            if ai_ready():
                prompt = (
                    f"你是一位严谨而富于戏剧张力的修仙跑团地下城主(DM)。\n"
                    f"玩家：{c.name}（境界：{c.realm.name}，战力：{int(CombatEngine.calculate_power(c))}）\n"
                    f"当前情境：正在破解上古藏宝图洞府禁制。\n"
                    f"玩家即兴行动：“{free_text}”\n"
                    f"玩家背包真实拥有的呼应物品：{[it.name for it in mentioned_items] or '无特定匹配'}\n"
                    "请根据修仙逻辑、物理常理与机智程度进行裁决。\n"
                    "输出严格 JSON：\n"
                    "{\"success\": bool, \"clever_score\": int (1-10), "
                    "\"narrative\": \"80-160字生动叙事描述结果\", "
                    "\"fail_forward\": bool (若失败，是否因祸得福跌入隐藏密室)}"
                )
                res = _chat_json(prompt)
                if isinstance(res, dict) and "narrative" in res:
                    ai_narrative = res.get("narrative", "")
                    success_judgement = bool(res.get("success", False))
        except Exception:
            ai_narrative = ""

        # 消耗宝图
        c.remove_item_entity(tmap.uid)


        # 规则保底判定：如果 AI 没连通，根据字数与物品进行常理判定
        if not ai_narrative:
            if mentioned_items or any(w in free_text for w in ("水", "火", "阵", "符", "雷", "灵石", "引")):
                success_judgement = True
                ai_narrative = (
                    f"{c.name}心念电转，施展奇计：“{free_text[:40]}”。"
                    f"天地灵机随巧思应声而变，阵眼逆转，石门轰然洞开，令人拍案叫绝！"
                )
            else:
                success_judgement = False
                is_fail_forward = True
                ai_narrative = (
                    f"{c.name}试图以奇术破局，不料引动禁制反弹，脚下石阶坍塌坠入深渊。"
                    f"然而烟尘散去，暗室石壁上竟刻着前人遗留的绝学真意！"
                )

        if success_judgement:
            exp = 200
            stones = 350
            c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp)
            c.spirit_stones += stones
            c.karma.dao_heart = min(100, c.karma.dao_heart + 5)
            reward_item = ItemFactory.create_equip(
                name="太虚流云履", tier=2, slot="armor", lore="奇谋破阵得大能赏识所留宝履。"
            )
            c.add_item_entity(reward_item)
            return {
                "success": True,
                "outcome": "free_action_success",
                "narrative": ai_narrative,
                "message": (
                    f"【天道裁决 · 奇谋破关】\n{ai_narrative}\n"
                    f"落账收益：修为 +{exp}，灵石 +{stones}，道心 +5，"
                    f"获赐法宝【{reward_item.display_name}】！"
                ),
            }
        else:
            # 向前失败（Fail Forward）：虽败犹荣，获得隐藏机缘！
            loss_exp = 20
            c.realm.current_exp = max(0, c.realm.current_exp - loss_exp)
            hidden_pill = ItemFactory.from_legacy_name("九转培元丹")
            c.add_item_entity(hidden_pill)
            return {
                "success": True,
                "outcome": "fail_forward",
                "narrative": ai_narrative,
                "message": (
                    f"【天道反转 · 因祸得福（Fail Forward）】\n{ai_narrative}\n"
                    f"虽被反噬震伤修为 -{loss_exp}，却在密室暗格拾得上古遗丹【{hidden_pill.display_name}】！"
                ),
            }
