from pathlib import Path
import re

p = Path(r"D:\codex\xiuxian\workbench.js")
t = p.read_text(encoding="utf-8")

# 1) 强化 openChat / 补 ensureChatVisible
old_open = """  function openChat(npc) {
    state.chat.open = true;
    state.chat.npc = npc || \"\";
    setText(\"chatTitle\", \"交谈 · \" + (npc || \"同道\"));
    setText(\"cmdTarget\", \"交谈：\" + (npc || \"—\"));
    setText(\"cmdTag\", \"言语\");
    const m = $(\"chatModal\");
    if (m) {
      m.classList.remove(\"hidden\");
      m.style.display = \"\";
      m.setAttribute(\"aria-hidden\", \"false\");
    }
    if (!state.chat.lines.length) {
      state.chat.lines = [{ cls: \"sys\", text: \"会话已开 · 在下方直接说话\" }];
    }
    renderChat(true);
    const inp = $(\"chatInput\");
    if (inp) setTimeout(() => inp.focus(), 50);
  }
"""

new_open = """  function openChat(npc) {
    state.chat.open = true;
    if (npc) state.chat.npc = npc;
    const who = state.chat.npc || \"同道\";
    setText(\"chatTitle\", \"交谈 · \" + who);
    setText(\"cmdTarget\", \"交谈：\" + who);
    setText(\"cmdTag\", \"言语\");
    const m = $(\"chatModal\");
    if (m) {
      m.classList.remove(\"hidden\");
      m.style.display = \"\";
      m.style.visibility = \"visible\";
      m.style.pointerEvents = \"auto\";
      m.style.opacity = \"1\";
      m.setAttribute(\"aria-hidden\", \"false\");
    }
    if (!state.chat.lines.length) {
      state.chat.lines = [{ cls: \"sys\", text: \"会话已开 · 在下方直接说话\" }];
    }
    renderChat(true);
    const inp = $(\"chatInput\");
    if (inp) {
      try { inp.disabled = false; } catch (e) {}
      setTimeout(() => { try { inp.focus(); } catch (e) {} }, 50);
    }
  }

  function ensureChatVisible() {
    try {
      const m = $(\"chatModal\");
      if (!m) {
        openChat(state.chat.npc);
        return;
      }
      const hidden = m.classList.contains(\"hidden\")
        || m.style.display === \"none\"
        || m.style.visibility === \"hidden\";
      if (hidden) openChat(state.chat.npc);
    } catch (e) {
      try { openChat(state.chat.npc); } catch (e2) {}
    }
  }
"""

if old_open not in t:
    # fallback: insert ensureChatVisible after openChat function end by regex
    m = re.search(r"  function openChat\(npc\) \{.*?\n  \}\n", t, re.S)
    if not m:
        raise SystemExit("openChat not found")
    t = t[: m.end()] + "\n  function ensureChatVisible() {\n    try {\n      const m = $(\"chatModal\");\n      if (!m || m.classList.contains(\"hidden\") || m.style.display === \"none\" || m.style.visibility === \"hidden\") openChat(state.chat.npc);\n    } catch (e) {}\n  }\n" + t[m.end() :]
    # patch openChat internals
    t = t.replace(
        """      m.classList.remove(\"hidden\");
      m.style.display = \"\";
      m.setAttribute(\"aria-hidden\", \"false\");""",
        """      m.classList.remove(\"hidden\");
      m.style.display = \"\";
      m.style.visibility = \"visible\";
      m.style.pointerEvents = \"auto\";
      m.style.opacity = \"1\";
      m.setAttribute(\"aria-hidden\", \"false\");""",
    )
    print("patched via fallback")
else:
    t = t.replace(old_open, new_open)
    print("patched openChat block")

p.write_text(t, encoding="utf-8")
print("has ensureChatVisible", "function ensureChatVisible" in t)
print("has visibility visible", 'visibility = "visible"' in t)
