"""QA2 修复评审整改回归（本分支新增，非 QA 资产）。

- 评审 S2：QA2-01 的 QA 用例只构造了「死者作 target」方向的反悬赏条目；
  本文件补「死者作 hunter 方向同存全清 + 无关条目保留 + 非 dict 脏条目容错」。
- 评审 M1/S1：CLI LAN_ONLY_COMMANDS 与帮助「局域网专有」行的一致性断言
  （防两份字面量漂移），且派发用小写规范形集合须含 /ai自检（action 在
  派发前已被 .lower()，大写成员 /AI自检 否则永远命中不了）。
"""
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core import hunt
from core.clock import WorldClock
from core.models import CharacterStatus
from storage.db import CharacterRepository, WorldStateRepository, init_db
from server.world import WORLD

WORLD.stop_tick()
init_db()

LOC_A = "青云坊市客栈"


def _tag():
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _char(name, sin=0):
    c = WorldClock.create_new_character(f"q2fx_{name}_{_tag()}", f"Q2F{name}{_tag()}")
    c.location = LOC_A
    if sin:
        c.karma.add_sin(sin)
    CharacterRepository.save(c)
    return c


def _get(cid):
    return CharacterRepository.get_by_id(cid)


def _cleanup(*chars):
    ids = {c.id for c in chars if c}
    if ids:
        orders = hunt._load_orders()
        for tid in list(orders.keys()):
            if tid in ids:
                orders.pop(tid, None)
        hunt._save_orders(orders)
        d = hunt._load()
        for hid in list(d.keys()):
            rec = d[hid]
            tid = rec.get("target_id") if isinstance(rec, dict) else rec
            if hid in ids or tid in ids:
                d.pop(hid, None)
        hunt._save(d)
    for c in chars:
        if c is None:
            continue
        live = _get(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def test_counter_cleanup_hunter_direction_and_unrelated():
    victim = _char("双向犯", sin=120)
    killer = _char("双向主")
    third = _char("双向三")
    other = _char("双向外")
    snap = WorldStateRepository.get(hunt._COUNTER_KEY)
    try:
        v = _get(victim.id)
        v.karma.blood_mark_until = 0.0
        CharacterRepository.save(v)
        assert hunt.is_marked(_get(victim.id))
        assert hunt.accept(_get(killer.id), _get(victim.id).name)["success"]
        cd = dict(snap or {})
        # 死者作 target（键在猎人名下）
        cd[killer.id] = {"target_id": victim.id, "hunter_id": killer.id, "paid": 50}
        # 死者作 hunter（键 == victim.id，其对第三人的反悬赏）
        cd[victim.id] = {"target_id": third.id, "hunter_id": victim.id, "paid": 50}
        # 无关条目（第三人之间）与非 dict 脏条目：必须保留、不得抛错
        cd[third.id] = {"target_id": other.id, "hunter_id": third.id, "paid": 50}
        cd["q2fx_dirty"] = "not-a-dict"
        WorldStateRepository.set(hunt._COUNTER_KEY, cd)

        res = hunt.settle_kill(_get(killer.id), _get(victim.id))
        assert res is not None and res.get("dissolved") is not True, res
        cd2 = WorldStateRepository.get(hunt._COUNTER_KEY) or {}
        assert killer.id not in cd2, "死者作 target 的条目应清"
        assert victim.id not in cd2, "死者作 hunter 的条目应清"
        assert cd2.get(third.id, {}).get("target_id") == other.id, "无关条目不得误删"
        assert cd2.get("q2fx_dirty") == "not-a-dict", "脏条目应原样保留且不抛错"
        print("✓ 反悬赏双向全清 + 无关/脏条目保留")
    finally:
        if snap is None:
            WorldStateRepository.set(hunt._COUNTER_KEY, {})
        else:
            WorldStateRepository.set(hunt._COUNTER_KEY, snap)
        _cleanup(victim, killer, third, other)


def test_cli_lan_only_set_help_and_lower_consistency():
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("cli_main_q2fx", root / "cli" / "main.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    lan = set(m.LAN_ONLY_COMMANDS)
    lower = set(m.LAN_ONLY_COMMANDS_LOWER)
    assert lower == {c.lower() for c in lan}
    assert "/ai自检" in lower, "派发小写集须含 /ai自检（评审 M1）"
    assert len(lan) == 28, f"LAN_ONLY 应为既有 9 + QA2-03 的 19 = 28，实际 {len(lan)}"
    src = (root / "cli" / "main.py").read_text(encoding="utf-8")
    mm = re.search(r"局域网专有：([^\n]*)", src)
    assert mm, "帮助应有局域网专有声明行"
    documented = {t.lower() for t in re.findall(r"/[^\s/]+", mm.group(1))}
    lan_lower = {c.lower() for c in lan}
    assert lan_lower <= documented, f"帮助行漏声明：{sorted(lan_lower - documented)}"
    extra = documented - lan_lower
    assert extra <= {"/dim]"}, f"帮助行多出未在集合内的声明：{sorted(extra)}"
    print("✓ LAN_ONLY 集合 ↔ 帮助声明行一致（28 个），小写派发集含 /ai自检")
