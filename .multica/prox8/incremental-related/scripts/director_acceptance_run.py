"""连续多轮真 AI 导师推演，统计提案类型分布"""
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "0"
os.environ["AI_REQUIRED"] = "1"

from ai.gateway import probe_ai_channel
from core.world_director import WorldDirector, director_quality_report
from core.world_arc import active_arcs
from core.faction import faction_modifiers
from core.player_echo import echo_modifiers
from core.era_reentry import active_bias


def main():
    health = probe_ai_channel(force=True)
    print("AI", health.get("ok"), health.get("model"), health.get("error") or "")
    q = director_quality_report()
    print(f"chain {q['passed']}/{q['total']} ready={q['ready_for_ai_director']}")
    types = Counter()
    sources = Counter()
    all_dirs = []
    for i in range(4):
        print(f"\n===== ROUND {i+1} force=True =====")
        res = WorldDirector.run_cycle(trigger="command", force=True)
        print("ok", res.get("ok"), "src", res.get("source"), "n", res.get("count"), "err", res.get("error") or res.get("message") or "")
        for d in res.get("directives") or []:
            types[d.get("type")] += 1
            sources[d.get("source")] += 1
            all_dirs.append(d)
            print(f"  [{d.get('type')}/{d.get('source')}] {d.get('title')} @{d.get('location') or '-'}")
            print(f"    {str(d.get('narrative'))[:80]}")
            print(f"    effects={d.get('effects')}")
        print("arcs_spawned", len(res.get("arcs_spawned") or []))
        # 清活跃以免 max_active 挡后续（保留统计）
        try:
            from storage.db import WorldStateRepository
            st = WorldStateRepository.get("director") or {}
            # 只清 active，保留 stats/history
            WorldStateRepository.set(
                "director",
                {
                    **st,
                    "active": [],
                    "last_run_ts": 0,
                },
            )
        except Exception as e:
            print("clear", e)
    print("\n===== TYPE DIST =====")
    for k, v in types.most_common():
        print(f"  {k}: {v}")
    print("sources", dict(sources))
    print("bias", active_bias())
    print("arcs now", len(active_arcs()))
    print("faction", faction_modifiers())
    print("echo panic", echo_modifiers().get("market_panic"))
    print("\n===== BOARD =====")
    print(WorldDirector.format_heaven_board())
    return types


if __name__ == "__main__":
    main()
