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

  // 十方大荒四大秘境画卷 (Stitch 原生高保真图鉴)
  const WILDERNESS_REALMS = [
    {
      name: "落霞山灵泉",
      title: "落霞灵泉",
      tierName: "凡阶九品 · 入门历练",
      tagClass: "low",
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuA1AZ4waRujsx2R_ef9JUIGTcbPUMZ9ruLgErD47XYCtd78vC9qtCodfmJu04rMmzD58drdyOHMZtGx_Y3TMK-pMnUzhAeK2KWS57g3wlGiR83NLGZGh9moboS3ncIz5oV0NhoJonHqFXTrhAayoCF1MGzI7dKOpZJcLlIiPE7VXdQ8TDIQqtPUdNEeBTZkcHf3rLuD4zeAAvLi9JoYBZ8RTY8h9elPAjq-m3NSFW0fNaw3e24PJk2mDpVwwV7YF-sUm1NNbiLjoV20",
      mapDrop: "9%",
      dangerPercent: "22%",
      dangerText: "微波无害",
      desc: "群山连绵云雾轻绕，生有百年水灵芝与凡阶凝气草，乃初踏仙途温养道心绝佳宝地。",
      spiritRate: "灵泉温润 · 煞气极低",
      cost: "探险盘缠 20 灵石",
      location: "落霞山灵泉",
      rewards: ["凝气丹 五枚", "九叶野芝", "青木残卷"],
      isGuaranteed: true,
    },
    {
      name: "黑风绝渊",
      title: "落霞古洞",
      tierName: "玄阶上品 · 仙家古迹",
      tagClass: "mid",
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx",
      mapDrop: "18%",
      dangerPercent: "35%",
      dangerText: "暗藏禁制",
      desc: "洞藏千年落霞玉泉，可淬炼道骨肉身。深处有守洞玄猿栖息，暗合玄奥奇门杀阵。",
      spiritRate: "灵气充裕 · 凶险度中",
      cost: "探险盘缠 50 灵石",
      location: "黑风绝渊",
      rewards: ["落霞玉露", "破境清心丹", "真经残页"],
      isGuaranteed: false,
    },
    {
      name: "黑风绝渊裂隙",
      title: "黑风绝渊",
      tierName: "地阶中品 · 罡风天堑",
      tagClass: "danger",
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuDBrs5mCoUskHEbq1GlHOnBx7XWlud9-v5oIgbGeyYxe2ZzY4l3wRW1M1CTwwi8pFnX89v6X9ntxxBARx9Cb4Ql__nMwtBuQAYh-jEEtkSUo33eUdV59LGotu4vUq2__xsR-HnpMSLLev1Z7qwBpPGQmHxq04_AmEZpElihjyukTLNy9R-_Ypl69spuWXf7KoGj03iHgd1b8L-HVibTt72FDChjhuGY75UCephhoygFbX595WE_AWkDjio-wxN2z5AtO-zQuSGpJ-nk",
      mapDrop: "30%",
      dangerPercent: "55%",
      dangerText: "罡风裂魂",
      desc: "九天罡风呼啸凛冽，出产极寒玄冥阴玉。凡躯难抗，埋葬前朝万剑冢与嗜血妖兽。",
      spiritRate: "煞气弥漫 · 凶险度高",
      cost: "探险盘缠 100 灵石",
      location: "黑风绝渊",
      rewards: ["玄冥风晶", "地阶洗髓液", "幽冥舆图"],
      isGuaranteed: false,
    },
    {
      name: "万星古岛",
      title: "万星遗迹",
      tierName: "天阶绝境 · 上古仙阙",
      tagClass: "danger",
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuBbPOc8iM9b6MSMEI4lwWSqB16hzd1Hi4uor0XBPRt27QwOU-ZbBNZrbDjllObF13h_ontpANtf5BFwy8f9oM8gwa8BHesL_031HYxJRLDdD3Sh4He0-KflozAkqRWqa4mrCxGo5pKYOPuE2aypwkSNXu3iXGzdBTuCFwNFQRH0I8lfC3bsilMTemAfzWBWmQG6qrIBL3Vpp3rFksluu8Do6I10_Rl8dy4iDGXe699GlKoa0Uz7TO_Dg5TQ177c8CjpZvSyM-YuZSQ-",
      mapDrop: "40%",
      dangerPercent: "70%",
      dangerText: "十死一生",
      desc: "星辰陨落之所，阵眼遗存混沌星核，传闻更有天道至宝剑胎镇守，煞气与仙光激荡！",
      spiritRate: "紫雷狂暴 · 极度凶险",
      cost: "探险盘缠 200 灵石",
      location: "万星古岛",
      rewards: ["混沌星核", "紫雷真金", "天工秘录"],
      isGuaranteed: false,
    },
  ];

  const $ = (id) => document.getElementById(id);

  const state = {
    base: localStorage.getItem("wb.base") || "http://127.0.0.1:8765",
    token: localStorage.getItem("wb.token") || "",
    user: localStorage.getItem("wb.user") || "",
    name: localStorage.getItem("wb.name") || "",
    uid: localStorage.getItem("wb.uid") || "",
    theme: localStorage.getItem("wb.theme") === "dark" ? "dark" : "light",
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
    // 洞府运转专属动态设施
    sanctum: {
      springCharge: 92,
      herbsGrowth: 78,
      herbsRemainHours: 2,
      craneStatus: "idle",
      craneRemainSec: 0,
      craneDest: "",
      meditateMinutes: 0,
    },
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

    // 纳戒数据同步（服务端真实 item_entities 同步到 state.inventory）
    if (Array.isArray(st.items) && st.items.length > 0) {
      ensureDefaultInventory();
      for (const it of st.items) {
        const existIdx = state.inventory.findIndex(x => x.uid === it.uid || x.name === it.name);
        if (existIdx >= 0) {
          state.inventory[existIdx] = Object.assign({}, state.inventory[existIdx], it);
        } else {
          state.inventory.unshift(it);
        }
      }
    }

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
    // ---------- 视图切换与主境导航联动 ----------
  const VIEW_CRUMBS = {
    sanctum: "玄阁洞府",
    wilderness: "十方大荒",
    inventory: "百宝纳戒",
    bazaar: "九霄坊市",
  };

  function setView(v) {
    const valid = ["sanctum", "wilderness", "inventory", "bazaar"];
    if (!valid.includes(v)) v = "sanctum";
    state.view = v;
    document.querySelectorAll(".nav-tab[data-view]").forEach((b) => {
      const isCur = b.getAttribute("data-view") === v;
      b.classList.toggle("active", isCur);
      if (isCur) {
        b.className = "nav-tab active px-5 py-1.5 rounded-full text-xs font-semibold text-white bg-gradient-to-r from-jade-700 to-jade-600 shadow-sm flex items-center gap-1.5 transition-all";
      } else {
        b.className = "nav-tab px-5 py-1.5 rounded-full text-xs font-medium text-slate-600 hover:text-jade-800 hover:bg-white/60 transition-all flex items-center gap-1.5";
      }
    });
    const crumb = $("topNavCrumb");
    if (crumb) crumb.textContent = VIEW_CRUMBS[v] || "玄阁洞府";
    renderBody();
  }

  function renderBody() {
    const host = $("stageContent");
    if (!host) return;

    // 每次渲染统一刷新顶部天道盘数值（灵石、道阶等），确保多模块数值绝对一致
    const s = state.status || {};
    if ($("topStones")) setText("topStones", (s.stones != null ? s.stones : 0) + " 灵石");
    if ($("topDaoRealm")) setText("topDaoRealm", (s.realm || "—") + (s.rank && s.rank !== "散修" ? " · " + s.rank : ""));

    if (state.view === "sanctum") host.innerHTML = renderSanctum();
    else if (state.view === "wilderness") host.innerHTML = renderWilderness();
    else if (state.view === "inventory") host.innerHTML = renderInventory();
    else if (state.view === "bazaar") host.innerHTML = renderBazaar();
  }

  // ==========================================================================
  // 九天碧虚洞府专用通微弹窗、动效与交互控制器
  // ==========================================================================
  function openJadeDialog(opts) {
    closeJadeDialog();
    const overlay = document.createElement("div");
    overlay.id = "jadeDialogHost";
    overlay.className = "jade-dialog-overlay";
    overlay.innerHTML = `
      <div class="jade-dialog-card ${opts.cardClass || ''}">
        <div class="p-5 border-b border-jade-200/80 flex items-center justify-between bg-gradient-to-r from-jade-50 to-white">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">${opts.icon || '📜'}</span>
            <h3 class="text-base font-bold text-jade-950">${esc(opts.title)}</h3>
          </div>
          <button type="button" class="w-8 h-8 rounded-full bg-white hover:bg-jade-100 border border-jade-200 text-slate-500 hover:text-jade-900 flex items-center justify-center text-sm font-bold transition cursor-pointer" id="jadeDialogClose">✕</button>
        </div>
        <div class="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          ${opts.bodyHtml}
        </div>
        ${opts.footerHtml ? `<div class="p-4 bg-slate-50/80 border-t border-jade-100 flex items-center justify-end gap-3">${opts.footerHtml}</div>` : ''}
      </div>
    `;
    document.body.appendChild(overlay);
    const closeBtn = $("jadeDialogClose");
    if (closeBtn) closeBtn.addEventListener("click", closeJadeDialog);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeJadeDialog();
    });
    if (typeof opts.onMount === "function") opts.onMount(overlay);
  }

  function closeJadeDialog() {
    const el = $("jadeDialogHost");
    if (el) el.remove();
  }

  function spawnFloatBadge(text, targetEl, isGold) {
    if (!targetEl) return;
    const rect = targetEl.getBoundingClientRect();
    const badge = document.createElement("div");
    badge.className = "spirit-float-badge";
    badge.style.left = (rect.left + rect.width / 2) + "px";
    badge.style.top = (rect.top - 8) + "px";
    badge.style.color = isGold ? "#b45309" : "#047857";
    badge.style.fontSize = "13px";
    badge.textContent = text;
    document.body.appendChild(badge);
    setTimeout(() => badge.remove(), 1600);
  }

  // --------------------------------------------------------------------------
  // 修仙境界演进算法与解析器 (纯正东方修仙阶梯)
  // --------------------------------------------------------------------------
  const REALM_ORDER = ["练气期", "筑基期", "金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期", "真仙"];
  const SUB_TIERS = ["初期", "中期", "后期", "圆满"];

  function parseRealmInfo(realmStr) {
    const raw = String(realmStr || "练气期初期").replace(/[（(].*?[）)]/g, "").trim();
    let foundMajor = -1;
    let foundMajorName = "练气期";
    for (let i = 0; i < REALM_ORDER.length; i++) {
      if (raw.startsWith(REALM_ORDER[i]) || raw.includes(REALM_ORDER[i].slice(0, 2))) {
        foundMajor = i;
        foundMajorName = REALM_ORDER[i];
        break;
      }
    }
    if (foundMajor === -1) {
      foundMajor = 0;
      foundMajorName = "练气期";
    }

    let foundSub = 0;
    for (let j = 0; j < SUB_TIERS.length; j++) {
      if (raw.includes(SUB_TIERS[j])) {
        foundSub = j;
        break;
      }
    }

    let nextMajor = foundMajor;
    let nextSub = foundSub + 1;
    let isMajorBreakthrough = false;

    if (nextSub >= SUB_TIERS.length) {
      isMajorBreakthrough = true;
      nextMajor = Math.min(REALM_ORDER.length - 1, foundMajor + 1);
      nextSub = 0;
    }

    const currentName = `${foundMajorName}${SUB_TIERS[foundSub]}`;
    const nextName = `${REALM_ORDER[nextMajor]}${SUB_TIERS[nextSub]}`;

    const baseProbMap = [0.70, 0.60, 0.50, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15];
    const lifespanMap = [100, 200, 300, 500, 800, 1200, 2000, 3000, 10000];
    const baseProb = baseProbMap[foundMajor] || 0.30;
    const gainLifespan = lifespanMap[foundMajor] || 200;

    return {
      majorIndex: foundMajor,
      majorName: foundMajorName,
      subIndex: foundSub,
      subName: SUB_TIERS[foundSub],
      currentName,
      nextName,
      isMajorBreakthrough,
      baseProb,
      gainLifespan,
    };
  }

  function showCraneReturnedDialog(dest, pick, isOverflow = false) {
    if (!pick) return;
    openJadeDialog({
      title: isOverflow ? "青羽仙鹤 · 归巢捷报 (纳戒已满 · 暂存云巢)" : "青羽仙鹤 · 八荒巡弋归巢捷报",
      icon: "🕊️",
      bodyHtml: `
        <div class="text-center space-y-3">
          <div class="w-16 h-16 rounded-full ${isOverflow ? 'bg-amber-100 border-amber-300' : 'bg-jade-100 border-jade-300'} border flex items-center justify-center text-3xl mx-auto shadow-sm">
            🕊️
          </div>
          <h4 class="text-base font-bold text-jade-950">${isOverflow ? '灵兽破云归巢 · 仙物暂存云巢' : '灵兽破云归巢'}</h4>
          <p class="text-xs text-slate-600 leading-relaxed max-w-md mx-auto">
            ${isOverflow
              ? `青羽仙鹤巡弋【<strong>${esc(dest)}</strong>】顺利衔回机缘！因百宝纳戒乾坤已满（<strong>${state.inventory.length}/64</strong> 格位），仙物已稳妥暂存于<strong>洞府灵兽宝囊</strong>中：`
              : `青羽仙鹤巡弋【<strong>${esc(dest)}</strong>】方圆八百里，避开凶禽伏击，成功衔回机缘仙物并已存入纳戒：`}
          </p>
          <div class="p-3.5 bg-gradient-to-r from-amber-50 to-jade-50 rounded-xl border border-filigree-300 text-left space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-sm font-bold text-amber-900">${esc(pick.name)}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold">${esc(pick.tierName || '稀世机缘')} · ${esc(pick.slotCn || '灵物')}</span>
            </div>
            <p class="text-xs text-slate-600">${esc(pick.lore || pick.desc || '大荒绝地中孕育之天地造化奇珍。')}</p>
          </div>
          ${isOverflow ? `<p class="text-[11px] text-amber-800 bg-amber-50 p-2 rounded-lg border border-amber-200">提示：仙物安然无恙，道友可前往百宝纳戒出售或整理旧物，腾出空位后再至灵兽台领取！</p>` : ''}
        </div>
      `,
      footerHtml: isOverflow ? `
        <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
          暂留云巢
        </button>
        <button type="button" class="px-5 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold shadow-sm cursor-pointer" id="btnCraneGoClean">
          前往纳戒清理
        </button>
      ` : `
        <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
          暂留洞府
        </button>
        <button type="button" class="px-5 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-sm cursor-pointer" id="btnCraneGoBag">
          前往百宝纳戒查验
        </button>
      `,
      onMount: (overlay) => {
        const btnBag = overlay.querySelector("#btnCraneGoBag");
        if (btnBag) btnBag.addEventListener("click", () => {
          closeJadeDialog();
          state.bagFilter = "all"; // 重置为全部分类，保证无论图卷还是灵材均立现
          state.selectedItemIndex = 0; // 高亮选中首格刚落账的机缘物品
          setView("inventory");
          toast(`已入百宝纳戒：【${pick.name}】已就绪！`, "gold");
        });
        const btnClean = overlay.querySelector("#btnCraneGoClean");
        if (btnClean) btnClean.addEventListener("click", () => {
          closeJadeDialog();
          setView("inventory");
          toast(`百宝纳戒已满（${state.inventory.length}/64），请出售或整理旧物后再自仙鹤处领入！`, "gold");
        });
      },
    });
  }

  function handleCraneReturned(dest) {
    if (!state.demo) {
      api("/action", { token: state.token, command: `/灵鹤 ${dest}` })
        .then((res) => {
          if (res.status) applyStatus(res.status);
          if (res.text) pushFeed(res.text, res.ok ? "ai" : "bad");
          ensureDefaultInventory();
          const isOverflow = !!(res.overflow || (res.status && res.status.crane_pending_item));
          const latestItem = (res.status && res.status.crane_pending_item) || (res.status && Array.isArray(res.status.items) && res.status.items[0]) || state.inventory[0];
          if (latestItem) {
            if (isOverflow) {
              if (state.sanctum) state.sanctum.cranePendingItem = latestItem;
              toast(`纳戒已满！仙鹤将【${latestItem.name}】暂存云巢，请腾挪空间后领取！`, "gold");
              showCraneReturnedDialog(dest, latestItem, true);
            } else {
              toast(`青羽仙鹤归巢：得获【${latestItem.name}】！已存入纳戒！`, "gold");
              showCraneReturnedDialog(dest, latestItem, false);
            }
          }
        })
        .catch((err) => {
          toast("灵鹤神识传信受阻：" + err.message, "bad");
        });
      return;
    }

    const rewards = [
      {
        uid: "map_" + Date.now(),
        name: "落霞古洞藏宝残图",
        kind: "treasure_map",
        slotCn: "天机秘宝图卷",
        tier: 3,
        tierName: "地品",
        iconGlyph: "图",
        targetNodeName: "落霞古洞灵穴",
        archetypeCn: "离火九宫破阵",
        coords: "丙午方位 · 离火宫 南行三十里 古修士遗府",
        riddle: "双翼乘风入青云，仙鹤衔得古仙卷。火云掩映处，自有真仙遗泽。",
        lore: "青羽仙鹤掠过悬崖峭壁，在古修士枯骨旁衔回的秘境残卷！",
        desc: "青羽仙鹤衔回的秘境残卷，隐约散发太古火韵。",
        qty: 1,
      },
      {
        uid: "mat_" + Date.now(),
        name: "千年离火晶石",
        kind: "material",
        slotCn: "地火精萃",
        tier: 3,
        tierName: "地品",
        iconGlyph: "火",
        stats: { "纯阳火威": 50 },
        lore: "青羽仙鹤深入地脉火海，以纯阳神念衔出的地火精华，温热纯澈！",
        desc: "地脉离火万载凝结之精华，炼制纯阳法宝必用。",
        qty: 1,
      },
      {
        uid: "mat_" + Date.now(),
        name: "青鸾灵羽",
        kind: "material",
        slotCn: "神禽异宝",
        tier: 3,
        tierName: "地品",
        iconGlyph: "羽",
        stats: { "风雷遁速": 60 },
        lore: "青羽仙鹤巡弋途中偶遇异鸟，拾得的神禽遗羽，蕴含风雷道韵。",
        desc: "风雷之气盘绕不散，炼制飞遁灵宝的上乘主材。",
        qty: 1,
      },
    ];
    const pick = rewards[Math.floor(Math.random() * rewards.length)];

    ensureDefaultInventory();
    const isOverflow = state.inventory && state.inventory.length >= 64;
    const sc = state.sanctum;

    if (isOverflow) {
      if (sc) sc.cranePendingItem = pick;
      pushFeed(`【仙鹤啼鸣归巢】镇山仙鹤巡弋【${dest}】归来，衔回【${pick.name}】！因百宝纳戒乾坤已满（${state.inventory.length}/64），仙物已稳妥暂留于云巢灵囊中！请道友腾挪纳戒空间后领取。`, "ai");
      toast(`纳戒已满！仙鹤将【${pick.name}】暂存云巢，请腾挪空间后领取！`, "gold");
      showCraneReturnedDialog(dest, pick, true);
    } else {
      state.inventory.unshift(pick);
      pushFeed(`【仙鹤啼鸣归巢】镇山灵兽巡弋【${dest}】归来，神识传音报捷，衔回【${pick.name}】存入百宝纳戒！`, "ai");
      toast(`青羽仙鹤归巢：得获【${pick.name}】！已存入纳戒！`, "gold");
      showCraneReturnedDialog(dest, pick, false);
    }
  }

  function claimCranePendingItem() {
    const sc = state.sanctum;
    const pendingItem = (sc && sc.cranePendingItem) || (state.status && state.status.crane_pending_item);
    if (!pendingItem) {
      toast("仙鹤云巢灵囊中并无待领取的机缘仙物。", "bad");
      return;
    }
    if (!state.demo) {
      api("/action", { token: state.token, command: "/灵鹤 领取" })
        .then((res) => {
          if (res.status) applyStatus(res.status);
          if (res.text) pushFeed(res.text, res.ok ? "ai" : "bad");
          if (res.ok) {
            if (sc) sc.cranePendingItem = null;
            toast("仙鹤云巢机缘已顺利取回并存入百宝纳戒！", "gold");
            renderBody();
          } else {
            toast(res.error || "取回机缘受阻", "bad");
          }
        })
        .catch((err) => {
          toast("神识传信受阻：" + err.message, "bad");
        });
      return;
    }

    ensureDefaultInventory();
    if (state.inventory.length >= 64) {
      toast(`百宝纳戒乾坤已满（${state.inventory.length}/64），无法存入！请先前往纳戒移出或出售旧物！`, "bad");
      return;
    }

    state.inventory.unshift(pendingItem);
    if (sc) sc.cranePendingItem = null;
    if (state.status) state.status.crane_pending_item = null;
    toast(`已从仙鹤云巢取下【${pendingItem.name}】并存入纳戒！`, "gold");
    pushFeed(`【仙鹤云巢 · 取回机缘】你自青羽仙鹤灵囊中取下【${pendingItem.name}】，已妥善收入百宝纳戒！仙鹤振翅轻啼，重回栖息待命态。`, "ai");
    renderBody();
  }

  let sanctumTimer = null;
  function startSanctumLoop() {
    if (sanctumTimer) clearInterval(sanctumTimer);
    sanctumTimer = setInterval(() => {
      let changed = false;
      const sc = state.sanctum;
      if (!sc) return;

      // 仙鹤倒计时
      if (sc.craneStatus === "scouting") {
        if (sc.craneRemainSec > 1) {
          sc.craneRemainSec -= 1;
          changed = true;
        } else {
          sc.craneStatus = "idle";
          sc.craneRemainSec = 0;
          const dest = sc.craneDest || "落霞山";
          sc.craneDest = "";
          handleCraneReturned(dest);
          changed = true;
        }
      }

      // 灵泉慢充
      if (sc.springCharge < 100 && Math.random() < 0.2) {
        sc.springCharge = Math.min(100, sc.springCharge + 1);
        changed = true;
      }

      // 吐纳计时
      const s = state.status;
      if (s && (s.is_meditating || s.meditating)) {
        sc.meditateMinutes = (sc.meditateMinutes || 0) + 1;
      }

      if (changed && state.view === "sanctum") {
        renderBody();
      }
    }, 1000);
  }

  // --------------------------------------------------------------------------
  // 洞府核心行为统一调度器
  // --------------------------------------------------------------------------
  function handleSanctumAction(act, el) {
    const s = state.status || {};
    const sc = state.sanctum || (state.sanctum = {
      springCharge: 92,
      herbsGrowth: 78,
      herbsRemainHours: 2,
      craneStatus: "idle",
      craneRemainSec: 0,
      craneDest: "",
      meditateMinutes: 0,
    });

    if (act === "spring") {
      // 1. 玄冰灵泉提取灵露
      if (sc.springCharge < 10) {
        toast("灵泉尚在蓄液中，尚未聚成灵露，稍候再采", "gold");
        return;
      }
      sc.springCharge = 0;
      spawnFloatBadge("+200 真元", el, false);
      toast("汲取玄冰灵液：周天真元 +200，得【玄冰玉露】！", "gold");

      if (state.demo) {
        pushFeed("【洞府灵泉 · 汲取】你引地阴玄水入体，涤荡泥丸宫，周天真元 +200！得获【玄冰玉露】一份入纳戒。", "ok");
        state.inventory.unshift({
          name: "玄冰玉露",
          kind: "consumable",
          rarity: "uncommon",
          desc: "玄冰九曲灵泉孕育的灵露，饮之清心涤滤，修为进境倍增。",
          qty: 1,
        });

        if (s.exp && s.exp.includes("/")) {
          const parts = s.exp.replace(/,/g, "").split("/");
          let cur = parseFloat(parts[0]) || 0;
          let max = parseFloat(parts[1]) || 1400000;
          cur = Math.min(max, cur + 200);
          s.exp = `${cur.toLocaleString()} / ${parts[1].trim()}`;
        }
        renderBody();
      } else {
        sendCmd("/灵泉");
      }
      return;
    }

    if (act === "herbs") {
      // 2. 紫菁草园采摘与催熟
      const isReady = sc.herbsGrowth >= 100;
      openJadeDialog({
        title: "紫菁九叶草园 · 灵草温育",
        icon: "🌿",
        bodyHtml: `
          <div class="space-y-4">
            <div class="p-4 bg-emerald-50/60 rounded-xl border border-emerald-200 space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-emerald-950 flex items-center gap-1.5">
                  <span>🌿 当前品种植育：</span>
                  <span class="text-emerald-700">千年紫菁芝草（仙品三株）</span>
                </span>
                <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${isReady ? 'bg-emerald-200 text-emerald-900' : 'bg-amber-100 text-amber-900'}">
                  ${isReady ? '灵草已成熟 · 可采摘' : `尚余 ${sc.herbsRemainHours || 2} 时辰成熟`}
                </span>
              </div>
              <div class="w-full bg-emerald-100 h-2 rounded-full overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-500 to-teal-600 h-full rounded-full transition-all duration-500" style="width: ${sc.herbsGrowth}%"></div>
              </div>
              <div class="flex justify-between text-[11px] text-slate-500">
                <span>地脉灵蕴滋养：${sc.herbsGrowth}%</span>
                <span>炼丹主材：九转还魂丹</span>
              </div>
            </div>

            <div class="p-3.5 bg-white rounded-xl border border-jade-200 text-xs space-y-2">
              <div class="font-bold text-jade-950">洞天培育法令：</div>
              <p class="text-slate-600 leading-relaxed">
                芝草沐浴朝露紫气，若急需入药，可耗费 <strong>50 灵石</strong> 引地脉灵泉瞬息催熟；亦可耐心等待天时造化。
              </p>
              <div class="text-[11px] text-slate-500">
                随身灵石：<strong class="text-jade-900 font-mono">${s.stones || 0} 灵石</strong>
              </div>
            </div>
          </div>
        `,
        footerHtml: `
          <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-semibold cursor-pointer" id="btnHerbRush">
            耗 50 灵石地脉催熟
          </button>
          <button type="button" class="px-5 py-2 rounded-xl ${isReady ? 'bg-jade-700 hover:bg-jade-800 text-white cursor-pointer' : 'bg-slate-200 text-slate-400 cursor-not-allowed'} text-xs font-semibold shadow-sm" id="btnHerbHarvest">
            立即采摘仙草
          </button>
        `,
        onMount: (overlay) => {
          const rushBtn = overlay.querySelector("#btnHerbRush");
          if (rushBtn) {
            rushBtn.addEventListener("click", () => {
              if ((s.stones || 0) < 50) {
                toast("随身灵石不足 50，无法催熟仙草", "bad");
                return;
              }
              s.stones = (s.stones || 0) - 50;
              sc.herbsGrowth = 100;
              sc.herbsRemainHours = 0;
              toast("灵石催熟功成：芝草瞬息成熟！", "gold");
              pushFeed("【紫菁草园 · 催熟】你注入 50 灵石引动地脉真火，仙品芝草瞬息吞吐紫气，成熟待采！", "ai");
              if (!state.demo) sendCmd("/草园 催熟");
              closeJadeDialog();
              renderBody();
            });
          }
          const harvestBtn = overlay.querySelector("#btnHerbHarvest");
          if (harvestBtn) {
            harvestBtn.addEventListener("click", () => {
              if (sc.herbsGrowth < 100) {
                toast("灵草尚未完全成熟，请先催熟或稍候", "bad");
                return;
              }
              sc.herbsGrowth = 15;
              sc.herbsRemainHours = 4;
              state.inventory.unshift({
                name: "千年紫菁芝草",
                kind: "material",
                rarity: "epic",
                desc: "紫菁草园产出的极品仙芝，蕴含丰沛生机，炼制高阶还魂丹之上品主材。",
                qty: 3,
              });
              toast("采摘成功：得【千年紫菁芝草】x3 入纳戒！", "gold");
              pushFeed("【紫菁草园 · 采摘】你小心翼翼采下成熟仙草，灵香四溢，收获【千年紫菁芝草】x3 放入纳戒。", "ok");
              if (!state.demo) sendCmd("/草园");
              closeJadeDialog();
              renderBody();
            });
          }
        },
      });
      return;
    }

    if (act === "crane_claim") {
      claimCranePendingItem();
      return;
    }

    if (act === "crane") {
      // 3. 镇山仙鹤探路
      const hasPending = !!((sc && sc.cranePendingItem) || (state.status && state.status.crane_pending_item));
      if (hasPending) {
        const pObj = (sc && sc.cranePendingItem) || (state.status && state.status.crane_pending_item);
        toast(`仙鹤灵囊中尚有衔回的【${pObj.name}】未取！请先领取仙物再行敕令启程！`, "bad");
        return;
      }
      if (sc.craneStatus === "scouting") {
        openJadeDialog({
          title: "镇山灵兽 · 青羽仙鹤巡弋中",
          icon: "🕊️",
          bodyHtml: `
            <div class="text-center space-y-3 py-2">
              <div class="w-14 h-14 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center text-2xl mx-auto animate-pulse">
                🕊️
              </div>
              <h4 class="text-sm font-bold text-jade-950">仙鹤正于【${esc(sc.craneDest || '大荒')}】远巡</h4>
              <p class="text-xs text-slate-600">
                双翼横击三千里，正穿行于云雾罡风之间，尚余 <strong>${sc.craneRemainSec}</strong> 息归巢。
              </p>
              <div class="w-full bg-slate-100 h-2 rounded-full overflow-hidden max-w-xs mx-auto">
                <div class="bg-amber-500 h-full rounded-full transition-all duration-300" style="width: ${Math.max(10, 100 - sc.craneRemainSec * 4)}%"></div>
              </div>
            </div>
          `,
          footerHtml: `
            <button type="button" class="px-5 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold cursor-pointer" onclick="workbench.closeJadeDialog()">
              静候佳音
            </button>
          `,
        });
        return;
      }

      openJadeDialog({
        title: "镇山灵兽 · 命仙鹤八荒探路",
        icon: "🕊️",
        bodyHtml: `
          <div class="space-y-3.5">
            <p class="text-xs text-slate-600 leading-relaxed">
              青羽仙鹤乃通灵玄禽，双翼乘风，能辨大荒地脉吉凶。请法旨定夺巡弋方位：
            </p>

            <div class="space-y-2.5">
              <label class="p-3 rounded-xl border border-jade-200 bg-white hover:bg-jade-50/70 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-3">
                  <input type="radio" name="craneDest" value="落霞密林" checked class="text-jade-700" />
                  <div>
                    <div class="text-xs font-bold text-jade-950">巡弋【落霞密林】</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">历时 15 息 · 消耗 10 灵石 · 觅初阶灵药与地脉虚实</div>
                  </div>
                </div>
                <span class="text-xs text-jade-800 font-semibold">10 灵石</span>
              </label>

              <label class="p-3 rounded-xl border border-filigree-300 bg-amber-50/40 hover:bg-amber-50 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-3">
                  <input type="radio" name="craneDest" value="黑风绝渊赤焰" class="text-jade-700" />
                  <div>
                    <div class="text-xs font-bold text-amber-950">深潜【黑风绝渊赤焰】</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">历时 20 息 · 消耗 30 灵石 · 大概率探得【藏宝残图】碎片</div>
                  </div>
                </div>
                <span class="text-xs text-amber-900 font-semibold">30 灵石</span>
              </label>

              <label class="p-3 rounded-xl border border-jade-200 bg-white hover:bg-jade-50/70 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-3">
                  <input type="radio" name="craneDest" value="南海碧波古墟" class="text-jade-700" />
                  <div>
                    <div class="text-xs font-bold text-jade-950">破浪【南海碧波古墟】</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">历时 25 息 · 消耗 50 灵石 · 探寻上古洞府密辛机缘</div>
                  </div>
                </div>
                <span class="text-xs text-jade-800 font-semibold">50 灵石</span>
              </label>
            </div>

            <div class="text-[11px] text-slate-500 text-right">
              当前随身灵石：<strong class="text-jade-900 font-mono">${s.stones || 0} 灵石</strong>
            </div>
          </div>
        `,
        footerHtml: `
          <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
            暂罢
          </button>
          <button type="button" class="px-5 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-sm cursor-pointer" id="btnDispatchCrane">
            敕令仙鹤启程
          </button>
        `,
        onMount: (overlay) => {
          const btn = overlay.querySelector("#btnDispatchCrane");
          if (btn) {
            btn.addEventListener("click", () => {
              const selected = overlay.querySelector("input[name='craneDest']:checked");
              const dest = selected ? selected.value : "落霞密林";
              const costMap = { "落霞密林": 10, "黑风绝渊赤焰": 30, "南海碧波古墟": 50 };
              const timeMap = { "落霞密林": 15, "黑风绝渊赤焰": 20, "南海碧波古墟": 25 };
              const cost = costMap[dest] || 10;
              const timeSec = timeMap[dest] || 15;

              if ((s.stones || 0) < cost) {
                toast(`随身灵石不足 ${cost}，无法派遣仙鹤`, "bad");
                return;
              }

              s.stones = (s.stones || 0) - cost;
              sc.craneStatus = "scouting";
              sc.craneRemainSec = timeSec;
              sc.craneDest = dest;

              toast(`青羽仙鹤展翅长鸣，破云前往【${dest}】！`, "gold");
              pushFeed(`【仙鹤启程】镇山仙鹤领法旨，展翅长唳，飞往【${dest}】巡弋探查！`);

              closeJadeDialog();
              renderBody();
            });
          }
        },
      });
      return;
    }

    if (act === "breakthrough") {
      // 4. 引雷破境大典 / 顺畅顿悟晋阶
      const rInfo = parseRealmInfo(s.realm);
      let expPct = 0;
      let curExp = 0;
      let maxExp = 1;
      if (s.exp && s.exp.includes("/")) {
        const parts = s.exp.replace(/,/g, "").split("/");
        curExp = parseFloat(parts[0]) || 0;
        maxExp = parseFloat(parts[1]) || 1;
        expPct = Math.min(100, Math.max(0, Math.round((curExp / maxExp) * 100)));
      }

      // 门禁判定：未满 100% 坚决拦截
      if (expPct < 100) {
        const diff = Math.max(1, Math.round(maxExp - curExp));
        toast(`修为尚未圆满（当前进境 ${expPct}%），不可强行引雷！`, "bad");
        pushFeed(`【天道警示】道友当前道阶【${rInfo.currentName}】真元尚欠 ${diff.toLocaleString()} 点未至圆满，强行引雷恐遭天火反噬焚体，请先闭关吐纳或服用灵丹！`, "bad");
        return;
      }

      // 分流 A：小阶顿悟突破（例如 练气初期 -> 练气中期）
      if (!rInfo.isMajorBreakthrough) {
        s.realm = rInfo.nextName;
        const newMax = Math.round(maxExp * 1.5);
        s.exp = `0 / ${newMax.toLocaleString()}`;
        toast(`【灵犀顿悟】真元贯通周天经脉，顺畅晋阶为【${rInfo.nextName}】！`, "gold");
        pushFeed(`【周天晋阶】你福至心灵，体内真元如水银泻地，顺畅通畅，晋升至【${rInfo.nextName}】！（小阶顿悟不增寿元）`, "ok");
        if (!state.demo) sendCmd("/突破");
        renderBody();
        return;
      }

      // 分流 B：大境界引雷渡劫（例如 练气圆满 -> 筑基初期）
      let baseProb = rInfo.baseProb;
      let probDisplay = Math.round(baseProb * 100);

      openJadeDialog({
        title: "九天雷劫 · 渡劫问心法会",
        icon: "⚡",
        bodyHtml: `
          <div class="space-y-4" id="tribulationBox">
            <div class="p-4 bg-gradient-to-r from-amber-50 via-rose-50 to-jade-50 rounded-xl border border-amber-300 space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-600 font-semibold">破境进阶契约：</span>
                <span class="text-xs font-bold text-amber-900">${esc(rInfo.currentName)} ➔ ${esc(rInfo.nextName)}</span>
              </div>
              <div class="flex items-center justify-between text-xs">
                <span>周天真元充盈：</span>
                <strong class="font-mono text-jade-800">${esc(s.exp)} (100% 圆满)</strong>
              </div>
              <div class="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                <div class="bg-gradient-to-r from-jade-600 to-amber-500 h-full rounded-full" style="width: 100%"></div>
              </div>
              <div class="text-[11px] text-amber-800 font-medium">
                天道煞气：大境界突破必引动九天雷劫，降伏心魔方得成仙！成败皆有天数，切莫掉以轻心。
              </div>
            </div>

            <div class="p-3.5 bg-white rounded-xl border border-jade-200 space-y-2 text-xs">
              <div class="font-bold text-jade-950 flex items-center justify-between">
                <span>护法灵物与大阵加护：</span>
                <span class="text-filigree-700 font-bold" id="tribProbText">天命成功率：${probDisplay + 15}%</span>
              </div>
              <div class="space-y-2 pt-1">
                <label class="flex items-center gap-2 text-slate-700 cursor-pointer">
                  <input type="checkbox" id="chkPill" checked class="text-jade-700 rounded" />
                  <span>消耗纳戒中【护心破境灵丹】（成功率 +15%）</span>
                </label>
                <label class="flex items-center gap-2 text-slate-700 cursor-pointer">
                  <input type="checkbox" id="chkArray" checked class="text-jade-700 rounded" />
                  <span>运转【太乙两仪生灭阵】（抵御煞气天雷反噬，降低渡劫创伤）</span>
                </label>
              </div>
            </div>

            <div id="thunderStage" class="hidden p-4 rounded-xl bg-slate-900 text-amber-300 font-mono text-xs space-y-1 text-center border border-amber-400">
              <div class="text-sm font-bold text-amber-400 animate-pulse">⚡ 九霄雷劫倾泻而下 ⚡</div>
              <div class="text-slate-300 text-[11px]" id="thunderStepText">第一道紫霄神雷淬体……</div>
            </div>
          </div>
        `,
        footerHtml: `
          <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
            暂敛锋芒
          </button>
          <button type="button" class="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5" id="btnDoBreakthrough">
            <span>⚡</span>
            <span>引动九霄天雷迎劫</span>
          </button>
        `,
        onMount: (overlay) => {
          const chkPill = overlay.querySelector("#chkPill");
          const probText = overlay.querySelector("#tribProbText");
          const getFinalProb = () => Math.min(0.95, baseProb + (chkPill && chkPill.checked ? 0.15 : 0.0));

          if (chkPill && probText) {
            chkPill.addEventListener("change", () => {
              const p = Math.round(getFinalProb() * 100);
              probText.textContent = `天命成功率：${p}%`;
            });
          }

          const btn = overlay.querySelector("#btnDoBreakthrough");
          if (btn) {
            btn.addEventListener("click", () => {
              btn.disabled = true;
              btn.classList.add("opacity-50");
              const stage = overlay.querySelector("#thunderStage");
              const step = overlay.querySelector("#thunderStepText");
              const card = overlay.querySelector(".jade-dialog-card");
              if (stage) stage.classList.remove("hidden");
              if (card) card.classList.add("tribulation-shake");

              setTimeout(() => {
                if (step) step.textContent = "泥丸宫天门大开，道心神雷降下，天道裁决中……";
              }, 700);

              setTimeout(() => {
                if (card) card.classList.remove("tribulation-shake");

                if (!state.demo) {
                  // 联机模式：由服务端 BreakthroughEngine 权威裁决
                  sendCmd("/突破");
                  closeJadeDialog();
                  toast("引雷破境敕令已通达天道，静候天命法旨！", "gold");
                  return;
                }

                // 离线 Demo 模式：真随机判定 (选项 B 硬核天道规则)
                const finalP = getFinalProb();
                const isSuccess = Math.random() < finalP;

                closeJadeDialog();

                if (isSuccess) {
                  // 渡劫成功
                  s.realm = rInfo.nextName;
                  const newMax = Math.round(maxExp * 2.5);
                  s.exp = `0 / ${newMax.toLocaleString()}`;
                  s.rem_years = (s.rem_years || 100) + rInfo.gainLifespan;
                  s.merit = (s.merit || 0) + 300;

                  toast(`雷劫破尽！恭贺道友破境登临【${rInfo.nextName}】！`, "gold");
                  pushFeed(`【天道雷劫 · 功成】${esc(s.name || "道友")}引动九重金液玉雷淬炼仙躯，心魔尽伏，功德圆满，一举登临【${rInfo.nextName}】！寿元绵延 +${rInfo.gainLifespan} 载！`, "ai");
                  renderBody();

                  openJadeDialog({
                    title: "天道垂青 · 登仙大捷",
                    icon: "✨",
                    bodyHtml: `
                      <div class="text-center space-y-3 py-3">
                        <div class="w-16 h-16 rounded-full bg-gradient-to-tr from-amber-400 to-amber-200 text-amber-950 flex items-center justify-center text-3xl mx-auto shadow-md">
                          🌟
                        </div>
                        <h4 class="text-lg font-bold text-jade-950">恭贺道友破境功成</h4>
                        <p class="text-xs text-slate-700 leading-relaxed max-w-md mx-auto">
                          九霄神雷洗尽凡尘因果，道身蜕化，寿元绵延 <strong>+${rInfo.gainLifespan} 载</strong>，天地灵气共鸣！
                        </p>
                        <div class="grid grid-cols-2 gap-2 text-xs max-w-xs mx-auto pt-1">
                          <div class="p-2 rounded-lg bg-jade-50 border border-jade-200">晋升道阶：<strong class="text-jade-900">${esc(rInfo.nextName)}</strong></div>
                          <div class="p-2 rounded-lg bg-amber-50 border border-amber-200">清净功德：<strong class="text-filigree-700">+300 点</strong></div>
                        </div>
                      </div>
                    `,
                    footerHtml: `
                      <button type="button" class="px-6 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold cursor-pointer" onclick="workbench.closeJadeDialog()">
                        稳固道基
                      </button>
                    `,
                  });
                } else {
                  // 渡劫失败 (选项 B 硬核天道：扣 20% 真元，50% 概率折损 1~3 年寿元，轻伤)
                  const penaltyExp = Math.round(maxExp * 0.2);
                  const remainExp = Math.max(0, maxExp - penaltyExp);
                  s.exp = `${remainExp.toLocaleString()} / ${maxExp.toLocaleString()}`;

                  let lostYears = 0;
                  if (Math.random() < 0.5) {
                    lostYears = Math.floor(Math.random() * 3) + 1;
                    s.rem_years = Math.max(1, (s.rem_years || 100) - lostYears);
                  }

                  toast("天雷反噬！渡劫未果，真元受损！", "bad");
                  pushFeed(`【天道雷劫 · 反噬】天劫狂暴，道心震荡！渡劫未果，体内真元折损 20%（-${penaltyExp.toLocaleString()}）${lostYears > 0 ? `，寿元折损 ${lostYears} 载` : ''}，受轻度震荡道伤！`, "bad");
                  renderBody();

                  openJadeDialog({
                    title: "天雷反噬 · 渡劫未果",
                    icon: "⚡",
                    bodyHtml: `
                      <div class="text-center space-y-3 py-3">
                        <div class="w-16 h-16 rounded-full bg-rose-100 text-rose-800 flex items-center justify-center text-3xl mx-auto shadow-sm">
                          💥
                        </div>
                        <h4 class="text-lg font-bold text-rose-950">九天雷劫未破</h4>
                        <p class="text-xs text-slate-700 leading-relaxed max-w-md mx-auto">
                          劫云狂暴，阴阳真火撕扯经脉，道心微滞未能引雷入体。幸得护法大阵庇护，保全肉身元神！
                        </p>
                        <div class="p-3 bg-rose-50/80 rounded-xl border border-rose-200 text-xs text-rose-900 space-y-1.5 max-w-sm mx-auto text-left">
                          <div>• 周天真元震荡跌落：<strong>-20% (${penaltyExp.toLocaleString()} 点)</strong></div>
                          ${lostYears > 0 ? `<div>• 天雷煞气侵蚀寿元：<strong>-${lostYears} 载</strong></div>` : '<div>• 寿元因大阵守护安然无恙</div>'}
                          <div>• 道体附带【雷震轻伤】，请先收功温养，重新蓄积真元后再引天劫！</div>
                        </div>
                      </div>
                    `,
                    footerHtml: `
                      <button type="button" class="px-6 py-2 rounded-xl bg-rose-700 hover:bg-rose-800 text-white text-xs font-semibold cursor-pointer" onclick="workbench.closeJadeDialog()">
                        温养疗伤
                      </button>
                    `,
                  });
                }
              }, 1500);
            });
          }
        },
      });
      return;
    }

    if (act === "meditate_toggle" || act === "meditate_enter" || act === "meditate_leave") {
      // 5. 入定闭关 / 收功出关
      const isMed = s.is_meditating || s.meditating || false;
      if (!isMed || act === "meditate_enter") {
        s.is_meditating = true;
        s.meditating = true;
        sc.meditateMinutes = 0;
        toast("洞府阵法锁闭：道友已入定吐纳，周天运转中", "gold");
        pushFeed("【洞府行止】你阖目盘坐于静室蒲团之上，开启太乙两仪生灭阵，五心朝天，吞吐周天紫气。");
        if (!state.demo) sendCmd("/闭关 1");
        renderBody();
      } else {
        openJadeDialog({
          title: "静室蒲团 · 收功出关结算",
          icon: "🧘",
          bodyHtml: `
            <div class="space-y-3.5">
              <div class="p-4 bg-jade-50/70 rounded-xl border border-jade-200 space-y-2">
                <div class="flex justify-between items-center text-xs">
                  <span class="text-slate-600">闭关运化时辰：</span>
                  <strong class="text-jade-900 font-mono">1 时辰 (入定两刻)</strong>
                </div>
                <div class="flex justify-between items-center text-xs">
                  <span class="text-slate-600">累积汲取真元：</span>
                  <strong class="text-filigree-700 font-mono">+6,200 修为</strong>
                </div>
                <div class="flex justify-between items-center text-xs">
                  <span class="text-slate-600">寿元天道流逝：</span>
                  <strong class="text-slate-500 font-mono">-0.05 载</strong>
                </div>
              </div>
              <p class="text-xs text-slate-600 leading-relaxed">
                六识渐开，真元运转周天归入丹田气海。道心澄澈无碍，是否立即收功出关？
              </p>
            </div>
          `,
          footerHtml: `
            <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
              继续入定
            </button>
            <button type="button" class="px-5 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-sm cursor-pointer" id="btnConfirmEmerge">
              收功出关
            </button>
          `,
          onMount: (overlay) => {
            const btn = overlay.querySelector("#btnConfirmEmerge");
            if (btn) {
              btn.addEventListener("click", () => {
                s.is_meditating = false;
                s.meditating = false;
                if (s.exp && s.exp.includes("/")) {
                  const parts = s.exp.replace(/,/g, "").split("/");
                  let cur = parseFloat(parts[0]) || 0;
                  let max = parseFloat(parts[1]) || 1400000;
                  cur = Math.min(max, cur + 6200);
                  s.exp = `${cur.toLocaleString()} / ${parts[1].trim()}`;
                }
                toast("收功出关：真元充盈，神清气爽！", "gold");
                pushFeed("【洞府行止】你长舒一口浊气，收功出关，周天真元 +6,200！");
                if (!state.demo) sendCmd("/出关");
                closeJadeDialog();
                renderBody();
              });
            }
          },
        });
      }
      return;
    }

    if (act === "vault_deposit") {
      // 6. 存入百石
      if ((s.stones || 0) < 100) {
        toast("随身灵石不足百块，无法存入金库", "bad");
        return;
      }
      s.stones = (s.stones || 0) - 100;
      s.vault = (s.vault || 0) + 95;
      spawnFloatBadge("-100 灵石", el, true);
      toast("百石寄存大阵金库（免遭大荒掠夺）！", "gold");
      pushFeed("【乾坤金库】存入 100 灵石，扣除五石护阵契税，金库蓄积增加 95 灵石。");
      if (!state.demo) sendCmd("/寄存 100");
      renderBody();
      return;
    }

    if (act === "vault_withdraw") {
      // 7. 支取百石
      if ((s.vault || 0) < 100) {
        toast("大阵金库储积不足百块灵石", "bad");
        return;
      }
      s.vault = (s.vault || 0) - 100;
      s.stones = (s.stones || 0) + 100;
      spawnFloatBadge("+100 灵石", el, true);
      toast("已从金库支取百石收入随身行囊！", "gold");
      pushFeed("【乾坤金库】从大阵金库支取 100 灵石入纳戒。");
      if (!state.demo) sendCmd("/支取 100");
      renderBody();
      return;
    }

    if (act === "astro") {
      // 8. 观星推演全图
      openJadeDialog({
        title: "天机星象 · 诸天二十八星宿图录",
        icon: "🌌",
        bodyHtml: `
          <div class="space-y-4">
            <div class="p-4 rounded-xl bg-slate-900 text-white space-y-2 border border-filigree-400/40">
              <div class="flex items-center justify-between text-xs text-amber-300">
                <span>芒种岁星入亢宿 · 东方苍龙</span>
                <span class="px-2 py-0.5 rounded bg-amber-400/20 text-amber-300 text-[10px] font-mono">[大吉 · 气数充沛]</span>
              </div>
              <h4 class="text-sm font-bold text-white tracking-wide">太素第七重微界 · 灵潮大定</h4>
              <p class="text-xs text-slate-300 leading-relaxed">
                周天星轨顺行，九天罡风趋于平稳。西荒绝渊凶煞有回落之象，南海碧波隐现古仙府遗迹！
              </p>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <div class="p-2.5 rounded-lg bg-jade-50 border border-jade-200">
                <span class="text-jade-900 font-bold block mb-1">【天时大宜】</span>
                <p class="text-slate-600">闭关静修、灵丹入药、大荒探宝</p>
              </div>
              <div class="p-2.5 rounded-lg bg-rose-50 border border-rose-200">
                <span class="text-rose-900 font-bold block mb-1">【因果切忌】</span>
                <p class="text-slate-600">孤身涉险死地、轻起杀伐因果</p>
              </div>
            </div>
          </div>
        `,
        footerHtml: `
          <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
            收敛神识
          </button>
          <button type="button" class="px-5 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-sm cursor-pointer" id="btnGoWildernessFromSanctum">
            踏入十方大荒历练
          </button>
        `,
        onMount: (overlay) => {
          const btn = overlay.querySelector("#btnGoWildernessFromSanctum");
          if (btn) {
            btn.addEventListener("click", () => {
              closeJadeDialog();
              setView("wilderness");
            });
          }
        },
      });
      return;
    }
  }

  // ==========================================================================
  // 主境一：【玄阁洞府 · 仙府总揽与乾坤枢机】 (Sanctum) - Stitch 原生 1:1 高保真
  // ==========================================================================
  function renderSanctum() {
    const s = state.status || {
      name: "太素仙尊 · 顾青玄",
      realm: "化神后期（圆满）",
      sect: "太素仙宗",
      rank: "太上掌教",
      stones: 128450,
      vault: 360000,
      exp: "1,240,000 / 140万",
      rem_years: 2800,
      sin: 120,
      merit: 3650,
      root: "先天混元灵根",
      blood_marked: false,
      pill_exp_mult: 1
    };

    let expPct = 88;
    if (s.exp && s.exp.includes("/")) {
      const parts = s.exp.replace(/,/g, "").split("/");
      const cur = parseFloat(parts[0]) || 0;
      const max = parseFloat(parts[1]) || 1;
      expPct = Math.min(100, Math.max(0, Math.round((cur / max) * 100)));
    }
    const rInfo = parseRealmInfo(s.realm);

    const isMed = s.is_meditating || s.meditating || false;
    const sc = state.sanctum || (state.sanctum = {
      springCharge: 92,
      herbsGrowth: 78,
      herbsRemainHours: 2,
      craneStatus: "idle",
      craneRemainSec: 0,
      craneDest: "",
      meditateMinutes: 0,
    });

    const recentFeeds = state.feed.slice(-4).reverse();
    const feedItems = recentFeeds.length > 0 ? recentFeeds.map((f) => `
      <div class="relative pl-5 pb-3 border-l-2 border-jade-300">
        <span class="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-jade-600 ring-2 ring-white"></span>
        <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
          <span class="font-mono text-slate-600">【${esc(f.time || "辰时")}】</span>
          <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 font-medium">因果显现</span>
        </div>
        <p class="text-xs text-slate-700 leading-relaxed">${esc(f.text)}</p>
      </div>
    `).join("") : `
      <div class="relative pl-5 pb-2 border-l-2 border-jade-300">
        <span class="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-jade-600 ring-2 ring-white"></span>
        <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
          <span class="font-mono text-slate-600">【辰时三刻】</span>
          <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 font-medium">+善缘 +10</span>
        </div>
        <p class="text-xs text-slate-700 leading-relaxed">道友今日于洞天参悟天工密卷，偶有所得，神识通达，道心温润。</p>
      </div>
      <div class="relative pl-5 pb-2 border-l-2 border-jade-300">
        <span class="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-filigree-500 ring-2 ring-white"></span>
        <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
          <span class="font-mono text-slate-600">【巳时初候】</span>
          <span class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-800 font-medium">天地演化</span>
        </div>
        <p class="text-xs text-slate-700 leading-relaxed">西荒黑风绝渊赤焰喷涌，世界疤痕显现，隐有上古凶煞降世！</p>
      </div>
    `;

    return `
    <div class="w-full flex flex-col gap-6">
      <!-- 顶部仙山云海全景画卷 (纯净自然原画，绝无人物面板文字重影) -->
      <div class="relative w-full rounded-2xl overflow-hidden shadow-md bg-slate-900 min-h-[220px] flex items-end p-6 border border-filigree-400/40"
           style="background-image: url('https://lh3.googleusercontent.com/aida-public/AB6AXuDNggPj4AGHEqJhe9iU83W1YRePfLywRJ7izNYtV_guyNEVqy7wQCWSumM2RgEu1kUnoyaikSEY-4SyTljW3XGa4F-PpCPhS2XZUu2FcCLSuDUIfpFod_Zq6GqTrXe6sC95V-CphUFf06CtaOlJjWAVAxJXnjE8GqkVaXB_XhscGY01nQqO74k7IpR9jKWef8souqUFhVB3FOswfEnnmemhgTWavzOyAlZbbXvjzStRAEsuAiZrQHRwI0GhLD7ImwJ_NSGyUhC5fQGa'); background-size: cover; background-position: center 35%;">
        <div class="absolute inset-0 bg-gradient-to-t from-jade-950/90 via-jade-950/40 to-transparent"></div>
        <div class="relative z-10 w-full flex flex-col md:flex-row items-start md:items-end justify-between gap-4">
          <div class="space-y-1.5">
            <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/20 backdrop-blur-md text-emerald-200 text-xs font-medium border border-white/20">
              <span class="text-xs">🌅</span>
              <span>洞天福地 · 太素第七重微界</span>
            </div>
            <h1 class="text-2xl sm:text-3xl font-bold text-white tracking-widest drop-shadow-md">
              九天碧虚洞府 · 乾坤枢机
            </h1>
            <p class="text-xs sm:text-sm text-jade-100/90 max-w-xl leading-relaxed">
              日出扶桑，紫气东渐三千里。聚灵法阵周天运转，灵泉温润，道友灵神已与主峰地脉相契。
            </p>
          </div>
          <div class="flex items-center gap-3.5 bg-white/90 backdrop-blur-md px-4 py-2.5 rounded-xl shadow-md border border-filigree-400/40">
            <div class="flex flex-col text-right">
              <span class="text-[11px] text-slate-500 font-medium">灵气浓度</span>
              <span class="text-sm font-bold text-jade-900">九品上极 · 灵潮充沛</span>
            </div>
            <div class="w-9 h-9 rounded-full bg-jade-100 flex items-center justify-center text-jade-700 text-base">
              <span>💧</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 12 栏主网格：左 4 栏修士本命玉牌，右 8 栏仙府运转万象图 -->
      <div class="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <!-- ================= 左栏：修士本命玉牌与立绘 (4 Cols) ================= -->
        <div class="xl:col-span-4 flex flex-col gap-5">
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-4 relative overflow-hidden">
            <!-- 头部：本命玉牌名号与道阶角标 -->
            <div class="flex items-start justify-between relative z-10">
              <div class="flex items-center gap-2.5">
                <div class="w-2 h-6 rounded-sm bg-jade-700"></div>
                <div>
                  <span class="text-[11px] text-slate-500 uppercase tracking-wider block">修士本命玉牌</span>
                  <span class="text-base font-bold text-jade-950 tracking-wide">${esc(s.name || "太素仙尊 · 顾青玄")}</span>
                </div>
              </div>
              <div class="flex flex-col items-center justify-center px-2 py-1 rounded-lg bg-jade-50 border border-jade-200 shadow-2xs">
                <span class="text-[10px] text-filigree-700 font-semibold">道阶</span>
                <span class="text-xs font-bold text-jade-800">${esc((s.realm || "化神").slice(0, 2))}</span>
              </div>
            </div>

            <!-- 真人仙风立绘 (Stitch 原生原画，彻底告别单字大圆圈) -->
            <div class="relative w-full h-56 rounded-xl overflow-hidden bg-slate-900 shadow-inner group ${isMed ? 'meditating-glow' : ''}">
              <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuC92R2mr6xU9UHjsRfuNu3g2Zp1nBIKlcuhjOOX4E208W0CQffLkq5NTks8DeAIDsPOnVZbhDC1Mw62UweMhOUr4Yweo6-Yl-XPj4lwbwZFGJ63SwOYGC-RtjclNtB3dHecCgeTHMMT1eO4GmNfkAky--4kxkAtzNBdmq6UYa2m9spz5HL4uyaacOnjLcntHyq6q-seoNoZkWP2hCKkTbDp6Lu2immHkKZwYuf4NdsMbeQZAamMXQtxcA"
                   class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                   alt="太素仙尊道身真影" />
              <div class="absolute inset-0 bg-gradient-to-t from-jade-950/85 via-transparent to-transparent"></div>
              <div class="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between px-3 py-1.5 rounded-lg bg-white/85 backdrop-blur-md shadow-xs">
                <span class="text-xs text-jade-950 font-medium">${isMed ? '【周天运化吐纳中】' : `当前境界：${esc(s.realm || "化神后期")}`}</span>
                <span class="text-xs text-filigree-700 font-bold">${isMed ? '静室锁闭' : '登仙第玖阶'}</span>
              </div>
            </div>

            <!-- 破境九转金环进度 -->
            <div class="p-3 bg-white/80 rounded-xl border border-jade-200/80 shadow-2xs flex items-center gap-3.5">
              <div class="relative w-12 h-12 flex-shrink-0 flex items-center justify-center">
                <svg class="w-12 h-12 transform -rotate-90" viewBox="0 0 36 36">
                  <path class="text-jade-100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" stroke-width="3.2"></path>
                  <path class="text-filigree-500 stroke-current" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke-dasharray="${expPct}, 100" stroke-linecap="round" stroke-width="3.2"></path>
                </svg>
                <span class="absolute text-[11px] font-bold text-jade-900 font-mono">${expPct}%</span>
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex justify-between items-center text-xs">
                  <span class="text-slate-600 font-medium">${esc(rInfo.currentName)} 进境</span>
                  <span class="text-jade-800 font-bold font-mono">${esc(s.exp || "0 / 100")}</span>
                </div>
                <div class="w-full bg-jade-100 h-1.5 rounded-full mt-1.5 overflow-hidden">
                  <div class="bg-gradient-to-r from-jade-600 to-filigree-500 h-full rounded-full" style="width: ${expPct}%"></div>
                </div>
                <div class="mt-1 flex items-center gap-1 text-[11px] text-filigree-700 truncate">
                  <span>✨</span>
                  <span>${rInfo.isMajorBreakthrough ? (expPct >= 100 ? '天劫已至：可引动九天雷劫迎抗天命' : '大圆满引劫：尚需积蓄真元方可迎抗天命') : (expPct >= 100 ? '真元盈满：经脉畅通可顿悟晋阶' : '周天运化：打坐吐纳稳步精进')}</span>
                </div>
              </div>
            </div>

            <!-- 五行道韵与天元灵根星图 -->
            <div class="bg-jade-50/70 rounded-xl p-3.5 space-y-2 border border-jade-100">
              <div class="flex items-center justify-between">
                <span class="text-xs text-jade-900 font-bold flex items-center gap-1">
                  <span>🌿</span>
                  <span>五行道韵与天元灵根</span>
                </span>
                <span class="text-[10px] px-2 py-0.5 rounded bg-jade-200/80 text-jade-800 font-medium">先天混元</span>
              </div>
              <div class="grid grid-cols-2 gap-2 text-xs pt-1">
                <div class="flex items-center justify-between px-2.5 py-1.5 bg-white/80 rounded-lg border border-jade-100">
                  <span class="text-slate-600 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-jade-600"></span>天品水灵根
                  </span>
                  <span class="font-bold text-jade-900 font-mono">96%</span>
                </div>
                <div class="flex items-center justify-between px-2.5 py-1.5 bg-white/80 rounded-lg border border-jade-100">
                  <span class="text-slate-600 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>变异九霄雷
                  </span>
                  <span class="font-bold text-filigree-700 font-mono">84%</span>
                </div>
                <div class="flex items-center justify-between px-2.5 py-1.5 bg-white/80 rounded-lg border border-jade-100">
                  <span class="text-slate-600 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>青木长生骨
                  </span>
                  <span class="font-bold text-jade-900 font-mono">74%</span>
                </div>
                <div class="flex items-center justify-between px-2.5 py-1.5 bg-white/80 rounded-lg border border-jade-100">
                  <span class="text-slate-600 flex items-center gap-1.5">
                    <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>玄金锐气
                  </span>
                  <span class="font-bold text-slate-700 font-mono">58%</span>
                </div>
              </div>
            </div>

            <!-- 因果天平 · 道心气象 -->
            <div class="bg-white/80 rounded-xl p-3 border border-jade-200/80 space-y-2">
              <div class="flex items-center justify-between text-xs">
                <span class="font-bold text-jade-900 flex items-center gap-1">
                  <span>⚖️ 因果天平 · 道心气象</span>
                </span>
                <span class="text-[11px] text-jade-700 font-medium">道心无垢</span>
              </div>
              <div class="grid grid-cols-2 gap-2 text-center text-xs">
                <div class="bg-jade-50 p-2 rounded-lg border border-jade-200">
                  <div class="text-[10px] text-slate-500">清净功德云霞</div>
                  <div class="text-sm font-bold text-jade-700 font-mono">+${s.merit || 3650}</div>
                </div>
                <div class="bg-rose-50 p-2 rounded-lg border border-rose-200">
                  <div class="text-[10px] text-slate-500">凡尘业力煞气</div>
                  <div class="text-sm font-bold text-rose-700 font-mono">-${s.sin || 120}</div>
                </div>
              </div>
              <div class="grid grid-cols-3 gap-1.5 text-[11px] text-slate-600 pt-1 text-center">
                <div class="bg-slate-50 py-1 rounded">命禄寿元 <strong class="text-jade-900">${Number(s.rem_years || 145).toFixed(0)}载</strong></div>
                <div class="bg-slate-50 py-1 rounded">神识感召 <strong class="text-jade-900">4,850步</strong></div>
                <div class="bg-slate-50 py-1 rounded">宗门道勋 <strong class="text-filigree-700">太上长老</strong></div>
              </div>
            </div>

            <!-- 本命温养法宝卡 -->
            <div class="rounded-xl overflow-hidden border border-filigree-400/40 bg-gradient-to-r from-jade-900 to-slate-900 p-3 text-white relative">
              <div class="flex items-center justify-between text-xs mb-1.5">
                <span class="text-filigree-300 font-semibold flex items-center gap-1">
                  <span>🛡️ 本命温养法宝</span>
                </span>
                <span class="px-1.5 py-0.2 rounded bg-filigree-500/20 text-filigree-300 border border-filigree-400/30 text-[10px]">地阶温灵 · 九转</span>
              </div>
              <div class="flex items-center justify-between">
                <div>
                  <h4 class="text-sm font-bold text-white tracking-wide">九天碧玉太虚剑</h4>
                  <div class="text-[10px] text-jade-300 mt-0.5">剑灵觉醒：太虚玄青雀</div>
                </div>
                <div class="text-right">
                  <span class="text-[10px] text-slate-400">锋芒</span>
                  <div class="text-sm font-bold text-filigree-300 font-mono">9,880</div>
                </div>
              </div>
            </div>

            <!-- 核心交互动作组 -->
            <div class="grid grid-cols-3 gap-2 pt-1">
              <button type="button" class="py-2.5 px-2 rounded-lg ${isMed ? 'bg-amber-600 hover:bg-amber-700 animate-pulse' : 'bg-jade-700 hover:bg-jade-800'} text-white text-xs font-semibold shadow-sm transition flex items-center justify-center gap-1 cursor-pointer" data-sanctum-act="meditate_toggle">
                <span>🧘</span>
                <span>${isMed ? "收功出关" : "入定闭关"}</span>
              </button>
              <button type="button" class="py-2.5 px-2 rounded-lg ${expPct >= 100 ? 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white border border-amber-400 ring-2 ring-amber-300 animate-pulse' : 'bg-slate-100 hover:bg-slate-200 text-slate-500 border border-slate-300'} text-xs font-semibold shadow-sm transition flex items-center justify-center gap-1 cursor-pointer" data-sanctum-act="breakthrough" title="${expPct >= 100 ? '修为圆满，可发起突破' : '修为未满，点击查看差额'}">
                <span>⚡</span>
                <span>${expPct >= 100 ? (rInfo.isMajorBreakthrough ? "引雷渡劫" : "顺畅晋阶") : `破境 (${expPct}%)`}</span>
              </button>
              <button type="button" class="py-2.5 px-2 rounded-lg bg-white/90 hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-semibold shadow-2xs transition flex items-center justify-center gap-1 cursor-pointer" data-cmd="/look">
                <span>👁️</span>
                <span>观照道身</span>
              </button>
            </div>
          </div>
        </div>

        <!-- ================= 右栏：仙府运转万象图 (8 Cols) ================= -->
        <div class="xl:col-span-8 flex flex-col gap-5">
          <!-- 仙府运转总览卷轴 -->
          <div class="jade-panel rounded-2xl p-6 shadow-sm border border-jade-200/90 relative">
            <div class="flex items-center justify-between pb-3 mb-4 border-b border-jade-200/80">
              <div>
                <div class="text-[11px] text-slate-400">卷次 · 洞府营造总览 / 天命甲辰四百二十卷</div>
                <h2 class="text-lg font-bold text-jade-950 tracking-wide mt-0.5">仙府运转万象图</h2>
              </div>
              <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-jade-100 border border-jade-300 text-[11px] text-jade-800 font-medium">
                <span class="w-2 h-2 rounded-full bg-jade-600 animate-pulse"></span>
                <span>护山大阵: 太乙两仪生灭阵 · 稳固</span>
              </div>
            </div>

            <!-- 三大设施卡：玄冰灵泉、紫菁草园、镇山仙鹤 -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <!-- 设施 1：玄冰九曲灵泉 -->
              <div class="p-3.5 bg-white/80 rounded-xl border border-jade-200 shadow-2xs flex flex-col justify-between">
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <span class="w-7 h-7 rounded-lg bg-jade-100 text-jade-700 flex items-center justify-center text-xs">🌊</span>
                    <span class="text-[10px] px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 font-medium">产出倍率 +180%</span>
                  </div>
                  <h3 class="text-sm font-bold text-jade-950">玄冰九曲灵泉</h3>
                  <p class="text-xs text-slate-600 mt-1 line-clamp-2">地下地阴玄水汇聚而成，当前注满【玄冰灵液】7,400升，可助突破心魔。</p>
                </div>
                <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
                  <span class="text-[11px] text-slate-500">储液充盈度 <strong class="text-jade-800 font-mono">${sc.springCharge}%</strong></span>
                  <button type="button" class="px-2.5 py-1 rounded ${sc.springCharge >= 10 ? 'bg-jade-700 hover:bg-jade-800 text-white cursor-pointer' : 'bg-slate-200 text-slate-400 cursor-not-allowed'} text-[11px] font-medium" data-sanctum-act="spring">
                    ${sc.springCharge >= 10 ? '提取灵露' : '蓄液中…'}
                  </button>
                </div>
              </div>

              <!-- 设施 2：紫菁九叶草园 -->
              <div class="p-3.5 bg-white/80 rounded-xl border border-jade-200 shadow-2xs flex flex-col justify-between">
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <span class="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center text-xs">🌿</span>
                    <span class="text-[10px] px-1.5 py-0.2 rounded ${sc.herbsGrowth >= 100 ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'} font-medium">
                      ${sc.herbsGrowth >= 100 ? '芝草已成熟' : `尚余 ${sc.herbsRemainHours || 2} 时辰成熟`}
                    </span>
                  </div>
                  <h3 class="text-sm font-bold text-jade-950">紫菁九叶草园</h3>
                  <p class="text-xs text-slate-600 mt-1 line-clamp-2">沐浴晨曦朝露，已孕育千年仙品芝草三株，采摘后可炼制【九转还魂丹】。</p>
                </div>
                <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
                  <span class="text-[11px] text-slate-500">地脉灵蕴滋养 <strong class="text-filigree-700 font-mono">${sc.herbsGrowth}%</strong></span>
                  <button type="button" class="px-2.5 py-1 rounded bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-[11px] font-medium cursor-pointer" data-sanctum-act="herbs">
                    ${sc.herbsGrowth >= 100 ? '采摘仙草' : '照料药圃'}
                  </button>
                </div>
              </div>

              <!-- 设施 3：镇山灵兽 · 青羽仙鹤 -->
              ${(() => {
                const pendingItem = (sc && sc.cranePendingItem) || (state.status && state.status.crane_pending_item);
                const isScouting = sc.craneStatus === 'scouting';
                return `
                <div class="p-3.5 ${pendingItem ? 'bg-gradient-to-b from-amber-50/90 to-white border-amber-300 shadow-sm' : 'bg-white/80 border-jade-200'} rounded-xl border shadow-2xs flex flex-col justify-between">
                  <div>
                    <div class="flex items-center justify-between mb-2">
                      <span class="w-7 h-7 rounded-lg ${pendingItem ? 'bg-amber-100 text-amber-800' : 'bg-jade-100 text-jade-700'} flex items-center justify-center text-xs">🕊️</span>
                      <span class="text-[10px] px-1.5 py-0.2 rounded font-medium ${
                        pendingItem
                          ? 'bg-amber-100 text-amber-900 border border-amber-300 animate-pulse'
                          : (isScouting ? 'bg-amber-100 text-amber-800' : 'bg-jade-100 text-jade-800')
                      }">
                        ${pendingItem ? '衔宝归巢 · 待取机缘' : (isScouting ? '八荒远巡中' : '灵鹤守护中')}
                      </span>
                    </div>
                    <h3 class="text-sm font-bold text-jade-950">镇山灵兽 · 青羽仙鹤</h3>
                    <p class="text-xs text-slate-600 mt-1 line-clamp-2">
                      ${pendingItem
                        ? `仙鹤破云归巢，灵囊暂存【<strong class="text-amber-900">${esc(pendingItem.name)}</strong>】！百宝纳戒腾出空位后可随时取下。`
                        : (isScouting
                            ? `青羽仙鹤正于【${esc(sc.craneDest || '大荒')}】远巡破空，寻找天机秘宝！`
                            : '今日巡弋南溟归来，神识传音：“东南千里赤霞蒸腾，似有上古洞府秘宝现世。”')}
                    </p>
                  </div>
                  <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
                    <span class="text-[11px] text-slate-500">
                      ${pendingItem
                        ? `灵禽宝囊 <strong class="text-amber-800 font-bold">${esc(pendingItem.tierName || '地品')}</strong>`
                        : (isScouting
                            ? `远巡【${esc(sc.craneDest || '秘境')}】 <strong class="text-jade-800 font-medium">余 ${sc.craneRemainSec} 息</strong>`
                            : '警戒度 <strong class="text-jade-800 font-medium">极佳</strong>')}
                    </span>
                    ${pendingItem
                      ? `<button type="button" class="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-bold shadow-xs cursor-pointer" data-sanctum-act="crane_claim">领取仙物</button>`
                      : `<button type="button" class="px-2.5 py-1 rounded ${isScouting ? 'bg-amber-100 text-amber-800 border border-amber-300 cursor-wait' : 'bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 cursor-pointer'} text-[11px] font-medium" data-sanctum-act="crane">
                          ${isScouting ? '巡弋中…' : '命灵鹤探路'}
                        </button>`
                    }
                  </div>
                </div>`;
              })()}
            </div>

            <!-- 天机推演条 -->
            <div class="mt-4 p-3 bg-gradient-to-r from-jade-50 via-white to-amber-50 rounded-xl border border-jade-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-lg bg-jade-800 text-filigree-300 flex items-center justify-center font-calligraphy text-base font-bold shadow-2xs">
                  廿一
                </div>
                <div>
                  <div class="text-xs font-bold text-jade-950 flex items-center gap-2">
                    <span>天机推演 · 芒种岁星入亢宿</span>
                    <span class="text-[10px] text-filigree-700">[大吉 · 宜纳气]</span>
                  </div>
                  <div class="text-[11px] text-slate-600 mt-0.5">
                    <span class="text-jade-700 font-semibold">【宜】</span>引雷淬体、双修论道、洗练灵剑 &nbsp;|&nbsp;
                    <span class="text-rose-700 font-semibold">【忌】</span>强开死关、轻动杀念
                  </div>
                </div>
              </div>
              <button type="button" class="text-xs text-jade-700 hover:text-jade-900 font-semibold flex items-center gap-1 min-w-max cursor-pointer" data-sanctum-act="astro">
                <span>观星推演全图</span>
                <span>➔</span>
              </button>
            </div>
          </div>

          <!-- 洞府内廷：静室蒲团、乾坤金库与仙途因果纪事 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 乾坤金库与静室操作 -->
            <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-4">
              <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
                <h3 class="text-sm font-bold text-jade-950 flex items-center gap-1.5">
                  <span>🏛️ 乾坤金库与洞府行止</span>
                </h3>
                <span class="text-xs text-filigree-700 font-medium">大阵庇护 · 不可掠夺</span>
              </div>
              <div class="p-3 bg-white/80 rounded-xl border border-jade-100 text-xs space-y-2">
                <div class="flex justify-between items-center">
                  <span class="text-slate-500">随身灵石：</span>
                  <span class="font-bold text-jade-900 font-mono">${s.stones || 520} 灵石</span>
                </div>
                <div class="flex justify-between items-center">
                  <span class="text-slate-500">金库储积：</span>
                  <span class="font-bold text-filigree-700 font-mono">${s.vault || 1600} 灵石</span>
                </div>
                <div class="flex gap-2 pt-1">
                  <button type="button" class="flex-1 py-1.5 rounded bg-jade-700 hover:bg-jade-800 text-white text-xs font-medium cursor-pointer" data-sanctum-act="vault_deposit">存入百石</button>
                  <button type="button" class="flex-1 py-1.5 rounded bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-medium cursor-pointer" data-sanctum-act="vault_withdraw">支取百石</button>
                </div>
              </div>
              <div class="p-3 bg-white/80 rounded-xl border border-jade-100 text-xs space-y-2">
                <div class="flex justify-between items-center">
                  <span class="font-bold text-jade-950">静室蒲团 · 锁门闭关</span>
                  <span class="text-slate-500">${isMed ? "闭关入定中" : "神完气足"}</span>
                </div>
                <div class="flex gap-2 pt-1">
                  <button type="button" class="flex-1 py-1.5 rounded ${isMed ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : 'bg-jade-700 hover:bg-jade-800 text-white cursor-pointer'} text-xs font-medium" data-sanctum-act="meditate_enter">闭关一刻</button>
                  <button type="button" class="flex-1 py-1.5 rounded ${isMed ? 'bg-amber-600 hover:bg-amber-700 text-white cursor-pointer animate-pulse' : 'bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 cursor-pointer'} text-xs font-medium" data-sanctum-act="meditate_leave">收功出关</button>
                </div>
              </div>
            </div>

            <!-- 仙途行止 · 因果纪事 -->
            <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-3">
              <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
                <h3 class="text-sm font-bold text-jade-950 flex items-center gap-1.5">
                  <span>📜 仙途行止 · 因果纪事</span>
                </h3>
                <div class="flex gap-1.5">
                  <button type="button" class="px-2 py-0.5 rounded bg-jade-100 hover:bg-jade-200 text-jade-800 text-[11px] font-medium cursor-pointer" data-cmd="/任务">修行指引</button>
                  <button type="button" class="px-2 py-0.5 rounded bg-jade-100 hover:bg-jade-200 text-jade-800 text-[11px] font-medium cursor-pointer" data-cmd="/世情">观照世情</button>
                </div>
              </div>
              <div class="space-y-3 pt-1">
                ${feedItems}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 十方大荒秘境探险图卷与动态遭遇战控制器
  // ==========================================================================
  const WILDERNESS_TARGETS = {
    "野外山原": {
      name: "野外山原",
      zone: "落霞灵脉外围",
      tierName: "凡阶九品 · 入门历练",
      dangerPct: 22,
      dangerDesc: "微波无害",
      dropRate: 9,
      staminaCost: 15,
      powerMin: 60,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuDNggPj4AGHEqJhe9iU83W1YRePfLywRJ7izNYtV_guyNEVqy7wQCWSumM2RgEu1kUnoyaikSEY-4SyTljW3XGa4F-PpCPhS2XZUu2FcCLSuDUIfpFod_Zq6GqTrXe6sC95V-CphUFf06CtaOlJjWAVAxJXnjE8GqkVaXB_XhscGY01nQqO74k7IpR9jKWef8souqUFhVB3FOswfEnnmemhgTWavzOyAlZbbXvjzStRAEsuAiZrQHRwI0GhLD7ImwJ_NSGyUhC5fQGa",
      beast: {
        name: "白额青鬃兽",
        avatar: "🐺",
        title: "山野凶兽 · 凡阶中品",
        lore: "盘踞山原外围的成年灵兽，皮毛似青铜，齿爪锋利，擅借密林隐匿扑袭。",
        power: 85,
      },
      rewards: [
        { name: "凝气丹 五枚", kind: "consumable", tier: 1, tierName: "凡品", desc: "炼化周天微量真元之初阶灵丹。" },
        { name: "九叶野芝", kind: "material", tier: 1, tierName: "凡品", desc: "野生采撷之草药，可炼制培元丹。" },
        { name: "青木残卷", kind: "material", tier: 2, tierName: "人品", desc: "记载草木通灵诀窍的残旧经帛。" },
      ]
    },
    "落霞古洞": {
      name: "落霞古洞",
      zone: "落霞荒泽深处",
      tierName: "玄阶上品 · 仙家古迹",
      dangerPct: 35,
      dangerDesc: "暗藏禁制",
      dropRate: 18,
      staminaCost: 25,
      powerMin: 200,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx",
      beast: {
        name: "守洞玄猿",
        avatar: "🦍",
        title: "通灵古兽 · 玄阶上品",
        lore: "通晓粗浅五行棍法的灵猿，镇守落霞灵泉禁制，双臂具千钧神力。",
        power: 280,
      },
      rewards: [
        { name: "落霞玉露", kind: "consumable", tier: 2, tierName: "人品", desc: "落霞古洞灵泉凝结之甘露，饮之涤荡经络。" },
        { name: "破境清心丹", kind: "pill", tier: 2, tierName: "人品", desc: "突破小阶时宁心定志，护御识海灵台。" },
        { name: "古修真经残页", kind: "material", tier: 3, tierName: "地品", desc: "古修洞府遗存之黄庭经文真意碎片。" },
      ]
    },
    "黑风绝渊": {
      name: "黑风绝渊",
      zone: "西荒绝壁之渊",
      tierName: "地阶中品 · 罡风天堑",
      dangerPct: 55,
      dangerDesc: "罡风裂魂",
      dropRate: 30,
      staminaCost: 35,
      powerMin: 800,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuDBrs5mCoUskHEbq1GlHOnBx7XWlud9-v5oIgbGeyYxe2ZzY4l3wRW1M1CTwwi8pFnX89v6X9ntxxBARx9Cb4Ql__nMwtBuQAYh-jEEtkSUo33eUdV59LGotu4vUq2__xsR-HnpMSLLev1Z7qwBpPGQmHxq04_AmEZpElihjyukTLNy9R-_Ypl69spuWXf7KoGj03iHgd1b8L-HVibTt72FDChjhuGY75UCephhoygFbX595WE_AWkDjio-wxN2z5AtO-zQuSGpJ-nk",
      beast: {
        name: "九幽冥风蝠",
        avatar: "🦇",
        title: "冥煞凶魔 · 地阶中品",
        lore: "深渊九天罡风煞气孕育的嗜血蝠王，双翼掀动黑风魔刃，能噬修士神识。",
        power: 950,
      },
      rewards: [
        { name: "玄冥风晶", kind: "material", tier: 3, tierName: "地品", desc: "九幽罡风凝结的风灵结晶，炼制飞剑之极品法材。" },
        { name: "地阶洗髓液", kind: "consumable", tier: 3, tierName: "地品", desc: "伐毛洗髓灵液，重塑肉身经脉道基。" },
        { name: "幽冥秘藏舆图", kind: "treasure_map", tier: 3, tierName: "地品", desc: "指引西荒绝壁下太古剑冢的天机舆图。" },
      ]
    },
    "万星遗迹": {
      name: "万星遗迹",
      zone: "东海遗存残界",
      tierName: "天阶绝境 · 上古仙阙",
      dangerPct: 70,
      dangerDesc: "十死一生",
      dropRate: 40,
      staminaCost: 50,
      powerMin: 2500,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuBbPOc8iM9b6MSMEI4lwWSqB16hzd1Hi4uor0XBPRt27QwOU-ZbBNZrbDjllObF13h_ontpANtf5BFwy8f9oM8gwa8BHesL_031HYxJRLDdD3Sh4He0-KflozAkqRWqa4mrCxGo5pKYOPuE2aypwkSNXu3iXGzdBTuCFwNFQRH0I8lfC3bsilMTemAfzWBWmQG6qrIBL3Vpp3rFksluu8Do6I10_Rl8dy4iDGXe699GlKoa0Uz7TO_Dg5TQ177c8CjpZvSyM-YuZSQ-",
      beast: {
        name: "太古剑煞傀儡",
        avatar: "⚔️",
        title: "仙阙守卫 · 天阶通玄",
        lore: "上古剑宗大阵遗留的太古陨铁傀儡，身负残存九霄剑意，遇生灵即斩。",
        power: 3200,
      },
      rewards: [
        { name: "混沌星核", kind: "material", tier: 4, tierName: "天品", desc: "星辰陨落残片，蕴含鸿蒙混沌初开之灵力。" },
        { name: "万星天命剑胎", kind: "equip", tier: 4, tierName: "天品", slot: "weapon", slotCn: "绝世神兵", desc: "汲取万星光芒孕育的本命剑胎。" },
        { name: "天道藏宝全图", kind: "treasure_map", tier: 4, tierName: "天品", desc: "直通上古仙阙核心宝库的天道全景图卷。" },
      ]
    },
  };

  function resolveWildernessTarget(rawName) {
    const s = String(rawName || "野外山原").trim();
    for (const k in WILDERNESS_TARGETS) {
      if (s.includes(k) || k.includes(s) || (k.includes("万星") && s.includes("万星"))) {
        return WILDERNESS_TARGETS[k];
      }
    }
    return WILDERNESS_TARGETS["野外山原"];
  }

  function handleWildernessAction(act, targetName, el) {
    const s = state.status || {};
    const isMed = s.is_meditating || s.meditating || false;

    // 门禁一：闭关阻断
    if (isMed) {
      toast("洞府大阵锁闭中：道友正入定吐纳，不可强行外出！", "bad");
      pushFeed("【洞府禁制】你正处于闭关入定状态，周天紫气运化中，洞府大阵锁闭。请先在洞府中【收功出关】再踏入十方大荒！", "bad");
      return;
    }

    // 门禁二：盘缠校验 (必须 >= 20 灵石)
    if ((s.stones || 0) < 20) {
      toast("随身灵石不足 20，盘缠短缺无法启程！", "bad");
      pushFeed(`【盘缠告急】大荒路远凶险，需备足 20 灵石盘缠以催动神行法器。当前囊中仅余 ${s.stones || 0} 灵石，请先至坊市或金库支取！`, "bad");
      return;
    }

    const target = resolveWildernessTarget(targetName);
    const rInfo = parseRealmInfo(s.realm);

    // 扣除盘缠 20 灵石
    s.stones = Math.max(0, (s.stones || 0) - 20);
    renderBody();

    openJadeDialog({
      title: "十方灵墟 · 秘境探险图卷",
      icon: "🧭",
      cardClass: "max-w-xl",
      bodyHtml: `
        <div class="space-y-4" id="adventureStageBox">
          <div class="relative w-full h-40 rounded-xl overflow-hidden bg-slate-900 border border-jade-300 shadow-sm">
            <img src="${target.image}" class="w-full h-full object-cover transition-transform duration-700 hover:scale-105" alt="${esc(target.name)}" />
            <div class="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-transparent to-black/30"></div>
            <div class="absolute top-2.5 left-2.5 flex items-center gap-1.5">
              <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-jade-950/90 text-jade-200 border border-jade-500/40">${esc(target.tierName)}</span>
              <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/90 text-amber-950">凶险度 ${target.dangerPct}% (${esc(target.dangerDesc)})</span>
            </div>
            <div class="absolute bottom-2.5 left-2.5 right-2.5 flex items-end justify-between text-white">
              <div>
                <h3 class="text-lg font-bold tracking-wide">${esc(target.name)}</h3>
                <p class="text-xs text-jade-200">${esc(target.zone)}</p>
              </div>
              <div class="text-right text-[11px] text-amber-300 font-mono">
                <span>盘缠已付: 20 灵石</span>
              </div>
            </div>
          </div>

          <!-- 探险动态演进容器 -->
          <div id="advStepContainer" class="p-4 rounded-xl bg-slate-900 text-amber-200 font-mono text-xs space-y-2 border border-amber-400/60 shadow-inner">
            <div class="flex items-center gap-2 text-amber-400 font-bold text-sm">
              <span class="animate-spin">🌀</span>
              <span id="advStageTitle">御风飞遁 · 破云寻幽中……</span>
            </div>
            <p class="text-slate-300 text-xs leading-relaxed" id="advStageDesc">
              催动神行法器，破开重重云海罡风，周遭天地灵气激荡，正深入【${esc(target.name)}】秘境腹地……
            </p>
          </div>
        </div>
      `,
      footerHtml: `
        <div id="advFooterActions" class="w-full flex items-center justify-between">
          <span class="text-xs text-slate-500 font-mono" id="advStatusText">秘境推演进行中……</span>
          <button type="button" class="px-4 py-2 rounded-xl bg-slate-200 text-slate-500 text-xs font-medium cursor-not-allowed" id="btnAdvAction" disabled>
            静候机缘
          </button>
        </div>
      `,
      onMount: (overlay) => {
        const titleEl = overlay.querySelector("#advStageTitle");
        const descEl = overlay.querySelector("#advStageDesc");
        const boxEl = overlay.querySelector("#adventureStageBox");
        const footerEl = overlay.querySelector("#advFooterActions");

        // 阶段一：破云寻幽 (历时 700ms 切换至遭遇斗法)
        setTimeout(() => {
          if (!document.body.contains(overlay)) return;
          if (titleEl) titleEl.textContent = `妖兽突袭 · 遭遇【${target.beast.name}】！`;
          if (descEl) {
            descEl.innerHTML = `
              <div class="flex items-center gap-3 p-2.5 bg-slate-800/80 rounded-lg border border-rose-500/40 my-1 combat-clash">
                <span class="text-3xl">${target.beast.avatar}</span>
                <div>
                  <div class="text-xs font-bold text-rose-300">${esc(target.beast.title)} · ${esc(target.beast.name)}</div>
                  <div class="text-[11px] text-slate-300 leading-normal">${esc(target.beast.lore)}</div>
                </div>
              </div>
              <div class="text-amber-300 font-sans text-xs pt-1">
                ⚡ 剑气激荡！法宝与兽爪轰鸣碰撞，双方真元暴烈对决……
              </div>
            `;
          }
        }, 800);

        // 阶段二：天道裁决与战利品结算 (历时 2000ms)
        setTimeout(async () => {
          if (!document.body.contains(overlay)) return;

          let isWin = false;
          let expGain = 0;
          let stonesGain = 0;
          let droppedItems = [];
          let narrative = "";

          if (!state.demo) {
            // 联机模式：向服务端调用 /探险
            try {
              const res = await api("/action", { token: state.token, command: `/探险 ${target.name}` });
              if (res.status) applyStatus(res.status);
              if (res.adventure) {
                isWin = !!res.adventure.combat_success;
                expGain = res.adventure.exp_delta || 0;
                stonesGain = res.adventure.stones_delta || 0;
                narrative = res.adventure.narrative || res.text;
                droppedItems = res.adventure.loot || [];
              } else {
                isWin = !!res.ok;
                narrative = res.text || "";
              }
            } catch (err) {
              isWin = false;
              narrative = "神识传音受阻：" + err.message;
            }
          } else {
            // Demo 离线模式：规则权威裁决
            const p = Math.max(0.2, Math.min(0.92, 1.0 - (target.dangerPct / 100) + (rInfo.majorIndex * 0.08)));
            isWin = Math.random() < p;

            if (isWin) {
              expGain = Math.round(180 * (1 + rInfo.majorIndex * 0.4) * (1 + target.dangerPct / 100));
              stonesGain = Math.floor(Math.random() * 30) + 15;

              // 经验增长
              if (s.exp && s.exp.includes("/")) {
                const parts = s.exp.replace(/,/g, "").split("/");
                let cur = parseFloat(parts[0]) || 0;
                let max = parseFloat(parts[1]) || 1;
                cur = Math.min(max, cur + expGain);
                s.exp = `${cur.toLocaleString()} / ${parts[1].trim()}`;
              }
              s.stones = (s.stones || 0) + stonesGain;

              // 战利品判定：首次探险 100% 保底掉落藏宝图
              ensureDefaultInventory();
              const hasFoundMap = state.hasFoundMap || state.inventory.some(x => x.kind === "treasure_map" || (x.name && x.name.includes("图")));
              const rollMap = !hasFoundMap || (Math.random() < (target.dropRate / 100));

              if (rollMap) {
                state.hasFoundMap = true;
                const mapTier = Math.min(5, Math.max(1, rInfo.majorIndex + 1));
                const tName = ["凡品", "人品", "地品", "天品", "仙品"][mapTier - 1] || "地品";
                const newMap = {
                  uid: "map_" + Date.now(),
                  name: `${target.name}古修遗图[${target.name}灵穴]`,
                  kind: "treasure_map",
                  slotCn: "天机秘宝图卷",
                  tier: mapTier,
                  tierName: tName,
                  iconGlyph: "图",
                  targetNodeName: `${target.name}深处灵穴`,
                  archetypeCn: "坎水五行破阵",
                  coords: "丙午方位 · 离火宫 南行三十里 古修士遗府",
                  riddle: "五行倒悬，阴阳同炉。阵眼匿于地脉灵穴最深处，非晓生克之道者不可轻启。",
                  lore: `自【${target.name}】斩获的上古修士随身秘藏图卷，泛着幽微灵光。`,
                  qty: 1,
                };
                droppedItems.push(newMap);
                state.inventory.unshift(newMap);
              }

              // 常规灵物掉落一件
              const reg = target.rewards[Math.floor(Math.random() * target.rewards.length)];
              if (reg) {
                const regItem = Object.assign({ uid: "item_" + Date.now(), qty: 1 }, reg);
                droppedItems.push(regItem);
                state.inventory.unshift(regItem);
              }

              narrative = `【秘境大捷】你在【${target.name}】阵斩凶兽【${target.beast.name}】，破开古禁制，气运通达！`;
            } else {
              // 失败：真元轻微受挫
              expGain = -40;
              narrative = `【秘境负伤】妖兽【${target.beast.name}】煞气滔天，你护体罡气碎裂，狼狈遁出秘境，受轻微震荡！`;
            }
          }

          // 呈现结果面板
          if (boxEl) {
            if (isWin) {
              boxEl.innerHTML = `
                <div class="text-center space-y-3 py-2">
                  <div class="w-14 h-14 rounded-full bg-gradient-to-tr from-amber-400 to-amber-200 text-amber-950 flex items-center justify-center text-3xl mx-auto shadow-md victory-glow">
                    🏆
                  </div>
                  <h4 class="text-base font-bold text-jade-950">斩妖破阵 · 凯旋大捷</h4>
                  <p class="text-xs text-slate-600 leading-relaxed max-w-md mx-auto">
                    ${esc(narrative)}
                  </p>

                  <div class="grid grid-cols-2 gap-2 text-xs max-w-sm mx-auto pt-1">
                    <div class="p-2.5 rounded-xl bg-jade-50 border border-jade-200 flex items-center justify-between">
                      <span class="text-slate-600">周天真元：</span>
                      <strong class="text-jade-900 font-mono">+${expGain.toLocaleString()} 点</strong>
                    </div>
                    <div class="p-2.5 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-between">
                      <span class="text-slate-600">拾得灵石：</span>
                      <strong class="text-filigree-700 font-mono">+${stonesGain} 灵石</strong>
                    </div>
                  </div>

                  <!-- 战利品列表 -->
                  <div class="p-3 bg-white rounded-xl border border-jade-200 space-y-2 text-left max-w-md mx-auto">
                    <div class="text-xs font-bold text-jade-950 flex items-center justify-between">
                      <span>拾获天材地宝与机缘：</span>
                      <span class="text-[10px] text-jade-700 font-medium">已落账入纳戒</span>
                    </div>
                    <div class="space-y-1.5">
                      ${droppedItems.map(it => `
                        <div class="flex items-center justify-between p-2 rounded-lg ${it.kind === 'treasure_map' ? 'bg-amber-50/90 border border-amber-300 ring-1 ring-amber-300/40' : 'bg-slate-50 border border-slate-200'} text-xs">
                          <div class="flex items-center gap-2">
                            <span class="font-calligraphy font-bold text-sm ${it.kind === 'treasure_map' ? 'text-amber-800' : 'text-jade-800'}">${it.kind === 'treasure_map' ? '📜' : '💎'}</span>
                            <span class="font-bold text-slate-900">${esc(it.name)}</span>
                            <span class="text-[10px] px-1 rounded ${it.kind === 'treasure_map' ? 'bg-amber-200 text-amber-900 font-bold' : 'bg-jade-100 text-jade-800'}">${esc(it.tierName || '凡品')}</span>
                          </div>
                          ${it.kind === 'treasure_map' ? '<span class="text-[10px] text-amber-900 font-bold">★ 藏宝图卷</span>' : '<span class="text-[10px] text-slate-500">数量 x1</span>'}
                        </div>
                      `).join("")}
                    </div>
                  </div>
                </div>
              `;

              toast(`秘境大捷：真元+${expGain}，战利品已入纳戒！`, "gold");
              pushFeed(`【大荒探险 · 凯旋】你在【${target.name}】斩妖破阵，得获真元+${expGain}、灵石+${stonesGain}，珍宝已落账百宝纳戒！`, "ok");
            } else {
              boxEl.innerHTML = `
                <div class="text-center space-y-3 py-2">
                  <div class="w-14 h-14 rounded-full bg-rose-100 text-rose-800 flex items-center justify-center text-3xl mx-auto shadow-sm">
                    💥
                  </div>
                  <h4 class="text-base font-bold text-rose-950">力战不敌 · 败退回山</h4>
                  <p class="text-xs text-slate-600 leading-relaxed max-w-md mx-auto">
                    ${esc(narrative)}
                  </p>
                  <div class="p-3 bg-rose-50/80 rounded-xl border border-rose-200 text-xs text-rose-900 space-y-1 max-w-sm mx-auto text-left">
                    <div>• 护体法宝黯淡，随身真元震荡跌落：<strong>-40 点</strong></div>
                    <div>• 盘缠 20 灵石已耗于大荒路程中</div>
                    <div>• 道友可先回洞府入定吐纳温养道躯，稍后再启程迎战！</div>
                  </div>
                </div>
              `;

              toast("秘境凶险，力战负伤遁回！", "bad");
              pushFeed(`【大荒探险 · 败退】你在【${target.name}】遭遇妖兽重击，负伤遁出，周天真元微损！`, "bad");
            }
          }

          if (footerEl) {
            const hasMap = droppedItems.some(x => x.kind === "treasure_map");
            footerEl.innerHTML = `
              <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
                稳固道心
              </button>
              <div class="flex items-center gap-2">
                ${hasMap ? `
                  <button type="button" class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5" id="btnGoBagAfterAdv">
                    <span>🧭</span>
                    <span>前往纳戒研读宝图</span>
                  </button>
                ` : `
                  <button type="button" class="px-5 py-2.5 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-sm cursor-pointer" onclick="workbench.closeJadeDialog()">
                    重整旗鼓
                  </button>
                `}
              </div>
            `;

            const goBagBtn = footerEl.querySelector("#btnGoBagAfterAdv");
            if (goBagBtn) {
              goBagBtn.addEventListener("click", () => {
                closeJadeDialog();
                state.bagFilter = "treasure_map";
                state.selectedItemIndex = 0;
                setView("inventory");
                toast("已入百宝纳戒：天机藏宝图卷已定盘就绪！", "gold");
              });
            }
          }

          renderBody();
        }, 2000);
      },
    });
  }

  // ==========================================================================
  // 主境二：【十方大荒 · 秘境探险图卷】 (Wilderness) - Stitch 原生 1:1 高保真
  // ==========================================================================
  function renderWilderness() {
    const curLoc = (state.status && state.status.location) || "落霞山灵泉";

    return `
    <div class="w-full flex flex-col gap-5">
      <!-- 顶部界隙天痕异变条 (Top Dynamic Alert Banner) -->
      <section class="w-full" data-purpose="world-scar-alert">
        <div class="relative overflow-hidden rounded-xl border border-rose-300/80 bg-gradient-to-r from-rose-50/95 via-amber-50/90 to-jade-50/80 p-3 sm:p-4 shadow-sm">
          <div class="relative flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div class="flex flex-wrap items-center gap-3">
              <div class="flex items-center gap-2">
                <span class="relative flex h-3 w-3">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-3 w-3 bg-rose-600"></span>
                </span>
                <h2 class="text-sm sm:text-base font-bold text-rose-950 flex items-center gap-1.5">
                  <span>【界隙天痕异变】</span>
                  <span class="text-rose-700">赤焰火海 · 地脉狂暴涌动</span>
                </h2>
              </div>
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-rose-600/10 text-rose-700 border border-rose-500/30">
                极度凶险 · 煞气侵蚀 +45%
              </span>
              <div class="text-xs text-slate-600 flex items-center gap-2 bg-white/70 px-2.5 py-1 rounded-md border border-rose-200">
                <span>周天灵气稀释因子: <strong class="text-rose-700 font-mono">0.62倍</strong></span>
                <span class="text-slate-300">|</span>
                <span class="text-amber-800">火毒炽盛，水系法宝消耗+20%</span>
              </div>
            </div>
            <div class="flex items-center gap-3 self-end md:self-auto">
              <button class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-jade-700 text-white text-xs font-medium hover:bg-jade-800 transition-all shadow-sm border border-filigree-400/40 cursor-pointer" type="button" data-cmd="/佩戴 九天避火佩">
                <span>🛡️</span>
                <span>佩戴【九天避火佩】抵御煞气</span>
              </button>
              <div class="text-xs text-slate-500 bg-white/80 px-2.5 py-1 rounded-md border border-slate-200 flex items-center gap-1.5">
                <span>距地脉灵潮逆转: <span class="font-mono font-semibold text-rose-800">02时48分</span></span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 12 栏主结构：左 8 栏 2x2 秘境大卡，右 4 栏大荒实纪探险行纪 -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- 左侧 8 栏：秘境目录与 2x2 探索卡片 -->
        <section class="lg:col-span-8 flex flex-col gap-5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-jade-200/80">
            <div class="flex items-center gap-3">
              <div class="w-1.5 h-6 rounded-full bg-gradient-to-b from-filigree-400 to-jade-700"></div>
              <h1 class="text-xl font-bold text-jade-950 flex items-center gap-2">
                <span>十方灵墟 · 秘境图卷探幽</span>
                <span class="text-xs font-normal text-slate-500 hidden sm:inline">（探索上古封印与洞天福地）</span>
              </h1>
            </div>
            <div class="flex items-center gap-1.5 overflow-x-auto text-xs pb-1 sm:pb-0">
              <button class="px-3 py-1 rounded-full bg-jade-700 text-white font-medium shadow-sm cursor-pointer whitespace-nowrap">全部秘境</button>
              <button class="px-3 py-1 rounded-full bg-white/80 hover:bg-jade-100 text-slate-600 border border-jade-200 font-medium transition cursor-pointer whitespace-nowrap">初阶机缘</button>
              <button class="px-3 py-1 rounded-full bg-white/80 hover:bg-jade-100 text-slate-600 border border-jade-200 font-medium transition cursor-pointer whitespace-nowrap">天道险关</button>
              <button class="px-3 py-1 rounded-full bg-white/80 hover:bg-jade-100 text-slate-600 border border-jade-200 font-medium transition cursor-pointer whitespace-nowrap">已开辟地图 (12/36)</button>
            </div>
          </div>

          <!-- 2x2 秘境卡片网格 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 卡片 1: 野外山原 -->
            <article class="jade-panel jade-panel-hover rounded-xl overflow-hidden flex flex-col border border-jade-200 shadow-sm relative group">
              <div class="relative h-44 w-full overflow-hidden bg-slate-900">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuDNggPj4AGHEqJhe9iU83W1YRePfLywRJ7izNYtV_guyNEVqy7wQCWSumM2RgEu1kUnoyaikSEY-4SyTljW3XGa4F-PpCPhS2XZUu2FcCLSuDUIfpFod_Zq6GqTrXe6sC95V-CphUFf06CtaOlJjWAVAxJXnjE8GqkVaXB_XhscGY01nQqO74k7IpR9jKWef8souqUFhVB3FOswfEnnmemhgTWavzOyAlZbbXvjzStRAEsuAiZrQHRwI0GhLD7ImwJ_NSGyUhC5fQGa"
                     class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" alt="野外山原" />
                <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-black/30"></div>
                <div class="absolute top-3 left-3 flex flex-wrap gap-1.5">
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-jade-900/80 text-jade-100 border border-jade-500/40 backdrop-blur-sm">凡阶九品 · 入门历练</span>
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-filigree-500/90 text-amber-950 border border-filigree-300 shadow-sm">★ 初探必得保底</span>
                </div>
                <div class="absolute bottom-2.5 left-3 right-3 flex items-end justify-between text-white">
                  <div>
                    <h3 class="text-lg font-bold tracking-wide">野外山原</h3>
                    <p class="text-xs text-jade-200">落霞灵脉外围</p>
                  </div>
                  <div class="text-right">
                    <span class="text-[11px] text-slate-300">藏宝残图掉落率</span>
                    <div class="text-sm font-bold text-filigree-300 font-mono">9%</div>
                  </div>
                </div>
              </div>
              <div class="p-4 flex-1 flex flex-col justify-between gap-3">
                <div>
                  <div class="flex items-center justify-between text-xs mb-1.5">
                    <span class="text-slate-500 flex items-center gap-1">
                      <span>凶险程度</span>
                      <span class="font-bold text-jade-700">微波无害</span>
                    </span>
                    <span class="font-mono font-semibold text-jade-800">22%</span>
                  </div>
                  <div class="w-full h-1.5 bg-jade-100 rounded-full overflow-hidden">
                    <div class="bg-gradient-to-r from-jade-500 to-jade-600 h-full rounded-full" style="width: 22%"></div>
                  </div>
                  <p class="mt-2.5 text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    适合温养初生道心，群山连绵云雾轻绕，采撷野生朱果与凡阶凝气草绝佳之地。
                  </p>
                </div>
                <div class="bg-jade-50/70 p-2.5 rounded-lg border border-jade-100">
                  <span class="text-[11px] text-slate-500 block mb-1.5 font-medium">产出珍物预视:</span>
                  <div class="flex items-center gap-2">
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">凝气丹 五枚</span>
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">九叶野芝</span>
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-filigree-700 font-medium">青木残卷</span>
                  </div>
                </div>
                <button class="w-full py-2.5 px-4 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-sm border border-filigree-400/30 cursor-pointer" type="button" data-wild-act="adventure" data-target="野外山原" data-cmd="/探险 野外山原">
                  <span>启程赴险</span>
                  <span class="text-[11px] font-normal text-jade-200">（耗神行 15点）</span>
                </button>
              </div>
            </article>

            <!-- 卡片 2: 落霞古洞 -->
            <article class="jade-panel jade-panel-hover rounded-xl overflow-hidden flex flex-col border border-jade-200 shadow-sm relative group">
              <div class="relative h-44 w-full overflow-hidden bg-slate-900">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx"
                     class="w-full h-full object-cover object-left transition-transform duration-700 group-hover:scale-105" alt="落霞古洞" />
                <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-black/30"></div>
                <div class="absolute top-3 left-3 flex flex-wrap gap-1.5">
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-900/85 text-emerald-100 border border-emerald-400/40 backdrop-blur-sm">玄阶上品 · 仙家古迹</span>
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-jade-700/85 text-white border border-jade-400/40">★ 灵泉充裕</span>
                </div>
                <div class="absolute bottom-2.5 left-3 right-3 flex items-end justify-between text-white">
                  <div>
                    <h3 class="text-lg font-bold tracking-wide">落霞古洞</h3>
                    <p class="text-xs text-amber-200">落霞荒泽深处</p>
                  </div>
                  <div class="text-right">
                    <span class="text-[11px] text-slate-300">藏宝残图掉落率</span>
                    <div class="text-sm font-bold text-filigree-300 font-mono">18%</div>
                  </div>
                </div>
              </div>
              <div class="p-4 flex-1 flex flex-col justify-between gap-3">
                <div>
                  <div class="flex items-center justify-between text-xs mb-1.5">
                    <span class="text-slate-500 flex items-center gap-1">
                      <span>凶险程度</span>
                      <span class="font-bold text-amber-700">暗藏禁制</span>
                    </span>
                    <span class="font-mono font-semibold text-amber-700">35%</span>
                  </div>
                  <div class="w-full h-1.5 bg-jade-100 rounded-full overflow-hidden">
                    <div class="bg-gradient-to-r from-jade-600 via-amber-500 to-amber-600 h-full rounded-full" style="width: 35%"></div>
                  </div>
                  <p class="mt-2.5 text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    洞藏【千年落霞玉泉】，可淬炼肉身骨骼，洞深处有守洞玄猿栖息，暗合玄奥奇阵。
                  </p>
                </div>
                <div class="bg-jade-50/70 p-2.5 rounded-lg border border-jade-100">
                  <span class="text-[11px] text-slate-500 block mb-1.5 font-medium">产出珍物预视:</span>
                  <div class="flex items-center gap-2">
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">落霞玉露</span>
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">破境清心丹</span>
                    <span class="px-2 py-1 bg-white rounded border border-filigree-300 text-xs text-filigree-800 font-semibold">古修真经残页</span>
                  </div>
                </div>
                <button class="w-full py-2.5 px-4 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-sm border border-filigree-400/30 cursor-pointer" type="button" data-wild-act="adventure" data-target="落霞古洞" data-cmd="/探险 落霞古洞">
                  <span>启程赴险</span>
                  <span class="text-[11px] font-normal text-jade-200">（耗神行 25点）</span>
                </button>
              </div>
            </article>

            <!-- 卡片 3: 黑风绝渊裂隙 -->
            <article class="jade-panel jade-panel-hover rounded-xl overflow-hidden flex flex-col border border-jade-200 shadow-sm relative group">
              <div class="relative h-44 w-full overflow-hidden bg-slate-900">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuDBrs5mCoUskHEbq1GlHOnBx7XWlud9-v5oIgbGeyYxe2ZzY4l3wRW1M1CTwwi8pFnX89v6X9ntxxBARx9Cb4Ql__nMwtBuQAYh-jEEtkSUo33eUdV59LGotu4vUq2__xsR-HnpMSLLev1Z7qwBpPGQmHxq04_AmEZpElihjyukTLNy9R-_Ypl69spuWXf7KoGj03iHgd1b8L-HVibTt72FDChjhuGY75UCephhoygFbX595WE_AWkDjio-wxN2z5AtO-zQuSGpJ-nk"
                     class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" alt="黑风绝渊裂隙" />
                <div class="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-transparent to-black/30"></div>
                <div class="absolute top-3 left-3 flex flex-wrap gap-1.5">
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-stone-900/85 text-amber-200 border border-amber-500/40 backdrop-blur-sm">地阶中品 · 罡风天堑</span>
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-900/80 text-rose-200 border border-rose-400/40">道阶: 筑基二重+</span>
                </div>
                <div class="absolute bottom-2.5 left-3 right-3 flex items-end justify-between text-white">
                  <div>
                    <h3 class="text-lg font-bold tracking-wide">黑风绝渊裂隙</h3>
                    <p class="text-xs text-stone-300">西荒绝壁之渊</p>
                  </div>
                  <div class="text-right">
                    <span class="text-[11px] text-slate-300">藏宝残图掉落率</span>
                    <div class="text-sm font-bold text-filigree-300 font-mono">30%</div>
                  </div>
                </div>
              </div>
              <div class="p-4 flex-1 flex flex-col justify-between gap-3">
                <div>
                  <div class="flex items-center justify-between text-xs mb-1.5">
                    <span class="text-slate-500 flex items-center gap-1">
                      <span>凶险程度</span>
                      <span class="font-bold text-amber-800">罡风裂魂</span>
                    </span>
                    <span class="font-mono font-semibold text-amber-800">55%</span>
                  </div>
                  <div class="w-full h-1.5 bg-jade-100 rounded-full overflow-hidden">
                    <div class="bg-gradient-to-r from-amber-500 to-amber-700 h-full rounded-full" style="width: 55%"></div>
                  </div>
                  <p class="mt-2.5 text-xs text-slate-600 line-clamp-2 leading-relaxed">
                    九天罡风呼啸凛冽，出产极寒玄冥阴玉。凡躯难抗，埋葬前朝万剑冢与嗜血妖兽。
                  </p>
                </div>
                <div class="bg-jade-50/70 p-2.5 rounded-lg border border-jade-100">
                  <span class="text-[11px] text-slate-500 block mb-1.5 font-medium">产出珍物预视:</span>
                  <div class="flex items-center gap-2">
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">玄冥风晶</span>
                    <span class="px-2 py-1 bg-white rounded border border-jade-200 text-xs text-jade-900 font-medium">地阶洗髓液</span>
                    <span class="px-2 py-1 bg-white rounded border border-filigree-300 text-xs text-filigree-800 font-semibold">幽冥秘藏舆图</span>
                  </div>
                </div>
                <button class="w-full py-2.5 px-4 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-sm border border-filigree-400/30 cursor-pointer" type="button" data-wild-act="adventure" data-target="黑风绝渊" data-cmd="/探险 黑风绝渊">
                  <span>启程赴险</span>
                  <span class="text-[11px] font-normal text-jade-200">(耗神行 35)</span>
                </button>
              </div>
            </article>

            <!-- 卡片 4: 万星遗迹残址 -->
            <article class="jade-panel jade-panel-hover rounded-xl overflow-hidden flex flex-col border-2 border-filigree-400/60 shadow-md relative group bg-gradient-to-b from-white/90 via-jade-50/30 to-amber-50/20">
              <div class="absolute top-0 right-0 z-20 overflow-hidden w-28 h-28 pointer-events-none">
                <div class="bg-gradient-to-r from-filigree-600 to-amber-400 text-white font-bold text-[9px] py-1 text-center rotate-45 transform translate-x-8 translate-y-4 shadow-sm tracking-widest">
                  绝境天阶
                </div>
              </div>
              <div class="relative h-44 w-full overflow-hidden bg-slate-950">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuBbPOc8iM9b6MSMEI4lwWSqB16hzd1Hi4uor0XBPRt27QwOU-ZbBNZrbDjllObF13h_ontpANtf5BFwy8f9oM8gwa8BHesL_031HYxJRLDdD3Sh4He0-KflozAkqRWqa4mrCxGo5pKYOPuE2aypwkSNXu3iXGzdBTuCFwNFQRH0I8lfC3bsilMTemAfzWBWmQG6qrIBL3Vpp3rFksluu8Do6I10_Rl8dy4iDGXe699GlKoa0Uz7TO_Dg5TQ177c8CjpZvSyM-YuZSQ-"
                     class="w-full h-full object-cover object-right transition-transform duration-700 group-hover:scale-105" alt="万星遗迹残址" />
                <div class="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-slate-900/20 to-black/30"></div>
                <div class="absolute top-3 left-3 flex flex-wrap gap-1.5 z-10">
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-950/90 text-filigree-300 border border-filigree-400/60 backdrop-blur-sm">天阶绝境 · 上古仙阙</span>
                  <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-900/90 text-rose-200 border border-rose-400/40">⚡ 伴生九霄紫雷</span>
                </div>
                <div class="absolute bottom-2.5 left-3 right-3 flex items-end justify-between text-white z-10">
                  <div>
                    <h3 class="text-lg font-bold tracking-wide text-filigree-200">万星遗迹残址</h3>
                    <p class="text-xs text-indigo-200">东海遗存残界</p>
                  </div>
                  <div class="text-right">
                    <span class="text-[11px] text-filigree-200">藏宝残图掉落率</span>
                    <div class="text-sm font-bold text-filigree-300 font-mono">40% (极高)</div>
                  </div>
                </div>
              </div>
              <div class="p-4 flex-1 flex flex-col justify-between gap-3">
                <div>
                  <div class="flex items-center justify-between text-xs mb-1.5">
                    <div class="flex items-center gap-1.5">
                      <span class="text-slate-500">凶险程度</span>
                      <span class="font-bold text-rose-700">十死一生</span>
                      <span class="text-[10px] px-1 bg-rose-100 text-rose-800 rounded">化神初期以上</span>
                    </div>
                    <span class="font-mono font-bold text-rose-700">70%</span>
                  </div>
                  <div class="w-full h-1.5 bg-jade-100 rounded-full overflow-hidden">
                    <div class="bg-gradient-to-r from-amber-500 via-rose-600 to-rose-700 h-full rounded-full" style="width: 70%"></div>
                  </div>
                  <p class="mt-2.5 text-xs text-slate-700 line-clamp-2 leading-relaxed">
                    星辰陨落之所，阵眼遗存混沌星核，传闻更有天道至宝剑胎镇守，煞气与仙光激荡！
                  </p>
                </div>
                <div class="bg-filigree-50/70 p-2.5 rounded-lg border border-filigree-200">
                  <span class="text-[11px] text-amber-800 block mb-1.5 font-medium">产出珍物预视:</span>
                  <div class="flex items-center gap-2">
                    <span class="px-2 py-1 bg-white rounded border border-filigree-300 text-xs text-amber-950 font-bold">混沌星核</span>
                    <span class="px-2 py-1 bg-white rounded border border-filigree-300 text-xs text-amber-950 font-bold">万星天命剑胎</span>
                    <span class="px-2 py-1 bg-gradient-to-r from-filigree-100 to-amber-200 rounded border border-filigree-400 text-xs text-filigree-900 font-bold">天道藏宝全图</span>
                  </div>
                </div>
                <button class="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-filigree-600 via-jade-700 to-jade-800 hover:from-filigree-500 hover:to-jade-700 text-white text-xs font-bold transition-all flex items-center justify-center gap-2 shadow-md border border-filigree-300 cursor-pointer" type="button" data-wild-act="adventure" data-target="万星遗迹" data-cmd="/探险 万星古岛">
                  <span>⚡ 破界出征</span>
                  <span class="text-[11px] font-normal text-filigree-200">(耗神行 50)</span>
                </button>
              </div>
            </article>
          </div>
        </section>

        <!-- 右侧 4 栏：大荒实纪 · 探险行纪 (Stitch 原生竹简风卷轴) -->
        <aside class="lg:col-span-4 flex flex-col">
          <div class="relative bg-parchment-50 border-2 border-filigree-400/50 rounded-2xl p-5 shadow-lg flex flex-col h-full min-h-[640px] overflow-hidden">
            <!-- 卷轴顶端轴心 -->
            <div class="absolute top-0 left-0 right-0 h-3 bg-gradient-to-r from-stone-700 via-amber-800 to-stone-700 border-b border-filigree-500 flex items-center justify-between px-6">
              <div class="w-4 h-1.5 bg-filigree-400 rounded-sm"></div>
              <div class="w-4 h-1.5 bg-filigree-400 rounded-sm"></div>
            </div>

            <!-- 行纪头部 -->
            <div class="pt-3 pb-3 border-b border-parchment-300 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-xl">📜</span>
                <div>
                  <h2 class="text-base font-bold text-stone-900 tracking-wide">大荒实纪 · 探险行纪</h2>
                  <p class="text-[11px] text-stone-500">八荒巡弋实时通微</p>
                </div>
              </div>
              <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-jade-100 border border-jade-300 text-[11px] text-jade-800 font-medium">
                <span class="w-2 h-2 rounded-full bg-jade-600 animate-ping"></span>
                <span>神识同频中</span>
              </div>
            </div>

            <!-- 当前探险状态盒 -->
            <div class="mt-3.5 p-3 bg-white/80 rounded-xl border border-parchment-300 text-xs shadow-2xs">
              <div class="flex items-center justify-between mb-1">
                <span class="text-slate-500">正在探查: <strong class="text-jade-900">${esc(curLoc)}</strong></span>
                <span class="text-[11px] font-mono text-filigree-700 font-bold">历时 01时24分</span>
              </div>
              <div class="flex items-center gap-1.5 text-slate-600">
                <span class="text-jade-600">🕊️</span>
                <span>灵宠【青羽仙鹤】随行护道 · 警戒度良好</span>
              </div>
            </div>

            <!-- 时间线故事流 -->
            <div class="mt-4 flex-1 overflow-y-auto pr-1 space-y-4 text-xs">
              <div class="relative pl-5 pb-2 border-l-2 border-jade-300">
                <span class="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-jade-600 ring-2 ring-white"></span>
                <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
                  <span class="font-mono text-slate-600">【辰时三刻】</span>
                  <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 font-medium">+善缘 +10</span>
                </div>
                <p class="text-slate-700 leading-relaxed">
                  偶遇散修行商，花费50灵石换得一株三百年黄精，道心微润，气机运转畅达。
                </p>
              </div>

              <div class="relative pl-5 pb-2 border-l-2 border-jade-300">
                <span class="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-filigree-500 ring-2 ring-white"></span>
                <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
                  <span class="font-mono text-slate-600">【巳时初候】</span>
                  <span class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-800 font-medium">神识 +15</span>
                </div>
                <p class="text-slate-700 leading-relaxed">
                  踏入古洞前厅，触发上古避尘符阵，仙鹤啼鸣示警，规避禁制陷阱！
                </p>
              </div>

              <div class="relative pl-5 pb-2 border-l-2 border-filigree-400">
                <span class="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-amber-600 ring-2 ring-white"></span>
                <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
                  <span class="font-mono text-slate-600">【午时一刻】</span>
                  <span class="px-1.5 py-0.2 rounded bg-filigree-200 text-filigree-900 font-bold">掉落奇珍</span>
                </div>
                <p class="text-slate-800 font-medium leading-relaxed">
                  斩杀三阶盘丝洞蛛，缴获<span class="text-jade-800 font-semibold">【碧玉丝囊】x2</span>，偶得<span class="text-filigree-700 font-bold underline">【藏宝残图·丙】一角</span>！
                </p>
              </div>

              <div class="relative pl-5 pb-2 border-l-2 border-rose-300">
                <span class="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-rose-600 ring-2 ring-white"></span>
                <div class="flex items-center justify-between text-[11px] text-slate-400 mb-0.5">
                  <span class="font-mono text-slate-600">【未时将至】</span>
                  <span class="px-1.5 py-0.2 rounded bg-rose-100 text-rose-800 font-medium">煞气侵袭</span>
                </div>
                <p class="text-slate-700 leading-relaxed">
                  遭遇地脉煞气涌动（赤焰天痕影响），真元护盾消耗12%，正服用【避火丹】稳固元神。
                </p>
              </div>
            </div>

            <!-- 底部行纪控制 -->
            <div class="pt-3 mt-2 border-t border-parchment-300 flex items-center justify-between text-xs">
              <span class="text-slate-500">神识投影视真: <strong class="text-jade-900">无损耗</strong></span>
              <button type="button" class="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 font-medium shadow-2xs cursor-pointer" data-cmd="/返回">
                召回化身 (提前归返)
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 主境三：【百宝纳戒 · 灵物宝匣与天机藏图】 (Inventory) - 纯正仙侠 · 绝无西文
  // ==========================================================================
  function ensureDefaultInventory() {
    if (state.inventoryInitialized) return;
    if (state.inventory && state.inventory.length > 0) {
      state.inventoryInitialized = true;
      return;
    }
    state.inventoryInitialized = true;
    state.inventory = [
      {
        uid: "item_sword_01",
        name: "斩煞青锋剑",
        kind: "equip",
        slot: "weapon",
        slotCn: "法宝器灵",
        tier: 3,
        tierName: "地品",
        iconGlyph: "剑",
        stats: { "攻伐威能": 160, "破甲穿透": 45 },
        affixes: [
          { name: "破煞", desc: "对附带煞气之邪修及妖兽伤害提升 35%" },
          { name: "嗜血", desc: "击中掠取生机，反哺自身气血 12 点" },
        ],
        durability: "92 / 100",
        lore: "前代剑修于黑风绝渊斩杀骨魔后以心头血淬炼，剑身隐现幽青流芒。",
      },
      {
        uid: "item_robe_01",
        name: "玄水避火道袍",
        kind: "equip",
        slot: "armor",
        slotCn: "防身宝衣",
        tier: 2,
        tierName: "人品",
        iconGlyph: "袍",
        stats: { "护身甲御": 90, "避火抗性": 50 },
        affixes: [
          { name: "固元", desc: "周天元气稳固，受击气血折损减免 20%" },
        ],
        durability: "100 / 100",
        lore: "以北海灵鲛之丝织就，水火不侵，纤尘不染。",
      },
      {
        uid: "item_jade_01",
        name: "天机寻龙古玉",
        kind: "equip",
        slot: "trinket",
        slotCn: "本命灵佩",
        tier: 4,
        tierName: "天品",
        iconGlyph: "玉",
        stats: { "神识念力": 120, "回气速度": 25 },
        affixes: [
          { name: "凝神", desc: "神识感应范围扩张一倍，打坐吐纳效率提升 30%" },
        ],
        durability: "88 / 100",
        lore: "蕴含太虚星象天演之术，佩于腰间常闻灵泉叮咚之仙音。",
      },
      {
        uid: "item_map_01",
        name: "天机密卷 · 坎水藏宝图",
        kind: "treasure_map",
        slotCn: "天机秘宝图卷",
        tier: 3,
        tierName: "地品",
        iconGlyph: "图",
        targetNodeName: "落霞山灵泉",
        archetypeCn: "坎水五行破阵",
        coords: "甲子方位 · 震木宫 东南二十里 地脉三丈",
        riddle: "五行倒悬，阴阳同炉。阵眼匿于【落霞山灵泉】灵穴最深处，非晓坎水生克之道者不可启。",
        lore: "此图自落霞风水脉络截取而出，纸帛泛黄，微透赤金水墨，记载前朝真仙遗府所在。",
      },
      {
        uid: "item_pill_01",
        name: "九转还阳丹",
        kind: "pill",
        slotCn: "救命神丹",
        tier: 2,
        tierName: "人品",
        iconGlyph: "丹",
        stats: { "延寿增气": 3 },
        affixes: [
          { name: "生肌", desc: "生死肉白骨，濒危坐化时可凭空添续寿元三年。" },
        ],
        lore: "采七七四十九味地脉灵芝，于八卦炉中文火慢煨百日方成。",
      },
      {
        uid: "item_mat_01",
        name: "太乙精金矿胚",
        kind: "material",
        slotCn: "炼器神材",
        tier: 1,
        tierName: "凡品",
        iconGlyph: "金",
        stats: { "重铸精纯": 15 },
        lore: "深埋地脉万载的精金矿胚，重铸法宝洗练破煞词缀之必备神材。",
      },
      {
        uid: "item_dew_01",
        name: "百年落霞玉露",
        kind: "pill",
        slotCn: "淬骨灵液",
        tier: 3,
        tierName: "地品",
        iconGlyph: "露",
        stats: { "肉身根骨": 20 },
        lore: "自落霞古洞灵钟乳尖滴落汇集而成，三百年仅得一小盅。",
      },
      {
        uid: "item_wind_01",
        name: "玄冥风晶灵胚",
        kind: "material",
        slotCn: "罡风神材",
        tier: 3,
        tierName: "地品",
        iconGlyph: "风",
        stats: { "破甲附魔": 30 },
        lore: "采自黑风绝渊裂隙最深处，遇风自鸣，锐利无当。",
      },
      {
        uid: "item_pill_02",
        name: "辟毒清元灵丹",
        kind: "pill",
        slotCn: "驱邪灵丹",
        tier: 2,
        tierName: "人品",
        iconGlyph: "清",
        stats: { "避毒护体": 40 },
        lore: "克制南瞻部洲大荒瘴气与火毒，服下后通体清凉。",
      },
      {
        uid: "item_scroll_01",
        name: "万星残卷星图",
        kind: "treasure_map",
        slotCn: "上古秘卷",
        tier: 4,
        tierName: "天品",
        iconGlyph: "星",
        targetNodeName: "万星古岛",
        archetypeCn: "上古星斗大阵",
        coords: "天罡北斗 · 摇光星位 东海尽头 虚空裂谷",
        riddle: "诸天列宿，浩浩星芒。欲开万星仙阙，须聚齐三宿星钥方得其门而入。",
        lore: "传闻自天外陨星遗迹拓印而来，抚之微有紫雷震颤。",
      },
      {
        uid: "item_array_01",
        name: "紫金离火阵盘",
        kind: "equip",
        slot: "weapon",
        slotCn: "护道阵盘",
        tier: 3,
        tierName: "地品",
        iconGlyph: "阵",
        stats: { "真火威能": 135, "阵法封锁": 50 },
        lore: "以纯阳赤金熔铸，布阵之时离火腾空，凡妖避易。",
      },
      {
        uid: "item_talisman_01",
        name: "太虚青木神符",
        kind: "material",
        slotCn: "御风灵符",
        tier: 1,
        tierName: "凡品",
        iconGlyph: "符",
        stats: { "神行遁速": 80 },
        lore: "引青木灵气绘制的千里飞遁符，遇险燃之可瞬息避退数十里。",
      },
    ];
  }

  // ==========================================================================
  // 本命三槽法宝穿戴与同槽替换控制器
  // ==========================================================================
  function handleEquipAction(act, itemName, el) {
    if (!state.equipped) state.equipped = [];
    const name = String(itemName || "").trim();
    if (!name) return;

    if (act === "equip") {
      ensureDefaultInventory();
      const itemIdx = state.inventory.findIndex(x => x.name === name || x.uid === name);
      if (itemIdx < 0) {
        toast(`纳戒中未寻得【${name}】`, "bad");
        return;
      }
      const item = state.inventory[itemIdx];
      // 校验是否为合法装备
      if (item.kind && item.kind !== "equip" && item.kind !== "weapon" && item.kind !== "armor" && item.kind !== "trinket" && !item.slot) {
        toast(`【${item.name}】非护道装备，不可佩戴入体！`, "bad");
        return;
      }

      // 推断槽位
      let slot = item.slot;
      if (!slot) {
        if (item.name.includes("甲") || item.name.includes("袍") || item.name.includes("衣")) slot = "armor";
        else if (item.name.includes("玉") || item.name.includes("佩") || item.name.includes("戒") || item.name.includes("珠")) slot = "trinket";
        else slot = "weapon";
        item.slot = slot;
      }

      // 同槽替换：若已有装备，先退回纳戒
      const existingIdx = state.equipped.findIndex(x => x.slot === slot);
      let replacedItem = null;
      if (existingIdx >= 0) {
        replacedItem = state.equipped.splice(existingIdx, 1)[0];
        state.inventory.push(replacedItem);
      }

      // 从纳戒移除并放入已装备
      state.inventory.splice(itemIdx, 1);
      state.equipped.push(item);
      state.selectedItemIndex = 0;

      const slotMap = { weapon: "本命法宝", armor: "防身道袍", trinket: "道心灵佩" };
      const slotCn = slotMap[slot] || "本命法宝";

      toast(`【法宝入体】已将【${item.name}】佩戴至${slotCn}槽位，周天战力暴涨！`, "gold");
      pushFeed(`【本命佩戴】道体法阵轰鸣，你祭起【${item.name}】（${slotCn}）纳归丹田，威能激荡！${replacedItem ? `原装备【${replacedItem.name}】已卸下归还纳戒。` : ''}`, "ok");

      if (!state.demo) {
        api("/action", { token: state.token, command: `/穿戴 ${item.name}` })
          .then(res => {
            if (res.status) applyStatus(res.status);
            if (res.text) pushFeed(res.text, res.ok ? "ok" : "bad");
          })
          .catch(err => toast("穿戴法宝神识受阻：" + err.message, "bad"));
      }
      renderBody();
      return;
    }

    if (act === "unequip") {
      const eqIdx = state.equipped.findIndex(x => x.name === name || x.uid === name);
      if (eqIdx < 0) {
        toast(`身上并未佩戴【${name}】`, "bad");
        return;
      }
      const removed = state.equipped.splice(eqIdx, 1)[0];
      ensureDefaultInventory();
      state.inventory.unshift(removed);

      toast(`【卸下法宝】已将【${removed.name}】卸下并收回百宝纳戒！`, "gold");
      pushFeed(`【法宝归戒】你收功敛气，将【${removed.name}】从道身卸下，收入乾坤纳戒妥善温养。`, "ok");

      if (!state.demo) {
        api("/action", { token: state.token, command: `/卸下 ${removed.name}` })
          .then(res => {
            if (res.status) applyStatus(res.status);
            if (res.text) pushFeed(res.text, res.ok ? "ok" : "bad");
          })
          .catch(err => toast("卸下法宝神识受阻：" + err.message, "bad"));
      }
      renderBody();
      return;
    }
  }

  // ==========================================================================
  // 天机秘宝 · 风水定盘五行破阵大典控制器
  // ==========================================================================
  function handleTreasureAction(act, mapName, el) {
    ensureDefaultInventory();
    const s = state.status || {};
    const isMed = s.is_meditating || s.meditating || false;

    // 门禁：闭关阻断
    if (isMed) {
      toast("洞府大阵锁闭中：道友正入定吐纳，不可强行外出寻宝！", "bad");
      pushFeed("【洞府禁制】你正处于闭关入定状态，洞府大阵锁闭。请先在洞府中【收功出关】再行依图寻宝！", "bad");
      return;
    }

    // 找到该藏宝图
    let mapIdx = -1;
    if (mapName) {
      mapIdx = state.inventory.findIndex(x => x.name === mapName || (x.kind === "treasure_map" && x.name.includes(mapName)));
    }
    if (mapIdx < 0) {
      mapIdx = state.inventory.findIndex(x => x.kind === "treasure_map" || String(x.name).includes("图"));
    }
    if (mapIdx < 0) {
      toast("纳戒中未寻得天机藏宝图卷！", "bad");
      pushFeed("【天机未显】你翻遍百宝纳戒，未见任何藏宝图卷。可先前往大荒探险寻获机缘！", "bad");
      return;
    }

    const tmap = state.inventory[mapIdx];
    const targetNode = tmap.targetNodeName || "落霞古洞灵穴";
    const archetype = tmap.archetypeCn || "坎水五行破阵";
    const coords = tmap.coords || "甲子方位 · 震木宫 东南二十里 地脉三丈";
    const riddle = tmap.riddle || "五行倒悬，阴阳同炉。阵眼匿于地脉灵穴最深处，非晓生克之道者不可轻启。";

    openJadeDialog({
      title: "天机秘宝 · 风水定盘五行破阵大典",
      icon: "🧭",
      cardClass: "max-w-xl",
      bodyHtml: `
        <div class="space-y-4" id="treasureStageBox">
          <div class="relative w-full h-40 rounded-xl overflow-hidden bg-slate-900 border border-amber-300 shadow-sm">
            <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx"
                 class="w-full h-full object-cover" alt="古修洞府遗穴" />
            <div class="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-transparent to-black/30"></div>
            <div class="absolute top-2.5 left-2.5 flex items-center gap-1.5">
              <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950/90 text-amber-200 border border-amber-500/40">${esc(tmap.tierName || '地品')} · ${esc(tmap.slotCn || '天机秘宝图卷')}</span>
              <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-jade-700/90 text-white">定盘已锁定</span>
            </div>
            <div class="absolute bottom-2.5 left-2.5 right-2.5 flex items-end justify-between text-white">
              <div>
                <h3 class="text-base font-bold tracking-wide">${esc(tmap.name)}</h3>
                <p class="text-xs text-amber-200">定位灵穴：${esc(targetNode)}</p>
              </div>
              <div class="text-right text-[11px] text-slate-300 font-mono">
                <span>[${esc(archetype)}]</span>
              </div>
            </div>
          </div>

          <div class="bg-amber-50/70 p-3.5 rounded-xl border border-amber-300/80 space-y-2 text-xs">
            <div class="flex items-center justify-between">
              <span class="font-bold text-amber-950">🧭 干支风水定盘方位</span>
              <span class="text-filigree-700 font-mono text-[11px]">${esc(coords)}</span>
            </div>
            <p class="text-[11px] text-amber-900/90 leading-relaxed italic bg-white/70 p-2 rounded-lg border border-amber-200">
              “${esc(riddle)}”
            </p>
          </div>

          <div class="p-3.5 bg-slate-900 text-amber-200 font-mono text-xs rounded-xl border border-amber-400/60 space-y-2">
            <div class="flex items-center justify-between text-amber-300 font-bold">
              <span>【古阵现世 · 阵眼异象】</span>
              <span class="text-[11px] text-rose-400">离火炽盛 · 暴烈火煞封死石门</span>
            </div>
            <p class="text-slate-300 text-xs leading-relaxed">
              地脉深处掘出一座青铜古仙石门，三千禁制流转，火煞如龙咆哮。请法旨决断破阵神道：
            </p>

            <div class="space-y-2 pt-1 font-sans text-xs">
              <label class="p-2.5 rounded-lg border border-jade-600/60 bg-slate-800/90 hover:bg-slate-800 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-2.5">
                  <input type="radio" name="puzzleChoice" value="water" checked class="text-jade-500" />
                  <div>
                    <div class="font-bold text-white">① 调运癸水真元 (以柔克刚 · 五行相克)</div>
                    <div class="text-[10px] text-slate-400">引纯阴玄水浇灌离火阵眼 · 成功率 92% · 耗真元 50 点</div>
                  </div>
                </div>
                <span class="text-emerald-400 font-bold text-[11px]">极稳健</span>
              </label>

              <label class="p-2.5 rounded-lg border border-amber-600/60 bg-slate-800/90 hover:bg-slate-800 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-2.5">
                  <input type="radio" name="puzzleChoice" value="force" class="text-amber-500" />
                  <div>
                    <div class="font-bold text-white">② 祭出本命神兵 (以力破巧 · 强轰阵眼)</div>
                    <div class="text-[10px] text-slate-400">祭出道体全部煞气强行破壁 · 成功率 75% · 依赖战力</div>
                  </div>
                </div>
                <span class="text-amber-400 font-bold text-[11px]">需战力</span>
              </label>

              <label class="p-2.5 rounded-lg border border-slate-600 bg-slate-800/90 hover:bg-slate-800 flex items-center justify-between cursor-pointer transition">
                <div class="flex items-center gap-2.5">
                  <input type="radio" name="puzzleChoice" value="earth" class="text-amber-500" />
                  <div>
                    <div class="font-bold text-white">③ 勾动戊土灵石 (土掩烈火 · 稳固道基)</div>
                    <div class="text-[10px] text-slate-400">注入地脉灵石化火生金 · 成功率 85% · 耗 30 灵石</div>
                  </div>
                </div>
                <span class="text-slate-300 font-bold text-[11px]">30 灵石</span>
              </label>
            </div>
          </div>
        </div>
      `,
      footerHtml: `
        <div id="treasureFooterActions" class="w-full flex items-center justify-between">
          <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
            暂罢寻宝
          </button>
          <button type="button" class="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5" id="btnExecuteDig">
            <span>⚡</span>
            <span>敕令五行破阵开匣</span>
          </button>
        </div>
      `,
      onMount: (overlay) => {
        const btn = overlay.querySelector("#btnExecuteDig");
        const boxEl = overlay.querySelector("#treasureStageBox");
        const footerEl = overlay.querySelector("#treasureFooterActions");

        if (btn) {
          btn.addEventListener("click", () => {
            btn.disabled = true;
            btn.classList.add("opacity-50");

            const choiceEl = overlay.querySelector("input[name='puzzleChoice']:checked");
            const choice = choiceEl ? choiceEl.value : "water";

            // 扣除成本判定
            if (choice === "earth" && (s.stones || 0) < 30) {
              toast("随身灵石不足 30，无法以戊土灵石化阵！", "bad");
              btn.disabled = false;
              btn.classList.remove("opacity-50");
              return;
            }
            if (choice === "earth") {
              s.stones = (s.stones || 0) - 30;
            }

            // 破阵动效展示
            if (boxEl) {
              boxEl.innerHTML = `
                <div class="text-center space-y-4 py-8 bg-slate-900 rounded-xl text-amber-300 font-mono border border-amber-400">
                  <div class="text-4xl animate-spin mx-auto w-12 h-12 flex items-center justify-center">☯️</div>
                  <div class="text-base font-bold text-amber-400 animate-pulse">五行阴阳归位 · 阵盘轰鸣运转</div>
                  <p class="text-xs text-slate-300 max-w-sm mx-auto leading-relaxed">
                    玄水激荡，真火渐熄，青铜石门三千符文逐一熄灭，古仙遗府禁制洞开……
                  </p>
                </div>
              `;
            }

            setTimeout(async () => {
              if (!document.body.contains(overlay)) return;

              let excavatedEquip = null;
              let dropPill = null;
              let stoneGain = 0;

              if (!state.demo) {
                // 联机模式：向服务端调用 /挖宝
                try {
                  const res = await api("/action", { token: state.token, command: `/挖宝 ${tmap.name}` });
                  if (res.status) applyStatus(res.status);
                  pushFeed(res.text, res.ok ? "ok" : "bad");
                } catch (err) {
                  toast("挖宝神识受阻：" + err.message, "bad");
                }
              }

              // Demo 模式或前端权威落账：从纳戒消耗宝图
              const curMapIdx = state.inventory.findIndex(x => x.uid === tmap.uid || x.name === tmap.name);
              if (curMapIdx >= 0) {
                state.inventory.splice(curMapIdx, 1);
              }

              // 掘出高阶神兵与灵药
              const equipTier = Math.max(2, tmap.tier || 3);
              const tName = ["凡品", "人品", "地品", "天品", "仙品"][equipTier - 1] || "地品";
              const weaponNames = ["斩龙古剑", "太乙玄天戈", "七星诛魔剑", "赤霄惊神刃"];
              const pickName = weaponNames[Math.floor(Math.random() * weaponNames.length)];

              excavatedEquip = {
                uid: "excavated_" + Date.now(),
                name: pickName,
                kind: "equip",
                slot: "weapon",
                slotCn: "绝世法宝",
                tier: equipTier,
                tierName: tName,
                iconGlyph: "剑",
                stats: {
                  "攻伐威能": equipTier >= 3 ? 180 : 90,
                  "真元贯通": equipTier >= 3 ? 120 : 60,
                },
                affixes: [
                  { name: "破煞", desc: "破除大荒妖兽护体罡气，造成 25% 真实伤害。" },
                  { name: "斩龙", desc: "对龙蛇鳞甲类凶兽额外造成 35% 威慑压制。" },
                ],
                lore: `自【${targetNode}】上古洞府密室石棺中发掘而出的古仙佩剑，锋芒毕露，隐隐有龙吟破空之声。`,
                qty: 1,
              };

              dropPill = {
                uid: "pill_" + Date.now(),
                name: "九转还魂真丹",
                kind: "pill",
                tier: 3,
                tierName: "地品",
                iconGlyph: "丹",
                desc: "上古秘藏中保存完好的绝品仙丹，服用可大补元气并辟除心魔火煞。",
                qty: 2,
              };

              stoneGain = Math.floor(Math.random() * 80) + 120;
              s.stones = (s.stones || 0) + stoneGain;

              state.inventory.unshift(dropPill);
              state.inventory.unshift(excavatedEquip);
              state.selectedItemIndex = 0;

              // 渲染开箱大捷结算面板
              if (boxEl) {
                boxEl.innerHTML = `
                  <div class="text-center space-y-3 py-2">
                    <div class="w-14 h-14 rounded-full bg-gradient-to-tr from-amber-400 to-amber-200 text-amber-950 flex items-center justify-center text-3xl mx-auto shadow-md victory-glow">
                      🌟
                    </div>
                    <h4 class="text-base font-bold text-jade-950">洞府石门大开 · 绝代天机现世</h4>
                    <p class="text-xs text-slate-600 leading-relaxed max-w-md mx-auto">
                      五行火煞尽破，你在【${esc(targetNode)}】深处掘出前朝金丹修士坐化遗蜕，开辟古仙宝匣，藏宝图气数尽化散入天地！
                    </p>

                    <div class="grid grid-cols-2 gap-2 text-xs max-w-sm mx-auto pt-1">
                      <div class="p-2 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-between">
                        <span class="text-slate-600">发掘灵石：</span>
                        <strong class="text-filigree-700 font-mono">+${stoneGain} 灵石</strong>
                      </div>
                      <div class="p-2 rounded-xl bg-jade-50 border border-jade-200 flex items-center justify-between">
                        <span class="text-slate-600">宝图消耗：</span>
                        <strong class="text-rose-700 font-medium">已消耗 -1</strong>
                      </div>
                    </div>

                    <!-- 掘得的神兵卡片 -->
                    <div class="p-3.5 bg-gradient-to-r from-amber-50 via-white to-amber-50 rounded-xl border-2 border-amber-400/80 shadow-sm text-left max-w-md mx-auto space-y-2">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2.5">
                          <span class="w-8 h-8 rounded-lg bg-jade-800 text-amber-300 font-calligraphy text-lg font-bold flex items-center justify-center shadow-2xs">剑</span>
                          <div>
                            <div class="text-sm font-bold text-jade-950">${esc(excavatedEquip.name)}</div>
                            <div class="text-[10px] text-amber-900 font-semibold">${esc(excavatedEquip.tierName)} · ${esc(excavatedEquip.slotCn)}</div>
                          </div>
                        </div>
                        <span class="text-xs font-bold text-rose-700 font-mono">攻伐 +${excavatedEquip.stats['攻伐威能']}</span>
                      </div>
                      <div class="text-[11px] text-slate-600 bg-white/90 p-2 rounded-lg border border-amber-200 leading-relaxed">
                        ${esc(excavatedEquip.lore)}
                      </div>
                      <div class="flex items-center gap-2 pt-0.5">
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300 font-bold">【破煞】词缀</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-900 border border-rose-300 font-bold">【斩龙】词缀</span>
                        <span class="text-[10px] text-slate-500 ml-auto">另得【九转还魂真丹】x2</span>
                      </div>
                    </div>
                  </div>
                `;

                toast(`破阵大捷：掘得【${excavatedEquip.name}】与灵石+${stoneGain}！已存入纳戒！`, "gold");
                pushFeed(`【天机破阵 · 开箱】你依照风水定盘在【${targetNode}】破除五行古阵，掘得【${excavatedEquip.name}】（${excavatedEquip.tierName}），宝图消耗，战利品已入纳戒！`, "ok");
              }

              if (footerEl) {
                footerEl.innerHTML = `
                  <button type="button" class="px-4 py-2 rounded-xl bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 text-xs font-medium cursor-pointer" onclick="workbench.closeJadeDialog()">
                    收入百宝纳戒
                  </button>
                  <button type="button" class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5" id="btnEquipNowAfterDig">
                    <span>⚔️</span>
                    <span>立即佩戴入体 · 运转周天</span>
                  </button>
                `;

                const equipBtn = footerEl.querySelector("#btnEquipNowAfterDig");
                if (equipBtn) {
                  equipBtn.addEventListener("click", () => {
                    closeJadeDialog();
                    handleEquipAction("equip", excavatedEquip.name);
                  });
                }
              }

              renderBody();
            }, 1400);
          });
        }
      },
    });
  }

  function renderInventory() {
    ensureDefaultInventory();
    const inv = state.inventory;
    const filter = state.bagFilter || "all";

    const filtered = inv.filter((it) => {
      if (filter === "all") return true;
      if (filter === "equip") return it.kind === "equip";
      if (filter === "pill") return it.kind === "pill" || it.kind === "consumable";
      if (filter === "material") return it.kind === "material";
      if (filter === "treasure_map") return it.kind === "treasure_map" || it.kind === "map" || String(it.name).includes("图");
      return true;
    });

    const activeIndex = Math.min(state.selectedItemIndex || 0, Math.max(0, filtered.length - 1));
    const sel = filtered[activeIndex] || filtered[0] || inv[0];

    if (!state.equipped) state.equipped = [];
    const eqList = state.equipped;

    const weaponEquip = eqList.find((x) => x.slot === "weapon") || { name: "空置法宝", tierName: "凡品", affixes: [] };
    const armorEquip = eqList.find((x) => x.slot === "armor") || { name: "空置道袍", tierName: "凡品", affixes: [] };
    const trinketEquip = eqList.find((x) => x.slot === "trinket") || { name: "空置灵佩", tierName: "凡品", affixes: [] };

    const weaponAffix = (weaponEquip.affixes && weaponEquip.affixes[0] && weaponEquip.affixes[0].name) || "破煞";
    const weaponSub = weaponEquip.name === "空置法宝" ? "法宝位 · 虚席以待" : `${weaponEquip.tierName || "凡品"} · ${weaponAffix}`;

    const armorAffix = (armorEquip.affixes && armorEquip.affixes[0] && armorEquip.affixes[0].name) || "固元";
    const armorSub = armorEquip.name === "空置道袍" ? "道袍位 · 虚席以待" : `${armorEquip.tierName || "凡品"} · ${armorAffix}`;

    const trinketAffix = (trinketEquip.affixes && trinketEquip.affixes[0] && trinketEquip.affixes[0].name) || "凝神";
    const trinketSub = trinketEquip.name === "空置灵佩" ? "灵佩位 · 虚席以待" : `${trinketEquip.tierName || "凡品"} · ${trinketAffix}`;

    const bagCells = filtered.map((it, idx) => {
      const isSel = it === sel;
      const tName = it.tierName ? it.tierName.slice(0, 1) : "凡";
      const glyph = it.iconGlyph || it.name.slice(0, 1);
      const isGold = it.tier >= 3;
      return `
      <div class="p-3 rounded-xl border ${isSel ? "border-filigree-400 bg-white shadow-md ring-2 ring-filigree-400/40" : "border-jade-200 bg-white/70 hover:bg-white hover:border-jade-400"} transition-all cursor-pointer flex flex-col items-center justify-between text-center relative group min-h-[96px]"
           data-bag-idx="${idx}" title="${esc(it.name)}">
        <span class="absolute top-1.5 left-1.5 text-[10px] px-1 rounded font-bold ${isGold ? "bg-amber-100 text-amber-900 border border-amber-300" : "bg-jade-100 text-jade-800"}">
          ${tName}
        </span>
        <div class="w-10 h-10 rounded-full ${isSel ? "bg-filigree-400/20 text-filigree-800" : "bg-jade-100/60 text-jade-800"} flex items-center justify-center font-calligraphy text-xl font-bold mt-1 shadow-2xs">
          ${glyph}
        </div>
        <div class="text-xs font-semibold text-slate-800 truncate w-full mt-2">${esc(it.name)}</div>
      </div>`;
    }).join("");

    let inspectorHtml = "";
    const isMapItem = sel && (sel.kind === "treasure_map" || sel.kind === "map" || String(sel.name).includes("图"));
    if (isMapItem) {
      inspectorHtml = `
      <div class="space-y-4">
        <div class="relative w-full h-44 rounded-xl overflow-hidden bg-slate-900 border border-filigree-400/40 shadow-sm">
          <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx"
               class="w-full h-full object-cover" alt="藏宝图卷" />
          <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-transparent"></div>
          <div class="absolute top-2.5 left-2.5 px-2 py-0.5 rounded bg-filigree-500/90 text-amber-950 font-bold text-[11px] shadow-sm">
            ${esc(sel.tierName)} · ${esc(sel.slotCn)}
          </div>
          <div class="absolute bottom-2.5 left-2.5 right-2.5 text-white">
            <h4 class="text-base font-bold">${esc(sel.name)}</h4>
            <div class="text-[11px] text-filigree-200 font-mono">定位灵穴：${esc(sel.targetNodeName || "落霞荒泽")}</div>
          </div>
        </div>

        <div class="bg-amber-50/70 p-3.5 rounded-xl border border-filigree-300/80 space-y-2 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-bold text-amber-950">🧭 干支风水定盘方位</span>
            <span class="text-filigree-700 font-semibold">[${esc(sel.archetypeCn || "坎水五行破阵")}]</span>
          </div>
          <div class="bg-white/80 p-2.5 rounded-lg border border-amber-200 font-mono text-slate-700 leading-relaxed">
            ${esc(sel.coords || "甲子方位 · 震木宫 东南二十里 地脉三丈")}
          </div>
          <p class="text-[11px] text-amber-900/80 leading-relaxed italic">
            “${esc(sel.riddle || "五行倒悬，阴阳同炉。非晓坎水生克之道者不可轻启。")}”
          </p>
        </div>

        <div class="text-xs text-slate-600 bg-white/80 p-3 rounded-xl border border-jade-100 leading-relaxed">
          ${esc(sel.lore)}
        </div>

        <button class="w-full py-2.5 rounded-xl bg-gradient-to-r from-filigree-600 to-amber-600 hover:from-filigree-500 hover:to-amber-500 text-white text-xs font-bold shadow-md border border-filigree-300 transition cursor-pointer" type="button" data-treasure-act="dig" data-map-name="${esc(sel.name)}">
          依图寻宝探秘 (御风启程)
        </button>
      </div>`;
    } else if (sel) {
      const statsList = Object.entries(sel.stats || {}).map(([k, v]) => `
        <div class="flex justify-between items-center py-1 border-b border-slate-100 text-xs">
          <span class="text-slate-500">${esc(k)}</span>
          <span class="font-bold text-jade-900 font-mono">+${v}</span>
        </div>
      `).join("");

      const affixesList = (sel.affixes || []).map((af) => `
        <div class="bg-jade-50/80 p-2 rounded-lg border border-jade-100 text-xs">
          <span class="text-jade-900 font-bold">【${esc(af.name)}】</span>
          <span class="text-slate-600">${esc(af.desc)}</span>
        </div>
      `).join("");

        const isEquip = sel && (sel.kind === "equip" || sel.kind === "weapon" || sel.kind === "armor" || sel.kind === "trinket" || !!sel.slot);
        const isPill = sel && (sel.kind === "pill" || sel.kind === "consumable");

        inspectorHtml = `
      <div class="space-y-4">
        <div class="flex items-center gap-3 pb-3 border-b border-jade-200">
          <div class="w-12 h-12 rounded-xl bg-jade-800 text-filigree-300 flex items-center justify-center font-calligraphy text-2xl font-bold shadow-2xs">
            ${sel.iconGlyph || sel.name.slice(0, 1)}
          </div>
          <div>
            <h4 class="text-base font-bold text-jade-950">${esc(sel.name)}</h4>
            <div class="flex items-center gap-1.5 mt-0.5 text-xs text-slate-500">
              <span class="px-1.5 py-0.2 rounded bg-filigree-100 text-filigree-800 font-medium">${esc(sel.tierName)}</span>
              <span>${esc(sel.slotCn || "法宝物华")}</span>
            </div>
          </div>
        </div>

        ${statsList ? `<div class="bg-white/90 p-3 rounded-xl border border-jade-100 space-y-1">${statsList}</div>` : ""}
        ${affixesList ? `<div class="space-y-2">${affixesList}</div>` : ""}

        <div class="text-xs text-slate-600 bg-white/80 p-3 rounded-xl border border-jade-100 leading-relaxed">
          ${esc(sel.lore || "天地造化所钟之奇珍。")}
        </div>

        <div class="flex flex-col gap-2 pt-1">
          ${isEquip ? `
            <button class="w-full py-2 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-equip-act="equip" data-equip-name="${esc(sel.name)}">
              佩戴入体 (运转周天)
            </button>
          ` : isPill ? `
            <button class="w-full py-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-cmd="/服用 ${esc(sel.name)}">
              服食灵丹 (周天化纳)
            </button>
          ` : `
            <button class="w-full py-2 rounded-lg bg-slate-100 text-slate-500 border border-slate-200 text-xs font-medium cursor-default" type="button" disabled>
              天材地宝 · 炼器洗练神材
            </button>
          `}
          <div class="grid grid-cols-2 gap-2">
            <button class="py-1.5 rounded-lg bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-medium cursor-pointer" type="button" data-act="sell:${esc(sel.name)}">
              挂牌寄售坊市
            </button>
            <button class="py-1.5 rounded-lg bg-white hover:bg-rose-50 text-slate-600 border border-slate-200 text-xs font-medium cursor-pointer" type="button" data-cmd="/卖 ${esc(sel.name)}">
              回售仙盟商会
            </button>
          </div>
        </div>
      </div>`;
    }

    return `
    <div class="w-full flex flex-col gap-5">
      <div class="flex items-center justify-between pb-3 border-b border-jade-200/80">
        <div class="flex items-center gap-3">
          <div class="w-1.5 h-6 rounded-full bg-gradient-to-b from-filigree-400 to-jade-700"></div>
          <h1 class="text-xl font-bold text-jade-950 flex items-center gap-2">
            <span>百宝纳戒 · 灵物宝匣与天机藏图</span>
            <span class="text-xs font-normal text-slate-500 hidden sm:inline">（乾坤芥子储物空间）</span>
          </h1>
        </div>
        <div class="text-xs text-slate-600 flex items-center gap-2 bg-white/80 px-3 py-1.5 rounded-lg border ${inv.length >= 64 ? 'border-amber-400 bg-amber-50/70 text-amber-900' : 'border-jade-200'}">
          <span>纳戒容积: <strong class="${inv.length >= 64 ? 'text-amber-800' : 'text-jade-900'} font-mono">${filter === 'all' ? inv.length : `${filtered.length} 件 (总占 ${inv.length})`}</strong> / 陆拾肆 格位 ${inv.length >= 64 ? '<span class="text-[10px] px-1 rounded bg-amber-200 text-amber-900 font-bold">已满</span>' : ''}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <!-- 左侧 3 栏：本命佩戴三槽 -->
        <div class="lg:col-span-3 flex flex-col gap-4">
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
              <h3 class="text-sm font-bold text-jade-950">本命三槽</h3>
              <span class="text-[11px] text-jade-700 font-medium">道体佩戴</span>
            </div>

            <!-- 法宝槽 -->
            <div class="p-3 bg-white/90 rounded-xl border border-jade-200 flex items-center justify-between">
              <div class="flex items-center gap-2.5">
                <div class="w-10 h-10 rounded-lg bg-jade-800 text-filigree-300 flex items-center justify-center font-calligraphy text-lg font-bold shadow-2xs">
                  剑
                </div>
                <div>
                  <h4 class="text-xs font-bold text-jade-950">${esc(weaponEquip.name)}</h4>
                  <div class="text-[10px] text-filigree-700 font-medium">${esc(weaponSub)}</div>
                </div>
              </div>
              ${weaponEquip.name !== "空置法宝" ? `<button type="button" class="text-xs text-slate-400 hover:text-rose-600 cursor-pointer" data-equip-act="unequip" data-equip-name="${esc(weaponEquip.name)}">卸下</button>` : ""}
            </div>

            <!-- 防具槽 -->
            <div class="p-3 bg-white/90 rounded-xl border border-jade-200 flex items-center justify-between">
              <div class="flex items-center gap-2.5">
                <div class="w-10 h-10 rounded-lg bg-jade-700 text-white flex items-center justify-center font-calligraphy text-lg font-bold shadow-2xs">
                  袍
                </div>
                <div>
                  <h4 class="text-xs font-bold text-jade-950">${esc(armorEquip.name)}</h4>
                  <div class="text-[10px] text-jade-700 font-medium">${esc(armorSub)}</div>
                </div>
              </div>
              ${armorEquip.name !== "空置道袍" ? `<button type="button" class="text-xs text-slate-400 hover:text-rose-600 cursor-pointer" data-equip-act="unequip" data-equip-name="${esc(armorEquip.name)}">卸下</button>` : ""}
            </div>

            <!-- 饰品槽 -->
            <div class="p-3 bg-white/90 rounded-xl border border-jade-200 flex items-center justify-between">
              <div class="flex items-center gap-2.5">
                <div class="w-10 h-10 rounded-lg bg-amber-600 text-white flex items-center justify-center font-calligraphy text-lg font-bold shadow-2xs">
                  玉
                </div>
                <div>
                  <h4 class="text-xs font-bold text-jade-950">${esc(trinketEquip.name)}</h4>
                  <div class="text-[10px] text-filigree-700 font-medium">${esc(trinketSub)}</div>
                </div>
              </div>
              ${trinketEquip.name !== "空置灵佩" ? `<button type="button" class="text-xs text-slate-400 hover:text-rose-600 cursor-pointer" data-equip-act="unequip" data-equip-name="${esc(trinketEquip.name)}">卸下</button>` : ""}
            </div>
          </div>
        </div>

        <!-- 中间 5 栏：芥子空间百宝格 (4x3 饱满大格) -->
        <div class="lg:col-span-5 flex flex-col gap-4">
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-jade-200/80">
              <div class="flex items-center gap-1 text-xs">
                <button type="button" class="px-2.5 py-1 rounded-full ${filter === "all" ? "bg-jade-700 text-white" : "bg-white text-slate-600 border border-jade-200"} font-medium cursor-pointer" data-bag-filter="all">全部</button>
                <button type="button" class="px-2.5 py-1 rounded-full ${filter === "equip" ? "bg-jade-700 text-white" : "bg-white text-slate-600 border border-jade-200"} font-medium cursor-pointer" data-bag-filter="equip">法宝</button>
                <button type="button" class="px-2.5 py-1 rounded-full ${filter === "pill" ? "bg-jade-700 text-white" : "bg-white text-slate-600 border border-jade-200"} font-medium cursor-pointer" data-bag-filter="pill">丹药</button>
                <button type="button" class="px-2.5 py-1 rounded-full ${filter === "material" ? "bg-jade-700 text-white" : "bg-white text-slate-600 border border-jade-200"} font-medium cursor-pointer" data-bag-filter="material">灵材</button>
                <button type="button" class="px-2.5 py-1 rounded-full ${filter === "treasure_map" ? "bg-jade-700 text-white" : "bg-white text-slate-600 border border-jade-200"} font-medium cursor-pointer" data-bag-filter="treasure_map">藏宝天机</button>
              </div>
              <span class="text-[11px] text-slate-400">选中灵物验真</span>
            </div>

            <!-- 百宝网格：饱满 4 列排列 -->
            <div class="grid grid-cols-4 gap-2.5">
              ${bagCells}
            </div>
          </div>
        </div>

        <!-- 右侧 4 栏：万象灵宝鉴真神台 -->
        <div class="lg:col-span-4 flex flex-col gap-4">
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
              <h3 class="text-sm font-bold text-jade-950">鉴真台</h3>
              <span class="text-[11px] px-2 py-0.5 rounded bg-filigree-100 text-filigree-800 border border-filigree-300 font-medium">天道玄鉴</span>
            </div>
            ${inspectorHtml}
          </div>
        </div>
      </div>
    </div>`;
  }

  // ==========================================================================
  // 主境四：【九霄坊市 · 诸天通宝与乾坤寄售】 (Bazaar) - Stitch 原生 1:1 高保真
  // ==========================================================================
  function ensureDefaultMarket() {
    if (state.marketListings && state.marketListings.length > 0) return;
    state.marketListings = [
      { id: 1, name: "地阶上品 · 黑水沼泽天机残图", tier: "地品", affixes: "古修密卷 · 独一无二", seller: "青阳散人", price: 800, tax: 40, kind: "map" },
      { id: 2, name: "地阶绝品 · 断魂幽煞剑", tier: "天品", affixes: "破煞甲级 · 嗜血乙级", seller: "紫虚真人", price: 1500, tax: 75, kind: "sword" },
      { id: 3, name: "玄阶极品 · 辟毒清元丹 (拾丸)", tier: "人品", affixes: "克制黑水沼泽赤焰瘴气", seller: "百草仙姑", price: 300, tax: 15, kind: "pill" },
      { id: 4, name: "天阶残卷 · 落霞古洞太虚玉简", tier: "天品", affixes: "领悟太虚通法概率升至四成", seller: "玄溟剑尊", price: 5000, tax: 250, kind: "scroll" },
    ];
  }

  function renderBazaar() {
    ensureDefaultMarket();
    const listings = state.marketListings;

    return `
    <div class="w-full flex flex-col gap-5">
      <!-- 顶部九霄天街深绿大气 Banner (Stitch 原生) -->
      <section class="w-full">
        <div class="relative overflow-hidden rounded-2xl bg-gradient-to-r from-jade-950 via-jade-900 to-slate-900 p-5 sm:p-6 shadow-md border border-filigree-400/40 text-white">
          <div class="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="space-y-1.5">
              <div class="flex items-center gap-2">
                <span class="w-8 h-8 rounded-full bg-filigree-500/20 text-filigree-300 flex items-center justify-center font-calligraphy text-base border border-filigree-400/40">坊</span>
                <h1 class="text-xl sm:text-2xl font-bold tracking-wide">九霄天街 · 灵霄仙阁诸界总坊</h1>
                <span class="px-2 py-0.5 rounded bg-filigree-500/20 text-filigree-300 text-[10px] border border-filigree-400/30">诸天万修汇聚</span>
              </div>
              <p class="text-xs sm:text-sm text-jade-200/90 leading-relaxed max-w-xl">
                天道商律：寄售契税半成，灵物挂牌七昼夜无人竞购自动退返纳戒。当值掌柜【白鹤道人】坐镇鉴宝护法。
              </p>
            </div>
            <div class="flex items-center gap-3">
              <div class="px-4 py-2 rounded-xl bg-white/10 backdrop-blur-md border border-white/10 text-center">
                <div class="text-[10px] text-jade-200">在售天机奇珍</div>
                <div class="text-base font-bold text-filigree-300 font-mono">壹仟贰佰件</div>
              </div>
              <div class="px-4 py-2 rounded-xl bg-white/10 backdrop-blur-md border border-white/10 text-center">
                <div class="text-[10px] text-jade-200">今日总成交灵石</div>
                <div class="text-base font-bold text-white font-mono">捌拾肆万枚</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 12 栏结构：左 8 栏寄售行卷图文流，右 4 栏万象鉴真神台与我的货摊 -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <!-- 左侧 8 栏：寄售行卷 -->
        <section class="lg:col-span-8 flex flex-col gap-4">
          <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
            <div class="flex items-center gap-1.5 overflow-x-auto text-xs">
              <button class="px-3 py-1 rounded-full bg-jade-700 text-white font-medium shadow-sm cursor-pointer whitespace-nowrap">全部寄售 (肆)</button>
              <button class="px-3 py-1 rounded-full bg-white text-slate-600 border border-jade-200 font-medium hover:bg-jade-50 cursor-pointer whitespace-nowrap">神兵法宝</button>
              <button class="px-3 py-1 rounded-full bg-white text-slate-600 border border-jade-200 font-medium hover:bg-jade-50 cursor-pointer whitespace-nowrap">灵丹妙药</button>
              <button class="px-3 py-1 rounded-full bg-white text-slate-600 border border-jade-200 font-medium hover:bg-jade-50 cursor-pointer whitespace-nowrap">天机藏图</button>
              <button class="px-3 py-1 rounded-full bg-white text-slate-600 border border-jade-200 font-medium hover:bg-jade-50 cursor-pointer whitespace-nowrap">天材地宝</button>
            </div>
            <span class="text-[11px] text-slate-400 hidden sm:inline">行情刷新时序: 每炷香一更</span>
          </div>

          <!-- 货品图文卡片流 (Stitch 原生高保真行卷) -->
          <div class="space-y-4">
            <!-- 货品 1：黑水沼泽天机残图 -->
            <article class="jade-panel jade-panel-hover rounded-xl p-4 shadow-sm border border-jade-200 flex flex-col sm:flex-row items-center gap-4 relative group">
              <div class="absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded bg-jade-100 text-jade-800 font-semibold border border-jade-300">
                当前鉴真聚焦
              </div>
              <div class="relative w-36 h-28 rounded-lg overflow-hidden bg-slate-900 flex-shrink-0 shadow-inner">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx"
                     class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" alt="黑水沼泽天机图" />
                <div class="absolute bottom-1 left-1 px-1.5 py-0.2 rounded bg-black/70 text-[9px] text-white">黑水沼泽 · 遗迹祭坛</div>
              </div>
              <div class="flex-1 min-w-0 space-y-1.5">
                <div class="flex items-center gap-2">
                  <h3 class="text-base font-bold text-jade-950 truncate">地阶上品 · 黑水沼泽天机残图</h3>
                </div>
                <div class="flex items-center gap-1.5 text-[10px]">
                  <span class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 border border-amber-300 font-medium">古修密卷</span>
                  <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 border border-jade-300 font-medium">独一无二</span>
                  <span class="text-slate-400">| 寄售散修: 青阳散人</span>
                </div>
                <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                  天干地支勘测点：子位十二·坎位负四。此残图以深海灵鲛皮揉制，内蕴太虚神识印记，破阵要求需调动五行坎水真元。
                </p>
                <div class="flex items-center justify-between pt-1">
                  <div class="text-xs text-slate-500">
                    寄售标价: <strong class="text-base font-bold text-filigree-700 font-mono">下品灵石 捌佰枚</strong>
                  </div>
                  <div class="flex gap-2">
                    <button class="px-3 py-1.5 rounded-lg bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-medium cursor-pointer" type="button" data-cmd="/鉴宝 1">
                      神念验宝
                    </button>
                    <button class="px-4 py-1.5 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-cmd="/买寄售 1">
                      立即交割
                    </button>
                  </div>
                </div>
              </div>
            </article>

            <!-- 货品 2：断魂幽煞剑 -->
            <article class="jade-panel jade-panel-hover rounded-xl p-4 shadow-sm border border-jade-200 flex flex-col sm:flex-row items-center gap-4 relative group">
              <div class="relative w-36 h-28 rounded-lg overflow-hidden bg-slate-900 flex-shrink-0 shadow-inner">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuDNggPj4AGHEqJhe9iU83W1YRePfLywRJ7izNYtV_guyNEVqy7wQCWSumM2RgEu1kUnoyaikSEY-4SyTljW3XGa4F-PpCPhS2XZUu2FcCLSuDUIfpFod_Zq6GqTrXe6sC95V-CphUFf06CtaOlJjWAVAxJXnjE8GqkVaXB_XhscGY01nQqO74k7IpR9jKWef8souqUFhVB3FOswfEnnmemhgTWavzOyAlZbbXvjzStRAEsuAiZrQHRwI0GhLD7ImwJ_NSGyUhC5fQGa"
                     class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" alt="断魂幽煞剑" />
                <div class="absolute bottom-1 left-1 px-1.5 py-0.2 rounded bg-black/70 text-[9px] text-white">九天碧玉太虚兵戈</div>
              </div>
              <div class="flex-1 min-w-0 space-y-1.5">
                <div class="flex items-center gap-2">
                  <h3 class="text-base font-bold text-jade-950 truncate">地阶绝品 · 断魂幽煞剑</h3>
                  <span class="text-[10px] text-slate-400">| 寄售散修: 紫虚真人</span>
                </div>
                <div class="flex items-center gap-1.5 text-[10px]">
                  <span class="px-1.5 py-0.2 rounded bg-rose-100 text-rose-900 border border-rose-300 font-medium">破煞 (甲级)</span>
                  <span class="px-1.5 py-0.2 rounded bg-rose-100 text-rose-900 border border-rose-300 font-medium">嗜血 (乙级)</span>
                  <span class="text-slate-500">攻伐增益 +160</span>
                </div>
                <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                  以万载玄冥寒玉淬火七七四十九日铸成，剑尖游离煞气，出鞘有白鹤哀鸣之音，专破幽冥护体罡气。
                </p>
                <div class="flex items-center justify-between pt-1">
                  <div class="text-xs text-slate-500">
                    寄售标价: <strong class="text-base font-bold text-filigree-700 font-mono">下品灵石 壹仟伍佰枚</strong>
                  </div>
                  <div class="flex gap-2">
                    <button class="px-3 py-1.5 rounded-lg bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-medium cursor-pointer" type="button" data-cmd="/鉴宝 2">
                      神念验宝
                    </button>
                    <button class="px-4 py-1.5 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-cmd="/买寄售 2">
                      立即交割
                    </button>
                  </div>
                </div>
              </div>
            </article>

            <!-- 货品 3：辟毒清元丹 -->
            <article class="jade-panel jade-panel-hover rounded-xl p-4 shadow-sm border border-jade-200 flex flex-col sm:flex-row items-center gap-4 relative group">
              <div class="w-36 h-28 rounded-lg bg-jade-50 border border-jade-200 flex flex-col items-center justify-center flex-shrink-0">
                <span class="w-12 h-12 rounded-full bg-jade-200 text-jade-800 flex items-center justify-center font-calligraphy text-2xl font-bold shadow-2xs">丹</span>
                <span class="text-[10px] text-slate-400 mt-1">共拾丸</span>
              </div>
              <div class="flex-1 min-w-0 space-y-1.5">
                <div class="flex items-center justify-between">
                  <h3 class="text-base font-bold text-jade-950">玄阶极品 · 辟毒清元丹 (拾丸)</h3>
                  <span class="text-[10px] text-slate-400">寄售散修: 百草仙姑</span>
                </div>
                <div class="flex items-center gap-1.5 text-[10px]">
                  <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 border border-jade-300 font-medium">克制黑水沼泽赤焰瘴气</span>
                  <span class="px-1.5 py-0.2 rounded bg-jade-100 text-jade-800 border border-jade-300 font-medium">温养灵脉三载</span>
                </div>
                <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                  采集千年玄冰雪莲与甘露熬炼而成，入腹化作九道清凉真气，辟除万毒，固护元神。
                </p>
                <div class="flex items-center justify-between pt-1">
                  <div class="text-xs text-slate-500">
                    寄售标价: <strong class="text-base font-bold text-filigree-700 font-mono">下品灵石 叁佰枚</strong>
                  </div>
                  <button class="px-4 py-1.5 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-cmd="/买寄售 3">
                    立即交割
                  </button>
                </div>
              </div>
            </article>

            <!-- 货品 4：落霞古洞太虚玉简 -->
            <article class="jade-panel jade-panel-hover rounded-xl p-4 shadow-sm border border-jade-200 flex flex-col sm:flex-row items-center gap-4 relative group">
              <div class="w-36 h-28 rounded-lg bg-amber-50 border border-filigree-200 flex flex-col items-center justify-center flex-shrink-0">
                <span class="w-12 h-12 rounded-full bg-amber-200 text-amber-900 flex items-center justify-center font-calligraphy text-2xl font-bold shadow-2xs">玉简</span>
                <span class="text-[10px] text-amber-800 mt-1">太古玄文</span>
              </div>
              <div class="flex-1 min-w-0 space-y-1.5">
                <div class="flex items-center justify-between">
                  <h3 class="text-base font-bold text-jade-950">天阶残卷 · 落霞古洞太虚玉简</h3>
                  <span class="text-[10px] text-slate-400">寄售散修: 玄溟剑尊</span>
                </div>
                <div class="flex items-center gap-1.5 text-[10px]">
                  <span class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 border border-amber-300 font-medium">领悟太虚通法概率升至四成</span>
                  <span class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 border border-amber-300 font-medium">金丹期方可启封</span>
                </div>
                <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                  落霞古洞深处所得上古真仙随笔玉简，铭刻太阴太阳造化残诀，参悟可使自身神识念力大幅精进。
                </p>
                <div class="flex items-center justify-between pt-1">
                  <div class="text-xs text-slate-500">
                    寄售标价: <strong class="text-base font-bold text-filigree-700 font-mono">下品灵石 伍仟枚</strong>
                  </div>
                  <div class="flex gap-2">
                    <button class="px-3 py-1.5 rounded-lg bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 text-xs font-medium cursor-pointer" type="button" data-cmd="/鉴宝 4">
                      神念验宝
                    </button>
                    <button class="px-4 py-1.5 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs cursor-pointer" type="button" data-cmd="/买寄售 4">
                      立即交割
                    </button>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>

        <!-- 右侧 4 栏：万象灵物鉴真神台与我的货摊 -->
        <aside class="lg:col-span-4 flex flex-col gap-5">
          <!-- 万象灵物 · 鉴真神台 (纯净自然原画，绝无人物表格重影) -->
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-3.5 border border-filigree-400/50">
            <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
              <h2 class="text-base font-bold text-jade-950 flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-filigree-500"></span>
                <span>万象灵物 · 鉴真神台</span>
              </h2>
              <span class="text-[10px] px-2 py-0.5 rounded bg-jade-100 text-jade-800 border border-jade-200 font-medium">灵霄仙阁共签</span>
            </div>

            <!-- 全景验宝图卷 -->
            <div class="relative w-full h-44 rounded-xl overflow-hidden bg-slate-900 border border-filigree-400/40 shadow-inner">
              <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuAY-3PXdQr6IEHvP5aEDaOeKorPpTjLy0nVqnYkTOxKcwaWu8UEbSmjdR3njEijyvKQE91PBvyeBMwEBRpne4OzXdhXknKlw9d6u8mbQ4d8arwzRQjzPV60ikcN9XAnjLMKuZQMb6hyul-OKMojwKAfa-K5Pls3P447zVBXPg1o8frmbuUldeJE9KLEB4d2N5WKweWlAf_WUUpui6dTupPUQApdqhI0ALBAI1sKyHxzUFBwy6P9xZMNyt5ZPFzo5R11TN-gLeGXO-lx"
                   class="w-full h-full object-cover" alt="神台验宝" />
              <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-transparent"></div>
              <div class="absolute top-2.5 right-2.5 px-1.5 py-2 rounded bg-rose-950/90 text-rose-200 border border-rose-500 text-[10px] font-bold [writing-mode:vertical-rl] tracking-widest shadow-md">
                遗迹祭坛朱砂封印
              </div>
              <div class="absolute bottom-2.5 left-2.5 text-white">
                <span class="text-[10px] px-2 py-0.5 rounded bg-jade-900/80 text-jade-200 border border-jade-500/40">灵气浓郁度: 九品上乘</span>
              </div>
            </div>

            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between">
                <span class="text-slate-500">验宝物: <strong class="text-jade-950">黑水沼泽天机残图</strong></span>
                <span class="text-[10px] text-filigree-700">真灵契约已核验</span>
              </div>
              <div class="bg-white/80 p-2.5 rounded-xl border border-jade-100 space-y-1.5 text-[11px] text-slate-600">
                <div class="flex justify-between">
                  <span>因果印记:</span>
                  <span class="text-slate-800 font-medium">上古坐化金丹修士随身洞府遗泽</span>
                </div>
                <div class="flex justify-between">
                  <span>方位索引:</span>
                  <span class="text-slate-800 font-medium">十方大荒深处 · 阴冥沼泽骨龙坡</span>
                </div>
                <div class="flex justify-between">
                  <span>契约交割护法:</span>
                  <span class="text-jade-700 font-medium">万象商盟律令担保</span>
                </div>
              </div>
            </div>

            <button class="w-full py-2.5 rounded-xl bg-gradient-to-r from-jade-800 via-jade-700 to-jade-800 hover:from-jade-700 hover:to-jade-600 text-white text-xs font-bold shadow-md border border-filigree-400/40 flex items-center justify-center gap-2 cursor-pointer" type="button" data-cmd="/买寄售 1">
              <span>交付 捌佰灵石 · 契约立成</span>
            </button>
            <div class="text-center">
              <button class="text-[11px] text-slate-500 hover:text-jade-700 cursor-pointer" type="button" data-person="青阳散人">
                神识传音卖家 (青阳散人)
              </button>
            </div>
          </div>

          <!-- 我的坊市摊位 · 聚宝灵坛 (Stitch 原生) -->
          <div class="jade-panel rounded-2xl p-5 shadow-sm space-y-3.5 border border-jade-200">
            <div class="flex items-center justify-between pb-2 border-b border-jade-200/80">
              <h2 class="text-base font-bold text-jade-950 flex items-center gap-1.5">
                <span>🏮 我的坊市摊位 · 聚宝灵坛</span>
              </h2>
              <span class="text-[10px] text-slate-400">摊位法座: 乾位第三</span>
            </div>

            <div class="bg-white/80 p-3 rounded-xl border border-jade-100 space-y-2 text-xs">
              <div class="flex items-center justify-between">
                <span class="text-slate-500">当前已挂牌灵物:</span>
                <span class="font-bold text-jade-900 font-mono">叁 / 捌 件</span>
              </div>
              <div class="p-2.5 bg-jade-50/70 rounded-lg border border-jade-100 flex items-center justify-between">
                <span class="text-[11px] text-slate-600">待提取收益 (已扣除半成契税):</span>
                <span class="text-sm font-bold text-jade-800 font-mono">贰仟肆佰灵石</span>
              </div>
              <button class="w-full py-2 rounded-lg bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold shadow-2xs transition cursor-pointer" type="button" data-cmd="/收益">
                一键收益划归纳戒
              </button>
            </div>

            <div class="grid grid-cols-2 gap-2 pt-1 text-xs">
              <button class="py-2 rounded-lg bg-white hover:bg-jade-50 text-jade-800 border border-jade-300 font-medium cursor-pointer" type="button" data-act="view:inventory">
                挑选新灵物挂牌
              </button>
              <button class="py-2 rounded-lg bg-white hover:bg-jade-50 text-slate-700 border border-jade-200 font-medium cursor-pointer" type="button" data-cmd="/坊市">
                调整寄售标价
              </button>
            </div>
            <div class="text-center pt-0.5">
              <button class="text-[11px] text-slate-400 hover:text-slate-600 cursor-pointer" type="button" data-cmd="/撤回寄售">
                撤回挂牌灵物 (无需契税)
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>`;
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

    if (c.startsWith("/探险") || c.startsWith("/adventure")) {
      const parts = c.trim().split(/\s+/);
      const target = parts.slice(1).join(" ").trim() || "野外山原";
      handleWildernessAction("adventure", target);
      return;
    }

    if (c.startsWith("/挖宝") || c.startsWith("/dig")) {
      const parts = c.trim().split(/\s+/);
      const mapName = parts.slice(1).join(" ").trim();
      handleTreasureAction("dig", mapName);
      return;
    }

    if (c.startsWith("/穿戴") || c.startsWith("/装备") || c.startsWith("/equip")) {
      const parts = c.trim().split(/\s+/);
      const itemName = parts.slice(1).join(" ").trim();
      handleEquipAction("equip", itemName);
      return;
    }

    if (c.startsWith("/卸下") || c.startsWith("/unequip")) {
      const parts = c.trim().split(/\s+/);
      const itemName = parts.slice(1).join(" ").trim();
      handleEquipAction("unequip", itemName);
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

      if (c.startsWith("/突破") || c.startsWith("/break")) {
        const isSucc = data.ok && (data.success !== false && !(data.tribulation && data.tribulation.fatal));
        if (isSucc && (data.tribulation || data.new_realm || (data.status && data.status.realm))) {
          const newR = (data.tribulation && data.tribulation.new_realm) || (data.status && data.status.realm) || "新阶位";
          openJadeDialog({
            title: "天道垂青 · 登仙大捷",
            icon: "✨",
            bodyHtml: `
              <div class="text-center space-y-3 py-3">
                <div class="w-16 h-16 rounded-full bg-gradient-to-tr from-amber-400 to-amber-200 text-amber-950 flex items-center justify-center text-3xl mx-auto shadow-md">
                  🌟
                </div>
                <h4 class="text-lg font-bold text-jade-950">恭贺道友破境功成</h4>
                <p class="text-xs text-slate-700 leading-relaxed max-w-md mx-auto">
                  九霄神雷洗尽凡尘因果，天地灵气共鸣！
                </p>
                <div class="p-2.5 rounded-lg bg-jade-50 border border-jade-200 text-xs max-w-xs mx-auto">
                  晋升道阶：<strong class="text-jade-900">${esc(newR)}</strong>
                </div>
              </div>
            `,
            footerHtml: `
              <button type="button" class="px-6 py-2 rounded-xl bg-jade-700 hover:bg-jade-800 text-white text-xs font-semibold cursor-pointer" onclick="workbench.closeJadeDialog()">
                稳固道基
              </button>
            `,
          });
        } else if (!isSucc) {
          openJadeDialog({
            title: "天雷反噬 · 渡劫未果",
            icon: "⚡",
            bodyHtml: `
              <div class="text-center space-y-3 py-3">
                <div class="w-16 h-16 rounded-full bg-rose-100 text-rose-800 flex items-center justify-center text-3xl mx-auto shadow-sm">
                  💥
                </div>
                <h4 class="text-lg font-bold text-rose-950">九天雷劫未破</h4>
                <p class="text-xs text-slate-700 leading-relaxed max-w-md mx-auto">
                  ${esc(data.error || data.text || "天劫狂暴，未能功成！")}
                </p>
              </div>
            `,
            footerHtml: `
              <button type="button" class="px-6 py-2 rounded-xl bg-rose-700 hover:bg-rose-800 text-white text-xs font-semibold cursor-pointer" onclick="workbench.closeJadeDialog()">
                温养疗伤
              </button>
            `,
          });
        }
      }

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
    const s = state.status || (state.status = {
      name: "太素仙尊 · 顾青玄",
      realm: "化神后期（圆满）",
      sect: "太素仙宗",
      rank: "太上掌教",
      stones: 128450,
      vault: 360000,
      exp: "1,240,000 / 140万",
      rem_years: 2800,
      sin: 120,
      merit: 3650,
      root: "先天混元灵根",
      blood_marked: false,
      pill_exp_mult: 1,
      is_meditating: false,
    });
    const sc = state.sanctum;

    if (c.startsWith("/挖宝")) {
      return { ok: true, text: "【玄黄镜演 · 挖宝破阵】你依照天机密卷指引，寻得地脉坎水灵穴，破除阵眼禁制，得获【凡阶地髓灵液】一份！" };
    }
    if (c.startsWith("/探险")) {
      s.stones = Math.max(0, (s.stones || 0) - 20);
      ensureDefaultInventory();
      const parts = c.trim().split(/\s+/);
      const targetName = parts.slice(1).join(" ").trim() || "野外山原";
      const target = resolveWildernessTarget(targetName);
      const hasFoundMap = state.hasFoundMap || state.inventory.some(x => x.kind === "treasure_map" || (x.name && x.name.includes("图")));
      if (!hasFoundMap) {
        state.hasFoundMap = true;
        state.inventory.unshift({
          uid: "map_" + Date.now(),
          name: `${target.name}古修遗图[${target.name}灵穴]`,
          kind: "treasure_map",
          slotCn: "天机秘宝图卷",
          tier: 2,
          tierName: "人品",
          iconGlyph: "图",
          targetNodeName: `${target.name}深处灵穴`,
          archetypeCn: "坎水五行破阵",
          coords: "丙午方位 · 离火宫 南行三十里 古修士遗府",
          riddle: "五行倒悬，阴阳同炉。阵眼匿于地脉灵穴最深处，非晓生克之道者不可轻启。",
          lore: `自【${target.name}】斩获的上古修士随身秘藏图卷。`,
          qty: 1,
        });
      }
      return {
        ok: true,
        text: `【玄黄镜演 · 大荒探险】你耗费 20 灵石盘缠，深入【${target.name}】，阵斩凶兽，得获机缘入纳戒！`,
        status: s,
      };
    }
    if (c.startsWith("/闭关") || c.startsWith("/打坐")) {
      s.is_meditating = true;
      s.meditating = true;
      return { ok: true, text: "【洞府闭关】洞府大阵锁闭，道友已入定吐纳，周天运转，灵息绵延。", status: s };
    }
    if (c.startsWith("/出关")) {
      s.is_meditating = false;
      s.meditating = false;
      return { ok: true, text: "【出关收功】你长舒浊气，收功出关，周天真元凝练入体。", status: s };
    }
    if (c.startsWith("/服用") || c.startsWith("/吃") || c.startsWith("/use")) {
      const parts = c.trim().split(/\s+/);
      const pillName = parts.slice(1).join(" ").trim();
      ensureDefaultInventory();
      const pIdx = state.inventory.findIndex(x => x.name === pillName || x.name.includes(pillName));
      if (pIdx >= 0) {
        const consumed = state.inventory.splice(pIdx, 1)[0];
        toast(`【丹道化纳】服下【${consumed.name}】，药力通达周天，真元充盈！`, "gold");
        return { ok: true, text: `【服食灵丹】你盘膝而坐，服下【${consumed.name}】，药力通达周天经脉，真元充盈！`, status: s };
      }
      return { ok: false, text: `纳戒中未寻得灵丹【${pillName}】。`, status: s };
    }
    if (c.startsWith("/突破")) {
      const rInfo = parseRealmInfo(s.realm);
      let curExp = 0, maxExp = 1;
      if (s.exp && s.exp.includes("/")) {
        const parts = s.exp.replace(/,/g, "").split("/");
        curExp = parseFloat(parts[0]) || 0;
        maxExp = parseFloat(parts[1]) || 1;
      }
      if (curExp < maxExp) {
        return { ok: false, text: `【修为未圆满】当前道阶【${rInfo.currentName}】真元未达圆满，不可强行引雷！`, status: s };
      }
      s.realm = rInfo.nextName;
      s.exp = `0 / ${Math.round(maxExp * 1.8).toLocaleString()}`;
      s.rem_years = (s.rem_years || 100) + rInfo.gainLifespan;
      return { ok: true, text: `【天命功成】雷劫破尽，神雷淬体，一举晋阶至【${rInfo.nextName}】！`, status: s };
    }
    if (c.startsWith("/寄存")) {
      const parts = c.split(" ");
      const num = parseInt(parts[1]) || 100;
      if ((s.stones || 0) >= num) {
        s.stones -= num;
        s.vault = (s.vault || 0) + Math.floor(num * 0.95);
        return { ok: true, text: `【乾坤金库】成功存入 ${num} 灵石至大阵金库，免遭大荒掠夺。`, status: s };
      }
      return { ok: false, text: "随身灵石不足，无法寄存。" };
    }
    if (c.startsWith("/支取")) {
      const parts = c.split(" ");
      const num = parseInt(parts[1]) || 100;
      if ((s.vault || 0) >= num) {
        s.vault -= num;
        s.stones = (s.stones || 0) + num;
        return { ok: true, text: `【乾坤金库】自大阵金库支取 ${num} 灵石划归纳戒。`, status: s };
      }
      return { ok: false, text: "金库储积不足，无法支取。" };
    }
    if (c.startsWith("/灵泉")) {
      if (sc) sc.springCharge = 0;
      state.inventory.unshift({ name: "玄冰玉露", kind: "consumable", rarity: "uncommon", desc: "玄冰九曲灵泉孕育的灵露，饮之清心涤滤。", qty: 1 });
      return { ok: true, text: "【洞府灵泉 · 汲取】汲取玄冰灵液，真元+7,400，得【玄冰玉露】一份入纳戒！", status: s };
    }
    if (c.startsWith("/草园")) {
      const isRush = c.includes("催熟");
      if (isRush) {
        s.stones = Math.max(0, (s.stones || 0) - 50);
        if (sc) { sc.herbsGrowth = 100; sc.herbsRemainHours = 0; }
        return { ok: true, text: "【紫菁草园 · 催熟】消耗 50 灵石灌注地脉灵泉，芝草瞬息成熟！", status: s };
      }
      if (sc) { sc.herbsGrowth = 15; sc.herbsRemainHours = 4; }
      state.inventory.unshift({ name: "千年紫菁芝草", kind: "material", rarity: "epic", desc: "紫菁草园产出的极品仙芝。", qty: 3 });
      return { ok: true, text: "【紫菁草园 · 采摘】采下成熟仙草，得【千年紫菁芝草】x3 放入纳戒！", status: s };
    }
    if (c.startsWith("/灵鹤")) {
      const parts = c.trim().split(/\s+/);
      if (parts[1] && ["领取", "收纳", "取回", "claim"].includes(parts[1])) {
        const pendingItem = (sc && sc.cranePendingItem) || (s && s.crane_pending_item);
        if (!pendingItem) {
          return { ok: false, text: "青羽仙鹤云巢灵囊中并无可领取的机缘仙物。", status: s };
        }
        ensureDefaultInventory();
        if (state.inventory.length >= 64) {
          return { ok: false, text: `百宝纳戒乾坤已满（${state.inventory.length}/64），请先前往纳戒移出、佩戴或出售旧物，腾出空位后再来领取！`, status: s };
        }
        state.inventory.unshift(pendingItem);
        if (sc) sc.cranePendingItem = null;
        if (s) s.crane_pending_item = null;
        return { ok: true, text: `【仙鹤云巢 · 取回机缘】你自青羽仙鹤灵囊中取下【${pendingItem.name}】，已妥善收入百宝纳戒！仙鹤振翅轻啼，重回栖息待命态。`, status: s };
      }
      const pendingItem = (sc && sc.cranePendingItem) || (s && s.crane_pending_item);
      if (pendingItem) {
        return { ok: false, text: `青羽仙鹤云巢中尚有衔回的【${pendingItem.name}】未取！请先输入 /灵鹤 领取 或在洞府灵台领取后再敕令启程！`, status: s };
      }
      const dest = parts[1] || "落霞密林";
      const costMap = { "落霞密林": 10, "黑风绝渊赤焰": 30, "南海碧波古墟": 50, "落霞山": 10 };
      const cost = costMap[dest] || 10;
      if ((s.stones || 0) < cost) {
        return { ok: false, text: `随身灵石不足 ${cost}，无法派遣仙鹤！`, status: s };
      }
      s.stones = (s.stones || 0) - cost;
      handleCraneReturned(dest);
      return { ok: true, text: `【镇山仙鹤 · 探路巡弋】消耗 ${cost} 灵石。青羽仙鹤翱翔于【${dest}】上空，破开云雾，神识传音报捷！`, status: s };
    }
    if (c.startsWith("/look")) {
      return { ok: true, text: `【观照道身】道号：${s.name} · 境界：${s.realm} · 随身灵石：${s.stones} · 金库储积：${s.vault}`, status: s };
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

    function openSideDrawer() {
      state.drawerOpen = true;
      const d = $("sideDrawer");
      const b = $("drawerBackdrop");
      if (d) d.classList.add("open");
      if (b) b.classList.add("open");
    }

    function closeSideDrawer() {
      state.drawerOpen = false;
      const d = $("sideDrawer");
      const b = $("drawerBackdrop");
      if (d) d.classList.remove("open");
      if (b) b.classList.remove("open");
    }

    function setDrawerTab(tab) {
      state.drawerTab = tab;
      const t1 = $("tabCultivators");
      const t2 = $("tabTeleport");
      if (t1) t1.className = `flex-1 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition ${tab === 'cultivators' ? 'bg-jade-700 text-white shadow-2xs' : 'text-slate-600 hover:text-jade-800'}`;
      if (t2) t2.className = `flex-1 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition ${tab === 'teleport' ? 'bg-jade-700 text-white shadow-2xs' : 'text-slate-600 hover:text-jade-800'}`;
      renderSideDrawer();
    }

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

      // 洞府专属动作 data-sanctum-act
      const sanctumEl = e.target.closest("[data-sanctum-act]");
      if (sanctumEl) {
        handleSanctumAction(sanctumEl.getAttribute("data-sanctum-act"), sanctumEl);
        return;
      }

      // 大荒专属探险动作 data-wild-act
      const wildEl = e.target.closest("[data-wild-act]");
      if (wildEl) {
        const act = wildEl.getAttribute("data-wild-act");
        const target = wildEl.getAttribute("data-target") || "野外山原";
        handleWildernessAction(act, target, wildEl);
        return;
      }

      // 本命装备专属动作 data-equip-act
      const equipEl = e.target.closest("[data-equip-act]");
      if (equipEl) {
        const act = equipEl.getAttribute("data-equip-act");
        const name = equipEl.getAttribute("data-equip-name");
        handleEquipAction(act, name, equipEl);
        return;
      }

      // 天机宝图寻宝动作 data-treasure-act
      const treasureEl = e.target.closest("[data-treasure-act]");
      if (treasureEl) {
        const act = treasureEl.getAttribute("data-treasure-act");
        const mapName = treasureEl.getAttribute("data-map-name");
        handleTreasureAction(act, mapName, treasureEl);
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
  startSanctumLoop();
  tryRestore();

  window.workbench = {
    state,
    renderBody,
    closeJadeDialog,
    openJadeDialog,
    handleSanctumAction,
    handleWildernessAction,
    handleCraneReturned,
    ensureDefaultInventory,
    handleEquipAction,
    handleTreasureAction,
    claimCranePendingItem,
  };
})();
