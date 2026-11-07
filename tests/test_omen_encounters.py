"""奇遇抉择补强（spec: gallery-gameplay §7，验收 E-1~E-8）。

只补强现役 omen_scene：六剧本配图、指定抉择后果接链（诺言/KarmaLink/
江湖痕迹 omen_encounter）、AI 剧本剥离后果且不点亮、后果以场景 id 幂等、
OMEN_COOLDOWN_SECONDS=600 与自然开启日限 5 场（force 豁免）。
隔离方式：唯一 user_id 前缀；场景 KV 每例重置；日计数/图鉴 KV 用例后清理。
"""
import os
import random
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

import config
from core import gallery as gallery_mod
from core import omen_scene as os_mod
from core.clock import WorldClock
from core.gallery_assets import GALLERY_ASSET_KEYS, asset_path
from storage.db import (
    init_db,
    CharacterRepository,
    EventLedgerRepository,
    KarmaLinkRepository,
    PromiseRepository,
    WorldStateRepository,
)

init_db()

DAY = 86400.0
# 二期 §9.8 契约变更：六剧本配图由一期借代键改指 omen/* 专图键
# （唯一事实源 core.gallery_assets.OMEN_SCRIPT_ASSET_KEYS），本表随之修订。
EXPECTED_IMAGES = {
    "black_market": "omen/black-market",
    "orphan_trust": "omen/orphan-trust",
    "spring_dispute": "omen/spring-dispute",
    "stele": "omen/stele",
    "escort_deal": "omen/escort-deal",
    "inn_whisper": "omen/inn-whisper",
}


def _tag():
    return uuid.uuid4().hex[:8]


def _player():
    c = WorldClock.create_new_character(f"oe_{_tag()}", f"遇缘客{_tag()}")
    CharacterRepository.save(c)
    return c


def _npc(name, location):
    npc = WorldClock.create_new_character(f"npc_oe_{_tag()}", name)
    npc.location = location
    CharacterRepository.save(npc)
    return npc


def _relocate(char, location):
    char.location = location
    CharacterRepository.save(char)
    return char


def _reset_scene():
    WorldStateRepository.delete(os_mod._KEY)


def _cleanup(char):
    WorldStateRepository.delete("omen_daily:" + char.id)
    WorldStateRepository.delete(gallery_mod.ATLAS_KEY_PREFIX + str(char.user_id))


def _promises_of(char_id):
    return [p for p in PromiseRepository.list_all() if p.promiser_id == char_id]


def _links_between(a_id, b_id):
    return [
        link for link in KarmaLinkRepository.list_all()
        if link.involves(a_id) and link.involves(b_id)
    ]


def _trace_count(char_id):
    import core.jianghu as jianghu

    rows = jianghu.list_recent(limit=200, kind="omen_encounter")
    return len([r for r in rows if char_id in (r.get("actor_ids") or [])])


# ---------------------------------------------------------------------------
# E-1 六部配图 + E-4 痕迹 + 图鉴点亮（预置剧本）
# ---------------------------------------------------------------------------
def test_e1_six_scripts_images_and_gallery_unlock():
    _reset_scene()
    for sid, key in EXPECTED_IMAGES.items():
        assert key in GALLERY_ASSET_KEYS
        c = _player()
        try:
            res = os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id=sid, allow_ai=False)
            assert res["success"] and res["scene"]["image_key"] == key, sid
            assert res["omen_image"] == asset_path(key), sid
            # 预置剧本开启点亮其配图键（§8.3 事件型）
            atlas = gallery_mod.get_atlas(c.user_id)
            assert key in atlas["unlocked"], sid
            os_mod.abandon(CharacterRepository.get_by_id(c.id))
        finally:
            _cleanup(c)


