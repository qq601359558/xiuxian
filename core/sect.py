"""
宗门轻量版：入门考核 / 月俸 / 传功 / 晋升 / 势力统计
从 CLI 迁到 core，供局域网服与 CLI 共用。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from config import SECTS_CONFIG, WORLD_LOCATIONS, SECONDS_PER_GAME_MONTH
from core.models import Character, CharacterStatus
from core.clock import WorldClock
from core.qi import global_qi_multiplier

# 晋升所需大境界（外门→内门→执事）
PROMOTE_REQ_TIER = {
    "内门弟子": 2,   # 筑基
    "执事": 3,       # 金丹
    "长老": 4,       # 元婴
}


def _match_sect(name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    for key in SECTS_CONFIG:
        if name == key or name in key or key in name:
            return key
    return None


def _root_ok_for_sect(c: Character, sect: str) -> bool:
    if sect != "万剑仙门":
        return True
    elems = {e.value for e in c.spiritual_root.elements}
    return bool(elems & {"金", "雷"})


def evaluate_join(c: Character, sect: str) -> tuple[bool, str]:
    cfg = SECTS_CONFIG.get(sect)
    if not cfg:
        return False, f"未闻此宗门：{sect}"
    if c.sect:
        return False, f"已拜入【{c.sect}】，不可三心二意；需先 /叛门。"
    if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
        return False, "身死道消，何谈拜山。"
    # 必须在总坛
    hq = cfg.get("headquarters") or ""
    if hq and c.location != hq:
        return False, f"须亲至【{hq}】山门方可叩关，当前在【{c.location}】。"
    dao = c.karma.dao_heart
    sin = c.karma.sin_value
    if dao < cfg.get("req_dao_heart", 0):
        return False, f"道心不足（需≥{cfg.get('req_dao_heart')}，现 {dao}）。"
    if sin > cfg.get("max_sin", 10**9):
        return False, f"业力过重（需≤{cfg.get('max_sin')}，现 {sin}）。"
    if cfg.get("min_sin") and sin < cfg["min_sin"]:
        return False, f"魔宗要的是血债（需≥{cfg['min_sin']}，现 {sin}）。"
    if sect == "万剑仙门" and not _root_ok_for_sect(c, sect) and dao < 70:
        return False, "非金/雷灵根且道心未达 70，剑心不通。"
    return True, ""


def join_sect(c: Character, sect_name: str) -> Dict[str, Any]:
    sect = _match_sect(sect_name)
    if not sect:
        return {"success": False, "message": f"未知名仙门：{sect_name}，可 /宗门 查阅。"}
    ok, reason = evaluate_join(c, sect)
    if not ok:
        return {"success": False, "message": f"【山门拒止】{reason}"}

    cfg = SECTS_CONFIG[sect]
    c.sect = sect
    c.sect_rank = "外门弟子"
    gift = cfg.get("starter_array")
    if gift and gift not in c.arrays:
        c.arrays.append(gift)
        gift_msg = f"获赐【{gift}】。"
    else:
        gift_msg = ""
    return {
        "success": True,
        "sect": sect,
        "message": (
            f"【山门洞开】{c.name} 通过考核，拜入【{sect}】·外门弟子。\n"
            f"{gift_msg}\n"
            f"· 可至【{cfg.get('cave_location')}】免费闭关\n"
            f"· 现实每 2 小时可 /领俸禄\n· 可 /传功 <弟子道号> 指点后进\n"
            f"· {cfg.get('rules_tip','')}"
        ),
    }


def leave_sect(c: Character) -> Dict[str, Any]:
    if not c.sect:
        return {"success": False, "message": "本就是散修。"}
    old = c.sect
    c.sect = None
    c.sect_rank = "散修"
    # 叛门：道心轻挫
    c.karma.dao_heart = max(0, c.karma.dao_heart - 5)
    return {
        "success": True,
        "message": f"【叛出门墙】脱离【{old}】，道心 -5。山高水长，好自为之。",
    }


def claim_salary(c: Character, now: Optional[float] = None) -> Dict[str, Any]:
    return WorldClock.claim_sect_salary(c, now=now)


def promote(c: Character) -> Dict[str, Any]:
    if not c.sect:
        return {"success": False, "message": "散修无阶可晋。"}
    order = ["外门弟子", "内门弟子", "执事", "长老"]
    if c.sect_rank not in order:
        return {"success": False, "message": f"【{c.sect_rank}】已极高，非考核可晋。"}
    idx = order.index(c.sect_rank)
    if idx >= len(order) - 1:
        return {"success": False, "message": "已是长老之尊。"}
    nxt = order[idx + 1]
    need = PROMOTE_REQ_TIER.get(nxt, 99)
    if c.realm.tier < need:
        return {
            "success": False,
            "message": f"晋升【{nxt}】需境界达 {need} 阶以上（现 {c.realm.name}）。",
        }
    c.sect_rank = nxt
    salary_bonus = 10 if nxt in ("执事", "长老") else 0
    return {
        "success": True,
        "message": f"【晋升】{c.name} 于【{c.sect}】晋为【{nxt}】。" + (f"月俸额外+{salary_bonus}。" if salary_bonus else ""),
        "salary_bonus": salary_bonus,
    }


def transmit_teaching(
    master: Character,
    disciple: Character,
) -> Dict[str, Any]:
    """传功：同宗高境界指点低境界，消耗师父少量灵石/修为给弟子机缘目标"""
    if not master.sect or master.sect != disciple.sect:
        return {"success": False, "message": "须同门方可传功。"}
    if master.id == disciple.id:
        return {"success": False, "message": "不可自传。"}
    if master.realm.tier <= disciple.realm.tier:
        return {"success": False, "message": "境界须高于对方方可指点。"}
    if master.status == CharacterStatus.DEAD or disciple.status == CharacterStatus.DEAD:
        return {"success": False, "message": "生死相隔，无法传功。"}
    cost = 20 * master.realm.tier
    try:
        from core.social_bonds import transmit_cost_mult

        cost = max(1, int(cost * transmit_cost_mult(master, disciple)))
    except Exception:
        pass
    if master.spirit_stones < cost:
        return {"success": False, "message": f"传功需备礼 {cost} 灵石，不足。"}
    master.spirit_stones -= cost
    gain = int(40 * (1 + disciple.spiritual_root.efficiency) * global_qi_multiplier())
    disciple.realm.current_exp = min(disciple.realm.max_exp, disciple.realm.current_exp + gain)
    merit = 8
    try:
        from core.social_bonds import transmit_cost_mult as _tm

        if _tm(master, disciple) < 1.0:
            merit = 8
        else:
            merit = 5
    except Exception:
        merit = 5
    master.karma.add_merit(merit)
    return {
        "success": True,
        "exp_gained": gain,
        "message": (
            f"【传功】{master.name} 以神识点化 {disciple.name}，"
            f"耗礼 {cost} 灵石，对方修为 +{gain}，你功德 +{merit}。"
        ),
    }


def sect_roster(sect: str) -> List[Character]:
    from storage.db import CharacterRepository

    out = []
    for c in CharacterRepository.list_all_alive():
        if c.sect == sect and c.status != CharacterStatus.DEAD:
            out.append(c)
    out.sort(key=lambda x: (-x.realm.tier, -x.realm.sub_tier, x.name))
    return out


def format_sect_board(viewer: Optional[Character] = None) -> str:
    lines = ["【天下仙门】"]
    for name, cfg in SECTS_CONFIG.items():
        members = sect_roster(name)
        players = sum(1 for m in members if not str(m.user_id).startswith("npc_"))
        lines.append(
            f"· {name}（{cfg.get('alignment','')}）在册 {len(members)} 人（玩家 {players}）"
            f"\n  总坛 {cfg.get('headquarters')} | 月俸 {cfg.get('monthly_salary')}"
            f"\n  {cfg.get('rules_tip','')}"
        )
        if members[:3]:
            top = "、".join(f"{m.name}·{m.sect_rank}·{m.realm.name}" for m in members[:3])
            lines.append(f"  高层/知名：{top}")
    if viewer is not None:
        if viewer.sect:
            lines.append(f"你的宗籍：【{viewer.sect}】·{viewer.sect_rank}")
        else:
            lines.append("你的宗籍：散修。/拜入 <宗门> 须亲至总坛山门。")
    return "\n".join(lines)
