"""块一·内容面锁定测试（playability-block1 T2：B1-3/B1-4/B1-5/B1-6/B1-7 服务端）。

约定：ALLOW_LOCAL_AI=1 AI_REQUIRED=0 NPC_TICK_INTERVAL=0 前置（运行口径）；
本文件自建角色一律唯一名前缀 pb1ct_，用后按 user_id/id 清理（零残留）。
AI 强制关闭用 monkeypatch 改 config 运行时开关（不改 .env）。
"""
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("NPC_TICK_INTERVAL", "0")
os.environ.setdefault("USE_CCSWITCH", "0")

import config
from core.clock import WorldClock
from storage.db import (
    DB_PATH,
    CharacterRepository,
    WorldStateRepository,
    init_db,
)

init_db()

FORBIDDEN = ("CC Switch", "USE_CCSWITCH", "LLM_API", ".env", "server.log")
LOC = "青云坊市客栈"
FAR_LOC = "万剑仙门峰"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup(user_ids=(), char_ids=(), thread_ids=(), tokens=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        for uid in user_ids:
            conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
            conn.execute("DELETE FROM accounts WHERE user_id=?", (uid,))
        for cid in char_ids:
            conn.execute("DELETE FROM characters WHERE id=?", (cid,))
            conn.execute("DELETE FROM fate_threads WHERE player_id=?", (cid,))
            conn.execute("DELETE FROM event_ledger WHERE actor_id=? OR target_id=?", (cid, cid))
            conn.execute("DELETE FROM npc_minds WHERE npc_id=?", (cid,))
            conn.execute("DELETE FROM character_bios WHERE character_id=?", (cid,))
            conn.execute("DELETE FROM npc_agendas WHERE npc_id=?", (cid,))
        for tid in thread_ids:
            conn.execute("DELETE FROM fate_threads WHERE id=?", (tid,))
        for tok in tokens:
            conn.execute("DELETE FROM auth_sessions WHERE token=?", (tok,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _mk(uid_suffix: str, name: str, location: str = LOC):
    tag = _tag()
    uid = f"pb1ct_{uid_suffix}_{tag}"
    c = WorldClock.create_new_character(uid, f"{name}{tag}")
    c.location = location
    CharacterRepository.save(c)
    return CharacterRepository.get_by_id(c.id), uid


def _force_ai_off(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "USE_CCSWITCH", False)
    monkeypatch.setattr(config, "ALLOW_LOCAL_AI", False)
    import ai.gateway as gw

    monkeypatch.setattr(gw, "LLM_API_KEY", "")
    monkeypatch.setattr(gw, "USE_CCSWITCH", False)


def _assert_clean(payload, label: str):
    blob = str(payload)
    for bad in FORBIDDEN:
        assert bad not in blob, f"{label} 泄漏运维词 {bad}：{blob[:400]}"


# ================= B1-3：交谈兜底 + 出口无运维词 =================

def test_b13_talk_fallback_no_ops_words_and_personality_differs(monkeypatch):
    _force_ai_off(monkeypatch)
    from core.npc_mind import NpcDialogueEngine
    from storage.db import NpcMindRepository

    player, puid = _mk("p_talk", "谈客")
    npc1, nuid1 = _mk("npc_danbo", "淡泊客")
    npc2, nuid2 = _mk("npc_hao", "豪爽客")
    try:
        NpcMindRepository.upsert(npc1.id, "淡泊避世", {}, {})
        NpcMindRepository.upsert(npc2.id, "豪爽仗义", {}, {})
        r1 = NpcDialogueEngine.talk(
            CharacterRepository.get_by_id(npc1.id), player, "幸会，道友近来可好")
        r2 = NpcDialogueEngine.talk(
            CharacterRepository.get_by_id(npc2.id), player, "幸会，道友近来可好")
        for r in (r1, r2):
            assert r.get("ok") is True, r
            line = (r.get("line") or "").strip()
            assert line and line != "嗯。", r
            _assert_clean(r, "交谈兜底")
        assert r1["line"] != r2["line"], "不同性格兜底回复应有别"
        print("✓ B1-3 交谈：AI 关闭走本地兜底、无运维词、性格有别")
    finally:
        _cleanup(user_ids=[puid, nuid1, nuid2],
                 char_ids=[player.id, npc1.id, npc2.id])


def test_b13_world_exits_no_ops_words(monkeypatch):
    _force_ai_off(monkeypatch)
    from server.world import World

    tag = _tag()
    uid = f"pb1ct_exit_{tag}"
    old_health = None
    try:
        old_health = WorldStateRepository.get("ai_health")
    except Exception:
        old_health = None
    w = World(auto_tick=False)
    r = w.join(f"出口客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        r_art = w.handle(tok, "/自创功法 测试玄功")
        _assert_clean(r_art, "/自创功法")
        r_ai = w.handle(tok, "/ai")
        _assert_clean(r_ai, "/ai")
        # /交谈：同场任一 NPC，兜底回复非空且无运维词
        from core.here import list_here

        rows = [x for x in list_here(char) if x.get("is_npc")]
        assert rows, "坊市应有 NPC"
        r_talk = w.handle(tok, f"/交谈 {rows[0]['name']} 道友近来可好")
        _assert_clean(r_talk, "/交谈")
        assert r_talk.get("ok") is True, r_talk
        assert (r_talk.get("text") or "").strip(), r_talk
        print("✓ B1-3 出口：/交谈、/自创功法、/ai 均无运维词")
    finally:
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])
        try:
            if old_health is None:
                WorldStateRepository.delete("ai_health")
            else:
                WorldStateRepository.set("ai_health", old_health)
        except Exception:
            pass


def test_b13_npc_chat_pool_per_personality():
    from core import npc_chat
    from storage.db import NpcMindRepository

    player, puid = _mk("p_pool", "池客")
    made = []
    try:
        lines_by_pers = {}
        for pers, suffix in (("淡泊避世", "danbo"), ("豪爽仗义", "hao"),
                             ("市侩圆滑", "shik"), ("谨慎多疑", "jin")):
            npc, nuid = _mk(f"npc_{suffix}", f"池{suffix}")
            made.append((npc, nuid))
            NpcMindRepository.upsert(npc.id, pers, {}, {})
            npc = CharacterRepository.get_by_id(npc.id)
            lines = []
            for t in range(3):
                rec = {"willingness": 80, "turns": t,
                       "messages": [{"who": player.name, "text": "道友近来可好，可有消息"}]}
                out = npc_chat.local_hangup_or_reply(npc, player, rec)
                assert out.get("will_continue") is True, out
                lines.append(out["line"])
            assert len(set(lines)) >= 3, f"{pers} 兜底池应 ≥3 条互异回复：{lines}"
            for ln in lines:
                inner = ln.rsplit("「", 1)[-1].rstrip("」")
                assert inner != "嗯。" and len(ln) > 10, f"{pers} 兜底不得只剩「嗯。」：{ln}"
            lines_by_pers[pers] = lines
        assert lines_by_pers["淡泊避世"] != lines_by_pers["豪爽仗义"]
        print("✓ B1-3 兜底池：每性格 ≥3 条有内容回复、性格有别")
    finally:
        _cleanup(user_ids=[puid] + [u for _, u in made],
                 char_ids=[player.id] + [c.id for c, _ in made])


def test_b13_fallback_three_sentences_no_repeat_retest_texts():
    """块一复测再修（B1-3）：复测原话两连问，断 AI 兜底须为三句性格化
    回复、两轮互异、不复述玩家原话截断、无运维词；重开会话亦不撞首句。"""
    from core import npc_chat
    from storage.db import NpcMindRepository, WorldStateRepository

    player, puid = _mk("p_fall", "断言客")
    npc, nuid = _mk("npc_fall", "清高客")
    try:
        WorldStateRepository.delete(npc_chat._KEY)
        NpcMindRepository.upsert(npc.id, "清高自持", {}, {})
        npc = CharacterRepository.get_by_id(npc.id)
        opened = npc_chat.open_session(player, npc)
        assert opened.get("success") is True, opened
        lines = []
        for text in ("道友你好，在下初到此地，想请教剑道修行之事",
                     "那依道友之见，新人当先修何物？"):
            said = npc_chat.player_say(CharacterRepository.get_by_id(player.id), text)
            assert said.get("success") is True, said
            out = npc_chat.local_hangup_or_reply(
                CharacterRepository.get_by_id(npc.id),
                CharacterRepository.get_by_id(player.id), said["session"])
            assert out.get("will_continue") is True, out
            line = out["line"]
            assert line.count("。") >= 3, f"兜底须多句（≥3 句）：{line}"
            assert "想请教剑" not in line and "道友你好，在下初到此地" not in line, \
                f"兜底不得原样复述玩家截断原话：{line}"
            _assert_clean(line, "断 AI 兜底")
            npc_chat.apply_npc_reply(player.id, line, True)
            lines.append(line)
        assert lines[0] != lines[1], f"连续两轮兜底不得同一句：{lines}"
        # 重开会话：_local_seq 跨会话接续，首句不得撞回第一轮
        npc_chat.close_session(player.id, "测试重开", by="player")
        opened2 = npc_chat.open_session(
            CharacterRepository.get_by_id(player.id),
            CharacterRepository.get_by_id(npc.id))
        assert opened2.get("success") is True, opened2
        said3 = npc_chat.player_say(CharacterRepository.get_by_id(player.id),
                                    "再请教一句")
        out3 = npc_chat.local_hangup_or_reply(
            CharacterRepository.get_by_id(npc.id),
            CharacterRepository.get_by_id(player.id), said3["session"])
        assert out3["line"] != lines[0], f"重开会话首句不得撞回第一轮：{out3['line']}"
        assert out3["line"].count("。") >= 3, out3["line"]
        print("✓ B1-3 复测再修：断 AI 兜底三句、两轮互异、重开不撞")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id])


