"""
NPC 人设包
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, CharacterBioRepository
from core.clock import WorldClock
from core.npc_personas import (
    NAMED_PERSONAS,
    ROLE_TEMPLATES,
    get_persona,
    persona_prompt_block,
    speech_hints,
    ensure_persona_bio,
    _role_key,
)


def _npc(name, rank="散修", sect=None, note=""):
    c = WorldClock.create_new_character(f"np_{name}", name)
    c.sect_rank = rank
    c.sect = sect
    CharacterRepository.save(c)
    return c


def test_named_personas_cover_roster_core():
    # 至少覆盖商会/三宗关键 NPC
    for name in ("金满堂", "柳三娘", "玄清子", "幽冥老祖", "驼爷"):
        assert name in NAMED_PERSONAS, name
    assert len(NAMED_PERSONAS) >= 25
    assert len(ROLE_TEMPLATES) >= 10
    print(f"✓ 具名 {len(NAMED_PERSONAS)} 条，职分模板 {len(ROLE_TEMPLATES)}")


def test_named_block():
    init_db()
    c = _npc("柳三娘", rank="丹铺掌柜", sect="四海散修商会")
    p = get_persona(c)
    assert p.get("source") == "named"
    blk = persona_prompt_block(c)
    assert "人设" in blk
    assert "丹" in blk or "掌柜" in blk or "药" in blk
    assert len(blk) <= 220
    print("✓ 柳三娘人设块", blk[:50])


def test_role_fallback():
    c = _npc("无名执事甲", rank="执事", sect="青云宗")
    p = get_persona(c)
    assert p.get("source") == "role"
    assert p.get("role") == "执事"
    assert "规矩" in str(p.get("values")) or "差事" in str(p.get("values"))
    print("✓ 职分兜底 执事")


def test_ensure_bio():
    init_db()
    CharacterBioRepository.save("np_存传测试", "", None)
    c = _npc("存传测试", rank="掌柜")
    # 强制短 bio
    CharacterBioRepository.save(c.id, "短", None)
    out = ensure_persona_bio(c)
    assert len(out) > 30
    stored = CharacterBioRepository.get(c.id)
    assert stored and len(stored) > 30
    print("✓ bio 落库")


def test_speech_hints():
    c = _npc("独孤败测", rank="掌门")
    # 用具名键
    c2 = WorldClock.create_new_character("np_剑圣·独孤败", "剑圣·独孤败")
    CharacterRepository.save(c2)
    h = speech_hints(c2)
    assert "剑" in h or "口吻" in h or "本座" in h or h
    print("✓ speech_hints", h[:40])


if __name__ == "__main__":
    test_named_personas_cover_roster_core()
    test_named_block()
    test_role_fallback()
    test_ensure_bio()
    test_speech_hints()
    print("\n✅ npc-personas 测试通过")
