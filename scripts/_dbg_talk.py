import os
import sys

sys.path.insert(0, r"D:\codex\xiuxian")
os.environ["ALLOW_LOCAL_AI"] = "1"

from server.world import World
import dis

fn = World.handle
print("consts types:")
for c in fn.__code__.co_consts:
    if isinstance(c, tuple):
        strs = [x for x in c if isinstance(x, str)]
        if strs and any(s in ("/talk", "/交谈") or "talk" in str(s) for s in strs):
            print(" TUPLE", c[:8], "..." if len(c) > 8 else "")
    elif isinstance(c, str) and ("talk" in c or "交" in c):
        print(" STR", c[:60])

# 直接 eval 条件：从代码对象看 LOAD_CONST
print("--- dis snippet around talk ---")
# 用 co_lnotab 查找 1496 附近
import linecache

print("co_firstlineno", fn.__code__.co_firstlineno)
print("co_name", fn.__code__.co_name)

# 执行并 tracer
import sys

def tracer(frame, event, arg):
    if frame.f_code is fn.__code__ and event == "line":
        if frame.f_lineno and 1490 <= frame.f_lineno <= 1505:
            print("LINE", frame.f_lineno, frame.f_locals.get("action"), frame.f_locals.get("parts", [])[:2])
    return tracer

from storage.db import init_db
from core.clock import WorldClock
from storage.db import CharacterRepository
import config

config.ALLOW_LOCAL_AI = True
config.LLM_API_KEY = ""
init_db()
w = World(auto_tick=False)
s = w.join("调试五", user_id="dbg_talk_5")
tok = s["token"]
ch = w.get_char(tok)
ch.location = "青云坊市客栈"
CharacterRepository.save(ch)
npc = WorldClock.create_new_character("npc_dbg_ls5", "柳三娘")
npc.location = "青云坊市客栈"
CharacterRepository.save(npc)

sys.settrace(tracer)
r = w.handle(tok, "/交谈 柳三娘")
sys.settrace(None)
print("RESULT", r)
