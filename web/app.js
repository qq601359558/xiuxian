/* 天道因果录 · 网页客户端 — 点击为主，指令栏默认收起 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    base: localStorage.getItem("td_base") || ((location.protocol === "http:" || location.protocol === "https:") && location.hostname !== "localhost" && location.hostname !== "127.0.0.1" ? location.origin : "http://127.0.0.1:8765"),
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
<<<<<<< HEAD
    chatNpc: "",
=======
    lastTrigger: null,
    lastFocus: null,
>>>>>>> fb383c1fb995e8dabd8bd77ac6775956a22274bf
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

  // ---------- 斜杠指令补全 ----------
  const cmdSuggest = {
    items: [],
    index: 0,
    cache: null,
  };

  function cmdListEl() {
    return $("cmdSuggest");
  }

  function hideSuggest() {
    const el = cmdListEl();
    if (el) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
    cmdSuggest.items = [];
    cmdSuggest.index = 0;
  }

  async function loadCommandCatalog(force) {
    if (cmdSuggest.cache && !force) return cmdSuggest.cache;
    try {
      const base = (state.base || "").replace(/\/$/, "");
      const res = await fetch(base + "/commands");
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      cmdSuggest.cache = data.commands || [];
    } catch (e) {
      // 本地兜底：与 core/command_catalog 常用子集同步
      cmdSuggest.cache = [
        { cmd: "/look", usage: "/look", desc: "观照自身", category_cn: "观照与出入" },
        { cmd: "/世情", usage: "/世情 [简]", desc: "世界演变总览", category_cn: "天下与演变" },
        { cmd: "/天道", usage: "/天道 [推演]", desc: "天道导演态势", category_cn: "天下与演变" },
        { cmd: "/势力", usage: "/势力", desc: "宗门关系/令/围剿", category_cn: "宗门势力" },
        { cmd: "/望气", usage: "/望气 [己]", desc: "凶地与坊市恐慌", category_cn: "天下与演变" },
        { cmd: "/世界弧", usage: "/世界弧", desc: "世界弧状态", category_cn: "天下与演变" },
        { cmd: "/做", usage: "/做 <言行>", desc: "自由言行", category_cn: "人际因果" },
        { cmd: "/帮助", usage: "/帮助 [关键字]", desc: "指令目录", category_cn: "观照与出入" },
      ];
    }
    return cmdSuggest.cache;
  }

  function localFuzzy(q) {
    const all = cmdSuggest.cache || [];
    const query = (q || "").trim().toLowerCase();
    if (!query.startsWith("/")) return [];
    if (query === "/") {
      return all.slice(0, 14).map((e) => ({ ...e, score: 0 }));
    }
    const scored = [];
    for (const e of all) {
      const cmd = String(e.cmd || "").toLowerCase();
      const aliases = (e.aliases || []).map((a) => String(a).toLowerCase());
      const desc = String(e.desc || "").toLowerCase();
      const usage = String(e.usage || "").toLowerCase();
      const core = query.replace(/^\//, "");
      let s = 0;
      if (cmd === query) s = 100;
      else if (cmd.startsWith(query)) s = 80 - (cmd.length - query.length);
      else if (aliases.some((a) => a === query || a.startsWith(query))) s = 70;
      else if (core && cmd.indexOf(core) >= 0) s = 55;
      else if (core && aliases.some((a) => a.indexOf(core) >= 0)) s = 50;
      else if (core && desc.indexOf(core) >= 0) s = 40;
      else if (core && usage.indexOf(core) >= 0) s = 35;
      if (s > 0) scored.push({ ...e, score: s });
    }
    scored.sort((a, b) => b.score - a.score || String(a.cmd).localeCompare(String(b.cmd)));
    return scored.slice(0, 12);
  }

  function renderSuggest(items) {
    const el = cmdListEl();
    if (!el) return;
    cmdSuggest.items = items || [];
    if (!cmdSuggest.items.length) {
      hideSuggest();
      return;
    }
    const hint =
      '<div class="hint">↑↓ 选择 · Enter 填入 · Esc 关闭 · 共 ' +
      cmdSuggest.items.length +
      " 条</div>";
    el.innerHTML =
      hint +
      cmdSuggest.items
        .map(function (it, i) {
          return (
            '<div class="cmd-item' +
            (i === cmdSuggest.index ? " active" : "") +
            '" data-i="' +
            i +
            '" role="option">' +
            '<div class="c">' +
            esc(it.cmd) +
            (it.usage && it.usage !== it.cmd
              ? '<span class="usage">' + esc(it.usage) + "</span>"
              : "") +
            "</div>" +
            '<div class="d">' +
            esc(it.desc || "") +
            "</div>" +
            (it.category_cn ? '<div class="cat">' + esc(it.category_cn) + "</div>" : "") +
            "</div>"
          );
        })
        .join("");
    el.classList.remove("hidden");
    el.querySelectorAll(".cmd-item").forEach(function (node) {
      node.addEventListener("click", function () {
        const i = Number(node.getAttribute("data-i"));
        applySuggest(i);
      });
      node.addEventListener("mouseenter", function () {
        cmdSuggest.index = Number(node.getAttribute("data-i"));
        el.querySelectorAll(".cmd-item").forEach(function (n, j) {
          n.classList.toggle("active", j === cmdSuggest.index);
        });
      });
    });
  }

  function applySuggest(i) {
    const items = cmdSuggest.items;
    if (!items || !items[i]) return;
    const cmd = items[i].cmd || "";
    const usage = String(items[i].usage || cmd);
    const inp = $("cmdInput");
    if (!inp) return;
    // 若 usage 含参数占位，填入 usage；否则填 cmd + 空格方便续写
    if (usage && /[<>|]/.test(usage)) {
      inp.value = usage;
    } else {
      inp.value = cmd + " ";
    }
    hideSuggest();
    inp.focus();
  }

  async function updateSuggest() {
    const inp = $("cmdInput");
    if (!inp) return;
    const v = inp.value;
    if (!v || v[0] !== "/") {
      hideSuggest();
      return;
    }
    await loadCommandCatalog(false);
    // 有空格且已有主指令：仍可按整词搜，但优先补主指令
    let items = localFuzzy(v.split(/\s/)[0]);
    if (!items.length) items = localFuzzy(v);
    cmdSuggest.index = 0;
    renderSuggest(items);
  }

  function bindSuggest() {
    const inp = $("cmdInput");
    if (!inp || inp._sugBound) return;
    inp._sugBound = true;
    inp.addEventListener("input", function () {
      updateSuggest();
    });
    inp.addEventListener("focus", function () {
      if (inp.value && inp.value[0] === "/") updateSuggest();
    });
    inp.addEventListener("keydown", function (e) {
      const el = cmdListEl();
      const open = el && !el.classList.contains("hidden") && cmdSuggest.items.length;
      if (!open) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        cmdSuggest.index = Math.min(cmdSuggest.items.length - 1, cmdSuggest.index + 1);
        renderSuggest(cmdSuggest.items);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        cmdSuggest.index = Math.max(0, cmdSuggest.index - 1);
        renderSuggest(cmdSuggest.items);
      } else if (e.key === "Enter") {
        // 若列表打开且输入以 / 开头且仅是查询（无空格）→ 填入而不是提交
        if (inp.value && inp.value[0] === "/" && !/\s/.test(inp.value)) {
          e.preventDefault();
          applySuggest(cmdSuggest.index);
        } else if (inp.value && inp.value[0] === "/" && /\s$/.test(inp.value)) {
          // ignore
        } else if (cmdSuggest.items.length && inp.value[0] === "/") {
          // 有参数时 Enter 提交指令；补全仅当无参数
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        hideSuggest();
      } else if (e.key === "Tab") {
        if (cmdSuggest.items[cmdSuggest.index]) {
          e.preventDefault();
          applySuggest(cmdSuggest.index);
        }
      }
    });
    document.addEventListener("click", function (e) {
      const wrap = document.querySelector(".composer-wrap");
      if (wrap && !wrap.contains(e.target)) hideSuggest();
    });
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

  // ---------- 账户钱包（account-death T13） ----------
  // 后端字段名原样使用：wallet{username,balance,entries[],ledger[]}，
  // entry{ts,kind,amount,ref,note}；不改名、不捏造。
  const WALLET_KIND_CN = {
    death_sweep: "死亡归集",
    consignment_sale: "寄售成交",
    auction_sale: "拍卖成交",
    auction_refund: "拍卖退款",
    wallet_withdraw: "钱包提取",
  };
  function walletKindCn(kind) {
    return WALLET_KIND_CN[kind] || kind || "流水";
  }
  function fmtWalletTs(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts * 1000);
      const p = (n) => String(n).padStart(2, "0");
      return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    } catch (_) {
      return "";
    }
  }
  function walletEntriesHtml(wallet) {
    const entries = (wallet && (wallet.entries || wallet.ledger)) || [];
    if (!entries.length) return '<p class="empty">暂无流水。</p>';
    return entries
      .map((e) => {
        const amt = Number(e.amount) || 0;
        const sign = amt >= 0 ? "+" : "";
        const note = e.note || e.ref || "";
        const ts = fmtWalletTs(e.ts);
        return `<div class="wallet-row"><span>${esc(walletKindCn(e.kind))}${ts ? " · " + esc(ts) : ""}${note ? `<span class="muted">（${esc(note)}）</span>` : ""}</span><span class="amt">${sign}${amt} 灵石</span></div>`;
      })
      .join("");
  }
  // 命盘钱包行：户名＋余额＋最近流水（可展开）＋提取入口的显示层。
  // 提取本身走 /钱包提取 命令，失败时后端不改余额，本函数只做只读渲染。
  function renderWallet(wallet) {
    if (!wallet) return;
    const bal = wallet.balance != null ? wallet.balance : 0;
    setText("stWallet", bal + " 灵石");
    setText("walletBalance", bal + " 灵石");
    const userEl = $("walletUser");
    if (userEl) {
      const name = wallet.username || state.username || "";
      userEl.textContent = name ? "户名：" + name : "户名：—";
    }
    const box = $("walletEntries");
    if (box) box.innerHTML = walletEntriesHtml(wallet);
    // 钱包恢复可用（U12 降级反向：此前因缺失被禁用的提取表单重新启用）
    const amt = $("walletAmount");
    if (amt) amt.disabled = false;
    const form = $("walletForm");
    if (form) {
      const btn = form.querySelector("button[type=submit]");
      if (btn) btn.disabled = false;
    }
  }
  // U12 降级：wallet 缺失时显示 — 且禁用提取表单（不是隐藏余额后仍可提交）
  function renderWalletMissing() {
    setText("stWallet", "—");
    setText("walletBalance", "—");
    const userEl = $("walletUser");
    if (userEl) userEl.textContent = "户名：—";
    const box = $("walletEntries");
    if (box) box.innerHTML = '<p class="empty">暂无流水。</p>';
    const amt = $("walletAmount");
    if (amt) amt.disabled = true;
    const form = $("walletForm");
    if (form) {
      const btn = form.querySelector("button[type=submit]");
      if (btn) btn.disabled = true;
    }
  }
  function setWalletMsg(text, isErr) {
    const el = $("walletMsg");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("err", !!isErr);
  }

  // ---------- 行囊（灰度批次 B） ----------
  function renderBag(st) {
    const list = $("bagList");
    if (!list) return;
    const inv = Array.isArray(st.inventory) ? st.inventory : [];
    const eq = Array.isArray(st.equipped) ? st.equipped : [];
    const arr = Array.isArray(st.arrays) ? st.arrays : [];
    // 游戏语义：穿戴会把物品移出行囊、卸下才放回（core/loot_equip），两列表互斥，
    // 已穿戴必须单独成行渲染，否则永远看不见。
    // 计数：行囊内同名物品合并显示 ×n
    const counts = new Map();
    inv.forEach((n) => counts.set(n, (counts.get(n) || 0) + 1));
    const total = inv.length + eq.length + arr.length;
    setText("bagCount", total ? total + " 件" : "");
    list.innerHTML = "";
    if (!counts.size && !eq.length && !arr.length) {
      list.innerHTML = '<p class="empty">行囊空空</p>';
    }
    const mkBtn = (label, cmd) => {
      const b = document.createElement("button");
      b.className = "btn-mini";
      b.textContent = label;
      b.addEventListener("click", () => { lastCmd = cmd; send(cmd); });
      return b;
    };
    const mkRow = (nameText, btns) => {
      const row = document.createElement("div");
      row.className = "bag-row";
      const nm = document.createElement("span");
      nm.className = "bag-name";
      nm.textContent = nameText;
      row.appendChild(nm);
      if (btns && btns.length) {
        const acts = document.createElement("span");
        acts.className = "bag-acts";
        btns.forEach((b) => acts.appendChild(b));
        row.appendChild(acts);
      }
      return row;
    };
    eq.forEach((name) => {
      list.appendChild(mkRow(name + "（已穿戴）", [mkBtn("卸下", "/卸下 " + name)]));
    });
    counts.forEach((n, name) => {
      list.appendChild(mkRow(name + (n > 1 ? " ×" + n : ""), [
        mkBtn("穿戴", "/穿戴 " + name),
        mkBtn("服用", "/服用 " + name),
      ]));
    });
    arr.forEach((name) => {
      const row = document.createElement("div");
      row.className = "bag-row";
      const nm = document.createElement("span");
      nm.className = "bag-name";
      nm.textContent = name + "（阵盘）";
      row.appendChild(nm);
      list.appendChild(row);
    });
    // 法门（功法）只读展示（F02：附主修/辅修标记）
    const arts = $("bagArts");
    if (arts) {
      const sk = Array.isArray(st.skills) ? st.skills : [];
      const slot = st.arts && typeof st.arts === "object" ? st.arts : null;
      if (sk.length) {
        let label = "法门：" + sk.join("、");
        if (slot) {
          if (slot.main) label += "｜主修：" + slot.main;
          if (Array.isArray(slot.sub) && slot.sub.length) label += "｜辅修：" + slot.sub.join("、");
        }
        arts.textContent = label;
        arts.classList.remove("hide");
      } else {
        // U13：空法门亦须文字空态，不得空白一片
        arts.textContent = "法门：暂无";
        arts.classList.remove("hide");
      }
    }
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
      } else {
        // U08/G5：解析失败只显示原文，不画条、不显示 0%
        setBar("stExpBar", 0);
        setBar("hudExpBar", 0);
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
      setText("stStones", st.stones + " 灵石");
      setText("hudStones", st.stones + " 灵石");
    }
    if (st.vault != null) setText("stVault", st.vault + " 灵石");
    // 账户钱包行（T13-2）：status.wallet 由后端 _status_dict 下发
    // MF3：降级守卫统一为 == null——缺键时 st.wallet 为 undefined，== null 为真，
    // 故缺键亦触发降级，不再残留旧钱包；其余假值（不应出现）不渲染也不降级。
    if (st.wallet) renderWallet(st.wallet);
    else if (st.wallet == null) renderWalletMissing();
    if (st.rem_years != null) {
      const y = Number(st.rem_years);
      const label = (Math.round(y * 10) / 10) + " 岁";
      setText("stLife", label);
      setText("hudLife", label);
      // 出生寿元约 70–100，用 100 做满槽；条只作相对长度，不得标注百分比含义（U05/G1）
      const pct = Math.max(0, Math.min(100, (y / 100) * 100));
      // 大限态唯一可信阈值：lifespan_warning 或 rem_years < 10（U05/D4）
      const lifeWarn = !!(st.lifespan_warning || y < 10);
      setBar("stLifeBar", pct, lifeWarn);
      setBar("hudLifeBar", pct, lifeWarn);
      const lifeEl = $("stLife");
      if (lifeEl) lifeEl.style.color = lifeWarn ? "var(--blood)" : "";
      const hudLifeState = $("hudLifeState");
      if (hudLifeState) {
        hudLifeState.textContent = lifeWarn ? "大限将至" : "";
        hudLifeState.classList.toggle("hide", !lifeWarn);
      }
    } else if (st.rem_years == null) {
      // U05 降级：缺失时两处均显示 —、条宽 0、不标红、不报错
      // MF3：原 "rem_years" in st 守卫在缺键时不触发、旧值残留；改为 == null（null/缺键均触发）
      setText("stLife", "—");
      setText("hudLife", "—");
      setBar("stLifeBar", 0, false);
      setBar("hudLifeBar", 0, false);
      const hudLifeState = $("hudLifeState");
      if (hudLifeState) hudLifeState.classList.add("hide");
    }
    if (st.sin != null || st.merit != null) {
      // U06：任一缺失该数字位显示 — 不写 0；血煞时在因果区加血色文字标志（不只靠颜色）
      const sinT = st.sin != null ? st.sin : "—";
      const merT = st.merit != null ? st.merit : "—";
      setText("stKarma", "业 " + sinT + " / 德 " + merT + (st.blood_marked ? " · 血煞缠身" : ""));
    }
    if (st.qi_mult != null) {
      const q = Number(st.qi_mult);
      const t = "×" + q.toFixed(2);
      setText("stQi", t);
      setText("hudQi", t);
    } else if (st.qi_mult == null) {
      // MF3：原 "qi_mult" in st 守卫缺键不触发、旧值残留；改为 == null
      setText("stQi", "—");
      setText("hudQi", "—");
    }
    // U06：道心单独 0–100 条并钳制，缺失则整条隐藏（不显示 0 或假值）
    const daoRow = $("daoHeartRow");
    if (st.dao_heart != null) {
      const dh = Math.max(0, Math.min(100, Number(st.dao_heart)));
      setText("stDaoHeart", dh + "");
      setBar("stDaoHeartBar", dh, false);
      if (daoRow) daoRow.classList.remove("hide");
    } else if (st.dao_heart == null) {
      // MF3：原 "dao_heart" in st 守卫缺键不触发、旧条残留；改为 == null
      if (daoRow) daoRow.classList.add("hide");
    }
    // 前世（转世继承）：st.past_life 由后端 _status_dict 下发
    // {lives,last_name,last_cause,shadow_count}；lives>0 显示「{last_name} · {last_cause}」，
    // shadow_count>0 时另起小字「因果余绪 {n} 条」。
    // MF3 口径：缺键时 st.past_life 为 undefined，== null 为真，故键缺失或 lives=0
    // 一律降级显示 —，不残留旧世信息、不报错。
    // 瞬时闪烁：转世/登录的合成局部对象不含 past_life，会瞬时显示 —，
    // 其后紧跟的 refreshSoft(true) 全量刷新立即纠正为真实前世（同势力/天象口径）。
    {
      const pastEl = $("stPastLife");
      if (pastEl) {
        const pl = st.past_life;
        if (pl != null && Number(pl.lives) > 0) {
          const parts = [pl.last_name, pl.last_cause].filter(
            (x) => x != null && String(x) !== ""
          );
          let pastHtml = parts.length ? esc(parts.join(" · ")) : "—";
          const shadowCount = Number(pl.shadow_count) || 0;
          if (shadowCount > 0) {
            pastHtml += `<span class="past-sub">因果余绪 ${shadowCount} 条</span>`;
          }
          pastEl.innerHTML = pastHtml;
        } else {
          pastEl.textContent = "—";
        }
      }
    }
    // U07：势力只呈现归属（宗门 + 职阶）；空宗门写散修，空职阶只写宗门，不写假职阶
    // MF3：原 "sect"/"rank" in st 守卫缺键不触发、旧值残留；改为无条件按空处理
    // （null/undefined/空串一律按空宗门→散修、空职阶→只写宗门，与 §5 缺失口径一致）。
    // 注意瞬时闪烁：转世/登录的合成局部对象不含 sect/rank，本行会瞬时显示“散修”，
    // 其后紧跟的 refreshSoft(true) 全量刷新立即纠正为真实归属（见转世/enterWorld 调用点）。
    {
      let sectText = st.sect ? st.sect : "散修";
      if (st.rank) sectText += " · " + st.rank;
      setText("stSect", sectText);
    }
    // 纪元天象（F13）：命盘一行显示当前纪元主题名
    if (st.season_theme && st.season_theme.name) {
      setText("stTheme", st.season_theme.name);
    } else {
      // MF3：原 "season_theme" in st 守卫在缺键或有对象无 name 时不触发、旧值残留；
      // 改为无条件降级（null/缺键/无 name 一律显示 —，与 §5 缺失口径一致）。
      // 瞬时闪烁：转世/登录局部对象不含本键，会瞬时显示 —，其后 refreshSoft 全量刷新纠正。
      setText("stTheme", "—");
    }
    // 心魔长期状态（F16）：命盘一行显示心魔阶段
    if (st.heart_demon_state) {
      const hd = st.heart_demon_state;
      setText("stDemon", hd.stage > 0 ? hd.stage_name + " · 魔念 " + hd.seed : "无种");
      const dEl = $("stDemon");
      if (dEl) dEl.style.color = hd.stage >= 3 ? "var(--blood)" : hd.stage === 2 ? "var(--warn, #d97706)" : "";
    } else {
      // U06 降级：缺失不得写「无种」（无种以 stage==0 为准），显示 —
      // MF3：原 "heart_demon_state" in st 守卫缺键不触发、旧值残留；改为无条件降级。
      // 瞬时闪烁：转世/登录局部对象不含本键，会瞬时显示 —，其后 refreshSoft 全量刷新纠正。
      setText("stDemon", "—");
      const dEl = $("stDemon");
      if (dEl) dEl.style.color = "";
    }
    if (st.inventory || st.equipped || st.arrays) renderBag(st);
    // 灵宠（F01）：命盘一行显示出战灵宠
    // MF3：原 "pet"/"pets_count" in st 守卫缺键不触发、旧值残留；改为无条件按空处理
    // （null/缺键/无宠一律显示 —，与 §5 缺失口径一致）。
    // 瞬时闪烁：转世/登录局部对象不含本键，会瞬时显示 —，其后 refreshSoft 全量刷新纠正。
    {
      if (st.pet) {
        setText("stPet", st.pet.name + " · " + (st.pet.level || 1) + "级");
      } else if (st.pets_count) {
        setText("stPet", "休息中 " + st.pets_count + " 只");
      } else {
        setText("stPet", "—");
      }
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
    if (st.blood_marked) {
      labels.push("血煞缠身");
      warn = true;
    }
    if (st.lifespan_warning) {
      labels.push("大限将至");
      warn = true;
    }
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
        // U09 状态色统一：血煞用血色 danger，大限/冲突用橙色 warn，其余用玉色默认
        pill.classList.toggle("danger", !!st.blood_marked);
        pill.classList.toggle("warn", warn && !st.blood_marked);
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

    // 地点标签（U09/G4）：只分闭关 / 凶域 / 中性三态；无 is_safe 字段时
    // 不得断言「安全」，中性态只写地点名或 —（旧「安全」文案已删除）
    const zone = $("zoneTag");
    if (zone) {
      if (st.meditating || st.status === "MEDITATING") {
        zone.textContent = "闭关";
        zone.className = "tag warn";
      } else if (st.conflict_zone) {
        zone.textContent = "凶域";
        zone.className = "tag danger";
      } else if (st.location) {
        zone.textContent = st.location;
        zone.className = "tag neutral";
      } else {
        zone.textContent = "—";
        zone.className = "tag neutral";
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
      setText("stStones", stones + " 灵石");
      setText("hudStones", stones + " 灵石");
    }
    if (vault) setText("stVault", vault + " 灵石");
    if (sin) setText("stKarma", "业 " + sin + " / 德 —");
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
        `<button class="btn-primary sm" data-talk="${esc(r.name)}">点开聊窗</button>` +
        `<button data-fight="${esc(r.name)}">斗法</button>` +
        `<button data-profile="${esc(r.name)}">人物</button>` +
        `</div>`;
      // 整卡点击也能开聊
      card.style.cursor = "pointer";
      card.addEventListener("click", (ev) => {
        if (ev.target.closest("button") || ev.target.closest("a")) return;
        if (!r.name || r.name === state.name) return;
        openChat(r.name);
        lastCmd = "/交谈 " + r.name;
        send("/交谈 " + r.name);
      });
      box.appendChild(card);
    }
  }

  // ---------- tabs ----------
  function switchTab(name) {
    if (name !== "feed" && name !== "goals" && name !== "world") return;
    document.querySelectorAll('.tab[data-tab]').forEach((t) => {
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
      bindSuggest();
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
  // U15：捕获阶段记录本次触发控件（按钮 / 表单提交按钮），send() 在请求期间
  // 将其 disabled + .is-loading，二次触发不发请求；成功/失败后一律恢复。
  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t && t.closest) {
      const b = t.closest("button, a.btn-icon, .boost-item");
      if (b) state.lastTrigger = b;
    }
  }, true);
  document.addEventListener("submit", (e) => {
    state.lastTrigger = e.submitter || document.activeElement;
  }, true);

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
    const trig = state.lastTrigger && state.lastTrigger instanceof HTMLElement ? state.lastTrigger : null;
    if (trig && !trig.disabled) {
      trig.disabled = true;
      trig.classList.add("is-loading");
      trig.setAttribute("aria-busy", "true");
    }
    try {
      const data = await api("/action", { token: state.token, command: c });
      handleResult(data);
      return data;
    } catch (e) {
      log("失败：" + e.message, "err");
      return null;
    } finally {
      if (trig) {
        trig.disabled = false;
        trig.classList.remove("is-loading");
        trig.removeAttribute("aria-busy");
      }
      setBusy(false);
      if (state.composerOpen) {
        const input = $("cmdInput");
        if (input) input.focus();
      }
      const cinp = $("chatInput");
      if (cinp && !$("chatModal").classList.contains("hidden") && !state.chatEnded) {
        cinp.focus();
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
    state.lastFocus = document.activeElement;
    m.classList.remove("hidden");
    m.setAttribute("aria-hidden", "false");
    state.chatEnded = false;
    if (npcName) state.chatNpc = npcName;
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
    state.chatNpc = "";
    setChatInputEnabled(true);
    // U25：关闭后焦点回到触发点附近
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
  }
  function handleChatPayload(data, text) {
    if (data.chat_open) {
      openChat(data.npc || "");
      if (data.ok && text) {
        const lines = text.split("\n").filter(Boolean);
        for (const ln of lines) {
          if (/会话开始|用 \/说|可开口/.test(ln)) chatAppend("", ln, "sys");
          else if (/【会话已终】|作别|不愿再言|挂断|动手|赠礼|成交|行窃|擒拿|释放/.test(ln)) chatAppend("", ln, "sys");
          else if (/【同场】/.test(ln)) chatAppend("", ln, "sys");
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
<<<<<<< HEAD
  function removeInlineOmenBar() {
    state.omenInlineOpen = false;
    const bar = $("inlineOmenBar");
    if (bar) bar.remove();
  }

  function renderInlineOmenBar(title, choices) {
    state.omenInlineOpen = true;
    let bar = $("inlineOmenBar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "inlineOmenBar";
      bar.className = "inline-omen-bar";
      const form = $("cmdForm");
      if (form && form.parentNode) {
        form.parentNode.insertBefore(bar, form);
      }
    }
    bar.innerHTML = "";
    const titleEl = document.createElement("span");
    titleEl.className = "omen-tag";
    titleEl.textContent = `【机缘 · ${title || "奇遇"}】`;
    bar.appendChild(titleEl);

    const list = Array.isArray(choices) ? choices : [];
    for (const ch of list) {
      const id = typeof ch === "object" ? ch.id : ch.split(".")[0];
      const label = typeof ch === "object" ? ch.label : ch.replace(/^\d+\./, "");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-soft omen-chip";
      btn.textContent = label;
      btn.addEventListener("click", () => {
        send("/奇遇 " + id);
      });
      bar.appendChild(btn);
    }
    const leaveBtn = document.createElement("button");
    leaveBtn.type = "button";
    leaveBtn.className = "btn-ghost sm omen-abandon";
    leaveBtn.textContent = "抽身";
    leaveBtn.addEventListener("click", () => {
      send("/奇遇 弃");
      removeInlineOmenBar();
    });
    bar.appendChild(leaveBtn);
=======
  function openOmen(title) {
    const m = $("omenModal");
    if (!m) return;
    state.lastFocus = document.activeElement;
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
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
>>>>>>> fb383c1fb995e8dabd8bd77ac6775956a22274bf
  }

  function parseOmenChoices(text) {
    const m = /选项：(.+)/.exec(text || "");
    if (!m) return [];
    return m[1].split("|").map((s) => s.trim()).filter(Boolean);
  }

  function handleOmenPayload(data, text) {
    const isInline = data.omen_inline || data.omen_open;
    if (!isInline && !data.omen_ended) return false;
    if (isInline) {
      const choices = data.omen_choices || parseOmenChoices(text);
      renderInlineOmenBar(data.omen_title || "奇遇", choices);
      return true;
    }
    if (data.omen_ended) {
      removeInlineOmenBar();
      return true;
    }
    return false;
  }

  (function bindChat() {
    const form = $("chatForm");
    const inp = $("chatInput");
    const btn = $("chatClose");
    // 聊天窗：直接自由发言，无需 /说；服务端判行为
    async function sendChatFree(v) {
      if (!state.token) {
        chatAppend("", "尚未入世", "sys");
        return;
      }
      setBusy(true);
      try {
        const body = { token: state.token, text: v };
        if (state.chatNpc) body.to = state.chatNpc;
        const data = await api("/chat", body);
        if (data.status) applyStatus(data.status);
        handleResult(data);
      } catch (e) {
        chatAppend("", "发送失败：" + e.message, "sys");
      } finally {
        setBusy(false);
        if (inp && !state.chatEnded) inp.focus();
      }
    }
    if (form && inp) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (state.chatEnded) return;
        const v = (inp.value || "").trim();
        if (!v) return;
        // U15：失败保留输入——成功后才清空；失败时草稿留在输入框内
        chatAppend("你", v, "me");
<<<<<<< HEAD
        // 有目标时带上 to，保证服务端能对上号
        if (state.chatNpc && !$("chatNpcName").textContent.includes(state.chatNpc)) {
          /* header already set */
        }
        sendChatFree(v);