def test_b13_fallback_attitude_bands_differ():
    """块一复测再修（B1-3）：同性格 NPC，态度友善 vs 敌对时兜底第二句
    口径须不同（友善带亲近意、敌对带戒备意）。"""
    from core import npc_chat
    from core.npc_mind import shift_attitude
    from storage.db import NpcMindRepository, WorldStateRepository

    player, puid = _mk("p_att", "态度客")
    made = []
    try:
        WorldStateRepository.delete(npc_chat._KEY)
        outs = {}
        for suffix, delta in (("you", 50), ("di", -50)):
            npc, nuid = _mk(f"npc_att_{suffix}", f"态度{suffix}")
            made.append((npc, nuid))
            NpcMindRepository.upsert(npc.id, "清高自持", {}, {})
            npc = CharacterRepository.get_by_id(npc.id)
            shift_attitude(npc, player.id, delta, reason="测试态度")
            npc = CharacterRepository.get_by_id(npc.id)
            rec = {"willingness": 80, "turns": 0,
                   "messages": [{"who": player.name, "text": "道友近来可好"}]}
            out = npc_chat.local_hangup_or_reply(npc, player, rec)
            assert out.get("will_continue") is True, out
            outs[suffix] = out["line"]
        assert outs["you"] != outs["di"], f"态度不同兜底应不同：{outs}"
        assert any(k in outs["you"] for k in ("投缘", "坦荡", "心意", "交情")), outs["you"]
        assert any(k in outs["di"] for k in ("旧账", "少套近乎", "耐心有限", "搭腔")), outs["di"]
        print("✓ B1-3 复测再修：兜底态度口径随友善/敌对分化")
    finally:
        _cleanup(user_ids=[puid] + [u for _, u in made],
                 char_ids=[player.id] + [c.id for c, _ in made])


