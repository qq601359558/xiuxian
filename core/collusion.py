"""
NPC 同场合谋事件：规则定结局，AI 宁少而准写叙事
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import CharacterRepository, KarmaLinkRepository, WorldStateRepository
from core.bounty import KarmaLink
from core import rumors
from core.npc_mind import attitude_toward, ensure_mind, _is_npc

_COOLDOWN_KEY = "npc_collusion_cd"
_COOLDOWN_S = 30 * 60.0


def ensure_link(
    a: Character,
    b: Character,
    link_type: str,
    note: str = "",
    now: Optional[float] = None,
) -> KarmaLink:
    t = now if now is not None else time.time()
    for link in KarmaLinkRepository.list_all():
        if link.link_type == link_type and link.involves(a.id) and link.involves(b.id):
            link.strength += 1
            if note:
                link.note = f"{link.note}；{note}" if link.note else note
            KarmaLinkRepository.save(link)
            return link
    link = KarmaLink(
        a_id=a.id,
        a_name=a.name,
        b_id=b.id,
        b_name=b.name,
        link_type=link_type,
        strength=1,
        note=note or f"{a.name}与{b.name}：{link_type}",
        created_at=t,
    )
    KarmaLinkRepository.save(link)
    return link


def links_of(char_id: str) -> List[KarmaLink]:
    return [l for l in KarmaLinkRepository.list_all() if l.involves(char_id)]


def links_between(a_id: str, b_id: str) -> List[KarmaLink]:
    return [
        l
        for l in KarmaLinkRepository.list_all()
        if l.involves(a_id) and l.involves(b_id)
    ]


def format_links(char: Character) -> str:
    ls = links_of(char.id)
    if not ls:
        return f"【因果】{char.name} 暂无显著恩怨牵缠。"
    lines = [f"【因果】{char.name} 的牵缠："]
    for l in ls[:12]:
        oid, oname = l.other_side(char.id)
        lines.append(f"· {l.link_type} · {oname} · 强度{l.strength}  {l.note or ''}")
    return "\n".join(lines)


def _pair_key(a_id: str, b_id: str) -> str:
    return ":".join(sorted([a_id, b_id]))


def _cooldown_ok(a_id: str, b_id: str, now: float) -> bool:
    try:
        cds = WorldStateRepository.get(_COOLDOWN_KEY) or {}
    except Exception:
        cds = {}
    key = _pair_key(a_id, b_id)
    last = float(cds.get(key) or 0.0)
    if now - last < _COOLDOWN_S:
        return False
    cds[key] = now
    # 只保留最近 80 对
    if len(cds) > 80:
        items = sorted(cds.items(), key=lambda x: -x[1])[:80]
        cds = dict(items)
    try:
        WorldStateRepository.set(_COOLDOWN_KEY, cds)
    except Exception:
        pass
    return True


def _pick_kind(link: KarmaLink) -> str:
    if link.link_type == "仇":
        return random.choice(["寻仇未遂", "密谈", "分赃不均"])
    if link.link_type in ("恩", "盟"):
        return random.choice(["密谈", "结伴而行"])
    if link.link_type == "师徒":
        return "结伴而行"
    return "密谈"


_LOCAL_LINES = {
    "密谈": "{a}与{b}在{loc}低语数句，旋即分开。",
    "寻仇未遂": "{a}盯了{b}半晌，终究按剑未发。",
    "结伴而行": "{a}与{b}在{loc}同行一段，似在交换消息。",
    "分赃不均": "{a}与{b}因分润在{loc}争执数声，拂袖而去。",
}


def try_collude_pair(
    a: Character,
    b: Character,
    now: Optional[float] = None,
    use_ai: bool = True,
) -> Optional[Dict[str, Any]]:
    """同场且有关系边时，小概率产生合谋事件。无边返回 None。"""
    t = now if now is not None else time.time()
    if a.id == b.id or a.location != b.location:
        return None
    if a.status == CharacterStatus.DEAD or b.status == CharacterStatus.DEAD:
        return None
    links = links_between(a.id, b.id)
    if not links:
        return None
    link = links[0]
    if not _cooldown_ok(a.id, b.id, t):
        return None
    kind = _pick_kind(link)
    loc = a.location

    # 仇边且同图非安全区：不止文案，尝试真实寻仇结算
    deep = None
    if link.link_type in ("仇", "血仇") and kind in ("寻仇未遂", "分赃不均"):
        try:
            from core.jianghu_sim import JianghuSimulator
            from config import WORLD_LOCATIONS as _WL

            if not _WL.get(loc, {}).get("is_safe", True):
                for actor, target in ((a, b), (b, a)):
                    if not _is_npc(actor) or actor.status == CharacterStatus.DEAD:
                        continue
                    if target.status == CharacterStatus.DEAD:
                        continue
                    deep = JianghuSimulator.resolve_agenda(
                        actor,
                        "revenge",
                        {"target_hint": target.name, "note": f"与{target.name}有仇"},
                        now=t,
                    )
                    if deep.get("acted") and deep.get("outcome") in ("kill", "wounded", "escaped"):
                        kind = "寻仇"
                        break
                    deep = None
        except Exception:
            deep = None

    narrative = ""
    source = "rule"
    if deep and deep.get("narrative"):
        narrative = deep["narrative"][:200]
        source = "rule"
    elif use_ai:
        try:
            from ai.gateway import _chat_json, ai_ready

            if ai_ready():
                try:
                    from core.npc_personas import persona_prompt_block

                    pa = persona_prompt_block(a) if _is_npc(a) else ""
                    pb = persona_prompt_block(b) if _is_npc(b) else ""
                except Exception:
                    pa = pb = ""
                data = _chat_json(
                    "你是修仙世界旁白。只输出 JSON。\n"
                    f"两名修士在【{loc}】发生一幕：{kind}。关系：{link.link_type}（{link.note}）。\n"
                    f"A：{a.name}（{a.realm.name}） B：{b.name}（{b.realm.name}）\n"
                    + (f"A人设：{pa}\n" if pa else "")
                    + (f"B人设：{pb}\n" if pb else "")
                    + "输出 {\"narrative\":\"80字内\"}。不改数值、不虚构第三人；对白口吻符合各自人设。"
                    , timeout=15.0
                )
                if data and data.get("narrative"):
                    narrative = str(data["narrative"])[:200]
                    source = "ai"
        except Exception:
            narrative = ""
    if not narrative:
        narrative = _LOCAL_LINES.get(kind, "{a}与{b}在{loc}有所交集。").format(
            a=a.name, b=b.name, loc=loc
        )

    # 门禁效果：态度微调
    try:
        from core.npc_mind import shift_attitude

        if _is_npc(a) and not _is_npc(b):
            shift_attitude(a, b.id, 3 if kind != "寻仇未遂" else -5, reason=kind)
        if _is_npc(b) and not _is_npc(a):
            shift_attitude(b, a.id, 3 if kind != "寻仇未遂" else -5, reason=kind)
        if _is_npc(a) and _is_npc(b):
            ensure_mind(a)
            ensure_mind(b)
    except Exception:
        pass

    rumors.note_collusion(a.name, b.name, kind, loc)
    try:
        from storage.db import ChronicleRepository

        ChronicleRepository.record("WORLD", f"{a.name}/{b.name}", f"{kind}于{loc}：{narrative[:40]}")
    except Exception:
        pass
    # 落因果账（合谋/寻仇都是江湖事实）
    try:
        import core.jianghu as jianghu

        if deep:
            try:
                CharacterRepository.save(a)
                CharacterRepository.save(b)
            except Exception:
                pass
        jianghu.append_event(
            kind="collusion",
            actor_ids=[a.id, b.id],
            actor_names=[a.name, b.name],
            location=loc,
            summary=f"{a.name}与{b.name}于{loc}：{kind}",
            rule_result={"kind": kind, "deep_outcome": (deep or {}).get("outcome"), "source": source},
            narrative=narrative[:200],
            source=source,
        )
    except Exception:
        pass

    return {
        "kind": kind,
        "narrative": narrative,
        "source": source,
        "location": loc,
        "a": a.name,
        "b": b.name,
        "acted": True,
        "deep_outcome": (deep or {}).get("outcome"),
    }


def try_collude_in_world(max_pairs: int = 2, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """从同场 NPC 里挑有关系边的对，最多触发 max_pairs 次。"""
    t = now if now is not None else time.time()
    npcs = [c for c in CharacterRepository.list_all_alive() if _is_npc(c)]
    by_loc: Dict[str, List[Character]] = {}
    for n in npcs:
        by_loc.setdefault(n.location, []).append(n)

    out: List[Dict[str, Any]] = []
    for loc, group in by_loc.items():
        if len(group) < 2 or len(out) >= max_pairs:
            continue
        # 随机打乱，找有边的对
        random.shuffle(group)
        for i, a in enumerate(group):
            if len(out) >= max_pairs:
                break
            for b in group[i + 1 :]:
                if not links_between(a.id, b.id):
                    continue
                # 约 35% 概率真正触发（宁少而准）
                if random.random() > 0.35:
                    continue
                r = try_collude_pair(a, b, now=t, use_ai=True)
                if r:
                    out.append(r)
                    break
    return out
