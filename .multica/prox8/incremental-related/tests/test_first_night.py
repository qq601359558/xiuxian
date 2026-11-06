"""第一晚：入世后必有天道、同场、一步结果"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ALLOW_LOCAL_AI", "1")
os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("LLM_API_KEY", "")

import config

config.ALLOW_LOCAL_AI = True
config.LLM_API_KEY = ""
config.USE_CCSWITCH = False

from storage.db import init_db
from server.world import World


def test_new_life_first_night_payload():
    init_db()
    w = World(auto_tick=False)
    name = f"初夜{int(time.time()) % 100000}"
    sess = w.join(name, user_id=f"firstnight_{int(time.time())}")
    assert sess.get("token")
    assert sess.get("newbie_feed"), sess
    assert "初入道" in sess.get("newbie_feed", "") or "第一" in sess.get("newbie_feed", "")
    fn = sess.get("first_night")
    assert fn is not None, sess.keys()
    # 同场应有人（花名册）
    tok = sess["token"]
    here = w.handle(tok, "/here")
    assert here.get("ok") is True
    assert isinstance(here.get("here"), list)
    assert len(here.get("here") or []) >= 1, here
    # 天道可读
    td = w.handle(tok, "/天道")
    assert td.get("ok") is True and "天道" in td.get("text", "")
    # 一步结果：同场点名可搭话或 buy
    if here.get("here"):
        nm = here["here"][0]["name"]
        talk = w.handle(tok, f"/交谈 {nm}")
        assert talk.get("ok") is True or talk.get("chat_open") or talk.get("error"), talk
    print("✓ 第一晚：newbie_feed + first_night + 同场有人 + 天道可读")


def test_resume_has_tour_stable():
    init_db()
    w = World(auto_tick=False)
    name = f"再入{int(time.time()) % 100000}"
    s1 = w.join(name, user_id=f"fn2_{int(time.time())}")
    tok = s1["token"]
    s2 = w.join(name, user_id=s1.get("user_id"))
    assert s2.get("token") or s2.get("resumed") is not None
    r = w.handle(tok, "/look")
    assert r.get("ok") is True
    print("✓ 重复入世稳定")


if __name__ == "__main__":
    test_new_life_first_night_payload()
    test_resume_has_tour_stable()
    print("first night tests passed")
