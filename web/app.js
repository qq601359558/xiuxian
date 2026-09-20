/* 天道因果录 · 网页客户端 — 点击为主，指令栏默认收起 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    base: localStorage.getItem("td_base") || "http://127.0.0.1:8765",
    token: localStorage.getItem("td_token") || "",
    name: localStorage.getItem("td_name") || "",
    uid: localStorage.getItem("td_uid") || "",
    username: localStorage.getItem("td_user") || "",
    authMode: "login",
    busy: false,
    pendingDemon: false,
    selectedBoosts: [],
    lastLegacy: null,
    composerOpen: false,
    chatEnded: false,
  };
  let lastCmd = "";

  function ensureUid() {
    if (state.uid) return state.uid;
    // 本机稳定账号 ID（同一浏览器续玩）
    const rnd =
      (crypto && crypto.randomUUID)
        ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
        : "uid" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    state.uid = rnd;
    localStorage.setItem("td_uid", state.uid);
    return state.uid;
  }

  // ---------- utils ----------
  function log(text, cls) {
    if (!text) return;
    const el = document.createElement("div");
    el.className = "line " + (cls || "");
    el.textContent = text;
    const box = $("log");
    box.appendChild(el);
    // 保留最近 400 条，避免卡顿
    while (box.children.length > 400) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setText(id, v) {
    const el = $(id);
    if (el && v != null && v !== "") el.textContent = v;
  }

  // ---------- 世界演变态势卡 ----------
  function renderEvolution(data) {
    const grid = $("evoGrid");
    const sum = $("evoSummary");
    const meta = $("evoMeta");
    if (!grid) return;
    if (meta) {
      const ts = data && data.updated_at ? new Date(Number(data.updated_at) * 1000) : new Date();
      meta.textContent = "更新 " + ts.toLocaleTimeString();
    }
    if (sum) {
      const lines = (data && data.summary_lines) || [];
      sum.textContent = lines.length ? lines.join(" · ") : "世界暂稳，可 /天道 推演";
    }
    const d = (data && data.director) || {};
    const arcs = (data && data.arcs) || [];
    const fm = ((data && data.faction) || {}).modifiers || {};
    const em = ((data && data.echo) || {}).modifiers || {};
    const bias = ((data && data.era) || {}).bias_cn || {};
    const blood = (data && data.blood) || [];
    const realms = (data && data.realms_open) || [];
    const panic = Number(em.market_panic || 0);
    const sieges = fm.active_sieges || [];
    const rels = ((data && data.faction) || {}).relations || [];
    const nHostile = rels.filter((r) => r.status === "hostile").length;
    const biasTop = Object.keys(bias)
      .sort((a, b) => Number(bias[b]) - Number(bias[a]))
      .slice(0, 2)
      .map((k) => k + Number(bias[k]).toFixed(0))
      .join(" ");
    const cells = [
      { h: "天道导演", v: String((d.active || []).length), p: d.last_source ? "来源 " + d.last_source : "暂无活跃", cls: (d.active || []).length ? "ok" : "" },
      { h: "世界弧", v: String(arcs.length), p: arcs[0] ? arcs[0].title : "无进行中", cls: arcs.length ? "ok" : "" },
      { h: "宗门围剿", v: String(sieges.length), p: sieges[0] ? sieges[0].sect + "→" + sieges[0].target : nHostile ? "敌对 " + nHostile : "格局平稳", cls: sieges.length ? "warn" : "" },
      { h: "坊市恐慌", v: panic.toFixed(0), p: em.market_reason || (panic < 8 ? "平稳" : "人心浮动"), cls: panic >= 30 ? "warn" : "" },
      { h: "凶地热点", v: String((em.hot_regions || []).length), p: (em.hot_regions || []).length ? (em.hot_regions || []).slice(0, 2).map((x) => x[0]).join("、") : "无显著", cls: (em.hot_regions || []).length ? "warn" : "ok" },
      { h: "血煞/重业", v: String(blood.length), p: blood[0] ? blood[0].name + "@" + (blood[0].location || "") : "天道清朗", cls: blood.length ? "warn" : "ok" },
      { h: "秘境开启", v: String(realms.length), p: realms[0] ? String(realms[0].name || realms[0]) : "暂无", cls: realms.length ? "ok" : "" },
      { h: "史笔回流", v: biasTop || "—", p: biasTop ? "影响下一拍提案" : "传说未积", cls: "" },
    ];
    grid.innerHTML = cells
      .map(function (c) {
        return '<div class="evo-cell ' + (c.cls || "") + '"><h4>' + esc(c.h) + '</h4><div class="v">' + esc(c.v) + "</div><p>" + esc(c.p) + "</p></div>";
      })
      .join("");
  }

  async function loadEvolutionCard() {
    const meta = $("evoMeta");
    try {
      const base = (state.base || "").replace(/\/$/, "");
      const res = await fetch(base + "/world/director");
      if (!res.ok) throw new Error(res.statusText || String(res.status));
      const data = await res.json();
      const evoSrc = data.evolution || {};
      const d = evoSrc.director || data.director || {};
      const em = ((evoSrc.echo || data.echo) || {}).modifiers || (evoSrc.echo && evoSrc.echo.modifiers) || ((data.echo || {}).modifiers) || {};
      const fm = ((evoSrc.faction || data.faction) || {}).modifiers || ((data.faction || {}).modifiers) || {};
      const ev = {
        updated_at: data.server_time || evoSrc.updated_at || Date.now() / 1000,
        director: d,
        arcs: evoSrc.arcs || data.arcs || [],
        faction: evoSrc.faction || data.faction || {},
        echo: { modifiers: em, board_text: evoSrc.echo_board_text || (data.echo || {}).board_text || "" },
        era: evoSrc.era || data.era || {},
        blood: evoSrc.blood || [],
        realms_open: evoSrc.realms_open || [],
        summary_lines: data.summary_lines || evoSrc.summary_lines || [],
      };
      if (!ev.summary_lines.length) {
        const n = (d.active || []).length;
        ev.summary_lines.push(n ? "天道活跃态势 " + n + " 条" : "天道暂无活跃态势");
        if ((ev.arcs || []).length) ev.summary_lines.push("世界弧 " + ev.arcs.length + " 场");
        if ((fm.active_sieges || []).length) ev.summary_lines.push("宗门围剿 " + fm.active_sieges.length);
        if (Number(em.market_panic || 0) >= 8) ev.summary_lines.push("坊市恐慌 " + Number(em.market_panic).toFixed(0));
        if ((em.hot_regions || []).length) ev.summary_lines.push("凶地 " + em.hot_regions.length);
      }
      renderEvolution(ev);
    } catch (e) {
      if (meta) meta.textContent = "态势卡不可用：" + (e && e.message ? e.message : e);
      // 回退：走 /世情 文本里的 evolution
      try {
        if (state.token) {
          const r = await api("/action", { token: state.token, command: "/世情 简" });
          if (r && r.evolution) renderEvolution(r.evolution);
        }
      } catch (e2) {}
    }
  }

  function bindEvoCard() {
    const btn = $("evoRefresh");
    if (btn && !btn._bound) {
      btn._bound = true;
      btn.addEventListener("click", function () {
        loadEvolutionCard();
      });
    }
  }

  async function api(path, body) {
    const url = state.base.replace(/\/$/, "") + path;
    const opts = body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : { method: "GET" };
    const res = await fetch(url, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.error || j.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return res.json();
  }

  function setBusy(b) {
    state.busy = b;
    const btn = $("btnJoin");
    if (btn) btn.disabled = b;
  }

  function setBar(id, pct, low) {
    const el = $(id);
    if (!el) return;
    const p = Math.max(0, Math.min(100, pct));
    el.style.width = p + "%";
    const wrap = el.parentElement;
    if (wrap) wrap.classList.toggle("low", !!low);
  }

  // ---------- status ----------
  function applyStatus(st) {
    if (!st) return;
    if (st.name) {
      setText("stName", st.name);
      setText("avatarChar", (st.name || "修").slice(0, 1));
    }
    if (st.realm) {
      setText("stRealm", st.realm);
      setText("hudRealm", st.realm);
    }
    if (st.exp) {
      setText("stExp", st.exp);
      setText("hudExp", st.exp);
      const m = String(st.exp).match(/(\d+)\s*\/\s*(\d+)/);
      if (m) {
        const cur = +m[1], max = +m[2] || 1;
        setBar("stExpBar", (cur / max) * 100);
        setBar("hudExpBar", (cur / max) * 100);
      }
    }
    if (st.location) {
      setText("stLoc", st.location);
      setText("hudLoc", st.location);
      setText("sceneName", st.location);
      setText("sceneChip", st.location);
    }
    if (st.root) setText("stRoot", st.root);
    if (st.stones != null) {
      setText("stStones", st.stones);
      setText("hudStones", st.stones);
    }
    if (st.vault != null) setText("stVault", st.vault);
    if (st.rem_years != null) {
      const y = Number(st.rem_years);
      const label = (Math.round(y * 10) / 10) + " 岁";
      setText("stLife", label);
      setText("hudLife", label);
      // 出生寿元约 70–100，用 100 做满槽
      const pct = Math.max(0, Math.min(100, (y / 100) * 100));
      setBar("stLifeBar", pct, y < 10);
      setBar("hudLifeBar", pct, y < 10);
      const lifeEl = $("stLife");
      if (lifeEl) lifeEl.style.color = y < 10 ? "var(--blood)" : "";
    }
    if (st.sin != null || st.merit != null) {
      setText("stKarma", (st.sin || 0) + " / " + (st.merit || 0));
    }
    if (st.qi_mult != null) {
      const q = Number(st.qi_mult);
      const t = q.toFixed(2) + "x";
      setText("stQi", t);
      setText("hudQi", t);
    }

    // 庇护 / 冲突区 / 闭关
    const labels = [];
    let warn = false;
    if (st.meditating || st.status === "MEDITATING") {
      labels.push("闭关入定");
    }
    if (st.newbie_protected) {
      labels.push("新手 " + (st.newbie_left_hours || 0) + "h");
    }
    if (st.protect) labels.push(st.protect);
    if (st.conflict_zone) {
      labels.push("冲突区");
      warn = true;
    }
    const pill = $("stProt");
    const note = $("stProtRow");
    if (pill) {
      if (labels.length) {
        pill.textContent = labels[0];
        pill.classList.remove("hide");
        pill.classList.toggle("warn", warn);
      } else {
        pill.classList.add("hide");
      }
    }
    if (note) {
      if (labels.length) {
        note.textContent = labels.join(" · ") + "　不可被攻击时随身财货不可转移";
        note.classList.remove("hide");
        note.classList.toggle("warn", warn);
      } else {
        note.classList.add("hide");
      }
    }

    // 地点安全标签
    const zone = $("zoneTag");
    if (zone) {
      if (st.meditating || st.status === "MEDITATING") {
        zone.textContent = "闭关";
        zone.className = "tag warn";
      } else if (st.conflict_zone) {
        zone.textContent = "凶域";
        zone.className = "tag danger";
      } else if (st.location) {
        zone.textContent = "安全";
        zone.className = "tag safe";
      }
    }

    // 闭关时迁跃按钮弱化提示
    const med = !!(st.meditating || st.status === "MEDITATING");
    document.querySelectorAll("[data-go]").forEach((b) => {
      b.style.opacity = med ? "0.45" : "";
      b.title = med ? "闭关锁门中，请先出关" : "";
    });

    // 场景说明
    if (st.location) {
      setText("sceneMeta", "输入 /做 可自由言行；点迁跃换地，点同场看人。");
    }
  }

  function parseLookFallback(text) {
    if (!text) return;
    const name = (text.match(/【([^】]+)】/) || [])[1];
    const realm = (text.match(/】\s*([^\s|]+)/) || [])[1];
    const loc = (text.match(/位置：([^（\n]+)/) || [])[1];
    const stones = (text.match(/随身灵石\s*(\d+)/) || [])[1];
    const vault = (text.match(/金库\s*(\d+)/) || [])[1];
    const sin = (text.match(/业力\s*(\d+)/) || [])[1];
    const life = (text.match(/寿元约([\d.]+)岁/) || [])[1];
    if (name) {
      setText("stName", name);
      setText("avatarChar", name.slice(0, 1));
    }
    if (realm) {
      setText("stRealm", realm);
      setText("hudRealm", realm);
    }
    if (loc) {
      const l = loc.trim();
      setText("stLoc", l);
      setText("hudLoc", l);
      setText("sceneName", l);
      setText("sceneChip", l);
    }
    if (stones) {
      setText("stStones", stones);
      setText("hudStones", stones);
    }
    if (vault) setText("stVault", vault);
    if (sin) setText("stKarma", sin + " / —");
    if (life) {
      const y = Number(life);
      setText("stLife", life + " 岁");
      setText("hudLife", life + " 岁");
      setBar("stLifeBar", y, y < 10);
      setBar("hudLifeBar", y, y < 10);
    }
  }

  function parseHereList(hereArr) {
    const box = $("hereList");
    if (!box) return;
    box.innerHTML = "";
    const cnt = $("hereCount");
    if (cnt) cnt.textContent = hereArr && hereArr.length ? hereArr.length + " 人" : "";
    if (!hereArr || !hereArr.length) {
      box.innerHTML = '<p class="empty">此地暂无其他修士</p>';
      return;
    }
    for (const r of hereArr) {
      const card = document.createElement("div");
      card.className = "here-card";
      const att = r.attitude_cn || (r.is_npc ? "中立" : "—");
      const attCls =
        r.attitude === "hostile" || r.attitude === "wary"
          ? "att-hostile"
          : r.attitude === "friendly" || r.attitude === "ally"
          ? "att-friendly"
          : "";
      const rank = r.rank ? r.rank + "·" : "";
      const pers = r.personality ? `性格 ${r.personality}` : "";
      const ag = r.agenda
        ? `议程 ${r.agenda}${r.agenda_progress != null ? " " + r.agenda_progress + "/5" : ""}`
        : "";
      const blood = r.blood_marked ? ' <span class="blood">血煞</span>' : "";
      card.innerHTML =
        `<div class="nm"><a href="#" class="nm-link" data-profile="${esc(r.name)}">${esc(r.name)}</a>${blood}</div>` +
        `<div class="meta">${esc(r.realm)} · ${esc(r.sect || "散修")}${rank}<br/>` +
        `${pers ? pers + " · " : ""}${r.is_npc ? "对你：" : ""}` +
        `<span class="${attCls}">${esc(att)}</span>${ag ? " · " + ag : ""}</div>` +
        `<div class="acts">` +
        `<button data-talk="${esc(r.name)}">交谈</button>` +
        `<button data-fight="${esc(r.name)}">斗法</button>` +
        `<button data-profile="${esc(r.name)}">人物</button>` +
        `</div>`;
      box.appendChild(card);
    }
  }

  // ---------- tabs ----------
  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.getAttribute("data-tab") === name);
    });
    document.querySelectorAll(".pane").forEach((p) => {
      p.classList.toggle("active", p.id === "pane-" + name);
    });
    if (name === "world") {
      bindEvoCard();
      loadEvolutionCard();
    }
  }

  function openComposer(open) {
    state.composerOpen = !!open;
    const c = $("cmdForm");
    if (!c) return;
    c.classList.toggle("open", state.composerOpen);
    if (state.composerOpen) {
      const inp = $("cmdInput");
      if (inp) inp.focus();
    }
  }

  function ensureToggle() {
    if ($("toggleCmd")) return;
    const stage = document.querySelector(".stage");
    if (!stage) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "toggleCmd";
    btn.className = "toggle-cmd";
    btn.textContent = "高级敕令";
    btn.title = "展开/收起指令输入（默认关闭，按钮即可游玩）";
    btn.addEventListener("click", () => openComposer(!state.composerOpen));
    stage.appendChild(btn);
  }

  // ---------- refresh ----------
  async function refreshSoft(silent) {
    if (!state.token) return;
    try {
      const look = await api("/action", { token: state.token, command: "/look" });
      if (look.ok) {
        if (look.status) applyStatus(look.status);
        else parseLookFallback(look.text || "");
      }
      const here = await api("/action", { token: state.token, command: "/here" });
      if (here.ok && here.here) parseHereList(here.here);
    } catch (e) {
      if (!silent) log("刷新失败：" + e.message, "err");
    }
  }

  // ---------- send ----------
  async function send(cmd) {
    if (!state.token) {
      log("尚未入世，请先登录。", "err");
      return;
    }
    if (state.busy) {
      log("天道正在裁决，稍候…", "sys");
      return;
    }
    const c = (cmd || "").trim();
    if (!c) return;

    // 用户可见：仅在打开指令栏时显示 » 前缀；按钮操作也记一行短令
    log("» " + c, "cmd");
    switchTab("feed");
    setBusy(true);
    try {
      const data = await api("/action", { token: state.token, command: c });
      handleResult(data);
    } catch (e) {
      log("失败：" + e.message, "err");
    } finally {
      setBusy(false);
      if (state.composerOpen) {
        const input = $("cmdInput");
        if (input) input.focus();
      }
    }
  }

  // ---------- NPC 会话窗 ----------
  const chatEl = () => $("chatModal");
  function chatAppend(who, text, cls) {
    const box = $("chatLog");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "msg " + (cls || "npc");
    el.textContent = who ? who + "：" + text : text;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  }
  function openChat(npcName) {
    const m = chatEl();
    if (!m) return;
    m.classList.remove("hidden");
    m.setAttribute("aria-hidden", "false");
    state.chatEnded = false;
    setChatInputEnabled(true);
    if ($("chatNpcName") && npcName) $("chatNpcName").textContent = "交谈 · " + npcName;
    const inp = $("chatInput");
    if (inp) inp.focus();
  }
  function setChatInputEnabled(on) {
    const inp = $("chatInput");
    const form = $("chatForm");
    if (inp) {
      inp.disabled = !on;
      inp.placeholder = on ? "说点什么…（回车发送；可写动作如「递上丹药」）" : "会话已结束（点 × 关闭）";
    }
    if (form) {
      const btn = form.querySelector("button[type=submit], button.btn-primary");
      if (btn) btn.disabled = !on;
    }
  }
  function markChatEnded(text) {
    state.chatEnded = true;
    setChatInputEnabled(false);
    if (text) {
      const lines = String(text).split("\n").filter(Boolean);
      for (const ln of lines) chatAppend("", ln, "sys");
    }
  }
  function closeChat() {
    const m = chatEl();
    if (!m) return;
    m.classList.add("hidden");
    m.setAttribute("aria-hidden", "true");
    state.chatEnded = false;
    setChatInputEnabled(true);
  }
  function handleChatPayload(data, text) {
    if (data.chat_open) {
      openChat(data.npc || "");
      if (data.ok && text) {
        const lines = text.split("\n").filter(Boolean);
        for (const ln of lines) {
          if (/会话开始|用 \/说|可开口/.test(ln)) chatAppend("", ln, "sys");
          else if (/【会话已终】|作别|不愿再言|挂断|动手|赠礼|成交|行窃|擒拿|释放/.test(ln)) chatAppend("", ln, "sys");
          else chatAppend(data.npc || "对方", ln.replace(/^「|」$/g, ""), "npc");
        }
      } else if (!data.ok && data.error) {
        chatAppend("", data.error, "sys");
      }
      return true;
    }
    if (data.chat_ended) {
      // 挂断后不自动关窗：玩家看清结果后手动 ×
      markChatEnded(text || data.error || "会话已结束。");
      return true;
    }
    return false;
  }

  // ---------- 奇遇弹窗 ----------
  function omenAppend(who, text, cls) {
    const box = $("omenLog");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "msg " + (cls || "npc");
    el.textContent = who ? who + "：" + text : text;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  }
  function openOmen(title) {
    const m = $("omenModal");
    if (!m) return;
    m.classList.remove("hidden");
    m.setAttribute("aria-hidden", "false");
    if ($("omenTitle") && title) $("omenTitle").textContent = "奇遇 · " + title;
    const inp = $("omenInput");
    if (inp) inp.focus();
  }
  function closeOmen() {
    const m = $("omenModal");
    if (!m) return;
    m.classList.add("hidden");
    m.setAttribute("aria-hidden", "true");
    const chips = $("omenChips");
    if (chips) chips.innerHTML = "";
  }
  function parseOmenChoices(text) {
    const m = /选项：(.+)/.exec(text || "");
    if (!m) return [];
    return m[1].split("|").map((s) => s.trim()).filter(Boolean);
  }
  function handleOmenPayload(data, text) {
    if (!data.omen_open && !data.omen_ended) return false;
    if (data.omen_open) {
      openOmen(data.omen_title || "奇遇");
      const meta = $("omenMeta");
      if (meta && text) {
        const g = /目标：(.+)/.exec(text);
        const p = /进度：(.+)/.exec(text);
        const s = /灵石 (\d+).*修为 (\d+)\/(\d+)/.exec(text);
        meta.textContent = [g && g[1], p && p[1], s && `灵石${s[1]} 修为${s[2]}/${s[3]}`]
          .filter(Boolean).join(" · ");
      }
      if (data.ok && text) {
        for (const ln of text.split("\n").filter(Boolean)) {
          if (/【奇遇|目标：|进度：|选项：|灵石 /.test(ln)) omenAppend("", ln, "sys");
          else omenAppend("", ln, "npc");
        }
        const chips = $("omenChips");
        if (chips) {
          chips.innerHTML = "";
          for (const c of parseOmenChoices(text)) {
            const id = c.split(".")[0];
            const label = c.replace(/^\d+\./, "");
            const b = document.createElement("button");
            b.type = "button";
            b.className = "chip";
            b.textContent = label;
            b.addEventListener("click", () => {
              omenAppend("你", "（选择）" + label, "me");
              lastCmd = "/奇遇";
              send("/奇遇 " + id);
            });
            chips.appendChild(b);
          }
        }
      }
      return true;
    }
    if (data.omen_ended) {
      if (text) omenAppend("", text, "sys");
      setTimeout(closeOmen, 1800);
      return true;
    }
    return false;
  }

  (function bindChat() {
    const form = $("chatForm");
    const inp = $("chatInput");
    const btn = $("chatClose");
    if (form && inp) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        if (state.chatEnded) return;
        const v = (inp.value || "").trim();
        if (!v) return;
        inp.value = "";
        chatAppend("你", v, "me");
        lastCmd = "/说";
        send("/说 " + v);
      });
    }
    if (btn) {
      btn.addEventListener("click", () => {
        if (!state.chatEnded) {
          lastCmd = "/挂断";
          send("/挂断");
        }
        closeChat();
      });
    }
  })();

  (function bindOmen() {
    const form = $("omenForm");
    const inp = $("omenInput");
    const btn = $("omenClose");
    if (form && inp) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const v = (inp.value || "").trim();
        if (!v) return;
        inp.value = "";
        omenAppend("你", v, "me");
        lastCmd = "/奇遇说";
        send("/奇遇说 " + v);
      });
    }
    if (btn) {
      btn.addEventListener("click", () => {
        lastCmd = "/奇遇";
        send("/奇遇 弃");
        closeOmen();
      });
    }
  })();

  function handleResult(data) {
    const text = data.text || data.error || "";
    const isErr = data.ok === false || !!data.error;

    if (data.pending_heart_demon) {
      state.pendingDemon = true;
      showDemon(data.text, data.heart_demon_options || []);
      log(text, "demon");
      return;
    }
    if (data.heart_demon) {
      state.pendingDemon = false;
      hideDemon();
    }

    // 命盘同步（奇遇/交易等均带 status）
    if (data.status) applyStatus(data.status);

    // 奇遇窗
    if (handleOmenPayload(data, text)) {
      return;
    }
    // NPC 会话窗
    if (handleChatPayload(data, text)) {
      return;
    }

    let cls = isErr ? "err" : "ok";
    if (!isErr && /心魔|天劫|陨落|坐化|杀|血|【/.test(text)) cls = "ai";
    // 多行长文进 feed；短结果也进 feed
    log(text, cls);

    // 目标类结果切到目标页
    if (lastCmd && /目标/.test(lastCmd) && !isErr) {
      const gb = $("goalsBody");
      if (gb) gb.textContent = text;
      switchTab("goals");
    }
    // 世间类结果
    if (lastCmd && /榜|宗门|秘境|灵气|纪元|who|天下|告示|坊市|世情|世界演变|天道|势力|望气|世界弧|纪元回流/.test(lastCmd) && !isErr) {
      const wb = $("worldBody");
      if (wb) wb.textContent = text;
      if (data.evolution) renderEvolution(data.evolution);
      // /世情 /世界演变 也刷新态势卡
      if (/世情|世界演变|演变/.test(lastCmd)) loadEvolutionCard();
      // 不强制切走，保留 feed 可见
    }

    if (data.status) applyStatus(data.status);

    if (data.death || (data.fatal && data.legacy)) {
      const legacy = data.legacy || {};
      state.lastLegacy = legacy;
      showDeath(text, legacy);
      return;
    }

    if (data.ok && data.boosts_applied !== undefined && data.settle !== undefined) {
      log(data.text || "转世完成", "ok");
      applyStatus({
        name: data.name,
        realm: data.realm,
        location: data.location,
        rem_years: data.rem_years,
      });
      hideDeath();
      refreshSoft(true);
      return;
    }

    const needRefresh =
      data.ok !== false &&
      (/^\/(go|前往|斗法|fight|闭关|meditate|出关|emerge|突破|break|机缘|event|做|do|回访|revenge|tick|世情|归隐|出隐|拜入|叛门|领俸禄|晋升|传功|寄存|秘境)/i.test(
        lastCmd
      ) ||
        data.here ||
        data.target_died ||
        data.spawned ||
        data.protect ||
        data.logout_kind);

    if (needRefresh || lastCmd === "/look" || lastCmd === "/here") {
      refreshSoft(true);
    }
  }

  // ---------- prompt modal ----------
  let promptCfg = null;
  function openPrompt(title, hint, prefix, placeholder, numeric) {
    promptCfg = { prefix: prefix || "", numeric: !!numeric };
    $("promptTitle").textContent = title || "输入";
    $("promptHint").textContent = hint || "";
    const inp = $("promptInput");
    inp.value = "";
    inp.placeholder = placeholder || "";
    inp.inputMode = numeric ? "numeric" : "text";
    $("promptModal").classList.remove("hidden");
    setTimeout(() => inp.focus(), 30);
  }
  function closePrompt() {
    $("promptModal").classList.add("hidden");
    promptCfg = null;
  }
  function confirmPrompt() {
    if (!promptCfg) return;
    const v = $("promptInput").value.trim();
    if (!v) {
      $("promptInput").focus();
      return;
    }
    if (promptCfg.numeric && !/^\d+$/.test(v)) {
      $("promptHint").textContent = "请输入正整数";
      return;
    }
    const cmd = (promptCfg.prefix + " " + v).trim();
    closePrompt();
    lastCmd = cmd;
    send(cmd);
  }

  // ---------- demon ----------
  function showDemon(fullText, options) {
    $("demonModal").classList.remove("hidden");
    let narrative = fullText || "";
    const idx = narrative.indexOf("【心魔问心】");
    if (idx >= 0) narrative = narrative.slice(idx + 6);
    const optIdx = narrative.indexOf("选项：");
    if (optIdx > 0) narrative = narrative.slice(0, optIdx);
    $("demonText").textContent = narrative.trim() || "心魔幻境已开……";

    const box = $("demonOpts");
    box.innerHTML = "";
    (options || []).forEach((o, i) => {
      const b = document.createElement("button");
      b.textContent = `${i + 1}. ${o.label}${o.style ? "（" + o.style + "）" : ""}`;
      b.onclick = () => {
        hideDemon();
        lastCmd = "心魔选择";
        send(String(i + 1));
      };
      box.appendChild(b);
    });
    if (!options || !options.length) {
      const b = document.createElement("button");
      b.textContent = "暂避锋芒";
      b.onclick = () => {
        hideDemon();
        send("yield");
      };
      box.appendChild(b);
    }
  }

  function hideDemon() {
    $("demonModal").classList.add("hidden");
    $("demonFree").value = "";
  }

  // ---------- death / rebirth ----------
  function showDeath(text, legacy) {
    $("deathModal").classList.remove("hidden");
    const cause = legacy.death_cause || "身死道消";
    $("deathText").textContent =
      "本世道途已终（" + cause + "）。真灵可携道统重入轮回。";
    $("deathLegacy").innerHTML =
      `道统点 <b>${legacy.points ?? 0}</b> · 已历 <b>${legacy.lives ?? 0}</b> 世<br/>` +
      `可选出身加成（至多 ${legacy.max_boosts ?? 3} 项）`;

    const box = $("boostBox");
    box.innerHTML = "";
    state.selectedBoosts = [];
    (legacy.boosts || []).forEach((b) => {
      const el = document.createElement("div");
      el.className = "boost-item";
      el.innerHTML = `<span>${esc(b.name)}</span><span class="muted">${esc(b.desc)}</span><span class="cost">${b.cost}点</span>`;
      el.onclick = () => {
        const max = legacy.max_boosts || 3;
        if (state.selectedBoosts.includes(b.key)) {
          state.selectedBoosts = state.selectedBoosts.filter((k) => k !== b.key);
          el.classList.remove("selected");
        } else {
          if (state.selectedBoosts.length >= max) {
            log(`至多选 ${max} 项出身加成`, "err");
            return;
          }
          state.selectedBoosts.push(b.key);
          el.classList.add("selected");
        }
      };
      box.appendChild(el);
    });
    $("rebornName").value = "";
  }

  function hideDeath() {
    $("deathModal").classList.add("hidden");
  }

  async function doReborn() {
    const name = $("rebornName").value.trim();
    let cmd = "/转世";
    if (name) cmd += " " + name;
    if (state.selectedBoosts.length) cmd += " " + state.selectedBoosts.join(" ");
    hideDeath();
    lastCmd = cmd;
    await send(cmd);
  }

  // ---------- join / register / login ----------
  function enterWorld(data, msg) {
    state.token = data.token;
    localStorage.setItem("td_token", data.token);
    if (data.user_id) {
      state.uid = data.user_id;
      localStorage.setItem("td_uid", data.user_id);
    }
    if (data.username) {
      state.username = data.username;
      localStorage.setItem("td_user", data.username);
    }
    if (data.name) {
      state.name = data.name;
      localStorage.setItem("td_name", data.name);
    }
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    log(msg || (data.resumed ? `【续玩】${data.name} · ${data.realm}` : `【入世】${data.name} · ${data.realm} · ${data.location}`), "ok");
    if (data.rem_years != null) {
      log(`自然寿元约 ${data.rem_years} 岁 · 道统池 ${data.legacy_points || 0} 点`, "sys");
    }
    if (data.newbie_feed) log(data.newbie_feed, "ok");
    applyStatus({
      name: data.name,
      realm: data.realm,
      location: data.location,
      rem_years: data.rem_years,
    });
  }

  async function authJoin() {
    const base = $("serverUrl").value.trim() || state.base;
    const user = ($("username") && $("username").value.trim()) || "";
    const pass = ($("password") && $("password").value) || "";
    const charName = ($("playerName") && $("playerName").value.trim()) || user;
    state.base = base.replace(/\/$/, "");
    localStorage.setItem("td_base", state.base);

    const isReg = state.authMode === "register";
    if (!user) {
      $("gateMsg").textContent = "请填写用户名";
      return;
    }
    if (!pass || pass.length < 6) {
      $("gateMsg").textContent = "密码至少 6 位";
      return;
    }
    $("gateMsg").textContent = isReg ? "注册中…" : "登录中…";
    setBusy(true);
    try {
      const path = isReg ? "/register" : "/login";
      const data = await api(path, {
        username: user,
        password: pass,
        name: charName,
      });
      enterWorld(
        data,
        isReg
          ? `【注册成功】${data.name} · ${data.realm}`
          : data.resumed
          ? `【登录成功·续玩】${data.name} · ${data.realm}`
          : `【登录成功】${data.name} · ${data.realm}`
      );
      try {
        const h = await api("/health");
        if (h.ok) setText("aiBadge", "服在线");
      } catch (_) {
        setText("aiBadge", "服离线");
      }
      await refreshSoft(true);
      startPolling();
      ensureToggle();
    } catch (e) {
      $("gateMsg").textContent = e.message || "认证失败";
    } finally {
      setBusy(false);
    }
  }

  // ---------- events ----------
  $("btnJoin").addEventListener("click", authJoin);
  $("playerName").addEventListener("keydown", (e) => {
    if (e.key === "Enter") authJoin();
  });
  const pwEl = $("password");
  if (pwEl) pwEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") authJoin();
  });
  const tabLogin = $("tabLogin");
  const tabReg = $("tabReg");
  const fieldChar = $("fieldChar");
  function setAuthMode(m) {
    state.authMode = m;
    if (tabLogin) tabLogin.classList.toggle("active", m === "login");
    if (tabReg) tabReg.classList.toggle("active", m === "register");
    if (fieldChar) fieldChar.style.display = m === "register" ? "" : "none";
    if ($("btnJoin")) $("btnJoin").textContent = m === "register" ? "注 册" : "登 录";
  }
  if (tabLogin) tabLogin.addEventListener("click", () => setAuthMode("login"));
  if (tabReg) tabReg.addEventListener("click", () => setAuthMode("register"));
  setAuthMode("login");

  const gateForm = $("gateForm");
  if (gateForm) {
    gateForm.addEventListener("submit", (e) => {
      e.preventDefault();
      authJoin();
    });
  }

  $("cmdForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("cmdInput").value;
    lastCmd = v;
    $("cmdInput").value = "";
    send(v);
  });

  document.querySelectorAll("[data-cmd]").forEach((btn) => {
    btn.addEventListener("click", () => {
      lastCmd = btn.getAttribute("data-cmd");
      send(lastCmd);
    });
  });

  document.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const dest = btn.getAttribute("data-go");
      lastCmd = "/go " + dest;
      send(lastCmd);
    });
  });

  document.querySelectorAll("[data-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const title = btn.getAttribute("data-prompt") || "输入";
      const prefix = btn.getAttribute("data-cmd-prefix") || "";
      const ph = btn.getAttribute("data-placeholder") || "";
      const numeric = btn.getAttribute("data-num") === "1";
      const hints = {
        拜入: "须亲至总坛山门。可填：青云宗 / 万剑仙门 / 九幽天魔宗 / 四海散修商会",
        传功: "须同门且境界高于对方",
        寄存: "存入坊市金库，不可被夺；归隐中不可操作",
        支取: "从金库取出灵石",
        寄售: "货名 价格，如：妖兽内丹 60",
        买寄售: "寄售编号（先点坊市）",
        撤单: "自己的寄售编号",
        挂赏: "道号 赏金 [缘由]，句末加「匿」可匿名",
        接令: "告示编号（先点告示）",
        自创功法: "理念短语，如：噬血炼骨 / 玄天正气",
        探险: "野外 / 剑冢残碑 / 荒古兽巢 / 幽冥鬼市 / 灵药残圃 / 落霞古洞 等",
        穿戴: "装备名，如：青锋剑 / 玄铁护腕",
        卸下: "已穿戴的装备名",
        购买: "先点「坊市」看货单。示例：聚气丹 / 筑基丹 / 一阶青木迷踪阵",
        出售: "卖给商会，约五折回收。示例：妖兽内丹 1",
        服用: "丹药名，如：聚气丹 / 筑基丹",
      };
      openPrompt(title, hints[title] || "", prefix, ph, numeric);
    });
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      switchTab(tab.getAttribute("data-tab"));
      if (tab.getAttribute("data-tab") === "goals") {
        lastCmd = "/目标";
        send("/目标");
      }
    });
  });

  $("promptOk").addEventListener("click", confirmPrompt);
  $("promptCancel").addEventListener("click", closePrompt);
  $("promptInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmPrompt();
    if (e.key === "Escape") closePrompt();
  });
  $("promptModal").addEventListener("click", (e) => {
    if (e.target === $("promptModal")) closePrompt();
  });

  const hereList = $("hereList");
  if (hereList) {
    hereList.addEventListener("click", (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement)) return;
      const talk = t.getAttribute("data-talk");
      const fight = t.getAttribute("data-fight");
      const prof = t.getAttribute("data-profile");
      if (t.classList && t.classList.contains("nm-link")) e.preventDefault();
      if (prof) {
        lastCmd = "/人物 " + prof;
        send(lastCmd);
        return;
      }
      if (talk) {
        lastCmd = "/交谈 " + talk;
        openPrompt(
          "交谈 · " + talk,
          "输入想说的话；留空仅拱手一礼。",
          "/交谈 " + talk,
          "例如：打听血刀老祖下落 / 可有买卖？",
          false
        );
        return;
      } else if (fight) {
        if (confirm("确定对「" + fight + "」动手？")) {
          lastCmd = "/斗法 " + fight;
          send(lastCmd);
        }
      }
    });
  }

  $("demonFreeGo").addEventListener("click", () => {
    const v = $("demonFree").value.trim();
    if (!v) return;
    hideDemon();
    lastCmd = v;
    send(v);
  });
  $("demonFree").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("demonFreeGo").click();
  });

  $("btnReborn").addEventListener("click", doReborn);
  $("btnLater").addEventListener("click", () => {
    hideDeath();
    log("真灵暂驻轮回。下次「入世」将自动转世。", "sys");
  });

  $("btnLogout").addEventListener("click", async () => {
    if (!state.token) return;
    if (!confirm("暂离红尘？将按庇护/逃遁规则结算。")) return;
    lastCmd = "/下线";
    await send("/下线");
    localStorage.removeItem("td_token");
    state.token = "";
    stopPolling();
    $("app").classList.add("hidden");
    $("gate").classList.remove("hidden");
    $("gateMsg").textContent = "";
  });

  // ---------- 世界频道 ----------
  const wstate = {
    lastSeenTs: parseFloat(localStorage.getItem("td_wseen") || "0") || 0,
    unread: 0,
    toastTimer: null,
  };

  function fmtWts(ts) {
    try {
      const d = new Date((ts || 0) * 1000);
      const p = (n) => String(n).padStart(2, "0");
      return `${p(d.getHours())}:${p(d.getMinutes())}`;
    } catch (e) {
      return "";
    }
  }

  function appendWorldMsg(m) {
    const box = $("worldFeed");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "wmsg " + (m.level || "info");
    const ts = document.createElement("span");
    ts.className = "ts";
    ts.textContent = fmtWts(m.ts);
    el.appendChild(ts);
    el.appendChild(document.createTextNode(m.text || ""));
    box.appendChild(el);
    while (box.children.length > 80) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  function showToast(text, level) {
    const t = $("worldToast");
    if (!t) return;
    t.textContent = text;
    t.className = "show " + (level || "");
    if (wstate.toastTimer) clearTimeout(wstate.toastTimer);
    wstate.toastTimer = setTimeout(() => {
      t.classList.remove("show");
    }, 4000);
  }

  function updateWorldBadge() {
    const b = $("worldBadge");
    if (!b) return;
    if (wstate.unread > 0) {
      b.textContent = String(wstate.unread);
      b.classList.remove("hidden");
    } else {
      b.classList.add("hidden");
    }
  }

  function markWorldSeen(ts) {
    if (ts > wstate.lastSeenTs) {
      wstate.lastSeenTs = ts;
      localStorage.setItem("td_wseen", String(ts));
    }
  }

  async function pollWorldMessages() {
    if (!state.base) return;
    try {
      const url =
        state.base.replace(/\/$/, "") +
        "/world/messages?since=" +
        encodeURIComponent(wstate.pollCursor || 0) +
        "&limit=20";
      const res = await fetch(url, { method: "GET" });
      if (!res.ok) return;
      const data = await res.json();
      if (!data || !data.ok || !Array.isArray(data.messages)) return;
      const worldTabActive =
        document.querySelector('.tab[data-tab="world"]') &&
        document.querySelector('.tab[data-tab="world"]').classList.contains("active");
      for (const m of data.messages) {
        appendWorldMsg(m);
        if (m.ts > (wstate.pollCursor || 0)) wstate.pollCursor = m.ts;
        if (m.level === "major" || m.level === "epic" || m.level === "gm") {
          if (m.ts > wstate.lastSeenTs) wstate.unread += 1;
        }
        if (m.level === "epic" || m.level === "gm") {
          showToast(m.text, m.level);
          if (typeof switchTab === "function") {
            switchTab("world");
            wstate.unread = 0;
            markWorldSeen(m.ts);
          }
        }
        if (m.ts > (wstate._shown || 0)) wstate._shown = m.ts;
      }
      // 仅在世界页可见时推进 lastSeen，保证刷新后角标仍在
      if (worldTabActive && wstate._shown) {
        wstate.unread = 0;
        markWorldSeen(wstate._shown);
      }
      updateWorldBadge();
    } catch (e) {
      /* 网络瞬断忽略 */
    }
  }

  // 打开世界页清零角标
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      if (tab.getAttribute("data-tab") === "world") {
        wstate.unread = 0;
        updateWorldBadge();
        if (wstate._shown) markWorldSeen(wstate._shown);
      }
    });
  });

  // ---------- 轮询：命盘 + 同场 ----------
  let pollTimer = null;
  let worldTimer = null;
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      if (!state.token || state.busy || state.pendingDemon) return;
      refreshSoft(true);
    }, 5000);
    worldTimer = setInterval(() => {
      pollWorldMessages();
      loadEvolutionCard();
    }, 20000);
    pollWorldMessages();
    bindEvoCard();
    loadEvolutionCard();
  }
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (worldTimer) {
      clearInterval(worldTimer);
      worldTimer = null;
    }
  }

  // 预填
  $("serverUrl").value = state.base;
  if (state.username && $("username")) $("username").value = state.username;
  else if (state.name && $("username")) $("username").value = state.name;
  if (state.name && $("playerName")) $("playerName").value = state.name;
  ensureToggle();
  openComposer(false);

  // 恢复会话：token 仍有效则续用；失效则用 user_id/道号自动重登
  (async function restore() {
    const tryEnter = async (token) => {
      const look = await api("/action", { token: token, command: "/look" });
      if (!look.ok) throw new Error(look.error || "look fail");
      state.token = token;
      localStorage.setItem("td_token", token);
      $("gate").classList.add("hidden");
      $("app").classList.remove("hidden");
      log("（已恢复上次会话）", "sys");
      if (look.text) log(look.text, "sys");
      if (look.status) applyStatus(look.status);
      else parseLookFallback(look.text || "");
      if (look.status && look.status.dead) {
        const lg = await api("/action", { token: token, command: "/legacy" });
        if (lg.ok) showDeath(look.text || "", lg);
      } else {
        refreshSoft(true);
        startPolling();
      }
    };

    if (state.token) {
      try {
        await tryEnter(state.token);
        return;
      } catch (_) {
        localStorage.removeItem("td_token");
        state.token = "";
      }
    }
    // token 失效：已有账号则尝试用 token 不行就提示登录（密码不在本地，无法静默重登）
    if (state.username || state.uid) {
      $("gateMsg").textContent = "会话已失效，请重新登录（角色数据已保存）";
    }
  })();
})();
