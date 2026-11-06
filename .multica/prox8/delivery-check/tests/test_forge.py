"""AI 造化：生成物去重与落库"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.forge import forge, exclusion_names
from storage.db import GeneratedNameRepository, init_db
import config
import ai.gateway as gw

config.LLM_API_KEY = ""
config.USE_CCSWITCH = False
gw.LLM_API_KEY = ""
gw.USE_CCSWITCH = False


def test_forge_unique_and_persist():
    init_db()
    banned0 = exclusion_names()
    r1 = forge("pill", "回春")
    assert r1["success"], r1
    n1 = r1["item"]["name"]
    assert n1 not in banned0
    assert GeneratedNameRepository.get(n1) is not None
    assert n1 in exclusion_names()
    # 再生成不得与本轮已出、或系统名撞名
    seen = {n1}
    for i in range(8):
        r = forge("pill")
        assert r["success"]
        n = r["item"]["name"]
        assert n not in seen, n
        assert GeneratedNameRepository.get(n) is not None
        seen.add(n)
    print("✓ 丹药生成去重落库", n1)

    e = forge("equip", "剑")
    assert e["success"] and e["item"]["kind"] == "equip"
    assert e["item"]["name"] in exclusion_names()
    m = forge("monster")
    assert m["success"] and m["item"]["kind"] == "monster"
    print("✓ 法宝/妖兽", e["item"]["name"], m["item"]["name"])

    # 数值钳制
    assert 0.08 <= r1["item"]["pill_exp_mult"] <= 0.50
    assert 0.02 <= e["item"]["power_bonus"] <= 0.12


if __name__ == "__main__":
    test_forge_unique_and_persist()
    print("\n✅ 天工造化测试通过")