def test_e4_any_terminal_leaves_trace_and_ledger():
    _reset_scene()
    c = _player()
    try:
        before_trace = _trace_count(c.id)
        before_ledger = len([
            r for r in EventLedgerRepository.query_for_memory(c.id, limit=50)
            if r.get("type") == "omen_encounter"
        ])
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="stele", allow_ai=False)
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "3")  # 绕道 leave 终局
        # 二期 §9.8：stele 配图已改指专图键 omen/stele（原借代 maps/map-ancient）
        assert res["ended"] and res["omen_image"] == asset_path("omen/stele")
        assert _trace_count(c.id) == before_trace + 1
        after_ledger = len([
            r for r in EventLedgerRepository.query_for_memory(c.id, limit=50)
            if r.get("type") == "omen_encounter"
        ])
        assert after_ledger == before_ledger + 1
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-2 后果·诺言（orphan_trust / escort_deal）与降级
# ---------------------------------------------------------------------------
def test_e2_orphan_trust_creates_real_promise():
    _reset_scene()
    c = _relocate(_player(), f"托孤地{_tag()}")
    npc = _npc("柳三娘", c.location)
    try:
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="orphan_trust", allow_ai=False)
        os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 应下 → n2
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 死战 → fight 终局
        assert res["ended"] and res["omen_status"] == "success"
        mine = _promises_of(c.id)
        assert len(mine) == 1, mine
        p = mine[0]
        assert p.promisee_id == npc.id and p.promisee_name == "柳三娘"
        assert p.kind == "arrive" and p.status.value == "ACTIVE"
        assert "落霞" in p.param and p.deadline > time.time()
    finally:
        _cleanup(c)


def test_e2_escort_deal_creates_real_promise():
    _reset_scene()
    c = _relocate(_player(), f"镖局地{_tag()}")
    npc = _npc("驼爷", c.location)
    try:
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="escort_deal", allow_ai=False)
        os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 帮驼爷 → n2a
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 仍帮驼爷 → side_tuo
        assert res["ended"]
        mine = [p for p in _promises_of(c.id) if p.promisee_id == npc.id]
        assert len(mine) == 1 and mine[0].kind == "quest" and mine[0].status.value == "ACTIVE"
    finally:
        _cleanup(c)


def test_e2_promise_degrades_to_trace_when_npc_missing():
    _reset_scene()
    c = _relocate(_player(), f"荒村{_tag()}")  # 唯一地点，同场必无「柳三娘」实体
    try:
        before = _trace_count(c.id)
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="orphan_trust", allow_ai=False)
        os_mod.choose(CharacterRepository.get_by_id(c.id), "1")
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")
        assert res["ended"] and res["omen_status"] == "success"  # 场景正常终局
        assert _promises_of(c.id) == []  # 无诺言
        assert _trace_count(c.id) == before + 1  # 降级为仅江湖痕迹
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-3 后果·因果边（black_market / spring_dispute）与幂等
# ---------------------------------------------------------------------------
def _attitude(npc_id, other_id):
    from core.npc_mind import ensure_mind

    npc = CharacterRepository.get_by_id(npc_id)
    mind = ensure_mind(npc)
    return ((mind.get("attitudes") or {}).get(other_id) or {}).get("value", 0)


def test_e3_black_market_karma_link_attitude_and_idempotent():
    _reset_scene()
    c = _relocate(_player(), f"黑市巷{_tag()}")
    npc = _npc("黑市汉子", c.location)
    try:
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="black_market", allow_ai=False)
        res = os_mod.say(CharacterRepository.get_by_id(c.id), "我要杀了你，抢了你的货")
        assert res["ended"] and res["omen_status"] == "failed"  # threat → threat_fail 终局
        links = [l for l in _links_between(c.id, npc.id) if l.link_type == "仇"]
        assert len(links) == 1 and links[0].strength == 1
        assert _attitude(npc.id, c.id) == -10  # 子顶 |Δ|≤10，方向为仇
        # 幂等：模拟终局重入（同 scene 再过 _finish）不重复落账
        scene = os_mod._load()[c.id]
        assert scene["consequence_done"] is True
        trace_before = _trace_count(c.id)
        os_mod._finish(CharacterRepository.get_by_id(c.id), scene, "failed", "重演", {})
        links = [l for l in _links_between(c.id, npc.id) if l.link_type == "仇"]
        assert links[0].strength == 1 and _attitude(npc.id, c.id) == -10
        assert _trace_count(c.id) == trace_before
    finally:
        _cleanup(c)