# ================= B1-5：/修炼 =================

def test_b15_xiulian_dispatch_gate_and_catalog():
    from core.command_catalog import format_help, search_commands, catalog_json
    from server.world import World

    by_cmd = {e["cmd"]: e for e in catalog_json()["commands"]}
    assert "/修炼" in by_cmd, "catalog 须含 /修炼 条目"
    assert "闭关" in by_cmd["/修炼"]["desc"] and "同源" in by_cmd["/修炼"]["desc"]
    assert "/修炼" in by_cmd["/闭关"]["desc"], "/闭关 条目须互指 /修炼"
    assert "/修炼" in format_help("修炼")
    assert any(h["cmd"] == "/修炼" for h in search_commands("修炼", limit=40))

    tag = _tag()
    uid = f"pb1ct_xiu_{tag}"
    w = World(auto_tick=False)
    r = w.join(f"修炼客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        char.born_at = time.time() - 80 * 3600.0
        char.spirit_stones = max(char.spirit_stones, 500)
        CharacterRepository.save(char)
        # /炼体 修炼 子命令不被 /修炼 精确分发吞掉
        r_body = w.handle(tok, "/炼体 修炼")
        assert "未知指令" not in str(r_body), r_body
        # /修炼 分发可用：回闭关反馈而非未知指令
        r1 = w.handle(tok, "/修炼 1")
        assert "未知指令" not in str(r1), r1
        assert r1.get("ok") is True, r1
        # 门禁口径：闭关中再发 /修炼 与 /闭关 同行为（锁门拦截）
        r2 = w.handle(tok, "/修炼")
        r3 = w.handle(tok, "/闭关")
        for rr in (r2, r3):
            assert rr.get("ok") is False, rr
            assert "闭关锁门" in (rr.get("error") or ""), rr
        print("✓ B1-5 /修炼：分发/门禁与 /闭关 同口径、catalog 互指、子命令无冲突")
    finally:
        try:
            w.handle(tok, "/出关")
        except Exception:
            pass
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])


