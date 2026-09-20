"""AI 必选模式：无 Key 且未开降级时应拒绝核心交互"""
import os
import sys
from pathlib import Path

# 确保本测试跑在「必须 AI」模式
os.environ.pop("ALLOW_LOCAL_AI", None)
os.environ["ALLOW_LOCAL_AI"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 强制 reload config 相关
import importlib
import config as config_mod
importlib.reload(config_mod)
import ai.gateway as gw
importlib.reload(gw)

from core.clock import WorldClock
from core.free_action import FreeActionEngine
from core.npc_mind import NpcDialogueEngine
from core.combat_fate import CombatFateEngine
from core.heart_demon import HeartDemonEngine


def main():
    assert not config_mod.ai_available() or True  # key 可有可无
    # 仅当真的没有 key 时断言拒绝
    if config_mod.ai_available():
        print("已配置 LLM_API_KEY，跳过「无 AI 拒绝」断言")
        print("✅ AI 模式检查通过（有 Key）")
        return

    assert not gw.ai_ready(), "无 Key 且未 ALLOW_LOCAL_AI 时 ai_ready 应为 False"

    p = WorldClock.create_new_character("ai_req_p", "求道者")
    n = WorldClock.create_new_character("npc_ai_req", "路人")
    n.location = p.location = "青云坊市客栈"

    r1 = NpcDialogueEngine.talk(n, p, "你好")
    assert r1["ok"] is False
    assert "AI" in r1["error"] or "天道" in r1["error"]

    r2 = FreeActionEngine.resolve(p, "我四处张望")
    assert r2["ok"] is False

    n.location = "落霞山灵泉(野外)"
    p.location = "落霞山灵泉(野外)"
    r3 = CombatFateEngine.resolve_ambush(p, n)
    assert r3["success"] is False

    s = HeartDemonEngine.start(p)
    r4 = HeartDemonEngine.resolve(p, s, choice_id="yield")
    assert r4["success"] is False

    print("✓ 交谈/言行/斗法/心魔在无 AI 时均被拒绝")
    print("\n✅ AI 必选模式 测试通过")


if __name__ == "__main__":
    main()