def test_e3_spring_dispute_rob_karma_link():
    _reset_scene()
    c = _relocate(_player(), f"灵泉涧{_tag()}")
    npc = _npc("对峙散修", c.location)
    try:
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="spring_dispute", allow_ai=False)
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 出手强夺 → rob
        assert res["ended"]
        links = [l for l in _links_between(c.id, npc.id) if l.link_type == "仇"]
        assert len(links) == 1 and links[0].strength == 1
        assert _attitude(npc.id, c.id) == -10
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-5 AI 剧本剥离后果 + 配图兜底 + 不点亮
# ---------------------------------------------------------------------------
def test_e5_ai_script_consequence_stripped_and_no_unlock():
    _reset_scene()
    c = _relocate(_player(), f"雷泽{_tag()}")
    npc = _npc("柳三娘", c.location)
    try:
        data = {
            "title": "雷泽夜遇",
            "speakers": ["神秘人"],
            "intro": "雷光之下有人拦路。",
            "goal": "作出选择",
            "start": "n1",
            "max_turns": 6,
            "consequence": {"type": "promise", "kind": "quest", "npc_name": "柳三娘"},
            "nodes": {
                "n1": {
                    "speaker": "神秘人",
                    "prompt": "「应我一件事。」",
                    "consequence": {"type": "promise", "kind": "quest", "npc_name": "柳三娘"},
                    "choices": [
                        {"id": "1", "label": "应下", "to": "ok", "effects": {},
                         "consequence": {"type": "karma_link", "npc_name": "柳三娘"}},
                    ],
                    "edges": [],
                },
                "ok": {
                    "speaker": "旁白",
                    "prompt": "事了拂衣去。",
                    "success": True,
                    "effects": {"exp": 10},
                    "consequence": {"type": "promise", "kind": "quest", "npc_name": "柳三娘"},
                    "choices": [],
                    "edges": [],
                },
            },
        }
        sid = os_mod.ingest_ai_script(data, c)
        assert sid and sid.startswith("ai_")
        script = os_mod.SCRIPTS[sid]

        def _has_cons(obj):
            if isinstance(obj, dict):
                if any(k in obj for k in os_mod._CONSEQUENCE_KEYS):
                    return True
                return any(_has_cons(v) for v in obj.values())
            if isinstance(obj, list):
                return any(_has_cons(v) for v in obj)
            return False

        assert not _has_cons(script["nodes"])  # 各层后果字段全剥离
        res = os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id=sid, allow_ai=False)
        assert res["success"]
        # 配图兜底：标题含「雷」→ arts/thunder；且 AI 剧本不点亮图鉴
        assert res["scene"]["image_key"] == "arts/thunder"
        assert res["omen_image"] == asset_path("arts/thunder")
        atlas = gallery_mod.get_atlas(c.user_id)
        assert "arts/thunder" not in atlas["unlocked"]
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")
        assert res["ended"]
        assert _promises_of(c.id) == []  # 无诺言产生
        assert _links_between(c.id, npc.id) == []  # 无因果边产生
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-6 冷却生效 / E-7 日上限（非 force；force 豁免）
# ---------------------------------------------------------------------------
def _force_chance(monkeypatch):
    monkeypatch.setattr(config, "omen_chance", lambda: 1.0)


def test_e6_cooldown_blocks_natural_and_force_exempts(monkeypatch):
    _force_chance(monkeypatch)
    _reset_scene()
    c = _player()
    try:
        c.last_omen_at = time.time()  # 刚刚开启过一场
        CharacterRepository.save(c)
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res is None  # 600s 冷却内不开启
        # force 豁免冷却
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), force=True, allow_ai=False, rng=random.Random(0))
        assert res and res["triggered"] and res["omen_image"]
        scene_id = res["scene"]["id"]
        os_mod.abandon(CharacterRepository.get_by_id(c.id))
        # 冷却外（last_omen_at 在 700s 前）可自然开启
        c2 = CharacterRepository.get_by_id(c.id)
        c2.last_omen_at = time.time() - 700
        CharacterRepository.save(c2)
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res and res["triggered"] and res["scene"]["id"] != scene_id
        assert os_mod._daily_open_count(c.id) == 1  # 自然开启计日限（force 不计）
        os_mod.abandon(CharacterRepository.get_by_id(c.id))
    finally:
        _cleanup(c)


