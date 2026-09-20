"""
预生成世界 NPC 全阵容：各仙门编制（掌门/长老/执事/弟子）+ 商会 + 散修
幂等：同 user_id 已存在则跳过创建
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import CharacterRepository, NpcMindRepository, NpcAgendaRepository, init_db
from core.npc_agenda import ensure_agenda


def _n(uid, name, tier, sub, loc, sect, rank, sin, merit, stones, personality, agenda, note):
    return {
        "uid": uid, "name": name, "tier": tier, "sub": sub, "loc": loc,
        "sect": sect, "rank": rank, "sin": sin, "merit": merit, "stones": stones,
        "personality": personality, "agenda": agenda, "note": note,
    }


ROSTER: List[Dict[str, Any]] = [
    # ================= 青云宗（正道名门）=================
    _n("npc_qy_01", "玄清子", 4, 1, "青云宗外门山门", "青云宗", "掌门",
       0, 400, 5000, "清高自持", "patrol", "元婴掌门，道法自然，轻易不出山"),
    _n("npc_qy_02", "静虚真人", 3, 2, "宗门玄元洞府", "青云宗", "太上长老",
       0, 350, 3200, "淡泊避世", "seclusion", "金丹后期老宿，常年闭死关"),
    _n("npc_qy_03", "云鹤道人", 2, 2, "青云宗外门山门", "青云宗", "执法长老",
       0, 180, 650, "清高自持", "patrol", "外门执法，嫉恶如仇"),
    _n("npc_qy_04", "丹霞子", 3, 0, "宗门玄元洞府", "青云宗", "丹殿长老",
       0, 120, 2800, "谨慎多疑", "treasure", "掌管丹房，炼丹如命"),
    _n("npc_qy_05", "林惊羽", 2, 0, "青云宗外门山门", "青云宗", "内门弟子",
       5, 40, 380, "豪爽仗义", "patrol", "内门大师兄，好打抱不平"),
    _n("npc_qy_06", "苏婉清", 1, 3, "宗门玄元洞府", "青云宗", "内门弟子",
       0, 25, 220, "淡泊避世", "seclusion", "剑心通明，少问世事"),
    _n("npc_qy_07", "石猛", 1, 0, "青云宗外门山门", "青云宗", "外门弟子",
       5, 10, 120, "豪爽仗义", "patrol", "守山弟子，好酒"),
    _n("npc_qy_08", "赵小满", 1, 1, "青云宗外门山门", "青云宗", "外门弟子",
       0, 5, 80, "谨慎多疑", "social", "新入门，战战兢兢"),
    _n("npc_qy_09", "青萝", 1, 2, "宗门玄元洞府", "青云宗", "外门弟子",
       0, 30, 200, "淡泊避世", "seclusion", "常年在洞府打杂闭关"),

    # ================= 万剑仙门（杀伐中立）=================
    _n("npc_wj_01", "剑圣·独孤败", 5, 0, "万剑仙门峰", "万剑仙门", "掌门",
       30, 200, 8000, "清高自持", "seclusion", "化神剑修，一剑可开山"),
    _n("npc_wj_02", "断岳剑尊", 3, 2, "万剑仙门峰", "万剑仙门", "大长老",
       40, 80, 3500, "莽撞好斗", "patrol", "主掌刑罚剑阵，火爆脾气"),
    _n("npc_wj_03", "白霜", 2, 1, "洗剑池洞天", "万剑仙门", "洗剑池执事",
       0, 60, 400, "清高自持", "seclusion", "洗剑池执事，剑意冰寒"),
    _n("npc_wj_04", "赤霄", 2, 3, "万剑仙门峰", "万剑仙门", "内门首席",
       25, 30, 900, "莽撞好斗", "patrol", "以战养战，好挑战强者"),
    _n("npc_wj_05", "墨离", 2, 0, "洗剑池洞天", "万剑仙门", "内门弟子",
       10, 15, 350, "阴鸷记仇", "social", "剑走偏锋，心眼小"),
    _n("npc_wj_06", "剑奴阿七", 1, 2, "万剑仙门峰", "万剑仙门", "外门弟子",
       15, 0, 260, "莽撞好斗", "patrol", "剑痴，见强者就想切磋"),
    _n("npc_wj_07", "小环", 1, 0, "万剑仙门峰", "万剑仙门", "外门弟子",
       0, 8, 90, "豪爽仗义", "social", "剑冢扫地丫头，耳目灵通"),

    # ================= 九幽天魔宗（魔道巨擘）=================
    _n("npc_jy_01", "幽冥老祖", 5, 1, "九幽天魔宗坛", "九幽天魔宗", "宗主",
       500, 0, 9000, "阴鸷记仇", "patrol", "化神魔尊，喜怒无常"),
    _n("npc_jy_02", "血衣侯", 3, 1, "九幽天魔宗坛", "九幽天魔宗", "执法魔使",
       320, 0, 2200, "阴鸷记仇", "revenge", "替宗主清洗叛徒"),
    _n("npc_jy_03", "厉无锋", 3, 0, "九幽天魔宗坛", "九幽天魔宗", "护法",
       200, 0, 800, "莽撞好斗", "patrol", "金丹魔修，护短"),
    _n("npc_jy_04", "骨姬", 1, 3, "九幽天魔宗坛", "九幽天魔宗", "执事",
       120, 0, 350, "市侩圆滑", "social", "魔宗情报贩子"),
    _n("npc_jy_05", "血刀老祖", 2, 1, "黑风绝渊", "九幽天魔宗", "外门长老",
       280, 0, 1200, "阴鸷记仇", "survive", "血债累累，天道标记"),
    _n("npc_jy_06", "毒娘子", 2, 0, "黑风绝渊", "九幽天魔宗", "内门弟子",
       150, 0, 480, "市侩圆滑", "treasure", "善用奇毒，黑市常客"),
    _n("npc_jy_07", "阿骨", 1, 1, "黑风绝渊", "九幽天魔宗", "外门弟子",
       60, 0, 150, "莽撞好斗", "patrol", "炼尸一脉，憨傻好斗"),

    # ================= 四海散修商会（中立）=================
    _n("npc_sh_01", "金满堂", 3, 1, "青云坊市客栈", "四海散修商会", "会长",
       5, 100, 12000, "市侩圆滑", "treasure", "商会会长，只谈买卖不谈道义"),
    _n("npc_sh_02", "铁算盘", 1, 3, "青云坊市客栈", "四海散修商会", "大执事",
       10, 0, 900, "贪财好利", "treasure", "账房一把手，只认灵石"),
    _n("npc_sh_03", "柳三娘", 1, 2, "青云坊市客栈", "四海散修商会", "丹铺掌柜",
       0, 40, 300, "谨慎多疑", "treasure", "丹药摊主，怕惹祸上身"),
    _n("npc_sh_04", "陆仁贾", 1, 1, "青云坊市客栈", "四海散修商会", "牙人",
       0, 20, 420, "市侩圆滑", "social", "坊市牙人，消息灵通"),
    _n("npc_sh_05", "驼爷", 2, 0, "青云坊市客栈", "四海散修商会", "镖头",
       20, 50, 700, "豪爽仗义", "patrol", "走货镖头，刀口舔血"),
    _n("npc_sh_06", "小雀儿", 1, 0, "青云坊市客栈", "四海散修商会", "伙计",
       0, 5, 60, "谨慎多疑", "social", "客栈跑堂，爱听墙角"),

    # ================= 无主/野外/海外 =================
    _n("npc_wd_01", "采药翁", 1, 1, "落霞山灵泉", None, "散修",
       0, 25, 180, "谨慎多疑", "survive", "独行采药，怕劫修"),
    _n("npc_wd_02", "赤练子", 2, 0, "落霞山灵泉", None, "散修",
       90, 0, 500, "阴鸷记仇", "revenge", "被仇家毁过道基"),
    _n("npc_wd_03", "山君", 2, 2, "落霞山灵泉", None, "妖修",
       110, 0, 300, "莽撞好斗", "patrol", "虎妖化形，占山为王"),
    _n("npc_wd_04", "蜃楼客", 2, 2, "万星古岛", None, "散修",
       40, 10, 700, "淡泊避世", "treasure", "海外散人，寻上古遗宝"),
    _n("npc_wd_05", "海娘子", 3, 0, "万星古岛", None, "散修",
       70, 20, 1500, "市侩圆滑", "treasure", "乱星海女海盗，见风使舵"),
    _n("npc_wd_06", "盲眼琴师", 2, 3, "古修士洞府残址", None, "散修",
       0, 90, 400, "淡泊避世", "social", "琴音可乱人心，来历成谜"),
    _n("npc_wd_07", "盗墓贼·孙九", 1, 2, "古修士洞府残址", None, "散修",
       55, 0, 250, "贪财好利", "treasure", "专刨无主洞府"),
    _n("npc_wd_08", "青州游侠·燕十三", 2, 1, "青云山外围", None, "散修",
       15, 70, 380, "豪爽仗义", "social", "行侠仗义，居无定所"),
]


def seed_roster(force_mind: bool = False) -> Dict[str, int]:
    init_db()
    created = skipped = minds = 0

    for row in ROSTER:
        existing = CharacterRepository.get_by_user_id(row["uid"])
        is_new = False
        if existing and existing.status != CharacterStatus.DEAD:
            char = existing
            skipped += 1
            # 若缺编制则补 rank
            if row.get("rank") and char.sect_rank != row["rank"] and force_mind:
                char.sect_rank = row["rank"]
                CharacterRepository.save(char)
        else:
            char = WorldClock.create_new_character(row["uid"], row["name"])
            char.realm.tier = row["tier"]
            char.realm.sub_tier = row["sub"]
            char.realm.current_exp = 0
            char.location = row["loc"]
            char.sect = row["sect"]
            char.sect_rank = row.get("rank") or (
                "散修" if not row["sect"] else "外门弟子"
            )
            char.karma.sin_value = row["sin"]
            char.karma.merit_value = row["merit"]
            char.spirit_stones = row["stones"]
            if row["sin"] >= 80:
                import time as _t
                from config import SECONDS_PER_GAME_YEAR
                char.karma.blood_mark_until = _t.time() + 3 * SECONDS_PER_GAME_YEAR
            CharacterRepository.save(char)
            created += 1
            is_new = True

        mind = NpcMindRepository.get(char.id)
        if force_mind or not mind:
            NpcMindRepository.upsert(
                char.id, row["personality"],
                {"roster_note": row["note"], "rank": row.get("rank", "")},
                (mind or {}).get("attitudes") or {},
            )
            minds += 1
        else:
            traits = dict(mind.get("traits") or {})
            if "roster_note" not in traits:
                traits["roster_note"] = row["note"]
                traits["rank"] = row.get("rank", "")
                NpcMindRepository.upsert(
                    char.id, mind["personality"], traits, mind.get("attitudes") or {}
                )

        if is_new or force_mind:
            prev = NpcAgendaRepository.get(char.id) or {}
            NpcAgendaRepository.upsert(
                npc_id=char.id,
                npc_name=char.name,
                agenda_type=row["agenda"],
                target_hint=row.get("sect") or "",
                note=row["note"],
                state="active",
                last_tick=prev.get("last_tick", 0),
                progress=prev.get("progress", 0),
                extra=prev.get("extra") or {},
            )
            minds += 1
        elif not NpcAgendaRepository.get(char.id):
            ensure_agenda(char)

    return {"created": created, "skipped": skipped, "minds_updated": minds}


def roster_summary() -> List[str]:
    lines = []
    for row in ROSTER:
        sect = row["sect"] or "散修"
        rank = row.get("rank") or ""
        lines.append(
            f"{row['name']} | {sect}·{rank} | t{row['tier']}{row['sub']} | {row['loc']} | "
            f"业{row['sin']} | {row['personality']} | {row['note']}"
        )
    return lines


def roster_by_sect() -> Dict[str, List[str]]:
    """按宗门分组预览"""
    groups: Dict[str, List[str]] = {}
    for row in ROSTER:
        sect = row["sect"] or "无主/散修"
        groups.setdefault(sect, []).append(
            f"{row.get('rank') or '散修'}·{row['name']}（{row['personality']}）"
        )
    return groups


if __name__ == "__main__":
    r = seed_roster()
    print(f"seed: {r} | 阵容人数: {len([x for x in ROSTER if x['uid'] != 'npc_02'])}")
    for sect, members in roster_by_sect().items():
        print(f"\n【{sect}】{len(members)}人")
        for m in members:
            print(f"  · {m}")
