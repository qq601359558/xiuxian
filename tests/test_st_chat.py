"""ST式交谈：角色卡 / lore 注入 / 会话摘要"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")

from storage.db import init_db, CharacterRepository
from core.clock import WorldClock
from core.npc_personas import (
    character_card_block,
    example_lines,
    player_persona_block,
    get_persona,
)
from core import lorebook
from core import npc_chat
from ai.play_prompts import npc_talk_prompt
from core.legends import add_legend


def _npc(name="玄清子", uid="npc_st_xqz"):
    c = WorldClock.create_new_character(uid, name)
    c.sect = "青云宗"
    c.sect_rank = "掌门"
    c.location = "青云宗外门山门"
    CharacterRepository.save(c)
    return c


def _player(name="道友", uid="player_st_a"):
    c = WorldClock.create_new_character(uid, name)
    c.sect = "青云宗"
    c.location = "青云宗外门山门"
    CharacterRepository.save(c)
    return c


def test_character_card_and_examples():
    init_db()
    npc = _npc()
    card = character_card_block(npc)
    assert "人设" in card or "示例" in card
    ex = example_lines(npc)
    assert ex, ex
    p = get_persona(npc)
    # 玄清子具名卡应有示例
    assert p.get("examples") or p.get("catch")
    pl = _player()
    pc = player_persona_block(pl)
    assert "对方简卡" in pc and pl.name in pc
    print("✓ 角色卡与示例台词")


def test_lorebook_keyword_inject():
    init_db()
    WorldStateRepository_reset_era = True
    add_legend(
        title="黑风旧事",
        text="黑风绝渊曾起血潮",
        season=1,
        tags=["blood_feud"],
        weight=3,
    )
    npc = _npc("牙人甲", uid="npc_st_yr")
    npc.location = "黑风绝渊"
    CharacterRepository.save(npc)
    pl = _player("过客", uid="player_st_b")
    pl.location = "黑风绝渊"
    CharacterRepository.save(pl)
    blk = lorebook.lore_prompt_block(pl, npc, player_words="听说黑风绝渊不太平")
    assert "坊间与天机" in blk or blk == ""
    # 关键词命中黑风绝渊
    hits = lorebook.keyword_hits("黑风绝渊", extra_keys=["黑风绝渊"])
    assert any("黑风" in h for h in hits), hits
    # 秘境名
    hits2 = lorebook.keyword_hits("落霞古洞", extra_keys=["落霞古洞"])
    assert any("落霞" in h or "古洞" in h for h in hits2), hits2
    print("✓ lore 关键词注入", hits[:2])


def test_chat_memory_summary():
    init_db()
    npc = _npc("掌柜柳", uid="npc_st_lz")
    pl = _player("买客", uid="player_st_c")
    opened = npc_chat.open_session(pl, npc)
    assert opened["success"]
    rec = npc_chat.player_say(pl, "道友，这丹怎么卖？")
    assert rec["success"]
    npc_chat.apply_npc_reply(pl.id, "聚气丹四十灵石。", will_continue=True, attitude_delta=2)
    npc_chat.player_say(pl, "太贵了些。")
    closed = npc_chat.apply_npc_reply(
        pl.id, "不二价。", will_continue=False, attitude_delta=-1, hangup_reason="对方不再议价。"
    )
    assert closed["success"]
    mem = npc_chat.chat_memory_lines(pl.id, npc.id)
    assert "上次交谈记忆" in mem
    assert "掌柜柳" in mem or "丹" in mem or "价" in mem
    panel = npc_chat.format_chat_panel(pl.id)
    assert "会话已终" in panel or "交谈" in panel
    print("✓ 会话摘要记忆", mem.replace("\n", " ")[:60])


def test_prompt_includes_card_lore_memory():
    init_db()
    npc = _npc()
    pl = _player()
    from core.npc_personas import character_card_block, player_persona_block

    card = character_card_block(npc)
    lore = lorebook.lore_prompt_block(pl, npc, player_words="宗门")
    mem = npc_chat.chat_memory_lines(pl.id, npc.id)
    text = npc_talk_prompt(
        name=npc.name,
        realm=npc.realm.name,
        sect=npc.sect or "散修",
        role="掌门",
        persona=card,
        card=card,
        examples="「本座已知。」",
        player_card=player_persona_block(pl),
        lore=lore or "【坊间与天机】\n- 暂无",
        chat_memory=mem or "",
        personality="清高",
        bio="测试",
        player=pl.name,
        att_cn="中立",
        att_value=0,
        player_realm=pl.realm.name,
        stones=10,
        inv="无",
        location="青云宗外门山门",
        safe_cn="安全",
        goods="无",
        time_brief="天道",
        events="无",
        words="你好",
    )
    assert "示例" in text or "人设" in text
    assert "坊间与天机" in text
    assert "对方说：你好" in text
    print("✓ 交谈 prompt 含卡/lore/记忆槽位")


if __name__ == "__main__":
    test_character_card_and_examples()
    test_lorebook_keyword_inject()
    test_chat_memory_summary()
    test_prompt_includes_card_lore_memory()
    print("\nst_chat tests passed")