def test_e7_daily_open_cap_and_next_day(monkeypatch):
    _force_chance(monkeypatch)
    _reset_scene()
    c = _player()
    try:
        c.last_omen_at = 0.0
        CharacterRepository.save(c)
        from datetime import date as _date

        WorldStateRepository.set("omen_daily:" + c.id, {
            "date": _date.fromtimestamp(time.time()).isoformat(), "opens": 5,
        })
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res is None  # 第 6 场不开启
        # 次日恢复：计数按日期失效
        WorldStateRepository.set("omen_daily:" + c.id, {
            "date": _date.fromtimestamp(time.time() - DAY).isoformat(), "opens": 5,
        })
        assert os_mod._daily_open_count(c.id) == 0
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res and res["triggered"]
        os_mod.abandon(CharacterRepository.get_by_id(c.id))
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-6 扩展（MF-1，§7.4）：交谈内奇遇分支豁免冷却与日限
# ---------------------------------------------------------------------------
def test_e6_chat_omen_exempt_from_cooldown(monkeypatch):
    _force_chance(monkeypatch)
    _reset_scene()
    c = _player()
    npc = _npc("柳三娘", c.location)
    try:
        c.last_omen_at = time.time()  # 刚刚开启过一场，600s 冷却生效中
        CharacterRepository.save(c)
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res is None  # 自然触发仍被冷却拦截（对照）
        res = os_mod.maybe_trigger_natural_omen(
            CharacterRepository.get_by_id(c.id), in_chat_npc=CharacterRepository.get_by_id(npc.id),
            allow_ai=False, rng=random.Random(0),
        )
        assert res is not None and res["triggered"] and res["mode"] == "chat"  # 交谈分支豁免冷却
        assert os_mod.get_scene(c.id) is None  # 交谈奇遇不占用主界面场景
    finally:
        _cleanup(c)


def test_e6_chat_omen_exempt_from_daily_cap(monkeypatch):
    _force_chance(monkeypatch)
    _reset_scene()
    c = _player()
    npc = _npc("驼爷", c.location)
    try:
        c.last_omen_at = 0.0  # 隔离变量：本例只顶日限，不触发冷却
        CharacterRepository.save(c)
        from datetime import date as _date

        WorldStateRepository.set("omen_daily:" + c.id, {
            "date": _date.fromtimestamp(time.time()).isoformat(), "opens": 5,
        })
        assert os_mod._daily_open_count(c.id) == 5  # 当日自然开启已达上限
        res = os_mod.maybe_trigger_natural_omen(CharacterRepository.get_by_id(c.id), allow_ai=False, rng=random.Random(0))
        assert res is None  # 自然触发仍被日限拦截（对照）
        res = os_mod.maybe_trigger_natural_omen(
            CharacterRepository.get_by_id(c.id), in_chat_npc=CharacterRepository.get_by_id(npc.id),
            allow_ai=False, rng=random.Random(0),
        )
        assert res is not None and res["triggered"] and res["mode"] == "chat"  # 交谈分支豁免日限
        assert os_mod.get_scene(c.id) is None
    finally:
        _cleanup(c)


# ---------------------------------------------------------------------------
# E-8 存量零回归：抉择效果口径不变 + event_chains 只多配图键
# ---------------------------------------------------------------------------
def test_e8_baseline_effects_unchanged_and_event_chain_image():
    _reset_scene()
    c = _player()
    try:
        c.realm.current_exp = 0
        c.karma.dao_heart = 50  # 避开道心 100 上限钳制（save 审计口径）
        heart0 = c.karma.dao_heart
        CharacterRepository.save(c)
        os_mod.start_scene(CharacterRepository.get_by_id(c.id), script_id="stele", allow_ai=False)
        res = os_mod.choose(CharacterRepository.get_by_id(c.id), "1")  # 静坐观碑 → sit
        assert res["ended"] and res["omen_status"] == "success"
        c2 = CharacterRepository.get_by_id(c.id)
        # 基线口径（实测存量行为）：choose 直达终局只落终局节点 effects，
        # 选项 effects 不落账（say 的边效果才落）——本轮不改此口径
        assert c2.realm.current_exp == 0
        assert c2.karma.dao_heart == heart0 + 3  # sit 终局效果原样
    finally:
        _cleanup(c)

    from core.event_chains import EventChainEngine, chain_image_key

    c3 = _player()
    ch = EventChainEngine.maybe_start(c3, trigger="travel", force=True)
    assert ch is not None
    assert ch.image_key in GALLERY_ASSET_KEYS
    assert ch.image_key == chain_image_key(ch.kind, ch.title)
    assert ch.title and len(ch.steps) == ch.max_steps  # 模板结构不变
    assert EventChainEngine.maybe_start(c3, trigger="travel", force=True) is None  # 单人 1 条沿现行