# ================= B1-6：行情去原码 =================

_RAW_ID = re.compile(r"(mat|equip|pill)_[a-z0-9_]+")


def _assert_rows_clean(rows, label: str):
    names = [g["name"] for g in rows]
    assert names, f"{label} 行集为空"
    assert len(names) == len(set(names)), f"{label} 显示名重复：{names[:10]}"
    for n in names:
        assert not _RAW_ID.search(n), f"{label} 显示名含原码：{n}"


def test_b16_market_rows_no_raw_ids_no_dupes():
    from core.chat_actions import _shop_stock_preview
    from core.market import MarketEngine
    from core.trade import NpcShopEngine

    _assert_rows_clean(MarketEngine.catalog(), "catalog()")
    _assert_rows_clean(MarketEngine.catalog(LOC), "catalog(loc)")
    data = MarketEngine.trade_board_data(LOC)
    for region in data["regions"]:
        _assert_rows_clean(region["rows"], f"trade_board_data[{region['name']}]")
    board = MarketEngine.trade_board(LOC)
    assert not _RAW_ID.search(board), "trade_board 文本含原码"

    player, puid = _mk("p_mkt", "行情客")
    npc, nuid = _mk("npc_shop", "柜客")
    try:
        npc.sect = "四海散修商会"
        npc.sect_rank = "掌柜"
        CharacterRepository.save(npc)
        res = NpcShopEngine.catalog(player, npc.name)
        assert res.get("success") is True, res
        _assert_rows_clean(res["goods"], "NPC专柜")
        assert not _RAW_ID.search(res["message"]), "NPC专柜文本含原码"
        preview = _shop_stock_preview(CharacterRepository.get_by_id(npc.id))
        assert preview and len(preview) == len(set(preview)), preview
        for n in preview:
            assert not _RAW_ID.search(n), f"专柜预览含原码：{n}"
        print("✓ B1-6 行情：行集无原码、无重复显示名（商会/行情/NPC专柜/预览）")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id])


