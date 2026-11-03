"""
心魔长期状态机（F16 收尾）：魔念（心魔种）→ 阶段 → 发作 → 镇压/入魔

设计口径（spec: docs/compose/spec/heart-demon.md）：
- 既有一次性问答（core/heart_demon.py）判定口径一律不动；本模块只在其上叠加
  长期状态：魔念只认既有事实（杀业增量 / 血煞缠身时长 / 血煞反噬事件），
  惰性推导（纯函数 + 锚点），不新造线程。
- 阶段纯推导不落库：seed<=0 无种 / <40 蛰伏 / <90 滋长 / >=90 临发。
- 无种（seed=0）者全路径与 F16 前逐值一致：不播种外不掷发作、不追加后果。
- 一切数值本模块常量裁定；AI 只演既有问答的心魔之言，不决定本状态机数值。
- 道心压制与胜率一律读「有效道心」（本体 + F10 炼神加值，BodySoulEngine 单点）。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

from core.models import Character, CharacterStatus

# ---------------- 常量（规则裁定） ----------------
DEMON_SEED_CAP = 150.0            # 魔念封顶（防极端值污染公式/面板）
DEMON_STAGE2_SEED = 40.0          # 滋长阈值
DEMON_STAGE3_SEED = 90.0          # 临发阈值
STAGE_NAMES = {0: "无种", 1: "蛰伏", 2: "滋长", 3: "临发"}

SIN_SEED_FACTOR = 0.5             # 杀业增量 → 魔念（每 +1 业力 +0.5 魔念）
BLOOD_SEED_PER_DAY = 2.0          # 血煞缠身每现实日 +2 魔念
BACKLASH_SEED_GAIN = 25.0         # 血煞反噬事件播种量
BACKLASH_BASE_CHANCE = 0.60       # 反噬播种基础概率（道心 0）
BACKLASH_DAO_FACTOR = 0.003       # 有效道心每点 −0.003 播种概率（道心 100 → 0.30）

ERUPTION_CHANCE_BREAKTHROUGH = {2: 0.35, 3: 0.65}   # 突破问心发作概率（按阶段）
ERUPTION_CHANCE_MEDITATION = {2: 0.25, 3: 0.50}     # 闭关结算发作概率（按阶段）

ERUPTION_WOUND_SEED = 5.0         # 发作 wound/heart_hit 后果：魔念 +5
ERUPTION_FAIL_SEED = 15.0         # 发作 fail 后果（阶段<3）：魔念 +15
DUEL_WOUND_DAO = -8               # 闭关内斗 wound：道心 −8（≤ caps 20）
DUEL_FAIL_DAO = -15               # 闭关内斗 fail：道心 −15
DUEL_PASS_DAO = 2                 # 闭关内斗 pass：道心 +2

POSSESSED_DAO_LOSS = 20           # 入魔档：道心 −20（= EVENT_EFFECT_CAPS dao_heart 幅度上限）
POSSESSED_SIN_GAIN = 40           # 入魔档：业力 +40（= EVENT_EFFECT_CAPS sin 上限）

SUPPRESS_ITEM = "百年灵芝"         # 服丹镇魔材料（温养道基，既有产出；目录无清心丹，spec 定兼任）
SUPPRESS_ITEM_COUNT = 1
SUPPRESS_STONES = 30              # 服丹镇魔灵石成本
SUPPRESS_PILL_SEED = 35.0         # 服丹镇魔：魔念 −35
SUPPRESS_CALM_SEED = 20.0         # 静坐镇魔：魔念 −20
SUPPRESS_CALM_MIN_DAO = 50        # 静坐镇魔有效道心门槛
SUPPRESS_CALM_COOLDOWN = 20 * 3600.0  # 静坐镇魔冷却（现实秒）

DUEL_TEXTS = {
    "pass": "识海深处魔影低啸着退散——这一关，你守住了。",
    "wound": "心魔趁入定最深时扑向识海，你虽将其逼退，道心已是一阵刺痛。",
    "fail": "魔念如潮倒灌，灵台几乎失守；你咬破舌尖才勉强收功，冷汗湿透道袍。",
    "possessed": "魔种临发而心关尽溃——双目睁开时，瞳底已有一线赤芒久久不散。",
}


def _eff_dao_heart(c: Character) -> int:
    """有效道心单点（F10 炼神口径；异常回退本体）"""
    try:
        from core.body_soul import BodySoulEngine

        return BodySoulEngine.effective_dao_heart(c)
    except Exception:
        return int(getattr(c.karma, "dao_heart", 0) or 0)


def _dao_suppress_mult(c: Character) -> float:
    """道心压制系数：魔念增量按有效道心打折"""
    eff = _eff_dao_heart(c)
    if eff >= 85:
        return 0.25
    if eff >= 60:
        return 0.5
    return 1.0


class DemonStateEngine:
    """心魔长期状态：魔念推导 / 发作 / 镇压 / 入魔（全规则）"""

    # ---------------- 阶段推导 ----------------
    @staticmethod
    def stage_for(seed: float) -> int:
        if seed >= DEMON_STAGE3_SEED:
            return 3
        if seed >= DEMON_STAGE2_SEED:
            return 2
        if seed > 0:
            return 1
        return 0

    @staticmethod
    def _stage_floor(stage: int) -> float:
        """阶段下限魔念（回落一阶 = 降至下限 −1）"""
        return {3: DEMON_STAGE3_SEED, 2: DEMON_STAGE2_SEED, 1: 1.0}.get(stage, 0.0)

    # ---------------- 惰性推导 ----------------
    @staticmethod
    def _pending_growth(c: Character, now: float) -> float:
        """锚点以来未落库的魔念增量（纯读推导，不改对象）"""
        anchor = float(getattr(c, "demon_anchor_at", 0.0) or 0.0)
        if anchor <= 0:
            return 0.0  # 从未同步：只建基线，不追溯历史（spec 2.2）
        t = max(now, anchor)
        mult = _dao_suppress_mult(c)
        growth = 0.0
        # 杀业增量
        sin_now = int(getattr(c.karma, "sin_value", 0) or 0)
        sin_seen = int(getattr(c, "demon_sin_seen", 0) or 0)
        if sin_now > sin_seen:
            growth += (sin_now - sin_seen) * SIN_SEED_FACTOR
        # 血煞缠身时长：覆盖起点须还原标记起算点——add_sin 每次把标记刷新为
        # 「当下 + 3 游戏年」，故单次标记起点 = until − 3 游戏年；连续刷新时此式
        # 为覆盖下界（永不高估）。覆盖区间 = [max(锚点, 起点), min(t, until)]
        blood_until = float(getattr(c.karma, "blood_mark_until", 0.0) or 0.0)
        if blood_until > anchor:
            from config import SECONDS_PER_GAME_YEAR

            mark_start = blood_until - 3 * SECONDS_PER_GAME_YEAR
            covered = min(t, blood_until) - max(anchor, mark_start)
            if covered > 0:
                growth += covered / 86400.0 * BLOOD_SEED_PER_DAY
        return growth * mult

    @staticmethod
    def effective_seed(c: Character, now: Optional[float] = None) -> float:
        """当前有效魔念（落库值 + 惰性增量，钳封顶）；纯读不落库"""
        t = now or time.time()
        base = float(getattr(c, "demon_seed", 0.0) or 0.0)
        return max(0.0, min(DEMON_SEED_CAP, base + DemonStateEngine._pending_growth(c, t)))

    @staticmethod
    def stage(c: Character, now: Optional[float] = None) -> int:
        return DemonStateEngine.stage_for(DemonStateEngine.effective_seed(c, now))

    @staticmethod
    def sync(c: Character, now: Optional[float] = None) -> float:
        """把惰性增量落库并推进锚点/业力基线；返回落库后魔念。幂等。"""
        t = now or time.time()
        anchor = float(getattr(c, "demon_anchor_at", 0.0) or 0.0)
        if anchor <= 0:
            # 首同步只建基线（不追溯历史杀业/血煞）
            c.demon_anchor_at = t
            c.demon_sin_seen = int(getattr(c.karma, "sin_value", 0) or 0)
            c.demon_seed = max(0.0, min(DEMON_SEED_CAP, float(getattr(c, "demon_seed", 0.0) or 0.0)))
            return c.demon_seed
        c.demon_seed = DemonStateEngine.effective_seed(c, t)
        c.demon_anchor_at = max(anchor, t)
        c.demon_sin_seen = int(getattr(c.karma, "sin_value", 0) or 0)
        return c.demon_seed

    @staticmethod
    def summary(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """status 透出（纯读推导，不落库）"""
        seed = DemonStateEngine.effective_seed(c, now)
        st = DemonStateEngine.stage_for(seed)
        return {"stage": st, "stage_name": STAGE_NAMES[st], "seed": int(round(seed))}

    # ---------------- 播种 ----------------
    @staticmethod
    def on_blood_backlash(c: Character, rng=None, now: Optional[float] = None) -> Dict[str, Any]:
        """血煞反噬事件落账后的播种钩子（EventEngine.fire 调用，try/except 在调用方）"""
        r = rng or random
        t = now or time.time()
        DemonStateEngine.sync(c, t)
        eff = _eff_dao_heart(c)
        chance = max(0.0, BACKLASH_BASE_CHANCE - eff * BACKLASH_DAO_FACTOR)
        if r.random() >= chance:
            return {"seeded": False, "chance": chance}
        before = DemonStateEngine.stage_for(c.demon_seed)
        c.demon_seed = min(DEMON_SEED_CAP, c.demon_seed + BACKLASH_SEED_GAIN)
        return {
            "seeded": True,
            "chance": chance,
            "stage_before": before,
            "stage_after": DemonStateEngine.stage_for(c.demon_seed),
        }

    # ---------------- 发作 ----------------
    @staticmethod
    def roll_eruption(c: Character, scene: str, rng=None, now: Optional[float] = None) -> bool:
        """阶段>=2 才掷发作；无种/蛰伏恒 False（旧行为钉死）"""
        r = rng or random
        st = DemonStateEngine.stage(c, now)
        if st < 2:
            return False
        table = ERUPTION_CHANCE_BREAKTHROUGH if scene == "breakthrough" else ERUPTION_CHANCE_MEDITATION
        return r.random() < table.get(st, 0.0)

    @staticmethod
    def _drop_one_stage(c: Character) -> None:
        """魔念降至当前阶段下限 −1（回落一阶）；已落库口径调用（先 sync）"""
        st = DemonStateEngine.stage_for(c.demon_seed)
        if st <= 1:
            if st == 1:
                c.demon_seed = 0.0  # 蛰伏回落即除种
            return
        c.demon_seed = max(0.0, DemonStateEngine._stage_floor(st) - 1.0)

    @staticmethod
    def _apply_possessed(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """入魔档：既有最重口径加重（道心 −20 / 业力 +40 走 caps 与 add_sin）+ 世情播报"""
        t = now or time.time()
        DemonStateEngine.sync(c, t)  # 先落库既有增量，再记入魔之账
        c.karma.dao_heart = max(0, min(100, int(c.karma.dao_heart) - POSSESSED_DAO_LOSS))
        c.karma.add_sin(POSSESSED_SIN_GAIN, t)
        # 入魔业力不折算魔念：吸收进业力基线（spec 2.5：魔念只置于临发下限，不再双计）
        c.demon_sin_seen = int(c.karma.sin_value)
        c.demon_seed = max(c.demon_seed, DEMON_STAGE3_SEED)  # 魔种深种不清零
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="heart_demon",
                actor_ids=[c.id],
                actor_names=[c.name],
                location=c.location or "",
                summary=(
                    f"【心魔入魔】修士【{c.name}】心魔临发而道心溃守，魔念深种——"
                    f"天道记账：道心 −{POSSESSED_DAO_LOSS}、业力 +{POSSESSED_SIN_GAIN}"
                ),
            )
        except Exception:
            pass
        return {"possessed": True, "dao_loss": POSSESSED_DAO_LOSS, "sin_gain": POSSESSED_SIN_GAIN}

    @staticmethod
    def apply_eruption_outcome(
        c: Character, outcome: str, now: Optional[float] = None
    ) -> Dict[str, Any]:
        """突破问心发作场次的阶段后果（resolve 既有结算后追加；非发作场次不得调用）"""
        t = now or time.time()
        DemonStateEngine.sync(c, t)
        st = DemonStateEngine.stage_for(c.demon_seed)
        info: Dict[str, Any] = {"stage_before": st, "possessed": False}
        if outcome == "pass":
            DemonStateEngine._drop_one_stage(c)
            info["note"] = "问心压过魔念，心魔退却一阶。"
        elif outcome in ("wound", "heart_hit"):
            c.demon_seed = min(DEMON_SEED_CAP, c.demon_seed + ERUPTION_WOUND_SEED)
            info["note"] = "魔念借问心之机又涨了几分。"
        elif outcome in ("dao_crack", "fail"):
            if st >= 3:
                info.update(DemonStateEngine._apply_possessed(c, t))
                info["note"] = "临发之魔趁问心溃关——入魔之兆已现！"
            else:
                c.demon_seed = min(DEMON_SEED_CAP, c.demon_seed + ERUPTION_FAIL_SEED)
                info["note"] = "问心受挫，魔念趁势滋长。"
        # outcome == death：既有死亡口径已处理，不追加
        info["stage_after"] = DemonStateEngine.stage_for(c.demon_seed)
        return info

    @staticmethod
    def resolve_meditation_eruption(
        c: Character, rng=None, now: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """闭关结算发作检查 + 规则内斗裁定；不发作返回 None（旧行为不变）"""
        t = now or time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(t):
            return None
        DemonStateEngine.sync(c, t)
        st = DemonStateEngine.stage_for(c.demon_seed)
        if st < 2:
            return None
        r = rng or random
        if r.random() >= ERUPTION_CHANCE_MEDITATION.get(st, 0.0):
            return None
        # 规则内斗：胜率由有效道心与阶段裁定（与问答同一 outcome 词汇/effects caps）
        eff = _eff_dao_heart(c)
        p_pass = max(0.20, min(0.90, 0.45 + (eff - 50) * 0.006 - (st - 2) * 0.12))
        roll = r.random()
        info: Dict[str, Any] = {"stage_before": st, "possessed": False}
        if roll < p_pass:
            outcome = "pass"
            DemonStateEngine._drop_one_stage(c)
            c.karma.dao_heart = max(0, min(100, int(c.karma.dao_heart) + DUEL_PASS_DAO))
        elif roll < p_pass + 0.35:
            outcome = "wound"
            c.karma.dao_heart = max(0, min(100, int(c.karma.dao_heart) + DUEL_WOUND_DAO))
            c.demon_seed = min(DEMON_SEED_CAP, c.demon_seed + ERUPTION_WOUND_SEED)
        else:
            outcome = "fail"
            if st >= 3:
                info.update(DemonStateEngine._apply_possessed(c, t))
            else:
                c.karma.dao_heart = max(0, min(100, int(c.karma.dao_heart) + DUEL_FAIL_DAO))
                c.demon_seed = min(DEMON_SEED_CAP, c.demon_seed + ERUPTION_FAIL_SEED)
        info.update(
            {
                "erupted": True,
                "outcome": outcome,
                "stage_after": DemonStateEngine.stage_for(c.demon_seed),
                "text": DUEL_TEXTS["possessed" if info.get("possessed") else outcome],
            }
        )
        return info

    # ---------------- 镇压 ----------------
    @staticmethod
    def _check_alive(c: Character, now: float) -> Optional[Dict[str, Any]]:
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead(now):
            return {"success": False, "message": "此世已了，真灵已散，无从镇魔。"}
        return None

    @staticmethod
    def suppress_pill(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """服丹镇魔（主路径）：百年灵芝 ×1 + 灵石 30 → 魔念 −35；成功才扣费"""
        t = now or time.time()
        dead = DemonStateEngine._check_alive(c, t)
        if dead:
            return dead
        DemonStateEngine.sync(c, t)
        if c.demon_seed <= 0:
            return {"success": False, "message": "识海清净，并无心魔之种，无需服丹。"}
        have = int((c.inventory or []).count(SUPPRESS_ITEM))
        if have < SUPPRESS_ITEM_COUNT:
            return {"success": False, "message": f"行囊中无【{SUPPRESS_ITEM}】，无法服丹镇魔（坊市/探险/灵田皆有出）。"}
        if int(c.spirit_stones) < SUPPRESS_STONES:
            return {"success": False, "message": f"灵石不足（需 {SUPPRESS_STONES}），无法服丹镇魔。"}
        for _ in range(SUPPRESS_ITEM_COUNT):
            c.inventory.remove(SUPPRESS_ITEM)
        c.spirit_stones -= SUPPRESS_STONES
        st_before = DemonStateEngine.stage_for(c.demon_seed)
        c.demon_seed = max(0.0, c.demon_seed - SUPPRESS_PILL_SEED)
        st_after = DemonStateEngine.stage_for(c.demon_seed)
        cleared = c.demon_seed <= 0
        msg = (
            f"服下【{SUPPRESS_ITEM}】、化开 {SUPPRESS_STONES} 灵石药力，温养道基——魔念 −{SUPPRESS_PILL_SEED:.0f}，"
            f"心魔自【{STAGE_NAMES[st_before]}】退至【{STAGE_NAMES[st_after]}】。"
        )
        if cleared:
            msg += "魔种已除，识海重归清明。"
        return {"success": True, "message": msg, "stage_before": st_before, "stage_after": st_after, "seed": c.demon_seed}

    @staticmethod
    def suppress_calm(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """静坐镇魔（道心硬抗）：有效道心 ≥50、冷却 20h → 魔念 −20；无资源成本"""
        t = now or time.time()
        dead = DemonStateEngine._check_alive(c, t)
        if dead:
            return dead
        DemonStateEngine.sync(c, t)
        if c.demon_seed <= 0:
            return {"success": False, "message": "识海清净，并无心魔之种，无需静坐镇魔。"}
        eff = _eff_dao_heart(c)
        if eff < SUPPRESS_CALM_MIN_DAO:
            return {"success": False, "message": f"有效道心 {eff} 不足 {SUPPRESS_CALM_MIN_DAO}，硬抗只会引魔反扑——先服丹或养心。"}
        last = float(getattr(c, "demon_calm_at", 0.0) or 0.0)
        if last > 0 and t - last < SUPPRESS_CALM_COOLDOWN:
            rem_h = (SUPPRESS_CALM_COOLDOWN - (t - last)) / 3600.0
            return {"success": False, "message": f"静坐镇魔耗损心神，需再调息 {rem_h:.1f} 小时方可再行。"}
        st_before = DemonStateEngine.stage_for(c.demon_seed)
        c.demon_seed = max(0.0, c.demon_seed - SUPPRESS_CALM_SEED)
        c.demon_calm_at = t
        st_after = DemonStateEngine.stage_for(c.demon_seed)
        msg = (
            f"以道心硬撼魔念，静坐竟日——魔念 −{SUPPRESS_CALM_SEED:.0f}，"
            f"心魔自【{STAGE_NAMES[st_before]}】退至【{STAGE_NAMES[st_after]}】。"
        )
        if c.demon_seed <= 0:
            msg += "魔种已除，识海重归清明。"
        return {"success": True, "message": msg, "stage_before": st_before, "stage_after": st_after, "seed": c.demon_seed}

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(c: Character, now: Optional[float] = None) -> str:
        t = now or time.time()
        DemonStateEngine.sync(c, t)
        seed = c.demon_seed
        st = DemonStateEngine.stage_for(seed)
        eff = _eff_dao_heart(c)
        lines = ["【镇魔 · 心魔长卷】"]
        if st == 0:
            lines.append("识海清净，心魔无种。杀业与血煞皆是魔种之壤——行止之间，自有天道看着。")
        else:
            lines.append(
                f"心魔阶段：【{STAGE_NAMES[st]}】（魔念 {seed:.0f} / 临发 {DEMON_STAGE3_SEED:.0f}）"
            )
            lines.append(
                f"魔念之源：业力 {int(c.karma.sin_value)}、血煞{'缠身' if c.karma.is_blood_marked(t) else '已散'}；"
                f"有效道心 {eff}（压制系数 ×{_dao_suppress_mult(c):.2f}）。"
            )
            if st >= 2:
                lines.append(
                    f"⚠ 此魔已可发作：突破问心约 {int(ERUPTION_CHANCE_BREAKTHROUGH[st]*100)}%、"
                    f"闭关结算约 {int(ERUPTION_CHANCE_MEDITATION[st]*100)}% 概率趁隙而起；"
                    "临发之魔若在发作中溃关，更有入魔之险（道心大损、业力暴涨）。"
                )
            else:
                lines.append("魔种尚在蛰伏，不会发作；继续积业或血煞缠身，终将滋长。")
        lines.append(
            f"镇压：/镇魔 服丹（{SUPPRESS_ITEM}×{SUPPRESS_ITEM_COUNT} + 灵石 {SUPPRESS_STONES} → 魔念 −{SUPPRESS_PILL_SEED:.0f}）"
            f"｜ /镇魔 静坐（有效道心 ≥{SUPPRESS_CALM_MIN_DAO}，冷却 20 小时 → 魔念 −{SUPPRESS_CALM_SEED:.0f}）"
        )
        return "\n".join(lines)
