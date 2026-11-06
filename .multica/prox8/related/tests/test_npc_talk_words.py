"""
交谈：玩家话语必须影响回应（本地兜底）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.npc_mind import NpcDialogueEngine, ensure_mind
from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element


def _make(name, uid, pers_force=None):
    now = time.time()
    c = Character(
        user_id=uid,
        name=name,
        realm=Realm(tier=1, sub_tier=0, current_exp=0),
        lifespan=Lifespan(birth_base=80, accumulated_gain=0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1),
        location="青云坊市客栈",
    )
    return c


def test_local_line_uses_words():
    npc = _make("陆仁贾", "npc_talk_a")
    player = _make("问话人", "p_talk_a")
    mind = ensure_mind(npc)
    att = {"value": 0, "label": "neutral"}

    a = NpcDialogueEngine._local_line(npc, player, att, mind, "打听血刀老祖下落")
    b = NpcDialogueEngine._local_line(npc, player, att, mind, "可有灵石买卖？")
    c = NpcDialogueEngine._local_line(npc, player, att, mind, "")
    d = NpcDialogueEngine._local_line(npc, player, att, mind, "今日天气不错")

    assert a[0] != b[0], "打听与买卖应不同"
    assert "下落" in a[0] or "打听" in a[0] or "消息" in a[0] or "买" not in a[0]
    assert a[0] != c[0], "有话与空话应不同"
    assert "今日天气" in d[0] or "知悉" in d[0] or "记下" in d[0] or "想想" in d[0]
    print("✓ 本地交谈按话语分支")


def test_hostile_and_trade_keywords():
    npc = _make("血刀老祖", "npc_talk_b")
    player = _make("来客", "p_talk_b")
    mind = ensure_mind(npc)
    hostile = {"value": -80, "label": "hostile"}
    line, _ = NpcDialogueEngine._local_line(npc, player, hostile, mind, "你这魔头找死")
    assert "死" in line or "杀" in line or "客气" in line
    line2, _ = NpcDialogueEngine._local_line(npc, player, {"value": 0, "label": "neutral"}, mind, "我收妖兽内丹，什么价")
    assert "灵石" in line2 or "价" in line2 or "买卖" in line2 or "公道" in line2
    print("✓ 敌对/买卖关键词")


if __name__ == "__main__":
    test_local_line_uses_words()
    test_hostile_and_trade_keywords()
    print("\n✅ 交谈话语分支测试通过")