def test_b16_world_market_and_hangqing_text():
    from server.world import World

    tag = _tag()
    uid = f"pb1ct_hq_{tag}"
    w = World(auto_tick=False)
    r = w.join(f"行情行客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        r_hq = w.handle(tok, "/行情")
        assert r_hq.get("ok") is True, r_hq
        assert not _RAW_ID.search(r_hq.get("text") or ""), "/行情 文本含原码"
        for region in (r_hq.get("prices") or {}).get("regions") or []:
            _assert_rows_clean(region["rows"], "/行情 prices")
        r_mk = w.handle(tok, "/坊市")
        assert r_mk.get("ok") is True, r_mk
        assert not _RAW_ID.search(r_mk.get("text") or ""), "/坊市 文本含原码"
        print("✓ B1-6 /行情 与 /坊市（_market 同源）：文本无原码、行集无重复")
    finally:
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])


# ================= B1-4：fate current_target + briefing 文案 =================

def _mk_thread(player, npc_id: str):
    from core.fate_thread import FateThread
    from storage.db import FateThreadRepository

    tid = f"ft_pb1ct_{_tag()}"
    thread = FateThread(
        id=tid, player_id=player.id, user_id=player.user_id, status="active",
        seed_source="origin", title="出身牵命",
        final_proposition={"text": "立身", "status": "active"},
        chapters=[{
            "idx": 0, "group": "setup", "kind": "visit", "tier": "short",
            "title": "去见那个人", "goal_text": "前往其所在之地",
            "status": "active", "goal_id": "",
            "check": {"kind": "visit_location", "ref": LOC, "npc_id": npc_id},
        }],
        current_chapter=0, created_at=time.time(),
    )
    FateThreadRepository.save(thread)
    return tid


def test_b14_current_target_same_and_far_and_briefing():
    from core.briefing import build_entry
    from core.fate_thread import FateThreadEngine

    player, puid = _mk("p_fate", "命途客", location=LOC)
    npc, nuid = _mk("npc_fate", "引路客", location=LOC)
    tid = _mk_thread(player, npc.id)
    try:
        sd = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd is not None
        assert sd["chapters"][0].get("check", {}).get("kind") == "visit_location"
        assert sd["chapters"][0]["check"].get("npc_id") == npc.id
        ct = sd.get("current_target")
        assert ct and ct["npc_id"] == npc.id and ct["npc_name"] == npc.name, sd
        assert ct["npc_location"] == LOC and ct["same_location"] is True, ct
        entry = build_entry(CharacterRepository.get_by_id(player.id),
                            since=0, allow_proactive=False)
        fate_text = entry["lines"]["fate"]
        assert f"{npc.name} 正在此处（{LOC}），可直接上前交谈" in fate_text, fate_text

        # NPC 迁徙后现查：地点与 same_location 随之变化（不吃快照）
        npc2 = CharacterRepository.get_by_id(npc.id)
        npc2.location = FAR_LOC
        CharacterRepository.save(npc2)
        sd2 = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        ct2 = sd2.get("current_target")
        assert ct2 and ct2["npc_location"] == FAR_LOC and ct2["same_location"] is False, ct2
        entry2 = build_entry(CharacterRepository.get_by_id(player.id),
                             since=0, allow_proactive=False)
        assert f"{npc.name} 在{FAR_LOC}" in entry2["lines"]["fate"], entry2["lines"]["fate"]
        print("✓ B1-4 fate：current_target 现查（同场/异场）、briefing 文案随之")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id], thread_ids=[tid])


