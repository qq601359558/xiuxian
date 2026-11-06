"""注册/登录账号"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["USE_CCSWITCH"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

from core.account import register, login
from server.world import World
from storage.db import init_db, AccountRepository


def test_register_login():
    init_db()
    import time
    uname = f"测修{int(time.time())%100000}"
    r = register(uname, "secret123")
    assert r["ok"] is True, r
    uid = r["user_id"]
    r2 = register(uname, "secret123")
    assert r2["ok"] is False

    bad = login(uname, "wrong")
    assert bad["ok"] is False
    good = login(uname, "secret123")
    assert good["ok"] is True and good["user_id"] == uid
    print("✓ 注册/登录/密码校验")


def test_login_loads_same_character():
    init_db()
    import time
    uname = f"账玩{int(time.time())%100000}"
    w = World(auto_tick=False)
    reg = register(uname, "passw0rd")
    assert reg["ok"], reg
    j = w.join(uname, user_id=reg["user_id"])
    tok = j["token"]
    char = w.get_char(tok)
    char.spirit_stones = 888
    from storage.db import CharacterRepository
    CharacterRepository.save(char)

    # 再次登录
    lg = login(uname, "passw0rd")
    j2 = w.join(uname, user_id=lg["user_id"])
    assert j2["resumed"] is True
    c2 = w.get_char(j2["token"])
    assert c2.spirit_stones == 888
    print("✓ 登录续玩同一角色")


if __name__ == "__main__":
    test_register_login()
    test_login_loads_same_character()
    print("\n✅ 账号注册登录测试通过")
