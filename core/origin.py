"""
简版人生开局（game-feel-phase1 §3）：纯规则、零 AI 的出身包生成器。

口径要点（Spec 写死）：
- 全随机 + 全部 bounds + 总分中位带 [−20,20] 钳制 + 近 3 世防重；
  玩家无 reroll 入口，随机全部经入参 rng（测试可播种复算）。
- 落账全走既有设施：灵石赋值（建角发放口径）、旧债直写 PromiseRepository
  （kind=debt，不走 make_promise 同场门禁）、初始关系走 shift_attitude
  (reason="origin")、foe 另加 KarmaLink 种子边（strength=1 不起链）。
- 幂等闸：char.origin 非空即返回既有块，不重生成、不重复落账。
- 本模块不落盘 char：灵石/落点/目标都在入参 char 内存对象上完成，
  由调用方（join 锁外段 / reincarnate）以 CharacterRepository.save 收尾。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import SECONDS_PER_GAME_DAY, SECTS_CONFIG
from core.models import Character, CharacterStatus

# ---------------- 家世池（§3.3 定稿 12 类） ----------------
# tone: 灵石基调 low / mid_low / mid / high
FAMILIES: List[Dict[str, Any]] = [
    {"name": "寒门农家", "text": "山野寒门之子", "birthplaces": ["青云坊市客栈", "落霞山灵泉"], "bias": ["家道中落", "幼年奇遇"], "tone": "low"},
    {"name": "药农", "text": "青石镇药农之子", "birthplaces": ["青云坊市客栈", "落霞山灵泉"], "bias": ["父辈旧债", "宝物遗失"], "tone": "mid"},
    {"name": "商贾", "text": "行商之子", "birthplaces": ["青云坊市客栈"], "bias": ["父辈旧债", "家道中落"], "tone": "high"},
    {"name": "书香门第", "text": "书香门第之后", "birthplaces": ["青云坊市客栈", "青云宗外门山门"], "bias": ["师门旧怨", "幼年奇遇"], "tone": "mid"},
    {"name": "宗门旁支", "text": "宗门旁支子弟", "birthplaces": ["青云宗外门山门", "万剑仙门峰"], "bias": ["师门旧怨", "族仇未雪"], "tone": "mid"},
    {"name": "罪族遗孤", "text": "没落罪族遗孤", "birthplaces": ["青云坊市客栈"], "bias": ["族仇未雪", "背案在身"], "tone": "mid_low"},
    {"name": "猎户", "text": "山野猎户之子", "birthplaces": ["落霞山灵泉", "青云坊市客栈"], "bias": ["幼年奇遇", "恩人救命"], "tone": "mid_low"},
    {"name": "流民", "text": "流民之子", "birthplaces": ["青云坊市客栈"], "bias": ["家道中落", "恩人救命"], "tone": "low"},
    {"name": "渔户", "text": "泽国渔户之子", "birthplaces": ["落霞山灵泉", "青云坊市客栈"], "bias": ["幼年奇遇", "宝物遗失"], "tone": "mid"},
    {"name": "铁匠", "text": "坊市铁匠之子", "birthplaces": ["青云坊市客栈"], "bias": ["父辈旧债", "宝物遗失"], "tone": "mid"},
    {"name": "镖师之后", "text": "镖局子弟", "birthplaces": ["青云坊市客栈", "万剑仙门峰"], "bias": ["族仇未雪", "背案在身"], "tone": "mid"},
    {"name": "医户", "text": "杏林医户之子", "birthplaces": ["青云坊市客栈", "落霞山灵泉"], "bias": ["恩人救命", "父辈旧债"], "tone": "mid"},
]

# ---------------- 旧事模板族（§3.4 定稿 8 类） ----------------
# bind: 绑定角色（creditor 由债路径单独处理，不占关系名额）
STORY_BIND = {
    "父辈旧债": "creditor",
    "家道中落": "witness",
    "幼年奇遇": "witness",
    "族仇未雪": "foe",
    "恩人救命": "kin",
    "背案在身": "witness",
    "师门旧怨": "foe",
    "宝物遗失": "witness",
}
STORY_SUMMARY = {
    "父辈旧债": "父辈欠下{npc}一笔旧账，父债子偿",
    "家道中落": "家道中落，祖产散尽，只剩一口气",
    "幼年奇遇": "幼年曾在山中遇异事，醒来只记得{npc}的名字",
    "族仇未雪": "族中长辈死于{npc}之手/其同门之手，旧账未清",
    "恩人救命": "幼年落难，蒙{npc}出手相救，恩未报",
    "背案在身": "身上背着一桩说不清的旧案，{npc}知情",
    "师门旧怨": "长辈与{npc}一门有旧怨，绵延至今",
    "宝物遗失": "家传之物遗失多年，传言与{npc}有关",
}
RELIC_BY_FAMILY = {"药农": "祖传药碾", "铁匠": "祖传锻锤", "渔户": "避水珠"}
DEFAULT_RELIC = "家传玉佩"

# 关系构成模式（§3.6）
RELATION_PATTERNS = [
    ["kin", "foe"],
    ["kin", "witness"],
    ["kin", "foe", "witness"],
    ["kin", "kin", "foe"],
    ["kin", "foe", "witness", "witness"],
]

STONES_BY_TONE = {
    "low": (80, 150),
    "mid_low": (90, 180),
    "mid": (100, 220),
    "high": (140, 260),
}

_HOME_WORD = {"药农": "药圃", "商贾": "商号", "铁匠": "铁铺", "医户": "医馆", "渔户": "渔家"}


def select_fate_proposition(
    *,
    has_debt: bool,
    debt_promise_id: str = "",
    has_foe: bool,
    foe_id: str = "",
    foe_name: str = "",
    old_story_kind: str = "",
    family: str = "",
    item_ref: str = "",
    unfinished: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """终局命题选取（§3.7 优先级序写死）：
    未竟之志候选（可重实例化时）> debt_clear > foe_reckoning >
    lost_relic > family_revive > sect_inner > stand_firm。
    返回 (kind, 文案, check)。"""
    un = unfinished or {}
    uk = un.get("kind") or ""
    un_text = un.get("text") or ""
    un_check = un.get("check") or {}
    if uk == "debt_clear" and has_debt:
        return "debt_clear", un_text or f"还清旧债，护住{_HOME_WORD.get(family, '家业')}", {
            "kind": "promise_settled", "ref": debt_promise_id}
    if uk == "foe_reckoning" and has_foe:
        return "foe_reckoning", un_text or f"向{foe_name}讨个说法，让其再不敢轻慢你", {
            "kind": "npc_attitude_at_least", "npc_id": foe_id, "value": 0}
    if uk == "lost_relic":
        ref = un_check.get("item_ref") or item_ref
        if ref:
            return "lost_relic", un_text or f"寻回遗失的{ref}", {
                "kind": "item_in_bag_at_death", "item_ref": ref}
    if uk == "family_revive":
        return "family_revive", un_text or "攒下 500 灵石，重振家业", {
            "kind": "stones_at_least", "amount": 500}
    if uk == "sect_inner":
        return "sect_inner", un_text or "拜入一门，站稳脚跟", {
            "kind": "sect_joined", "ref": ""}
    if uk == "stand_firm":
        return "stand_firm", un_text or "筑基立身，不再任人摆布", {
            "kind": "realm_at_least", "tier": 2}
    if has_debt:
        return "debt_clear", f"还清旧债，护住{_HOME_WORD.get(family, '家业')}", {
            "kind": "promise_settled", "ref": debt_promise_id}
    if has_foe:
        return "foe_reckoning", f"向{foe_name}讨个说法，让其再不敢轻慢你", {
            "kind": "npc_attitude_at_least", "npc_id": foe_id, "value": 0}
    if old_story_kind == "宝物遗失" and item_ref:
        return "lost_relic", f"寻回遗失的{item_ref}", {
            "kind": "item_in_bag_at_death", "item_ref": item_ref}
    if old_story_kind == "家道中落" or family in ("商贾", "药农", "医户"):
        return "family_revive", "攒下 500 灵石，重振家业", {
            "kind": "stones_at_least", "amount": 500}
    if family == "宗门旁支":
        return "sect_inner", "拜入一门，站稳脚跟", {"kind": "sect_joined", "ref": ""}
    return "stand_firm", "筑基立身，不再任人摆布", {"kind": "realm_at_least", "tier": 2}


def _is_npc(c: Character) -> bool:
    uid = str(c.user_id or "")
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def _alive(c: Character, now: float) -> bool:
    return c.status != CharacterStatus.DEAD and not c.lifespan.is_dead(now)


def _score(stones: int, debt_amount: int, relations: List[Dict[str, Any]],
           gates: List[Dict[str, Any]]) -> int:
    stones_part = round(((stones - 150) - debt_amount) / 10)
    relation_part = round(sum(r["init_value"] for r in relations) / 10)
    gate_part = 0
    for g in gates:
        if g["effect"] == "favored":
            gate_part += 4 if g["gate"] == "place" else 8
        elif g["effect"] == "closed":
            gate_part -= 8
    return int(stones_part + relation_part + gate_part)


class OriginEngine:
    """出身包生成器（纯规则；随机经 rng 入参）。"""

    @staticmethod
    def _npc_pool(now: float) -> List[Character]:
        """NPC 池 = 花名册 37 人（§3.1）：按 uid 逐个索引查，避免全表扫描；
        花名册外 NPC（ai_npc_ 等）不入出身池。"""
        from storage.db import CharacterRepository

        out: List[Character] = []
        try:
            from core.npc_roster import ROSTER

            uids = [row.get("uid", "") for row in ROSTER]
        except Exception:
            uids = []
        for uid in uids:
            if not uid:
                continue
            try:
                c = CharacterRepository.get_by_user_id(uid)
            except Exception:
                c = None
            if c is not None and _is_npc(c) and _alive(c, now):
                out.append(c)
        return out

    @staticmethod
    def _creditor_pool(pool: List[Character]) -> List[Character]:
        """债主池（§3.5）：sect=四海散修商会 或 agenda=treasure。"""
        agenda_by_uid: Dict[str, str] = {}
        try:
            from core.npc_roster import ROSTER

            for row in ROSTER:
                agenda_by_uid[row.get("uid", "")] = row.get("agenda", "")
        except Exception:
            pass
        out = []
        for c in pool:
            if c.sect == "四海散修商会" or agenda_by_uid.get(str(c.user_id)) == "treasure":
                out.append(c)
        return out

    @staticmethod
    def _build_package(
        char: Character,
        rng: random.Random,
        now: float,
        covered_ids: set,
        force_family: Optional[str] = None,
        force_story: Optional[str] = None,
        pool: Optional[List[Character]] = None,
        vendetta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if pool is None:
            pool = OriginEngine._npc_pool(now)
        fam = None
        if force_family:
            fam = next((f for f in FAMILIES if f["name"] == force_family), None)
        if fam is None:
            fam = rng.choice(FAMILIES)
        if force_story and force_story in STORY_BIND:
            story_kind = force_story
        else:
            kinds = list(STORY_BIND.keys())
            weights = [3 if k in fam["bias"] else 1 for k in kinds]
            story_kind = rng.choices(kinds, weights=weights, k=1)[0]
        birthplace = rng.choice(fam["birthplaces"])
        item_ref = ""
        if story_kind == "宝物遗失":
            item_ref = RELIC_BY_FAMILY.get(fam["name"], DEFAULT_RELIC)

        # ---- 债 ----
        has_debt = story_kind == "父辈旧债" or rng.random() < 0.35
        creditor: Optional[Character] = None
        debt_amount = 0
        if has_debt:
            cands = [c for c in OriginEngine._creditor_pool(pool) if c.id not in covered_ids]
            if cands:
                creditor = rng.choice(cands)
                debt_amount = rng.randint(30, 120)
            else:
                has_debt = False

        # ---- 关系 ----
        relations: List[Dict[str, Any]] = []
        used: set = set(covered_ids)

        def pick(role: str) -> Optional[Character]:
            cands = []
            for c in pool:
                if c.id in used:
                    continue
                if role == "foe" and c.realm.tier > char.realm.tier + 1:
                    continue
                if role == "kin" and c.realm.tier > 3:
                    continue
                if role == "witness" and c.realm.tier > 4:
                    continue
                cands.append(c)
            if not cands:
                return None
            if role == "kin":
                pref = [c for c in cands
                        if c.location == birthplace or c.sect == "四海散修商会" or not c.sect]
                if pref:
                    cands = pref
            return rng.choice(cands)

        def add_rel(npc: Character, role: str) -> None:
            if role == "kin":
                v = rng.randint(25, 55)
            elif role == "foe":
                v = rng.randint(-45, -15)
            else:
                v = rng.randint(-10, 15)
            used.add(npc.id)
            relations.append({
                "npc_id": npc.id, "npc_name": npc.name, "role": role,
                "init_value": v, "is_creditor": bool(creditor and npc.id == creditor.id),
            })

        # ---- 世仇植入（game-feel-phase2 §4.3）：先试 vendetta 植入者，
        # 过既有硬校验（在世=已在 pool / bounds / 未被影子覆盖，
        # shadow_covered 标记的来源 3 植入者例外，落账时不叠加 shift）
        # 则直接占 foe 名额；不通过丢弃走原随机并记 vendetta_dropped。
        vendetta_npc: Optional[Character] = None
        vendetta_dropped = False
        vendetta_drop_reason = ""
        if vendetta and vendetta.get("npc_id"):
            cand = next((c for c in pool if c.id == vendetta["npc_id"]), None)
            if cand is None:
                vendetta_dropped, vendetta_drop_reason = True, "not_alive"
            elif cand.realm.tier > char.realm.tier + 1:
                vendetta_dropped, vendetta_drop_reason = True, "over_bounds"
            elif cand.id in used and not vendetta.get("shadow_covered"):
                vendetta_dropped, vendetta_drop_reason = True, "shadow_covered"
            else:
                vendetta_npc = cand
                used.add(cand.id)
                relations.append({
                    "npc_id": cand.id, "npc_name": cand.name, "role": "foe",
                    "init_value": rng.randint(-45, -30),
                    "is_creditor": bool(creditor and cand.id == creditor.id),
                    "vendetta": True,
                    "vendetta_for": str(vendetta.get("for_name") or cand.name),
                })

        bind_role = STORY_BIND[story_kind]
        story_npc: Optional[Character] = None
        if bind_role == "creditor":
            story_npc = creditor
        elif bind_role == "foe" and vendetta_npc is not None:
            story_npc = vendetta_npc
        else:
            story_npc = pick(bind_role)
            if story_npc is not None:
                add_rel(story_npc, bind_role)
        if (story_kind == "背案在身" and vendetta_npc is None
                and rng.random() < 0.5 and len(relations) < 4):
            extra_foe = pick("foe")
            if extra_foe is not None:
                add_rel(extra_foe, "foe")
                if story_npc is None:
                    story_npc = extra_foe
        pattern = rng.choice(RELATION_PATTERNS)
        for role in pattern:
            if role == "foe" and vendetta_npc is not None:
                continue  # 世仇已占 foe 名额，pattern 其余 foe 位不再另抽（§4.3）
            have = sum(1 for r in relations if r["role"] == role)
            want = pattern.count(role)
            while have < want and len(relations) < 4:
                npc = pick(role)
                if npc is None:
                    break
                add_rel(npc, role)
                have += 1
        if story_npc is None and relations:
            story_npc = next(
                (next(c for c in pool if c.id == r["npc_id"]) for r in relations), None)
        if story_npc is None and creditor is not None:
            story_npc = creditor

        # ---- 路径开关（0–2 个，closed 至多 1） ----
        gates: List[Dict[str, Any]] = []
        n_gates = rng.choice([0, 1, 1, 2, 2])
        closed_used = False
        rel_sects = set()
        for r in relations:
            npc = next((c for c in pool if c.id == r["npc_id"]), None)
            if npc is not None and npc.sect:
                rel_sects.add(npc.sect)
        sect_cands = [s for s in SECTS_CONFIG if s != "四海散修商会" and s not in rel_sects]
        if n_gates >= 1 and sect_cands:
            target = rng.choice(sect_cands)
            if not closed_used and rng.random() < 0.4:
                gates.append({"gate": "sect", "target_ref": target, "effect": "closed"})
                closed_used = True
            else:
                gates.append({"gate": "sect", "target_ref": target, "effect": "favored"})
        if len(gates) < 2 and rng.random() < 0.5:
            # vendor 以态度为载体：favored 须 kin 档、closed 须 foe 档
            vendor_done = False
            for r in relations:
                npc = next((c for c in pool if c.id == r["npc_id"]), None)
                if npc is None or npc.sect != "四海散修商会":
                    continue
                if r["role"] == "kin":
                    # vendor 只增 target_name（NPC 名）：target_ref 为 NPC id，
                    # 出身卡呈现需人名（前端增补工单）；sect 的 target_ref 本就是宗门名不动
                    gates.append({"gate": "vendor", "target_ref": npc.id,
                                  "target_name": npc.name, "effect": "favored"})
                    vendor_done = True
                    break
                if r["role"] == "foe" and not closed_used:
                    gates.append({"gate": "vendor", "target_ref": npc.id,
                                  "target_name": npc.name, "effect": "closed"})
                    closed_used = True
                    vendor_done = True
                    break
            if not vendor_done and len(gates) < 2:
                gates.append({"gate": "place", "target_ref": birthplace, "effect": "favored"})
        gates = gates[:2]

        # ---- 灵石 ----
        lo, hi = STONES_BY_TONE[fam["tone"]]
        stones_final = rng.randint(lo, hi)
        stones_final = max(80, min(260, stones_final))

        score = _score(stones_final, debt_amount, relations, gates)
        foe_rel = next((r for r in relations if r["role"] == "foe"), None)
        primary_id = ""
        if foe_rel:
            primary_id = foe_rel["npc_id"]
        elif creditor is not None:
            primary_id = creditor.id
        elif relations:
            primary_id = relations[0]["npc_id"]
        signature = f"{fam['name']}|{story_kind}|{primary_id}|{'debt' if has_debt else 'nodebt'}"
        summary = STORY_SUMMARY[story_kind].format(npc=story_npc.name if story_npc else "一位故人")
        origin: Dict[str, Any] = {
            "family": fam["name"],
            "family_text": fam["text"],
            "signature": signature,
            "birthplace": birthplace,
            "stones_final": stones_final,
            "debt": (
                {
                    "creditor_npc_id": creditor.id,
                    "creditor_name": creditor.name,
                    "amount": debt_amount,
                    "promise_id": "",
                } if has_debt and creditor is not None else None
            ),
            "relations": relations,
            "old_story": {
                "kind": story_kind,
                "npc_id": story_npc.id if story_npc else "",
                "item_ref": item_ref,
                "summary": summary,
            },
            "path_gates": gates,
            "strength_score": score,
            "short_goal_id": "",
            "fate_goal_id": "",
            "fate_text": "",
            "extreme_bad": score <= -15,
            "dedup_retries": 0,
            "generated_at": now,
            "life_no": 1,
        }
        if vendetta_dropped:
            origin["vendetta_dropped"] = True
            origin["vendetta_drop_reason"] = vendetta_drop_reason
        return origin

    @staticmethod
    def generate_for_new_life(
        char: Character,
        account=None,
        *,
        rng: Optional[random.Random] = None,
        now: Optional[float] = None,
        force_family: Optional[str] = None,
        force_story: Optional[str] = None,
        vendetta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """为新一世生成出身包并落账（不落盘 char，调用方统一 save）。

        幂等闸：char.origin 非空即原样返回。生成失败由调用方 try/except
        兜底（本函数内部落账点各自尽力而为）。
        """
        if getattr(char, "origin", None):
            return char.origin
        r = rng if rng is not None else random.Random()
        t = now if now is not None else time.time()

        traces = list(getattr(account, "traces", None) or []) if account is not None else []
        recent_sigs = {
            getattr(tr, "origin_signature", "")
            for tr in traces[-3:] if getattr(tr, "origin_signature", "")
        }
        covered_ids: set = set()
        if account is not None and traces:
            try:
                from core.inheritance import applied_shadow_entries

                for e in applied_shadow_entries(account, traces[-1]):
                    covered_ids.add(e["npc_id"])
            except Exception:
                covered_ids = set()
        unfinished = {}
        if traces:
            unfinished = getattr(traces[-1], "unfinished_prop", None) or {}

        # ---- 总分钳制 + 防重（生成器内部重抽，玩家无 reroll） ----
        pool = OriginEngine._npc_pool(t)
        pkg: Optional[Dict[str, Any]] = None
        last: Optional[Dict[str, Any]] = None
        dedup_retries = 0
        tries = 0
        while tries < 30:
            tries += 1
            cand = OriginEngine._build_package(
                char, r, t, covered_ids,
                force_family=force_family, force_story=force_story, pool=pool,
                vendetta=vendetta)
            last = cand
            if not (-20 <= cand["strength_score"] <= 20):
                if tries >= 20:
                    break  # 走确定性修正
                continue
            if cand["signature"] in recent_sigs:
                if dedup_retries < 10:
                    dedup_retries += 1
                    continue
                cand["dedup_exhausted"] = True
                pkg = cand
                break
            pkg = cand
            break
        if pkg is None:
            pkg = last
            # 确定性修正：stones 向 150 方向逐 10 调整至入带
            guard = 0
            while pkg is not None and not (-20 <= pkg["strength_score"] <= 20) and guard < 40:
                guard += 1
                cur = pkg["stones_final"]
                nxt = cur - 10 if cur > 150 else cur + 10
                if nxt == cur or not (80 <= nxt <= 260):
                    break
                pkg["stones_final"] = nxt
                pkg["strength_score"] = _score(
                    nxt, pkg["debt"]["amount"] if pkg["debt"] else 0,
                    pkg["relations"], pkg["path_gates"])
            if pkg is not None:
                pkg["score_clamped"] = True
                # 钳制路径下防重无从重抽：signature 仍撞近世 → 诚实降级标记
                # （§3.6 防重口径：耗尽须记 dedup_exhausted，不得静默同命）
                if pkg["signature"] in recent_sigs:
                    pkg["dedup_exhausted"] = True
        assert pkg is not None
        pkg["dedup_retries"] = dedup_retries
        pkg["life_no"] = (int(getattr(account, "total_lives", 0) or 0) + 1) if account is not None else 1
        pkg["extreme_bad"] = pkg["strength_score"] <= -15

        # ---------------- 落账 ----------------
        from storage.db import CharacterRepository

        char.spirit_stones = int(pkg["stones_final"])
        char.location = pkg["birthplace"]

        # 旧债：生成器直写仓储（§3.5，不走 make_promise）
        promise_id = ""
        if pkg["debt"]:
            try:
                from core.promises import Promise, PromiseStatus
                from storage.db import PromiseRepository

                p = Promise(
                    promiser_id=char.id,
                    promiser_name=char.name,
                    promisee_id=pkg["debt"]["creditor_npc_id"],
                    promisee_name=pkg["debt"]["creditor_name"],
                    promisee_is_npc=True,
                    kind="debt",
                    param=str(pkg["debt"]["amount"]),
                    desc=f"旧债：欠{pkg['debt']['amount']} 灵石（出身）",
                    status=PromiseStatus.ACTIVE,
                    created_at=t,
                    activated_at=t,
                    deadline=t + 10 * SECONDS_PER_GAME_DAY,
                )
                PromiseRepository.save(p)
                promise_id = p.id
                pkg["debt"]["promise_id"] = promise_id
            except Exception:
                pkg["debt"] = None

        char.origin = pkg

        # 初始关系：逐人 shift_attitude(reason="origin")；foe 另加种子边
        foe_npc = None
        foe_rel: Optional[Dict[str, Any]] = None
        for rel in pkg["relations"]:
            npc = CharacterRepository.get_by_id(rel["npc_id"])
            if npc is None:
                continue
            # 世仇 + 影子覆盖同人（VD-05）：态度以影子值为准，
            # origin 不对其再调 shift_attitude（防双重落账）。
            if not (rel.get("vendetta") and rel["npc_id"] in covered_ids):
                try:
                    from core.npc_mind import shift_attitude

                    shift_attitude(npc, char.id, int(rel["init_value"]), reason="origin")
                except Exception:
                    pass
            if rel["role"] == "foe" and foe_npc is None:
                foe_npc = npc
                foe_rel = rel
        if foe_npc is not None:
            try:
                from core.collusion import ensure_link

                if foe_rel is not None and foe_rel.get("vendetta"):
                    _for = str(foe_rel.get("vendetta_for") or foe_npc.name)
                    _note = (
                        "世仇：前世血债未清" if _for == foe_npc.name
                        else f"世仇：替{_for}讨前世血债")
                else:
                    _note = f"出身旧怨：{pkg['old_story']['kind']}"
                ensure_link(char, foe_npc, "仇", note=_note)
            except Exception:
                pass

        # 极端坏命种子：先 add_opportunity，后挂 checked 目标（§3.8 次序）
        if pkg["extreme_bad"]:
            try:
                from core.goals import GoalEngine

                res = GoalEngine.add_opportunity(
                    char, "逆袭之机",
                    f"命途多舛，天道另开一线：{pkg['old_story']['summary']}")
                pkg["extreme_bad_seed"] = bool(res.get("success"))
            except Exception:
                pkg["extreme_bad_seed"] = False

        # ---- 目标：短期（§3.7 优先级）+ 终局命题 ----
        from core.goals import GoalEngine

        foe_rel = next((x for x in pkg["relations"] if x["role"] == "foe"), None)
        sect_favored = next(
            (g for g in pkg["path_gates"] if g["gate"] == "sect" and g["effect"] == "favored"),
            None)
        if pkg["debt"] and promise_id:
            short = GoalEngine.add_checked_goal(
                char, source="origin", title="偿清旧债",
                detail=(
                    f"父辈旧债：欠{pkg['debt']['creditor_name']} {pkg['debt']['amount']} 灵石，"
                    "买其货/赠其物皆可抵债。"),
                check={"kind": "promise_settled", "ref": promise_id},
                deadline_days=10, now=t)
        elif foe_rel:
            short = GoalEngine.add_checked_goal(
                char, source="origin", title="先站稳脚跟",
                detail="境界先到练气中，方有自保之力。",
                check={"kind": "realm_at_least", "tier": 1, "sub": 2},
                deadline_days=15, now=t)
        elif sect_favored:
            short = GoalEngine.add_checked_goal(
                char, source="origin", title=f"拜入{sect_favored['target_ref']}",
                detail=f"出身与{sect_favored['target_ref']}有旧缘，叩关或有优待。",
                check={"kind": "sect_joined", "ref": sect_favored["target_ref"]},
                deadline_days=20, now=t)
        else:
            short = GoalEngine.add_checked_goal(
                char, source="origin", title="攒下安身钱",
                detail="先攒下 100 灵石安身立命。",
                check={"kind": "stones_at_least", "amount": 100},
                deadline_days=7, now=t)
        pkg["short_goal_id"] = short.get("id", "")

        kind, text, check = select_fate_proposition(
            has_debt=bool(pkg["debt"] and promise_id),
            debt_promise_id=promise_id,
            has_foe=foe_rel is not None,
            foe_id=foe_rel["npc_id"] if foe_rel else "",
            foe_name=foe_rel["npc_name"] if foe_rel else "",
            old_story_kind=pkg["old_story"]["kind"],
            family=pkg["family"],
            item_ref=pkg["old_story"].get("item_ref", ""),
            unfinished=unfinished,
        )
        fate_goal = GoalEngine.add_checked_goal(
            char, source="fate", title=text, detail=text,
            check=check, deadline_days=None, now=t)
        pkg["fate_goal_id"] = fate_goal.get("id", "")
        pkg["fate_kind"] = kind
        # 命题一句话随 origin 块下发（origin 块只增字段，前端增补工单）：
        # 出身卡命题行优先读 fate_text，不再回退 entry.lines.fate 造成双前缀
        pkg["fate_text"] = text
        char.origin = pkg
        return pkg
