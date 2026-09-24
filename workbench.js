/**
 * 天道因果录 · 灵蕴玄枢 工作台 v2
 * 水墨翡翠白玉仙侠规范 · 100% 纯正简体中文 · 黄金循环垂直切片
 * 架构：玄阁洞府、十方大荒、百宝纳戒、九霄坊市 + 右侧同场神识抽屉 + 底部敕令台
 */
(function () {
  "use strict";

  // 十方天地经典地标
  const PLACES = [
    { name: "青云坊市客栈", tip: "商会客栈 · 安全庇护", region: "南瞻部洲", isSafe: true },
    { name: "青云宗外门山门", tip: "正道山门 · 灵气温润", region: "青云灵脉", isSafe: true },
    { name: "宗门玄元洞府", tip: "后山静室 · 闭关福地", region: "后山福地", isSafe: true },
    { name: "落霞山灵泉", tip: "凡阶野外 · 灵雾氤氲", region: "落霞荒泽", isSafe: false },
    { name: "万剑仙门峰", tip: "剑气冲霄 · 仙家总坛", region: "中土神州", isSafe: true },
    { name: "黑风绝渊", tip: "大凶死地 · 罡风刺骨", region: "西荒绝壁", isSafe: false },
    { name: "万星古岛", tip: "诸星残阵 · 上古遗迹", region: "东海尽头", isSafe: false },
    { name: "洗剑池洞天", tip: "剑池淬锋 · 幽静洞天", region: "剑峰深处", isSafe: true },
    { name: "九幽天魔宗坛", tip: "九幽煞泉 · 魔道凶穴", region: "幽冥地府", isSafe: false },
  ];

  // 十方大荒四大秘境画卷
  const WILDERNESS_REALMS = [
    {
      name: "落霞山灵泉",
      title: "落霞灵泉 · 凡阶秘境",
      tierName: "凡阶 · 适宜练气与筑基",
      tagClass: "low",
      desc: "水雾氤氲，生有百年水灵芝与地底阴火凝晶，乃初踏仙途探索之上佳宝地。",
      spiritRate: "灵气充裕 · 凶险度低",
      cost: "探险盘缠 20 灵石",
      location: "落霞山灵泉",
    },
    {
      name: "黑风绝渊",
      title: "黑风绝渊 · 险阶秘境",
      tierName: "险阶 · 适宜结丹与元婴",
      tagClass: "mid",
      desc: "九天罡风割体，深渊下埋葬前朝万剑冢与嗜血妖兽，常生破煞玄金。",
      spiritRate: "煞气弥漫 · 凶险度中",
      cost: "探险盘缠 50 灵石",
      location: "黑风绝渊",
    },
    {
      name: "万星古岛",
      title: "万星古岛 · 地阶秘境",
      tierName: "地阶 · 适宜化神与炼虚",
      tagClass: "danger",
      desc: "上古星辰崩碎垂落之残岛，密布诸星杀阵与天工残卷，藏有五行天机。",
      spiritRate: "星辰灵流 · 凶险度高",
      cost: "探险盘缠 100 灵石",
      location: "万星古岛",
    },
    {
      name: "九幽天魔宗坛",
      title: "幽冥天渊 · 天阶秘境",
      tierName: "天阶 · 适宜合体与大乘",
      tagClass: "danger",
      desc: "九幽煞泉倒灌，魔道上古巨擘封禁之所。因果纠缠，非大神通者涉足即陨。",
      spiritRate: "幽冥玄煞 · 极度凶险",
      cost: "探险盘缠 200 灵石",
      location: "九幽天魔宗坛",
    },
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
    view: "sanctum", // 'sanctum', 'wilderness', 'inventory', 'bazaar'
    status: null,
    here: [],
    feed: [],
    world: null,
    commands: [],
    filter: "",
    busy: false,
    offline: false,
    demo: false,
    chat: { open: false, npc: "", lines: [] },
    sug: [],
    sugI: 0,
    drawerOpen: false,
    drawerTab: "cultivators", // 'cultivators' or 'teleport'
    // 百宝纳戒
    bagFilter: "all",
    selectedItemIndex: 0,
    inventory: [],
    equipped: [],
    // 坊市货单
    marketListings: [],
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
  }

  async function api(path, body) {
    let base = (state.base || "").trim().replace(/\/$/, "");
    if (base && !/^https?:\/\//i.test(base)) base = "http://" + base;
    const url = base + path;
    const opts = {
      method: body ? "POST" : "GET",
      credentials: "omit",
      cache: "no-store",
    };
    if (body) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      setOffline(true);
      throw new Error("无法感应阵枢灵脉（请确认服务已启动）");
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

  function busy(on, label) {
    state.busy = !!on;
    const go = $("cmdGo");
    const send = $("chatSend");
    if (go) {
      go.disabled = !!on;
      go.textContent = on ? "…" : "敕令疾行";
    }
    if (send) {
      send.disabled = !!on;
      send.textContent = on ? "…" : "传音";
    }
    const dot = $("busyDot");
    if (dot) dot.style.display = on ? "inline-block" : "none";
    const chatDot = $("chatBusy");
    if (chatDot) chatDot.style.display = on ? "inline-block" : "none";
    if (on && label) toast(label, "gold");
  }

  // ---------- 状态同步 ----------
  function applyStatus(st) {
    if (!st) return;
    state.status = Object.assign({}, state.status || {}, st);
    const s = state.status;

    // 顶部天道盘
    setText("topDaoName", s.name || state.name || "—");
    setText("topDaoRealm", (s.realm || "—") + (s.rank && s.rank !== "散修" ? " · " + s.rank : ""));
    setText("topStones", (s.stones != null ? s.stones : 0) + " 灵石");
    setText("topLocation", s.location || "—");
    setText("topHereCount", (state.here.length || 0) + " 位同道");

    const drawerSub = $("drawerLocSub");
    if (drawerSub) {
      drawerSub.textContent = `所在：${s.location || "—"} · 周遭同道 ${state.here.length || 0} 人`;
    }

    renderBody();
  }

  function pulseWorld() {
    renderBody();
  }

  function pushFeed(text, kind) {
    if (!text) return;
    state.feed.push({ text: String(text), kind: kind || kindOf(text), ts: Date.now() / 1000 });
    if (state.feed.length > 200) state.feed = state.feed.slice(-200);
    if (state.view === "sanctum" || state.view === "wilderness") {
      renderBody();
    }
  }

  function kindOf(text) {
    const t = String(text || "");
    if (/^»/.test(t)) return "cmd";
    if (/失败|错误|拒绝|不可|中断|身死|陨落/.test(t)) return "bad";
    if (/天道|世界弧|异象|大劫|血煞|机缘/.test(t)) return "ai";
    return "ok";
  }

  // ---------- 视图切换 ----------
  function setView(v) {
    const valid = ["sanctum", "wilderness", "inventory", "bazaar"];
    if (!valid.includes(v)) v = "sanctum";
    state.view = v;
    document.querySelectorAll(".nav-tab[data-view]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-view") === v);
    });
    renderBody();
  }

  function renderBody() {
    const host = $("stageContent");
    if (!host) return;
    if (state.view === "sanctum") host.innerHTML = renderSanctum();
    else if (state.view === "wilderness") host.innerHTML = renderWilderness();
    else if (state.view === "inventory") host.innerHTML = renderInventory();
    else if (state.view === "bazaar") host.innerHTML = renderBazaar();
  }

  // ==========================================================================
  // 主境一：【玄阁洞府】 (Sanctum)
  // ==========================================================================
  function renderSanctum() {
    const s = state.status || {
      name: state.name || "散修道人",
      realm: "练气期",
      sect: "散修",
      rank: "散修",
      exp: "60/100",
      rem_years: 92,
      sin: 0,
      merit: 20,
      stones: 100,
      vault: 0,
      root: "五行杂灵根",
      blood_marked: false,
      meditating: false,
    };

    const isMed = !!(s.meditating || s.status === "MEDITATING");
    const expParts = String(s.exp || "0/100").split("/");
    const expCur = parseFloat(expParts[0]) || 0;
    const expMax = parseFloat(expParts[1]) || 100;
    const expPct = Math.min(100, Math.max(0, (expCur / expMax) * 100));

    const feedItems = (state.feed || [])
      .slice(-6)
      .reverse()
      .map((f) => {
        const d = new Date(f.ts * 1000);
        const timeStr = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
        const cls = f.kind === "ai" ? "feed-ai" : f.kind === "bad" ? "feed-bad" : f.kind === "cmd" ? "feed-cmd" : "";
        return `<div class="feed-item ${cls}">
          <span class="feed-text">${esc(f.text)}</span>
          <span class="feed-time">${timeStr}</span>
        </div>`;
      })
      .join("") || `<div style="font-size:12px;color:var(--ink-400);padding:8px">暂无天道因果流转。</div>`;

    return `
    <div class="sanctum-grid">
      <!-- 左栏：道身真影与根本气机 -->
      <div class="jade-card gold-rim avatar-card">
        <div class="avatar-frame">
          <span>${esc((s.name || "道").slice(0, 1))}</span>
        </div>
        <div class="dao-name">${esc(s.name || "道友")}</div>
        <div class="dao-realm">${esc(s.realm || "练气期")} · ${esc(s.sect || "散修")}${s.rank && s.rank !== "散修" ? " · " + esc(s.rank) : ""}</div>
        <div style="font-size:11px;color:var(--gold-600);margin-bottom:14px">灵根禀赋：${esc(s.root || "五行混元灵根")}</div>

        <div class="stat-bar-group">
          <div class="stat-row">
            <span>寿元气数</span>
            <span style="font-weight:600;color:var(--jade-700)">约 ${Number(s.rem_years || 0).toFixed(0)} 岁</span>
          </div>
          <div class="stat-row">
            <span>修为进境</span>
            <span style="font-weight:600;color:var(--gold-600)">${esc(s.exp || "0/100")}</span>
          </div>
          <div class="stat-progress">
            <div class="stat-progress-fill" style="width:${expPct}%"></div>
          </div>
          <div class="stat-row" style="margin-top:6px">
            <span>因果功过</span>
            <span>业力 ${s.sin || 0} / 功德 ${s.merit || 0}</span>
          </div>
          <div class="stat-row">
            <span>道身清浊</span>
            <span style="color:${s.blood_marked ? "var(--blood-500)" : "var(--jade-700)"}">${s.blood_marked ? "血煞缠身" : "正道清虚"}</span>
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:8px;margin-top:16px">
          <button type="button" class="btn primary block" data-cmd="/闭关 1">${isMed ? "深层吐纳中" : "入定闭关吐纳"}</button>
          <button type="button" class="btn secondary block" data-cmd="/突破">引雷渡劫破境</button>
          <button type="button" class="btn ghost block" data-cmd="/look">观照自身道身</button>
        </div>
      </div>

      <!-- 右栏：洞府静室与因果纪事 -->
      <div style="display:flex;flex-direction:column;gap:20px">
        <div class="sanctum-subrooms">
          <!-- 静室蒲团 -->
          <div class="room-card">
            <h4>静室蒲团</h4>
            <p>避绝尘世喧嚣，锁门行周天大循环。当前：${isMed ? "闭关入定中" : "神完气足，行止自由"}</p>
            <div style="display:flex;gap:8px">
              <button type="button" class="btn sm primary" data-cmd="/闭关 1">闭关一刻</button>
              <button type="button" class="btn sm secondary" data-cmd="/出关">收功出关</button>
            </div>
          </div>

          <!-- 乾坤金库 -->
          <div class="room-card">
            <h4>乾坤金库</h4>
            <p>随身备：${s.stones || 0} 灵石 | 金库储：${s.vault || 0} 灵石（大阵庇护不可掠夺）</p>
            <div style="display:flex;gap:8px">
              <button type="button" class="btn sm primary" data-cmd="/寄存 100">存入百石</button>
              <button type="button" class="btn sm secondary" data-cmd="/支取 100">支取百石</button>
            </div>
          </div>

          <!-- 丹房药鼎 -->
          <div class="room-card">
            <h4>丹房药鼎</h4>
            <p>采集天地灵萃，凝聚九转神丹。药力：${s.pill_exp_mult ? "丹效蕴体" : "炉火纯青"}</p>
            <div style="display:flex;gap:8px">
              <button type="button" class="btn sm secondary" data-cmd="/帮助 丹药">研读丹经</button>
              <button type="button" class="btn sm ghost" data-cmd="/服用 聚气丹">纳气服丹</button>
            </div>
          </div>

          <!-- 炼器神台 -->
          <div class="room-card">
            <h4>炼器神台</h4>
            <p>淬炼法宝灵胚，洗练随机词缀。法宝加持自身战力与天地契合度。</p>
            <div style="display:flex;gap:8px">
              <button type="button" class="btn sm primary" data-act="view:inventory">纳戒宝物</button>
              <button type="button" class="btn sm secondary" data-cmd="/帮助 穿戴">祭炼法门</button>
            </div>
          </div>
        </div>

        <!-- 仙途行止 · 天道因果日志 -->
        <div class="jade-card">
          <div class="card-head">
            <h3>仙途行止 · 因果纪事</h3>
            <div style="display:flex;gap:6px">
              <button type="button" class="btn sm ghost" data-cmd="/任务">修行指引</button>
              <button type="button" class="btn sm ghost" data-cmd="/世情">观照世情</button>
            </div>
          </div>
          <div class="feed-box">
            ${feedItems}
          </div>
        </div>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 主境二：【十方大荒 · 秘境探险图卷】 (Wilderness)
  // ==========================================================================
  function renderWilderness() {
    const curLoc = (state.status && state.status.location) || "青云坊市客栈";
    const ev = (state.world && state.world.evolution) || {};
    const d = ev.director || {};
    const hasDirectorEvents = (d.active || []).length > 0;
    const bannerNarrative = hasDirectorEvents
      ? (d.active[0].narrative || d.active[0].title || "天地煞气浮动")
      : "世间气机平稳祥和，正逢仙家修士探幽求索之良辰。";

    const realmCards = WILDERNESS_REALMS.map((r) => {
      const isHere = curLoc === r.location;
      return `
      <div class="realm-card">
        <span class="realm-tag ${r.tagClass}">${r.tierName}</span>
        <div>
          <div class="realm-title">${esc(r.title)}</div>
          <div class="realm-desc">${esc(r.desc)}</div>
        </div>
        <div>
          <div class="realm-stats">
            <span>${esc(r.spiritRate)}</span>
            <span style="color:var(--gold-600);font-weight:600">${esc(r.cost)}</span>
          </div>
          <div style="display:flex;gap:8px;margin-top:10px">
            <button type="button" class="btn sm secondary" data-cmd="/望气">神识望气</button>
            ${
              isHere
                ? `<button type="button" class="btn sm primary block" data-cmd="/探险 ${esc(r.name)}">踏入探索</button>`
                : `<button type="button" class="btn sm ghost block" data-go="${esc(r.location)}">御剑前往</button>`
            }
          </div>
        </div>
      </div>`;
    }).join("");

    return `
    <div style="display:flex;flex-direction:column;gap:18px">
      <!-- 天地异象横幅：世界疤痕 -->
      <div class="world-scar-banner">
        <div class="scar-left">
          <span class="scar-badge">异象示现</span>
          <span class="scar-text">【天地疤痕 · 煞气警示】${esc(bannerNarrative)}</span>
        </div>
        <button type="button" class="btn sm ghost" data-cmd="/天道">天道导演</button>
      </div>

      <!-- 大荒探险契印与保底金印 -->
      <div class="guarantee-box">
        <div class="guarantee-left">
          <div class="guarantee-seal">保</div>
          <div>
            <div class="guarantee-title">天道探险气运金印 · 必得造化</div>
            <div style="font-size:12px;color:var(--ink-500)">外出历练随身备足 20 灵石作为盘缠，初探秘境必得天道气运保底，可获法宝或奇珍灵物。</div>
          </div>
        </div>
        <button type="button" class="btn sm gold" data-cmd="/探险">备足盘缠 · 探秘</button>
      </div>

      <!-- 四大秘境图卷网格 -->
      <div class="realms-grid">
        ${realmCards}
      </div>

      <!-- 历练指引与因果 -->
      <div class="jade-card">
        <div class="card-head">
          <h3>大荒行止 · 探索实录</h3>
          <button type="button" class="btn sm ghost" data-cmd="/秘境">秘境天机榜</button>
        </div>
        <div style="font-size:13px;color:var(--ink-700);line-height:1.6">
          大千大荒，无奇不有。秘境之中暗藏五行杀劫与古修遗府；若身怀实体藏宝图，更可依循干支卦象定点挖掘。<br />
          当前位置：<strong>【${esc(curLoc)}】</strong>。若遇凶险，可随时引动神识敕令使用遁符避祸。
        </div>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 主境三：【百宝纳戒 · 灵物宝匣与天机藏图】 (Inventory)
  // ==========================================================================
  function ensureDefaultInventory() {
    if (state.inventory && state.inventory.length > 0) return;
    state.inventory = [
      {
        uid: "item_sword_01",
        name: "斩煞青锋剑",
        kind: "equip",
        slot: "weapon",
        slotCn: "法宝器灵",
        tier: 3,
        tierName: "地品",
        stats: { "攻伐威能": 160, "破甲穿透": 45 },
        affixes: [
          { name: "破煞", desc: "对附带煞气之邪修及妖兽伤害提升 35%" },
          { name: "嗜血", desc: "击中掠取生机，反哺自身气血 12 点" },
        ],
        durability: "92 / 100",
        lore: "前代剑修于黑风绝渊斩杀骨魔后以心头血淬炼，剑身隐现幽青流芒。",
        icon: "⚔️",
      },
      {
        uid: "item_robe_01",
        name: "玄水避火道袍",
        kind: "equip",
        slot: "armor",
        slotCn: "防身宝衣",
        tier: 2,
        tierName: "人品",
        stats: { "护身甲御": 90, "避火抗性": 50 },
        affixes: [
          { name: "固元", desc: "周天元气稳固，受击气血折损减免 20%" },
        ],
        durability: "100 / 100",
        lore: "以北海灵鲛之丝织就，水火不侵，纤尘不染。",
        icon: "🥋",
      },
      {
        uid: "item_jade_01",
        name: "天机寻龙古玉",
        kind: "equip",
        slot: "trinket",
        slotCn: "本命灵佩",
        tier: 4,
        tierName: "天品",
        stats: { "神识念力": 120, "回气速度": 25 },
        affixes: [
          { name: "凝神", desc: "神识感应范围扩张一倍，打坐吐纳效率提升 30%" },
        ],
        durability: "88 / 100",
        lore: "蕴含太虚星象天演之术，佩于腰间常闻灵泉叮咚之仙音。",
        icon: "📿",
      },
      {
        uid: "item_map_01",
        name: "天机密卷 · 坎水藏宝图",
        kind: "treasure_map",
        slotCn: "天机秘宝图卷",
        tier: 3,
        tierName: "地品",
        targetNodeName: "落霞山灵泉",
        archetypeCn: "坎水五行破阵",
        coords: "甲子方位 · 震木宫 东南二十里 地脉三丈",
        riddle: "五行倒悬，阴阳同炉。阵眼匿于【落霞山灵泉】灵穴最深处，非晓坎水生克之道者不可启。",
        lore: "此图自落霞风水脉络截取而出，纸帛泛黄，微透赤金水墨，记载前朝真仙遗府所在。",
        icon: "🗺️",
      },
      {
        uid: "item_pill_01",
        name: "九转还阳丹",
        kind: "pill",
        slotCn: "救命神丹",
        tier: 2,
        tierName: "人品",
        stats: { "延寿增气": 3 },
        affixes: [
          { name: "生肌", desc: "生死肉白骨，濒危坐化时可凭空添续寿元三年。" },
        ],
        lore: "采七七四十九味地脉灵芝，于八卦炉中文火慢煨百日方成。",
        icon: "💊",
      },
      {
        uid: "item_mat_01",
        name: "太乙精金矿胚",
        kind: "material",
        slotCn: "炼器神材",
        tier: 1,
        tierName: "凡品",
        stats: { "重铸精纯": 15 },
        lore: "深埋地脉万载的精金矿胚，重铸法宝洗练破煞词缀之必备神材。",
        icon: "💎",
      },
    ];
  }

  function renderInventory() {
    ensureDefaultInventory();
    const inv = state.inventory;
    const filter = state.bagFilter;

    const filtered = inv.filter((it) => {
      if (filter === "all") return true;
      if (filter === "equip") return it.kind === "equip";
      if (filter === "pill") return it.kind === "pill";
      if (filter === "material") return it.kind === "material";
      if (filter === "treasure_map") return it.kind === "treasure_map";
      return true;
    });

    const activeIndex = Math.min(state.selectedItemIndex, Math.max(0, filtered.length - 1));
    const sel = filtered[activeIndex] || filtered[0] || inv[0];

    // 三大本命佩戴槽
    const weaponEquip = inv.find((x) => x.slot === "weapon") || { name: "空置法宝", tierName: "凡品", affixes: [] };
    const armorEquip = inv.find((x) => x.slot === "armor") || { name: "空置法衣", tierName: "凡品", affixes: [] };
    const trinketEquip = inv.find((x) => x.slot === "trinket") || { name: "空置灵佩", tierName: "凡品", affixes: [] };

    const bagCells = filtered.map((it, idx) => {
      const isSel = it === sel;
      const tName = it.tierName ? it.tierName.slice(0, 1) : "凡";
      return `
      <div class="bag-cell ${isSel ? "selected" : ""}" data-bag-idx="${idx}" title="${esc(it.name)}">
        <span class="cell-badge">${tName}</span>
        <div class="cell-icon">${it.icon || "📦"}</div>
        <div class="cell-name">${esc(it.name)}</div>
      </div>`;
    }).join("");

    // 右侧万象灵宝鉴真录
    let inspectorHtml = "";
    if (sel && sel.kind === "treasure_map") {
      inspectorHtml = `
      <div class="inspector-seal-title">${esc(sel.name)}</div>
      <div class="inspector-tier">${esc(sel.tierName || "地品")} · ${esc(sel.slotCn || "天机藏宝图卷")}</div>
      
      <div class="map-parchment">
        <h5>天机谶语</h5>
        <p>${esc(sel.riddle || "天机幽微，机缘隐现于世间。")}</p>
        <div style="margin-top:10px;font-size:11px;color:#7a2020;line-height:1.6">
          <div><strong>地脉节点：</strong>${esc(sel.targetNodeName || "未定凶地")}</div>
          <div><strong>风水卦象：</strong>${esc(sel.coords || "甲子方位 · 地脉三丈")}</div>
          <div><strong>生克阵眼：</strong>${esc(sel.archetypeCn || "五行生克")}</div>
        </div>
      </div>

      <div style="font-size:12px;color:var(--ink-500);margin-bottom:16px">
        古籍考据：${esc(sel.lore || "此图残破，年代久远。")}
      </div>

      <div style="display:flex;flex-direction:column;gap:8px">
        <button type="button" class="btn primary block gold" data-cmd="/挖宝">循图挖宝 · 开启机缘</button>
        <button type="button" class="btn secondary block" data-cmd="/宝图 ${esc(sel.name)}">研读推演天机</button>
      </div>`;
    } else if (sel) {
      const statsRows = Object.entries(sel.stats || {}).map(([k, v]) => `
        <div class="affix-row">
          <span class="affix-name">${esc(k)}</span>
          <span class="affix-val">+${v}</span>
        </div>
      `).join("");

      const affixesRows = (sel.affixes || []).map((a) => `
        <div class="affix-row">
          <span class="affix-name">【${esc(a.name)}】</span>
          <span class="affix-val">${esc(a.desc)}</span>
        </div>
      `).join("");

      inspectorHtml = `
      <div class="inspector-seal-title">${esc(sel.name)}</div>
      <div class="inspector-tier">${esc(sel.tierName || "凡品")} · ${esc(sel.slotCn || "仙道灵宝")}</div>

      ${statsRows ? `<div class="inspector-affixes">${statsRows}</div>` : ""}
      ${affixesRows ? `<div class="inspector-affixes">${affixesRows}</div>` : ""}

      ${sel.durability ? `<div style="font-size:12px;color:var(--ink-500);margin-bottom:12px">耐久威能：${sel.durability}</div>` : ""}
      ${sel.lore ? `<div style="font-size:12px;color:var(--ink-500);margin-bottom:16px">古籍载：${esc(sel.lore)}</div>` : ""}

      <div style="display:flex;flex-direction:column;gap:8px">
        ${sel.kind === "equip" ? `<button type="button" class="btn primary block" data-cmd="/穿戴 ${esc(sel.name)}">佩戴入体</button>` : ""}
        ${sel.kind === "pill" ? `<button type="button" class="btn primary block" data-cmd="/服用 ${esc(sel.name)}">纳气服丹</button>` : ""}
        <button type="button" class="btn secondary block" data-act="sell:${esc(sel.name)}">挂牌寄售到坊市</button>
        <button type="button" class="btn ghost block" data-cmd="/出售 ${esc(sel.name)} 1">回售仙盟商会</button>
      </div>`;
    } else {
      inspectorHtml = `<div style="padding:24px 0;text-align:center;color:var(--ink-400)">纳戒空空如也。</div>`;
    }

    return `
    <div class="inventory-layout">
      <!-- 左栏：本命佩戴三槽 -->
      <div class="jade-card">
        <div class="card-head">
          <h3>本命三槽</h3>
          <span class="card-tag">道体佩戴</span>
        </div>
        <div class="relic-slots">
          <div class="relic-slot">
            <div class="slot-oct-box">⚔️</div>
            <div class="slot-meta" style="flex:1">
              <h4>${esc(weaponEquip.name)}</h4>
              <div class="affix-pill">${esc((weaponEquip.affixes && weaponEquip.affixes[0] && weaponEquip.affixes[0].name) || "主战法宝")}</div>
            </div>
            ${weaponEquip.name !== "空置法宝" ? `<button type="button" class="btn sm ghost" data-cmd="/卸下 ${esc(weaponEquip.name)}">卸下</button>` : ""}
          </div>

          <div class="relic-slot">
            <div class="slot-oct-box">🥋</div>
            <div class="slot-meta" style="flex:1">
              <h4>${esc(armorEquip.name)}</h4>
              <div class="affix-pill">${esc((armorEquip.affixes && armorEquip.affixes[0] && armorEquip.affixes[0].name) || "防身宝衣")}</div>
            </div>
            ${armorEquip.name !== "空置法衣" ? `<button type="button" class="btn sm ghost" data-cmd="/卸下 ${esc(armorEquip.name)}">卸下</button>` : ""}
          </div>

          <div class="relic-slot">
            <div class="slot-oct-box">📿</div>
            <div class="slot-meta" style="flex:1">
              <h4>${esc(trinketEquip.name)}</h4>
              <div class="affix-pill">${esc((trinketEquip.affixes && trinketEquip.affixes[0] && trinketEquip.affixes[0].name) || "本命灵佩")}</div>
            </div>
            ${trinketEquip.name !== "空置灵佩" ? `<button type="button" class="btn sm ghost" data-cmd="/卸下 ${esc(trinketEquip.name)}">卸下</button>` : ""}
          </div>
        </div>
      </div>

      <!-- 中栏：芥子空间百宝格 -->
      <div class="jade-card bag-grid-wrap">
        <div class="bag-filter-bar">
          <div class="bag-tabs">
            <button type="button" class="btn sm ${filter === "all" ? "primary" : "ghost"}" data-bag-filter="all">全部</button>
            <button type="button" class="btn sm ${filter === "equip" ? "primary" : "ghost"}" data-bag-filter="equip">法宝</button>
            <button type="button" class="btn sm ${filter === "pill" ? "primary" : "ghost"}" data-bag-filter="pill">丹药</button>
            <button type="button" class="btn sm ${filter === "material" ? "primary" : "ghost"}" data-bag-filter="material">灵材</button>
            <button type="button" class="btn sm ${filter === "treasure_map" ? "primary" : "ghost"}" data-bag-filter="treasure_map">藏宝天机</button>
          </div>
          <span style="font-size:12px;color:var(--ink-400)">容纳：${filtered.length} 件</span>
        </div>

        <div class="bag-grid">
          ${bagCells}
        </div>
      </div>

      <!-- 右栏：万象灵宝鉴真录 -->
      <div class="jade-card gold-rim inspector-card">
        <div class="card-head">
          <h3>鉴真台</h3>
          <span class="card-tag">天道玄鉴</span>
        </div>
        ${inspectorHtml}
      </div>
    </div>`;
  }

  // ==========================================================================
  // 主境四：【九霄坊市 · 乾坤寄售与百家摊集】 (Bazaar)
  // ==========================================================================
  function ensureDefaultMarket() {
    if (state.marketListings && state.marketListings.length > 0) return;
    state.marketListings = [
      { id: 1, name: "赤血断岳刀", tier: "地品", affixes: "嗜血·破甲", seller: "万毒老祖", price: 680, tax: 34 },
      { id: 2, name: "紫霄定雷玉符", tier: "天品", affixes: "避雷·辟邪", seller: "青云真人", price: 1200, tax: 60 },
      { id: 3, name: "九转回春聚气丹", tier: "人品", affixes: "培元", seller: "百草散人", price: 150, tax: 8 },
      { id: 4, name: "天工玄木残卷", tier: "凡品", affixes: "铸纹", seller: "墨家传人", price: 80, tax: 4 },
    ];
  }

  function renderBazaar() {
    ensureDefaultMarket();
    const listings = state.marketListings;
    const s = state.status || { stones: 100, vault: 0 };

    const rows = listings.map((it, idx) => `
      <tr>
        <td style="font-weight:600;color:var(--jade-700)">${esc(it.name)}</td>
        <td><span class="card-tag">${esc(it.tier)}</span></td>
        <td style="color:var(--gold-600);font-size:12px">${esc(it.affixes)}</td>
        <td>${esc(it.seller)}</td>
        <td style="font-weight:600;color:var(--gold-600)">${it.price} 灵石</td>
        <td style="color:var(--ink-400);font-size:11px">${it.tax} 石</td>
        <td>
          <button type="button" class="btn sm primary" data-cmd="/买寄售 ${it.id || idx + 1}">买下</button>
        </td>
      </tr>
    `).join("");

    return `
    <div style="display:flex;flex-direction:column;gap:18px">
      <!-- 坊市商律告示横幅 -->
      <div class="bazaar-header-tip">
        <div>
          <strong>【天道商盟敕律】</strong> 凡诸天修士寄售交易，一律抽取 5% 契税充实仙盟府库，童叟无欺，因果自担。
        </div>
        <button type="button" class="btn sm ghost" data-cmd="/坊市">刷新货单</button>
      </div>

      <div class="bazaar-grid">
        <!-- 左侧：诸天寄售行卷 -->
        <div class="jade-card">
          <div class="card-head">
            <h3>诸天寄售行卷</h3>
            <span class="card-tag">全界流转</span>
          </div>
          <table class="listing-table">
            <thead>
              <tr>
                <th>灵宝法物</th>
                <th>品阶</th>
                <th>词缀精粹</th>
                <th>物主道号</th>
                <th>标价</th>
                <th>契税(5%)</th>
                <th>商行买卖</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>

        <!-- 右侧：个人摆摊灵坛与金库储蓄 -->
        <div style="display:flex;flex-direction:column;gap:20px">
          <!-- 个人货摊 -->
          <div class="stall-box">
            <div class="card-head">
              <h3>个人摆摊灵坛</h3>
              <span class="card-tag">我的货摊</span>
            </div>
            <p style="font-size:12px;color:var(--ink-500);margin-bottom:14px">
              闲置法宝丹药可直接挂牌寄售，售出后灵石将自动划入金库。
            </p>
            <div style="display:flex;flex-direction:column;gap:8px">
              <button type="button" class="btn primary block" data-act="focus-cmd:/寄售 ">挂牌寄售法物</button>
              <button type="button" class="btn secondary block" data-cmd="/撤单 1">撤回货位摊位</button>
            </div>
          </div>

          <!-- 坊市金库柜台 -->
          <div class="jade-card">
            <div class="card-head">
              <h3>金库兑换柜台</h3>
              <span class="card-tag">安全储蓄</span>
            </div>
            <div style="font-size:13px;color:var(--ink-700);margin-bottom:12px">
              <div>随身携带：<strong>${s.stones || 0}</strong> 灵石（可用于交易、历练盘缠）</div>
              <div>金库储蓄：<strong>${s.vault || 0}</strong> 灵石（大阵庇护，斗法不可被掠）</div>
            </div>
            <div style="display:flex;gap:8px">
              <button type="button" class="btn sm primary block" data-cmd="/寄存 100">存入百石</button>
              <button type="button" class="btn sm secondary block" data-cmd="/支取 100">支取百石</button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 右侧滑入式神识浮匣 (Side Drawer)
  // ==========================================================================
  function setDrawerTab(tab) {
    state.drawerTab = tab;
    $("tabCultivators") && $("tabCultivators").classList.toggle("active", tab === "cultivators");
    $("tabTeleport") && $("tabTeleport").classList.toggle("active", tab === "teleport");
    renderSideDrawer();
  }

  function openSideDrawer() {
    state.drawerOpen = true;
    $("sideDrawer") && $("sideDrawer").classList.add("open");
    $("drawerBackdrop") && $("drawerBackdrop").classList.add("open");
    renderSideDrawer();
  }

  function closeSideDrawer() {
    state.drawerOpen = false;
    $("sideDrawer") && $("sideDrawer").classList.remove("open");
    $("drawerBackdrop") && $("drawerBackdrop").classList.remove("open");
  }

  function renderSideDrawer() {
    const box = $("drawerBody");
    if (!box) return;

    if (state.drawerTab === "teleport") {
      const cur = (state.status && state.status.location) || "";
      box.innerHTML = PLACES.map((p) => {
        const isCur = p.name === cur;
        return `
        <div class="place-card ${isCur ? "current" : ""}" data-go="${esc(p.name)}">
          <div>
            <div class="place-name">${esc(p.name)} ${isCur ? "· 当前所在" : ""}</div>
            <div class="place-tip">${esc(p.tip)}</div>
          </div>
          <button type="button" class="btn sm ${isCur ? "ghost" : "primary"}">${isCur ? "已至" : "迁跃"}</button>
        </div>`;
      }).join("");
      return;
    }

    // 周遭同道列表
    const rows = state.here || [];
    if (!rows.length) {
      box.innerHTML = `
      <div style="padding:40px 10px;text-align:center;color:var(--ink-400)">
        <div style="font-size:24px;margin-bottom:8px">🍃</div>
        <div>周遭方圆暂无其他修士。</div>
        <div style="font-size:12px;margin-top:6px">可切到「十方迁跃」前往客栈或宗门。</div>
      </div>`;
      return;
    }

    box.innerHTML = rows.map((r) => {
      const isBlood = !!r.blood_marked;
      const att = r.attitude_cn || (r.is_npc ? "中立" : "道友");
      return `
      <div class="cultivator-item ${isBlood ? "danger-red" : ""}">
        <div class="cultivator-row">
          <div>
            <span class="cultivator-name">${esc(r.name)}</span>
            <span style="font-size:12px;color:var(--ink-500);margin-left:6px">${esc(r.realm || "")}</span>
          </div>
          <span class="card-tag ${isBlood ? "danger" : ""}">${isBlood ? "血煞通缉" : att}</span>
        </div>
        <div style="font-size:11px;color:var(--ink-500)">
          ${esc(r.sect || "散修")}${r.rank ? " · " + esc(r.rank) : ""} · 秉性：${esc(r.personality || "行止难测")}
        </div>
        <div class="cultivator-actions">
          <button type="button" class="btn sm primary" data-person="${esc(r.name)}">神识传音</button>
          <button type="button" class="btn sm secondary" data-cmd="/交易 ${esc(r.name)}">互市交易</button>
          <button type="button" class="btn sm ghost" data-cmd="/斗法 ${esc(r.name)}">当面切磋</button>
        </div>
      </div>`;
    }).join("");
  }

  // ==========================================================================
  // 神识交谈玉简 (Chat Jade Modal)
  // ==========================================================================
  function openChat(name) {
    state.chat.open = true;
    if (name) state.chat.npc = name;
    const who = state.chat.npc || "同道";
    setText("chatTitle", "神识交谈 · " + who);
    setText("cmdTarget", "交谈对象：" + who);
    setText("cmdTag", "言语传音");

    const modal = $("chatModal");
    if (modal) {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    }
    if (!state.chat.lines.length) {
      state.chat.lines = [{ cls: "sys", text: `已与【${who}】连通神识，在下方直接开口传音。` }];
    }
    renderChat(true);
    const inp = $("chatInput");
    if (inp) {
      inp.disabled = false;
      setTimeout(() => { try { inp.focus(); } catch (_) {} }, 60);
    }
  }

  function closeChat(hangup) {
    state.chat.open = false;
    state.chat.npc = "";
    setText("cmdTarget", "未锁定同道");
    setText("cmdTag", "神识敕令");

    const modal = $("chatModal");
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }

    if (hangup && !state.demo && state.token) {
      api("/action", { token: state.token, command: "/挂断" }).catch(() => {});
    }
  }

  function chatMsg(who, text, cls) {
    state.chat.lines.push({ who, text, cls: cls || "npc" });
    if (state.chat.lines.length > 120) state.chat.lines = state.chat.lines.slice(-120);
    renderChat(true);
  }

  function renderChat(scroll) {
    const log = $("chatLog");
    if (!log) return;
    log.innerHTML = (state.chat.lines || []).map((l) => {
      if (l.cls === "sys") return `<div class="msg sys">${esc(l.text)}</div>`;
      return `<div class="msg ${esc(l.cls)}">
        <span class="who">${esc(l.who || "")}</span>
        ${esc(l.text)}
      </div>`;
    }).join("");
    if (scroll) log.scrollTop = log.scrollHeight;
  }

  async function sendChat(text) {
    const c = (text || "").trim();
    if (!c || state.busy) return;
    chatMsg("你", c, "me");

    if (state.demo) {
      setTimeout(() => {
        chatMsg(state.chat.npc || "同道", "（玄黄镜演）道友所言甚合吾意，接通大世界后可真实结算因果。", "npc");
      }, 500);
      return;
    }

    busy(true, "对方神识思量中…");
    chatMsg("", "（对方神识沉吟中…）", "sys");
    try {
      const data = await api("/chat", {
        token: state.token,
        text: c,
        to: state.chat.npc || undefined,
      });
      state.chat.lines = (state.chat.lines || []).filter((l) => !(l.cls === "sys" && l.text.includes("沉吟中")));
      handleChatData(data);
    } catch (e) {
      state.chat.lines = (state.chat.lines || []).filter((l) => !(l.cls === "sys" && l.text.includes("沉吟中")));
      renderChat(true);
      chatMsg("", "传音受阻：" + e.message, "sys");
      toast(e.message, "bad");
    } finally {
      busy(false);
      const inp = $("chatInput");
      if (inp && state.chat.open) inp.focus();
    }
  }

  function handleChatData(data) {
    if (!data) return;
    if (data.status) applyStatus(data.status);
    const text = data.text || data.error || "";
    if (data.ok === false) {
      chatMsg("", text || "传音未送达", "sys");
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
      chatMsg("", text || "神识联通已断开", "sys");
      pushFeed(text);
    }
  }

  // ==========================================================================
  // 底部神识敕令台 (Divine Sense Console)
  // ==========================================================================
  async function sendCmd(cmd) {
    const c = (cmd || "").trim();
    if (!c || state.busy) return;

    if (state.chat.open && !c.startsWith("/")) {
      sendChat(c);
      return;
    }

    busy(true, "天道裁决中…");
    try {
      pushFeed("» " + c, "cmd");
      let data;
      if (state.demo) {
        data = demoResult(c);
      } else {
        data = await api("/action", { token: state.token, command: c });
      }

      if (data.status) applyStatus(data.status);
      if (data.text) pushFeed(data.text, data.ok === false ? "bad" : undefined);
      if (data.chat_open || data.chat_ended) handleChatData(data);
      renderBody();
    } catch (e) {
      pushFeed("敕令失败：" + e.message, "bad");
      toast(e.message, "bad");
    } finally {
      busy(false);
      const inp = $("cmdInput");
      if (inp) inp.value = "";
      hideSug();
    }
  }

  function demoResult(c) {
    if (c.startsWith("/挖宝")) {
      return { ok: true, text: "【玄黄镜演 · 挖宝破阵】你依照天机密卷指引，寻得地脉坎水灵穴，破除阵眼禁制，得获【凡阶地髓灵液】一份！" };
    }
    if (c.startsWith("/探险")) {
      return { ok: true, text: "【玄黄镜演 · 大荒探险】你耗费 20 灵石盘缠，深入落霞密林，天道气运保底垂青，寻得一阶玄阴草两株。" };
    }
    if (c.startsWith("/闭关")) {
      return { ok: true, text: "【玄黄镜演 · 闭关吐纳】洞府大阵锁闭，吞吐周天紫气，修为精进，气血充盈。" };
    }
    return { ok: true, text: `【玄黄镜演】已受命执行敕令：${c}。` };
  }

  // ---------- 指令联想 ----------
  async function loadCommands() {
    if (state.demo) {
      state.commands = [
        { cmd: "/look", usage: "/look", desc: "观照道身状态" },
        { cmd: "/闭关", usage: "/闭关 [小时]", desc: "洞府入定吐纳" },
        { cmd: "/出关", usage: "/出关", desc: "提前收功出关" },
        { cmd: "/突破", usage: "/突破", desc: "引动九天雷劫破境" },
        { cmd: "/探险", usage: "/探险 [秘境名]", desc: "踏入十方大荒历练" },
        { cmd: "/挖宝", usage: "/挖宝", desc: "循实体藏宝图挖掘机缘" },
        { cmd: "/宝图", usage: "/宝图 [图名]", desc: "研读推演藏宝图天机" },
        { cmd: "/穿戴", usage: "/穿戴 <装备名>", desc: "佩戴法宝入体" },
        { cmd: "/卸下", usage: "/卸下 <装备名>", desc: "卸下装备收入纳戒" },
        { cmd: "/坊市", usage: "/坊市", desc: "查看诸天商会与寄售" },
        { cmd: "/寄售", usage: "/寄售 <物品> <价格>", desc: "挂牌寄售仙物" },
        { cmd: "/买寄售", usage: "/买寄售 <编号>", desc: "购买他人寄售灵宝" },
        { cmd: "/寄存", usage: "/寄存 <灵石数>", desc: "灵石存入金库庇护" },
        { cmd: "/支取", usage: "/支取 <灵石数>", desc: "自金库取出灵石" },
        { cmd: "/交谈", usage: "/交谈 <道号>", desc: "与同场修士传音" },
        { cmd: "/做", usage: "/做 <自由言行>", desc: "神识敕令自由行动" },
        { cmd: "/天道", usage: "/天道 [推演]", desc: "观照天道导演与变数" },
        { cmd: "/世情", usage: "/世情", desc: "大千世界全局态势" },
        { cmd: "/任务", usage: "/任务", desc: "初入仙途历练指引" },
        { cmd: "/帮助", usage: "/帮助", desc: "查阅全部天道敕令" },
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
    if (query === "/") return all.slice(0, 10).map((e) => Object.assign({}, e));
    const core = query.replace(/^\//, "");
    const out = [];
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
    return out.slice(0, 8);
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
    el.innerHTML = state.sug.map((it, i) => `
      <div class="suggest-item ${i === 0 ? "active" : ""}" data-sug-i="${i}">
        <span style="font-weight:600;color:var(--jade-700)">${esc(it.cmd)}</span>
        <span style="font-size:11px;color:var(--ink-500)">${esc(it.desc || it.usage || "")}</span>
      </div>
    `).join("");
    el.classList.remove("hidden");
  }

  function applySug(i) {
    const it = state.sug[i];
    if (!it) return;
    const inp = $("cmdInput");
    inp.value = it.cmd + " ";
    hideSug();
    inp.focus();
  }

  function hideSug() {
    const el = $("suggest");
    if (el) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  }

  // ==========================================================================
  // 全局刷新与登录流程
  // ==========================================================================
  async function refreshAll() {
    if (state.demo) {
      renderSideDrawer();
      renderBody();
      return;
    }
    if (!state.token) return;

    try {
      const look = await api("/action", { token: state.token, command: "/look" });
      if (look && look.status) applyStatus(look.status);
    } catch (_) {}

    try {
      const here = await api("/action", { token: state.token, command: "/here" });
      if (here && Array.isArray(here.here)) state.here = here.here;
      setText("topHereCount", (state.here.length || 0) + " 位同道");
    } catch (_) {}

    try {
      const world = await api("/world/director");
      if (world && world.ok !== false) state.world = world;
    } catch (_) {}

    renderSideDrawer();
    renderBody();
  }

  function showApp() {
    $("gate") && $("gate").classList.add("hidden");
    $("app") && $("app").classList.remove("hidden");
  }

  function showGate(msg) {
    $("app") && $("app").classList.add("hidden");
    $("gate") && $("gate").classList.remove("hidden");
    if (msg != null && $("gateMsg")) $("gateMsg").textContent = msg;
  }

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
    if (!username || !password) {
      $("gateMsg").textContent = "请完整填写仙籍账号与神识密匙";
      return;
    }

    const btn = $("gateSubmit");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "灵脉感应中…";

    try {
      const payload = state.mode === "register"
        ? await api("/register", { username, password, name })
        : await api("/login", { username, password, name });

      if (!payload || payload.ok === false) {
        throw new Error((payload && payload.error) || "无法登临大千世界");
      }
      state.token = payload.token;
      state.name = payload.name || name;
      state.user = username;
      state.uid = payload.user_id || "";
      localStorage.setItem("wb.token", state.token);
      localStorage.setItem("wb.user", state.user);
      localStorage.setItem("wb.name", state.name);
      state.demo = false;
      localStorage.removeItem("wb.demo");

      applyStatus({
        name: state.name,
        realm: payload.realm || "练气期",
        location: payload.location || "青云坊市客栈",
        rem_years: payload.rem_years || 85,
        stones: 100,
      });

      showApp();
      toast("已入世 · " + state.name, "ok");
      await loadCommands();
      await refreshAll();
    } catch (err) {
      $("gateMsg").textContent = err.message || "入世受阻";
      toast(err.message, "bad");
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
    $("gateMsg").textContent = "正在感应宗门阵枢 " + server + " …";
    try {
      const r = await fetch(server + "/health");
      const j = await r.json();
      if (j && j.ok) {
        state.base = server;
        localStorage.setItem("wb.base", state.base);
        $("gateMsg").textContent = "宗门阵枢通达灵动：" + server;
      } else {
        $("gateMsg").textContent = "阵枢感应迟滞，请确认灵脉地址";
      }
    } catch (e) {
      $("gateMsg").textContent = "未能连通阵枢。可直接使用「玄黄镜演（离线演示）」体验。";
    }
  }

  function loadDemo() {
    state.demo = true;
    state.token = "demo";
    state.name = "太虚散人";
    state.status = {
      name: "太虚散人",
      realm: "筑基初期",
      sect: "四海散修盟",
      rank: "供奉",
      location: "青云坊市客栈",
      location_safe: true,
      stones: 520,
      vault: 1600,
      rem_years: 145,
      sin: 8,
      merit: 45,
      exp: "380/600",
      root: "金水双灵根",
      blood_marked: false,
      meditating: false,
    };
    state.here = [
      { name: "柳三娘", realm: "筑基中期", sect: "四海散修盟", rank: "掌柜", is_npc: true, personality: "和气生财", attitude_cn: "友善" },
      { name: "凌剑心", realm: "筑基圆满", sect: "万剑仙门", rank: "真传", is_npc: true, personality: "剑道痴迷", attitude_cn: "中立" },
      { name: "幽冥邪尊", realm: "化神期", sect: "九幽天魔宗", rank: "太上长老", is_npc: true, personality: "乖戾狠辣", attitude_cn: "敌视", blood_marked: true },
    ];
    state.feed = [
      { kind: "ai", text: "【天地演化】西荒黑风绝渊赤焰喷涌，世界疤痕显现，隐有上古凶煞降世！", ts: Date.now() / 1000 - 120 },
      { kind: "ok", text: "【仙途因果】你今日于客栈闭关参悟天工密卷，偶有所得，神识通达。", ts: Date.now() / 1000 - 30 },
    ];
    localStorage.setItem("wb.demo", "1");
    showApp();
    applyStatus(state.status);
    ensureDefaultInventory();
    ensureDefaultMarket();
    renderSideDrawer();
    renderBody();
    loadCommands();
    toast("已激活玄黄镜演模式", "gold");
  }

  async function tryRestore() {
    if (localStorage.getItem("wb.demo") === "1") {
      loadDemo();
      return;
    }
    if ($("fServer")) $("fServer").value = state.base;
    if (state.user && $("fUser")) $("fUser").value = state.user;
    if (state.name && $("fName")) $("fName").value = state.name;

    if (!state.token) return;
    try {
      const look = await api("/action", { token: state.token, command: "/look" });
      if (!look || look.ok === false) throw new Error("失效");
      if (look.status) applyStatus(look.status);
      showApp();
      await loadCommands();
      await refreshAll();
    } catch (_) {
      localStorage.removeItem("wb.token");
      state.token = "";
      showGate("昔日会话已逝，请重新踏入大世界。");
    }
  }

  // ==========================================================================
  // 事件与交互绑定
  // ==========================================================================
  function bind() {
    setTheme(state.theme);

    // 入世 / 登入切换
    document.querySelectorAll("[data-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.mode = btn.getAttribute("data-mode");
        document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b === btn));
        $("fNameWrap") && $("fNameWrap").classList.toggle("hidden", state.mode !== "register");
        if ($("gateSubmit")) {
          $("gateSubmit").textContent = state.mode === "register" ? "铸造道号 · 踏入仙途" : "踏入大千世界";
        }
      });
    });

    $("gateForm") && $("gateForm").addEventListener("submit", doAuth);
    $("btnProbe") && $("btnProbe").addEventListener("click", probeServer);
    $("btnDemo") && $("btnDemo").addEventListener("click", loadDemo);

    // 主境导航
    document.querySelectorAll(".nav-tab[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => setView(btn.getAttribute("data-view")));
    });

    // 抽屉触发
    $("btnOpenDrawer") && $("btnOpenDrawer").addEventListener("click", openSideDrawer);
    $("btnCloseDrawer") && $("btnCloseDrawer").addEventListener("click", closeSideDrawer);
    $("drawerBackdrop") && $("drawerBackdrop").addEventListener("click", closeSideDrawer);

    // 抽屉内部 Tab 切换
    $("tabCultivators") && $("tabCultivators").addEventListener("click", () => setDrawerTab("cultivators"));
    $("tabTeleport") && $("tabTeleport").addEventListener("click", () => setDrawerTab("teleport"));

    // 主题天象与归隐
    $("btnTheme") && $("btnTheme").addEventListener("click", () => {
      setTheme(state.theme === "dark" ? "light" : "dark");
    });
    $("btnLogout") && $("btnLogout").addEventListener("click", async () => {
      try {
        if (!state.demo && state.token) await api("/logout", { token: state.token });
      } catch (_) {}
      state.token = "";
      localStorage.removeItem("wb.token");
      showGate("已暂离归隐大千世界。");
    });

    // 底部敕令输入
    $("cmdForm") && $("cmdForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const val = $("cmdInput").value;
      if (state.chat.open && val && !val.startsWith("/")) {
        sendChat(val);
      } else {
        sendCmd(val);
      }
    });

    $("cmdInput") && $("cmdInput").addEventListener("input", renderSug);
    $("cmdInput") && $("cmdInput").addEventListener("keydown", (e) => {
      const sugBox = $("suggest");
      const open = sugBox && !sugBox.classList.contains("hidden") && state.sug.length;
      if (open && e.key === "ArrowDown") {
        e.preventDefault();
        state.sugI = Math.min(state.sug.length - 1, state.sugI + 1);
        updateSugActive();
      } else if (open && e.key === "ArrowUp") {
        e.preventDefault();
        state.sugI = Math.max(0, state.sugI - 1);
        updateSugActive();
      } else if (open && e.key === "Enter" && $("cmdInput").value.startsWith("/") && !$("cmdInput").value.trim().includes(" ")) {
        e.preventDefault();
        applySug(state.sugI);
      } else if (e.key === "Escape") {
        hideSug();
      }
    });

    $("suggest") && $("suggest").addEventListener("click", (e) => {
      const it = e.target.closest("[data-sug-i]");
      if (it) applySug(Number(it.getAttribute("data-sug-i")));
    });

    function updateSugActive() {
      document.querySelectorAll("#suggest .suggest-item").forEach((el, i) => {
        el.classList.toggle("active", i === state.sugI);
      });
    }

    // 交谈弹窗表单
    $("chatForm") && $("chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("chatInput").value;
      if (!v.trim()) return;
      $("chatInput").value = "";
      sendChat(v);
    });

    $("chatClose") && $("chatClose").addEventListener("click", () => closeChat(true));
    $("btnChatHang") && $("btnChatHang").addEventListener("click", () => closeChat(true));
    $("btnChatMem") && $("btnChatMem").addEventListener("click", () => {
      if (!state.demo && state.token) sendCmd("/会话");
      else chatMsg("", "（玄黄镜演）昔日因果历历在目，暂无冗余记录。", "sys");
    });

    // 全局事件委托（主工作区内各类按钮动作）
    document.addEventListener("click", (e) => {
      // 1. 点同道人名开聊
      const personEl = e.target.closest("[data-person]");
      if (personEl) {
        const name = personEl.getAttribute("data-person");
        openChat(name);
        closeSideDrawer();
        if (!state.demo) {
          pushFeed("» /交谈 " + name, "cmd");
          api("/action", { token: state.token, command: "/交谈 " + name })
            .then(handleChatData)
            .catch((err) => chatMsg("", "无法连通神识：" + err.message, "sys"));
        }
        return;
      }

      // 2. 指令执行 data-cmd
      const cmdEl = e.target.closest("[data-cmd]");
      if (cmdEl) {
        sendCmd(cmdEl.getAttribute("data-cmd"));
        return;
      }

      // 3. 迁跃 data-go
      const goEl = e.target.closest("[data-go]");
      if (goEl) {
        const place = goEl.getAttribute("data-go");
        sendCmd("/go " + place);
        closeSideDrawer();
        return;
      }

      // 4. 背包过滤与选中
      const bagFilterEl = e.target.closest("[data-bag-filter]");
      if (bagFilterEl) {
        state.bagFilter = bagFilterEl.getAttribute("data-bag-filter");
        state.selectedItemIndex = 0;
        renderBody();
        return;
      }

      const bagCellEl = e.target.closest("[data-bag-idx]");
      if (bagCellEl) {
        state.selectedItemIndex = Number(bagCellEl.getAttribute("data-bag-idx"));
        renderBody();
        return;
      }

      // 5. 特殊动作 data-act
      const actEl = e.target.closest("[data-act]");
      if (actEl) {
        const a = actEl.getAttribute("data-act");
        if (a.startsWith("view:")) {
          setView(a.slice(5));
        } else if (a.startsWith("sell:")) {
          const item = a.slice(5);
          const inp = $("cmdInput");
          if (inp) {
            inp.value = `/寄售 ${item} 100`;
            inp.focus();
          }
          toast(`已预填敕令：/寄售 ${item} <灵石价格>`, "gold");
        } else if (a.startsWith("focus-cmd:")) {
          const prefix = a.slice(10);
          const inp = $("cmdInput");
          if (inp) {
            inp.value = prefix;
            inp.focus();
          }
        }
      }
    });

    // 快捷键支持
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        hideSug();
        closeSideDrawer();
        const m = $("chatModal");
        if (m && !m.classList.contains("hidden")) closeChat(false);
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
  }

  bind();
  tryRestore();
})();
