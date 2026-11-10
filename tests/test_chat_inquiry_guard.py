"""C4 缺陷回归：会话内「打听/询问」类话术不得被误判为敌意动作而吞回复。

定性（复测 C4）：新玩家在会话中说「道友请留步，在下初到贵地，想打听些消息」，
core/chat_actions.classify_local 的 attack 关键词含单字「打」，子串命中
「打**听**」→ 误判 attack → do_attack → CombatFateEngine.resolve_ambush 硬前置
（安全大阵 / 新手庇护）拒绝 → server/world.py /说 的「动作被规则拒绝」分支
只回系统行、从不回落常规对话生成，NPC 正文为空。

契约：
- 含良性复合词（打听/打探/打量/打算/打招呼/琢磨/偷懒…）且剔除复合词后
  无敌意关键词的话术 → dialogue，NPC 照常给出一轮正文回复；
- 复合词之外另有真实敌意（「打听完便一掌拍死你」）→ 仍判 attack；
- 敌意动作对庇护期玩家的拦截语义保持原样（ok=False、只有系统行、无 NPC 正文）；
- AI 分类把良性话术判敌意时，本地证据全由复合词解释 → 纠正为 dialogue；
- 问候型话术不回归。
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

import pytest

from core.chat_actions import classify_ai, classify_local
from server.world import World

DEFECT_PHRASE = "道友请留步，在下初到贵地，想打听些消息"
GREETING_PHRASE = "道友安好，在下初到贵地，特来问候"


def _tag():
    return uuid.uuid4().hex[:8]


_W = None


def _world():
    global _W
    if _W is None:
        _W = World(auto_tick=False)
    return _W


def _join(w, prefix):
    name = f"{prefix}{_tag()}"
    r = w.join(name, user_id=f"chat_inquiry_{_tag()}")
    assert r.get("token"), r
    return r["token"], w.get_char(r["token"])


def _npc_name(char):
    from core.here import list_here

    rows = [x for x in list_here(char) if x.get("is_npc")]
    assert rows, "出生地应有同场 NPC"
    return rows[0]["name"]


def _npc_lines(resp, npc):
    return [
        ln for ln in (resp.get("chat_lines") or [])
        if ln.get("cls") == "npc" and ln.get("who") == npc and (ln.get("text") or "").strip()
    ]


# ---------------------------------------------------------------------------
# 分类器单元：良性复合词不被单字敌意关键词误吞
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    DEFECT_PHRASE,
    "我想打听一下消息",
    "请问何处可以打探消息",
    "道友，你打算何时动身",      # 打算（含「打」）
    "容我打量打量这件法器",      # 打量（含「打」）
    "先打个招呼再说",            # 打招呼（含「打」）
    "容我摸索着找找路",          # 摸索（含「摸」）
    "容我打坐片刻再叙",          # 打坐（含「打」）
    "赶了半日路，想偷懒歇歇",    # 偷懒（含「偷」）
])
def test_benign_compounds_classify_dialogue(text):
    assert classify_local(text)["intent"] == "dialogue", text


@pytest.mark.parametrize("text,intent", [
    ("打听完消息，我便一掌拍死你", "attack"),   # 复合词外另有真实敌意
    ("我要杀了你", "attack"),
    ("顺手偷走他的储物袋", "steal"),
    ("把他绑起来带走", "kidnap"),
])
def test_real_hostility_still_classified(text, intent):
    assert classify_local(text)["intent"] == intent, text


def test_ai_hostile_verdict_on_benign_text_corrected(monkeypatch):
    """AI 分类器若把打听类话术判 attack，但本地敌意证据全在良性复合词内，
    须纠正为 dialogue（AI 不可用时的本地兜底同理由 classify_local 保证）。"""
    import ai.gateway as gw
    from core.clock import WorldClock

    monkeypatch.setattr(gw, "ai_available", lambda: True)
    monkeypatch.setattr(gw, "_chat_json", lambda prompt: {
        "intent": "attack", "target_item": "", "stones": 0,
    })
    p = WorldClock.create_new_character(f"cig_p_{_tag()}", f"问讯客{_tag()}")
    n = WorldClock.create_new_character(f"cig_n_{_tag()}", f"被问客{_tag()}")
    assert classify_ai(DEFECT_PHRASE, p, n)["intent"] == "dialogue"
    # 真实敌意：剔除复合词后仍有敌意关键词，AI 的 attack 判定保留
    assert classify_ai("打听完消息，我便一掌拍死你", p, n)["intent"] == "attack"


# ---------------------------------------------------------------------------
# 端到端 /说：庇护期新玩家说打听类话术 → NPC 正文回复（原缺陷钉子）
# ---------------------------------------------------------------------------
def test_say_inquiry_gets_npc_reply_for_protected_newbie():
    w = _world()
    tok, char = _join(w, "问讯新客")
    import time as _time

    assert char.is_newbie_protected(_time.time()), "前提：新玩家应在新手庇护期内"
    npc = _npc_name(char)
    assert w.handle(tok, f"/交谈 {npc}").get("chat_open") is True
    r = w.handle(tok, f"/说 {DEFECT_PHRASE}")
    assert r.get("ok") is True, r
    assert r.get("chat_open") is True, r
    assert _npc_lines(r, npc), r.get("chat_lines")  # NPC 正文行必须在（庇护系统行可并存、不可独占）


def test_say_greeting_not_regressed():
    w = _world()
    tok, char = _join(w, "问候新客")
    npc = _npc_name(char)
    assert w.handle(tok, f"/交谈 {npc}").get("chat_open") is True
    r = w.handle(tok, f"/说 {GREETING_PHRASE}")
    assert r.get("ok") is True, r
    assert _npc_lines(r, npc), r.get("chat_lines")


def test_talk_with_words_inquiry_gets_npc_reply():
    """/交谈 <人> <话> 入口同话术：NPC 正文行必须在。"""
    w = _world()
    tok, char = _join(w, "带话问讯客")
    npc = _npc_name(char)
    r = w.handle(tok, f"/交谈 {npc} {DEFECT_PHRASE}")
    assert r.get("ok") is True, r
    assert _npc_lines(r, npc), r.get("chat_lines")


def test_say_real_attack_still_blocked_for_protected_newbie():
    """敌意动作拦截语义原样：庇护期玩家真动手 → ok=False、只有系统行、无 NPC 正文。"""
    w = _world()
    tok, char = _join(w, "动手新客")
    npc = _npc_name(char)
    assert w.handle(tok, f"/交谈 {npc}").get("chat_open") is True
    r = w.handle(tok, "/说 我要一掌拍死你")
    assert r.get("ok") is False, r
    assert r.get("action") == "attack", r
    assert not _npc_lines(r, npc), r.get("chat_lines")
    sys_texts = [ln["text"] for ln in r["chat_lines"] if ln.get("cls") == "sys"]
    assert any("庇护" in t for t in sys_texts), r.get("chat_lines")


def teardown_module():
    if _W is not None:
        _W.stop_tick()