def test_b14_current_target_null_without_visit_chapter():
    from core.fate_thread import FateThread, FateThreadEngine
    from storage.db import FateThreadRepository

    player, puid = _mk("p_fate2", "无目标客", location=LOC)
    tid = f"ft_pb1ct_{_tag()}"
    try:
        FateThreadRepository.save(FateThread(
            id=tid, player_id=player.id, user_id=player.user_id, status="active",
            seed_source="origin", title="出身牵命",
            final_proposition={"text": "立身", "status": "active"},
            chapters=[{
                "idx": 0, "group": "setup", "kind": "treasure", "tier": "short",
                "title": "寻资", "goal_text": "寻一份立身之资",
                "status": "active", "goal_id": "",
                "check": {"kind": "stones_at_least", "amount": 200},
            }],
            current_chapter=0, created_at=time.time()))
        sd = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd is not None and sd.get("current_target") is None, sd
        print("✓ B1-4 fate：无 visit 类章时 current_target 为 null")
    finally:
        _cleanup(user_ids=[puid], char_ids=[player.id], thread_ids=[tid])


def test_b14_visit_chapter_needs_talk():
    """块一复测再修（B1-4）：带 npc_id 的 visit_location 章节，抵达 ≠ 完成，
    须与目标 NPC 真实交谈一轮才完成；无 npc_id 的纯地点章仍到访即成。"""
    from core.fate_thread import FateThreadEngine
    from core.goals import GoalEngine
    from core import npc_chat

    player, puid = _mk("p_fate3", "访客", location=LOC)
    npc, nuid = _mk("npc_fate3", "被访客", location=LOC)
    tid = _mk_thread(player, npc.id)
    try:
        check = {"kind": "visit_location", "ref": LOC, "npc_id": npc.id}
        now = time.time()
        p = CharacterRepository.get_by_id(player.id)
        assert GoalEngine._eval_check(p, check, now, final=False) is None
        # 抵达目标所在地（记 visited），但未交谈 → 仍未完成（复测根因）
        FateThreadEngine.record_visit(p, LOC)
        p = CharacterRepository.get_by_id(player.id)
        assert GoalEngine._eval_check(p, check, now, final=False) is None
        # 与目标 NPC 真实交谈一轮 → 完成
        opened = npc_chat.open_session(p, CharacterRepository.get_by_id(npc.id))
        assert opened.get("success") is True, opened
        said = npc_chat.player_say(CharacterRepository.get_by_id(player.id), "幸会，道友")
        assert said.get("success") is True, said
        npc_chat.apply_npc_reply(player.id, "回礼，道友请坐。", True)
        p = CharacterRepository.get_by_id(player.id)
        assert GoalEngine._eval_check(p, check, now, final=False) == "done"
        # 无 npc_id 的纯地点章：到访即成（旧行为不变）
        check2 = {"kind": "visit_location", "ref": LOC}
        assert GoalEngine._eval_check(p, check2, now, final=False) == "done"
        print("✓ B1-4 复测再修：visit 章须与目标交谈才完成；纯地点章到访即成")
    finally:
        _cleanup(user_ids=[puid, nuid], char_ids=[player.id, npc.id], thread_ids=[tid])


