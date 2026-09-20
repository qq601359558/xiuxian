"""网页一世循环：死亡→道统→转世 服务端测试"""
import os
os.environ["ALLOW_LOCAL_AI"] = "1"
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.world import World
from core.models import CharacterStatus
from storage.db import init_db, CharacterRepository


def main():
    init_db()
    w = World(auto_tick=False)
    j = w.join("一世道人")
    tok = j["token"]
    assert j.get("legacy_points") is not None

    look = w.handle(tok, "/look")
    assert look["ok"] and look.get("status")
    assert look["status"]["name"] == "一世道人"
    print("✓ /look 返回结构化 status")

    here = w.handle(tok, "/here")
    assert here["ok"]
    print("✓ /here 可用")

    lg = w.handle(tok, "/legacy")
    assert lg["ok"] and "points" in lg
    print(f"✓ /legacy points={lg['points']} boosts={len(lg['boosts'])}")

    # 强制死亡
    char = w.get_char(tok)
    char.status = CharacterStatus.DEAD
    char.lifespan.death_timestamp = 0
    char.death_cause = "测试坐化"
    CharacterRepository.save(char)

    # 死后 look 应标 dead
    look2 = w.handle(tok, "/look")
    assert look2.get("status", {}).get("dead") is True
    print("✓ 死亡后 status.dead=true")

    # 转世（道号全局唯一）
    import time as _t
    n2 = f"二世{int(_t.time()) % 100000}"
    r = w.reincarnate(tok, name=n2, boosts=["stones"])
    assert r["ok"], r
    assert n2 in r["name"]
    assert r.get("settle") is not None
    print(f"✓ 转世成功：{r['text'][:40]}…")

    look3 = w.handle(tok, "/look")
    assert look3["status"]["name"] == r["name"]
    assert not look3["status"]["dead"]
    print("✓ 转世后命盘为新角色")

    print("\n✅ 网页一世循环（服务端）测试通过")


if __name__ == "__main__":
    main()
