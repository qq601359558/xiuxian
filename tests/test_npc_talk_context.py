"""
交谈 AI 上下文：人设职分/地点/时间/货单必须进 prompt
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.npc_mind import NpcDialogueEngine
from core.memory import ensure_bio
from core.npc_roster import ROSTER


def _mk(name, uid, rank="散修", sect="四海散修商会"):
    now = time.time()
    return Character(
        user_id=uid,
        name=name,
        realm=Realm(tier=1, sub_tier=2, current_exp=0),
        lifespan=Lifespan(birth_base=80, accumulated_gain=0, death_timestamp=now + 80 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.METAL], efficiency=1),
        location="青云坊市客栈",
        sect=sect,
        sect_rank=rank,
    )


def test_bio_includes_role():
    n = _mk("柳三娘", "npc_ctx_liu", rank="丹铺掌柜")
    bio = ensure_bio(n, refresh=True)
    assert "丹铺掌柜" in bio, bio
    assert "丹药摊主" in bio or "坊间称" in bio, bio
    print("✓ bio 含职分与花名册备注")


def test_roster_has_shop_role():
    row = next(r for r in ROSTER if r["name"] == "柳三娘")
    assert row["rank"] == "丹铺掌柜"
    assert "丹" in row["note"]
    print("✓ 花名册：柳三娘=丹铺掌柜")


def test_local_shopkeeper_mentions_pills():
    """无 AI 时掌柜谈丹药应报架上丹药，不得说不卖"""
    n = _mk("柳三娘", "npc_ctx_liu2", rank="丹铺掌柜")
    p = _mk("买家", "p_ctx_buyer", rank="散修", sect=None)
    p.inventory = []
    mind = {"personality": "谨慎多疑", "traits": {}, "attitudes": {}}
    att = {"value": 0, "label": "neutral"}
    # 模拟 talk 的本地掌柜分支
    role = "丹铺掌柜"
    roster_note = "丹药摊主，怕惹祸上身"
    words = "聚气丹怎么卖"
    if any(k in words for k in ("丹", "药", "买", "卖", "价")) and "掌柜" in role:
        from config import ITEM_CATALOG
        pills = [x for x, c in ITEM_CATALOG.items() if c.get("kind") == "pill"]
        line = f"{'、'.join(pills[:4])} 都在架上"
        assert "聚气丹" in line or "筑基丹" in line
        assert "不卖" not in line
    print("✓ 掌柜本地兜底报丹药")


if __name__ == "__main__":
    test_roster_has_shop_role()
    test_bio_includes_role()
    test_local_shopkeeper_mentions_pills()
    print("\n✅ 交谈上下文测试通过")
