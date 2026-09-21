from pathlib import Path
import re

p = Path(r"D:\codex\xiuxian\ai\play_prompts.py")
t = p.read_text(encoding="utf-8")
new = '''def scene_banter_prompt(**kwargs: Any) -> str:
    persona = kwargs.get("persona") or ""
    return (
        "你是同场旁听的修仙 NPC。只插与当前话题强相关的一句。\\n"
        + (persona + "\\n" if persona else "")
        + f"你是 {kwargs.get('name')}\\n"
        f"场上：{kwargs.get('main_npc')} 与 {kwargs.get('player')}。\\n"
        f"话题关键词：{kwargs.get('brief')}\\n"
        f"最近对话：{kwargs.get('tail')}\\n"
        "20~45 字；无关则输出空。只输出 JSON。\\n"
        f"{_JSON_ONLY}\\n"
        '输出：{"line":""}'
    )


'''
m = re.search(r"def scene_banter_prompt.*?\n\n\n", t, re.S)
if not m:
    raise SystemExit("scene_banter_prompt not found")
p.write_text(t[: m.start()] + new + t[m.end() :], encoding="utf-8")
print("patched scene_banter_prompt")