def test_b14_talk_completes_chapter_via_world(monkeypatch):
    """块一复测再修（B1-4 端到端）：/go 抵达目标所在地后第一章仍在，
    目标卡 same_location=true 且可上前交谈；断 AI 下一轮 /说 后章节完成。"""
    from server.world import World
    from core.fate_thread import FateThreadEngine
    from core.goals import GoalEngine
    from storage.db import FateThreadRepository

    _force_ai_off(monkeypatch)
    w = World(auto_tick=False)
    uid = f"u_b14e2e_{_tag()}"
    r = w.join(f"访途行客{_tag()}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    npc = None
    nuid = ""
    tid = ""
    try:
        player = CharacterRepository.get_by_id(char.id)
        # 注意：_mk 生成的 user_id 是 pb1ct_ 前缀，_is_npc 会判假，/说 将走
        # 真人传音分支而非 NPC 对话链；此处须用真 npc_ 前缀建目标 NPC。
        from core.clock import WorldClock

        npc = WorldClock.create_new_character(f"npc_b14e2e_{_tag()}", f"引见客{_tag()}")
        npc.location = LOC
        npc.born_at = time.time() - 80 * 3600.0
        CharacterRepository.save(npc)
        npc = CharacterRepository.get_by_id(npc.id)
        nuid = npc.user_id
        tid = _mk_thread(player, npc.id)
        goal = GoalEngine.add_checked_goal(
            player, source="thread", title="去见那个人", detail="当面说清",
            check={"kind": "visit_location", "ref": LOC, "npc_id": npc.id},
            instance=f"{tid}:c0",
        )
        thread = FateThreadEngine._active_thread(player.id)
        thread.chapters[0]["goal_id"] = goal["id"]
        thread.chapters[0]["check"]["instance"] = f"{tid}:c0"
        FateThreadRepository.save(thread)
        CharacterRepository.save(player)
        # 先把玩家放到远处，再 /go 抵达目标所在地
        player.location = FAR_LOC
        CharacterRepository.save(player)
        r_go = w.handle(tok, f"/go {LOC}")
        assert r_go.get("ok") is True, r_go
        sd = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd["chapters"][0]["status"] == "active", sd
        ct = sd.get("current_target")
        assert ct and ct["same_location"] is True, ct
        # 上前交谈：/交谈 + 断 AI 下一轮 /说（裸文本路由）→ 章节完成
        r_talk = w.handle(tok, f"/交谈 {npc.name}")
        assert r_talk.get("ok") is True, r_talk
        r_say = w.handle(tok, "道友你好，在下初到此地，想请教一二")
        assert r_say.get("ok") is True, r_say
        assert r_say.get("source") == "local", r_say
        _assert_clean(r_say.get("text") or "", "/说 回复")
        sd2 = FateThreadEngine.thread_status_dict(
            CharacterRepository.get_by_id(player.id))
        assert sd2["chapters"][0]["status"] == "done", sd2
        assert sd2.get("current_target") is None, sd2
        print("✓ B1-4 复测再修端到端：/go 到场章仍在，交谈一轮后章节完成")
    finally:
        _cleanup(user_ids=[uid, nuid], char_ids=[c for c in
                 [char.id if char else None, npc.id if npc else None] if c],
                 thread_ids=[tid] if tid else [], tokens=[tok])


# ================= B1-7：briefing relations 过滤 origin =================

def test_b17_briefing_relations_filters_origin():
    from core.briefing import build_entry
    from core.npc_mind import shift_attitude
    from core.relations import relations_recent_and_marks

    player, puid = _mk("p_rel", "留痕客")
    npc_o, nuid_o = _mk("npc_org", "出身客")
    npc_r, nuid_r = _mk("npc_real", "交谈客")
    try:
        shift_attitude(CharacterRepository.get_by_id(npc_o.id), player.id, 20, reason="origin")
        shift_attitude(CharacterRepository.get_by_id(npc_r.id), player.id, 20, reason="交谈")
        # 数据层不动：relations_recent 仍含 origin 项
        recent, _marks = relations_recent_and_marks(player.id, recent_limit=30, pool=30)
        assert any(x.get("reason") == "origin" for x in recent), recent
        # briefing 层过滤：origin 不出现、真实变化仍出现
        entry = build_entry(CharacterRepository.get_by_id(player.id),
                            since=0, allow_proactive=False)
        rels = entry["lines"]["relations"]
        assert rels, "真实变化项应仍出现在 briefing relations"
        assert all(x.get("reason") != "origin" for x in rels), rels
        assert any(x.get("npc_id") == npc_r.id for x in rels), rels
        print("✓ B1-7 briefing：origin 留痕已过滤、真实变化仍在、数据层未动")
    finally:
        _cleanup(user_ids=[puid, nuid_o, nuid_r],
                 char_ids=[player.id, npc_o.id, npc_r.id])


# ================= 评审 MF-2：/ai 面板 USE_CCSWITCH=1 口径去泄漏 =================

_FORBIDDEN_MF2 = ("CC Switch", "CCSWITCH", "USE_CCSWITCH", "LLM_API", ".env", "server.log")


def test_mf2_ai_panel_ccswitch_mode_no_ops_leak(monkeypatch):
    """USE_CCSWITCH=1 口径下调 /ai：模式为中性表述、无地址行，整个回包
    （文本 + ai_data 结构化字段）不含运维词与通道地址原文。"""
    import ai.gateway as gw

    monkeypatch.setattr(config, "USE_CCSWITCH", True)
    monkeypatch.setattr(config, "LLM_API_KEY", "mf2-test-key")
    monkeypatch.setattr(gw, "USE_CCSWITCH", True)
    monkeypatch.setattr(gw, "LLM_API_KEY", "mf2-test-key")
    monkeypatch.setattr(gw, "_chat_json", lambda prompt, timeout=0, **kw: {"line": "通了"})

    from server.world import World

    tag = _tag()
    uid = f"pb1ct_mf2_{tag}"
    try:
        old_health = WorldStateRepository.get("ai_health")
    except Exception:
        old_health = None
    w = World(auto_tick=False)
    r = w.join(f"自检客{tag}", user_id=uid)
    tok = r["token"]
    char = w.get_char(tok)
    try:
        r_ai = w.handle(tok, "/ai")
        assert r_ai.get("ok") is True, r_ai
        blob = str(r_ai)
        for bad in _FORBIDDEN_MF2:
            assert bad not in blob, f"/ai(CCSWITCH) 泄漏运维词 {bad}：{blob[:400]}"
        text = r_ai.get("text") or ""
        assert "本机代理" in text, text
        assert "地址" not in text, text
        ai_data = r_ai.get("ai_data") or {}
        assert "base" not in ai_data, ai_data
        assert ai_data.get("mode") == "本机代理", ai_data
        print("✓ MF-2 /ai：CCSWITCH 口径下模式中性、无地址、回包无运维词")
    finally:
        _cleanup(user_ids=[uid], char_ids=[char.id] if char else [], tokens=[tok])
        try:
            if old_health is None:
                WorldStateRepository.delete("ai_health")
            else:
                WorldStateRepository.set("ai_health", old_health)
        except Exception:
            pass


# ================= 评审 SF-4：ai_block_reason 探测失败分支去泄漏 =================

def test_sf4_ai_block_reason_probe_failed_branch_worldview(monkeypatch):
    import ai.gateway as gw

    monkeypatch.setattr(
        gw, "ai_health_status",
        lambda: {"last_error": "ConnectError: LLM_API_KEY rejected, see server.log"},
    )
    monkeypatch.setattr(config, "ALLOW_LOCAL_AI", True)
    reason = gw.ai_block_reason()
    assert reason, "已配置但探测失败分支应给出玩家文案"
    assert "灵机" in reason, reason
    for bad in _FORBIDDEN_MF2 + ("ConnectError", "自检", "探测失败"):
        assert bad not in reason, f"ai_block_reason 泄漏 {bad}：{reason}"
    # 导演质量自检 detail 同口径：已配置/未配置中性措辞，经 /ai 面板展示无运维词
    from core.world_director import director_quality_report

    q = director_quality_report()
    checks = {c.get("name"): c for c in q.get("checks") or []}
    detail = (checks.get("ai_channel_configured") or {}).get("detail") or ""
    assert detail in ("已配置", "仅本地降级", "未配置"), detail
    print("✓ SF-4：ai_block_reason 探测失败分支为世界观文案、导演自检 detail 中性")
