"""AI 中台：registry / quota / router / facts 扩展"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reset():
    from ai.registry import clear_registry_for_tests, bootstrap_from_play_prompts
    from ai.quota import quota

    clear_registry_for_tests()
    bootstrap_from_play_prompts()
    quota.reset_for_tests()
    return quota


def test_registry_lists_builtin_scenes():
    _reset()
    from ai.registry import list_scenes, get_scene

    scenes = list_scenes()
    assert "npc_agenda" in scenes
    assert "combat" in scenes
    spec = get_scene("npc_agenda")
    assert spec is not None and spec.requires_facts is True
    assert get_scene("combat").requires_facts is True


def test_router_unknown_scene_rejected():
    _reset()
    from ai.router import invoke

    r = invoke("no_such_scene_xyz", payload={}, actor_id="t")
    assert r["ok"] is False
    assert "unknown_scene" in r["error"]


def test_router_requires_facts():
    _reset()
    from ai.router import invoke

    r = invoke("npc_agenda", payload={"bio": "x", "ag_cn": "巡守", "ag_note": "", "loc_name": "坊市", "safe_cn": "安全", "others": "", "events": "", "personality": "稳"}, actor_id="t")
    assert r["ok"] is False
    assert r["error"] == "facts_required"


def test_quota_exceeded():
    from ai.registry import clear_registry_for_tests, bootstrap_from_play_prompts
    from ai.quota import QuotaLimiter
    from ai import router

    clear_registry_for_tests()
    bootstrap_from_play_prompts()
    limiter = QuotaLimiter()
    limiter._daily_budget = 0
    # 塞满 npc_proactive（默认限 10）
    for _ in range(10):
        ok, _ = limiter.allow("npc_proactive")
        assert ok
    ok, reason = limiter.check("npc_proactive")
    assert ok is False
    assert "频繁" in reason or "npc_proactive" in reason

    # router 使用全局 quota — 验证拒绝路径用注入 gateway 不会被调用
    called = {"n": 0}

    def gw(prompt, timeout=20.0):
        called["n"] += 1
        return {"line": "x"}

    from ai.quota import quota

    quota.reset_for_tests()
    quota._daily_budget = 10**9
    # 直接打满全局 quota 的同一场景
    scene = "npc_proactive"
    for _ in range(quota._limit_for(scene)):
        quota.hit(scene)
    r = router.invoke(
        scene,
        payload={"name": "A", "realm": "练气", "personality": "x", "persona": "", "player": "B", "att_cn": "中立", "location": "坊市"},
        actor_id="t",
        gateway=gw,
    )
    assert r["ok"] is False
    assert "频繁" in r["error"] or "quota" in r["error"] or scene in r["error"]
    assert called["n"] == 0


def test_router_success_with_injected_gateway():
    _reset()
    from ai.router import invoke
    from ai.facts import FactPack

    facts = FactPack({
        "season": {"time_str": "纪元1年", "timestamp": 1},
        "self": {"id": "n1", "name": "甲", "status": "IDLE", "location": "青云坊市客栈"},
        "location": {"name": "青云坊市客栈", "is_safe": True},
        "others_nearby": [],
        "known_ids": ["n1", "p1"],
        "karma_links": [],
        "bounties": [],
        "recent_ledger": [],
        "jianghu_events": [],
        "npc_agendas": [],
    })

    def gw(prompt, timeout=20.0):
        assert "青云坊市客栈" in prompt or "甲" in prompt
        return {
            "act": True,
            "action": "stay",
            "new_location": None,
            "narrative": "甲在客栈打坐。",
            "progress_delta": 0,
            "ref_ids": ["n1"],
        }

    r = invoke(
        "npc_agenda",
        facts=facts,
        payload={
            "bio": "散修",
            "personality": "谨慎",
            "ag_cn": "巡守",
            "ag_note": "周边",
            "loc_name": "青云坊市客栈",
            "safe_cn": "安全",
            "others": "无",
            "events": "无",
        },
        actor_id="npc_n1",
        gateway=gw,
    )
    assert r["ok"] is True
    assert r["data"]["action"] == "stay"
    assert "n1" in r["ref_ids"]


def test_router_schema_reject_non_object():
    _reset()
    from ai.router import invoke
    from ai.facts import FactPack

    facts = FactPack({"self": {"id": "x"}, "known_ids": ["x"]})

    def gw(prompt, timeout=20.0):
        return "just a string"

    r = invoke(
        "combat",
        facts=facts,
        payload={"att_brief": "a", "def_brief": "b", "rule_hint": 0.5},
        actor_id="t",
        gateway=gw,
    )
    assert r["ok"] is False
    assert r["error"] == "not_json_object"


def test_facts_pack_jianghu_and_known_ids():
    _reset()
    from core.clock import WorldClock
    from ai.facts import build_fact_pack

    c = WorldClock.create_new_character("t_fact_j", "事实客")
    ev = {
        "id": "ev_test_1",
        "kind": "npc_agenda",
        "summary": "某人夜访坊市",
        "location": c.location,
        "actor_ids": ["npc_secret_1"],
        "target_ids": ["npc_secret_2"],
    }
    pack = build_fact_pack(
        c,
        jianghu_events=[ev],
        npc_agendas=[{"npc_id": "npc_secret_1", "npc_name": "夜行人", "agenda_type": "social", "note": "打探"}],
        known_extra_ids=["ev_extra"],
    )
    known = pack.known_ids
    assert "npc_secret_1" in known
    assert "npc_secret_2" in known
    assert "ev_test_1" in known
    assert "ev_extra" in known
    block = pack.to_prompt_block()
    assert "江湖因果账" in block
    assert "ev_test_1" in block or "某人夜访坊市" in block
    assert "夜行人" in block


def test_registry_register_and_replace():
    _reset()
    from ai.registry import register, get_scene, SceneSpec

    def builder(**kwargs):
        return "p"

    register(SceneSpec(scene_id="custom_scene_x", builder=builder, requires_facts=False), replace=True)
    assert get_scene("custom_scene_x") is not None
    try:
        register(SceneSpec(scene_id="custom_scene_x", builder=builder), replace=False)
        assert False, "should raise"
    except ValueError:
        pass


def main():
    test_registry_lists_builtin_scenes()
    print("✓ registry 列表")
    test_router_unknown_scene_rejected()
    print("✓ 未注册 scene 拒绝")
    test_router_requires_facts()
    print("✓ requires_facts 拒绝")
    test_quota_exceeded()
    print("✓ 配额超限拒绝且不打网关")
    test_router_success_with_injected_gateway()
    print("✓ 注入网关成功路径 + ref_ids")
    test_router_schema_reject_non_object()
    print("✓ schema 校验拒绝")
    test_facts_pack_jianghu_and_known_ids()
    print("✓ FactPack 因果/议程/known_ids")
    test_registry_register_and_replace()
    print("✓ register/replace")
    print("\n✅ AI 中台平台测试通过")


if __name__ == "__main__":
    main()
