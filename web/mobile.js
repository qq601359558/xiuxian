/* 天道因果录 · 手机版客户端（spec: mobile-web D2）
独立小客户端：只复用 workbench.js 的接口语义（/register /login /action 等）
与会话键（wb.*）、阵枢默认地址口径（wb.base）；不加载 workbench.js，
不读遗留客户端的旧阵枢键，不自造数值结果，一切裁决以服务端返回为准。 */
(function () {
  "use strict";

  var $ = function (id) {
    return document.getElementById(id);
  };

  // 十方迁跃地名（与桌面 workbench.js PLACES 同表；迁跃命令为 /go <地名>）
  var PLACES = [
    { name: "青云坊市客栈", tip: "商会客栈 · 安全庇护" },
    { name: "青云宗外门山门", tip: "正道山门 · 灵气温润" },
    { name: "宗门玄元洞府", tip: "后山静室 · 闭关福地" },
    { name: "落霞山灵泉", tip: "凡阶野外 · 灵雾氤氲" },
    { name: "万剑仙门峰", tip: "剑气冲霄 · 仙家总坛" },
    { name: "黑风绝渊", tip: "大凶死地 · 罡风刺骨" },
    { name: "万星古岛", tip: "诸星残阵 · 上古遗迹" },
    { name: "洗剑池洞天", tip: "剑池淬锋 · 幽静洞天" },
    { name: "九幽天魔宗坛", tip: "九幽煞泉 · 魔道凶穴" },
  ];

  var state = {
    // 阵枢默认地址：与 workbench.js:138-147 逐字同口径——读 wb.base，
    // 存下的回环地址丢弃；本机回落 127.0.0.1:8765，否则 NAS 域名。
    base: (function () {
      var stored = localStorage.getItem("wb.base") || "";
      if (/^(https?:\/\/)?(localhost|127\.0\.0\.1)(:\d+)?\/?$/i.test(stored)) {
        localStorage.removeItem("wb.base");
        stored = "";
      }
      var local =
        location.hostname === "localhost" ||
        location.hostname === "127.0.0.1" ||
        location.protocol === "file:";
      return (
        stored ||
        (local ? "http://127.0.0.1:8765" : "http://mn.20230803.xyz:8765")
      );
    })(),
    token: localStorage.getItem("wb.token") || "",
    user: localStorage.getItem("wb.user") || "",
    name: localStorage.getItem("wb.name") || "",
    uid: localStorage.getItem("wb.uid") || "",
    theme: localStorage.getItem("wb.theme") === "dark" ? "dark" : "light",
    mode: "login",
    view: "feed",
    status: null,
    entry: null,
    entryPending: false,
    originCard: null,
    here: [],
    feed: [],
    world: null,
    commands: [],
    busy: false,
    demo: false,
    sug: [],
    sugI: 0,
    selectedBagName: "",
    opsBuilt: false,
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }

  // ---- 图库接入（gallery-gameplay §3/§8/§10.4）----
  // 路径一律用后端下发字段（st.portrait / items[].img / equipped[].img /
  // art_images / spells_catalog[].img / here[].avatar / omen_image）；
  // 唯一例外是图鉴段的 139 键展示表（§10.5）。图片 onerror 隐藏图位（§3.8）。
  var GALLERY_REALM_CN = ["凡人", "练气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"];
  var GALLERY_REALM_KEYS = ["fanren", "lianqi", "zhuji", "jindan", "yuanying", "huashen", "lianxu", "heti", "dacheng", "dujie"];
  // NPC 单人图（game-feel-phase2 §9.1/§9.10）：slug = uid 去 npc_ 前缀且 _ 换 -，与后端 GALLERY_GROUPS 同表镜像
  var GALLERY_NPC_SINGLE = [["qy-01", "玄清子"], ["qy-02", "静虚真人"], ["qy-03", "云鹤道人"], ["qy-04", "丹霞子"], ["qy-05", "林惊羽"], ["qy-06", "苏婉清"], ["qy-07", "石猛"], ["qy-08", "赵小满"], ["qy-09", "青萝"], ["wj-01", "剑圣·独孤败"], ["wj-02", "断岳剑尊"], ["wj-03", "白霜"], ["wj-04", "赤霄"], ["wj-05", "墨离"], ["wj-06", "剑奴阿七"], ["wj-07", "小环"], ["jy-01", "幽冥老祖"], ["jy-02", "血衣侯"], ["jy-03", "厉无锋"], ["jy-04", "骨姬"], ["jy-05", "血刀老祖"], ["jy-06", "毒娘子"], ["jy-07", "阿骨"], ["sh-01", "金满堂"], ["sh-02", "铁算盘"], ["sh-03", "柳三娘"], ["sh-04", "陆仁贾"], ["sh-05", "驼爷"], ["sh-06", "小雀儿"], ["wd-01", "采药翁"], ["wd-02", "赤练子"], ["wd-03", "山君"], ["wd-04", "蜃楼客"], ["wd-05", "海娘子"], ["wd-06", "盲眼琴师"], ["wd-07", "盗墓贼·孙九"], ["wd-08", "青州游侠·燕十三"]];
  var GALLERY_GROUPS = [
    { title: "人物·男相", keys: GALLERY_REALM_KEYS.map(function (r, i) { return ["portraits/male-" + r, "男相·" + GALLERY_REALM_CN[i], "定相男后随境界点亮，或同场遇见男修"]; }) },
    { title: "人物·女相", keys: GALLERY_REALM_KEYS.map(function (r, i) { return ["portraits/female-" + r, "女相·" + GALLERY_REALM_CN[i], "定相女后随境界点亮，或同场遇见女修"]; }) },
    { title: "人物·NPC 单人", keys: GALLERY_NPC_SINGLE.map(function (p) { return ["portraits/" + "npc-" + p[0], "NPC·" + p[1], "与" + p[1] + "同场或交谈"]; }) },
    { title: "人物·NPC 原型", keys: [["portraits/npc-laodao", "NPC·老道", "与老道原型 NPC 同场或交谈"], ["portraits/npc-shanggu", "NPC·商贾", "与商贾原型 NPC 同场或交谈"], ["portraits/npc-nvxiu", "NPC·女修", "与女修原型 NPC 同场或交谈"], ["portraits/npc-shaonian", "NPC·少年", "与少年原型 NPC 同场或交谈"]] },
    { title: "法宝", keys: [["artifacts/sword", "法宝·剑", "拥有剑类法宝"], ["artifacts/cauldron", "法宝·鼎炉", "拥有鼎炉类法宝"], ["artifacts/banner", "法宝·幡旗", "拥有幡旗类法宝"], ["artifacts/orb", "法宝·珠戒", "拥有珠戒类法宝"], ["artifacts/mirror", "法宝·镜", "拥有镜类法宝"], ["artifacts/bell", "法宝·铃钟", "拥有铃钟类法宝"], ["artifacts/pagoda", "法宝·塔", "拥有塔类法宝"], ["artifacts/gourd", "法宝·葫芦", "拥有葫芦类法宝"], ["artifacts/fan", "法宝·扇", "拥有扇类法宝"], ["artifacts/seal", "法宝·印玺", "拥有印玺类法宝"], ["artifacts/armor", "法宝·甲胄", "拥有甲胄类法宝"], ["artifacts/boots", "法宝·靴履", "拥有靴履类法宝"], ["artifacts/staff", "法宝·法杖", "拥有法杖类法宝"], ["artifacts/vessel", "法宝·舟舰", "拥有舟舰类法宝"], ["artifacts/blade", "法宝·战刃", "拥有刀刃类法宝"], ["artifacts/spear", "法宝·戈枪", "拥有戈枪类法宝"], ["artifacts/case", "法宝·剑匣", "拥有剑匣类法宝"], ["artifacts/needle", "法宝·灵刺", "拥有灵刺类法宝"], ["artifacts/shuttle", "法宝·破空梭", "拥有飞梭类法宝"], ["artifacts/talisman", "法宝·符箓", "拥有符箓护符类法宝"]] },
    { title: "功法", keys: [["arts/metal", "功法·金", "习得金系功法"], ["arts/wood", "功法·木", "习得木系功法"], ["arts/water", "功法·水", "习得水系功法"], ["arts/fire", "功法·火", "习得火系功法"], ["arts/earth", "功法·土", "习得土系功法"], ["arts/thunder", "功法·雷", "习得雷系功法"], ["arts/sword", "功法·剑", "习得剑系功法"], ["arts/ice", "功法·冰", "习得冰系功法"], ["arts/wind", "功法·风", "习得风系功法"], ["arts/spirit", "功法·神魂", "习得神魂类功法"]] },
    { title: "藏宝图", keys: [["maps/map-common", "宝图·凡图", "持有凡品藏宝图"], ["maps/map-fine", "宝图·良图", "持有良品藏宝图"], ["maps/map-rare", "宝图·珍图", "持有珍品藏宝图"], ["maps/map-ancient", "宝图·古图", "持有古品藏宝图或逢残碑奇遇"], ["maps/map-celestial", "宝图·仙图", "持有仙品藏宝图"], ["maps/arch-puzzle", "宝图·解谜", "研读五行解谜类宝图"], ["maps/arch-combat", "宝图·凶地", "研读凶地守护类宝图"], ["maps/arch-hazard", "宝图·涉险", "研读遗迹涉险类宝图"]] },
    { title: "灵宠", keys: [["pets/pet-qinglinmang", "灵宠·青鳞蟒", "收服青鳞蟒"], ["pets/pet-jifengxun", "灵宠·疾风隼", "收服疾风隼"], ["pets/pet-xuanjiagui", "灵宠·玄甲龟", "收服玄甲龟"], ["pets/pet-xunbaoshu", "灵宠·寻宝鼠", "收服寻宝鼠"]] },
    { title: "场景·地点", keys: [["scenes/market-inn", "场景·青云坊市客栈", "到访青云坊市客栈"], ["scenes/qingyun-gate", "场景·青云宗外门山门", "到访青云宗外门山门"], ["scenes/xuanyuan-cave", "场景·宗门玄元洞府", "到访宗门玄元洞府"], ["scenes/luoxia-spring", "场景·落霞山灵泉", "到访落霞山灵泉"], ["scenes/heishui-swamp", "场景·黑水沼泽", "到访黑水沼泽"], ["scenes/wanjian-peak", "场景·万剑仙门峰", "到访万剑仙门峰"], ["scenes/xijian-pool", "场景·洗剑池洞天", "到访洗剑池洞天"], ["scenes/jiuyou-altar", "场景·九幽天魔宗坛", "到访九幽天魔宗坛"], ["scenes/heifeng-abyss", "场景·黑风绝渊", "到访黑风绝渊"], ["scenes/wanxing-isle", "场景·万星古岛", "到访万星古岛"]] },
    { title: "场景·秘境", keys: [["scenes/realm-luoxia-cave", "场景·落霞古洞", "进入秘境落霞古洞"], ["scenes/realm-sword-tomb", "场景·剑冢残碑", "进入秘境剑冢残碑"], ["scenes/realm-wanxing-ruins", "场景·万星遗迹残址", "进入秘境万星遗迹"], ["scenes/realm-ghost-market", "场景·幽冥鬼市", "进入秘境幽冥鬼市"], ["scenes/dungeon-entrance", "场景·锁妖古窟", "进入锁妖古窟"]] },
    { title: "奇遇", keys: [["omen/black-market", "奇遇·黑市兜售", "逢黑市奇遇"], ["omen/orphan-trust", "奇遇·旧友托孤", "逢孤托奇遇"], ["omen/spring-dispute", "奇遇·灵泉争饮", "逢灵泉之争奇遇"], ["omen/stele", "奇遇·残碑悟道", "逢残碑奇遇"], ["omen/escort-deal", "奇遇·镖银争议", "逢护送交易奇遇"], ["omen/inn-whisper", "奇遇·客栈夜话", "逢客栈耳语奇遇"]] },
    { title: "丹药", keys: [["goods/pill-breakthrough", "丹药·破境", "持有破境类丹药"], ["goods/pill-cultivation", "丹药·修炼", "持有修行类丹药"], ["goods/pill-recovery", "丹药·疗愈", "持有疗复类丹药"], ["goods/pill-lifespan", "丹药·延寿", "持有延寿类丹药"], ["goods/pill-soul", "丹药·神魂", "持有养魂类丹药"], ["goods/pill-detox", "丹药·解毒", "持有解毒类丹药"], ["goods/pill-root", "丹药·洗髓", "持有洗根类丹药"], ["goods/pill-combat", "丹药·战斗", "持有战辅类丹药"]] },
    { title: "材料", keys: [["goods/mat-herb", "材料·灵草", "持有灵草类材料"], ["goods/mat-ore", "材料·矿石", "持有矿石类材料"], ["goods/mat-metal", "材料·金属", "持有金石类材料"], ["goods/mat-beast", "材料·兽材", "持有兽材类材料"], ["goods/mat-liquid", "材料·灵液", "持有灵液类材料"], ["goods/mat-wood", "材料·灵木", "持有灵木类材料"], ["goods/mat-aura", "材料·灵气", "持有灵蕴类材料"]] },
  ];
  function galleryAssetPath(key) { return "/assets/" + key + ".webp"; }
  function galleryFrameClass(tier) {
    var t = parseInt(tier, 10);
    if (!isFinite(t) || t < 1) t = 1;
    if (t > 5) t = 5;
    return "frame-tier-" + t;
  }
  function galleryImg(src, cls, alt) {
    if (!src) return "";
    return '<img class="gallery-img ' + (cls || "") + '" src="' + esc(src) + '" alt="' + esc(alt || "") + '" loading="lazy" onerror="this.style.display=\'none\'" />';
  }
  function spiritHtmlM(eq) {
    var sp = eq && eq.spirit;
    if (!sp) return "";
    var mood = Number(sp.mood != null ? sp.mood : 0);
    return '<div class="spirit-block"><div class="spirit-head"><span>器灵 · ' + esc(sp.name || "无名灵") + '</span><span>' + esc(sp.stage_cn || "") + '</span></div>' +
      '<div class="muted">性格 ' + esc(sp.personality_cn || "—") + ' · 成长 ' + esc(sp.growth != null ? sp.growth : 0) + ' · 心情 ' + esc(mood) + (mood < 40 ? "（器灵怠工）" : "") + '</div>' +
      '<div class="spirit-mood"><i style="width:' + Math.max(0, Math.min(100, mood)) + '%"></i></div>' +
      '<div class="chiprow"><button type="button" class="chip" data-cmd="/器灵">器灵面板</button>' +
      '<button type="button" class="chip" data-cmd="/温养 ' + esc(eq.name) + '">温养</button>' +
      '<button type="button" class="chip" data-fill="/灵语 ">灵语</button></div></div>';
  }
  function clueChainHtmlM(it) {
    var cc = it && it.clue_chain;
    if (!cc) return '<div class="muted">线索链未激活：研读宝图（/宝图）后顺带激活。</div>';
    var statusCn = { active: "进行中", awaiting_chest: "线索已尽 · 待开匣", completed: "已完成", abandoned: "已弃链" }[cc.status] || cc.status || "";
    return '<div class="clue-chain">寻宝线索链：' + esc(statusCn) + ' · 第 ' + esc(cc.step != null ? cc.step : 0) + '/' + esc(cc.total_steps != null ? cc.total_steps : 0) + ' 步' +
      (cc.current_node_name ? ' · 当前节点【' + esc(cc.current_node_name) + '】' : "") +
      '<div class="chiprow" style="margin-top:6px"><button type="button" class="chip" data-cmd="/寻宝">寻宝进度</button></div></div>';
  }
  var galleryNewlySeenKey = "";
  function checkGalleryNewly(st) {
    var g = st && st.gallery;
    if (!g || !Array.isArray(g.newly) || !g.newly.length) return;
    var key = g.newly.slice().sort().join(",") + "|" + (g.count || "");
    if (key === galleryNewlySeenKey) return;
    galleryNewlySeenKey = key;
    toast("图鉴新点亮：" + g.newly.length + " 图（" + (g.count || g.newly.length) + (g.total ? "/" + g.total : "") + "）", "ok");
  }
  function setText(id, v) {
    var el = $(id);
    if (el) el.textContent = v;
  }
  function setTheme(t) {
    state.theme = t === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", state.theme);
    localStorage.setItem("wb.theme", state.theme);
  }
  function toast(msg, kind) {
    var box = $("toasts");
    if (!box) return;
    var el = document.createElement("div");
    el.className = "toast" + (kind === "bad" ? " bad" : "");
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(function () {
      el.remove();
    }, 3200);
  }

  async function api(path, body) {
    var base = (state.base || "").trim().replace(/\/$/, "");
    if (base && !/^https?:\/\//i.test(base)) base = "http://" + base;
    var opts = {
      method: body ? "POST" : "GET",
      credentials: "omit",
      cache: "no-store",
    };
    if (body) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    var res;
    try {
      res = await fetch(base + path, opts);
    } catch (e) {
      throw new Error("无法感应阵枢灵脉（请确认服务已启动）");
    }
    if (!res.ok) {
      var msg = res.statusText || String(res.status);
      try {
        var j = await res.json();
        msg = j.error || j.message || msg;
      } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  function kindOf(text) {
    var t = String(text || "");
    if (/^»/.test(t)) return "cmd";
    if (/失败|错误|拒绝|不可|中断|身死|陨落/.test(t)) return "bad";
    if (/天道|世界弧|异象|大劫|血煞|机缘/.test(t)) return "ai";
    return "ok";
  }
  function pushFeed(text, kind, img) {
    if (!text) return;
    state.feed.push({
      text: String(text),
      kind: kind || kindOf(text),
      img: img || "",
      ts: Date.now() / 1000,
    });
    if (state.feed.length > 200) state.feed = state.feed.slice(-200);
    if (state.view === "feed") renderFeed();
  }
  function fmtTime(ts) {
    try {
      var d = new Date(ts * 1000);
      var p = function (n) {
        return (n < 10 ? "0" : "") + n;
      };
      return p(d.getHours()) + ":" + p(d.getMinutes());
    } catch (_) {
      return "";
    }
  }

  // ---- 状态同步：只读后端下发字段，不自造数值 ----
  function applyStatus(st) {
    if (!st) return;
    checkGalleryNewly(st);
    state.status = Object.assign({}, state.status || {}, st);
    setText("topDaoName", st.name || state.name || "—");
    setText(
      "topDaoRealm",
      (st.realm || "—") +
        (st.rank && st.rank !== "散修" ? " · " + st.rank : ""),
    );
    setText("topStones", (st.stones != null ? st.stones : 0) + " 灵石");
    setText(
      "topRemYears",
      "寿元 " +
        (st.rem_years != null ? Number(st.rem_years).toFixed(1) : "—") +
        " 载",
    );
    setText("topLocation", st.location || "—");
    renderCurrent();
  }

  function busy(on) {
    state.busy = !!on;
    var go = $("cmdGo");
    if (go) {
      go.disabled = !!on;
      go.textContent = on ? "…" : "发送";
    }
    var dot = $("busyDot");
    if (dot) dot.style.display = on ? "inline-block" : "none";
  }

  // ---- 各分区渲染 ----
  function renderCurrent() {
    if (state.view === "feed") renderFeed();
    else if (state.view === "sanctum") renderSanctum();
    else if (state.view === "bag") renderBag();
    else if (state.view === "world") renderWorld();
    else if (state.view === "ops") renderOps();
  }

  function renderFeed() {
    renderEntryCardM();
    var host = $("feedLog");
    if (!host) return;
    if (!state.feed.length) {
      host.innerHTML =
        '<div class="card empty"><div class="empty-seal">录</div><p class="empty-title">暂无动态</p><p class="muted">发一道敕令，或等天道演化</p><button type="button" class="btn primary" data-fill="/look ">观照道身</button></div>';
      return;
    }
    host.innerHTML = state.feed
      .slice(-60)
      .map(function (f) {
        return (
          '<div class="feed-line ' +
          esc(f.kind || "ok") +
          '">' +
          (f.kind === "ai" ? '<span class="feed-eyebrow">天道演化</span>' : "") +
          '<span class="ts">' +
          esc(fmtTime(f.ts)) +
          "</span>" +
          // 奇遇配图（omen_image，后端下发完整路径；失败 onerror 隐藏）
          (f.img ? galleryImg(f.img, "feed-omen-img", "奇遇配图") : "") +
          (f.kind === "cmd"
            ? '<span class="cmd-mark">»</span> ' + esc(String(f.text).replace(/^»\s?/, ""))
            : esc(f.text)) +
          "</div>"
        );
      })
      .join("");
    host.scrollTop = host.scrollHeight;
    window.scrollTo(0, document.body.scrollHeight);
  }

  function kv(k, v, cls) {
    return (
      '<div class="kv"><span class="k">' +
      esc(k) +
      '</span><span class="v' +
      (cls ? " " + cls : "") +
      '">' +
      v +
      "</span></div>"
    );
  }

  function renderSanctum() {
    var host = $("sanctumBody");
    if (!host) return;
    var st = state.status || {};
    if (!state.status) {
      host.innerHTML =
        '<div class="card muted">命盘未至。先发一道敕令（如 /look），或等候同步。</div>';
      return;
    }
    var expPct = 0;
    if (st.exp && String(st.exp).indexOf("/") >= 0) {
      var parts = String(st.exp).replace(/,/g, "").split("/");
      var cur = parseFloat(parts[0]) || 0;
      var max = parseFloat(parts[1]) || 1;
      expPct = Math.min(100, Math.max(0, Math.round((cur / max) * 100)));
    }
    var wallet = st.wallet || {};
    var past = st.past_life || {};
    var chains = st.karma_chains || {};
    var pet = st.pet || null;
    var arts = st.arts || {};
    var med = st.meditating || st.is_meditating;
    var html = "";
    // 人物立绘 + 定相 + 图鉴进度（§10.4-1）：portrait/gender/gallery 只认后端下发
    html += '<div class="card portrait-card">';
    if (st.portrait) html += galleryImg(st.portrait, "portrait-img", st.name || "人物立绘");
    html += '<div class="portrait-meta">';
    if (st.gender) {
      html += '<div class="muted">已定' + (st.gender === "female" ? "女" : "男") + '相 · 立绘随境界而变</div>';
    } else {
      html += '<div class="muted">尚未定相：当前为既有修行图占位。/定相 男|女 自选相貌（纯外观）。</div>';
    }
    html += '<div class="chiprow"><button type="button" class="chip" data-cmd="/定相 男">定相 · 男</button>' +
      '<button type="button" class="chip" data-cmd="/定相 女">定相 · 女</button></div>';
    if (st.gallery) {
      html += '<button type="button" class="gallery-progress-row" data-mview="ops">图鉴 ' +
        esc(st.gallery.count != null ? st.gallery.count : 0) + "/" + esc(st.gallery.total != null ? st.gallery.total : "—") +
        (st.gallery.title ? " · " + esc(st.gallery.title) : "") + " ›</button>";
    }
    html += "</div></div>";
    html +=
      '<div class="card"><p class="card-eyebrow">道身</p><h3>' +
      esc(st.name || state.name || "—") +
      " · " +
      esc(st.realm || "—") +
      "</h3>";
    html += kv("所在", esc(st.location || "—"));
    html += kv(
      "道身状态",
      esc(st.status_cn || st.status || "—") + (med ? " · " : ""),
    );
    if (st.blood_marked) html += kv("血煞", "血煞通缉", "warn");
    html += kv("修为", esc(st.exp || "—"));
    html +=
      '<div class="bar-row"><div class="bar"><i style="width:' +
      expPct +
      '%"></i></div><span class="pct">' +
      expPct +
      "%</span></div>";
    html += "</div>";
    html +=
      '<div class="card"><p class="card-eyebrow">身家</p><div class="stat-grid">' +
      '<div class="stat-cell"><span class="num">' +
      esc(st.stones != null ? st.stones : 0) +
      '</span><span class="lbl">灵石</span></div>' +
      '<div class="stat-cell"><span class="num">' +
      esc(st.vault != null ? st.vault : 0) +
      '</span><span class="lbl">金库</span></div>' +
      '<div class="stat-cell"><span class="num">' +
      esc(wallet.balance != null ? wallet.balance : 0) +
      '</span><span class="lbl">账户钱包</span></div></div></div>';
    html += '<div class="card"><p class="card-eyebrow">道途</p>';
    html += kv(
      "寿元",
      esc(st.rem_years != null ? Number(st.rem_years).toFixed(1) + " 载" : "—") +
        (st.lifespan_warning ? " · 告急" : ""),
      st.lifespan_warning ? "warn" : "",
    );
    html += kv("道心", esc(st.dao_heart != null ? st.dao_heart : "—"));
    html += kv(
      "因果 / 功德",
      esc(st.sin != null ? st.sin : "—") +
        " / " +
        esc(st.merit != null ? st.merit : "—"),
    );
    html += kv(
      "宗门",
      esc((st.sect || "散修") + (st.rank ? " · " + st.rank : "")),
    );
    html += kv(
      "宗门贡献",
      esc(st.sect_contribution != null ? st.sect_contribution : 0),
    );
    html += kv("灵根", esc(st.root || "—"));
    if (pet)
      html += kv(
        "灵宠",
        // 灵宠图（game-feel-phase2 §9.3）：pet.img 只认后端下发，缺失不渲染图位
        (pet.img ? galleryImg(pet.img, "pet-thumb", pet.name || "灵宠") : "") +
          esc(
            pet.name +
              " · " +
              pet.species +
              " · " +
              pet.level +
              " 级 · 亲密度 " +
              pet.intimacy,
          ),
      );
    else
      html += kv(
        "灵宠",
        "未收服（在养 " +
          esc(st.pets_count != null ? st.pets_count : 0) +
          " 只）",
      );
    if (arts.main) html += kv("主修心法", esc(arts.main));
    if (arts.sub && arts.sub.length)
      html += kv("辅修心法", esc(arts.sub.join("、")));
    if (st.skills && st.skills.length)
      html += kv("法门", esc(st.skills.join("、")));
    if (st.skills && st.skills.length) {
      // 功法图（art_images，后端下发）
      var artImgs = st.art_images || {};
      html += '<div class="kv"><span class="k">法门图</span><span class="v art-chips">' +
        st.skills.map(function (n) {
          return '<span class="art-chip">' + galleryImg(artImgs[n], "art-thumb", n) + "<span>" + esc(n) + "</span></span>";
        }).join("") + "</span></div>";
    }
    if (st.spells_catalog && st.spells_catalog.length) {
      // 神通图（spells_catalog[].img，后端下发）
      html += '<div class="kv"><span class="k">神通图</span><span class="v art-chips">' +
        st.spells_catalog.map(function (sp) {
          return '<span class="art-chip">' + galleryImg(sp.img, "art-thumb", sp.name || "神通") + "<span>" + esc(sp.name || "") + "</span></span>";
        }).join("") + "</span></div>";
    }
    html += "</div>";
    html += '<div class="card"><p class="card-eyebrow">前世因果</p>';
    if (past.lives) {
      html += kv(
        "前世",
        esc(
          "已历 " +
            past.lives +
            " 世" +
            (past.last_name ? " · 上世 " + past.last_name : "") +
            (past.last_cause ? "（" + past.last_cause + "）" : "") +
            (past.shadow_count ? " · 前缘 " + past.shadow_count + " 缕" : ""),
        ),
      );
    }
    html += kv(
      "因果链",
      esc("进行中 " + (chains.active != null ? chains.active : 0) + " 条"),
    );
    html += "</div>";
    // 俸禄与晋升
    html += '<div class="card"><h3>宗门俸禄</h3>';
    html += kv("月俸", esc(st.salary != null ? st.salary : 0) + " 灵石");
    if (st.salary_claimable) {
      html +=
        '<button type="button" class="btn primary block" data-cmd="/领俸禄">领俸禄</button>';
    } else if (st.salary_cd_sec) {
      html +=
        '<div class="muted">下次领俸约 ' +
        esc(Math.ceil(st.salary_cd_sec / 60)) +
        " 分钟后</div>";
    }
    if (st.can_promote && st.next_rank) {
      html +=
        '<button type="button" class="btn secondary block" data-cmd="/晋升">晋升' +
        esc(st.next_rank) +
        "</button>";
    }
    html += "</div>";
    // 钱包提取（只发命令，不预改余额）
    html +=
      '<div class="card"><h3>钱包提取</h3><div class="inline-row">' +
      '<input id="walletAmt" type="number" inputmode="numeric" min="1" placeholder="提取金额" aria-label="提取金额" />' +
      '<button type="button" class="btn primary" id="btnWalletWithdraw">提取</button></div>' +
      '<div class="muted">余额以服务端为准；转世后钱包随账户保留。</div></div>';
    host.innerHTML = html;
    var wb = $("btnWalletWithdraw");
    if (wb)
      wb.addEventListener("click", function () {
        var amt = (($("walletAmt") && $("walletAmt").value) || "").trim();
        if (!amt) {
          toast("请先填提取金额", "bad");
          return;
        }
        sendCmd("/钱包提取 " + amt);
      });
    var gfHtml = (st.origin ? '<div class="card"><details><summary><b>出身 · ' + esc(st.origin.family_text || st.origin.family || "") + '</b></summary>' + originBodyHtmlM({ origin: st.origin }) + "</details></div>" : "") + fateSectionHtmlM(st.fate) + fateThreadHtmlM(st.fate) + relationsSectionHtmlM(st.relations_recent);
    if (gfHtml) { var gd = document.createElement("div"); gd.innerHTML = gfHtml; host.appendChild(gd); }
  }

  function tierClass(t) {
    var m = { 凡品: "tier-1", 人品: "tier-2", 地品: "tier-3", 天品: "tier-4", 仙品: "tier-5" };
    return m[t] || "tier-0";
  }

  function renderBag() {
    var host = $("bagBody");
    if (!host) return;
    var st = state.status || {};
    var items = Array.isArray(st.items) ? st.items : [];
    var equipped = Array.isArray(st.equipped) ? st.equipped : [];
    var html = "";
    html += '<div class="card"><h3>已穿戴（' + equipped.length + "）</h3>";
    if (!equipped.length)
      html +=
        '<div class="empty"><div class="empty-seal">戒</div><p class="empty-title">未穿戴任何法宝</p><p class="muted">去探险寻宝，或入纳戒挑选</p><button type="button" class="chip ghost" data-cmd="/探险">去探险寻宝</button></div>';
    equipped.forEach(function (eq) {
      html +=
        '<div class="eq-row"><span class="eq-main">' +
        (eq.img ? '<span class="' + galleryFrameClass(eq.tier) + '">' + galleryImg(eq.img, "equip-thumb", eq.name) + "</span>" : "") +
        '<span class="slot">' +
        esc(eq.slotCn || eq.slot || "法宝") +
        '</span><span class="nm">' +
        esc(eq.name) +
        '</span></span><span class="tg ' +
        tierClass(eq.tierName) +
        '">' +
        esc(eq.tierName || "") +
        "</span></div>";
      html += spiritHtmlM(eq);
      if (!eq.spirit && (eq.tier || 0) >= 4)
        html += '<div class="chiprow"><button type="button" class="chip" data-cmd="/器灵 唤 ' + esc(eq.name) + '">唤灵</button></div>';
    });
    html += "</div>";
    // 同名合并 ×n
    var merged = {};
    var order = [];
    items.forEach(function (it) {
      if (!merged[it.name]) {
        merged[it.name] = { item: it, n: 0 };
        order.push(it.name);
      }
      merged[it.name].n += 1;
    });
    var maxSlots = st.max_bag_slots != null ? st.max_bag_slots : 64;
    var capPct = Math.min(100, Math.round((items.length / maxSlots) * 100));
    html +=
      '<div class="card"><h3>纳戒（' +
      items.length +
      " / " +
      esc(maxSlots) +
      " 格）</h3>" +
      '<div class="cap-bar"><i class="' +
      (items.length >= 56 ? "full" : "") +
      '" style="width:' +
      capPct +
      '%"></i></div>';
    if (!order.length)
      html +=
        '<div class="empty"><div class="empty-seal">戒</div><p class="empty-title">纳戒空空</p><p class="muted">可 /探险 寻机缘，或去坊市采买</p><button type="button" class="chip ghost" data-cmd="/探险">去探险</button></div>';
    order.forEach(function (name) {
      var m = merged[name];
      var it = m.item;
      var sel = state.selectedBagName === name;
      html +=
        '<button type="button" class="bag-row' +
        (sel ? " sel" : "") +
        '" data-bag="' +
        esc(name) +
        '">' +
        (it.img ? '<span class="' + galleryFrameClass(it.tier) + '">' + galleryImg(it.img, "bag-thumb", name) + "</span>" : "") +
        '<span class="tg ' +
        tierClass(it.tierName) +
        '">' +
        esc(it.tierName || "凡品") +
        "</span>" +
        '<span class="nm">' +
        esc(name) +
        "</span>" +
        (m.n > 1 ? '<span class="ct">×' + m.n + "</span>" : "") +
        '<span class="kind">' +
        esc(it.kind || "") +
        "</span></button>";
      if (sel) {
        html +=
          '<div class="card bag-detail">' +
          (it.img ? '<div class="' + galleryFrameClass(it.tier) + '">' + galleryImg(it.img, "detail-img", name) + "</div>" : "") +
          '<div class="muted">' +
          esc(it.desc || it.lore || "") +
          "</div>";
        // 已穿戴同名器物的器灵（spirit 只在 equipped[] 下发）
        var selEq = equipped.filter(function (e) { return e.name === name; })[0];
        if (selEq) html += spiritHtmlM(selEq);
        if (it.kind === "treasure_map" || it.kind === "map" || name.indexOf("图") >= 0)
          html += clueChainHtmlM(it);
        html += '<div class="chiprow" style="margin-top:8px">';
        if (it.kind === "equip")
          html +=
            '<button type="button" class="chip primary" data-cmd="/穿戴 ' +
            esc(name) +
            '">穿戴</button>' +
            '<button type="button" class="chip" data-cmd="/卸下 ' +
            esc(name) +
            '">卸下</button>';
        if (it.kind === "pill" || it.kind === "consumable")
          html +=
            '<button type="button" class="chip primary" data-cmd="/服用 ' +
            esc(name) +
            '">服用</button>';
        if (
          it.kind === "treasure_map" ||
          it.kind === "map" ||
          name.indexOf("图") >= 0
        )
          html +=
            '<button type="button" class="chip primary" data-cmd="/宝图 ' +
            esc(name) +
            '">研读宝图</button>' +
            '<button type="button" class="chip" data-cmd="/寻宝">寻宝</button>' +
            '<button type="button" class="chip" data-cmd="/挖宝 ' +
            esc(name) +
            '">挖宝</button>';
        html +=
          '<button type="button" class="chip ghost" data-fill="/寄售 ' +
          esc(name) +
          ' ">寄售</button>';
        html += "</div></div>";
      }
    });
    html += "</div>";
    host.innerHTML = html;
  }

  function renderWorld() {
    var host = $("worldBody");
    if (!host) return;
    var html = "";
    // 地点场景头图（game-feel-phase2 §9.4）：location_image 只认后端下发，空串不渲染图位
    var stW = state.status || {};
    if (stW.location_image) html += '<div class="card scene-card">' + galleryImg(stW.location_image, "world-scene-img", stW.location || "当前地点") + '<p class="card-eyebrow">' + esc(stW.location || "") + "</p></div>";
    // 主动戏剧当面行（§5.4）：迁跃/登录的当面戏剧复用入局 proactive 行结构呈现于世界分区
    var pvW = state.entry && state.entry.proactive && typeof state.entry.proactive === "object" ? state.entry.proactive : null;
    if (pvW && pvW.drama_id) html += '<div class="card"><p class="card-eyebrow">当面来访</p>' + dramaRowHtmlM(pvW) + "</div>";
    var w = state.world || {};
    var lines =
      w.summary_lines || (w.evolution && w.evolution.summary_lines) || [];
    if (lines.length) {
      html +=
        '<div class="card"><p class="card-eyebrow">世界态势</p>' +
        lines
          .slice(0, 5)
          .map(function (l) {
            return '<p class="world-para' + (/血煞/.test(l) ? " warn" : "") + '">' + esc(l) + "</p>";
          })
          .join("") +
        "</div>";
    } else {
      html +=
        '<div class="card"><p class="card-eyebrow">世界态势</p><p class="world-para">天道暂无活跃态势</p><p class="muted">诸天暂静，可先观照自身命盘，或迁跃他方。</p></div>';
    }
    html += '<div class="card"><h3>同场修士（' + state.here.length + "）</h3>";
    if (!state.here.length)
      html +=
        '<div class="empty"><div class="empty-seal">人</div><p class="empty-title">周遭方圆暂无其他修士</p><p class="muted">可迁跃前往客栈或宗门</p><button type="button" class="chip ghost" data-cmd="/go 青云坊市客栈">迁跃去客栈</button></div>';
    state.here.forEach(function (r) {
      var tag = r.blood_marked
        ? "血煞通缉"
        : !r.is_npc
          ? "同道仙友"
          : r.attitude_cn || "中立";
      var tagCls = r.blood_marked ? " danger" : !r.is_npc ? " gold" : r.attitude_cn === "友善" ? " friend" : r.attitude_cn === "仇视" ? " danger" : "";
      html +=
        '<div class="person"><div class="row1"><span class="nm">' +
        (r.avatar ? galleryImg(r.avatar, "here-avatar", r.name) : "") +
        esc(r.name) +
        '</span><span class="tag' +
        tagCls +
        '">' +
        esc(tag) +
        "</span>" + relationMarkM(r) + "</div>" +
        '<div class="muted">' +
        esc(r.realm || "") +
        " · " +
        esc(r.sect || "散修") +
        (r.rank ? " · " + esc(r.rank) : "") +
        "</div>" +
        '<div class="acts">' +
        '<button type="button" class="btn primary" data-fill="/交谈 ' +
        esc(r.name) +
        ' ">传音</button>' +
        '<button type="button" class="btn secondary" data-cmd="/交易 ' +
        esc(r.name) +
        '">交易</button>' +
        '<button type="button" class="btn danger" data-cmd="/斗法 ' +
        esc(r.name) +
        '">切磋</button>' +
        "</div></div>";
    });
    html += "</div>";
    var cur = (state.status && state.status.location) || "";
    html += '<div class="card"><h3>十方迁跃</h3>';
    PLACES.forEach(function (p) {
      var isCur = p.name === cur;
      html +=
        '<div class="place-row"><span class="nm">' +
        esc(p.name) +
        '<span class="tip">' +
        esc(p.tip) +
        "</span></span>" +
        (isCur
          ? '<span class="pill-cur">当前所在</span>'
          : '<button type="button" class="btn secondary" data-cmd="/go ' +
            esc(p.name) +
            '">迁跃</button>') +
        "</div>";
    });
    html += "</div>";
    host.innerHTML = html;
  }

  // 图鉴段（§10.4-4）：操作分区整页段，四类紧凑列表；点亮只认 st.gallery.unlocked
  function renderGalleryOps() {
    var host = $("galleryOps");
    if (!host) return;
    var st = state.status || {};
    var g = st.gallery || { unlocked: [], count: 0, total: 0, title: "" };
    var unlocked = {};
    (Array.isArray(g.unlocked) ? g.unlocked : []).forEach(function (k) { unlocked[k] = true; });
    var html = '<div class="muted">进度 ' + esc(g.count != null ? g.count : 0) + "/" + esc(g.total || "—") +
      (g.title ? " · 称号【" + esc(g.title) + "】（仅展示）" : " · 称号档：10 初窥门径 / 40 博览群真 / 80 洞鉴乾坤 / 120 博物通览 / 139 图录大成") + "</div>";
    GALLERY_GROUPS.forEach(function (grp) {
      html += '<div class="section-title">' + esc(grp.title) + "</div>";
      grp.keys.forEach(function (entry) {
        var key = entry[0], cn = entry[1], cond = entry[2];
        var lit = !!unlocked[key];
        html += '<div class="gallery-row">' + galleryImg(galleryAssetPath(key), lit ? "gallery-thumb" : "gallery-thumb gallery-silhouette", cn) +
          '<span class="nm">' + esc(cn) + '</span><span class="muted">' + (lit ? "◆ 已点亮" : "◇ " + esc(cond)) + "</span></div>";
      });
    });
    html += '<button type="button" class="btn secondary block" data-cmd="/图鉴">图鉴文本（/图鉴）</button>';
    host.innerHTML = html;
  }

  function renderOps() {
    var host = $("opsBody");
    if (!host) return;
    if (state.opsBuilt) { renderGalleryOps(); renderCeremonySkipOpsM(); return; }
    state.opsBuilt = true;
    var opts = PLACES.map(function (p) {
      return '<option value="' + esc(p.name) + '">' + esc(p.name) + "</option>";
    }).join("");
    host.innerHTML =
      '<div class="section-title">高频操作</div>' +
      '<div class="ops-grid">' +
      '<button type="button" class="btn primary ops-hero" data-cmd="/突破">突破</button>' +
      '<button type="button" class="btn secondary" data-cmd="/闭关">闭关</button>' +
      '<button type="button" class="btn secondary" data-cmd="/出关">出关</button>' +
      '<button type="button" class="btn secondary" data-cmd="/探险">探险</button>' +
      '<button type="button" class="btn secondary" data-cmd="/奇遇">奇遇</button>' +
      '<button type="button" class="btn secondary" data-cmd="/领俸禄">领俸禄</button>' +
      "</div>" +
      '<div class="section-title">传音（与同场修士交谈）</div>' +
      '<div class="chat-stack"><input id="chatName" type="text" placeholder="对方道号" aria-label="对方道号" />' +
      '<input id="chatText" type="text" placeholder="传音内容" aria-label="传音内容" /></div>' +
      '<button type="button" class="btn secondary block" id="btnChatSend">传音</button>' +
      '<div class="section-title">迁跃</div>' +
      '<div class="inline-row"><select id="goSelect" aria-label="迁跃目的地">' +
      opts +
      "</select>" +
      '<button type="button" class="btn secondary" id="btnGo">迁跃</button></div>' +
      '<div class="inline-row"><button type="button" class="btn secondary" id="btnCrane">灵鹤派遣</button></div>' +
      '<div class="section-title">常用命令（点按填入命令框）</div>' +
      '<div class="chiprow">' +
      [
        "/宗门",
        "/坊市",
        "/墓碑 ",
        "/道统",
        "/因果链",
        "/命途",
        "/回应 ",
        "/钱包",
        "/寄存 ",
        "/支取 ",
        "/典当 ",
        "/灵宠",
        "/任务",
        "/天道",
        "/世情",
        "/帮助",
      ]
        .map(function (c) {
          return (
            '<button type="button" class="chip" data-fill="' +
            esc(c) +
            '">' +
            esc(c.replace(/ $/, "")) +
            "</button>"
          );
        })
        .join("") +
      '<button type="button" class="chip" data-fill="/灵鹤 ">灵鹤</button>' +
      "</div>" +
      '<div class="card"><p class="card-eyebrow">定相（纯外观，随时可改）</p>' +
      '<div class="chiprow">' +
      '<button type="button" class="chip" data-cmd="/定相 男">定相 · 男</button>' +
      '<button type="button" class="chip" data-cmd="/定相 女">定相 · 女</button>' +
      "</div></div>" +
      '<div class="card"><p class="card-eyebrow">天道图鉴</p>' +
      '<div id="galleryOps"></div></div>' +
      '<div class="card"><p class="card-eyebrow">显示与切换</p>' +
      '<button type="button" class="display-row" data-theme-toggle="1">昼夜天象切换<span class="arr">›</span></button>' +
      '<button type="button" class="display-row" data-view-switch="desktop">桌面版<span class="arr">›</span></button>' +
      '<button type="button" class="display-row" data-auto-view="1">跟随设备自动选择<span class="arr">›</span></button>' +
      '<div id="ceremonySkipOps"></div></div>' +
      '<p class="muted">场景操作（秘境推进、挖宝、灵宠出战等）均可直接在下方命令框输入对应命令；服务端裁决为准。</p>';
    $("btnChatSend").addEventListener("click", function () {
      var n = ($("chatName").value || "").trim();
      var t = ($("chatText").value || "").trim();
      if (!n && !t) {
        toast("请先填对方道号或传音内容", "bad");
        return;
      }
      sendCmd(n && t ? "/交谈 " + n + " " + t : t || "/交谈 " + n);
    });
    $("btnGo").addEventListener("click", function () {
      sendCmd("/go " + $("goSelect").value);
    });
    $("btnCrane").addEventListener("click", function () {
      sendCmd("/灵鹤 " + $("goSelect").value);
    });
    renderGalleryOps();
    renderCeremonySkipOpsM();
  }

  function setView(v) {
    var valid = ["feed", "sanctum", "bag", "world", "ops"];
    if (valid.indexOf(v) < 0) v = "feed";
    state.view = v;
    document.querySelectorAll("[data-mview]").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mview") === v);
    });
    document.querySelectorAll("[data-pane]").forEach(function (p) {
      p.hidden = p.getAttribute("data-pane") !== v;
    });
    renderCurrent();
    if ((v === "sanctum" || v === "world") && state.token && !state.demo)
      refreshAll();
  }

  // ---- 游戏感第一期（game-feel-phase1）：只认后端下发结构渲染，缺失即不渲染 ----
  var CEREMONY_CN_M = { breakthrough: "突破", death: "归府", rebirth: "转世" };
  var STAGE_CN_M = { prelude: "前奏", reveal: "揭晓", aftermath: "余韵" };
  function ceremonySkippedM(kind) { try { return localStorage.getItem("ceremony_skip_" + kind) === "1"; } catch (_) { return false; } }
  function closeOverlayM(id) { var el = $(id); if (el) el.remove(); }
  // 件一 · 移动入局卡（§2.5）：feed 置顶，数据同 state.entry
  function entryTargetAttrsM(t) {
    if (!t) return "";
    if (t.command) return ' data-cmd="' + esc(t.command) + '"';
    if (t.view) {
      var v = { entry: "feed", inventory: "bag", bazaar: "ops", gallery: "ops" }[t.view] || t.view;
      if (["feed", "sanctum", "bag", "world", "ops"].indexOf(v) >= 0) return ' data-mview="' + esc(v) + '"';
      return ' data-entry-view="' + esc(t.view) + '"';
    }
    return "";
  }
  // 入局新 kind（game-feel-phase2 §8.2）：fate_chapter 命途 / drama 戏剧（drama 带 options 回应按钮组）
  var ENTRY_KIND_CN_M = { fate_chapter: "命途", drama: "戏剧" };
  var DRAMA_TYPE_CN_M = { betrayal: "背叛", provoke: "挑衅", involvement: "牵连", help: "求助", favor: "示好" };
  function entryItemHtmlM(it) {
    if (!it) return "";
    var attrs = entryTargetAttrsM(it.target);
    var tag = ENTRY_KIND_CN_M[it.kind] ? '<span class="entry-kind">' + ENTRY_KIND_CN_M[it.kind] + "</span>" : "";
    var opts = "";
    if (it.kind === "drama" && Array.isArray(it.options) && it.options.length) {
      var base = it.id ? "/回应 " + it.id + " " : (it.target && it.target.command ? it.target.command + " " : "/回应 ");
      opts = '<span class="chiprow">' + it.options.map(function (o) { return '<button type="button" class="chip primary" data-cmd="' + esc(base + (o.key || "")) + '">' + esc(o.label || o.key || "回应") + "</button>"; }).join("") + "</span>";
    }
    return '<div class="entry-act">' + tag + '<span class="tx"><b>' + esc(it.title || it.kind || "待办") + "</b>" + (it.text ? '<br><span class="muted">' + esc(it.text) + "</span>" : "") + "</span>" + opts + (attrs && !opts ? '<button type="button" class="chip primary"' + attrs + ">前往</button>" : "") + "</div>";
  }
  // 交谈旧账行文案（game-feel-phase2 §8.3，双端同文案）：字段缺失的段落不拼，不自造数
  function oldAccountTextM(oa) {
    if (!oa || typeof oa !== "object") return "";
    var parts = [];
    if (oa.open_promises != null) parts.push("未了诺言 " + oa.open_promises);
    if (oa.chains_with_npc != null) parts.push("与他发酵中因果 " + oa.chains_with_npc);
    else if (oa.fermenting_chains != null) parts.push("发酵中因果 " + oa.fermenting_chains);
    if (oa.nearest_chain_game_days != null) parts.push("最近一条约 " + oa.nearest_chain_game_days + " 游戏日");
    if (oa.last_relation) parts.push("最近：" + oa.last_relation);
    return parts.length ? "旧账：" + parts.join(" · ") : "";
  }
  // 主动戏剧当面行（§5.4/§8.2）：复用 entry.proactive 结构，drama_id 在场才渲染为戏剧行
  function dramaRowHtmlM(pv) {
    if (!pv || !pv.drama_id) return "";
    return '<div class="drama-row"><span class="entry-kind">戏剧' + (pv.drama_type ? "·" + esc(DRAMA_TYPE_CN_M[pv.drama_type] || pv.drama_type) : "") + '</span><span class="tx">' + (pv.npc ? "<b>" + esc(pv.npc) + "</b> " : "") + esc(pv.text || pv.line || "") + '</span><button type="button" class="chip primary" data-fill="/回应 ">去回应</button></div>';
  }
  function renderEntryCardM() {
    var host = $("entryCard");
    if (!host) return;
    var e = state.entry;
    if (!e) { host.innerHTML = state.entryPending ? '<div class="card"><p class="muted">天道繁忙，入局信息待补——可先自由行动。</p></div>' : ""; return; }
    var lines = e.lines || {};
    var html = '<div class="card"><p class="card-eyebrow">入局 · 当下之事</p>';
    if (lines.fate) html += '<p class="world-para">' + esc(lines.fate) + "</p>";
    if (lines.chains && (lines.chains.text || lines.chains.fermenting != null)) html += '<p class="world-para">' + esc(lines.chains.text || ("发酵中因果链 " + lines.chains.fermenting + " 条")) + "</p>";
    if (Array.isArray(lines.relations)) lines.relations.forEach(function (r) { if (r && r.summary) html += '<p class="world-para">' + esc(r.summary) + "</p>"; });
    var pvObj = e.proactive && typeof e.proactive === "object" ? e.proactive : null;
    var pv = typeof e.proactive === "string" ? e.proactive : (pvObj && pvObj.text) || "";
    if (pvObj && pvObj.drama_id) html += dramaRowHtmlM(pvObj);
    else if (pv) html += '<p class="world-para">' + esc(pv) + "</p>";
    var queue = Array.isArray(e.queue) ? e.queue : [];
    var hl = Array.isArray(e.highlight) && e.highlight.length ? e.highlight : queue.slice(0, 3);
    if (e.empty || !queue.length) html += '<p class="muted">' + esc(e.empty_text || "江湖无事，可自由行动") + "</p>";
    else {
      hl.forEach(function (it) { html += entryItemHtmlM(it); });
      var rest = queue.slice(hl.length);
      if (rest.length) {
        html += "<details><summary>另有 " + esc(e.rest_count != null ? e.rest_count : rest.length) + " 件待办</summary>";
        rest.forEach(function (it) { html += entryItemHtmlM(it); });
        html += "</details>";
      }
    }
    host.innerHTML = html + "</div>";
  }
  async function refreshEntryM() {
    if (state.demo || !state.token) return;
    try {
      var base = (state.base || "").trim().replace(/\/$/, "");
      if (base && !/^https?:\/\//i.test(base)) base = "http://" + base;
      var res = await fetch(base + "/world/briefing", { headers: { Authorization: "Bearer " + state.token }, cache: "no-store" });
      if (!res.ok) return;
      var b = await res.json();
      if (b && b.entry) { state.entry = b.entry; state.entryPending = false; }
    } catch (_) {}
  }

  // 件二 · 出身（§3.11）：全屏卡（gate 视觉语言）+ 命盘折叠段；origin 缺失不出现
  function originRowsM(o) {
    var rows = [];
    if (!o) return rows;
    if (o.family_text || o.family) rows.push(["家世", o.family_text || o.family]);
    var os = o.old_story || {};
    if (os.summary || os.kind) rows.push(["旧事", os.summary || os.kind]);
    var rel = [];
    if (o.debt && o.debt.amount) rel.push("欠" + (o.debt.creditor_name || "旧债主") + " " + o.debt.amount + " 灵石（旧债）");
    if (Array.isArray(o.relations) && o.relations.length) {
      var rc = { kin: "亲缘", foe: "宿怨", witness: "知情" };
      // 世仇植入条目（game-feel-phase2 §4.3）：relations[].vendetta 在场才加世仇行标记
      rel.push(o.relations.map(function (r) { return (r.npc_name || "") + "·" + (rc[r.role] || r.role || "") + (r.init_value != null ? " " + (r.init_value > 0 ? "+" : "") + r.init_value : "") + (r.vendetta ? "·世仇" + (r.vendetta_for ? "（替" + r.vendetta_for + "讨前世血债）" : "（前世血债未清）") : ""); }).join("、"));
    }
    if (rel.length) rows.push(["债与关系", rel.join("；")]);
    if (Array.isArray(o.path_gates) && o.path_gates.length) {
      var ec = { closed: "拒止", favored: "亲近" };
      rows.push(["路径开关", o.path_gates.map(function (g) { return (g.target_ref || "") + "（" + (ec[g.effect] || g.effect || "") + "）"; }).join("、")]);
    }
    if (o.birthplace) rows.push(["出生地", o.birthplace]);
    return rows;
  }
  function originFateLineM(o) {
    if (!o) return "";
    if (o.fate_text || o.proposition) return o.fate_text || o.proposition;
    return (state.entry && state.entry.lines && state.entry.lines.fate) || "";
  }
  function originBodyHtmlM(oc) {
    var o = oc && oc.origin;
    if (!o) return "";
    var html = oc.prev_epitaph ? '<p class="gold">前世曰：' + esc(oc.prev_epitaph) + "</p>" : "";
    originRowsM(o).forEach(function (r) { html += kv(r[0], esc(r[1])); });
    var fl = originFateLineM(o);
    if (fl) html += '<p class="gold">终局命题：' + esc(fl) + "</p>";
    return html;
  }
  function showOriginOverlayM() {
    var oc = state.originCard;
    if (!oc || !oc.just_created || !oc.origin) return;
    closeOverlayM("originOverlay");
    var ov = document.createElement("div");
    ov.id = "originOverlay"; ov.className = "gf-overlay";
    ov.innerHTML = '<div class="gf-card"><p class="card-eyebrow">此世出身</p>' + originBodyHtmlM(oc) +
      '<button type="button" class="btn primary block" data-origin-close="1">收起出身卡</button></div>';
    document.body.appendChild(ov);
  }

  // 件三 · 仪式与命格（§4.1/§4.5）：全屏卡只认 ceremony 结构；略过纯前端关闭
  function fateSectionHtmlM(fate) {
    if (!fate || typeof fate !== "object") return "";
    var pending = fate.pending || fate.fate_pending || fate.pending_draws || [];
    if (!Array.isArray(pending)) pending = [];
    if (!pending.length && Array.isArray(fate.candidates) && fate.candidates.length) pending = [{ candidates: fate.candidates }];
    var boons = fate.boons || fate.fate_boons || fate.chosen || [];
    if (!Array.isArray(boons)) boons = [];
    if (!pending.length && !boons.length) return "";
    var html = '<div class="card"><h3>命格待选</h3>';
    if (boons.length) html += '<p class="muted">已选：' + boons.map(function (b) { return esc((b.icon ? b.icon + " " : "") + (b.name || b.key || "")); }).join("、") + "</p>";
    pending.forEach(function (draw, di) {
      var cands = (draw && draw.candidates) || [];
      if (!cands.length) return;
      if (di === 0) cands.forEach(function (c) {
        html += '<div class="kv"><span class="k">' + esc(c.icon || "✦") + " " + esc(c.name || c.key || "") + '</span><button type="button" class="chip primary" data-fate-choice="' + esc(c.key || "") + '">择此命格</button></div>';
        if (c.desc) html += '<p class="muted">' + esc(c.desc) + "</p>";
      });
      else html += '<p class="muted">后续待选：' + cands.map(function (c) { return esc(c.name || c.key || ""); }).join("、") + "（先择前一抽）</p>";
    });
    return html + "</div>";
  }
  // 命途主线全量段（game-feel-phase2 §8.1）：只认 fate.thread 下发，null/缺失不渲染，字段缺失不自造
  var THREAD_SEED_CN_M = { unfinished: "未竟之志", vendetta: "世仇", karma_shadow: "前世影子", blood_feud: "血仇", sect: "宗门风云", origin: "出身旧事" };
  var THREAD_STATUS_CN_M = { active: "进行中", shelved: "已搁置", completed: "已了结", broken: "中道崩殂", inherited: "留待来世", done: "已成", failed: "未成" };
  var CHAPTER_STATUS_CN_M = { done: "已成", active: "进行中", locked: "未启", failed: "未成" };
  var CHAPTER_TIER_CN_M = { short: "短期", mid: "中期", final: "终局" };
  function fateThreadHtmlM(fate) {
    var th = fate && typeof fate === "object" ? fate.thread : null;
    if (!th || typeof th !== "object") return "";
    var html = '<div class="card"><p class="card-eyebrow">命途主线</p><h3>' + esc(th.title || "命途") + "</h3>";
    html += kv("种子来源", esc((THREAD_SEED_CN_M[th.seed_source] || th.seed_source || "—") + (th.status ? " · " + (THREAD_STATUS_CN_M[th.status] || th.status) : "")));
    if (th.antagonist && th.antagonist.name) html += kv("对手", esc(th.antagonist.name));
    if (th.patron && th.patron.name) html += kv("引路人", esc(th.patron.name));
    (Array.isArray(th.chapters) ? th.chapters : []).forEach(function (c) {
      if (!c) return;
      var cur = c.status === "active" && (th.current_chapter == null || c.idx === th.current_chapter);
      html += '<div class="kv thread-ch' + (cur ? " cur" : "") + '"><span class="k">第' + esc((c.idx != null ? c.idx : 0) + 1) + "章" + (c.tier ? " · " + esc(CHAPTER_TIER_CN_M[c.tier] || c.tier) : "") + '</span><span class="v">' + esc(c.title || "") + ' <span class="muted">' + esc(CHAPTER_STATUS_CN_M[c.status] || c.status || "") + "</span>" + (c.goal_text ? '<br><span class="muted">' + esc(c.goal_text) + "</span>" : "") + "</span></div>";
    });
    var fp = th.final_proposition || {};
    if (fp.text) html += kv("终局命题", esc(fp.text) + (fp.status ? "（" + esc(THREAD_STATUS_CN_M[fp.status] || fp.status) + "）" : ""));
    if (th.shelvable) html += '<button type="button" class="btn secondary block" data-cmd="/命途 搁置">搁置命途</button>';
    else if (th.status === "shelved") html += '<button type="button" class="btn primary block" data-cmd="/命途 续">续接命途</button>';
    return html + "</div>";
  }
  function maybeShowCeremonyM(cer) {
    if (!cer || !cer.kind || ceremonySkippedM(cer.kind)) return;
    closeOverlayM("ceremonyOverlay");
    var html = "";
    (Array.isArray(cer.beats) ? cer.beats : []).forEach(function (b) {
      if (!b) return;
      if (b.asset_key) html += galleryImg("/assets/" + b.asset_key + ".webp", "feed-omen-img", b.stage || "");
      html += '<p class="card-eyebrow">' + esc(STAGE_CN_M[b.stage] || b.stage || "") + '</p><p class="world-para">' + esc(b.text || "") + "</p>";
      if (Array.isArray(b.choices) && b.choices.length) {
        html += '<div class="chiprow">' + b.choices.map(function (c) { return '<button type="button" class="chip primary" data-fate-choice="' + esc(c.key || "") + '">' + esc(c.icon || "✦") + " " + esc(c.name || c.key || "") + "</button>"; }).join("") + "</div>";
        b.choices.forEach(function (c) { if (c.desc) html += '<p class="muted">' + esc(c.name || "") + "：" + esc(c.desc) + "</p>"; });
      }
    });
    var rr = cer.result_ref && typeof cer.result_ref === "object" ? Object.keys(cer.result_ref).filter(function (k) { var v = cer.result_ref[k]; return v != null && typeof v !== "object"; }).map(function (k) { return k + ": " + cer.result_ref[k]; }).join(" · ") : "";
    if (rr) html += '<p class="muted">' + esc(rr) + "</p>";
    var ov = document.createElement("div");
    ov.id = "ceremonyOverlay";
    ov.className = "gf-overlay";
    ov.innerHTML = '<div class="gf-card"><p class="card-eyebrow">' + esc(CEREMONY_CN_M[cer.kind] || "仪式") + "仪式</p>" + (html || '<p class="muted">仪式已成。</p>') +
      '<label class="muted gf-check"><input type="checkbox" data-ceremony-autoskip="' + esc(cer.kind) + '" /> 同类自动略过</label>' +
      '<button type="button" class="btn primary block" data-ceremony-close="1">略过</button></div>';
    document.body.appendChild(ov);
  }
  function renderCeremonySkipOpsM() {
    var host = $("ceremonySkipOps"); if (!host) return;
    host.innerHTML = ["breakthrough", "death", "rebirth"].filter(function (k) { return ceremonySkippedM(k); }).map(function (k) { return '<button type="button" class="display-row" data-ceremony-unskip="' + k + '">' + esc(CEREMONY_CN_M[k] || k) + '仪式自动略过：取消<span class="arr">›</span></button>'; }).join("");
  }

  // 件四 · 关系可见化（§5.4）：命盘近 5 条 + 同场箭头，与 relations_recent/marks 同源
  function relationsSectionHtmlM(list) {
    if (!Array.isArray(list) || !list.length) return "";
    var html = '<div class="card"><h3>关系动态</h3>';
    list.slice(0, 5).forEach(function (r) { var d = typeof r.delta === "number" ? r.delta : 0; html += '<div class="kv"><span class="k">' + (d > 0 ? "↑" + d : d < 0 ? "↓" + Math.abs(d) : "·") + " " + esc(r.after_cn || "") + '</span><span class="v">' + esc(r.summary || "") + "</span></div>"; });
    return html + "</div>";
  }
  function relationMarkM(row) {
    var marks = (state.status && state.status.relations_marks) || null;
    var m = marks && row ? ((row.id != null && marks[row.id]) || (row.name && marks[row.name]) || null) : null;
    return m && typeof m.delta === "number" && m.delta !== 0 ? ' <span class="rel-mark">' + (m.delta > 0 ? "↑" + m.delta : "↓" + Math.abs(m.delta)) + "</span>" : "";
  }

  // ---- 命令通道 ----
  function demoResult(c) {
    var st = state.status || {};
    return {
      ok: true,
      text: "" + c + " —— 演化一局：灵气流转，道心微动（离线演示，不落存档）。",
      status: st,
    };
  }

  async function sendCmd(cmd) {
    var c = (cmd || "").trim();
    if (!c) return;
    if (state.busy) {
      toast("天道神念推演中，诸法暂滞，请稍候…", "bad");
      return;
    }
    busy(true);
    try {
      pushFeed("» " + c, "cmd");
      var data;
      if (state.demo) data = demoResult(c);
      else data = await api("/action", { token: state.token, command: c });
      if (data.status) applyStatus(data.status);
      if (data.entry) { state.entry = data.entry; state.entryPending = false; if (state.view === "feed") renderFeed(); }
      if (data.origin_card) { state.originCard = data.origin_card; if (data.origin_card.just_created) showOriginOverlayM(); }
      if (data.ceremony) maybeShowCeremonyM(data.ceremony);
      // 交谈旧账行（game-feel-phase2 §8.3）：交谈开启响应 old_account 在场才渲染，置于交谈文本之前
      if (data.old_account) pushFeed(oldAccountTextM(data.old_account), "ok");
      if (data.text) pushFeed(data.text, data.ok === false ? "bad" : undefined, data.omen_image || "");
      else if (data.ok === false && data.error)
        pushFeed("敕令失败：" + data.error, "bad");
      if (data.dead)
        pushFeed("此身已坐化。输入 /转世 可再入轮回，钱包随账户保留。", "bad");
      // 仅成功才清空输入框；服务端拒绝（ok:false）与网络异常都保留草稿（M-12）
      if (data.ok !== false) {
        var inp = $("cmdInput");
        if (inp) inp.value = "";
      }
      hideSug();
      return data;
    } catch (e) {
      pushFeed("敕令失败：" + e.message, "bad");
      toast(e.message, "bad");
      return { ok: false, error: e.message };
    } finally {
      busy(false);
    }
  }

  async function loadCommands() {
    if (state.demo) {
      state.commands = [
        { cmd: "/look", desc: "观照道身状态" },
        { cmd: "/闭关", desc: "洞府入定吐纳" },
        { cmd: "/出关", desc: "提前收功出关" },
        { cmd: "/突破", desc: "引动九天雷劫破境" },
        { cmd: "/探险", desc: "踏入十方大荒历练" },
        { cmd: "/挖宝", desc: "循藏宝图挖掘机缘" },
        { cmd: "/穿戴", desc: "佩戴法宝入体" },
        { cmd: "/卸下", desc: "卸下装备收入纳戒" },
        { cmd: "/坊市", desc: "查看诸天商会与寄售" },
        { cmd: "/领俸禄", desc: "领取宗门月俸" },
        { cmd: "/交谈", desc: "与同场修士传音" },
        { cmd: "/命途", desc: "查看此世命途主线与章节" },
        { cmd: "/回应", desc: "回应找上门的主动戏剧" },
        { cmd: "/帮助", desc: "查阅全部天道敕令" },
      ];
      return;
    }
    try {
      var j = await api("/commands");
      state.commands = j.commands || [];
    } catch (_) {}
  }

  function fuzzy(q) {
    var query = (q || "").trim().toLowerCase();
    if (!query || query[0] !== "/") return [];
    var all = state.commands || [];
    if (query === "/")
      return all.slice(0, 10).map(function (e) {
        return Object.assign({}, e);
      });
    var core = query.replace(/^\//, "");
    var out = [];
    all.forEach(function (e) {
      var cmd = String(e.cmd || "").toLowerCase();
      var desc = String(e.desc || "").toLowerCase();
      var s = 0;
      if (cmd === query) s = 100;
      else if (cmd.indexOf(query) === 0) s = 80;
      else if (core && cmd.indexOf(core) >= 0) s = 55;
      else if (core && desc.indexOf(core) >= 0) s = 40;
      if (s > 0) out.push(Object.assign({}, e, { score: s }));
    });
    out.sort(function (a, b) {
      return b.score - a.score;
    });
    return out.slice(0, 8);
  }
  function renderSug() {
    var el = $("suggest");
    var inp = $("cmdInput");
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
      .map(function (it, i) {
        return (
          '<div class="suggest-item' +
          (i === 0 ? " active" : "") +
          '" data-sug-i="' +
          i +
          '">' +
          '<span class="cmd">' +
          esc(it.cmd) +
          '</span><span class="desc">' +
          esc(it.desc || it.usage || "") +
          "</span></div>"
        );
      })
      .join("");
    el.classList.remove("hidden");
  }
  function applySug(i) {
    var it = state.sug[i];
    if (!it) return;
    var inp = $("cmdInput");
    inp.value = it.cmd + " ";
    hideSug();
    inp.focus();
  }
  function hideSug() {
    var el = $("suggest");
    if (el) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  }

  async function refreshAll() {
    if (state.demo) {
      renderCurrent();
      return;
    }
    if (!state.token) return;
    try {
      var look = await api("/action", { token: state.token, command: "/look" });
      if (look && look.status) applyStatus(look.status);
    } catch (_) {}
    try {
      var here = await api("/action", { token: state.token, command: "/here" });
      if (here && Array.isArray(here.here)) state.here = here.here;
    } catch (_) {}
    try {
      var world = await api("/world/director");
      if (world && world.ok !== false) state.world = world;
    } catch (_) {}
    await refreshEntryM();
    renderCurrent();
  }

  function showApp() {
    $("gate") && $("gate").classList.add("hidden");
    $("app") && $("app").classList.remove("hidden");
    setView("feed");
  }
  function showGate(msg) {
    $("app") && $("app").classList.add("hidden");
    $("gate") && $("gate").classList.remove("hidden");
    if (msg != null && $("gateMsg")) $("gateMsg").textContent = msg;
  }

  async function doAuth(e) {
    if (e && e.preventDefault) e.preventDefault();
    var username = $("fUser").value.trim();
    var password = $("fPass").value;
    var name = ($("fName").value || username).trim();
    $("gateMsg").textContent = "";
    if (!username || !password) {
      $("gateMsg").textContent = "请完整填写仙籍账号与神识密匙";
      return;
    }
    var btn = $("gateSubmit");
    var old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "灵脉感应中…";
    try {
      var payload =
        state.mode === "register"
          ? await api("/register", {
              username: username,
              password: password,
              name: name,
            })
          : await api("/login", {
              username: username,
              password: password,
              name: name,
            });
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
      localStorage.setItem("wb.base", state.base);
      state.demo = false;
      localStorage.removeItem("wb.demo");
      if (payload.entry !== undefined) state.entry = payload.entry;
      if (payload.entry_pending !== undefined) state.entryPending = !!payload.entry_pending;
      if (payload.origin_card) state.originCard = payload.origin_card;
      applyStatus({
        name: state.name,
        realm: payload.realm || "练气期",
        location: payload.location || "青云坊市客栈",
        rem_years: payload.rem_years || 85,
        stones: 100,
      });
      showApp();
      if (payload.origin_card && payload.origin_card.just_created) showOriginOverlayM();
      if (payload.ceremony) maybeShowCeremonyM(payload.ceremony);
      toast("已入世 · " + state.name, "ok");
      if (payload.dead) {
        pushFeed(
          "此身已坐化（" +
            (payload.death_cause || "身死道消") +
            "）。输入 /转世 可再入轮回，钱包随账户保留。",
          "bad",
        );
      }
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
    $("gateMsg").textContent = "正在感应宗门阵枢 " + state.base + " …";
    try {
      var r = await fetch(state.base + "/health");
      var j = await r.json();
      if (j && j.ok) {
        localStorage.setItem("wb.base", state.base);
        $("gateMsg").textContent = "宗门阵枢通达灵动：" + state.base;
      } else {
        $("gateMsg").textContent = "阵枢感应迟滞，请确认灵脉地址";
      }
    } catch (err) {
      $("gateMsg").textContent =
        "未能连通阵枢。可直接使用「玄黄镜演（离线演示）」体验。";
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
      stones: 520,
      vault: 1600,
      rem_years: 145,
      sin: 8,
      merit: 45,
      exp: "380/600",
      root: "金水双灵根",
      blood_marked: false,
      meditating: false,
      sect_contribution: 480,
      salary: 120,
      salary_claimable: true,
      salary_cd_sec: 0,
      can_promote: false,
      next_rank: "客卿长老",
      wallet: { balance: 300 },
      past_life: { lives: 0, last_name: "", last_cause: "", shadow_count: 0 },
      karma_chains: { active: 0 },
      pet: null,
      pets_count: 0,
      arts: { main: "吐纳术", sub: ["御剑术"] },
      skills: ["吐纳术", "御剑术"],
      gender: "male",
      portrait: "/assets/portraits/male-zhuji.webp",
      gallery: { unlocked: ["portraits/male-lianqi", "portraits/male-zhuji"], count: 2, total: 139, title: "", newly: [] },
      art_images: { "吐纳术": "/assets/arts/earth.webp", "御剑术": "/assets/arts/sword.webp" },
      spells_catalog: [],
      items: [],
      equipped: [],
      max_bag_slots: 64,
      status_cn: "安然无恙",
    };
    state.here = [
      {
        name: "柳三娘",
        realm: "筑基中期",
        sect: "四海散修盟",
        rank: "掌柜",
        is_npc: true,
        personality: "和气生财",
        attitude_cn: "友善",
        avatar: "/assets/portraits/npc-nvxiu.webp",
      },
      {
        name: "凌剑心",
        realm: "筑基圆满",
        sect: "万剑仙门",
        rank: "真传",
        is_npc: true,
        personality: "剑道痴迷",
        attitude_cn: "中立",
      },
    ];
    state.feed = [
      {
        kind: "ai",
        text: "西荒黑风绝渊赤焰喷涌，世界疤痕显现，隐有上古凶煞降世！",
        ts: Date.now() / 1000 - 120,
      },
      {
        kind: "ok",
        text: "你今日于客栈闭关参悟天工密卷，偶有所得，神识通达。",
        ts: Date.now() / 1000 - 30,
      },
    ];
    localStorage.setItem("wb.demo", "1");
    showApp();
    applyStatus(state.status);
    loadCommands();
    toast("已激活玄黄镜演模式", "ok");
  }

  async function tryRestore() {
    if (localStorage.getItem("wb.demo") === "1") {
      loadDemo();
      return;
    }
    if (state.user && $("fUser")) $("fUser").value = state.user;
    if (state.name && $("fName")) $("fName").value = state.name;
    if (!state.token) return;
    try {
      var look = await api("/action", { token: state.token, command: "/look" });
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

  function switchViewPage(target) {
    try {
      localStorage.setItem("wb.viewpref", target);
    } catch (e) {}
    location.replace(target === "mobile" ? "/mobile.html" : "/index.html");
  }

  function bind() {
    setTheme(state.theme);
    document.querySelectorAll("[data-mode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.mode = btn.getAttribute("data-mode");
        document.querySelectorAll("[data-mode]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        $("fNameWrap") &&
          $("fNameWrap").classList.toggle("hidden", state.mode !== "register");
        if ($("gateSubmit")) {
          $("gateSubmit").textContent =
            state.mode === "register" ? "铸造道号 · 踏入仙途" : "踏入大千世界";
        }
      });
    });
    $("gateForm") && $("gateForm").addEventListener("submit", doAuth);
    $("btnProbe") && $("btnProbe").addEventListener("click", probeServer);
    $("btnDemo") && $("btnDemo").addEventListener("click", loadDemo);

    $("cmdForm") &&
      $("cmdForm").addEventListener("submit", function (e) {
        e.preventDefault();
        sendCmd($("cmdInput").value);
      });
    var inp = $("cmdInput");
    if (inp) {
      inp.addEventListener("input", renderSug);
      inp.addEventListener("focus", function () {
        document.body.classList.add("kb-open");
      });
      inp.addEventListener("blur", function () {
        document.body.classList.remove("kb-open");
      });
      inp.addEventListener("keydown", function (e) {
        var sugBox = $("suggest");
        var open =
          sugBox && !sugBox.classList.contains("hidden") && state.sug.length;
        if (open && e.key === "ArrowDown") {
          e.preventDefault();
          state.sugI = Math.min(state.sug.length - 1, state.sugI + 1);
          updateSugActive();
        } else if (open && e.key === "ArrowUp") {
          e.preventDefault();
          state.sugI = Math.max(0, state.sugI - 1);
          updateSugActive();
        } else if (
          open &&
          e.key === "Enter" &&
          inp.value.startsWith("/") &&
          !inp.value.trim().includes(" ")
        ) {
          e.preventDefault();
          applySug(state.sugI);
        } else if (e.key === "Escape") hideSug();
      });
    }
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", function () {
        if (window.visualViewport.height < window.innerHeight * 0.8) {
          document.body.classList.add("kb-open");
        } else if (document.activeElement !== $("cmdInput")) {
          document.body.classList.remove("kb-open");
        }
      });
    }
    // mousedown 守住焦点：点发送/联想/快捷条时不让输入框失焦，避免
    // kb-open 切换造成命令坞上移、click 落空（M-12：发送按钮必须可点）。
    // 只拦 mousedown 默认行为（不拦 touchstart，click 仍正常触发）。
    ["cmdDock", "quickBar"].forEach(function (id) {
      var el = $(id);
      if (el) el.addEventListener("mousedown", function (e) { e.preventDefault(); });
    });
    $("suggest") &&
      $("suggest").addEventListener("click", function (e) {
        var t = e.target.closest("[data-sug-i]");
        if (t) applySug(Number(t.getAttribute("data-sug-i")));
      });
    $("btnLogoutM") &&
      $("btnLogoutM").addEventListener("click", async function () {
        try {
          if (!state.demo && state.token)
            await api("/logout", { token: state.token });
        } catch (_) {}
        state.token = "";
        localStorage.removeItem("wb.token");
        localStorage.removeItem("wb.demo");
        state.demo = false;
        showGate("已暂离归隐大千世界。");
      });

    // 全局委托：导航 / 命令 / 填入 / 迁跃 / 切换 / 行囊选中
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var nav = t.closest("[data-mview]");
      if (nav) {
        setView(nav.getAttribute("data-mview"));
        return;
      }
      var sw = t.closest("[data-view-switch]");
      if (sw) {
        switchViewPage(sw.getAttribute("data-view-switch"));
        return;
      }
      var auto = t.closest("[data-auto-view]");
      if (auto) {
        try {
          localStorage.removeItem("wb.viewpref");
        } catch (err) {}
        toast("已恢复跟随设备自动选择，下次打开按设备判定。", "ok");
        return;
      }
      var th = t.closest("[data-theme-toggle]");
      if (th) {
        setTheme(state.theme === "dark" ? "light" : "dark");
        return;
      }
      var cmd = t.closest("[data-cmd]");
      if (cmd) {
        sendCmd(cmd.getAttribute("data-cmd"));
        return;
      }
      var fill = t.closest("[data-fill]");
      if (fill) {
        var ci = $("cmdInput");
        if (ci) {
          ci.value = fill.getAttribute("data-fill");
          ci.focus();
          renderSug();
        }
        return;
      }
      var bag = t.closest("[data-bag]");
      if (bag) {
        var nm = bag.getAttribute("data-bag");
        state.selectedBagName = state.selectedBagName === nm ? "" : nm;
        renderBag();
        return;
      }
    });

    // 游戏感第一期新增委托（属性与既有委托不重叠）：命格选择/出身·仪式关闭/取消自动略过
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var fc = t.closest("[data-fate-choice]");
      if (fc) { closeOverlayM("ceremonyOverlay"); sendCmd("/命格 " + fc.getAttribute("data-fate-choice")); return; }
      if (t.closest("[data-origin-close]")) { closeOverlayM("originOverlay"); return; }
      if (t.closest("[data-ceremony-close]")) { closeOverlayM("ceremonyOverlay"); return; }
      var un = t.closest("[data-ceremony-unskip]");
      if (un) { try { localStorage.removeItem("ceremony_skip_" + un.getAttribute("data-ceremony-unskip")); } catch (_) {} renderCeremonySkipOpsM(); }
    });
    document.addEventListener("change", function (e) {
      var t = e.target;
      if (t && t.getAttribute && t.getAttribute("data-ceremony-autoskip")) {
        try { if (t.checked) localStorage.setItem("ceremony_skip_" + t.getAttribute("data-ceremony-autoskip"), "1"); else localStorage.removeItem("ceremony_skip_" + t.getAttribute("data-ceremony-autoskip")); } catch (_) {}
      }
    });

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && state.token && !state.demo) refreshAll();
    });
  }

  function updateSugActive() {
    document.querySelectorAll(".suggest-item").forEach(function (el, i) {
      el.classList.toggle("active", i === state.sugI);
    });
  }

  bind();
  tryRestore();
})();
