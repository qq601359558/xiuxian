import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from storage.db import init_db, CharacterRepository
from core.npc_mind import ensure_mind, _is_npc
from core.npc_agenda import ensure_agenda

init_db()
chars = CharacterRepository.list_all_alive()
npcs = [c for c in chars if _is_npc(c)]
players = [c for c in chars if not _is_npc(c)]
print(f"存活角色总数: {len(chars)}")
print(f"NPC: {len(npcs)} | 玩家: {len(players)}")
print("--- NPC 明细 ---")
for c in npcs:
    m = ensure_mind(c)
    ag = ensure_agenda(c)
    print(
        f"{c.name} | {c.realm.name} | {c.location} | "
        f"业力{c.karma.sin_value}/功德{c.karma.merit_value} | "
        f"性格:{m['personality']} | 议程:{ag.get('agenda_type')}"
    )
if players:
    print("--- 玩家 ---")
    for c in players:
        print(f"{c.name} | {c.realm.name} | {c.location}")
