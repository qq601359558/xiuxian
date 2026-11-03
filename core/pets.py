"""
灵宠系统（F01）：遇兽 → 契约 → 喂养 → 出战助战 → 放生/随主殁
规则权威：捕获概率、成本、成长、加成全部在此裁决；叙事只用本地模板，不依赖 AI。
Spec：docs/compose/spec/pets.md
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from config import ITEM_CATALOG
from core.models import Character, CharacterStatus, SpiritPet

# ==================== 物种池与常量（对照坊市物价校准） ====================
# tendency: attack 攻 / guard 守（战力全额加成）/ treasure 探宝（战力减半 + 探险额外拾获）
PET_SPECIES: Dict[str, Dict[str, Any]] = {
    "青鳞蟒": {"tendency": "attack", "weight": 30, "desc": "鳞甲泛青，吐信如剑，扑咬凌厉。"},
    "疾风隼": {"tendency": "attack", "weight": 25, "desc": "振翅无声，俯冲如电，先手夺人。"},
    "玄甲龟": {"tendency": "guard", "weight": 25, "desc": "背甲玄纹，沉稳如山，护主挡灾。"},
    "寻宝鼠": {"tendency": "treasure", "weight": 20, "desc": "鼻尖金须，嗅宝如神，专叼遗珍。"},
}
PET_TENDENCY_CN = {"attack": "攻", "guard": "守", "treasure": "探宝"}

PET_MAX_OWNED = 3               # 每人限养
PET_MAX_LEVEL = 10
PET_GROWTH_PER_LEVEL = 100      # 每 100 成长升 1 级
PET_CONTRACT_STONES = 60        # 契约灵石成本（聚气丹价 40 的 1.5 倍）
PET_FEED_STONES = 15            # 灵石喂养成本/次
PET_FEED_STONES_GROWTH = 10
PET_FEED_STONES_INTIMACY = 3
PET_FEED_PILL_GROWTH = 25       # 丹药喂养（消耗囊中丹药 1 颗）
PET_FEED_PILL_INTIMACY = 6
PET_INTIMACY_MAX = 100
PET_INTIMACY_MIN_WORK = 20      # 亲密度低于此值，灵宠不肯出力（无加成）
PET_POWER_BASE = 0.02
PET_POWER_PER_LEVEL = 0.01
PET_POWER_CAP = 0.10            # 出战战力加成上限（装备上限 +20% 的一半）
PET_ENCOUNTER_CHANCE = 0.18     # 探险成功后遇可契灵兽概率
PET_PENDING_FLEE_CHANCE = 0.5   # 已有待契约灵兽时，再次探险成功使其遁走的概率
PET_TREASURE_LOOT_P = 0.25      # 探宝宠额外拾获概率
PET_EXPLORE_GROWTH = 2          # 出战宠随主人探险成功所得成长

_ENCOUNTER_LINES = [
    "林间窸窣，一头{species}自草影间探出头来，灵光内蕴，竟不惧人，踱到近前打量于你。",
    "溪边雾起，{species}踏水而至，目光清亮，似与你命中有一段缘法。",
    "残垣后传来轻响，{species}探首而出，绕着你转了两圈，并未逃走。",
]


def level_for(growth: int) -> int:
    """成长值 → 等级（1 起，封顶 PET_MAX_LEVEL）"""
    return max(1, min(PET_MAX_LEVEL, int(growth) // PET_GROWTH_PER_LEVEL + 1))


def _alive_pets(c: Character) -> List[SpiritPet]:
    return [p for p in (c.pets or []) if p.state != "dead"]


def active_pet(c: Character) -> Optional[SpiritPet]:
    for p in _alive_pets(c):
        if p.active:
            return p
    return None


def _find_pet(c: Character, hint: str) -> Dict[str, Any]:
    """按名子串模糊匹配（与 /穿戴 同惯例）；返回 {"pet": ...} 或 {"error": ...}"""
    hint = (hint or "").strip()
    if not hint:
        return {"error": "须指明灵宠名。"}
    pets = _alive_pets(c)
    for p in pets:
        if p.name == hint or p.species == hint:
            return {"pet": p}
    hits = [p for p in pets if hint in p.name or hint in p.species]
    if not hits:
        return {"error": f"未养有名为【{hint}】的灵宠。/灵宠 查看。"}
    if len(hits) > 1:
        names = "、".join(p.name for p in hits)
        return {"error": f"【{hint}】匹配到多只灵宠（{names}），请指明全名。"}
    return {"pet": hits[0]}


class PetEngine:
    """灵宠裁决引擎（纯规则，无 AI 依赖）"""

    # ---------------- 遇兽 ----------------
    @staticmethod
    def maybe_encounter(c: Character, rng: Optional[random.Random] = None) -> Optional[str]:
        """
        探险成功后掷骰遇可契灵兽。命中则写入 c.pending_pet_species 并返回物种名。
        已有待契约灵兽时不重复触发，并有概率使其遁走（清空 pending，返回 None）。
        养宠已满则不再遇兽。
        """
        r = rng or random.Random()
        if len(_alive_pets(c)) >= PET_MAX_OWNED:
            return None
        if c.pending_pet_species:
            if r.random() < PET_PENDING_FLEE_CHANCE:
                c.pending_pet_species = ""
            return None
        if r.random() >= PET_ENCOUNTER_CHANCE:
            return None
        species = list(PET_SPECIES.keys())
        weights = [PET_SPECIES[s]["weight"] for s in species]
        pick = r.choices(species, weights=weights, k=1)[0]
        c.pending_pet_species = pick
        return pick

    @staticmethod
    def encounter_line(species: str) -> str:
        cfg = PET_SPECIES.get(species) or {}
        line = random.choice(_ENCOUNTER_LINES).format(species=species)
        return (
            f"【灵兽现踪】{line}（{cfg.get('desc', '')}）\n"
            f"可用 /契约 {species} 结契，需灵石 {PET_CONTRACT_STONES}。它不会久候——"
            "再历风浪便可能遁走。"
        )

    # ---------------- 契约 ----------------
    @staticmethod
    def contract(c: Character, species_hint: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.DEAD:
            return {"success": False, "message": "身死道消，无力结契。"}
        if c.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "闭关锁门，无暇结契。请先 /出关。"}
        pending = (c.pending_pet_species or "").strip()
        if not pending:
            return {
                "success": False,
                "message": "眼下并无可契灵兽。外出 /探险 成功时或可遇兽现踪。",
            }
        hint = (species_hint or "").strip()
        if hint and hint not in pending and pending not in hint:
            return {
                "success": False,
                "message": f"眼前灵兽是【{pending}】，并非【{hint}】。",
            }
        if len(_alive_pets(c)) >= PET_MAX_OWNED:
            return {
                "success": False,
                "message": f"灵宠已满（限养 {PET_MAX_OWNED} 只），先 /放生 再契约。",
            }
        if c.spirit_stones < PET_CONTRACT_STONES:
            return {
                "success": False,
                "message": (
                    f"结契需灵石 {PET_CONTRACT_STONES}（囊中 {c.spirit_stones}），"
                    "灵兽静候一旁，并未离去。"
                ),
            }
        c.spirit_stones -= PET_CONTRACT_STONES
        c.pending_pet_species = ""
        # 个体名：默认物种名，重名加序（二、三……）
        name = pending
        existing = {p.name for p in _alive_pets(c)}
        if name in existing:
            for suffix in ("二", "三", "四", "五"):
                if pending + suffix not in existing:
                    name = pending + suffix
                    break
        pet = SpiritPet(
            species=pending, name=name, growth=0, intimacy=10,
            active=False, state="rest", met_at=time.time(),
        )
        c.pets.append(pet)
        cfg = PET_SPECIES.get(pending) or {}
        return {
            "success": True,
            "pet": pet,
            "message": (
                f"【结契】灵石 {PET_CONTRACT_STONES} 化作契纹没入【{name}】眉心——"
                f"{cfg.get('desc', '')}\n"
                f"此兽性情偏「{PET_TENDENCY_CN.get(cfg.get('tendency', ''), '')}」。"
                f"/喂养 可助其成长，/出战 {name} 可令其随行助战。"
            ),
        }

    # ---------------- 喂养 ----------------
    @staticmethod
    def feed(c: Character, pet_hint: str, pill_name: str = "") -> Dict[str, Any]:
        if c.status == CharacterStatus.DEAD:
            return {"success": False, "message": "身死道消，无力喂养。"}
        found = _find_pet(c, pet_hint)
        if "pet" not in found:
            return {"success": False, "message": found["error"]}
        pet = found["pet"]
        pill = (pill_name or "").strip()
        if pill:
            cfg = ITEM_CATALOG.get(pill) or {}
            if cfg.get("kind") != "pill":
                return {"success": False, "message": f"【{pill}】不是丹药，灵宠不吃。"}
            if pill not in c.inventory:
                return {"success": False, "message": f"囊中并无【{pill}】。"}
            c.inventory.remove(pill)
            pet.growth += PET_FEED_PILL_GROWTH
            pet.intimacy = min(PET_INTIMACY_MAX, pet.intimacy + PET_FEED_PILL_INTIMACY)
            how = f"喂下丹药【{pill}】"
        else:
            if c.spirit_stones < PET_FEED_STONES:
                return {
                    "success": False,
                    "message": f"喂养需灵石 {PET_FEED_STONES}（囊中 {c.spirit_stones}）。",
                }
            c.spirit_stones -= PET_FEED_STONES
            pet.growth += PET_FEED_STONES_GROWTH
            pet.intimacy = min(PET_INTIMACY_MAX, pet.intimacy + PET_FEED_STONES_INTIMACY)
            how = f"以灵石 {PET_FEED_STONES} 喂养"
        lv = level_for(pet.growth)
        return {
            "success": True,
            "pet": pet,
            "message": (
                f"【喂养】{how}，【{pet.name}】欢快进食。"
                f"成长 {pet.growth}（{lv} 级）· 亲密 {pet.intimacy}。"
            ),
        }

    # ---------------- 出战 / 休息 / 放生 ----------------
    @staticmethod
    def deploy(c: Character, pet_hint: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.DEAD:
            return {"success": False, "message": "身死道消，灵宠无主。"}
        found = _find_pet(c, pet_hint)
        if "pet" not in found:
            return {"success": False, "message": found["error"]}
        pet = found["pet"]
        for p in _alive_pets(c):
            if p is not pet and p.active:
                p.active = False
                p.state = "rest"
        pet.active = True
        pet.state = "follow"
        return {
            "success": True,
            "pet": pet,
            "message": f"【出战】{pet.name} 已随行出战（同时仅一宠出战）。",
        }

    @staticmethod
    def rest(c: Character, pet_hint: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.DEAD:
            return {"success": False, "message": "身死道消，灵宠无主。"}
        found = _find_pet(c, pet_hint)
        if "pet" not in found:
            return {"success": False, "message": found["error"]}
        pet = found["pet"]
        pet.active = False
        pet.state = "rest"
        return {
            "success": True,
            "pet": pet,
            "message": f"【休息】{pet.name} 已退回灵兽袋静养。",
        }

    @staticmethod
    def release(c: Character, pet_hint: str) -> Dict[str, Any]:
        if c.status == CharacterStatus.DEAD:
            return {"success": False, "message": "身死道消，灵宠已随主而殁，无可放生。"}
        found = _find_pet(c, pet_hint)
        if "pet" not in found:
            return {"success": False, "message": found["error"]}
        pet = found["pet"]
        c.pets.remove(pet)
        return {
            "success": True,
            "message": (
                f"【放生】契纹散去，【{pet.name}】回望一眼，转身没入山林。"
                "此世缘尽，不复相见。"
            ),
        }

    # ---------------- 助战 ----------------
    @staticmethod
    def power_bonus(c: Character) -> float:
        """出战灵宠战力系数（与 EquipEngine.power_bonus 同模式：返回乘子）"""
        pet = active_pet(c)
        if not pet:
            return 1.0
        if pet.intimacy < PET_INTIMACY_MIN_WORK:
            return 1.0
        bonus = min(PET_POWER_CAP, PET_POWER_BASE + PET_POWER_PER_LEVEL * level_for(pet.growth))
        cfg = PET_SPECIES.get(pet.species) or {}
        if cfg.get("tendency") == "treasure":
            bonus *= 0.5
        return 1.0 + bonus

    @staticmethod
    def assist_line(c: Character) -> str:
        """出战宠助战描述（斗法/探险结算文本用）；无出战或不出力时为空串"""
        pet = active_pet(c)
        if not pet:
            return ""
        if pet.intimacy < PET_INTIMACY_MIN_WORK:
            return f"【灵宠】{pet.name} 亲密不足（{pet.intimacy}），缩在一旁不肯出力。先 /喂养 拉近感情。"
        cfg = PET_SPECIES.get(pet.species) or {}
        tendency = cfg.get("tendency")
        lv = level_for(pet.growth)
        if tendency == "attack":
            return f"【灵宠助战】{pet.name}（{lv} 级）扑咬撕扯，攻势如潮，主人战力得其助力。"
        if tendency == "guard":
            return f"【灵宠助战】{pet.name}（{lv} 级）横身护主，甲壳硬撼来袭，主人战力得其助力。"
        if tendency == "treasure":
            return f"【灵宠助战】{pet.name}（{lv} 级）鼻尖金须乱颤，四处嗅探遗珍。"
        return f"【灵宠助战】{pet.name}（{lv} 级）随行助战。"

    # ---------------- 死亡 ----------------
    @staticmethod
    def on_owner_death(c: Character) -> None:
        """主人坐化/身死：灵宠殁（与一世循环一致）。幂等。"""
        for p in c.pets or []:
            p.state = "dead"
            p.active = False
        c.pending_pet_species = ""

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(c: Character) -> str:
        lines = ["【灵宠】"]
        if c.pending_pet_species:
            lines.append(
                f"· 待契约：{c.pending_pet_species} 徘徊不去，/契约 {c.pending_pet_species}"
                f"（灵石 {PET_CONTRACT_STONES}）"
            )
        pets = c.pets or []
        if not pets:
            lines.append("尚未养有灵宠。外出 /探险 成功时，或可遇可契灵兽现踪。")
        for p in pets:
            cfg = PET_SPECIES.get(p.species) or {}
            t_cn = PET_TENDENCY_CN.get(cfg.get("tendency", ""), "")
            if p.state == "dead":
                state = "已殁"
            elif p.active:
                state = "出战中"
            else:
                state = "休息"
            lines.append(
                f"· {p.name}（{p.species}·{t_cn}）{level_for(p.growth)} 级 "
                f"成长 {p.growth} · 亲密 {p.intimacy} · {state}"
            )
        alive = _alive_pets(c)
        lines.append(f"共 {len(alive)}/{PET_MAX_OWNED} 只（不含已殁）· 同时出战 1 只")
        lines.append("指令：/契约 <兽名> /喂养 <宠名> [丹药] /出战 <宠名> /休息 <宠名> /放生 <宠名>")
        return "\n".join(lines)
