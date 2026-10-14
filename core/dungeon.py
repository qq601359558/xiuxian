"""
锁妖古窟探索与 Roguelike 秘境引擎
涵盖 9 层结构梯度、节点生成、局内道韵 3 选 1、临时储物袋与撤退/濒死结算
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from storage.db import CharacterRepository, WorldStateRepository
from core.models import Character
from core.items import ItemEntity, ItemFactory
from core.spells import (
    CombatEntity,
    SpellCombatEngine,
    create_player_entity,
    create_monster_entity,
    SPELL_CATALOG,
)


_KEY = "dungeon_sessions"

# ==============================================================================
# 9 层妖兽与守关魔尊配置表
# ==============================================================================
DUNGEON_FLOORS: Dict[int, Dict[str, Any]] = {
    1: {
        "floor": 1,
        "name": "锁妖古窟 · 幽暗外穴",
        "tier_name": "炼气期试炼",
        "min_tier": 1,
        "monsters": [
            {"name": "嗜血妖狼", "base_hp": 90, "base_atk": 18, "base_def": 4, "tier": 1},
            {"name": "阴煞黑鸦", "base_hp": 80, "base_atk": 22, "base_def": 3, "tier": 1},
        ],
        "boss": {"name": "双头赤眼狼王", "base_hp": 160, "base_atk": 30, "base_def": 8, "tier": 1, "shield": 30},
    },
    2: {
        "floor": 2,
        "name": "锁妖古窟 · 赤岩裂谷",
        "tier_name": "炼气圆满 / 准筑基",
        "min_tier": 1,
        "monsters": [
            {"name": "赤磷火蟒", "base_hp": 140, "base_atk": 28, "base_def": 8, "tier": 1},
            {"name": "地穴岩蛛", "base_hp": 130, "base_atk": 26, "base_def": 12, "tier": 1, "shield": 30},
        ],
        "boss": {"name": "六足金背蜈蚣", "base_hp": 220, "base_atk": 38, "base_def": 14, "tier": 1, "shield": 50},
    },
    3: {
        "floor": 3,
        "name": "锁妖古窟 · 煞骨灵冢",
        "tier_name": "筑基初期守关层",
        "min_tier": 1,
        "monsters": [
            {"name": "白骨尸卫", "base_hp": 180, "base_atk": 35, "base_def": 15, "tier": 2, "shield": 40},
            {"name": "幽冥鬼面蝠", "base_hp": 160, "base_atk": 40, "base_def": 10, "tier": 2},
        ],
        "boss": {"name": "【守关妖王】六翼阴煞骨雕", "base_hp": 340, "base_atk": 52, "base_def": 22, "tier": 2, "shield": 80},
    },
    4: {
        "floor": 4,
        "name": "锁妖古窟 · 万毒渊薮",
        "tier_name": "筑基中期深探",
        "min_tier": 2,
        "monsters": [
            {"name": "碧磷五毒蜥", "base_hp": 240, "base_atk": 48, "base_def": 20, "tier": 2, "shield": 50},
            {"name": "幻雾妖蝶", "base_hp": 220, "base_atk": 55, "base_def": 15, "tier": 2},
        ],
        "boss": {"name": "千年冰甲玄龟", "base_hp": 450, "base_atk": 50, "base_def": 38, "tier": 2, "shield": 120},
    },
    5: {
        "floor": 5,
        "name": "锁妖古窟 · 焚天炎池",
        "tier_name": "筑基后期搏杀",
        "min_tier": 2,
        "monsters": [
            {"name": "熔岩赤炎兽", "base_hp": 320, "base_atk": 65, "base_def": 25, "tier": 2, "shield": 60},
            {"name": "地煞火魅", "base_hp": 280, "base_atk": 75, "base_def": 18, "tier": 2},
        ],
        "boss": {"name": "裂地赤火猿王", "base_hp": 560, "base_atk": 85, "base_def": 30, "tier": 2, "shield": 100},
    },
    6: {
        "floor": 6,
        "name": "锁妖古窟 · 绝阴冰窟",
        "tier_name": "结丹初期大妖关",
        "min_tier": 2,
        "monsters": [
            {"name": "玄冰魔偶", "base_hp": 380, "base_atk": 78, "base_def": 32, "tier": 3, "shield": 90},
            {"name": "极北雪灵蛇", "base_hp": 350, "base_atk": 88, "base_def": 25, "tier": 3},
        ],
        "boss": {"name": "【守关妖王】九尾幻魇狐王", "base_hp": 720, "base_atk": 110, "base_def": 40, "tier": 3, "shield": 160},
    },
    7: {
        "floor": 7,
        "name": "锁妖古窟 · 幽冥绝渊",
        "tier_name": "结丹中期凶险",
        "min_tier": 3,
        "monsters": [
            {"name": "黑水赤炼蛟", "base_hp": 520, "base_atk": 115, "base_def": 45, "tier": 3, "shield": 120},
            {"name": "幽冥巡界夜叉", "base_hp": 480, "base_atk": 125, "base_def": 38, "tier": 3},
        ],
        "boss": {"name": "三首离火毒蛟", "base_hp": 950, "base_atk": 145, "base_def": 55, "tier": 3, "shield": 200},
    },
    8: {
        "floor": 8,
        "name": "锁妖古窟 · 太古雷狱",
        "tier_name": "结丹圆满 / 准元婴",
        "min_tier": 3,
        "monsters": [
            {"name": "天青雷吼兽", "base_hp": 650, "base_atk": 140, "base_def": 50, "tier": 3, "shield": 150},
            {"name": "破虚紫电雕", "base_hp": 600, "base_atk": 160, "base_def": 42, "tier": 3},
        ],
        "boss": {"name": "太古紫霄金翅大鹏", "base_hp": 1200, "base_atk": 180, "base_def": 65, "tier": 4, "shield": 260},
    },
    9: {
        "floor": 9,
        "name": "锁妖古窟 · 封魔古殿",
        "tier_name": "元婴总魔尊决战",
        "min_tier": 3,
        "monsters": [
            {"name": "寂灭魔侍", "base_hp": 750, "base_atk": 170, "base_def": 60, "tier": 4, "shield": 180},
            {"name": "嗜灵幽魔", "base_hp": 700, "base_atk": 190, "base_def": 50, "tier": 4},
        ],
        "boss": {"name": "【镇窟总魔尊】太古裂天巨兽", "base_hp": 1800, "base_atk": 230, "base_def": 85, "tier": 4, "shield": 380},
    },
}

# ==============================================================================
# 局内道韵词条库 (Dao Boons)
# ==============================================================================
DAO_BOON_CATALOG: Dict[str, Dict[str, Any]] = {
    "pure_yang": {
        "key": "pure_yang",
        "name": "纯阳烈煞",
        "icon": "🔥",
        "desc": "火系神通伤害提升 35%，真火爆燃伤害增幅，自身基础攻击 +25%。",
    },
    "iron_wall": {
        "key": "iron_wall",
        "name": "不动如山",
        "icon": "🛡️",
        "desc": "气血上限提升 30%，厚土灵盾厚度提升 40%，且反震伤害 +10%。",
    },
    "sword_heart": {
        "key": "sword_heart",
        "name": "剑心通明",
        "icon": "⚡",
        "desc": "太乙破虚剑气倍率额外提升 40%，破盾造成额外 50% 斩击。",
    },
    "spirit_well": {
        "key": "spirit_well",
        "name": "灵泉生机",
        "icon": "🌿",
        "desc": "真元上限提升 40%，青帝长生引治疗效果提升 30%，每次施展恢复少许灵盾。",
    },
    "ice_soul": {
        "key": "ice_soul",
        "name": "玄冥冰魄",
        "icon": "❄️",
        "desc": "玄冰寒煞魄冰霜伤害提升 30%，普攻附带 20% 几率减速目标。",
    },
}


# ==============================================================================
# 内部持久化辅助函数
# ==============================================================================
def _load_all() -> Dict[str, Any]:
    return WorldStateRepository.get(_KEY) or {}


def _save_all(d: Dict[str, Any]) -> None:
    WorldStateRepository.set(_KEY, d)


# ==============================================================================
# 节点网络生成器
# ==============================================================================
def _generate_floor_nodes(floor: int) -> List[Dict[str, Any]]:
    f_info = DUNGEON_FLOORS.get(floor, DUNGEON_FLOORS[1])
    nodes = []

    # 节点 1：必为探索/小怪
    m_pool = f_info.get("monsters", [])
    m1 = random.choice(m_pool)
    nodes.append({
        "idx": 0,
        "type": "combat",
        "title": "幽暗密道 · 妖煞伏行",
        "desc": f"穿过狭窄石缝，忽闻腥风扑鼻，一头【{m1['name']}】自阴影中窜出！",
        "monster_template": m1,
        "cleared": False,
    })

    # 节点 2：机缘 / 灵泉 / 残宝遗骸
    n2_type = random.choice(["relic", "spring", "combat"])
    if n2_type == "spring":
        nodes.append({
            "idx": 1,
            "type": "spring",
            "title": "古窟造化灵泉",
            "desc": "断崖凹陷处汇聚了一汪乳白色古泉，丝丝缕缕的天地造化灵气袅袅升腾。",
            "cleared": False,
        })
    elif n2_type == "relic":
        nodes.append({
            "idx": 1,
            "type": "relic",
            "title": "陨落古修遗骸",
            "desc": "一具盘坐于青石上的古修枯骨，指骨间微光闪烁，似乎残留着上古乾坤残宝。",
            "cleared": False,
        })
    else:
        m2 = random.choice(m_pool)
        nodes.append({
            "idx": 1,
            "type": "combat",
            "title": "阴风怪石 · 凶兽巢穴",
            "desc": f"前方洞窟白骨累累，盘踞着凶悍的【{m2['name']}】！",
            "monster_template": m2,
            "cleared": False,
        })

    # 节点 3：关底妖王或强力镇关妖兽
    boss_tpl = f_info["boss"]
    nodes.append({
        "idx": 2,
        "type": "boss",
        "title": f"【本层镇关凶煞】{boss_tpl['name']}",
        "desc": f"山腹洞窟豁然开朗，滔天妖气凝聚为实质，恐怖的【{boss_tpl['name']}】正冷冷俯视着你！",
        "monster_template": boss_tpl,
        "cleared": False,
    })

    return nodes


# ==============================================================================
# 锁妖古窟探索核心引擎
# ==============================================================================
class DungeonEngine:
    """锁妖古窟探索核心引擎"""

    @classmethod
    def get_session(cls, player_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家当前禁地会话"""
        d = _load_all()
        return d.get(player_id)

    @classmethod
    def start_dungeon(cls, char: Character, floor: int = 1) -> Dict[str, Any]:
        """开启或重置古窟探索"""
        floor = max(1, min(9, floor))
        sess = cls.get_session(char.id)
        if sess and sess.get("active"):
            return {
                "success": True,
                "message": f"感应到道友正身陷【锁妖古窟 · 第{sess.get('floor', 1)}层】，灵念已重新通达！",
                "session": sess,
            }

        # 消耗灵石开启辟邪法阵 (30 灵石)
        fee = 30
        if char.spirit_stones < fee:
            return {"success": False, "message": f"开启锁妖古窟辟邪法阵需供奉 {fee} 灵石，随身灵石不足！"}

        char.spirit_stones -= fee
        CharacterRepository.save(char)

        # 创建战斗实体
        p_ent = create_player_entity(char, boons=[])
        nodes = _generate_floor_nodes(floor)

        # 当前第一节点
        first_node = nodes[0]
        curr_monster = None
        if first_node["type"] in ("combat", "boss"):
            curr_monster = create_monster_entity(first_node["monster_template"], floor).to_dict()

        sess_data = {
            "player_id": char.id,
            "player_name": char.name,
            "active": True,
            "floor": floor,
            "node_idx": 0,
            "nodes": nodes,
            "player": p_ent.to_dict(),
            "monster": curr_monster,
            "boons": [],
            "boon_choices": [],
            "state": "battle" if curr_monster else "event",  # battle | event | choosing_boon | floor_cleared
            "stash": {
                "stones": 0,
                "items": [],
            },
            "combat_logs": [
                f"【叩关入窟】消耗 {fee} 块灵石，辟邪大阵光幕洞开，你踏入了【{DUNGEON_FLOORS[floor]['name']}】！",
                f"此地妖煞弥漫，神识受压。前方隐隐传来利爪摩挲岩壁之声……",
            ],
            "updated_at": time.time(),
        }

        d = _load_all()
        d[char.id] = sess_data
        _save_all(d)

        return {
            "success": True,
            "message": f"已叩开【{DUNGEON_FLOORS[floor]['name']}】石门，探索正式开启！",
            "session": sess_data,
        }

    @classmethod
    def execute_combat_action(
        cls,
        char: Character,
        action: str,  # "attack" | "spell" | "treasure"
        spell_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行战斗回合出招"""
        sess = cls.get_session(char.id)
        if not sess or not sess.get("active"):
            return {"success": False, "message": "未在探索锁妖古窟之中，先启关进入。"}

        if sess.get("state") != "battle" or not sess.get("monster"):
            return {"success": False, "message": "当前未处于战斗交锋阶段。"}

        p_dict = sess["player"]
        m_dict = sess["monster"]
        p_ent = CombatEntity.from_dict(p_dict)
        m_ent = CombatEntity.from_dict(m_dict)

        # 战斗步进
        res = SpellCombatEngine.step_round(
            p_ent,
            m_ent,
            action=action,
            spell_key=spell_key,
            boons=sess.get("boons", []),
        )

        sess["player"] = res["player"]
        sess["monster"] = res["monster"]
        sess.setdefault("combat_logs", []).extend(res["logs"])
        sess["combat_logs"] = sess["combat_logs"][-30:]
        sess["updated_at"] = time.time()

        # 战斗结束判定
        if res.get("ended"):
            if res.get("winner") == "player":
                # 战斗胜利！结算本节点
                curr_node_idx = sess.get("node_idx", 0)
                if curr_node_idx < len(sess["nodes"]):
                    sess["nodes"][curr_node_idx]["cleared"] = True

                # 战利品掉落入临时储物袋 (stash)
                floor = sess.get("floor", 1)
                loot_stones = random.randint(15 * floor, 35 * floor)
                sess["stash"]["stones"] = sess["stash"].get("stones", 0) + loot_stones

                drop_items = []
                if random.random() < 0.65:
                    item_name = "百年凝血草" if floor <= 3 else ("千年朱果" if floor <= 6 else "九叶涅槃芝")
                    sess["stash"].setdefault("items", []).append({"name": item_name, "count": 1})
                    drop_items.append(item_name)
                if res["monster"].get("name", "").startswith("【守关妖王】") or random.random() < 0.30:
                    pill_name = "聚气丹" if floor <= 3 else ("筑基丹" if floor <= 6 else "九转金丹")
                    sess["stash"].setdefault("items", []).append({"name": pill_name, "count": 1})
                    drop_items.append(pill_name)

                drop_text = f"收获随身灵石 +{loot_stones}"
                if drop_items:
                    drop_text += f"，拾得灵物【{'、'.join(drop_items)}】暂存入乾坤布袋！"

                sess["combat_logs"].append(f"🏆【战斩强敌】{drop_text}")
                sess["monster"] = None

                # 检查本层所有节点是否已完成
                all_cleared = all(n.get("cleared") for n in sess["nodes"])
                if all_cleared:
                    # 进入道韵三选一
                    cls._prepare_boon_choices(sess)
                    sess["state"] = "choosing_boon"
                    sess["combat_logs"].append(
                        f"✨【本层荡涤圆满】古窟石壁灵光涌动，天道残存道韵共鸣！请从三门造化道韵中抉择其一领悟。"
                    )
                else:
                    sess["state"] = "event"
                    sess["node_idx"] += 1
                    # 准备下一节点
                    next_node = sess["nodes"][sess["node_idx"]]
                    if next_node["type"] in ("combat", "boss"):
                        sess["monster"] = create_monster_entity(next_node["monster_template"], floor).to_dict()
                        sess["state"] = "battle"
                        sess["combat_logs"].append(f"👣【继续挺进】{next_node['desc']}")
                    else:
                        sess["combat_logs"].append(f"👣【行至要穴】{next_node['desc']}")

            elif res.get("winner") == "monster":
                # 战斗失败！濒死遁回客栈
                cls._handle_defeat(char, sess)
                d = _load_all()
                d[char.id] = sess
                _save_all(d)
                return {
                    "success": True,
                    "ended": True,
                    "winner": "monster",
                    "message": "气血枯竭，保命灵佩碎裂！你被挪移大阵送回客栈，重伤濒死，本次探索所得全数遗失！",
                    "session": sess,
                }

        d = _load_all()
        d[char.id] = sess
        _save_all(d)

        return {
            "success": True,
            "session": sess,
            "ended": res.get("ended", False),
            "winner": res.get("winner"),
            "logs": res["logs"],
        }

    @classmethod
    def interact_event(cls, char: Character, option: str = "confirm") -> Dict[str, Any]:
        """交互非战斗节点（造化灵泉 / 古修遗骸）"""
        sess = cls.get_session(char.id)
        if not sess or not sess.get("active"):
            return {"success": False, "message": "未在禁地探索中。"}

        if sess.get("state") != "event":
            return {"success": False, "message": "当前处于战斗或择道韵状态，无法交互要穴。"}

        curr_node_idx = sess.get("node_idx", 0)
        nodes = sess.get("nodes", [])
        if curr_node_idx >= len(nodes):
            return {"success": False, "message": "本层节点已全部肃清。"}

        node = nodes[curr_node_idx]
        ntype = node.get("type")
        floor = sess.get("floor", 1)

        if ntype == "spring":
            # 灵泉恢复 45% HP 和 45% MP
            p = sess["player"]
            rec_hp = int(p["max_hp"] * 0.45)
            rec_mp = int(p["max_mp"] * 0.45)
            p["hp"] = min(p["max_hp"], p["hp"] + rec_hp)
            p["mp"] = min(p["max_mp"], p["mp"] + rec_mp)
            node["cleared"] = True
            sess["combat_logs"].append(
                f"💧【汲饮灵泉】你掬起一捧造化灵泉饮下，四肢百骸灵力激荡，气血 +{rec_hp}，真元 +{rec_mp}！"
            )

        elif ntype == "relic":
            # 搜索遗骸获得灵石或宝物
            st = random.randint(30 * floor, 60 * floor)
            sess["stash"]["stones"] = sess["stash"].get("stones", 0) + st
            item = "上古破损残卷" if random.random() < 0.5 else "纯阳玄铁"
            sess["stash"].setdefault("items", []).append({"name": item, "count": 1})
            node["cleared"] = True
            sess["combat_logs"].append(
                f"💀【搜寻残宝】你躬身祭拜古修枯骨，自其储物戒残片中拾得 {st} 灵石与一卷【{item}】！"
            )

        # 检查是否全部清空
        all_cleared = all(n.get("cleared") for n in nodes)
        if all_cleared:
            cls._prepare_boon_choices(sess)
            sess["state"] = "choosing_boon"
            sess["combat_logs"].append(
                f"✨【本层荡涤圆满】古窟石壁灵光涌动，天道残存道韵共鸣！请从三门造化道韵中抉择其一领悟。"
            )
        else:
            sess["node_idx"] += 1
            next_node = nodes[sess["node_idx"]]
            if next_node["type"] in ("combat", "boss"):
                sess["monster"] = create_monster_entity(next_node["monster_template"], floor).to_dict()
                sess["state"] = "battle"
                sess["combat_logs"].append(f"👣【挺进下一要穴】{next_node['desc']}")
            else:
                sess["combat_logs"].append(f"👣【行至下一要穴】{next_node['desc']}")

        sess["updated_at"] = time.time()
        d = _load_all()
        d[char.id] = sess
        _save_all(d)

        return {"success": True, "session": sess}

    @classmethod
    def choose_boon(cls, char: Character, boon_key: str) -> Dict[str, Any]:
        """领悟局内道韵三选一"""
        sess = cls.get_session(char.id)
        if not sess or not sess.get("active"):
            return {"success": False, "message": "未在禁地探索中。"}

        if sess.get("state") != "choosing_boon":
            return {"success": False, "message": "当前未在领悟道韵阶段。"}

        choices = [b["key"] for b in sess.get("boon_choices", [])]
        if boon_key not in choices:
            return {"success": False, "message": "非当前顿悟的道韵候选项。"}

        sess.setdefault("boons", []).append(boon_key)
        boon_info = DAO_BOON_CATALOG.get(boon_key, {})
        sess["boon_choices"] = []
        sess["state"] = "floor_cleared"

        sess["combat_logs"].append(
            f"🧘【道韵加身】你顿悟了古窟道韵【{boon_info.get('name', boon_key)}】！灵光入体，战意倍增！"
        )
        sess["combat_logs"].append(
            f"⚖️【前路抉择】本层已荡平，道友可选择【捏碎遁符，脱离古窟】带走全部战利品，亦可选择【深入下一层】探寻至宝！"
        )

        sess["updated_at"] = time.time()
        d = _load_all()
        d[char.id] = sess
        _save_all(d)

        return {"success": True, "session": sess}

    @classmethod
    def advance_floor(cls, char: Character) -> Dict[str, Any]:
        """深入下一层"""
        sess = cls.get_session(char.id)
        if not sess or not sess.get("active"):
            return {"success": False, "message": "未在禁地探索中。"}

        if sess.get("state") != "floor_cleared":
            return {"success": False, "message": "请先肃清本层并领悟道韵再行深入。"}

        next_floor = sess.get("floor", 1) + 1
        if next_floor > 9:
            return cls.retreat(char, full_victory=True)

        sess["floor"] = next_floor
        sess["node_idx"] = 0
        sess["nodes"] = _generate_floor_nodes(next_floor)

        # 保留血量与真元，并根据道韵重算上限
        old_hp = sess["player"]["hp"]
        old_mp = sess["player"]["mp"]
        new_p = create_player_entity(char, boons=sess.get("boons", []))
        new_p.hp = min(new_p.max_hp, old_hp)
        new_p.mp = min(new_p.max_mp, old_mp)
        sess["player"] = new_p.to_dict()

        first_node = sess["nodes"][0]
        if first_node["type"] in ("combat", "boss"):
            sess["monster"] = create_monster_entity(first_node["monster_template"], next_floor).to_dict()
            sess["state"] = "battle"
        else:
            sess["monster"] = None
            sess["state"] = "event"

        sess["combat_logs"].append(
            f"🌀【踏入幽邃】你踏入传送古阵，抵达【{DUNGEON_FLOORS[next_floor]['name']}】！阴煞灵压扑面而来！"
        )
        sess["combat_logs"].append(first_node["desc"])
        sess["updated_at"] = time.time()

        d = _load_all()
        d[char.id] = sess
        _save_all(d)

        return {"success": True, "session": sess}

    @classmethod
    def retreat(cls, char: Character, full_victory: bool = False) -> Dict[str, Any]:
        """捏碎大挪移遁符脱离古窟，安全结算战利品"""
        sess = cls.get_session(char.id)
        if not sess or not sess.get("active"):
            return {"success": False, "message": "未在禁地探索中。"}

        if sess.get("state") == "battle":
            return {"success": False, "message": "强敌逼视交锋之中，虚空被封锁，无法捏碎遁符！唯有击溃妖兽方能抽身！"}

        stash = sess.get("stash", {})
        stones_earned = int(stash.get("stones", 0))
        items_earned = list(stash.get("items", []))

        # 战利品原子写入 Character 纳戒
        char.spirit_stones += stones_earned

        # 写入物品
        try:
            from core.loot_equip import EquipEngine
            for it in items_earned:
                it_name = it.get("name")
                for _ in range(int(it.get("count", 1))):
                    EquipEngine.award_item(char, it_name)
        except Exception:
            pass

        CharacterRepository.save(char)

        # 标记会话结束
        sess["active"] = False
        sess["state"] = "cleared" if full_victory else "retreated"
        d = _load_all()
        del d[char.id]
        _save_all(d)

        summary_msg = f"【功德圆满 · 安全归仓】你捏碎大挪移玉符遁出古窟！随身灵石 +{stones_earned}"
        if items_earned:
            names = [f"{i['name']}x{i.get('count', 1)}" for i in items_earned]
            summary_msg += f"，纳戒入库灵物：{'、'.join(names)}"

        return {
            "success": True,
            "message": summary_msg,
            "stones": stones_earned,
            "items": items_earned,
        }

    @classmethod
    def _prepare_boon_choices(cls, sess: Dict[str, Any]) -> None:
        """从道韵词条库中抽取 3 个随机候选"""
        existing = set(sess.get("boons", []))
        available = [k for k in DAO_BOON_CATALOG.keys() if k not in existing]
        if len(available) < 3:
            available = list(DAO_BOON_CATALOG.keys())
        picks = random.sample(available, min(3, len(available)))
        sess["boon_choices"] = [DAO_BOON_CATALOG[k] for k in picks]

    @classmethod
    def _handle_defeat(cls, char: Character, sess: Dict[str, Any]) -> None:
        """处理战斗阵亡"""
        sess["active"] = False
        sess["state"] = "defeated"
        sess["stash"] = {"stones": 0, "items": []}
        # 受到挫败：道心轻微受损，重伤传送回坊市客栈
        char.location = "青云坊市客栈"
        if getattr(char.karma, "dao_heart", 100) > 10:
            char.karma.dao_heart = max(10, char.karma.dao_heart - 3)
        CharacterRepository.save(char)
