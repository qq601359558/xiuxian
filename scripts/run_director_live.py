"""实测：真 AI 通道探测 + /天道推演一轮，打印提案质量摘要"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 不要用本地降级，走真实通道
os.environ["ALLOW_LOCAL_AI"] = "0"
os.environ["AI_REQUIRED"] = "1"

import importlib
import config

importlib.reload(config)
# 若 .env 已加载 Key，确保 runtime 不被测试环境覆盖成空
print("=== 配置 ===")
print("LLM_API_BASE", config.LLM_API_BASE)
print("LLM_MODEL", config.LLM_MODEL)
print("ai_available", config.ai_available())
print("USE_CCSWITCH", config.USE_CCSWITCH)
print("ALLOW_LOCAL_AI(runtime)", config.ALLOW_LOCAL_AI)

from ai.gateway import probe_ai_channel
from core.world_director import WorldDirector, director_quality_report

print("\n=== /ai 通道探测 ===")
health = probe_ai_channel(force=True)
print(health)

print("\n=== 导师链路自检 ===")
q = director_quality_report()
print(f"{q['passed']}/{q['total']} ready_for_ai={q['ready_for_ai_director']}")
for c in q["checks"]:
    mark = "OK" if c["ok"] else "NG"
    print(f"  [{mark}] {c['name']}: {c.get('detail','')}")

print("\n=== /天道 推演 ===")
res = WorldDirector.run_cycle(trigger="command", force=True)
print("ok", res.get("ok"), "source", res.get("source"), "count", res.get("count"))
print("hint", res.get("brief_hint"), "error", res.get("error") or res.get("message"))
for d in res.get("directives") or []:
    print("---")
    print("type", d.get("type"), "source", d.get("source"))
    print("title", d.get("title"))
    print("narrative", d.get("narrative"))
    print("location", d.get("location"), "effects", d.get("effects"))
print("arcs_spawned", len(res.get("arcs_spawned") or []))

print("\n=== /天道 面板 ===")
print(WorldDirector.format_heaven_board())
