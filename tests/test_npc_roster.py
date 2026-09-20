"""全阵容 NPC 测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.npc_roster import seed_roster, roster_by_sect
from storage.db import CharacterRepository, init_db
from core.npc_mind import _is_npc


def main():
    init_db()
    r1 = seed_roster()
    r2 = seed_roster()
    assert r2["created"] == 0, f"重复 seed 不应新建: {r2}"
    groups = roster_by_sect()
    total = sum(len(v) for v in groups.values())
    assert total >= 30, f"阵容过少: {total}"

    names = {c.name for c in CharacterRepository.list_all_alive() if _is_npc(c)}
    for key in ("玄清子", "剑圣·独孤败", "幽冥老祖", "金满堂", "燕十三"):
        assert any(key in n for n in names), f"缺少 {key}"

    for uid, rank in [("npc_qy_01", "掌门"), ("npc_wj_01", "掌门"), ("npc_jy_01", "宗主")]:
        c = CharacterRepository.get_by_user_id(uid)
        assert c is not None, uid
        assert c.sect_rank == rank, f"{uid} rank={c.sect_rank}"

    print(f"首次 seed: {r1}")
    print(f"二次 seed: {r2}")
    print(f"分组: { {k: len(v) for k, v in groups.items()} }")
    print("✓ 掌门/宗主编制正确")
    print("\n✅ 全阵容 NPC 测试通过")


if __name__ == "__main__":
    main()
