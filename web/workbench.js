/**
 * 天道因果录 · 工作台 v2（单轨唯一前端）
 * API: POST /register /login /action /chat /logout
 *      GET /health /commands /world/director
 */
(function () {
  "use strict";

  const PLACES = [
    { name: "青云坊市客栈", tip: "商会 · 安全" },
    { name: "青云宗外门山门", tip: "正道山门 · 安全" },
    { name: "宗门玄元洞府", tip: "闭关洞府 · 安全" },
    { name: "落霞山灵泉", tip: "野外灵泉 · 凶险" },
    { name: "万剑仙门峰", tip: "剑门 · 安全" },
    { name: "黑风绝渊", tip: "大凶之地" },
    { name: "万星古岛", tip: "遗迹残岛 · 凶险" },
    { name: "洗剑池洞天", tip: "剑门洞天" },
    { name: "九幽天魔宗坛", tip: "魔道总坛" },
  ];

  const $ = (id) => document.getElementById(id);
  const state = {
    base: localStorage.getItem("wb.base") || "http://127.0.0.1:8765",
    token: localStorage.getItem("wb.token") || "",
    user: localStorage.getItem("wb.user") || "",
    name: localStorage.getItem("wb.name") || "",
    uid: localStorage.getItem("wb.uid") || "",
    theme: localStorage.getItem("wb.theme") || "dark",
    mode: "login",
    view: "here",
    status: null,
    here: [],
    feed: [],
    world: null,
    commands: [],
    filter: "",
    locFilter: "",
    busy: false,
    offline: false,
    demo: false,
    chat: { open: false, npc: "", lines: [] },
    sug: [],
    sugI: 0,
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function setText(id, v) {
    const el = $(id);
    if (el) el.textContent = v == null || v === "" ? "—" : String(v);
  }

  function setTheme(t) {
    state.theme = t === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", state.theme);
    localStorage.setItem("wb.theme", state.theme);
  }

  function toast(msg, kind) {
    const host = $("toasts");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function setOffline(on) {
    state.offline = !!on;
    document.body.classList.toggle("is-offline", state.offline);
    const dot = $("connDot");
    const text = $("connText");
    if (!dot || !text) return;
    dot.classList.remove("on", "off");
    if (state.demo) {
      text.textContent = "离线演示";
      return;
    }
    if (on) {
      dot.classList.add("off");
      text.textContent = "连接中断";
    } else if (state.token) {
      dot.classList.add("on");
      text.textContent = (state.base || "").replace(/^https?:\/\//, "");
    } else {
      text.textContent = "未连接";
    }
  }

  async function api(path, body) {
    let base = (state.base || "").trim().replace(/\/$/, "");
    if (base && !/^https?:\/\//i.test(base)) base = "http://" + base;
    const url = base + path;
    const opts = body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : { method: "GET" };
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      setOffline(true);
      throw new Error("无法连接 " + base + "（请启动 server.run）");
    }
    if (!res.ok) {
      let msg = res.statusText || String(res.status);
      try {
        const j = await res.json();
        msg = j.error || j.message || msg;
      } catch (_) {}
      throw new Error(msg);
    }
    setOffline(false);
    return res.json();
  }

  function busy(on) {
    state.busy = !!on;
    const go = $("cmdGo");
    const send = $("chatSend");
    if (go) go.disabled = !!on;
    if (send) send.disabled = !!on;
    const rf = $("btnRefresh");
    if (rf) rf.disabled = !!on;
  }

  // ---------- 渲染：天道盘 ----------
  function applyStatus(st) {
    if (!st) return;
    state.status = Object.assign({}, state.status || {}, st);
    const s = state.status;
    setText("dName", s.name || state.name || "—");
    setText("dSect", (s.sect || "散修") + (s.rank && s.rank !== "散修" ? "·" + s.rank : ""));
    setText("dRealm", s.realm || "—");
    setText("dExp", s.exp || (s.meditating || s.status === "MEDITATING" ? "闭关中" : "行止自由"));
    setText("dLoc", s.location || "—");
    setText(
      "dSafe",
      s.location_safe === false || s.conflict_zone ? "凶险" : s.newbie_protected ? "庇护中" : "—"
    );
    const life = Number(s.rem_years || 0);
    setText("dLife", life ? life.toFixed(0) : "—");
    const le = $("dLife");
    if (le) le.className = "v " + (life && life < 15 ? "bad" : life < 40 ? "" : "ok");
    setText("dStones", s.stones != null ? s.stones : "—");
    setText("dVault", "金库 " + (s.vault != null ? s.vault : "—"));
    setText("dKarma", (s.sin || 0) + " / " + (s.merit || 0));
    const ke = $("dKarma");
    if (ke) ke.className = "v " + (s.sin >= 80 ? "bad" : s.merit >= 50 ? "ok" : "");
    setText("dBlood", s.blood_marked ? "血煞显影" : s.sin >= 80 ? "重业" : "尚清");
  }

  function pulseWorld() {
    const ev = (state.world && state.world.evolution) || {};
    const d = ev.director || {};
    const em = ((ev.echo || {}).modifiers) || {};
    const n = (d.active || []).length;
    const panic = Number(em.market_panic || 0);
    let label = "平稳";
    let cls = "ok";
    if (n) {
      label = "天道 " + n + " 势";
      cls = "";
    } else if (panic >= 30) {
      label = "坊市恐慌 " + panic.toFixed(0);
      cls = "bad";
    } else if ((ev.summary_lines || []).length) {
      label = "有讯";
    }
    setText("dWorld", label);
    const el = $("dWorld");
    if (el) el.className = "v " + cls;
    setText("dWorldSub", (ev.summary_lines || [])[0] || "天道态势");
  }

  // ---------- 视图 ----------
  const VIEWS = {
    here: { title: "同场修士", sub: "点人打开交谈玉简" },
    world: { title: "世界命盘", sub: "天道 · 弧 · 势力 · 望气 · 史笔" },
    feed: { title: "动态", sub: "敕令与世界消息" },
  };

  function setView(v) {
    if (!VIEWS[v]) v = "here";
    state.view = v;
    document.querySelectorAll(".rail-btn[data-view]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-view") === v);
    });
    setText("viewTitle", VIEWS[v].title);
    setText("viewSub", VIEWS[v].sub);
    renderBody();
  }

  function emptyState(title, desc, actions) {
    const acts = (actions || [])
      .map((a) => `<button type="button" class="btn sm" data-act="${esc(a.act)}">${esc(a.label)}</button>`)
      .join(" ");
    return `<div class="state"><strong>${esc(title)}</strong><p>${esc(desc)}</p><div class="actions" style="justify-content:center">${acts}</div></div>`;
  }

  function renderPlaces() {
    const box = $("locList");
    if (!box) return;
    const q = state.locFilter.trim();
    const cur = state.status && state.status.location;
    const rows = PLACES.filter((p) => !q || p.name.includes(q) || p.tip.includes(q));
    if (!rows.length) {
      box.innerHTML = `<div class="state" style="padding:24px 8px"><strong>无匹配</strong><p>换个关键词</p></div>`;
      return;
    }
    box.innerHTML = rows
      .map((p) => {
        const on = p.name === cur;
        return `<button type="button" class="place${on ? " on" : ""}" data-go="${esc(p.name)}">
          <div class="t">${esc(p.name)}</div>
          <div class="s">${esc(p.tip)}${on ? " · 当前" : ""}</div>
        </button>`;
      })
      .join("");
  }

  function renderHere() {
    const q = state.filter.trim();
    let rows = state.here || [];
    if (q) {
      rows = rows.filter(
        (r) =>
          (r.name || "").includes(q) ||
          (r.sect || "").includes(q) ||
          (r.realm || "").includes(q)
      );
    }
    if (!rows.length) {
      return emptyState(
        (state.here || []).length ? "无匹配同道" : "此地暂无其他修士",
        "可迁跃到坊市或宗门；也可在下方敕令里写 /做 描述行动。",
        [
          { label: "迁跃坊市", act: "go:青云坊市客栈" },
          { label: "看世界", act: "view:world" },
        ]
      );
    }
    return rows
      .map((r) => {
        const blood = !!r.blood_marked;
        const att = r.attitude_cn || (r.is_npc ? "中立" : "—");
        return `<button type="button" class="row" data-person="${esc(r.name)}">
          <div class="avatar ${blood ? "danger" : r.is_npc ? "npc" : ""}">${esc((r.name || "?").slice(0, 1))}</div>
          <div>
            <div class="nm">${esc(r.name)}</div>
            <div class="meta">${esc(r.realm || "")} · ${esc(r.sect || "散修")}${r.rank ? "·" + esc(r.rank) : ""} · 对你：${esc(att)}</div>
            <div class="chips">
              <span class="chip ${r.is_npc ? "ok" : "gold"}">${r.is_npc ? "NPC" : "修士"}</span>
              ${blood ? '<span class="chip bad">血煞</span>' : ""}
              ${r.personality ? `<span class="chip">${esc(r.personality)}</span>` : ""}
            </div>
          </div>
          <span class="btn sm primary">交谈</span>
        </button>`;
      })
      .join("");
  }

  function renderFeed() {
    const q = state.filter.trim();
    let rows = state.feed || [];
    if (q) rows = rows.filter((r) => String(r.text).includes(q));
    if (!rows.length) {
      return emptyState("暂无动态", "同场交谈、敕令结果与世界消息会出现在这里。", [
        { label: "同场", act: "view:here" },
        { label: "世界", act: "view:world" },
      ]);
    }
    return `<div class="feed">` +
      rows
        .slice()
        .reverse()
        .map((r) => {
          const t = new Date((r.ts || Date.now() / 1000) * 1000);
          const hh = t.toTimeString().slice(0, 5);
          const k = r.kind || "npc";
          const mark = k === "cmd" ? "/" : k === "ai" ? "天" : k === "bad" ? "!" : k === "ok" ? "成" : "·";
          return `<div class="feed-item">
            <div class="feed-dot ${esc(k)}">${mark}</div>
            <div class="feed-text${k === "cmd" ? " cmd" : ""}">${esc(r.text)}</div>
            <div class="feed-time">${hh}</div>
          </div>`;
        })
        .join("") +
      `</div>`;
  }

  function renderWorld() {
    const ev = (state.world && state.world.evolution) || {};
    if (!state.world && !state.demo) {
      return emptyState("世界态势未加载", "确认服务器已启动后点刷新。", [{ label: "刷新", act: "refresh" }]);
    }
    const d = ev.director || {};
    const arcs = ev.arcs || [];
    const fm = ((ev.faction || {}).modifiers) || {};
    const rels = ((ev.faction || {}).relations) || [];
    const em = ((ev.echo || {}).modifiers) || {};
    const bias = ((ev.era || {}).bias_cn) || {};
    const blood = ev.blood || [];
    const realms = ev.realms_open || [];
    const news = ev.channel_recent || [];
    const summary = (ev.summary_lines || []).join(" · ") || "世间暂稳";
    const panic = Number(em.market_panic || 0);
    const sieges = fm.active_sieges || [];
    const hostile = rels.filter((r) => r.status === "hostile");

    const kv = (k, v, cls) =>
      `<div class="kv-row"><div class="k">${esc(k)}</div><div class="v ${cls || ""}">${esc(v)}</div></div>`;

    return `
    <section class="block">
      <div class="block-head"><h3>此刻</h3><p>${esc(summary)}</p></div>
      <div class="kv">
        ${kv("天道来源", d.last_source || "—")}
        ${kv("活跃指令", (d.active || []).length)}
        ${kv("世界弧", arcs.length)}
        ${kv("坊市恐慌", panic.toFixed(0), panic >= 30 ? "bad" : panic < 8 ? "ok" : "")}
      </div>
    </section>
    <section class="block">
      <div class="block-head"><h3>天道导演</h3><p>AI 提案 · 规则落账</p></div>
      ${
        (d.active || []).length
          ? `<div class="kv">${(d.active || [])
              .slice(0, 5)
              .map((a) =>
                kv(
                  `[${a.type}] ${a.title}${a.location ? " @" + a.location : ""}`,
                  (a.narrative || "").slice(0, 22)
                )
              )
              .join("")}</div>`
          : `<div class="state" style="padding:12px 0;text-align:left"><p style="margin:0">暂无活跃指令，可在下方输入 <kbd>/天道 推演</kbd></p></div>`
      }
      <div class="actions">
        <button type="button" class="btn sm" data-cmd="/天道">天道</button>
        <button type="button" class="btn sm primary" data-cmd="/天道 推演">推演</button>
      </div>
    </section>
    <section class="block">
      <div class="block-head"><h3>世界弧</h3><p>预兆 → 升级 → 决算</p></div>
      ${
        arcs.length
          ? `<div class="kv">${arcs
              .slice(0, 5)
              .map((a) => kv(`[${a.stage}] ${a.title}`, a.kind))
              .join("")}</div>`
          : `<div class="state" style="padding:8px 0;text-align:left"><p style="margin:0">暂无进行中的弧。</p></div>`
      }
      <div class="actions"><button type="button" class="btn sm" data-cmd="/世界弧">弧详情</button></div>
    </section>
    <section class="block">
      <div class="block-head"><h3>势力</h3><p>关系 · 围剿 · 宗门令</p></div>
      <div class="kv">
        ${
          hostile.length
            ? hostile
                .map((r) => kv(`敌对 ${r.a} × ${r.b}`, String(r.score ?? ""), "bad"))
                .join("")
            : kv("敌对格局", "暂无显性敌对", "ok")
        }
        ${
          sieges.length
            ? sieges
                .slice(0, 3)
                .map((s) => kv(`围剿 ${s.sect} → ${s.target}`, s.loc || ""))
                .join("")
            : kv("宗门围剿", "无")
        }
        ${kv("开放宗门令", fm.n_open_missions || 0)}
      </div>
      <div class="actions">
        <button type="button" class="btn sm" data-cmd="/势力">势力</button>
        <button type="button" class="btn sm" data-cmd="/宗门令">宗门令</button>
      </div>
    </section>
    <section class="block">
      <div class="block-head"><h3>望气</h3><p>凶地与坊市</p></div>
      <div class="kv">
        ${kv("坊市", panic < 8 ? "平稳" : em.market_reason || "人心浮动", panic >= 30 ? "bad" : "")}
        ${
          (em.hot_regions || []).length
            ? (em.hot_regions || [])
                .map((h) => kv("凶地 " + h[0], Number(h[1]).toFixed(0), "bad"))
                .join("")
            : kv("凶地", "无显著热点", "ok")
        }
        ${blood.slice(0, 3).map((b) => kv("血煞 " + b.name, b.location || "", "bad")).join("")}
      </div>
      <div class="actions"><button type="button" class="btn sm" data-cmd="/望气">望气</button></div>
    </section>
    <section class="block">
      <div class="block-head"><h3>史笔 · 秘境</h3><p>纪元回流</p></div>
      <div class="kv">
        ${
          Object.keys(bias).length
            ? Object.keys(bias)
                .sort((a, b) => Number(bias[b]) - Number(bias[a]))
                .slice(0, 4)
                .map((k) => kv(k, Number(bias[k]).toFixed(1)))
                .join("")
            : kv("史笔权重", "传说未积")
        }
        ${
          realms.length
            ? realms.map((r) => kv("秘境 " + (r.name || r), r.location || "已开启", "ok")).join("")
            : kv("秘境", "暂无开启")
        }
      </div>
      <div class="actions">
        <button type="button" class="btn sm" data-cmd="/纪元回流">回流</button>
        <button type="button" class="btn sm" data-cmd="/秘境">天机榜</button>
      </div>
    </section>
    <section class="block">
      <div class="block-head"><h3>近闻</h3><p>详情 /频道</p></div>
      ${
        news.length
          ? `<div class="kv">${news
              .slice(0, 5)
              .map((n) => `<div class="kv-row"><div class="k" style="white-space:normal">${esc(n.text)}</div></div>`)
              .join("")}</div>`
          : `<div class="state" style="padding:8px 0;text-align:left"><p style="margin:0">风平浪静。</p></div>`
      }
      <div class="actions">
        <button type="button" class="btn sm" data-cmd="/频道">频道</button>
        <button type="button" class="btn sm" data-cmd="/世情">世界演变</button>
      </div>
    </section>`;
  }

  function renderBody() {
    const box = $("body");
    if (!box) return;
    if (state.view === "here") box.innerHTML = renderHere();
    else if (state.view === "feed") box.innerHTML = renderFeed();
    else box.innerHTML = renderWorld();
  }

  function pushFeed(text, kind) {
    if (!text) return;
    state.feed.push({ text: String(text), kind: kind || kindOf(text), ts: Date.now() / 1000 });
    if (state.feed.length > 240) state.feed = state.feed.slice(-240);
    if (state.view === "feed") renderBody();
  }

  function kindOf(text) {
    const t = String(text || "");
    if (/^»/.test(t)) return "cmd";
    if (/失败|错误|拒绝|不可|中断/.test(t)) return "bad";
    if (/天道|世界弧|围剿|大劫|血煞/.test(t)) return "ai";
    if (/成交|成功|已入世|已/.test(t)) return "ok";
    return "npc";
  }

  // ---------- 交谈玉简 ----------
  function closeChat(hangup) {
    // 1) 先关 UI，避免网络失败导致关不掉
    state.chat.open = false;
    state.chat.npc = "";
    try {
      setText("cmdTarget", "未锁定交谈");
      setText("cmdTag", "敕令");
    } catch (_) {}
    const modal = $("chatModal");
    if (modal) {
      modal.classList.add("hidden");
      modal.style.display = "none";
      modal.style.visibility = "hidden";
      modal.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("chat-open");
    // 2) 后台挂断（失败忽略）
    try {
      if (hangup && !state.demo && state.token) {
        api("/action", { token: state.token, command: "/挂断" })
          .then(() => {})
          .catch(() => {});
      }
    } catch (_) {}
  }

  function openChat(npc) {
    state.chat.open = true;
    state.chat.npc = npc || "";
    setText("chatTitle", "交谈 · " + (npc || "同道"));
    setText("cmdTarget", "交谈：" + (npc || "—"));
    setText("cmdTag", "言语");
    const m = $("chatModal");
    if (m) {
      m.classList.remove("hidden");
      m.style.display = "";
      m.setAttribute("aria-hidden", "false");
    }
    if (!state.chat.lines.length) {
      state.chat.lines = [{ cls: "sys", text: "会话已开 · 在下方直接说话" }];
    }
    renderChat(true);
    const inp = $("chatInput");
    if (inp) setTimeout(() => inp.focus(), 50);
  }

  function chatMsg(who, text, cls) {
    state.chat.lines.push({ who, text, cls: cls || "npc" });
    if (state.chat.lines.length > 100) state.chat.lines = state.chat.lines.slice(-100);
    renderChat(true);
  }

  function renderChat(scroll) {
    const log = $("chatLog");
    if (!log) return;
    log.innerHTML = (state.chat.lines || [])
      .map((l) => {
        if (l.cls === "sys") return `<div class="msg sys">${esc(l.text)}</div>`;
        return `<div class="msg ${esc(l.cls)}"><span class="who">${esc(l.who || "")}</span>${esc(l.text)}</div>`;
      })
      .join("");
    if (scroll) log.scrollTop = log.scrollHeight;
  }

  function handleChatData(data) {
    if (!data) return;
    if (data.status) applyStatus(data.status);
    const text = data.text || data.error || "";
    if (data.ok === false) {
      chatMsg("", text || "操作未完成", "sys");
      pushFeed(text, "bad");
      return;
    }
    if (data.chat_open) {
      if (data.npc && data.npc !== state.chat.npc) openChat(data.npc);
      String(text).split("\n").filter(Boolean).forEach((ln) => {
        if (/会话开始|可开口|挂断|同场】|会话记忆|直接打字/.test(ln)) chatMsg("", ln, "sys");
        else chatMsg(data.npc || "对方", ln.replace(/^「|」$/g, ""), "npc");
      });
      pushFeed(text, "npc");
      return;
    }
    if (data.chat_ended) {
      chatMsg("", text || "会话已结束", "sys");
      pushFeed(text);
    }
  }

  async function sendChat(text) {
    const c = (text || "").trim();
    if (!c || state.busy) return;
    chatMsg("你", c, "me");
    if (state.demo) {
      chatMsg(state.chat.npc || "对方", "（演示）已记录。接服务器后可真实结算。", "npc");
      return;
    }
    busy(true);
    try {
      const data = await api("/chat", {
        token: state.token,
        text: c,
        to: state.chat.npc || undefined,
      });
      handleChatData(data);
    } catch (e) {
      chatMsg("", "失败：" + e.message, "sys");
      toast(e.message, "bad");
    } finally {
      busy(false);
      const inp = $("chatInput");
      if (inp && state.chat.open) inp.focus();
    }
  }

  // ---------- 敕令 ----------
  function feedFromResult(data) {
    if (!data) return;
    const text = data.text || data.error || "";
    if (data.status) applyStatus(data.status);
    if (data.chat_open || data.chat_ended) {
      handleChatData(data);
      return;
    }
    if (text) pushFeed(text, data.ok === false ? "bad" : undefined);
    if (state.view !== "feed" && state.view !== "world") renderBody();
  }

  async function sendCmd(cmd) {
    const c = (cmd || "").trim();
    if (!c || state.busy) return;
    if (state.chat.open && !c.startsWith("/") && !c.startsWith("»")) {
      sendChat(c);
      return;
    }
    busy(true);
    try {
      if (!c.startsWith("»")) pushFeed("» " + c, "cmd");
      let data;
      if (state.demo) data = demoResult(c);
      else data = await api("/action", { token: state.token, command: c });
      feedFromResult(data);
    } catch (e) {
      pushFeed("失败：" + e.message, "bad");
      toast(e.message, "bad");
    } finally {
      busy(false);
      const inp = $("cmdInput");
      if (inp) inp.value = "";
      hideSug();
    }
  }

  function demoResult(c) {
    return { ok: true, text: "【演示】已记录敕令 " + c + "。接服务器后执行真实逻辑。" };
  }

  // ---------- 指令补全 ----------
  async function loadCommands() {
    if (state.demo) {
      state.commands = [
        { cmd: "/天道", usage: "/天道", desc: "天道导演态势" },
        { cmd: "/世情", usage: "/世情", desc: "世界演变" },
        { cmd: "/闭关", usage: "/闭关 [h]", desc: "吐纳修炼" },
        { cmd: "/坊市", usage: "/坊市", desc: "商会货单" },
      ];
      return;
    }
    try {
      const j = await api("/commands");
      state.commands = j.commands || [];
    } catch (_) {}
  }

  function fuzzy(q) {
    const query = (q || "").trim().toLowerCase();
    if (!query.startsWith("/")) return [];
    const all = state.commands || [];
    if (query === "/") return all.slice(0, 12).map((e) => Object.assign({}, e));
    const out = [];
    const core = query.replace(/^\//, "");
    for (const e of all) {
      const cmd = String(e.cmd || "").toLowerCase();
      const desc = String(e.desc || "").toLowerCase();
      let s = 0;
      if (cmd === query) s = 100;
      else if (cmd.startsWith(query)) s = 80;
      else if (core && cmd.indexOf(core) >= 0) s = 55;
      else if (core && desc.indexOf(core) >= 0) s = 40;
      if (s > 0) out.push(Object.assign({}, e, { score: s }));
    }
    out.sort((a, b) => b.score - a.score);
    return out.slice(0, 10);
  }

  function renderSug() {
    const el = $("suggest");
    const inp = $("cmdInput");
    if (!el || !inp) return;
    if (!inp.value || inp.value[0] !== "/") {
      el.classList.add("hidden");
      el.innerHTML = "";
      state.sug = [];
      return;
    }
    state.sug = fuzzy(inp.value);
    state.sugI = 0;
    if (!state.sug.length) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }
    el.innerHTML = state.sug
      .map(
        (it, i) =>
          `<button type="button" class="sug${i === 0 ? " on" : ""}" data-i="${i}">
            <div class="c">${esc(it.cmd)}<i>${esc(it.usage || "")}</i></div>
            <div class="d">${esc(it.desc || "")}</div>
          </button>`
      )
      .join("");
    el.classList.remove("hidden");
  }

  function applySug(i) {
    const it = state.sug[i];
    if (!it) return;
    const inp = $("cmdInput");
    const usage = String(it.usage || it.cmd);
    inp.value = /[<>|…]/.test(usage) ? usage : it.cmd + " ";
    $("suggest").classList.add("hidden");
    inp.focus();
  }

  function hideSug() {
    const el = $("suggest");
    if (el) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  }

  // ---------- 刷新 ----------
  function loading() {
    const box = $("body");
    if (!box) return;
    box.innerHTML = `<div class="state"><strong>加载中</strong><p>正在观照此界…</p></div>`;
  }

  async function refreshAll() {
    if (state.demo) {
      pulseWorld();
      renderPlaces();
      renderBody();
      return;
    }
    if (!state.token) return;
    loading();
    const errs = [];
    let look = null;
    let here = null;
    let world = null;
    try {
      look = await api("/action", { token: state.token, command: "/look" });
    } catch (e) {
      errs.push(e.message);
    }
    try {
      here = await api("/action", { token: state.token, command: "/here" });
    } catch (e) {
      errs.push(e.message);
    }
    try {
      world = await api("/world/director");
    } catch (e) {
      /* ignore */
    }
    if (look && look.status) applyStatus(look.status);
    else if (look && look.text) parseLook(look.text);
    if (here && Array.isArray(here.here)) state.here = here.here;
    if (world && world.ok !== false) state.world = world;
    pulseWorld();
    renderPlaces();
    renderBody();
    if (errs.length) toast("部分刷新失败：" + errs[0], "bad");
  }

  function parseLook(text) {
    const s = state.status || {};
    const name = (text.match(/【([^】]+)】/) || [])[1];
    const loc = (text.match(/位置：([^（\n]+)/) || [])[1];
    const stones = (text.match(/随身灵石\s*(\d+)/) || [])[1];
    const vault = (text.match(/金库\s*(\d+)/) || [])[1];
    const life = (text.match(/寿元约([\d.]+)/) || [])[1];
    if (name) s.name = name;
    if (loc) s.location = loc.trim();
    if (stones) s.stones = Number(stones);
    if (vault) s.vault = Number(vault);
    if (life) s.rem_years = Number(life);
    applyStatus(s);
  }

  function showApp() {
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    if (state.demo) setOffline(false);
    else setOffline(false);
  }

  function showGate(msg) {
    $("app").classList.add("hidden");
    $("gate").classList.remove("hidden");
    if (msg != null) {
      const el = $("gateMsg");
      el.textContent = msg;
    }
  }

  // ---------- 登录 ----------
  async function doAuth(e) {
    if (e && e.preventDefault) e.preventDefault();
    const username = $("fUser").value.trim();
    const password = $("fPass").value;
    const name = ($("fName").value || username).trim();
    let server = ($("fServer").value || state.base || "").trim().replace(/\/$/, "");
    if (server && !/^https?:\/\//i.test(server)) {
      server = "http://" + server;
      $("fServer").value = server;
    }
    if (server) {
      state.base = server;
      localStorage.setItem("wb.base", state.base);
    }
    $("gateMsg").textContent = "";
    $("gateMsg").classList.remove("ok");
    if (!username || !password) {
      $("gateMsg").textContent = "请填写账号与口令";
      return;
    }
    const btn = $("gateSubmit");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "连接中…";
    try {
      const payload =
        state.mode === "register"
          ? await api("/register", { username, password, name })
          : await api("/login", { username, password, name });
      if (!payload || payload.ok === false) {
        throw new Error((payload && payload.error) || "入世失败");
      }
      if (!payload.token) throw new Error("服务器未返回会话令牌");
      state.token = payload.token;
      state.name = payload.name || name;
      state.user = username;
      state.uid = payload.user_id || "";
      localStorage.setItem("wb.token", state.token);
      localStorage.setItem("wb.user", state.user);
      localStorage.setItem("wb.name", state.name);
      if (state.uid) localStorage.setItem("wb.uid", state.uid);
      state.demo = false;
      localStorage.removeItem("wb.demo");
      applyStatus({
        name: state.name,
        realm: payload.realm,
        location: payload.location,
        rem_years: payload.rem_years,
        stones: 0,
      });
      showApp();
      toast("已入世 · " + state.name, "ok");
      try {
        await loadCommands();
        await refreshAll();
      } catch (e2) {
        pushFeed("刷新不完整：" + e2.message, "bad");
      }
      if (payload.newbie_feed) pushFeed(payload.newbie_feed, "sys");
    } catch (err) {
      $("gateMsg").textContent = err.message || "无法进入大世界";
      toast($("gateMsg").textContent, "bad");
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function probeServer() {
    let server = ($("fServer").value || state.base || "").trim().replace(/\/$/, "");
    if (server && !/^https?:\/\//i.test(server)) {
      server = "http://" + server;
      $("fServer").value = server;
    }
    $("gateMsg").classList.remove("ok");
    $("gateMsg").textContent = "正在连接 " + server + " …";
    try {
      const r = await fetch(server + "/health");
      const j = await r.json();
      if (j && j.ok) {
        state.base = server;
        localStorage.setItem("wb.base", state.base);
        $("gateMsg").textContent = "服务器可达：" + server;
        $("gateMsg").classList.add("ok");
      } else {
        $("gateMsg").textContent = "响应异常，请检查地址";
      }
    } catch (e) {
      $("gateMsg").textContent =
        "连不上 " + server + "。请运行 .venv\\Scripts\\python.exe -m server.run，或使用离线演示。";
    }
  }

  function loadDemo() {
    state.demo = true;
    state.token = "demo";
    state.name = "演示道人";
    state.status = {
      name: "演示道人",
      realm: "筑基期",
      location: "青云坊市客栈",
      location_safe: true,
      stones: 1280,
      vault: 4000,
      rem_years: 86,
      sin: 12,
      merit: 40,
      sect: "青云宗",
      rank: "外门弟子",
      exp: "320/900",
    };
    state.here = [
      { name: "柳三娘", realm: "筑基期", sect: "四海散修商会", rank: "掌柜", is_npc: true, personality: "和气生财", attitude_cn: "友善" },
      { name: "石猛", realm: "练气期", sect: "青云宗", rank: "弟子", is_npc: true, personality: "年轻外露", attitude_cn: "中立" },
      { name: "幽冥老祖", realm: "化神期", sect: "九幽天魔宗", rank: "宗主", is_npc: true, personality: "魔道巨擘", attitude_cn: "敌视", blood_marked: true },
    ];
    state.feed = [
      { kind: "sys", text: "离线演示：数据为样例，不会写入服务器。", ts: Date.now() / 1000 },
      { kind: "ai", text: "【天道导演】血煞潮起：坊市一带血气浮动，除凶之议再起。", ts: Date.now() / 1000 - 90 },
    ];
    state.world = {
      evolution: {
        summary_lines: ["天道活跃态势 2 条", "世界弧 2 场", "坊市恐慌 22"],
        director: {
          last_source: "demo",
          active: [
            { type: "blood_tide", title: "血煞潮起", location: "青云坊市客栈", narrative: "血气浮动" },
            { type: "sect_tension", title: "两宗暗涌", narrative: "气氛紧绷" },
          ],
        },
        arcs: [
          { kind: "blood_feud", title: "围剿余波", stage: "escalate", location: "坊市" },
        ],
        faction: {
          modifiers: { active_sieges: [{ sect: "青云宗", target: "幽冥老祖", loc: "坊市" }], n_open_missions: 2 },
          relations: [{ a: "青云宗", b: "九幽天魔宗", score: -55, status: "hostile" }],
        },
        echo: { modifiers: { market_panic: 22, market_reason: "世道不宁", hot_regions: [["黑风绝渊", 48]] } },
        era: { bias_cn: { 机缘预兆: 24, 宗门紧张: 2 } },
        blood: [{ name: "幽冥老祖", location: "青云坊市客栈" }],
        realms_open: [{ name: "落霞古洞", location: "落霞山灵泉" }],
        channel_recent: [{ text: "【宗门围剿】青云宗→幽冥老祖" }],
      },
    };
    localStorage.setItem("wb.demo", "1");
    showApp();
    setOffline(false);
    setText("connText", "离线演示");
    applyStatus(state.status);
    pulseWorld();
    renderPlaces();
    renderBody();
  }

  async function tryRestore() {
    if (localStorage.getItem("wb.demo") === "1") {
      loadDemo();
      return;
    }
    $("fServer").value = state.base;
    if (state.user) $("fUser").value = state.user;
    if (state.name) $("fName").value = state.name;
    if (!state.token) return;
    try {
      const look = await api("/action", { token: state.token, command: "/look" });
      if (!look || look.ok === false) throw new Error("invalid");
      if (look.status) applyStatus(look.status);
      showApp();
      await loadCommands();
      await refreshAll();
    } catch (_) {
      localStorage.removeItem("wb.token");
      state.token = "";
      showGate("会话已失效，请重新登录");
    }
  }

  // ---------- 绑定 ----------
  function on(id, ev, fn) {
    const el = $(id);
    if (!el) return;
    try {
      el.addEventListener(ev, fn);
    } catch (_) {}
  }

  function bind() {
    setTheme(state.theme);
    try {
      if ($("fServer")) $("fServer").value = state.base;
      if (state.user && $("fUser")) $("fUser").value = state.user;
      if (state.name && $("fName")) $("fName").value = state.name;
      if ($("fNameWrap")) $("fNameWrap").classList.add("hidden");
    } catch (_) {}

    document.querySelectorAll("[data-mode]").forEach((t) => {
      t.addEventListener("click", () => {
        state.mode = t.getAttribute("data-mode") === "register" ? "register" : "login";
        document.querySelectorAll("[data-mode]").forEach((x) => {
          x.classList.toggle("active", x === t);
        });
        if ($("fNameWrap")) $("fNameWrap").classList.toggle("hidden", state.mode !== "register");
        if ($("gateSubmit")) {
          $("gateSubmit").textContent = state.mode === "register" ? "创建并入世" : "进入大世界";
        }
      });
    });

    on("gateForm", "submit", doAuth);
    on("btnProbe", "click", probeServer);
    on("btnDemo", "click", loadDemo);
    on("btnTheme", "click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
    on("btnLogout", "click", async () => {
      try {
        if (!state.demo && state.token) await api("/logout", { token: state.token });
      } catch (_) {}
      state.token = "";
      localStorage.removeItem("wb.token");
      showGate("已暂离");
    });
    on("btnHelp", "click", () => sendCmd("/帮助"));
    on("btnRefresh", "click", () => refreshAll());
    on("btnRetry", "click", () => {
      if (state.token && !state.demo) refreshAll();
      else showGate("请先登录");
    });
    on("btnNav", "click", () => document.body.classList.toggle("nav-open"));

    document.querySelectorAll(".rail-btn[data-view]").forEach((b) => {
      b.addEventListener("click", () => setView(b.getAttribute("data-view")));
    });

    $("locQ").addEventListener("input", (e) => {
      state.locFilter = e.target.value;
      renderPlaces();
    });
    $("listQ").addEventListener("input", (e) => {
      state.filter = e.target.value;
      renderBody();
    });

    $("locList").addEventListener("click", (e) => {
      const b = e.target.closest("[data-go]");
      if (!b) return;
      sendCmd("/go " + b.getAttribute("data-go"));
      document.body.classList.remove("nav-open");
    });

    $("body").addEventListener("click", (e) => {
      const person = e.target.closest("[data-person]");
      if (person) {
        const name = person.getAttribute("data-person");
        if (!state.chat.lines.length || state.chat.npc !== name) state.chat.lines = [];
        openChat(name);
        ensureChatVisible();
        if (!state.demo) {
          pushFeed("» /交谈 " + name, "cmd");
          api("/action", { token: state.token, command: "/交谈 " + name })
            .then((data) => {
              handleChatData(data);
              ensureChatVisible();
            })
            .catch((err) => {
              openChat(name);
              chatMsg("", "无法交谈：" + err.message, "sys");
            });
        }
        return;
      }
      const cmd = e.target.closest("[data-cmd]");
      if (cmd) {
        sendCmd(cmd.getAttribute("data-cmd"));
        return;
      }
      const act = e.target.closest("[data-act]");
      if (act) {
        const a = act.getAttribute("data-act");
        if (a.startsWith("view:")) setView(a.slice(5));
        else if (a.startsWith("go:")) sendCmd("/go " + a.slice(3));
        else if (a === "refresh") refreshAll();
      }
    });

    $("cmdForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("cmdInput").value;
      if (state.chat.open && v && !v.startsWith("/")) sendChat(v);
      else sendCmd(v);
    });
    $("cmdInput").addEventListener("input", renderSug);
    $("cmdInput").addEventListener("keydown", (e) => {
      const open = $("suggest") && !$("suggest").classList.contains("hidden") && state.sug.length;
      if (open && e.key === "ArrowDown") {
        e.preventDefault();
        state.sugI = Math.min(state.sug.length - 1, state.sugI + 1);
        paintSug();
      } else if (open && e.key === "ArrowUp") {
        e.preventDefault();
        state.sugI = Math.max(0, state.sugI - 1);
        paintSug();
      } else if (open && e.key === "Enter" && $("cmdInput").value.startsWith("/") && !$("cmdInput").value.trim().includes(" ")) {
        e.preventDefault();
        applySug(state.sugI);
      } else if (e.key === "Escape") {
        hideSug();
      }
    });
    $("suggest").addEventListener("click", (e) => {
      const b = e.target.closest("[data-i]");
      if (b) applySug(Number(b.getAttribute("data-i")));
    });

    $("chatForm") && $("chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("chatInput").value;
      if (!v.trim()) return;
      $("chatInput").value = "";
      sendChat(v);
    });
    // 关闭：UI 立刻关，挂断请求后台发
    on("chatClose", "click", () => closeChat(true));
    on("btnChatHang", "click", () => closeChat(true));
    on("btnChatMem", "click", () => {
      if (!state.demo && state.token) sendCmd("/会话");
      else chatMsg("", "（演示）无会话记忆", "sys");
    });
    const modal = $("chatModal");
    if (modal) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) closeChat(false);
      });
    }
    // 关闭按钮兜底（防止 workbench 绑定失败）
    document.addEventListener("click", (e) => {
      const t = e.target;
      if (!t || !t.closest) return;
      if (t.closest("#chatClose") || t.closest("#btnChatHang")) {
        closeChat(t.closest("#chatClose") || t.closest("#btnChatHang").id === "btnChatHang");
      }
      if (t.closest("[data-close-chat]")) closeChat(false);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        hideSug();
        const m = $("chatModal");
        if (m && !m.classList.contains("hidden")) closeChat(false);
        document.body.classList.remove("nav-open");
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        const target = state.chat.open ? $("chatInput") : $("cmdInput");
        if (target) {
          target.focus();
          if (target === $("cmdInput") && !target.value) {
            target.value = "/";
            renderSug();
          }
        }
      }
    });

    window.addEventListener("offline", () => setOffline(true));
    window.addEventListener("online", () => {
      if (!state.demo) setOffline(false);
    });
  }

  function paintSug() {
    document.querySelectorAll("#suggest .sug").forEach((el, i) => {
      el.classList.toggle("on", i === state.sugI);
    });
  }

  bind();
  tryRestore();
})();
