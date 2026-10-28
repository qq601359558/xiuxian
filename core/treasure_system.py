"""
Core-V2 新一代探险与藏宝系统 (Treasure & Adventure Engine V2)
涵盖：实体藏宝图生成、精准空间节点校验、五行天机阵解谜、凶地守护伏击、
世界疤痕环境异变、以及跑团 DM 级自由语（/做）裁决与 Fail Forward（向前失败）机制。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import ITEM_CATALOG
from core.models import Character, CharacterStatus
from core.items import ItemEntity, ItemKind, ItemFactory
from core.world_grid import WorldGridEngine, EnvironmentState
from core.combat import CombatEngine
from core.character_integrity import CharacterIntegrity, CharacterIntegrityError


class TreasureArchetype:
    COMBAT = "combat"                    # 凶地守护 / 邪修伏击
    ELEMENT_PUZZLE = "element_puzzle"    # 五行生克阵盘解谜
    RUIN_HAZARD = "ruin_hazard"          # 地渊坍塌 / 绝地涉险


# ==============================================================================
# 八卦风水五行地脉物候典籍
# ==============================================================================
FENGSHUI_BAGUA_LORE: Dict[str, Dict[str, str]] = {
    "震位 · 正东": {
        "direction_cn": "正东",
        "beast": "青龙",
        "element": "木",
        "rhyme": "东荒气象发青阳，木德流转引灵光。",
        "clue": "罗盘天池金针颤颤指东，苍莽古木与海天生机相连。此地绝非藏真之所，当循东方朝阳升起之方、生机盎然之处寻觅。",
    },
    "艮位 · 东北": {
        "direction_cn": "东北",
        "beast": "苍岩",
        "element": "土",
        "rhyme": "重峦叠嶂连幽谷，艮岳峥嵘掩仙窟。",
        "clue": "指针偏向东北艮山之位，隐透厚重岩石压迫之感。宝穴匿于崇山绝岭环抱之间，当往东北苍岩叠翠之处探寻。",
    },
    "坎位 · 极北": {
        "direction_cn": "极北",
        "beast": "玄武",
        "element": "水",
        "rhyme": "玄水沉渊锁万重，朔风萧瑟掠幽峰。",
        "clue": "罗盘指针直指极北坎水之方，冰冷煞气透过针盘微凉刺骨。机缘隐于北方幽暗阴湿水泽或深渊之底，当往极北寻去。",
    },
    "乾位 · 西北": {
        "direction_cn": "西北",
        "beast": "天罡",
        "element": "金",
        "rhyme": "乾天高朗云间隐，罡风呼啸过千仞。",
        "clue": "磁针斜指西北乾位天门，高天之上隐有罡风呼啸雷音。宝藏当在西北天高云深、地势孤拔之绝顶。",
    },
    "兑位 · 正西": {
        "direction_cn": "正西",
        "beast": "白虎",
        "element": "金",
        "rhyme": "夕照残阳西岭没，金戈煞气起苍阔。",
        "clue": "天池金针直指南天西垂落日方位，带有一股冷冽兵戈肃杀之气。当往极西杀伐险地、残阳落日之处摸索。",
    },
    "坤位 · 西南": {
        "direction_cn": "西南",
        "beast": "厚地",
        "element": "土",
        "rhyme": "厚土载物藏幽室，地气回环锁金石。",
        "clue": "指针偏向西南坤地，地脉脉动沉稳凝重。机缘深埋于西南方大地深处或古修陵寝地脉，当往西南探幽。",
    },
    "离位 · 正南": {
        "direction_cn": "正南",
        "beast": "朱雀",
        "element": "火",
        "rhyme": "南明离火耀长空，赤霞漫卷落仙宗。",
        "clue": "罗盘金针震颤指向南明午位，隐隐泛起一股温润灼热之意。宝图所示机缘当在南方热气升腾、霞光蒸蔚之地。",
    },
    "巽位 · 东南": {
        "direction_cn": "东南",
        "beast": "巽风",
        "element": "木",
        "rhyme": "烟波浩渺大泽东，巽风卷浪隐仙宫。",
        "clue": "指针斜指东南巽风之位，似有水泽波涛与长风浩荡之感。当向东南烟雨浩渺、水陆交界之方探访。",
    },
}


def calculate_fengshui_direction(curr_node: Any, target_node: Any) -> Dict[str, Any]:
    """根据两个节点的拓扑相对坐标计算八卦方位与风水气象"""
    c1 = getattr(curr_node, "coordinates", (0, 0)) if curr_node else (0, 0)
    c2 = getattr(target_node, "coordinates", (0, 0)) if target_node else (0, 0)
    dx = c2[0] - c1[0]
    dy = c2[1] - c1[1]

    if dx == 0 and dy == 0:
        return {
            "bagua": "中宫 · 龙穴",
            "direction_cn": "同穴",
            "beast": "黄龙",
            "element": "土",
            "rhyme": "真龙盘踞正中宫，天地灵机此际融。",
            "clue": "定盘天池金针静止不动，宝穴已在此山此水之间！",
            "dx": 0,
            "dy": 0,
        }

    # 角度计算 (0~360 度，0度为正东，90度为正北，180度为正西，270度为正南)
    deg = (math.degrees(math.atan2(dy, dx)) + 360) % 360

    if deg >= 337.5 or deg < 22.5:
        key = "震位 · 正东"
    elif 22.5 <= deg < 67.5:
        key = "艮位 · 东北"
    elif 67.5 <= deg < 112.5:
        key = "坎位 · 极北"
    elif 112.5 <= deg < 157.5:
        key = "乾位 · 西北"
    elif 157.5 <= deg < 202.5:
        key = "兑位 · 正西"
    elif 202.5 <= deg < 247.5:
        key = "坤位 · 西南"
    elif 247.5 <= deg < 292.5:
        key = "离位 · 正南"
    else:
        key = "巽位 · 东南"

    lore = FENGSHUI_BAGUA_LORE[key]
    return {
        "bagua": key,
        "direction_cn": lore["direction_cn"],
        "beast": lore["beast"],
        "element": lore["element"],
        "rhyme": lore["rhyme"],
        "clue": lore["clue"],
        "dx": dx,
        "dy": dy,
    }


class TreasureEngine:
    """新一代探险与藏宝裁决引擎"""

    @staticmethod
    def generate_treasure_map(
        c: Optional[Character] = None,
        tier: int = 2,
        preferred_target: Optional[str] = None,
        preferred_archetype: Optional[TreasureArchetype] = None,
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

        archetype = preferred_archetype or random.choice([
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
    def get_directional_guide(
        c: Character,
        tmap: ItemEntity,
        curr_node: Optional[Any],
        target_node: Optional[Any],
    ) -> Dict[str, Any]:
        """双轨制生成文言方位寻龙指引（AI 意境推演 + 八卦算经模板保底）"""
        target_name = target_node.base_name if target_node else "未知秘境"
        curr_name = curr_node.base_name if curr_node else (getattr(c, "location", "") or "红尘旷野")

        fengshui = calculate_fengshui_direction(curr_node, target_node)
        bagua = fengshui["bagua"]
        rhyme = fengshui["rhyme"]
        clue = fengshui["clue"]

        # 计算跳数与距离描述
        hops = 2
        if curr_node and target_node:
            path = WorldGridEngine.find_shortest_hops(curr_node.id, target_node.id)
            if path:
                hops = max(1, len(path) - 1)
            else:
                hops = max(1, WorldGridEngine.calculate_distance(curr_node.id, target_node.id))

        if hops == 1:
            dist_desc = "灵息浓烈，相隔约一舍之路（近在邻山）"
        elif hops in (2, 3):
            dist_desc = f"关山重重，约莫相距 {hops} 重山水"
        else:
            dist_desc = f"山高水远，相隔大荒 {hops} 站之遥"

        ai_poetry = ""
        ai_clue = ""
        try:
            from ai.gateway import ai_ready, _chat_json
            if ai_ready():
                prompt = (
                    "你是一位通晓天机风水神数的古典修仙寻龙宗师。\n"
                    f"玩家：{c.name}（当前位于【{curr_name}】）\n"
                    f"藏宝图目标地：【{target_name}】（请勿在文本中直接剧透死板地名，用山水物候朦胧点拨）\n"
                    f"相对八卦方位：【{bagua}】\n"
                    f"大致距离气机：【{dist_desc}】\n"
                    "请输出纯 JSON，包含：\n"
                    "\"poetry\": \"一句七言绝句风水谶语判词\",\n"
                    "\"clue\": \"60~100字古典优美、意境悠远的文言风水寻龙指引，依卦象为道友指出大致方位与物候特征，语带天机\"\n"
                )
                res = _chat_json(prompt, timeout=6.0)
                if isinstance(res, dict) and res.get("clue"):
                    ai_clue = str(res.get("clue")).strip()
                    if res.get("poetry"):
                        ai_poetry = str(res.get("poetry")).strip()
        except Exception:
            pass

        final_rhyme = ai_poetry or rhyme
        final_clue = ai_clue or clue

        full_text = (
            f"【天机定盘 · 寻龙点穴】\n"
            f"方位卦象：【{bagua}】（{dist_desc}）\n"
            f"谶语判词：『{final_rhyme}』\n"
            f"风水感应：{final_clue}\n"
            f"天道提点：此地乃【{curr_name}】，非宝图真穴。道友可御风向【{target_name}】方向动身，宝图未受损耗。"
        )

        return {
            "bagua": bagua,
            "direction_cn": fengshui["direction_cn"],
            "hops": hops,
            "dist_desc": dist_desc,
            "rhyme": final_rhyme,
            "clue": final_clue,
            "target_node_name": target_name,
            "full_text": full_text,
        }

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
                distance_info = "\n\n【勘测感应】天池金针归位，神芒冲天！你已身处宝图所指绝地！立即执行 /挖宝 破阵开匣！"
            else:
                guide = TreasureEngine.get_directional_guide(c, tmap, curr_node, target_node)
                distance_info = f"\n\n{guide.get('full_text')}"
        elif target_node:
            distance_info = f"\n\n【天机未测】宝图所示机缘深藏于【{target_name}】。请先动身前往。"

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
        try:
            CharacterIntegrity.assert_alive(c, now=t)
            CharacterIntegrity.assert_idle(c, action="/挖宝")
            CharacterIntegrity.assert_bag_space(c, needed_slots=1)
        except CharacterIntegrityError as e:
            return {"success": False, "message": str(e)}

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
            guide = TreasureEngine.get_directional_guide(c, tmap, curr_node, target_node)
            target_name = target_node.base_name if target_node else "未知"
            hops = guide.get("hops", 2)
            return {
                "success": False,
                "wrong_location": True,
                "target_node_name": target_name,
                "target_node_id": target_node.id if target_node else "",
                "bagua": guide.get("bagua", ""),
                "direction_text": guide.get("clue", ""),
                "message": guide.get("full_text"),
            }

        # 玩家已在正确地点！进入对应玩法原型
        archetype = tmap.custom_metadata.get("archetype", TreasureArchetype.ELEMENT_PUZZLE)
        tier = tmap.tier

        # 若纳戒已满（64/64），破除古阵将掘出神兵仙药，提前拦截避免爆仓丢宝
        if choice_id and hasattr(c, "is_bag_full") and c.is_bag_full():
            max_slots = getattr(c, "MAX_BAG_SLOTS", 64)
            return {
                "success": False,
                "message": f"百宝纳戒乾坤已满（{len(getattr(c, 'items', []))}/{max_slots}），破阵开匣将掘出古修神兵与仙药，请先腾挪纳戒空间再行破阵！",
            }

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

            choice_str = str(choice_id).strip().lower() if choice_id else ""
            if choice_str == "3":
                return {
                    "success": False,
                    "message": "自由破局请直接输入：/做 <你的操作>，宝图未受损耗。",
                }

            if choice_str not in ("1", "water", "earth", "巧破", "2", "force", "brute", "蛮力"):
                return {
                    "success": False,
                    "message": f"无效选项：{choice_id}。请输入 /挖宝 1（以水克火）或 /挖宝 2（蛮力轰门），或输入 /做 <自由操作>。宝图未受损耗。",
                }

            # 仅在合法选项时消耗宝图
            c.remove_item_entity(tmap.uid)

            if choice_str in ("1", "water", "earth", "巧破"):
                # 巧破五行
                exp_gain = 120 + tier * 50
                stones_gain = 200 + tier * 80
                c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)
                c.spirit_stones += stones_gain

                # 服务端权威生成高阶神兵与极品仙丹
                equip_tier = max(2, min(5, tier))
                weapon_pool = {
                    1: ["青锋剑", "玄铁剑"],
                    2: ["玄铁剑", "赤霄剑"],
                    3: ["斩龙古剑", "太乙玄天戈", "七星诛魔剑", "赤霄惊神刃"],
                    4: ["斩龙古剑", "太乙玄天戈", "七星诛魔剑", "赤霄惊神刃"],
                    5: ["斩仙神剑", "太乙玄天戈", "混元斩龙刃"],
                }
                candidates = weapon_pool.get(equip_tier, ["斩龙古剑", "太乙玄天戈", "七星诛魔剑", "赤霄惊神刃"])
                pick_weapon_name = random.choice(candidates)

                drop_weapon = ItemFactory.create_equip(
                    name=pick_weapon_name,
                    tier=equip_tier,
                    slot="weapon",
                    base_power=30.0 * equip_tier,
                    lore=f"自【{target_node.base_name if target_node else '古修秘境'}】上古洞府密室石棺中发掘而出的古仙神兵，锋芒毕露，隐隐有龙吟破空之声。",
                    affix_count=2,
                )
                c.add_item_entity(drop_weapon)

                pill_name = "九转还魂真丹" if equip_tier >= 3 else "玄元聚气丹"
                drop_pill = ItemEntity.create(
                    name=pill_name,
                    kind=ItemKind.PILL,
                    quality=equip_tier,
                    description="上古秘藏中保存完好的绝品仙丹，服用可大补元气并辟除心魔火煞。" if pill_name == "九转还魂真丹" else "温养周天经脉的玄门正宗凝气灵丹。"
                )
                c.add_item_entity(drop_pill)

                return {
                    "success": True,
                    "outcome": "perfect_solve",
                    "equipment": {
                        "uid": drop_weapon.uid,
                        "name": drop_weapon.name,
                        "kind": drop_weapon.kind.value,
                        "tier": drop_weapon.tier,
                        "tierName": drop_weapon.tier_name,
                        "slot": drop_weapon.slot,
                        "slotCn": "绝世法宝",
                        "stats": drop_weapon.stats,
                        "affixes": [{"name": a.name, "desc": a.desc} for a in drop_weapon.affixes],
                        "lore": drop_weapon.lineage_lore,
                    },
                    "pill": {
                        "uid": drop_pill.uid,
                        "name": drop_pill.name,
                        "kind": drop_pill.kind.value,
                        "tier": drop_pill.tier,
                        "tierName": drop_pill.tier_name,
                    },
                    "stone_gain": stones_gain,
                    "message": (
                        f"【妙算破阵 · 完好启封】\n"
                        f"你运起柔水法诀引动清泉注入生门，水火相济，阵纹白光一闪轰然洞开！\n"
                        f"洞内古修遗藏完好无损：修为 +{exp_gain}，灵石 +{stones_gain}，\n"
                        f"掘得绝品神兵【{drop_weapon.display_name}】与【{drop_pill.display_name}】！\n"
                        f"战利品已妥善纳归百宝纳戒。"
                    ),
                }
            elif choice_str in ("2", "force", "brute", "蛮力"):
                # 蛮力强攻
                loss_stones = 40
                exp_gain = 80 + tier * 30
                c.spirit_stones = max(0, c.spirit_stones - loss_stones)
                c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + exp_gain)

                equip_tier = max(1, tier - 1)
                drop_weapon = ItemFactory.create_equip(
                    name="残铁古剑",
                    tier=equip_tier,
                    slot="weapon",
                    base_power=20.0 * equip_tier,
                    lore="在蛮力轰击中幸存的残损古刃，剑身虽有裂痕，依旧留存微弱法光。",
                    affix_count=1,
                )
                c.add_item_entity(drop_weapon)

                return {
                    "success": True,
                    "outcome": "brute_force",
                    "equipment": {
                        "uid": drop_weapon.uid,
                        "name": drop_weapon.name,
                        "kind": drop_weapon.kind.value,
                        "tier": drop_weapon.tier,
                        "tierName": drop_weapon.tier_name,
                        "slot": drop_weapon.slot,
                        "slotCn": "绝世法宝",
                        "stats": drop_weapon.stats,
                        "affixes": [{"name": a.name, "desc": a.desc} for a in drop_weapon.affixes],
                        "lore": drop_weapon.lineage_lore,
                    },
                    "message": (
                        f"【蛮力轰门 · 震碎偏殿】\n"
                        f"你运起周身真力强行轰击阵眼，石门崩碎，剧烈爆炸震毁了内部丹药！\n"
                        f"受反震损耗灵石 {loss_stones}，搜刮残余洞室得修为 +{exp_gain}，"
                        f"抢救出残损法宝【{drop_weapon.display_name}】入纳戒。"
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
                    "equipment": {
                        "uid": drop_weapon.uid,
                        "name": drop_weapon.name,
                        "kind": drop_weapon.kind.value,
                        "tier": drop_weapon.tier,
                        "tierName": drop_weapon.tier_name,
                        "slot": drop_weapon.slot,
                        "slotCn": "绝世法宝",
                        "stats": drop_weapon.stats,
                        "affixes": [{"name": a.name, "desc": a.desc} for a in drop_weapon.affixes],
                        "lore": drop_weapon.lineage_lore,
                    },
                    "stone_gain": stones_gain,
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
                "equipment": {
                    "uid": ancient_relic.uid,
                    "name": ancient_relic.name,
                    "kind": ancient_relic.kind.value,
                    "tier": ancient_relic.tier,
                    "tierName": ancient_relic.tier_name,
                    "slot": getattr(ancient_relic, "slot", "trinket"),
                    "slotCn": "稀世重宝",
                    "stats": getattr(ancient_relic, "stats", {}),
                    "affixes": [{"name": a.name, "desc": a.desc} for a in getattr(ancient_relic, "affixes", [])],
                    "lore": ancient_relic.lineage_lore,
                },
                "stone_gain": stones_gain,
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
