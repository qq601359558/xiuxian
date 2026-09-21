/**
 * 天道因果录 · 工作台客户端
 * 对接局域网服 JSON API；无服时可离线演示
 */
(function () {
  "use strict";

  const LOCATIONS = [
    { name: "青云坊市客栈", safe: true, tip: "商会 · 安全" },
    { name: "青云宗外门山门", safe: true, tip: "正道山门" },
    { name: "宗门玄元洞府", safe: true, tip: "闭关洞府" },
    { name: "落霞山灵泉", safe: false, tip: "野外灵泉" },
    { name: "万剑仙门峰", safe: true, tip: "剑修仙门" },
    { name: "黑风绝渊", safe: false, tip: "大凶之地" },
    { name: "万星古岛", safe: false, tip: "遗迹残岛" },
    { name: "洗剑池洞天", safe: true, tip: "剑门洞天" },
    { name: "九幽天魔宗坛", safe: true, tip: "魔道总坛" },
  ];

  const $ = (id) => document.getElementById(id);
  const state = {
    base: localStorage.getItem("td_wb_base") || "http://127.0.0.1:8765",
    token: localStorage.getItem("td_wb_token") || "",
    user: localStorage.getItem("td_wb_user") || "",
    name: localStorage.getItem("td_wb_name") || "",
    uid: localStorage.getItem("td_wb_uid") || "",
    theme: localStorage.getItem("td_wb_theme") || "dark",
    gateMode: "login",
    view: "here",
    status: null,
    here: [],
    feed: [],
    world: null,
    commands: [],
    chat: { open: false, npc: "", lines: [] },
    busy: false,
    offline: false,
    demo: false,
    filter: "",
    locFilter: "",
    suggestIdx: 0,
    suggestItems: [],
  };

  // ---------- utils ----------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setTheme(t) {
    state.theme = t === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", state.theme);
    localStorage.setItem("td_wb_theme", state.theme);
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
    const dot = $("serverDot");
    const label = $("serverLabel");
    if (!dot || !label) return;
    dot.classList.remove("on", "off");
    if (state.demo) {
      label.textContent = "离线演示";
      return;
    }
    if (on) {
      dot.classList.add("off");
      label.textContent = "连接中断";
    } else if (state.token) {
      dot.classList.add("on");
      label.textContent = state.base.replace(/^https?:\/\//, "");
    } else {
      label.textContent = "未连接";
    }
  }

  async function api(path, body, opts) {
    let server = (state.base || "").trim().replace(/\/$/, "");
    if (server && !/^https?:\/\//i.test(server)) server = "http://" + server;
    const url = server + path;
    const init = Object.assign({}, opts || {});
    if (body) {
      init.method = "POST";
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    } else {
      init.method = "GET";
    }
    let res;
    try {
      res = await fetch(url, init);
    } catch (e) {
      setOffline(true);
      throw new Error("无法连接服务器 " + server + "（请确认 server.run 已启动）");
    }
    if (!res.ok) {
      let detail = res.statusText || String(res.status);
      try {
        const j = await res.json();
        detail = j.error || j.message || detail;
      } catch (_) {}
      if (res.status === 401) setOffline(false);
      throw new Error(detail);
    }
    setOffline(false);
    return res.json();
  }

  function busy(on) {
    state.busy = !!on;
    const btn = document.querySelector("#composeForm button[type=submit]");
    if (btn) btn.disabled = !!on;
    const r = $("btnRefresh");
    if (r) r.disabled = !!on;
  }

  // ---------- demo data ----------
  function loadDemo() {
    state.demo = true;
    state.token = "demo";
    state.name = "演示道人";
    state.user = "demo";
    state.status = {
      name: "演示道人",
      realm: "筑基期",
      tier: 2,
      sub_tier: 1,
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
      blood_marked: false,
      status: "IDLE",
    };
    state.here = [
      { name: "柳三娘", realm: "筑基期", sect: "四海散修商会", rank: "掌柜", is_npc: true, personality: "和气生财", attitude_cn: "友善", attitude: "friendly", location: "青云坊市客栈" },
      { name: "石猛", realm: "练气期", sect: "青云宗", rank: "弟子", is_npc: true, personality: "年轻外露", attitude_cn: "中立", attitude: "neutral", location: "青云坊市客栈" },
      { name: "幽冥老祖", realm: "化神期", sect: "九幽天魔宗", rank: "宗主", is_npc: true, personality: "魔道巨擘", attitude_cn: "敌视", attitude: "hostile", blood_marked: true, location: "青云坊市客栈" },
    ];
    state.feed = [
      { kind: "sys", text: "已进入离线演示：数据为样例，不会写入服务器。", ts: Date.now() / 1000 },
      { kind: "ai", text: "【天道导演】血煞潮起：青云坊市客栈一带血气浮动，除凶之议再起。", ts: Date.now() / 1000 - 120 },
      { kind: "ok", text: "【世界弧·升级】两宗对峙加剧 @青云宗外门山门", ts: Date.now() / 1000 - 300 },
      { kind: "npc", text: "柳三娘：客官里边请，货真价实。", ts: Date.now() / 1000 - 600 },
    ];
    state.world = {
      evolution: {
        summary_lines: ["天道活跃态势 2 条", "世界弧 2 场", "坊市恐慌 22", "血煞 1 人"],
        director: {
          active: [
            { type: "blood_tide", title: "血煞潮起", location: "青云坊市客栈" },
            { type: "sect_tension", title: "两宗暗涌", location: "" },
          ],
          last_source: "server AI",
        },
        arcs: [
          { kind: "blood_feud", title: "围剿余波", stage: "escalate", location: "青云坊市客栈" },
          { kind: "sect_crisis", title: "宗门紧张", stage: "prophesy", location: "" },
        ],
        faction: {
          modifiers: { active_sieges: [{ sect: "青云宗", target: "幽冥老祖", loc: "青云坊市客栈" }], n_open_missions: 2 },
          relations: [{ a: "青云宗", b: "九幽天魔宗", score: -55, status: "hostile" }],
        },
        echo: {
          modifiers: { market_panic: 22, market_reason: "世道不宁", hot_regions: [["黑风绝渊", 48]] },
        },
        era: { bias_cn: { 机缘预兆: 24, 宗门紧张: 2 } },
        blood: [{ name: "幽冥老祖", location: "青云坊市客栈", realm: "化神期", sin: 479 }],
        realms_open: [{ name: "落霞古洞", location: "落霞山灵泉" }],
        channel_recent: [{ text: "【宗门围剿】青云宗→幽冥老祖" }],
      },
    };
    state.commands = [
      { cmd: "/天道", usage: "/天道", desc: "天道导演态势", category_cn: "天下" },
      { cmd: "/世情", usage: "/世情", desc: "世界演变总览", category_cn: "天下" },
      { cmd: "/坊市", usage: "/坊市", desc: "商会货单", category_cn: "交易" },
      { cmd: "/闭关", usage: "/闭关 [h]", desc: "吐纳修炼", category_cn: "修行" },
    ];
    localStorage.setItem("td_wb_demo", "1");
    showApp();
    renderAll();
    setOffline(false);
    $("serverLabel").textContent = "离线演示";
  }

  // ---------- status / dial ----------
  function applyStatus(st) {
    if (!st) return;
    state.status = Object.assign({}, state.status || {}, st);
    const s = state.status;
    setText("dName", s.name || "—");
    setText("dSect", (s.sect || "散修") + (s.rank ? "·" + s.rank : ""));
    setText("dRealm", s.realm || "—");
    setText("dExp", s.exp || (s.status === "MEDITATING" || s.meditating ? "闭关中" : "行止自由"));
    setText("dLoc", s.location || "—");
    const locSafe = s.location_safe;
    const safeTxt =
      locSafe === false ? "野外凶险" : s.conflict_zone ? "冲突区" : s.newbie_protected ? "新手庇护中" : locSafe === true ? "安全区" : "—";
    setText("dSafe", safeTxt);
    const life = Number(s.rem_years || 0);
    setText("dLife", life ? life.toFixed(0) : "—");
    const lifeEl = $("dLife");
    if (lifeEl) lifeEl.className = "value " + (life && life < 15 ? "bad" : life < 40 ? "" : "ok");
    setText("dVault", "金库 " + (s.vault != null ? s.vault : "—"));
    setText("dStones", s.stones != null ? String(s.stones) : "—");
    setText("dKarma", `${s.sin || 0} / ${s.merit || 0}`);
    const kEl = $("dKarma");
    if (kEl) kEl.className = "value " + (s.sin >= 80 ? "bad" : s.merit >= 50 ? "ok" : "");
    setText("dBlood", s.blood_marked ? "血煞显影" : s.sin >= 80 ? "重业" : "尚清");
  }

  function setText(id, v) {
    const el = $(id);
    if (el) el.textContent = v == null ? "—" : String(v);
  }

  function pulseFromWorld() {
    const ev = (state.world && state.world.evolution) || {};
    const lines = ev.summary_lines || [];
    const d = ev.director || {};
    const n = (d.active || []).length;
    const panic = Number(((ev.echo || {}).modifiers || {}).market_panic || 0);
    let label = "平稳";
    let cls = "ok";
    if (n || panic >= 30) {
      label = n ? `天道 ${n} 势` : `恐慌 ${panic.toFixed(0)}`;
      cls = panic >= 30 ? "bad" : "";
    } else if (lines.length) {
      label = "有讯";
    }
    setText("dWorld", label);
    const el = $("dWorld");
    if (el) el.className = "value " + cls;
    setText("dWorldSub", lines[0] || "天道态势");
  }

  // ---------- locations ----------
  function renderLocations() {
    const box = $("locList");
    if (!box) return;
    const q = (state.locFilter || "").trim();
    const cur = state.status && state.status.location;
    const rows = LOCATIONS.filter((l) => !q || l.name.includes(q) || (l.tip || "").includes(q));
    if (!rows.length) {
      box.innerHTML = `<div class="state-box"><strong>无匹配地点</strong><p>换个关键字试试</p></div>`;
      return;
    }
    box.innerHTML = rows
      .map((l) => {
        const on = l.name === cur;
        return `<button type="button" class="list-item${on ? " active" : ""}" data-go="${esc(l.name)}" aria-current="${on}">
          <span class="t">${esc(l.name)}</span>
          <span class="s">${esc(l.tip || "")}${on ? " · 当前" : ""}</span>
        </button>`;
      })
      .join("");
  }

  // ---------- feed timeline ----------
  function classifyFeed(text) {
    const t = String(text || "");
    if (/^»\s*\//.test(t) || t.startsWith("»")) return "cmd";
    if (/失败|错误|拒绝|不可|中断/.test(t)) return "bad";
    if (/天道|世界弧|宗门围剿|大劫|血煞/.test(t)) return "ai";
    if (/成交|成功|已/.test(t)) return "ok";
    return "npc";
  }

  function pushFeed(text, kind) {
    if (!text) return;
    state.feed.push({ kind: kind || classifyFeed(text), text: String(text), ts: Date.now() / 1000 });
    if (state.feed.length > 200) state.feed = state.feed.slice(-200);
    if (state.view === "feed") renderView();
  }

  function renderFeed() {
    const q = state.filter.trim();
    let rows = state.feed;
    if (q) rows = rows.filter((r) => String(r.text).includes(q));
    if (!rows.length) {
      return emptyState("暂无动态", "同场有人时可直接说话；或 /天道 推演看世界走向。", [
        { label: "去同场", act: "view:here" },
        { label: "世界态势", act: "view:world" },
      ]);
    }
    const items = rows
      .slice()
      .reverse()
      .map((r) => {
        const t = new Date((r.ts || Date.now() / 1000) * 1000);
        const hh = t.toTimeString().slice(0, 5);
        const cls = r.kind || classifyFeed(r.text);
        const mark = cls === "cmd" ? "/" : cls === "ai" ? "天" : cls === "bad" ? "!" : cls === "ok" ? "成" : "·";
        return `<article class="tl-item">
          <div class="tl-dot ${esc(cls)}">${mark}</div>
          <div class="tl-body"><div class="text${cls === "cmd" ? " cmd" : ""}">${esc(r.text)}</div></div>
          <div class="tl-meta">${hh}</div>
        </article>`;
      })
      .join("");
    return `<div class="timeline">${items}</div>`;
  }

  // ---------- here ----------
  function renderHere() {
    const q = state.filter.trim();
    let rows = state.here || [];
    if (q) rows = rows.filter((r) => (r.name || "").includes(q) || (r.sect || "").includes(q) || (r.realm || "").includes(q));
    if (!rows.length) {
      return emptyState(
        state.here && state.here.length ? "无匹配同道" : "此地暂无其他修士",
        "可迁跃到坊市或宗门山门；也可用下方敕令 /做 描述行动。",
        [{ label: "迁跃坊市", act: "go:青云坊市客栈" }, { label: "看世界", act: "view:world" }]
      );
    }
    return `<div class="people-list">` +
      rows
        .map((r) => {
          const blood = r.blood_marked;
          const att = r.attitude_cn || (r.is_npc ? "中立" : "—");
          const active = state.chat.open && state.chat.npc === r.name;
          return `<button type="button" class="person-row${active ? " active" : ""}" data-person="${esc(r.name)}">
            <div class="avatar ${blood ? "blood" : r.is_npc ? "npc" : ""}">${esc((r.name || "?").slice(0, 1))}</div>
            <div class="person-info">
              <div class="name">${esc(r.name)}</div>
              <div class="meta">${esc(r.realm || "")} · ${esc(r.sect || "散修")}${r.rank ? "·" + esc(r.rank) : ""} · 对你：${esc(att)}</div>
              <div class="tag-row">
                ${r.is_npc ? '<span class="tag">NPC</span>' : '<span class="tag brand">玩家</span>'}
                ${blood ? '<span class="tag blood">血煞</span>' : ""}
                ${r.personality ? `<span class="tag">${esc(r.personality)}</span>` : ""}
              </div>
            </div>
            <div class="person-actions">
              <span class="btn sm primary">交谈</span>
            </div>
          </button>`;
        })
        .join("") +
      `</div>`;
  }

  // ---------- world ----------
  function renderWorld() {
    const ev = (state.world && state.world.evolution) || {};
    const d = ev.director || {};
    const fm = ((ev.faction || {}).modifiers) || {};
    const rels = ((ev.faction || {}).relations) || [];
    const em = ((ev.echo || {}).modifiers) || {};
    const bias = ((ev.era || {}).bias_cn) || {};
    const arcs = ev.arcs || [];
    const blood = ev.blood || [];
    const realms = ev.realms_open || [];
    const news = ev.channel_recent || [];

    if (state.demo === false && !state.world) {
      return emptyState("世界态势未加载", "确认服务器已启动，然后点刷新。", [{ label: "刷新", act: "refresh" }]);
    }

    const summary = (ev.summary_lines || []).join(" · ") || "世间暂稳";
    const panic = Number(em.market_panic || 0);
    const sieges = fm.active_sieges || [];
    const hostile = rels.filter((r) => r.status === "hostile");

    return `
    <div class="section-block">
      <div class="section-head"><h3>此刻结论</h3><span class="desc">${esc(summary)}</span></div>
      <div class="data-rows">
        <div class="data-row"><span class="k">天道来源</span><span class="v">${esc(d.last_source || "—")}</span></div>
        <div class="data-row"><span class="k">活跃指令</span><span class="v">${(d.active || []).length}</span></div>
        <div class="data-row"><span class="k">世界弧</span><span class="v">${arcs.length}</span></div>
        <div class="data-row"><span class="k">坊市恐慌</span><span class="v ${panic >= 30 ? "bad" : panic < 8 ? "ok" : ""}">${panic.toFixed(0)}</span></div>
      </div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>天道导演</h3><span class="desc">AI 提案 · 规则落账</span></div>
      ${
        (d.active || []).length
          ? `<div class="data-rows">${(d.active || [])
              .map(
                (a) => `<div class="data-row"><span class="k">[${esc(a.type)}] ${esc(a.title)}${a.location ? " @" + esc(a.location) : ""}</span><span class="v">${esc((a.narrative || "").slice(0, 28))}</span></div>`
              )
              .join("")}</div>`
          : `<div class="state-box" style="padding:12px 0;text-align:left"><p style="margin:0">暂无活跃指令。可在下方输入 <kbd>/天道 推演</kbd>。</p></div>`
      }
      <div class="action-row">
        <button type="button" class="btn sm" data-cmd="/天道">打开天道</button>
        <button type="button" class="btn sm primary" data-cmd="/天道 推演">推演一轮</button>
      </div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>世界弧</h3><span class="desc">预兆 → 升级 → 决算</span></div>
      ${
        arcs.length
          ? `<div class="data-rows">${arcs
              .map(
                (a) => `<div class="data-row"><span class="k">[${esc(a.stage)}] ${esc(a.title)}${a.location ? " @" + esc(a.location) : ""}</span><span class="v">${esc(a.kind)}</span></div>`
              )
              .join("")}</div>`
          : `<div class="state-box" style="padding:8px 0;text-align:left"><p style="margin:0">暂无进行中的世界弧。</p></div>`
      }
      <div class="action-row"><button type="button" class="btn sm" data-cmd="/世界弧">弧详情</button></div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>势力</h3><span class="desc">宗门关系与围剿</span></div>
      <div class="data-rows">
        ${
          hostile.length
            ? hostile
                .map((r) => `<div class="data-row"><span class="k">敌对 ${esc(r.a)} × ${esc(r.b)}</span><span class="v bad">${esc(String(r.score != null ? r.score : ""))}</span></div>`)
                .join("")
            : `<div class="data-row"><span class="k">敌对格局</span><span class="v ok">暂无显性敌对</span></div>`
        }
        ${
          sieges.length
            ? sieges
                .slice(0, 3)
                .map((s) => `<div class="data-row"><span class="k">围剿 ${esc(s.sect)} → ${esc(s.target)}</span><span class="v">${esc(s.loc || "")}</span></div>`)
                .join("")
            : `<div class="data-row"><span class="k">宗门围剿</span><span class="v">无</span></div>`
        }
        <div class="data-row"><span class="k">开放宗门令</span><span class="v">${fm.n_open_missions || 0}</span></div>
      </div>
      <div class="action-row">
        <button type="button" class="btn sm" data-cmd="/势力">势力总览</button>
        <button type="button" class="btn sm" data-cmd="/宗门令">宗门令</button>
      </div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>望气</h3><span class="desc">凶地与坊市</span></div>
      <div class="data-rows">
        <div class="data-row"><span class="k">坊市</span><span class="v ${panic >= 30 ? "bad" : ""}">${panic < 8 ? "平稳" : esc(em.market_reason || "人心浮动")}</span></div>
        ${
          (em.hot_regions || []).length
            ? (em.hot_regions || [])
                .map((h) => `<div class="data-row"><span class="k">凶地 ${esc(h[0])}</span><span class="v bad">${Number(h[1]).toFixed(0)}</span></div>`)
                .join("")
            : `<div class="data-row"><span class="k">凶地</span><span class="v ok">无显著热点</span></div>`
        }
        ${
          blood.length
            ? blood
                .slice(0, 4)
                .map((b) => `<div class="data-row"><span class="k">血煞 ${esc(b.name)}</span><span class="v bad">${esc(b.location || "")}</span></div>`)
                .join("")
            : ""
        }
      </div>
      <div class="action-row"><button type="button" class="btn sm" data-cmd="/望气">望气详报</button></div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>史笔与秘境</h3><span class="desc">纪元回流 / 开启中</span></div>
      <div class="data-rows">
        ${
          Object.keys(bias).length
            ? Object.keys(bias)
                .sort((a, b) => Number(bias[b]) - Number(bias[a]))
                .slice(0, 3)
                .map((k) => `<div class="data-row"><span class="k">${esc(k)}</span><span class="v">${Number(bias[k]).toFixed(1)}</span></div>`)
                .join("")
            : `<div class="data-row"><span class="k">史笔权重</span><span class="v">传说未积</span></div>`
        }
        ${
          realms.length
            ? realms
                .map((r) => `<div class="data-row"><span class="k">秘境 ${esc(r.name || r)}</span><span class="v ok">${esc(r.location || "已开启")}</span></div>`)
                .join("")
            : `<div class="data-row"><span class="k">秘境</span><span class="v">暂无开启</span></div>`
        }
      </div>
      <div class="action-row">
        <button type="button" class="btn sm" data-cmd="/纪元回流">回流</button>
        <button type="button" class="btn sm" data-cmd="/秘境">天机榜</button>
      </div>
    </div>

    <div class="section-block">
      <div class="section-head"><h3>近闻</h3><span class="desc">新闻摘要 · 详情 /频道</span></div>
      ${
        news.length
          ? `<div class="data-rows">${news
              .slice(0, 5)
              .map((n) => `<div class="data-row"><span class="k" style="white-space:normal">${esc(n.text)}</span></div>`)
              .join("")}</div>`
          : `<div class="state-box" style="padding:8px 0;text-align:left"><p style="margin:0">风平浪静。</p></div>`
      }
      <div class="action-row"><button type="button" class="btn sm" data-cmd="/频道">打开频道</button><button type="button" class="btn sm" data-cmd="/世情">世界演变全文</button></div>
    </div>`;
  }

  function emptyState(title, desc, actions) {
    const acts = (actions || [])
      .map((a) => `<button type="button" class="btn sm" data-empty-act="${esc(a.act)}">${esc(a.label)}</button>`)
      .join(" ");
    return `<div class="state-box"><strong>${esc(title)}</strong><p>${esc(desc)}</p><div class="action-row" style="justify-content:center">${acts}</div></div>`;
  }

  // ---------- chat detail ----------
  function openChat(npcName) {
    state.chat.open = true;
    state.chat.npc = npcName || "";
    state.chat.lines = state.chat.lines.filter((l) => true);
    $("detailTitle").textContent = "交谈 · " + (npcName || "");
    $("composeMode").textContent = "言语";
    $("composeTarget").textContent = "交谈对象：" + (npcName || "");
    document.body.classList.add("side-open");
    renderDetail();
    if (state.view === "here") renderView();
  }

  function closeChat() {
    state.chat.open = false;
    state.chat.npc = "";
    $("detailTitle").textContent = "详情";
    $("composeMode").textContent = "敕令";
    $("composeTarget").textContent = "未锁定交谈";
    renderDetail();
    if (state.view === "here") renderView();
    document.body.classList.remove("side-open");
  }

  function chatAppend(who, text, cls) {
    state.chat.lines.push({ who, text, cls: cls || "npc" });
    if (state.chat.lines.length > 80) state.chat.lines = state.chat.lines.slice(-80);
    renderDetail(true);
  }

  function renderDetail(scroll) {
    const body = $("detailBody");
    if (!body) return;
    if (!state.chat.open) {
      body.innerHTML = `<div class="detail-empty"><div><strong style="display:block;color:var(--ink-2);margin-bottom:6px">选一位同道</strong>点击同场列表开聊窗；买卖、打听由规则结算。</div></div>`;
      return;
    }
    const lines = state.chat.lines;
    const html =
      (lines.length
        ? lines
            .map((l) => {
              if (l.cls === "sys") return `<div class="msg sys">${esc(l.text)}</div>`;
              return `<div class="msg ${esc(l.cls)}"><span class="who">${esc(l.who || "")}</span>${esc(l.text)}</div>`;
            })
            .join("")
        : `<div class="msg sys">会话已开 · 直接在下方说话</div>`) +
      `<div class="chat-log-end"></div>`;
    body.innerHTML = `<div class="chat-log" id="chatLog">${html}</div>
      <div class="action-row">
        <button type="button" class="btn sm" data-cmd="/会话">会话记忆</button>
        <button type="button" class="btn sm" data-cmd="/挂断">挂断</button>
      </div>`;
    if (scroll) {
      const log = $("chatLog");
      if (log) log.scrollTop = log.scrollHeight;
    }
  }

  // ---------- views ----------
  function setView(v) {
    state.view = v;
    document.querySelectorAll("[data-view]").forEach((t) => {
      const on = t.getAttribute("data-view") === v;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    const title = { here: "同场修士", feed: "动态", world: "世界演变" }[v] || "工作台";
    setText("viewTitle", title);
    const search = $("listSearch");
    if (search) search.placeholder = v === "here" ? "筛选同场…" : v === "feed" ? "筛选动态…" : "筛选世界…";
    renderView();
  }

  function renderView() {
    const pane = $("paneBody");
    if (!pane) return;
    if (state.view === "here") pane.innerHTML = renderHere();
    else if (state.view === "feed") pane.innerHTML = renderFeed();
    else pane.innerHTML = renderWorld();
  }

  function renderAll() {
    applyStatus(state.status);
    pulseFromWorld();
    renderLocations();
    renderView();
    renderDetail();
  }

  function loadingPane() {
    const pane = $("paneBody");
    if (!pane) return;
    pane.innerHTML = `<div class="skeleton" style="width:70%"></div>
      <div class="skeleton" style="width:90%"></div>
      <div class="skeleton" style="width:55%"></div>
      <div class="skeleton" style="width:80%"></div>`;
  }

  // ---------- command suggest ----------
  function fuzzyCmd(q) {
    const query = (q || "").trim().toLowerCase();
    if (!query.startsWith("/")) return [];
    const all = state.commands || [];
    if (query === "/") return all.slice(0, 10).map((e) => Object.assign({}, e, { score: 0 }));
    const scored = [];
    for (const e of all) {
      const cmd = String(e.cmd || "").toLowerCase();
      const desc = String(e.desc || "").toLowerCase();
      const core = query.replace(/^\//, "");
      let s = 0;
      if (cmd === query) s = 100;
      else if (cmd.startsWith(query)) s = 80;
      else if (core && cmd.indexOf(core) >= 0) s = 55;
      else if (core && desc.indexOf(core) >= 0) s = 40;
      if (s > 0) scored.push(Object.assign({}, e, { score: s }));
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, 10);
  }

  function renderSuggest() {
    const el = $("suggest");
    const inp = $("composeInput");
    if (!el || !inp) return;
    const v = inp.value;
    if (!v || v[0] !== "/") {
      el.classList.add("hidden");
      el.innerHTML = "";
      state.suggestItems = [];
      return;
    }
    state.suggestItems = fuzzyCmd(v);
    state.suggestIdx = 0;
    if (!state.suggestItems.length) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }
    el.innerHTML =
      state.suggestItems
        .map(
          (it, i) =>
            `<button type="button" class="suggest-item${i === 0 ? " active" : ""}" data-sug="${i}" role="option">
              <div class="cmd">${esc(it.cmd)}<small>${esc(it.usage || "")}</small></div>
              <div class="desc">${esc(it.desc || "")}</div>
            </button>`
        )
        .join("");
    el.classList.remove("hidden");
  }

  function applySuggest(i) {
    const it = state.suggestItems[i];
    if (!it) return;
    const inp = $("composeInput");
    const usage = String(it.usage || it.cmd);
    if (/[<>|…]/.test(usage)) inp.value = usage;
    else inp.value = it.cmd + " ";
    $("suggest").classList.add("hidden");
    inp.focus();
  }

  async function loadCommands() {
    if (state.demo) return;
    try {
      const data = await api("/commands");
      state.commands = data.commands || [];
    } catch (_) {}
  }

  // ---------- actions ----------
  async function sendRaw(text) {
    const c = (text || "").trim();
    if (!c) return;
    if (state.busy) {
      toast("天道正在裁决，请稍候…");
      return;
    }
    busy(true);
    try {
      let data;
      if (state.demo) {
        data = demoHandle(c);
      } else if (state.chat.open && !c.startsWith("/")) {
        pushFeed(c, "cmd");
        chatAppend("你", c, "me");
        data = await api("/chat", { token: state.token, text: c, to: state.chat.npc || undefined });
      } else {
        pushFeed("» " + c, "cmd");
        data = await api("/action", { token: state.token, command: c });
      }
      handleResult(data);
    } catch (e) {
      pushFeed("失败：" + e.message, "bad");
      toast(e.message, "bad");
      if (state.chat.open) chatAppend("", "失败：" + e.message, "sys");
    } finally {
      busy(false);
      $("composeInput").value = "";
      $("suggest").classList.add("hidden");
    }
  }

  function demoHandle(c) {
    if (c.startsWith("/")) {
      const text = `【演示】已记录敕令 ${c}。接服务器后可执行真实逻辑。`;
      return { ok: true, text };
    }
    return {
      ok: true,
      chat_open: true,
      npc: state.chat.npc || "对方",
      text: `（演示）对方想了想：「${c.slice(0, 20)}」…此事须接服务器方能落账。`,
    };
  }

  function handleResult(data) {
    if (!data) return;
    const text = data.text || data.error || "";
    if (data.status) applyStatus(data.status);

    if (data.chat_open) {
      if (data.npc) openChat(data.npc);
      if (text) {
        String(text)
          .split("\n")
          .filter(Boolean)
          .forEach((ln) => {
            if (/会话开始|可开口|挂断|作别|【同场】|会话记忆|上次交谈|直接打字/.test(ln)) {
              chatAppend("", ln, "sys");
            } else {
              chatAppend(data.npc || "对方", ln.replace(/^「|」$/g, ""), "npc");
            }
          });
        pushFeed(text, "npc");
      }
      if (state.view === "here") renderView();
      return;
    }
    if (data.chat_ended) {
      chatAppend("", text || "会话已结束。", "sys");
      pushFeed(text, "sys");
      return;
    }
    if (data.ok === false && state.chat.open) {
      chatAppend("", text || "操作未完成", "sys");
      pushFeed(text || "操作未完成", "bad");
      return;
    }
    if (text) pushFeed(text, data.ok === false ? "bad" : undefined);
    if (state.view !== "feed") renderView();
  }

  async function refreshAll() {
    if (state.demo) {
      pulseFromWorld();
      renderAll();
      return;
    }
    if (!state.token) return;
    loadingPane();
    const errors = [];
    let look = null;
    let here = null;
    let world = null;
    try {
      look = await api("/action", { token: state.token, command: "/look" });
    } catch (e) {
      errors.push("观照：" + e.message);
    }
    try {
      here = await api("/action", { token: state.token, command: "/here" });
    } catch (e) {
      errors.push("同场：" + e.message);
    }
    try {
      world = await api("/world/director");
    } catch (e) {
      errors.push("世界：" + e.message);
    }
    if (look && look.status) applyStatus(look.status);
    else if (look && look.text) parseLook(look.text);
    if (here && Array.isArray(here.here)) state.here = here.here;
    if (world && world.ok !== false) state.world = world;
    pulseFromWorld();
    renderAll();
    if (errors.length && (!look || !here)) {
      pushFeed("部分数据刷新失败：" + errors.join("；"), "bad");
      toast("刷新失败：" + errors[0], "bad");
    }
  }

  function parseLook(text) {
    const s = state.status || {};
    const name = (text.match(/【([^】]+)】/) || [])[1];
    const loc = (text.match(/位置：([^（\n]+)/) || [])[1];
    const stones = (text.match(/随身灵石\s*(\d+)/) || [])[1];
    const vault = (text.match(/金库\s*(\d+)/) || [])[1];
    const life = (text.match(/寿元约([\d.]+)/) || [])[1];
    const realm = (text.match(/】\s*([^\s|]+)/) || [])[1];
    if (name) s.name = name;
    if (realm) s.realm = realm;
    if (loc) s.location = loc.trim();
    if (stones) s.stones = Number(stones);
    if (vault) s.vault = Number(vault);
    if (life) s.rem_years = Number(life);
    if (/安全/.test(text) && !/凶险|野外/.test(text.split("\n").find((l) => l.includes("位置：")) || "")) {
      s.location_safe = true;
    } else if (/凶险|大凶|野外/.test(text)) {
      s.location_safe = false;
    }
    applyStatus(s);
  }

  function showApp() {
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    if (state.demo) {
      $("serverLabel").textContent = "离线演示";
    } else {
      setOffline(false);
      const label = $("serverLabel");
      if (label) label.textContent = (state.base || "").replace(/^https?:\/\//, "");
      const dot = $("serverDot");
      if (dot) {
        dot.classList.remove("off");
        dot.classList.add("on");
      }
    }
  }

  function showGate(msg) {
    $("app").classList.add("hidden");
    $("gate").classList.remove("hidden");
    if (msg != null) $("gateMsg").textContent = msg;
  }

  async function doAuth(e) {
    if (e && e.preventDefault) e.preventDefault();
    const username = $("gUser").value.trim();
    const password = $("gPass").value;
    const name = ($("gName").value || username).trim();
    let server = ($("gServer").value || state.base || "").trim().replace(/\/$/, "");
    if (server && !/^https?:\/\//i.test(server)) {
      server = "http://" + server;
      $("gServer").value = server;
    }
    if (server) {
      state.base = server;
      localStorage.setItem("td_wb_base", state.base);
    }
    $("gateMsg").textContent = "";
    if (!username || !password) {
      $("gateMsg").textContent = "请填写账号与口令";
      return;
    }
    const btn = $("gateSubmit");
    const oldLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = "连接中…";
    try {
      let payload;
      if (state.gateMode === "register") {
        payload = await api("/register", { username, password, name });
      } else {
        payload = await api("/login", { username, password, name });
      }
      if (!payload || payload.ok === false) {
        throw new Error((payload && payload.error) || "入世失败");
      }
      if (!payload.token) throw new Error("服务器未返回会话令牌");
      state.token = payload.token;
      state.name = payload.name || name;
      state.user = username;
      state.uid = payload.user_id || "";
      if (payload.realm) {
        applyStatus({
          name: state.name,
          realm: payload.realm,
          location: payload.location,
          rem_years: payload.rem_years,
          stones: 0,
        });
      }
      localStorage.setItem("td_wb_token", state.token);
      localStorage.setItem("td_wb_user", state.user);
      localStorage.setItem("td_wb_name", state.name);
      if (state.uid) localStorage.setItem("td_wb_uid", state.uid);
      state.demo = false;
      localStorage.removeItem("td_wb_demo");
      showApp();
      toast("已入世 · " + state.name, "ok");
      // 刷新失败不阻断已登录
      try {
        await loadCommands();
        await refreshAll();
      } catch (e2) {
        pushFeed("界面刷新不完整：" + (e2 && e2.message), "bad");
      }
      if (payload.newbie_feed) pushFeed(payload.newbie_feed, "sys");
    } catch (err) {
      $("gateMsg").textContent = err.message || "无法进入大世界";
      toast($("gateMsg").textContent, "bad");
    } finally {
      btn.disabled = false;
      btn.textContent = oldLabel;
    }
  }

  async function probeServer() {
    let server = ($("gServer").value || state.base || "").trim().replace(/\/$/, "");
    if (server && !/^https?:\/\//i.test(server)) server = "http://" + server;
    $("gateMsg").textContent = "正在连接 " + server + " …";
    try {
      const r = await fetch(server + "/health");
      const j = await r.json();
      if (j && j.ok) {
        $("gateMsg").textContent = "服务器可达：" + server + "（可登录）";
        state.base = server;
        localStorage.setItem("td_wb_base", state.base);
      } else {
        $("gateMsg").textContent = "服务器无响应格式，请检查地址";
      }
    } catch (e) {
      $("gateMsg").textContent =
        "连不上 " + server + "。请先运行 .venv\\Scripts\\python.exe -m server.run，或点「离线演示」。";
    }
  }

  async function tryRestore() {
    if (localStorage.getItem("td_wb_demo") === "1") {
      loadDemo();
      return;
    }
    $("gServer").value = state.base;
    if (state.user) $("gUser").value = state.user;
    if (state.name) $("gName").value = state.name;
    if (!state.token) return;
    try {
      const look = await api("/action", { token: state.token, command: "/look" });
      if (!look || look.ok === false) throw new Error((look && look.error) || "token invalid");
      if (look.status) applyStatus(look.status);
      state.demo = false;
      showApp();
      await loadCommands();
      await refreshAll();
    } catch (_) {
      localStorage.removeItem("td_wb_token");
      state.token = "";
      showGate("会话已失效，请重新登录");
    }
  }

  // ---------- events ----------
  function bind() {
    setTheme(state.theme);
    $("gServer").value = state.base;
    if (state.user) $("gUser").value = state.user;
    if (state.name) $("gName").value = state.name;

    document.querySelectorAll("[data-gate-tab]").forEach((t) => {
      t.addEventListener("click", () => {
        state.gateMode = t.getAttribute("data-gate-tab");
        document.querySelectorAll("[data-gate-tab]").forEach((x) => {
          const on = x === t;
          x.classList.toggle("active", on);
          x.setAttribute("aria-selected", on ? "true" : "false");
        });
        $("fieldName").classList.toggle("hidden", state.gateMode !== "register");
        $("gateSubmit").textContent = state.gateMode === "register" ? "创建并入世" : "进入大世界";
      });
    });
    $("fieldName").classList.add("hidden");
    $("gateForm").addEventListener("submit", doAuth);
    $("btnDemo").addEventListener("click", loadDemo);
    if ($("btnProbe")) $("btnProbe").addEventListener("click", probeServer);

    $("btnTheme").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
    $("btnRetry").addEventListener("click", () => {
      if (state.token && !state.demo) refreshAll();
      else showGate();
    });
    $("btnRefresh").addEventListener("click", () => refreshAll());
    $("btnCloseSide").addEventListener("click", closeChat);
    $("btnSide").addEventListener("click", () => document.body.classList.toggle("side-open"));
    $("btnNav").addEventListener("click", () => document.body.classList.toggle("nav-open"));
    $("btnHelp").addEventListener("click", () => sendRaw("/帮助"));
    $("btnLogout").addEventListener("click", async () => {
      try {
        if (!state.demo && state.token) await api("/logout", { token: state.token });
      } catch (_) {}
      state.token = "";
      localStorage.removeItem("td_wb_token");
      showGate("已暂离");
    });

    document.querySelectorAll("[data-view]").forEach((t) => {
      t.addEventListener("click", () => setView(t.getAttribute("data-view")));
    });

    $("locSearch").addEventListener("input", (e) => {
      state.locFilter = e.target.value;
      renderLocations();
    });
    $("listSearch").addEventListener("input", (e) => {
      state.filter = e.target.value;
      renderView();
    });

    $("locList").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-go]");
      if (!btn) return;
      const dest = btn.getAttribute("data-go");
      sendRaw("/go " + dest);
      document.body.classList.remove("nav-open");
    });

    $("paneBody").addEventListener("click", (e) => {
      const person = e.target.closest("[data-person]");
      if (person) {
        const name = person.getAttribute("data-person");
        openChat(name);
        if (!state.demo) {
          pushFeed("» /交谈 " + name, "cmd");
          api("/action", { token: state.token, command: "/交谈 " + name })
            .then(handleResult)
            .catch((err) => {
              chatAppend("", "无法交谈：" + err.message, "sys");
            });
        } else {
          chatAppend("", "（演示）已锁定交谈对象 " + name, "sys");
        }
        return;
      }
      const cmd = e.target.closest("[data-cmd]");
      if (cmd) {
        sendRaw(cmd.getAttribute("data-cmd"));
        return;
      }
      const act = e.target.closest("[data-empty-act]");
      if (act) {
        const a = act.getAttribute("data-empty-act");
        if (a.startsWith("view:")) setView(a.slice(5));
        else if (a.startsWith("go:")) sendRaw("/go " + a.slice(3));
        else if (a === "refresh") refreshAll();
      }
    });

    $("detailBody").addEventListener("click", (e) => {
      const cmd = e.target.closest("[data-cmd]");
      if (cmd) sendRaw(cmd.getAttribute("data-cmd"));
    });

    const inp = $("composeInput");
    const form = $("composeForm");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = inp.value;
      if (state.chat.open && !String(v).startsWith("/")) {
        chatAppend("你", v, "me");
      }
      sendRaw(v);
    });
    inp.addEventListener("input", renderSuggest);
    inp.addEventListener("keydown", (e) => {
      const box = $("suggest");
      const open = box && !box.classList.contains("hidden") && state.suggestItems.length;
      if (open && e.key === "ArrowDown") {
        e.preventDefault();
        state.suggestIdx = Math.min(state.suggestItems.length - 1, state.suggestIdx + 1);
        renderSuggestIdx();
      } else if (open && e.key === "ArrowUp") {
        e.preventDefault();
        state.suggestIdx = Math.max(0, state.suggestIdx - 1);
        renderSuggestIdx();
      } else if (open && e.key === "Enter" && inp.value.startsWith("/") && !/\s/.test(inp.value.trim())) {
        e.preventDefault();
        applySuggest(state.suggestIdx);
      } else if (e.key === "Escape") {
        box.classList.add("hidden");
      } else if (open && e.key === "Tab") {
        e.preventDefault();
        applySuggest(state.suggestIdx);
      }
    });
    $("suggest").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sug]");
      if (b) applySuggest(Number(b.getAttribute("data-sug")));
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $("suggest").classList.add("hidden");
        document.body.classList.remove("nav-open", "side-open");
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        inp.focus();
        if (!inp.value) inp.value = "/";
        renderSuggest();
      }
    });

    window.addEventListener("offline", () => setOffline(true));
    window.addEventListener("online", () => {
      if (!state.demo) setOffline(false);
    });
  }

  function renderSuggestIdx() {
    document.querySelectorAll("#suggest .suggest-item").forEach((el, i) => {
      el.classList.toggle("active", i === state.suggestIdx);
    });
  }

  bind();
  tryRestore();
})();
