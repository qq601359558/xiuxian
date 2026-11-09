"""交谈结构化呈现（spec: chat-structure §B/§C 验收）。

契约：交谈类响应新增 chat_lines（{who, cls, text} 列表，前端只按字段渲染）；
text 字段保持原拼装不变（CLI/旧呈现兼容）；AI 正文经 clean_dialogue_text
呈现清洗（剥 markdown 残留、规范换行、幂等、不伤中文叙事符号）。
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core.dialogue_text import clean_dialogue_text
from server.world import World


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
    r = w.join(name, user_id=f"chat_structure_{_tag()}")
    assert r.get("token"), r
    return r["token"], w.get_char(r["token"])


def _npc_name(char):
    from core.here import list_here

    rows = [x for x in list_here(char) if x.get("is_npc")]
    assert rows, "出生地应有同场 NPC"
    return rows[0]["name"]


def _assert_lines_shape(lines):
    assert isinstance(lines, list) and lines, lines
    for ln in lines:
        assert isinstance(ln, dict), ln
        assert ln.get("cls") in ("sys", "npc", "me"), ln
        assert isinstance(ln.get("text"), str) and ln["text"], ln
        assert isinstance(ln.get("who"), str), ln


# ---------------------------------------------------------------------------
# §C 清洗纯函数
# ---------------------------------------------------------------------------
def test_clean_dialogue_text_strips_markdown_keeps_chinese():
    raw = "## 开场\r\n\r\n\r\n**道友**请看`灵石`，[详情](http://x.cn)在此。\n> 引文\n「张三」：【同场】照旧。"
    out = clean_dialogue_text(raw)
    assert "**" not in out and "##" not in out and "`" not in out and "](" not in out
    assert "「张三」" in out and "【同场】" in out
    assert "\r" not in out and "\n\n\n" not in out
    assert clean_dialogue_text(out) == out  # 幂等
    assert clean_dialogue_text(None) == "" and clean_dialogue_text(123) == ""


# ---------------------------------------------------------------------------
# §B /交谈 开启（无话）：chat_lines 全 sys，text 不变
# ---------------------------------------------------------------------------
def test_talk_open_chat_lines_all_sys():
    w = _world()
    tok, char = _join(w, "结构开场客")
    npc = _npc_name(char)
    r = w.handle(tok, f"/交谈 {npc}")
    assert r.get("ok") is True and r.get("chat_open") is True, r
    _assert_lines_shape(r.get("chat_lines"))
    assert all(ln["cls"] == "sys" for ln in r["chat_lines"]), r["chat_lines"]
    assert "会话开始" in r["text"] and "会话开始" in r["chat_lines"][0]["text"]


# ---------------------------------------------------------------------------
# §B /交谈 带话：问候 sys + 引擎眉题 sys + 正文 npc（who=目标），text 仍含「」
# ---------------------------------------------------------------------------
def test_talk_words_chat_lines_header_and_body():
    w = _world()
    tok, char = _join(w, "结构带话客")
    npc = _npc_name(char)
    r = w.handle(tok, f"/交谈 {npc} 道友近来可好")
    assert r.get("ok") is True and r.get("chat_open") is True, r
    _assert_lines_shape(r.get("chat_lines"))
    lines = r["chat_lines"]
    assert lines[0]["cls"] == "sys"
    headers = [ln for ln in lines if ln["cls"] == "sys" and ln["text"].startswith("【") and npc in ln["text"]]
    assert headers, lines  # 引擎眉题独立成 sys 行（旧前端正则猜不中、误入气泡的那行）
    bodies = [ln for ln in lines if ln["cls"] == "npc" and ln["who"] == npc]
    assert bodies, lines
    body = bodies[0]["text"]
    assert not body.startswith("「")
    assert f"「{body}」" in r["text"]  # text 字节口径不变：正文仍以「」拼装


# ---------------------------------------------------------------------------
# §B /说 对话 + /挂断：/说 首行为 npc 正文；/挂断 全 sys
# ---------------------------------------------------------------------------
def test_say_and_hangup_chat_lines():
    w = _world()
    tok, char = _join(w, "结构续话客")
    npc = _npc_name(char)
    r0 = w.handle(tok, f"/交谈 {npc}")
    assert r0.get("chat_open") is True, r0
    r = w.handle(tok, "/说 请问道友，此地灵气如何")
    assert r.get("ok") is True, r
    _assert_lines_shape(r.get("chat_lines"))
    assert r["chat_lines"][0]["cls"] == "npc" and r["chat_lines"][0]["who"] == npc
    assert r["chat_lines"][0]["text"] in r["text"]
    r2 = w.handle(tok, "/挂断")
    assert r2.get("chat_ended") is True, r2
    _assert_lines_shape(r2.get("chat_lines"))
    assert all(ln["cls"] == "sys" for ln in r2["chat_lines"])
    assert r2["text"].startswith("【挂断】")


# ---------------------------------------------------------------------------
# §B /说 动作类（赠礼）：同样带 chat_lines（形态断言，成败两路皆可）
# ---------------------------------------------------------------------------
def test_say_action_chat_lines():
    w = _world()
    tok, char = _join(w, "结构赠礼客")
    npc = _npc_name(char)
    assert w.handle(tok, f"/交谈 {npc}").get("chat_open") is True
    r = w.handle(tok, "/说 赠你10灵石")
    assert r.get("chat_lines"), r
    _assert_lines_shape(r.get("chat_lines"))


# ---------------------------------------------------------------------------
# §B 真人目标：/交谈 与 /说 均为 sys 传音确认，is_player 在场
# ---------------------------------------------------------------------------
def test_player_target_chat_lines():
    w = _world()
    tok1, char1 = _join(w, "结构传音甲")
    tok2, char2 = _join(w, "结构传音乙")
    if char1.location != char2.location:
        w.handle(tok2, f"/go {char1.location}")
    assert char1.location == char2.location, (char1.location, char2.location)
    r = w.handle(tok1, f"/交谈 {char2.name} 道友安好")
    assert r.get("ok") is True and r.get("is_player") is True, r
    _assert_lines_shape(r.get("chat_lines"))
    assert all(ln["cls"] == "sys" for ln in r["chat_lines"])
    assert any("传音" in ln["text"] for ln in r["chat_lines"])
    r2 = w.handle(tok1, "/说 再叙一句")
    assert r2.get("ok") is True, r2
    _assert_lines_shape(r2.get("chat_lines"))
    assert all(ln["cls"] == "sys" for ln in r2["chat_lines"])


# ---------------------------------------------------------------------------
# §B /灵语：成功带 chat_lines（正文 npc + 注记 sys）且无 chat_open；
# 无器灵失败不带 chat_lines（命令框呈现不被弹窗劫持）
# ---------------------------------------------------------------------------
def test_spirit_talk_chat_lines():
    from core.artifact_spirit import ArtifactSpiritEngine
    from core.items import ItemFactory
    from storage.db import CharacterRepository

    w = _world()
    tok, char = _join(w, "结构灵语客")
    it = ItemFactory.create_equip("镇海宝镜", tier=4, slot="trinket")
    char.add_item_entity(it)
    char.equipped.append(it.name)
    res = ArtifactSpiritEngine.awaken(char, it.name)
    assert res["success"], res
    CharacterRepository.save(char)

    r = w.handle(tok, "/灵语 你好")
    assert r.get("ok") is True, r
    assert "chat_open" not in r, r
    _assert_lines_shape(r.get("chat_lines"))
    first = r["chat_lines"][0]
    assert first["cls"] == "npc" and first["who"] == r.get("spirit_name")
    assert first["text"] in r["text"]
    assert all(ln["cls"] == "sys" for ln in r["chat_lines"][1:])


def test_spirit_talk_failure_has_no_chat_lines():
    w = _world()
    tok, char = _join(w, "结构无灵客")
    r = w.handle(tok, "/灵语 你好")
    assert r.get("ok") is False, r
    assert "chat_lines" not in r, r
