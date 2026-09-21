from pathlib import Path

p = Path(r"D:\codex\xiuxian\workbench.js")
t = p.read_text(encoding="utf-8")
start = t.find("  function openChat(npcName) {")
end = t.find("  // ---------- views ----------")
if start < 0 or end < 0:
    raise SystemExit(f"markers {start} {end}")
new = r'''  function openChat(npcName) {
    state.chat.open = true;
    state.chat.npc = npcName || "";
    $("detailTitle").textContent = "交谈 · " + (npcName || "");
    const titleEl = $("chatTitle");
    if (titleEl) titleEl.textContent = "交谈 · " + (npcName || "同道");
    $("composeMode").textContent = "言语";
    $("composeTarget").textContent = "交谈对象：" + (npcName || "");
    const m = $("chatModal");
    if (m) {
      m.classList.remove("hidden");
      m.setAttribute("aria-hidden", "false");
    }
    document.body.classList.add("side-open");
    renderChatModal();
    renderDetail();
    if (state.view === "here") renderView();
    const inp = $("chatInput");
    if (inp) {
      inp.disabled = false;
      setTimeout(function () { inp.focus(); }, 40);
    }
  }

  function closeChat() {
    state.chat.open = false;
    state.chat.npc = "";
    $("detailTitle").textContent = "详情";
    const titleEl = $("chatTitle");
    if (titleEl) titleEl.textContent = "交谈";
    $("composeMode").textContent = "敕令";
    $("composeTarget").textContent = "未锁定交谈";
    const m = $("chatModal");
    if (m) {
      m.classList.add("hidden");
      m.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("side-open");
    renderDetail();
    if (state.view === "here") renderView();
  }

  function chatAppend(who, text, cls) {
    state.chat.lines.push({ who: who, text: text, cls: cls || "npc" });
    if (state.chat.lines.length > 80) state.chat.lines = state.chat.lines.slice(-80);
    renderChatModal(true);
    renderDetail(true);
  }

  function chatMessagesHtml() {
    const lines = state.chat.lines;
    if (!lines.length) return '<div class="msg sys">会话已开 · 在弹窗输入框直接说话</div>';
    return lines
      .map(function (l) {
        if (l.cls === "sys") return '<div class="msg sys">' + esc(l.text) + "</div>";
        return (
          '<div class="msg ' +
          esc(l.cls) +
          '"><span class="who">' +
          esc(l.who || "") +
          "</span>" +
          esc(l.text) +
          "</div>"
        );
      })
      .join("");
  }

  function renderChatModal(scroll) {
    const log = $("chatLog");
    if (!log) return;
    log.innerHTML = chatMessagesHtml();
    if (scroll) log.scrollTop = log.scrollHeight;
  }

  function renderDetail(scroll) {
    const body = $("detailBody");
    if (!body) return;
    if (!state.chat.open) {
      body.innerHTML =
        '<div class="detail-empty"><div><strong style="display:block;color:var(--ink-2);margin-bottom:6px">选一位同道</strong>点击同场列表会弹出聊天窗。</div></div>';
      return;
    }
    body.innerHTML =
      '<div class="chat-log">' +
      chatMessagesHtml() +
      '</div><div class="action-row"><button type="button" class="btn sm" data-cmd="/会话">会话记忆</button><button type="button" class="btn sm" id="btnOpenChatModal">打开聊天窗</button></div>';
    if (scroll) {
      const log = body.querySelector(".chat-log");
      if (log) log.scrollTop = log.scrollHeight;
    }
  }

  function sendChatModal(text) {
    const c = (text || "").trim();
    if (!c || state.busy) return;
    chatAppend("你", c, "me");
    if (state.demo) {
      chatAppend(state.chat.npc || "对方", "（演示）已收到。接服务器后可真实结算。", "npc");
      return;
    }
    busy(true);
    const sendBtn = $("chatSend");
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = "…";
    }
    api("/chat", { token: state.token, text: c, to: state.chat.npc || undefined })
      .then(function (data) {
        handleChatResult(data);
      })
      .catch(function (e) {
        chatAppend("", "发送失败：" + e.message, "sys");
        toast(e.message, "bad");
      })
      .finally(function () {
        busy(false);
        if (sendBtn) {
          sendBtn.disabled = false;
          sendBtn.textContent = "发送";
        }
        const inp = $("chatInput");
        if (inp && state.chat.open) inp.focus();
      });
  }

  function handleChatResult(data) {
    if (!data) return;
    if (data.status) applyStatus(data.status);
    const text = data.text || data.error || "";
    if (data.ok === false) {
      chatAppend("", text || "操作未完成", "sys");
      pushFeed(text, "bad");
      return;
    }
    if (data.chat_open) {
      if (data.npc && data.npc !== state.chat.npc) {
        state.chat.npc = data.npc;
        const titleEl = $("chatTitle");
        if (titleEl) titleEl.textContent = "交谈 · " + data.npc;
        $("composeTarget").textContent = "交谈对象：" + data.npc;
      }
      if (text) {
        String(text)
          .split("\n")
          .filter(Boolean)
          .forEach(function (ln) {
            if (/会话开始|可开口|挂断|作别|【同场】|会话记忆|直接打字|上次交谈/.test(ln)) {
              chatAppend("", ln, "sys");
            } else {
              chatAppend(data.npc || state.chat.npc || "对方", ln.replace(/^「|」$/g, ""), "npc");
            }
          });
        pushFeed(text, "npc");
      }
      return;
    }
    if (data.chat_ended) {
      chatAppend("", text || "会话已结束。", "sys");
      pushFeed(text, "sys");
      return;
    }
    if (text) {
      chatAppend(data.npc || "系统", text, "npc");
      pushFeed(text);
    }
  }

'''
p.write_text(t[:start] + new + t[end:], encoding="utf-8")
print("replaced openChat block", start, end)