=======
        lastCmd = "/说";
        const data = await send("/说 " + v);
        if (data && data.ok !== false) inp.value = "";
        // MF8/U15：send() busy 早返返回 undefined（已在 feed 记“天道正在裁决，稍候…”），
        // 属稍候而非失败：不追加失败行、不记失败，输入保留待重试；仅 data 为 null
        // （网络/请求异常）或 ok===false 时才追加失败行。
        else if (data === undefined) { /* 稍候，草稿保留，不记失败 */ }
        else chatAppend("", "发送失败，草稿已保留。", "sys");
>>>>>>> fb383c1fb995e8dabd8bd77ac6775956a22274bf
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
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const v = (inp.value || "").trim();
        if (!v) return;
        // U15：失败保留输入——成功后才清空
        omenAppend("你", v, "me");
        lastCmd = "/奇遇说";
        const data = await send("/奇遇说 " + v);
        if (data && data.ok !== false) inp.value = "";
        // MF8/U15：同聊天提交——send() busy 早返（undefined）只表示稍候，
        // feed 已记“天道正在裁决，稍候…”，不追加失败行、不记失败，输入保留。
        else if (data === undefined) { /* 稍候，草稿保留，不记失败 */ }
        else omenAppend("", "发送失败，草稿已保留。", "sys");
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
      // 死亡结算页（T13-1）：钱包取 status.wallet，归集明细取 sweep/settlement。
      // 评审 S2：局内死亡后端下发 sweep 与 death_cause；settlement==null 时按
      // in_game 文案（“明细未随响应下发”），与恢复会话的“此前已结算”区分。
      const _sweep = data.sweep || data.settlement || null;
      if (data.death_cause) legacy.death_cause = data.death_cause;
      showDeath(text, legacy, {
        wallet: data.status && data.status.wallet,
        settlement: _sweep,
        username: state.username,
        death_context: "in_game",
        consignment_open_count:
          (_sweep && _sweep.consignment_open_count) != null
            ? _sweep.consignment_open_count
            : data.consignment_open_count,
      });
      return;
    }

    if (data.ok && data.boosts_applied !== undefined && data.settle !== undefined) {
      log(data.text || "转世完成", "ok");
      // MF3：合成局部对象（仅 4 键）——缺失键的降级行（钱包/势力/天象/心魔/灵宠）
      // 会瞬时显示降级态，下方 refreshSoft(true) 全量刷新立即纠正；非局部键的旧值
      // 亦只保留到该次刷新，不作最终呈现。
      applyStatus({
        name: data.name,
        realm: data.realm,
        location: data.location,
        rem_years: data.rem_years,
      });
      if (data.wallet) renderWallet(data.wallet);
      hideDeath();
      // 建角引导（T13-3）：转世成功后在天道录再展示一次三要素
      showRebirthGuide(data);
      refreshSoft(true);
      return;
    }

    // 钱包命令反馈（T13-2）：/钱包提取 失败时后端返回 ok:false 且余额不变，
    // 此处只显示 error 文案，绝不改动已渲染的余额；成功则刷新钱包行。
    if (lastCmd === "/钱包" || lastCmd.indexOf("/钱包提取") === 0 || lastCmd.indexOf("/wallet") === 0) {
      const w = data.wallet || (data.status && data.status.wallet);
      if (w) renderWallet(w);
      if (lastCmd.indexOf("/钱包提取") === 0 || lastCmd.indexOf("/wallet_withdraw") === 0) {
        if (data.ok) {
          setWalletMsg(data.text || "提取成功。", false);
          const inp = $("walletAmount");
          if (inp) inp.value = "";
        } else {
          setWalletMsg(data.error || "提取失败，余额不变。", true);
        }
      }
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
    state.lastFocus = document.activeElement;
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
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
  }
  async function confirmPrompt() {
    if (!promptCfg) return;
    if (state.busy) {
      $("promptHint").textContent = "天道正在裁决，稍候…";
      return;
    }
    const v = $("promptInput").value.trim();
    if (!v) {
      $("promptInput").focus();
      return;
    }
    if (promptCfg.numeric && !/^[1-9]\d*$/.test(v)) {
      $("promptHint").textContent = "请输入正整数";
      return;
    }
    const cmd = (promptCfg.prefix + " " + v).trim();
    // U15/U16：失败时弹层保持打开、输入保留、错误就地显示；成功后才关闭
    state.lastTrigger = $("promptOk");
    lastCmd = cmd;
    const data = await send(cmd);
    if (!data || data.ok === false) {
      $("promptHint").textContent = (data && data.error) || "发送失败，请重试。";
      $("promptInput").focus();
      return;
    }
    closePrompt();
  }

  // ---------- demon ----------
  function showDemon(fullText, options) {
    // MF6 残留：仅在弹层由隐藏变显示时保存一次 lastFocus，关闭时恢复（U25）。
    // 同会话多轮重弹时弹层本已显示，不再覆盖：上一轮刚被点击的选项按钮
    // 随即被下方 innerHTML 清空，覆盖后的 lastFocus 会使 hideDemon 的
    // contains 守卫失败、焦点落到 body；保留首轮焦点才能正确恢复。
    const demonModal = $("demonModal");
    if (demonModal.classList.contains("hidden")) state.lastFocus = document.activeElement;
    demonModal.classList.remove("hidden");
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
      b.onclick = async () => {
        // U15：选择先发请求；成功且非新一轮问心时关窗，失败时弹层保持打开
        lastCmd = "心魔选择";
        const data = await send(String(i + 1));
        if (data && data.ok !== false && !data.pending_heart_demon) hideDemon();
      };
      box.appendChild(b);
    });
    if (!options || !options.length) {
      const b = document.createElement("button");
      b.textContent = "暂避锋芒";
      b.onclick = async () => {
        lastCmd = "心魔选择";
        const data = await send("yield");
        if (data && data.ok !== false && !data.pending_heart_demon) hideDemon();
      };
      box.appendChild(b);
    }
    const firstOpt = box.querySelector("button");
    if (firstOpt) firstOpt.focus();
  }

  function hideDemon() {
    $("demonModal").classList.add("hidden");
    $("demonFree").value = "";
    // MF6：关闭后焦点回到触发点附近（同 closeChat 模式）
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
  }

  // ---------- death / rebirth ----------
  // 金额右对齐、单位统一「灵石」；零项不隐藏、显示「—」（spec §2.8）。
  function settleAmt(v) {
    const n = Number(v) || 0;
    return n ? n + " 灵石" : "—";
  }
  function settleRow(label, amtHtml) {
    return `<div class="settle-row"><span>${esc(label)}</span><span class="amt">${amtHtml}</span></div>`;
  }
  // 死亡结算明细表（T13-1，spec §2.8 顺序）：
  // 随身／寄存／拍卖退款逐单／当票没收／议政作废／寄售待结提示／合计。
  // 合计行＝随身＋寄存＋拍卖退款（后端 sweep.total，S1），与明细加总一致。
  // 评审 S2：settlement==null 时按场景区分文案——恢复会话／登录死者是“此前已结算”，
  // 局内新死（后端本应下发 sweep）是“明细未随响应下发”，不得混用。
  // 评审 S3：在售单数取 sweep/dead_payload 的 consignment_open_count，不编造。
  function renderDeathSettle(settlement, wallet, consignmentCount, deathContext) {
    const box = $("deathSettle");
    if (!box) return;
    const openCount =
      consignmentCount != null
        ? consignmentCount
        : settlement && settlement.consignment_open_count != null
        ? settlement.consignment_open_count
        : null;
    let html = "<h3>资金归集明细</h3>";
    if (!settlement) {
      if (deathContext === "in_game") {
        html +=
          '<div class="settle-note">局内新死：本次死亡刚结算，但归集明细未随响应下发，' +
          "请以账户钱包最近流水为准。</div>";
      } else {
        html +=
          '<div class="settle-note">本次登录未产生新的资金归集（此前已结算）。' +
          "归集金额已在账户钱包中，明细见下方钱包最近流水。</div>";
      }
    } else {
      html += settleRow("随身灵石", settleAmt(settlement.spirit));
      html += settleRow("寄存灵石", settleAmt(settlement.vault));
      const refunds = Array.isArray(settlement.auction_refunds) ? settlement.auction_refunds : [];
      if (refunds.length) {
        refunds.forEach((r) => {
          html += settleRow("拍卖退款 · " + (r.item || r.lot_id || "拍品"), "+" + (Number(r.amount) || 0) + " 灵石");
        });
      } else {
        html += settleRow("拍卖退款", "—");
      }
      const forfeits = Array.isArray(settlement.pawn_forfeits) ? settlement.pawn_forfeits : [];
      if (forfeits.length) {
        forfeits.forEach((t) => {
          html += settleRow("当票没收 · " + (t.item || t.ticket_id || "典当物"), "赎回价 " + (Number(t.redeem) || 0) + " 灵石");
        });
        html += '<div class="settle-note">当票没收：物品入当铺寄售；本金已在随身灵石中，不重复记账。</div>';
      } else {
        html += settleRow("当票没收", "—");
      }
      const voided = Number(settlement.council_voided) || 0;
      html += settleRow("议政票作废", voided ? voided + " 票" : "—");
      if (settlement.trade_cancelled) {
        html += '<div class="settle-note">当面交易会话已取消，锁定财货已解锁。</div>';
      }
      html += `<div class="settle-row total"><span>归集合计</span><span class="amt">${(Number(settlement.total) || 0)} 灵石</span></div>`;
    }
    html +=
      openCount != null
        ? `<div class="settle-note">寄售待结：在售 ${openCount} 单，留单待售，成交后货款入账户钱包；新角不得撤旧世单。</div>`
        : '<div class="settle-note">寄售待结：在售寄售单留单待售，成交后货款入账户钱包；新角不得撤旧世单。</div>';
    box.innerHTML = html;
    // 结算页钱包余额行：户名＋余额＋最近流水
    const wbox = $("deathWallet");
    if (wbox) {
      if (wallet) {
        const bal = wallet.balance != null ? wallet.balance : 0;
        const name = wallet.username || state.username || "";
        wbox.innerHTML =
          `<div class="wallet-top"><span>账户钱包${name ? "（户名：" + esc(name) + "）" : ""}</span><b>${bal} 灵石</b></div>` +
          `<div class="wallet-entries">${walletEntriesHtml(wallet)}</div>`;
      } else {
        wbox.innerHTML = "";
      }
    }
  }
  // 建角引导三要素（T13-3，spec §2.8）：①钱包余额与户名 ②新角随身 150 不变
  // ③/钱包提取 指引；明确「钱包不会自动划转」，不暗示自动划转。
  function rebirthGuideHtml(username, balance) {
    const name = username || state.username || "";
    const bal = balance != null ? balance : "—";
    return (
      `<div>① 钱还在你的账户名下：${name ? "户名 " + esc(name) + " · " : ""}账户钱包 <b>${bal} 灵石</b>。</div>` +
      `<div>② 新角出生随身 <b>150 灵石</b>不变（道统灵石加成另计）；钱包不会自动划转入随身。</div>` +
      `<div>③ 入世后用 <b>/钱包提取 &lt;金额&gt;</b> 取用账户金额（钱包 −n，随身 ＋n）。</div>`
    );
  }
  function showRebirthGuide(data) {
    const box = $("log");
    if (!box) return;
    const bal = data.wallet ? data.wallet.balance : null;
    const el = document.createElement("div");
    el.className = "line ok";
    el.innerHTML = "【转世指引】<br/>" + rebirthGuideHtml(state.username, bal);
    box.appendChild(el);
    while (box.children.length > 400) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  // ---------- 转世继承：前世留痕 / 遗物（reincarnation-inheritance T7） ----------
  // 态度词口径与 storage set_attitude / ATTITUDE_LABELS 一致（按 value 阈值现算，
  // 不依赖 shadow 条目自带 label，条目无 label 时亦可渲染）：
  // >=40 亲近（ally）、>=15 友善、<=-40 仇视、<=-15 戒备、其余 中立。
  function shadowAttitudeWord(value) {
    const v = Number(value);
    if (!Number.isFinite(v)) return "中立";
    if (v >= 40) return "亲近";
    if (v >= 15) return "友善";
    if (v <= -40) return "仇视";
    if (v <= -15) return "戒备";
    return "中立";
  }
  // trace 取数防御：主口径 legacy.trace（刚逝一世）；会话恢复等路径若后端
  // 只下发 traces 列表，则取末世兜底。两者皆缺失/为 null 时返回 null，
  // 调用方整段不渲染（不自造默认值掩盖缺失）。
  function deathTraceOf(legacy) {
    if (!legacy) return null;
    if (legacy.trace) return legacy.trace;
    if (Array.isArray(legacy.traces) && legacy.traces.length) {
      return legacy.traces[legacy.traces.length - 1] || null;
    }
    return null;
  }
  function heirloomBelongingsOf(legacy) {
    const trace = deathTraceOf(legacy);
    if (!trace || !Array.isArray(trace.belongings)) return [];
    return trace.belongings
      .map((n) => (n == null ? "" : String(n)))
      .filter((n) => n !== "");
  }
  // 「前世留痕」摘要：影子逐条 + 未了之诺条数；trace 为 null 或两类皆空时
  // 返回空串（整段不渲染）。享寿/死因已在首行渲染，此处不重复。
  function legacyTraceHtml(trace) {
    if (!trace) return "";
    const shadow = Array.isArray(trace.shadow) ? trace.shadow : [];
    const promises = Array.isArray(trace.open_promises) ? trace.open_promises : [];
    const lines = [];
    shadow.forEach((s) => {
      if (!s || s.npc_name == null || String(s.npc_name) === "") return;
      const v = s.value != null ? s.value : 0;
      lines.push(
        `<div class="trace-line">${esc(s.npc_name)}：前世${esc(shadowAttitudeWord(v))}（${esc(String(v))}）</div>`
      );
    });
    if (promises.length > 0) {
      lines.push(
        `<div class="trace-line">未了之诺 ${promises.length} 条，已随旧世消散</div>`
      );
    }
    if (!lines.length) return "";
    return `<div class="legacy-trace"><div class="trace-title">前世留痕</div>${lines.join("")}</div>`;
  }
  function syncHeirloomSelect() {
    const wrap = $("heirloomWrap");
    if (!wrap) return;
    if (state.selectedBoosts.includes("heirloom")) {
      wrap.classList.remove("hide");
    } else {
      wrap.classList.add("hide");
    }
  }

  function showDeath(text, legacy, extra) {
    extra = extra || {};
    // MF6：照聊天 modal 模式保存 lastFocus（须在下方 rebornName.focus() 之前），关闭时恢复（U25）
    state.lastFocus = document.activeElement;
    $("deathModal").classList.remove("hidden");
    const cause = legacy.death_cause || extra.death_cause || "身死道消";
    // 评审 S4：死亡页首行渲染死因与享寿。享寿取 dead_payload legacy.lifespan_lived，
    // 会话恢复路径取 /legacy 的 past_lives 末世 lived（同字段两种名字，兼容）。
    const lastLife =
      legacy.past_lives && legacy.past_lives.length
        ? legacy.past_lives[legacy.past_lives.length - 1]
        : null;
    const lived =
      legacy.lifespan_lived != null
        ? legacy.lifespan_lived
        : lastLife != null
        ? lastLife.lifespan_lived != null
          ? lastLife.lifespan_lived
          : lastLife.lived
        : null;
    $("deathText").textContent =
      "本世道途已终（" +
      cause +
      (lived != null ? "，享寿 " + lived + " 岁" : "") +
      "）。真灵可携道统重入轮回。";
    // 前世留痕（T7）：trace 三条进入路径结构不一，统一经 deathTraceOf 防御取数；
    // trace 为 null/缺失时 legacyTraceHtml 返回空串，整段不渲染、不报错。
    const deathTrace = deathTraceOf(legacy);
    const heirloomBelongings = heirloomBelongingsOf(legacy);
    $("deathLegacy").innerHTML =
      `道统点 <b>${legacy.points ?? 0}</b> · 已历 <b>${legacy.lives ?? 0}</b> 世<br/>` +
      `可选出身加成（至多 ${legacy.max_boosts ?? 3} 项）` +
      legacyTraceHtml(deathTrace);
    // 结算明细＋钱包余额在建角表单之前（spec §2.8 结构顺序）
    renderDeathSettle(
      extra.settlement || null,
      extra.wallet || null,
      extra.consignment_open_count,
      extra.death_context
    );
    const guide = $("deathGuide");
    if (guide) {
      const bal = extra.wallet ? extra.wallet.balance : null;
      guide.innerHTML = rebirthGuideHtml(extra.username || extra.wallet && extra.wallet.username, bal);
    }
    const errEl = $("deathError");
    if (errEl) {
      errEl.textContent = "";
      errEl.classList.add("hide");
    }

    const box = $("boostBox");
    box.innerHTML = "";
    state.selectedBoosts = [];
    // 遗物候选下拉（T7）：每次打开死亡页按本世 trace.belongings 重填，
    // 默认隐藏；仅 heirloom 被选中时由 syncHeirloomSelect 显示。
    const heirloomSel = $("heirloomSelect");
    if (heirloomSel) {
      heirloomSel.innerHTML = "";
      heirloomBelongings.forEach((itemName) => {
        const opt = document.createElement("option");
        opt.value = itemName;
        opt.textContent = itemName;
        heirloomSel.appendChild(opt);
      });
    }
    syncHeirloomSelect();
    (legacy.boosts || []).forEach((b) => {
      const el = document.createElement("div");
      el.className = "boost-item";
      // heirloom 无候选（belongings 为空/无 trace）：置灰不可选并附注，
      // 不计入 selectedBoosts，亦不占用 max_boosts 名额。
      const heirloomUnavailable = b.key === "heirloom" && !heirloomBelongings.length;
      if (heirloomUnavailable) {
        el.classList.add("disabled");
        el.setAttribute("aria-disabled", "true");
        el.innerHTML = `<span>${esc(b.name)}</span><span class="muted">${esc(b.desc)}</span><span class="boost-note">前世无遗物可留</span><span class="cost">${b.cost}点</span>`;
        el.onclick = () => {
          const errEl = $("deathError");
          if (errEl) {
            errEl.textContent = "前世无遗物可留";
            errEl.classList.remove("hide");
          }
        };
        box.appendChild(el);
        return;
      }
      el.innerHTML = `<span>${esc(b.name)}</span><span class="muted">${esc(b.desc)}</span><span class="cost">${b.cost}点</span>`;
      el.onclick = () => {
        const max = legacy.max_boosts || 3;
        if (state.selectedBoosts.includes(b.key)) {
          state.selectedBoosts = state.selectedBoosts.filter((k) => k !== b.key);
          el.classList.remove("selected");
        } else {
          if (state.selectedBoosts.length >= max) {
            // U14：超限就地提示（deathError 内）且不选中，不只记 feed
            const errEl = $("deathError");
            if (errEl) {
              errEl.textContent = `至多选 ${max} 项出身加成`;
              errEl.classList.remove("hide");
            }
            log(`至多选 ${max} 项出身加成`, "err");
            return;
          }
          state.selectedBoosts.push(b.key);
          el.classList.add("selected");
        }
        if (b.key === "heirloom") syncHeirloomSelect();
      };
      box.appendChild(el);
    });
    $("rebornName").value = "";
    // U25：死亡结算打开时焦点进入 modal（新道号输入框）
    const rn = $("rebornName");
    if (rn) rn.focus();
  }

  function hideDeath() {
    $("deathModal").classList.add("hidden");
    // MF6：关闭后焦点回到触发点附近（同 closeChat 模式）
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
  }

  async function doReborn() {
    // MF8 残留：照 confirmPrompt 加 busy 前置守卫。send() 的 busy 早返返回
    // undefined（仅在 feed 记“天道正在裁决，稍候…”且不发请求），若不守卫，
    // 下方 if (!data || !data.ok) 会将其误判为失败并在 deathError 写出
    // “转世失败，请重试。”。busy 时只就地提示稍候并返回，不写失败、不动按钮态。
    if (state.busy) {
      const errEl = $("deathError");
      if (errEl) {
        errEl.textContent = "天道正在裁决，稍候…";
        errEl.classList.remove("hide");
      }
      return;
    }
    const btn = $("btnReborn");
    const name = $("rebornName").value.trim();
    let cmd = "/转世";
    if (name) cmd += " " + name;
    if (state.selectedBoosts.length) {
      // heirloom 须拼作 heirloom:<物品名> 一个 token（物品名取下拉当前值）；
      // 下拉缺失/无值时退回裸 heirloom，交后端报错，不自造物品名。
      const boostTokens = state.selectedBoosts.map((k) => {
        if (k !== "heirloom") return k;
        const sel = $("heirloomSelect");
        const item = sel && sel.value ? String(sel.value).trim() : "";
        return item ? "heirloom:" + item : "heirloom";
      });
      cmd += " " + boostTokens.join(" ");
    }
    // 提交后按钮置灰防重复提交；失败时保留已填道号与已选加成，不清空重填。
    // MF4：主操作另补文案切换（触屏上不依赖等待光标即可辨识请求中态），结束后恢复原文案。
    const btnText = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.classList.add("is-loading");
      btn.textContent = "转世中…";
    }
    lastCmd = cmd;
    const data = await send(cmd);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("is-loading");
      btn.textContent = btnText;
    }
    if (!data || !data.ok) {
      // 失败： modal 保持打开（道号与加成原样保留），错误就地显示。
      $("deathModal").classList.remove("hidden");
      const errEl = $("deathError");
      if (errEl) {
        errEl.textContent = (data && data.error) || "转世失败，请重试。";
        errEl.classList.remove("hide");
      }
      return;
    }
    // 成功：handleResult 已 hideDeath 并展示转世指引。
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
    // MF3：合成局部对象（仅 4 键）——缺失键的降级行会瞬时显示降级态；
    // authJoin 在 enterWorld 返回后 await refreshSoft(true) 全量刷新纠正，见该处。
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
    const joinBtn = $("btnJoin");
    if (joinBtn) {
      joinBtn.textContent = isReg ? "注册中…" : "登录中…";
      joinBtn.classList.add("is-loading");
    }
    setBusy(true);
    try {
      const path = isReg ? "/register" : "/login";
      const data = await api(path, {
        username: user,
        password: pass,
        name: charName,
      });
      // 死者登录（account-death §2.6 行为变更）：显式处理 dead:true 分支，
      // 只展示死亡结算页，绝不静默建角；建角须玩家在结算页显式 /转世。
      if (data.dead === true) {
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
        $("gateMsg").textContent = "";
        $("gate").classList.add("hidden");
        $("app").classList.remove("hidden");
        log(`【死讯】${data.name} · ${data.death_cause || "身死道消"}`, "sys");
        const deadLegacy = Object.assign({}, data.legacy || {}, {
          death_cause: data.death_cause,
          max_boosts: (data.legacy && data.legacy.max_boosts) || 3,
        });
        state.lastLegacy = deadLegacy;
        showDeath("", deadLegacy, {
          wallet: data.wallet || null,
          settlement: data.settlement || null,
          username: data.username,
          death_context: "login",
          consignment_open_count: data.consignment_open_count,
        });
        ensureToggle();
        return;
      }
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
      // U11：请求结束恢复主按钮文案与可用态（setAuthMode 同步登录/注册文案）
      const joinBtn = $("btnJoin");
      if (joinBtn) joinBtn.classList.remove("is-loading");
      setAuthMode(state.authMode);
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

  $("cmdForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const raw = ($("cmdInput").value || "").trim();
    if (!raw) return;
    let v = raw;
    if (state.omenInlineOpen && !raw.startsWith("/")) {
      v = "/奇遇说 " + raw;
    }
    // 打开补全且仅输入 /xxx（无参数）时 Enter 已在 keydown 处理；此处提交完整指令
    lastCmd = v;
<<<<<<< HEAD
    $("cmdInput").value = "";
    hideSuggest();
    send(v);
=======
    // U15：失败保留输入——成功后才清空（原行为发送前即清空，失败后草稿不可找回）
    const data = await send(v);
    if (data && data.ok !== false) $("cmdInput").value = "";
>>>>>>> fb383c1fb995e8dabd8bd77ac6775956a22274bf
  });

  bindSuggest();
  loadCommandCatalog(true);

  // ---------- 场景抽屉 ----------
  function toggleDrawer(name) {
    const panels = document.querySelectorAll("[data-drawer-panel]");
    const tabs = document.querySelectorAll(".drawer-tab");
    let opened = false;
    panels.forEach((p) => {
      const on = p.getAttribute("data-drawer-panel") === name && p.classList.contains("hidden");
      // 简单：点同一 tab 再点则关
      const isTarget = p.getAttribute("data-drawer-panel") === name;
      const willOpen = isTarget && p.classList.contains("hidden");
      if (willOpen) opened = true;
    });
    panels.forEach((p) => {
      const isTarget = p.getAttribute("data-drawer-panel") === name;
      if (isTarget) {
        if (opened) p.classList.remove("hidden");
        else p.classList.add("hidden");
      } else {
        p.classList.add("hidden");
      }
    });
    tabs.forEach((t) => {
      t.classList.toggle("active", opened && t.getAttribute("data-drawer") === name);
    });
  }

  function bindDrawers() {
    document.querySelectorAll("[data-drawer]").forEach((el) => {
      if (el._drawerBound) return;
      el._drawerBound = true;
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleDrawer(el.getAttribute("data-drawer"));
      });
    });
  }

  document.querySelectorAll("[data-cmd]").forEach((btn) => {
    if (btn._cmdBound) return;
    btn._cmdBound = true;
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
      // U16：按钮自带的 data-hint 优先（两处「接令」借此消歧：世界页先看除凶、
      // 坊市区先看告示），命令文本与前缀本身一律不动
      const hints = {
        拜入: "须亲至总坛山门。可填：青云宗 / 万剑仙门 / 九幽天魔宗 / 四海散修商会",
        传功: "须同门且境界高于对方",
        游说: "备礼灵石请长老改立场，先点「议政」看席位与立场；铁杆长老油盐不进",
        寄存: "存入坊市金库，不可被夺；归隐中不可操作",
        支取: "从金库取出灵石",
        寄售: "货名 价格，如：妖兽内丹 60",
        买寄售: "寄售编号（先点坊市）",
        撤单: "自己的寄售编号",
        出价: "先点「拍卖」看拍品编号与当前价。填：编号 出价，出价先冻结、被超价自动退回",
        上拍: "货名 底价 [一口价]，如：青锋剑 100 300。120 分钟落槌，成交抽成 5%",
        典当: "行囊物品名：按当地市价五折得灵石，3 天内可按典当额+10%息赎回，逾期没收",
        赎回: "典当物名：付典当额+固定息取回，先点「典当」看当票",
        挂赏: "道号 赏金 [缘由]，句末加「匿」可匿名",
        接令: "告示编号（先点告示）",
        自创功法: "理念短语，如：噬血炼骨 / 玄天正气",
        探险: "野外 / 剑冢残碑 / 荒古兽巢 / 幽冥鬼市 / 灵药残圃 / 落霞古洞 等",
        穿戴: "装备名，如：青锋剑 / 玄铁护腕",
        卸下: "已穿戴的装备名",
        主修: "已习得的功法名；主修令闭关修为 +10%，调整槽位有 1 小时冷却",
        辅修: "已习得的功法名；每门辅修斗法战力 +3%，最多 2 门",
        卸功: "卸下已装配的主修或辅修功法名",
        炼体: "副修面板；「/炼体 修炼 [n]」耗妖兽内丹+灵石升层：战力 +1%/层、寿元 +1 岁/层，满 10 层",
        炼神: "副修面板；「/炼神 修炼 [n]」耗百年灵芝+灵石升层：有效道心 +2/层、神识 +3/层，满 10 层",
        镇魔: "心魔长卷；「/镇魔 服丹」耗百年灵芝+30 灵石镇压魔念，「/镇魔 静坐」以道心硬抗",
        研读: "可填书名或作者名（可空）：研读所持亲笔手稿，他人之作首次研读得修为/道心",
        购买: "先点「坊市」看货单。示例：聚气丹 / 筑基丹 / 一阶青木迷踪阵",
        出售: "卖给商会，约五折回收。示例：妖兽内丹 1",
        服用: "丹药名，如：聚气丹 / 筑基丹",
        契约: "探险遇兽后结契，耗灵石。兽名先在灵宠面板看",
        喂养: "宠名 [丹药名]：无丹药则耗灵石喂养，如：青鳞蟒 聚气丹",
        出战: "宠名，同时仅一宠出战助战",
        休息: "宠名，令出战灵宠退下",
        放生: "宠名，放归山林，不可挽回",
        钱包提取: "从账户钱包取出灵石到随身：钱包 −n，随身 ＋n；金额不得超过钱包余额",
        播种: "种子名 [数量]：种子先在坊市购买，如：聚灵草种子 2",
        接委托: "同场 NPC 名或 /委托 面板中的编号；同时只能持一条委托链",
      };
      openPrompt(title, btn.getAttribute("data-hint") || hints[title] || "", prefix, ph, numeric);
    });
  });

  document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
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

  // U18：移动端右栏抽屉开关（桌面端按钮隐藏、右栏常显）；U25：Esc 关闭已打开的弹层
  const railToggle = $("railToggle");
  if (railToggle) {
    railToggle.addEventListener("click", () => {
      const shell = document.querySelector(".shell");
      if (!shell) return;
      const open = shell.classList.toggle("rail-open");
      railToggle.setAttribute("aria-expanded", open ? "true" : "false");
      railToggle.classList.toggle("active", open);
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("promptModal").classList.contains("hidden")) closePrompt();
    // MF1：Esc 语义须与 × 完全一致，不得绕过 × 的游戏副作用——聊天 × 先
    // send("/挂断")（chatEnded 时守卫跳过）再关窗，奇遇 × 先 send("/奇遇 弃")
    // 再关窗；故 Esc 直接触发对应 × 按钮点击，而非直接调 closeChat()/closeOmen()。
    // 死亡 / 心魔 modal 不设 Esc，保持现状（死亡走「暂不转世」，心魔为阻塞态）。
    else if (!$("chatModal").classList.contains("hidden")) {
      const b = $("chatClose");
      if (b) b.click(); else closeChat();
    } else if (!$("omenModal").classList.contains("hidden")) {
      const b = $("omenClose");
      if (b) b.click(); else closeOmen();
    }
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
        // 点开聊窗：直接进入会话，无需再弹「输入指令」
        openChat(talk);
        state.chatNpc = talk;
        lastCmd = "/交谈 " + talk;
        send("/交谈 " + talk);
        return;
      } else if (fight) {
        if (confirm("确定对「" + fight + "」动手？")) {
          lastCmd = "/斗法 " + fight;
          send(lastCmd);
        }
      }
    });
  }

  $("demonFreeGo").addEventListener("click", async () => {
    const v = $("demonFree").value.trim();
    if (!v) return;
    // U15：成功且非新一轮问心时关窗；失败时弹层保持打开，输入保留
    state.lastTrigger = $("demonFreeGo");
    lastCmd = v;
    const data = await send(v);
    if (data && data.ok !== false && !data.pending_heart_demon) hideDemon();
  });
  $("demonFree").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("demonFreeGo").click();
  });

  $("btnReborn").addEventListener("click", doReborn);
  $("btnLater").addEventListener("click", () => {
    hideDeath();
    // §2.6：登录不再自动建角；暂不转世后，下次登录回到此页，或直接用 /转世 建角。
    log("真灵暂驻轮回。下次登录时可回到此页转世，或在敕令栏输入「/转世 新道号 [加成…]」。", "sys");
  });

  // 命盘钱包提取入口（T13-2）：只发命令、不预改余额；结果反馈见 handleResult。
  const walletForm = $("walletForm");
  if (walletForm) {
    walletForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = ($("walletAmount").value || "").trim();
      if (!/^[1-9]\d*$/.test(v)) {
        setWalletMsg("请输入正整数金额。", true);
        return;
      }
      setWalletMsg("", false);
      lastCmd = "/钱包提取 " + v;
      // U12/U15：成功时 handleResult 清空输入；失败时余额不变、错误进 walletMsg、输入保留
      await send(lastCmd);
    });
  }

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
  document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
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
  bindDrawers();

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
        if (lg.ok) {
          // 会话恢复的死者入口：钱包取 /look 的 status.wallet，归集明细本次
          // 不下发则结算区显示「此前已结算」＋钱包流水，不捏造明细。
          showDeath(look.text || "", lg, {
            wallet: look.status.wallet || null,
            settlement: null,
            username: state.username,
            death_context: "restore",
          });
        }
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
