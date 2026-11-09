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
    ceremonyNext: null,
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

  // 命令面板 feed 内嵌卡（command-panels §3-D1/§11-D2）：html 为本文件通用渲染器产出
  // （内部值已 esc），与纯文本项共用一条 feed 流。
  function pushFeedHtml(html, kind) {
    if (!html) return;
    state.feed.push({ text: "", html: String(html), kind: kind || "ok", img: "", ts: Date.now() / 1000 });
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
          (f.html ? f.html
            : f.kind === "cmd"
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
  var CEREMONY_CN_M = { breakthrough: "突破", death: "归府", rebirth: "转世", tribulation: "天劫", loot: "得宝", spirit: "器灵认主" };
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
  // 双幕队列（game-feel-phase3 §7.2）：ceremony_next 暂存 state.ceremonyNext，先演天劫幕，
  // 关闭/自动略过后顺延突破幕；两幕 skip 按 kind 独立判定，双略过时都不呈现（命格仍可达）。
  function maybeShowCeremonyQueueM(cer, next) {
    state.ceremonyNext = next && next.kind ? next : null;
    if (cer && cer.kind && !ceremonySkippedM(cer.kind)) { maybeShowCeremonyM(cer); return; }
    var nxt = state.ceremonyNext; state.ceremonyNext = null;
    if (nxt) maybeShowCeremonyM(nxt);
  }
  function closeCeremonyM() {
    closeOverlayM("ceremonyOverlay");
    var nxt = state.ceremonyNext; state.ceremonyNext = null;
    if (nxt) maybeShowCeremonyM(nxt);
  }
  function renderCeremonySkipOpsM() {
    var host = $("ceremonySkipOps"); if (!host) return;
    host.innerHTML = ["breakthrough", "death", "rebirth", "tribulation", "loot", "spirit"].filter(function (k) { return ceremonySkippedM(k); }).map(function (k) { return '<button type="button" class="display-row" data-ceremony-unskip="' + k + '">' + esc(CEREMONY_CN_M[k] || k) + '仪式自动略过：取消<span class="arr">›</span></button>'; }).join("");
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

// ==========================================================================
// 命令回复面板化（command-panels spec §3/§4/§5；CP-00 通用面板渲染器·移动端）
// 与桌面 workbench.js 同构：同一命令同一结构/分区/顺序/字段，只差单列紧凑
// 布局。buildCommandPanel(cmd, data) -> 卡片 HTML 或 ""（回落纯文本）。
// 铁律：只读结构键，禁解析 data.text、禁本地捏造；缺失显"—"，零值显 0。
// == command-panels: begin ==
function cpHas(v) { return v!== null && v!== undefined && v!== "";}
function cpPk(o) { if (!o || typeof o!== "object") return undefined; for (var i = 1; i < arguments.length; i++) { var v = o[arguments[i]]; if (v!== null && v!== undefined && v!== "") return v;} return undefined;}
function cpS(v) { return v == null? "": String(v);}
function cpN(v, d) { if (v === null || v === undefined || v === "") return "—"; var n = Number(v); if (!isFinite(n)) return esc(String(v)); if (Math.floor(n) === n) return String(n); var m = Math.pow(10, d == null? 2: d); return String(Math.round(n * m) / m);}
function cpY(v) { return v == null? "—": Number(v).toFixed(1) + " 载";}
function cpP(v) { if (v == null || v === "") return "—"; var n = Number(v); return isFinite(n)? (Math.round(n * 10) / 10) + "%": "—";}
function cpG(v, u) { if (v == null || v === "") return "—"; var n = Number(v); if (!isFinite(n)) return "—"; if (n === 0) return "0" + (u || ""); return (n > 0? "+": "−") + Math.abs(n) + (u || "");}
function cpT(ts) { if (ts == null || ts === "") return "—"; var d = new Date(Number(ts) * 1000); if (isNaN(d.getTime())) return "—"; var p = function (x) { return (x < 10? "0": "") + x;}; return p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());}
function cpR(ts) { if (ts == null || ts === "") return "—"; var s = Math.max(0, Math.round(Number(ts) - Date.now() / 1000)); if (s >= 86400) return "约 " + Math.ceil(s / 86400) + " 天"; if (s >= 3600) return "约 " + Math.ceil(s / 3600) + " 小时"; if (s >= 60) return "约 " + Math.ceil(s / 60) + " 分"; return "约 " + s + " 秒";}
function cpD(dl) { if (dl == null || dl === "") return "—"; var d = Math.ceil((Number(dl) - Date.now() / 1000) / 86400); return d <= 0? "已到期": "剩 " + d + " 天";}
// 内部码 → 中文标签（M3 口径，小修轮）：映射表命中 → 中文标签；无映射的纯
// ASCII 码 → ""（省略，不渲染原码）；已是中文展示值 → 原样保留。
function cpLab(map, v) { if (v == null || v === "") return ""; var s = String(v); if (map && map[s] != null) return map[s]; return /[A-Za-z]/.test(s)? "": s; }
var CP_DIR_CN = { blood_tide: "血煞潮", sect_tension: "宗门紧张", secret_realm_pressure: "秘境压力", calamity_forecast: "大劫预兆", omen: "机缘预兆", faction_order: "宗门令", sect_siege: "宗门围剿" };
function cpCard(t, sub, b) { return '<div class="card cp-card"><h3>' + esc(t) + '</h3>' + (sub? '<p class="muted">' + esc(sub) + '</p>': "") + b + '</div>';}
function cpSec(t, b) { return b? '<div class="cp-sec">' + esc(t) + '</div>' + b: "";}
function cpKv(k, v, n) { return '<div class="kv"><span class="k">' + esc(k) + '</span><span class="v' + (n? ' cp-num': '') + '">' + v + '</span></div>';}
function cpKvs(rs) { var h = ""; rs.forEach(function (r) { if (r) h += cpKv(r[0], r[1], r[2]);}); return h;}
function cpRow(m, r, b) { return '<div class="cp-row"><div class="cp-row-m">' + m + '</div>' + (b? '<span class="cp-badge">' + esc(b) + '</span>': "") + (r!= null? '<span class="cp-num">' + r + '</span>': "") + '</div>';}
function cpRows(items, fn, cap) { if (!Array.isArray(items) ||!items.length) return ""; var list = items.filter(Boolean); if (!list.length) return ""; var n = cap || list.length, h = list.slice(0, n).map(fn).join(""); if (list.length > n) h += '<details class="cp-fold"><summary>其余 ' + (list.length - n) + ' 条</summary>' + list.slice(n).map(fn).join("") + '</details>'; return h;}
function cpFold(t, b, open) { return b? '<details class="cp-fold"' + (open? ' open': '') + '><summary>' + esc(t) + '</summary>' + b + '</details>': "";}
function cpChips(list) { var bs = (list || []).filter(Boolean).map(function (c) { return c.fill? '<button type="button" class="chip" data-fill="' + esc(c.fill) + '">' + esc(c.label) + '</button>': '<button type="button" class="chip" data-cmd="' + esc(c.cmd) + '">' + esc(c.label) + '</button>';}).join(""); return bs? '<div class="chiprow">' + bs + '</div>': "";}
function cpBar(p) { p = Math.max(0, Math.min(100, Number(p) || 0)); return '<div class="bar-row"><div class="bar"><i style="width:' + p + '%"></i></div></div>';}
function cpNarr(t) { return t? '<p class="cp-note">' + esc(t) + '</p>': "";}
function cpNote(t) { return t? '<p class="muted">' + esc(t) + '</p>': "";}
function cpMain(t, sub) { return '<div>' + esc(t) + (sub? '<br><span class="muted">' + esc(sub) + '</span>': '') + '</div>';}
function cpGoalRow(g) { var src = { origin: "出身", fate_thread: "命途", fate: "命途", thread: "命途", dao: "道途", newbie: "新入", season: "纪元", sect: "宗门", chance: "机缘", omen: "机缘", avenge: "复仇", bounty: "悬赏", fame: "扬名", survive: "避劫", legacy: "道统" }[g.source] || ""; return cpRow(cpMain((src? "【" + src + "】": "") + cpS(g.title), cpS(g.detail)), "进度 " + cpN(g.progress), g.status === "done"? "已成": "");}
var CP_BOARD_CN_M = { realm: "境界榜", power: "战力榜", notoriety: "凶名榜", daohang: "道行榜", fame: "传奇榜", assets: "资产榜"};
function cpBoardRowsM(rows) { return (rows || []).filter(Boolean).map(function (r, i) { return cpRow(cpMain((r.rank!= null? r.rank: i + 1) + ". " + cpS(r.name), [r.realm, r.sect].filter(Boolean).join(" · ")), "分 " + cpN(r.score), r.is_npc? "NPC": "");}).join("");}
// ---- P0 ----
function cpProfile(data) { var p = data.profile; if (!p || typeof p!== "object") return ""; var head = cpKvs([["境界", esc(cpS(p.realm)), false], ["宗门", esc(cpS(p.sect) + (p.rank && p.rank!== p.sect? " · " + p.rank: "")), false], ["位置", esc(cpS(p.location) + (p.location_region? "（" + p.location_region + "）": "")), false], ["灵根", esc(cpS(p.root)), false]]); var nums = cpKvs([["寿元", cpY(p.rem_years), true], ["修为", esc(cpS(p.exp)), true], ["灵石", cpN(p.stones) + " 灵石", true], ["金库", cpN(p.vault) + " 灵石", true], ["功德", cpN(p.merit), true], ["业力", cpN(p.sin), true], ["道心", cpN(p.dao_heart), true]]); var sk = (Array.isArray(p.skills) && p.skills.length)? cpSec("法门", '<p class="cp-note">' + esc(p.skills.join("、")) + '</p>'): ""; var bio = p.bio? cpSec("小传", cpNarr(p.bio)): ""; var rec = (Array.isArray(p.recent) && p.recent.length)? cpSec("近日账录", p.recent.slice(0, 6).map(function (r) { return cpNote("· " + r);}).join("")): ""; return cpCard("个人信息 · " + cpS(p.name), cpS(p.realm), head + cpSec("道身数值", nums) + sk + bio + rec);}
function cpLook(data) { var s = data.status; if (!s || typeof s!== "object") return ""; var nums = cpKvs([["境界", esc(cpS(s.realm)), false], ["寿元", cpY(s.rem_years), true], ["修为", esc(cpS(s.exp)), true], ["灵石", cpN(s.stones) + " 灵石", true], ["金库", cpN(s.vault) + " 灵石", true], ["功德", cpN(s.merit), true], ["业力", cpN(s.sin), true], ["道心", cpN(s.dao_heart), true], ["灵根", esc(cpS(s.root)), false], ["位置", esc(cpS(s.location)), false], ["灵气", s.qi_mult == null? "—": "×" + cpN(s.qi_mult), true]]); var prot = s.newbie_protected? cpSec("新手庇护", cpKvs([["剩余", "约 " + cpN(s.newbie_left_hours) + " 小时", true]])): ""; return cpCard("观照 · " + cpS(s.name), cpS(s.realm), nums + prot + cpChips([{ label: "查看同场 ›", cmd: "/here"}]));}
// ---- P1 ----
function cpHere(data) { var list = data.here; if (!Array.isArray(list) ||!list.length) return ""; var rows = list.map(function (p) { var chips = '<div class="chiprow"><button type="button" class="chip" data-cmd="/交谈 ' + esc(p.name) + '">交谈</button><button type="button" class="chip" data-cmd="/斗法 ' + esc(p.name) + '">斗法</button></div>'; return cpRow(cpMain(p.name + " · " + cpS(p.realm), (p.sect || "") + (p.rank? " · " + p.rank: "") + (p.personality? " · " + p.personality: "") + (p.agenda? " · 议程：" + p.agenda + (p.agenda_progress!= null? "（进度 " + p.agenda_progress + "/5）": ""): "")) + chips, null, p.blood_marked? "血煞": (p.attitude_cn || cpLab({ hostile: "仇视", wary: "戒备", neutral: "中立", friendly: "友善", ally: "亲近" }, p.attitude)));}).join(""); var loc = data.status && data.status.location? data.status.location: ""; return cpCard("同场 · " + (loc || "此地"), "共 " + (data.count!= null? data.count: list.length) + " 人", rows);}
function cpNearby(data) { var e = data.entry, goals = data.goals, secs = []; if (e && typeof e === "object") { var lines = e.lines || {}, fate = cpS(lines.fate), chains = lines.chains && lines.chains.text? lines.chains.text: ""; if (fate || chains) secs.push(cpSec("世间", (fate? cpNote(fate): "") + (chains? cpNote(chains): ""))); var rels = Array.isArray(lines.relations)? lines.relations: []; if (rels.length) secs.push(cpSec("与你何干", rels.map(function (r) { return cpNote("· " + (r.summary || ""));}).join(""))); var queue = Array.isArray(e.queue)? e.queue: []; if (queue.length) secs.push(cpSec("找上门的事", queue.map(function (q) { var opts = Array.isArray(q.options)? q.options: []; var chips = opts.length && q.target && q.target.command? cpChips(opts.map(function (o) { return { label: o.label || o.key, cmd: q.target.command + " " + (o.key || "")};})): ""; return cpRow(cpMain(cpS(q.title), cpS(q.text)), null, "") + chips;}).join("")));} if (Array.isArray(goals) && goals.length) secs.push(cpSec("世间目标", goals.map(cpGoalRow).join(""))); if (!secs.length) return ""; return cpCard("近况", "", secs.join(""));}
function cpGoals(data) { var list = data.goals; if (!Array.isArray(list) ||!list.length) return ""; return cpCard("世间目标", list.length + " 条", list.map(function (g) { return cpRow(cpMain(cpS(g.title), cpS(g.detail) + (g.deadline_at!= null? " · " + cpD(g.deadline_at): "")), "进度 " + cpN(g.progress), g.status === "done"? "已成": ({ origin: "出身", fate_thread: "命途", fate: "命途", thread: "命途", dao: "道途", newbie: "新入", season: "纪元", sect: "宗门", chance: "机缘", omen: "机缘", avenge: "复仇", bounty: "悬赏", fame: "扬名", survive: "避劫", legacy: "道统"}[g.source] || ""));}).join(""));}
function cpTasks(data) { var defs = data.defs || {}, tasks = data.tasks || {}, secs = [], act = Array.isArray(tasks.active)? tasks.active: []; if (act.length) secs.push(cpSec("进行中", act.map(function (t) { var d = defs[t.task_id] || {}; return cpRow(cpMain(cpS(d.title || t.task_id), cpS(d.summary)), "已完成 " + (Array.isArray(t.done_steps)? t.done_steps.length: 0) + " 步", "");}).join(""))); var done = Array.isArray(tasks.done)? tasks.done: []; if (done.length) secs.push(cpSec("已完成", done.map(function (t) { var d = defs[t.task_id] || {}; return cpRow(cpMain(cpS(d.title || t.task_id), cpS(d.summary)), null, "已成");}).join(""))); if (!secs.length) return ""; return cpCard("任务 · 指引与赏格", "", secs.join(""));}
function cpRank(data) { if (Array.isArray(data.board_rows) && data.board_rows.length) return cpCard("榜单", data.board_rows.length + " 名", cpBoardRowsM(data.board_rows)); var boards = data.boards; if (boards &&!Array.isArray(boards) && typeof boards === "object") boards = Object.keys(boards).map(function (k) { return { name: k, title: boards[k].title, rows: boards[k].rows};}); if (!Array.isArray(boards) ||!boards.length) return ""; return cpCard("天道榜单", boards.length + " 榜", boards.map(function (b, i) { return cpFold((b.title || CP_BOARD_CN_M[b.name] || b.name || "榜单") + "（" + ((b.rows || []).length) + " 名）", cpBoardRowsM(b.rows), i === 0);}).join(""));}
function cpSecret(data) { var list = data.realms; if (!Array.isArray(list) ||!list.length) return ""; return cpCard("秘境天机", list.length + " 处", list.map(function (r) { var dg = cpPk(r, "危险%", "danger_pct", "danger"); return cpRow(cpMain(cpS(r.name), [r.location, r.desc || r.description].filter(Boolean).join(" · ")), "危险 " + cpP(dg!= null && Number(dg) <= 1? Number(dg) * 100: dg), (r.is_open != null ? (r.is_open ? "已开启" : "未开启") : (r.is_open != null ? (r.is_open ? "已开启" : "未开启") : (r.is_open != null ? (r.is_open ? "已开启" : "未开启") : cpS(cpPk(r, "状态", "status", "state") || "")))) + (cpPk(r, "门槛", "threshold", "req_tier", "min_tier")!= null? " · 门槛 " + cpPk(r, "门槛", "threshold", "req_tier", "min_tier"): ""));}).join(""));}
function cpWorld(data) { var ev = data.evolution; if (!ev || typeof ev!== "object") return ""; var secs = [], d = ev.director || {}; if (d && typeof d === "object" && (Array.isArray(d.active) || d.stats)) { var dst = d.stats || {}; var kv = cpKvs([["上次运行", cpT(d.last_run_ts), false], ["累计", "提案 " + cpN(dst.runs) + " · 落账 " + cpN(dst.accepted) + " · 驳回 " + cpN(dst.rejected), false]]); var act = (Array.isArray(d.active)? d.active: []).map(function (a) { return cpRow(cpMain(cpS(a.title), cpS(a.narrative) + (a.expires_at!= null? " · 剩余 " + cpR(a.expires_at): "")), null, cpS(a.type_cn || cpLab(CP_DIR_CN, a.type)));}).join(""); secs.push(cpFold("一 · 天道导演", kv + act, true));} if (Array.isArray(ev.arcs) && ev.arcs.length) { var sc = { prophesy: "预兆", escalation: "升级", resolution: "决算"}; secs.push(cpFold("二 · 世界弧", ev.arcs.map(function (a) { return cpRow(cpMain(cpS(a.title), "下阶段 " + cpR(a.stage_deadline)), null, a.stage_cn || cpLab(sc, a.stage));}).join(""), false));} var f = ev.faction || {}; if (f && typeof f === "object" && (Array.isArray(f.relations) || f.modifiers)) { var rels = (Array.isArray(f.relations)? f.relations: []).map(function (r) { return cpRow(cpMain(cpS(r.a) + " × " + cpS(r.b), cpS(r.note || "")), "分 " + cpG(r.score), r.status_cn || cpLab({ hostile: "敌对", tense: "紧张", neutral: "中立", warm: "亲近", allied: "结盟" }, r.status));}).join(""); var m = f.modifiers || {}; var extra = [(m.hostile_pairs || []).map(function (p) { return "敌对：" + p.join("×");}).join("；"), (m.tense_pairs || []).map(function (p) { return "紧张：" + p.join("×");}).join("；"), m.n_open_missions!= null? "开放宗门令：" + m.n_open_missions + " 条": ""].filter(Boolean).join(" · "); secs.push(cpFold("三 · 势力格局", rels + (extra? cpNote(extra): ""), false));} var echo = ev.echo || {}, blood = ev.blood; if ((echo && echo.modifiers) || (Array.isArray(blood) && blood.length)) { var em = (echo && echo.modifiers) || {}; var kv2 = cpKvs([["血气", cpN(em.blood_index), true], ["恐慌", cpN(em.fear_index), true], ["除凶热度", "×" + cpN(em.hunt_heat), true]]); var brows = (Array.isArray(blood)? blood: []).slice(0, 8).map(function (b) { return cpRow(cpMain(cpS(b.name), [b.realm, b.location].filter(Boolean).join(" · ")), "业力 " + cpN(b.sin), "血煞");}).join(""); secs.push(cpFold("四 · 望气·血煞", kv2 + brows, false));} var era = ev.era || {}; if (era && typeof era === "object" && (era.bias_cn || era.bias)) { var bias = era.bias_cn || era.bias || {}, keys = Object.keys(bias).map(function (k) { return [cpLab(CP_DIR_CN, k), bias[k]]; }).filter(function (p) { return p[0]; }); secs.push(cpFold("五 · 纪元回流", keys.length? keys.map(function (p) { return cpKv(p[0], esc(cpS(p[1])), true);}).join(""): cpNote("活跃权重：暂无（传说未积）"), false));} if (Array.isArray(ev.realms_open) && ev.realms_open.length) secs.push(cpFold("六 · 秘境开启", ev.realms_open.map(function (r) { return cpRow(cpMain(cpS(r.name), cpS(r.location) + (r.desc? " · " + r.desc: "")), "危险 " + cpP(r.danger!= null && Number(r.danger) <= 1? Number(r.danger) * 100: r.danger), r.is_open? "已开启": "");}).join(""), false)); if (Array.isArray(ev.npc_brief) && ev.npc_brief.length) secs.push(cpFold("七 · NPC 动向", ev.npc_brief.slice(0, 12).map(function (n) { return cpRow(cpMain(cpS(n.name), cpS(n.location || "")), null, cpS(n.agenda || ""));}).join(""), false)); if (!secs.length) return ""; return cpCard("世情 · 世界演变总览", (ev.summary_lines || []).join("；"), secs.join(""));}
function cpClue(data) { var cl = data.clue; if (!cl || typeof cl!== "object") return ""; var step = cl.current_step || {}; var stepText = (typeof step === "number" || typeof step === "string")? ("第 " + step + (cl.total_steps!= null? "/" + cl.total_steps: "") + " 步"): cpS(step.title || step.text || step); var kv = cpKvs([["线索链", esc(cpS(cpPk(cl, "chain", "map_name"))), false], ["当前步", esc(stepText), false]]); var cur = cl.current || {}; var curNote = (cur.kind_cn || cur.node_name)? cpNote(cpS((cur.kind_cn? cur.kind_cn + " · ": "") + (cur.node_name || ""))): ""; var opts = Array.isArray(cl.options)? cl.options: (Array.isArray(cur.options)? cur.options: []); var chips = opts.length? cpChips(opts.map(function (o) { return { label: o.label || o.key, cmd: "/寻宝 " + (o.key || o.label || "")};})): ""; var abandon = cl.can_abandon? cpChips([{ label: "放弃寻宝", cmd: "/寻宝 弃"}]): ""; return cpCard("寻宝 · 线索链", "", kv + (cur.riddle? cpNarr(cur.riddle): (step.text && step.title? cpNarr(step.text): "")) + curNote + chips + abandon);}
function cpSpirit(data) { var sp = data.spirit; if (!sp || typeof sp!== "object") return ""; var items = Array.isArray(sp.items)? sp.items: []; var item = items[0] || sp.item || {}; var state = cpPk(sp, "状态", "state", "status") || (item.spirit!= null? "已唤灵": ((items.length || sp.item)? "未唤灵": "")); var kv = cpKvs([["法宝", esc(cpS(item.name || sp.item_name || sp.name)), false], ["品阶", esc(cpS(item.tier_name || item.tier || sp.tier)), false], ["成长", cpN(cpPk(sp, "成长", "growth")), true], ["状态", esc(cpS(state)), false]]); var list = Array.isArray(sp.awakenable || sp["可唤灵列表"])? (sp.awakenable || sp["可唤灵列表"]): []; var rows = list.map(function (it) { return cpRow(cpMain(cpS(it.name || it)), null, "");}).join(""); var nm = cpS(item.name || sp.item_name || sp.name); var chips = nm? cpChips([{ label: "唤灵", cmd: "/器灵 唤 " + nm}, { label: "温养", cmd: "/温养 " + nm}]): ""; return cpCard("器灵", "", kv + (rows? cpSec("可唤灵", rows): "") + chips);}
function cpArts(data) { var secs = [], arts = data.arts; if (Array.isArray(arts) && arts.length) secs.push(cpSec("自创功法", arts.map(function (a) { var cm = a.cultivation_modifiers || {}; var spells = (Array.isArray(a.spells)? a.spells: []).map(function (s) { return s.name;}).join("、"); return cpRow(cpMain(cpS(a.name), [a.rank_cn, a.nature_cn, spells? "神通：" + spells: ""].filter(Boolean).join(" · ")), cm.exp_gain_multiplier!= null? "修炼 ×" + cpN(cm.exp_gain_multiplier): null, "");}).join(""))); var st = data.status || {}, skills = Array.isArray(st.skills)? st.skills: []; if (skills.length) secs.push(cpSec("已习得", '<p class="cp-note">' + esc(skills.join("、")) + '</p>')); if (!secs.length) return ""; return cpCard("功法", "", secs.join(""));}
function cpGallery(data) { var g = data.status && data.status.gallery; if (!g || typeof g!== "object") return ""; var kv = cpKvs([["进度", cpN(g.count) + "/" + cpN(g.total), true], ["称号", esc(cpS(g.title) || "尚未得图鉴称号"), false], ["未点亮", cpN((g.total!= null && g.count!= null)? g.total - g.count: null), true]]); return cpCard("天道图鉴", "", kv + '<div class="chiprow"><button type="button" class="chip primary" data-mview="ops">查看完整图鉴 ›</button></div>');}
function cpMarket(data) { var s = data.status; if (!s || typeof s!== "object") return ""; var listings = Array.isArray(s.market_listings)? s.market_listings: []; var kv = cpKvs([["金库", cpN(s.vault) + " 灵石", true], ["随身", cpN(s.stones) + " 灵石", true], ["在售", cpN(listings.length), true]]); return cpCard("坊市", "", kv + '<div class="chiprow"><button type="button" class="chip primary" data-mview="ops">查看完整坊市 ›</button></div>');}
function cpAuction(data) { var lots = data.auction && data.auction.lots; if (!Array.isArray(lots) ||!lots.length) return ""; var rows = lots.map(function (l) { var remRaw = cpPk(l, "剩余", "remain", "remain_sec"); var remStr = remRaw != null ? cpS(remRaw) : (l.remaining_s != null ? cpR(Date.now() / 1000 + Number(l.remaining_s)) : "—"); return cpRow(cpMain("#" + cpS(l.id) + " " + cpS(l.name), "起拍 " + cpN(cpPk(l, "起拍", "start_price", "start")) + " · 领先 " + cpS(cpPk(l, "领先", "leader") || "暂无") + " · 余 " + remStr + " · 挂单人 " + cpS(cpPk(l, "挂单人", "seller"))), "当前 " + cpN(cpPk(l, "当前价", "price", "current_price")) + " 灵石", ""); }).join(""); var chips = '<div class="flex flex-wrap gap-2 mt-2"><button type="button" class="btn sm secondary" data-act="focus-cmd:/上拍 ">上拍</button></div>'; return cpCard("拍卖行", lots.length + " 件在拍", rows + chips); }
function cpHunt(data) { var list = data.hunt; if (!Array.isArray(list) ||!list.length) return ""; var rows = list.map(function (h) { var mk = cpPk(h, "血煞", "blood", "mark"); var tag = mk === true? "血煞": (typeof mk === "string"? mk: ""); return cpRow(cpMain(cpS(h.name) + " · " + cpS(h.realm), "地点 " + cpS(cpPk(h, "地点", "location")) + " · 被 " + cpN(cpPk(h, "被盯人数", "watchers", "hunted_by", "hunters")) + " 人盯上"), "业力 " + cpN(cpPk(h, "业力", "sin")), tag); }).join(""); var chips = cpChips(list.slice(0, 4).map(function (h) { return { label: "接令·" + h.name, cmd: "/接除凶 " + h.name}; })); return cpCard("除凶榜", list.length + " 人在榜", rows + chips); }
function cpSect(data) { var list = data.sects; if (!Array.isArray(list) ||!list.length) return ""; var rows = list.map(function (x) { var top = x["高层"] || x.top || x.elders || []; var topStr = Array.isArray(top)? top.map(function (t) { return typeof t === "string"? t: (t.name + (t.rank? "·" + t.rank: "")); }).join("、"): ""; var tip = cpS(cpPk(x, "rules_tip") || ""); return cpRow(cpMain(cpS(x.name) + (x.alias? "（" + x.alias + "）": ""), "总坛 " + cpS(cpPk(x, "总坛", "hq", "headquarters")) + (topStr? " · 高层：" + topStr: "") + (tip? " · 门规：" + tip: "")), "月俸 " + cpN(cpPk(x, "月俸", "salary", "monthly_salary")) + " · " + cpN(cpPk(x, "人数", "members", "count")) + " 人", cpS(cpPk(x, "门槛", "req", "requirement") || x.alignment || "")); }).join(""); var mine = data.status && data.status.sect? cpSec("自身宗籍", cpKvs([["宗门", esc(cpS(data.status.sect)), false], ["职衔", esc(cpS(data.status.rank)), false]])): ""; return cpCard("天下仙门", list.length + " 宗", rows + mine); }
function cpFateThread(data) { var th = data.fate_thread; if (!th || typeof th!== "object") return ""; return fateThreadHtmlM({ thread: th});}
function cpMap(data) { var m = data.treasure_map; if (!m || typeof m!== "object") return ""; var tierCn = ["凡品", "人品", "地品", "天品", "仙品"][Number(m.tier) - 1] || cpS(m.tier); var kv = cpKvs([["宝图", esc(cpS(m.name)), false], ["品阶", esc(tierCn), false], ["卦位", esc(cpS(m.bagua)), false], ["坐标", esc(cpS(m.coords)), false], ["目标地点", esc(cpS(cpPk(m, "target_node", "targetNodeName"))), false], ["类型", esc(cpS(m.archetype)), false]]); return cpCard("宝图研读", "", kv + cpNarr(m.riddle) + (m.clue? cpNote("线索：" + m.clue): ""));}
  // ---- P2 ----
  function cpHelp(data) { var list = data.commands; if (!Array.isArray(list) || !list.length) return ""; var groups = {}, order = []; list.forEach(function (c) { var g = c.category_cn || c.category || "其他"; if (!groups[g]) { groups[g] = []; order.push(g); } groups[g].push(c); }); return cpCard("敕令目录", list.length + " 条", order.map(function (g, i) { return cpFold(g + "（" + groups[g].length + " 条）", groups[g].map(function (c) { return cpRow(cpMain(cpS(c.usage || c.cmd), cpS(c.desc)), null, ""); }).join(""), i === 0); }).join("")); }
  function cpWho(data) { var groups = data.who && data.who.groups; if (!Array.isArray(groups) || !groups.length) return ""; return cpCard("天下名录", groups.length + " 处", groups.map(function (g, i) { return cpFold(cpS(g.place) + "（" + ((g.members || []).length) + " 人）", (g.members || []).map(function (m) { return cpRow(cpMain(cpS(m.name), ""), esc(cpS(m.realm)), ""); }).join(""), i === 0); }).join("")); }
  function cpAgenda(data) { var list = data.agendas; if (!Array.isArray(list) || !list.length) return ""; return cpCard("NPC 议程", list.length + " 条", list.map(function (a) { return cpRow(cpMain(cpS(a.name) + " · " + cpS(a.type), cpS(a.note || "") + (a.secondary ? " · " + a.secondary : "")), "进度 " + cpN(a.progress) + "/5", ""); }).join("")); }
  function cpBounty(data) { var list = data.bounties; if (!Array.isArray(list) || !list.length) return ""; var rows = list.map(function (b) { return cpRow(cpMain(cpS(b.target), cpS(cpPk(b, "缘由", "reason")) + (cpPk(b, "匿", "anon", "anonymous") ? " · 匿名" : "")), "赏金 " + cpN(cpPk(b, "赏金", "bounty", "reward")) + " 灵石", (b.status_cn ? cpS(b.status_cn) + " #" : "#") + cpS(b.id)); }).join(""); var chips = cpChips(list.slice(0, 4).map(function (b) { return { label: "接令 #" + b.id, cmd: "/接令 " + b.id }; })); return cpCard("悬赏告示", list.length + " 条", rows + chips); }
  function cpHeaven(data) { var d = data.director; if (!d || typeof d !== "object") return ""; var dst = d.stats || d["累计"] || {}; var kv = cpKvs([["上次运行", cpT(cpPk(d, "last_run", "last_run_ts")), false], ["累计", typeof dst === "string" ? esc(dst) : ("提案 " + cpN(dst.runs) + " · 尝试 " + cpN(dst.attempts) + " · 落账 " + cpN(dst.accepted) + " · 驳回 " + cpN(dst.rejected)), false]]); var act = Array.isArray(cpPk(d, "活跃指令", "active")) ? cpPk(d, "活跃指令", "active") : []; var rows = act.map(function (a) { return cpRow(cpMain(cpS(a.title), cpS(a.narrative) + (a.expires_at != null ? " · 剩余 " + cpR(a.expires_at) : (a.expires_in_s != null ? " · 剩余 " + cpR(Date.now() / 1000 + Number(a.expires_in_s)) : ""))), null, cpS(a.type_cn || cpLab(CP_DIR_CN, a.type))); }).join(""); return cpCard("天道导演", "", kv + rows); }
  function cpArcs(data) { var a = data.arcs; if (!a || typeof a !== "object") return ""; var list = Array.isArray(a) ? a : (a["弧"] || a.arcs || a.list || []); var ast = (!Array.isArray(a) && (a["累计"] || a.stats)) || null; var kv = ast ? cpKvs([["累计", typeof ast === "string" ? esc(ast) : ("起弧 " + cpN(cpPk(ast, "started", "spawned")) + " · 升级 " + cpN(cpPk(ast, "upgraded", "advanced")) + " · 决算 " + cpN(cpPk(ast, "resolved", "climaxed"))), false]]) : ""; var stageCn = { prophesy: "预兆", escalation: "升级", resolution: "决算" }; var rows = (Array.isArray(list) ? list : []).map(function (x) { return cpRow(cpMain(cpS(x.title), "下阶段 " + (x.stage_deadline != null ? cpR(x.stage_deadline) : (x.deadline_in_s != null ? cpR(Date.now() / 1000 + Number(x.deadline_in_s)) : "—"))), null, x.stage_cn || cpLab(stageCn, x.stage)); }).join(""); var hist = (!Array.isArray(a) && (a["近史"] || a.history)) || []; var histHtml = Array.isArray(hist) && hist.length? cpSec("近史", hist.slice(0, 6).map(function (h) { var t = typeof h === "string" ? h : (h.text || h.title || ""); if (typeof h === "string" && h.indexOf("|") >= 0) { var parts = h.split("|"); t = parts[3] || h; } return cpNote("· " + t); }).join("")): ""; var mods = (!Array.isArray(a) && (a["弧修饰"] || a.modifiers)) || null; var modsHtml = ""; if (mods) { if (typeof mods === "string") modsHtml = cpSec("弧修饰", cpNote(mods)); else { var parts = []; if (mods.n_arcs != null) parts.push("在弧 " + mods.n_arcs + " 场"); var heat = mods.heat_by_location || {}; Object.keys(heat).forEach(function (k) { parts.push(k + " ×" + heat[k]); }); (mods.sect_tensions || []).forEach(function (p) { parts.push("宗门紧张 " + (Array.isArray(p) ? p.join("×") : p)); }); if (parts.length) modsHtml = cpSec("弧修饰", cpNote(parts.join(" · "))); } } if (!kv && !rows && !histHtml && !modsHtml) return ""; return cpCard("世界弧", "", kv + rows + histHtml + modsHtml); }
  function cpCreateArt(data) { var a = data.art; if (!a || typeof a !== "object") return ""; var cm = a.cultivation_modifiers || {}; var kv = cpKvs([["功法", esc(cpS(a.name)), false], ["品阶", esc(cpS(a.rank_cn || a.rank)), false], ["正邪", esc(cpS(a.nature_cn || a.nature)), false], ["修炼加速", cm.exp_gain_multiplier != null ? "×" + cpN(cm.exp_gain_multiplier) : "—", true], ["燃寿代价", cm.lifespan_burn_per_year != null ? cpN(cm.lifespan_burn_per_year) + " /年" : "—", true], ["劫威加成", cm.tribulation_power_add != null ? cpG(cm.tribulation_power_add) : "—", true]]); var spells = (Array.isArray(a.spells) ? a.spells : []).map(function (s) { return cpRow(cpMain(cpS(s.name), cpLab({ DAMAGE: "战斗伤害", BUFF: "辅助", HEAL: "回复", CONTROL: "制敌" }, s.effect_type)), s.multiplier != null ? "×" + cpN(s.multiplier) : null, ""); }).join(""); return cpCard("自创功法", "", kv + (spells ? cpSec("神通", spells) : "") + cpNarr(a.lore) + (a.effects_text ? cpNarr(a.effects_text) : "")); }
  function cpFate(data) { var f = data.fate; if (!f || typeof f !== "object") return ""; var secs = [], boons = Array.isArray(f.boons) ? f.boons : []; if (boons.length) secs.push(cpSec("已定命格", boons.map(function (b) { return cpRow(cpMain(cpS(b.name), "第 " + cpN(b.from_tier) + " 阶抽定 · " + cpT(b.chosen_at)), null, cpS(b.source_cn || "")); }).join(""))); var pending = Array.isArray(f.pending) ? f.pending : []; if (pending.length && pending[0] && Array.isArray(pending[0].candidates)) { var cands = pending[0].candidates; secs.push(cpSec("待选命格（择一）", cands.map(function (c) { return cpRow(cpMain((c.icon ? c.icon + " " : "") + cpS(c.name), cpS(c.desc || "")), null, ""); }).join("") + cpChips(cands.map(function (c) { return { label: "择 " + (c.name || c.key), cmd: "/命格 " + c.key }; })))); } if (!secs.length) return ""; if (f.power_bonus != null) secs.push(cpSec("命格加成", cpKvs([["战力加成", "×" + cpN(f.power_bonus), true]]))); return cpCard("命格", "", secs.join("")); }
  function cpRespond(data) { var list = data.drama_pending || data.drama; if (!Array.isArray(list) || !list.length) return ""; return cpCard("待回应之事", list.length + " 件", list.map(function (d) { var opts = Array.isArray(d.options) ? d.options : []; return cpRow(cpMain(cpS(d.npc_name || d.title || d.id), cpS(d.text)), null, "") + cpChips(opts.map(function (o) { return { label: o.label || o.key, cmd: "/回应 " + d.id + " " + (o.key || "") }; })); }).join("")); }
  function cpLinks(data) { var list = data.links; if (!Array.isArray(list) || !list.length) return ""; var kc = { gratitude: "恩", grudge: "仇", promise: "诺", blood_feud: "血仇", favor: "恩", debt: "债" }; return cpCard("因果牵缠", list.length + " 条", list.map(function (l) { return cpRow(cpMain(cpS(cpPk(l, "名", "name", "npc_name")), cpS(cpPk(l, "缘由", "reason", "note"))), "强度 " + cpN(cpPk(l, "强度", "strength", "value")), kc[l.kind] || l.kind || ""); }).join("")); }
  function cpFaction(data) { var f = data.factions; if (!f || typeof f !== "object") return ""; var secs = []; if (Array.isArray(f.relations) && f.relations.length) secs.push(cpSec("宗门关系", f.relations.map(function (r) { return cpRow(cpMain(cpS(r.a) + " × " + cpS(r.b), cpS(r.note || r.source || "")), "分 " + cpG(r.score), r.status_cn || cpLab({ hostile: "敌对", tense: "紧张", neutral: "中立", warm: "亲近", allied: "结盟" }, r.status)); }).join(""))); if (Array.isArray(f.orders) && f.orders.length) secs.push(cpSec("宗门令", f.orders.map(function (o) { return cpRow(cpMain("[" + cpS(o.sect || "") + "] " + cpS(o.content || o.title || ""), "id " + cpS(o.id || "")), "贡献 +" + cpN(cpPk(o, "贡献", "contribution", "reward_contrib")), ""); }).join(""))); if (Array.isArray(f.sieges) && f.sieges.length) secs.push(cpSec("围剿", f.sieges.map(function (s) { return cpRow(cpMain(cpS(s.title || s.target || ""), cpS(s.text || "")), null, ""); }).join(""))); if (f["累计"] != null) secs.push(cpSec("累计", cpNote(cpS(f["累计"])))); if (!secs.length) return ""; return cpCard("天下势力", "", secs.join("")); }
  function cpSectOrder(data) { var list = data.sect_orders; if (!Array.isArray(list) || !list.length) return ""; var rows = list.map(function (o) { return cpRow(cpMain("[" + cpS(o.sect) + "] " + cpS(cpPk(o, "内容", "content", "title")), "id " + cpS(o.id)), "贡献 +" + cpN(cpPk(o, "贡献", "contribution", "reward_contrib")), ""); }).join(""); var chips = cpChips(list.slice(0, 4).map(function (o) { return { label: "接令 " + o.id, cmd: "/接宗门令 " + o.id }; })); return cpCard("宗门令", list.length + " 条", rows + chips); }
  function cpSectPower(data) { var sp = data.sect_power; if (!sp || typeof sp !== "object") return ""; var list = Array.isArray(sp) ? sp : (sp.sects || sp.rows || sp.list || sp["宗门"] || []); if (!Array.isArray(list) || !list.length) return ""; var max = 1; list.forEach(function (r) { max = Math.max(max, Number(cpPk(r, "分", "score")) || 0); }); var rows = list.map(function (r) { var sc = Number(cpPk(r, "分", "score")) || 0; return cpRow(cpMain(cpS(cpPk(r, "宗门", "sect", "name")), cpN(cpPk(r, "人数", "members", "count")) + " 人"), "分 " + cpN(sc), "") + cpBar(sc / max * 100); }).join(""); var rel = []; var pair = function (arr, label) { if (Array.isArray(arr)) rel.push(label + "：" + arr.map(function (p) { return Array.isArray(p) ? p.join("×") : p; }).join("；")); }; pair(sp.hostile_pairs, "敌对"); pair(sp.hostile, "敌对"); pair(sp.tense_pairs, "紧张"); pair(sp.tense, "紧张"); if (Array.isArray(sp["敌对"])) rel.push("敌对：" + sp["敌对"].join("；")); if (Array.isArray(sp["紧张"])) rel.push("紧张：" + sp["紧张"].join("；")); return cpCard("宗门实力", list.length + " 宗" + (sp.open_missions != null ? " · 在令 " + sp.open_missions : ""), rows + (rel.length ? cpNote(rel.join(" · ")) : "")); }
  function cpContribution(data, cmd) { if (/\s+\S/.test((cmd || "").trim()) && /^\/?兑换/.test((cmd || "").trim())) return ""; var c = data.contribution; if (!c || typeof c !== "object") return ""; var head = cpKvs([["宗门", esc(cpS(c.sect)), false], ["贡献", cpN(c.points), true]]); var cat = Array.isArray(c.catalog) ? c.catalog : []; return cpCard("宗门贡献 · 兑换目录", "", head + (cat.length ? cpSec("兑换目录", cat.map(function (it) { return cpRow(cpMain(cpS(it.name), ""), cpN(cpPk(it, "cost", "贡献")) + " 贡献", cpPk(it, "需连环", "need_streak") != null ? "需连环≥" + cpPk(it, "需连环", "need_streak") : ""); }).join("")) : "")); }
  function cpScan(data) { var list = data.scan; if (!Array.isArray(list) || !list.length) return ""; var cc = { VAGUE: "灵压未明", CLEAR: "已辨明", HIDDEN: "隐匿", REALM: "境界可辨", FULL: "尽数洞悉" }; return cpCard("神识探查", list.length + " 条发现", cpRows(list, function (s) { return cpRow(cpMain(cpS(s.description || s.text || "")), null, s.clarity_cn || cpLab(cc, s.clarity)); }, 12)); }
  function cpNpcGoods(data) { var list = data.npc_goods; if (!Array.isArray(list) || !list.length) return ""; return cpCard("NPC 货单", list.length + " 件", list.map(function (g) { return cpRow(cpMain(cpS(g.name), cpS(cpPk(g, "描述", "desc", "description"))), cpN(cpPk(g, "price", "价")) + " 灵石", ""); }).join("")); }
  // ---- P3 ----
  function cpChannel(data) { var list = data.channel; if (!Array.isArray(list) || !list.length) return ""; return cpCard("世界频道", list.length + " 条", list.map(function (n) { var sevMap = { minor: 1, major: 2, epic: 3 }; var sev = typeof n.severity === "number" ? n.severity : (sevMap[n.severity] || 1); var stars = "★".repeat(Math.max(1, Math.min(3, sev))); var lbl = n.type_cn || cpLab(null, n.type); return cpRow(cpMain(cpS(n.text), ""), null, lbl? stars + " " + lbl: stars); }).join("")); }
  function cpLegend(data) { var l = data.legends; if (!l || typeof l!== "object") return ""; var rows0 = l.legends || l["近史"] || l.history || []; var rows = (Array.isArray(rows0)? rows0: []).map(function (h) { if (typeof h === "string") return cpRow(cpMain(cpS(h)), null, ""); return cpRow(cpMain(cpS(h.title || h.text || ""), cpS(h.title && h.text? h.text: "")), null, (h.season!= null? "第" + h.season + "纪": ""));}).join(""); var bias = cpPk(l, "活跃权重", "weights", "active_bias_cn", "active_bias"); var biasStr = bias == null? "暂无": (typeof bias === "object"? (Object.keys(bias).map(function (k) { var lb = cpLab(CP_DIR_CN, k); return lb? lb + " " + bias[k]: ""; }).filter(Boolean).join("；") || "暂无"): cpS(bias)); var kvRows = [["活跃权重", esc(biasStr), false]]; var cit = cpPk(l, "引用累计", "citations", "cited_count"); if (cit!= null) kvRows.push(["引用累计", cpN(cit), true]); if (l.total!= null) kvRows.push(["收录", cpN(l.total) + " 则", true]); var kv = cpKvs(kvRows); if (!kv &&!rows) return ""; return cpCard("传说 · 史笔", "", kv + rows);}
  function cpEra(data) { var e = data.era_flow; if (!e || typeof e!== "object") return ""; var lastFlow = cpPk(e, "上次回流", "last_flow", "last_flow_ts", "last_reentry_ts"); var bias = cpPk(e, "活跃权重", "weights", "active_bias_cn", "active_bias"); var biasStr = bias == null? "暂无": (typeof bias === "object"? (Object.keys(bias).map(function (k) { var lb = cpLab(CP_DIR_CN, k); return lb? lb + " " + bias[k]: ""; }).filter(Boolean).join("；") || "暂无"): cpS(bias)); var kvRows = [["上次回流", typeof lastFlow === "number"? cpT(lastFlow): esc(cpS(lastFlow) || "—"), false], ["活跃权重", esc(biasStr), false]]; if (e.current_season!= null) kvRows.push(["当前纪元", "第 " + cpN(e.current_season) + " 纪", false]); var cit = cpPk(e, "引用累计", "citations", "cited_count"); if (cit!= null) kvRows.push(["引用累计", cpN(cit), true]); var kv = cpKvs(kvRows); var legends = e["近传说"] || e.legends || e.recent_legends || []; var rows = (Array.isArray(legends)? legends: []).map(function (h) { return cpRow(cpMain(cpS(typeof h === "string"? h: (h.title || h.text || ""))), null, "");}).join(""); return cpCard("纪元回流", "", kv + rows);}
  function cpTrade(data) { var t = data.trade; if (!t || typeof t !== "object") return ""; var statusCn = { OPEN: "进行中", CLOSED: "已关闭", DONE: "已成交", CANCELLED: "已取消" }; var kvRows = [["对方", esc(cpS(t.partner)), false], ["状态", esc(cpS(cpLab(statusCn, t.status))), false]]; if (t.location) kvRows.push(["地点", esc(cpS(t.location)), false]); var kv = cpKvs(kvRows); var offers = "", sides = t.offers || t["报价双方"] || t.quotes; if (!sides && (t.a || t.b)) sides = { a: t.a, b: t.b }; if (sides && typeof sides === "object") { offers = Object.keys(sides).map(function (k) { var o = sides[k] || {}; var stones = o.stones != null ? o.stones : o["灵石"]; var items = Array.isArray(o.items) ? o.items.join("、") : cpS(o.items || o["物品"] || ""); var label = o.name ? o.name : (k === "me" ? "我方报价" : k === "partner" ? "对方报价" : k); var agreed = o.agreed === true ? " · 已同意" : (o.agreed === false ? " · 未同意" : ""); return cpKv(label, esc("灵石 " + cpN(stones) + (items ? " · " + items : "") + agreed), true); }).join(""); } return cpCard("当面交易", "", kv + offers + cpChips([{ label: "同意成交", cmd: "/交易同意" }, { label: "拒绝", cmd: "/交易拒绝" }])); }
  function cpSectQuests(data) { var q = data.sect_quests; if (q == null) return ""; if (!Array.isArray(q) && typeof q === "object") { var task = q.task || {}; var kv = cpKvs([["师父", esc(cpS(q.master || "")), false]]); var rows = cpRow(cpMain(cpS(task.label || task.title || ""), ""), null, q.done ? "已完成" : "进行中"); var chips = q.done ? "" : cpChips([{ label: "交师门", cmd: "/交师门" }]); return cpCard("师门任务", "1 项", kv + rows + chips); } var list = Array.isArray(q) ? q : (q.list || q.quests || q.daily || []); if (!Array.isArray(list) || !list.length) return ""; var rows2 = list.map(function (x) { return cpRow(cpMain(cpS(x.title || x.name || ""), cpS(x.desc || x.text || "")), null, x.done ? "已完成" : ""); }).join(""); return cpCard("师门任务", list.length + " 项", rows2); }
  function cpMingwu(data) { var list = data.relics; if (!Array.isArray(list) || !list.length) return ""; var rows = list.map(function (r) { return cpRow(cpMain(cpS(r.name), cpS(cpPk(r, "线索", "clue", "desc", "description"))), null, cpS(cpPk(r, "type", "status") || "")); }).join(""); return cpCard("名物 · 听闻册", list.length + " 件", rows); }
  function cpSectRing(data) { var ring = data.status && data.status.sect_ring; if (!ring || typeof ring !== "object" || !Array.isArray(ring.themes) || !ring.themes.length) return ""; return cpCard("宗门环 · " + cpS(ring.day), ring.done ? "今日已完成" : "", ring.themes.map(function (t, i) { return cpRow(cpMain(cpS(t.label), cpS(t.lore || "") + (t.need_item ? " · 需 " + t.need_item : "") + (t.need_streak ? " · 需连环≥" + t.need_streak : "")), null, ring.accepted ? "已接取" : "") + (ring.done ? "" : cpChips([{ label: "接取此环", cmd: "/接宗门环 " + (t.id != null ? t.id : i + 1) }])); }).join("")); }
  function cpApocalypse(data) { var s = data.season; if (!s || typeof s !== "object") return ""; var kv = cpKvs([["纪元", "第 " + cpN(s.season_number) + " 纪", true], ["进度", "第 " + cpN(s.day_in_season) + " 天/共 " + cpN(s.total_days) + " 天", true], ["剩余", "约 " + cpN(s.remain_real_days) + " 天", true], ["终局", s.is_ended ? "已终局" : (s.is_final_week ? "终局之周" : "灵机尚稳"), false]]); return cpCard("大劫 · 纪元终局", "", kv + cpNote("大劫降临后输入 /大劫 结算，未飞升者应劫转世并结转道统。")); }
  function cpAi(data) { var a = data.ai_data, dq = data.director_quality; if ((!a || typeof a !== "object") && !dq) return ""; var kv = a ? cpKvs([["模式", esc(cpLab({ CCSWITCH: "CC Switch 本机代理", OPENAI: "OpenAI 兼容直连" }, a.mode)), false], ["地址", esc(cpS(a.base)), false], ["模型", esc(cpS(a.model)), false], ["状态", a.ok ? "就绪" : esc(cpS(a.error || "未就绪")), false]]) : ""; var checks = ""; if (dq && Array.isArray(dq.checks)) checks = cpSec("天道导演链路（" + cpN(dq.passed) + "/" + cpN(dq.total) + " 通过）", dq.checks.map(function (c) { return cpRow(cpMain(cpS(c.name), cpS(c.detail || "")), null, c.ok ? "✓" : "✗"); }).join("")); return cpCard("AI 自检", "", kv + checks); }
  function cpAilog(data) { var list = data.items; if (!Array.isArray(list) || !list.length) return ""; return cpCard("AI 调用日志", list.length + " 条", cpRows(list, function (it) { return cpRow(cpMain(cpS(it.channel || it.kind || ""), (it.prompt || "").slice(0, 40) + ((it.prompt || "").length > 40 ? "…" : "")), (it.duration_ms != null ? it.duration_ms + "ms" : "") + " · HTTP " + cpS(it.http_status), it.status || ""); }, 10)); }
// ---- 附录 ----
function cpPet(data) { var list = data.pets; if (!Array.isArray(list) ||!list.length) { var one = data.status && data.status.pet; list = (one && typeof one === "object")? [one]: [];} if (!list.length) return ""; var rows = list.map(function (p) { var deployed = cpPk(p, "出战", "deployed") || p.state === "出战中" || p.active === true; var chips = !deployed? cpChips([{ label: "出战", cmd: "/出战 " + (p.name || "")}]): ""; return cpRow(cpMain(cpS(p.name) + " · " + cpS(cpPk(p, "种", "species", "kind")), "境界 " + (p.level != null ? p.level + " 级" : cpS(cpPk(p, "境界", "realm"))) + " · 成长 " + cpN(cpPk(p, "成长", "growth"))), null, (deployed? "出战中": "") || cpS(cpPk(p, "状态", "state", "status")) || "") + chips;}).join(""); var total = data.status && data.status.pets_count; return cpCard("灵宠", total!= null? "共 " + total + "/3 只": list.length + " 只", rows);}
function cpCave(data) { var c = data.status && data.status.cave; if (!c || typeof c!== "object") return ""; return cpCard("洞府灵田", "", cpKvs([["等级", cpN(c.level) + " 级", true], ["灵田", cpN(c.plots_used) + "/" + cpN(c.plots_total) + " 块", true], ["成熟", cpN(c.mature) + " 块", true]]) + cpNote("洞府等级越高田越多，闭关也越快（最高 +5%）。"));}
function cpMindArt(data) { var s = data.status; if (!s || typeof s!== "object" ||!s.arts) return ""; var arts = s.arts || {}; return cpCard("心法槽位", "", cpKvs([["主修", esc(cpS(arts.main) || "（空）"), false], ["辅修", esc((Array.isArray(arts.sub)? arts.sub: []).join("、") || "（空）"), false], ["已习得", esc((Array.isArray(s.skills)? s.skills: []).join("、") || "—"), false]]) + cpNote("主修一门定乾坤，辅修二门助斗法。"));}
function cpWallet(data) { var w = data.wallet; if (!w || typeof w!== "object") return ""; var head = cpKvs([["户名", esc(cpS(w.username) || "—"), false], ["余额", cpN(w.balance) + " 灵石", true]]); var entries = Array.isArray(w.entries)? w.entries: []; var wKindCn = { death_sweep: "死亡归集", auction_refund: "拍卖退款", auction_sale: "拍卖成交", consignment_sale: "寄售成交", wallet_withdraw: "钱包提取" }; var rows = entries.length? cpSec("流水", cpRows(entries, function (e) { var wTitle = [cpLab(wKindCn, cpPk(e, "种类", "kind", "type")), cpS(cpPk(e, "备注", "note"))].filter(Boolean).join(" · ") || "流水"; return cpRow(cpMain(wTitle), cpG(cpPk(e, "金额", "amount"), " 灵石"), cpT(cpPk(e, "ts", "time")));}, 10)): ""; return cpCard("账户钱包", "", head + rows + '<div class="chiprow"><button type="button" class="chip" data-fill="/钱包提取 ">钱包提取</button></div>');}
function cpPrices(data) { var p = data.prices; if (!p || typeof p!== "object" ||!Array.isArray(p.regions) ||!p.regions.length) return ""; return cpCard("天下行情", p.as_of? "官价 · " + cpS(p.as_of): "", p.regions.map(function (r, i) { return cpFold(cpS(r.name) + "（" + ((r.rows || []).length) + " 项）", (r.rows || []).map(function (row) { var origin = cpPk(row, "产地系数", "origin", "origin_mult"); return cpRow(cpMain(cpS(row.name), ""), "买 " + cpN(cpPk(row, "买入", "buy", "price")) + " / 回 " + cpN(cpPk(row, "回收", "sell", "sell_price")), origin == null? "": ("产地 " + (typeof origin === "number"? cpG(origin, "%"): origin)));}).join(""), i === 0);}).join(""));}
function cpAtlas(data) { var list = data.atlas; if (!Array.isArray(list) ||!list.length) return ""; return cpCard("天下版图", list.length + " 区域", list.map(function (r) { return cpRow(cpMain(cpS(cpPk(r, "region", "区域")), "主导 " + cpS(cpPk(r, "主导", "leader", "dominant"))), "本宗声威 " + cpS(cpPk(r, "本宗声威", "prestige", "mine")), "");}).join("") + '<div class="chiprow"><button type="button" class="chip" data-fill="/版图 ">查区域明细</button></div>');}
function cpTombstone(data) { var t = data.tombstone; if (!t || typeof t!== "object") return ""; return cpCard("墓碑", "", cpKvs([["道号", esc(cpS(t.name)), false], ["境界", esc(cpS(t.realm)), false], ["死因", esc(cpS(cpPk(t, "cause", "死因"))), false], ["道统点", cpN(cpPk(t, "points", "道统点")), true]]) + cpNarr(cpPk(t, "评语", "epitaph")));}
function cpChains(data) { var list = data.karma_chains; if (!Array.isArray(list) ||!list.length) return ""; var kindCn = { boon: "恩", grudge: "仇", promise: "诺", blood_feud: "血仇", favor: "恩", en: "恩", chou: "仇", nuo: "诺", xue: "血仇" }; var rows = list.map(function (c) { var prog = cpPk(c, "发酵进度", "progress", "ferment_pct"); var right = null; var bar = ""; if (typeof prog === "number") { if (prog >= 0 && prog <= 1) { right = cpP(prog * 100); bar = cpBar(prog * 100); } else if (prog > 1 && prog <= 100) { right = prog + "%"; bar = cpBar(prog); } else right = "进度 " + cpN(prog); } var hist = c["近史"] || c.history; var sub = Array.isArray(hist)? hist.slice(0, 2).join("；"): cpS(hist || ""); if (c.direction) sub += (sub ? " · " : "") + cpS(c.direction); if (cpPk(c, "上限", "cap")!= null) sub += (sub ? " · " : "") + "上限 " + cpPk(c, "上限", "cap"); if (c.elapsed_days != null && c.total_days != null) sub += (sub ? " · " : "") + "发酵 " + c.elapsed_days + "/" + c.total_days + " 天"; var name = cpPk(c, "对方", "target", "npc_name", "counterparty"); return cpRow(cpMain(cpS(name), sub), right, cpS(c.kind_cn || cpLab(kindCn, c.kind))) + bar; }).join(""); return cpCard("因果链", list.length + " 条", rows); }
function cpQuests(data) { var q = data.quests; var qKindCn = { deliver: "送信", fetch: "寻物", slay: "除妖" }; if (q == null) return ""; if (!Array.isArray(q) && typeof q === "object") { var secs = []; var chips = ""; if (q.active && typeof q.active === "object") { var a = q.active; var ring = a.ring || {}; var head = cpKvs([["发布者", esc(cpS(a.publisher || "")), false], ["进度", "第 " + cpN((a.ring_index || 0) + 1) + "/" + cpN(a.rings_total) + " 环", false], ["全链赏", "灵石 " + cpN(a.reward_stones) + " + 功德 " + cpN(a.reward_merit), true], ["剩余", a.expires_in_s!= null? cpR(Date.now() / 1000 + Number(a.expires_in_s)): "—", false]]); var cur = cpRow(cpMain("当前环【" + cpS(ring.kind_cn || cpLab(qKindCn, ring.kind)) + "】" + cpS(ring.desc || ""), (ring.progress!= null && ring.need!= null? "进度 " + ring.progress + "/" + ring.need + " · ": "") + (ring.deliver_npc_name? "交付：" + ring.deliver_npc_name: "")), null, ""); secs.push(cpSec("进行中", head + cur)); chips = cpChips([{ label: "交付", cmd: "/交付"}, { label: "弃委托", cmd: "/弃委托"}]);} var offers = Array.isArray(q.offers)? q.offers: []; if (offers.length) { var rows = offers.map(function (o) { var fr = o.first_ring || {}; var frStr = fr.desc? ("【" + cpS(fr.kind_cn || cpLab(qKindCn, fr.kind)) + "】" + fr.desc): ""; return cpRow(cpMain("【" + cpS(o.npc) + "】（" + cpS(o.realm) + "）委托 " + cpN(o.rings) + " 环", "赏 灵石 " + cpN(o.reward_stones) + " + 功德 " + cpN(o.reward_merit) + (frStr? " · 首环 " + frStr: "")), null, "") + cpChips([{ label: "接取委托", cmd: "/接委托 " + (o.npc || "")}]);}).join(""); secs.push(cpSec("可接委托", rows));} if (!secs.length) return ""; return cpCard("NPC 委托", offers.length? offers.length + " 件可接": "", secs.join("") + chips);} var list = data.quests; if (!Array.isArray(list) ||!list.length) return ""; return cpCard("NPC 委托", list.length + " 件", list.map(function (q) { var reward = q["赏"] || q.reward; var rewardStr = typeof reward === "string"? reward: reward && typeof reward === "object"? ("灵石 " + cpN(reward.stones) + " + 功德 " + cpN(reward.merit)): ""; var first = q["首环"] || q.first; var firstStr = typeof first === "string"? first: first && typeof first === "object"? ("【" + (first.kind_cn || cpLab(qKindCn, first.kind || first.type)) + "】" + (first.text || first.target || "")): ""; var chips = cpChips([{ label: "接取委托", cmd: "/接委托 " + (q.npc || "")}]); return cpRow(cpMain("【" + cpS(q.npc) + "】（" + cpS(q.realm) + "）委托 " + cpN(cpPk(q, "环数", "rings")) + " 环", (rewardStr? "赏 " + rewardStr + " · ": "") + (firstStr? "首环 " + firstStr: "")), null, "") + chips;}).join(""));}
function cpPromises(data) { var list = data.promises; if (!Array.isArray(list) ||!list.length) return ""; var kindCn = { gift: "赠物", debt: "旧债", arrive: "抵达", quest: "委托", no_attack: "不攻" }; var statusCn = { ACTIVE: "进行中", PENDING: "待应诺", DONE: "已结", SETTLED: "已结", EXPIRED: "已过期", KEPT: "已践诺", BROKEN: "已违约", DISSOLVED: "已消散" }; var groups = []; var seen = {}; list.forEach(function (p) { var b = p.bucket || "诺言"; if (!seen[b]) { seen[b] = []; groups.push([b, seen[b]]); } seen[b].push(p); }); var secs = groups.map(function (g) { var b = g[0], rows0 = g[1]; return cpSec(b, rows0.map(function (p) { var k = cpPk(p, "类型", "type", "kind"); var kCn = k == null ? "" : cpLab(kindCn, k); var st = cpPk(p, "状态", "status"); var stCn = st == null ? "" : cpLab(statusCn, st); return cpRow(cpMain(cpS(cpPk(p, "对象", "target", "promisee")) + " · " + cpS(kCn), cpS(cpPk(p, "内容", "content", "desc"))), cpPk(p, "期限", "deadline")!= null? cpD(cpPk(p, "期限", "deadline")): null, cpS(stCn)); }).join("")); }); return cpCard("诺言账", list.length + " 条未结之诺", secs.join("")); }
function cpRecipeRow(r) { var matsRaw = r["材料"] || r.materials; var mats = ""; if (Array.isArray(matsRaw)) mats = matsRaw.join("、"); else if (matsRaw && typeof matsRaw === "object") mats = Object.keys(matsRaw).map(function (k) { return k + "×" + matsRaw[k]; }).join("、"); else mats = cpS(matsRaw || ""); var rate = cpPk(r, "成率", "rate", "base_rate"); var rateStr = rate == null? "—": (typeof rate === "number" && rate <= 1? cpP(rate * 100): cpP(rate)); var fee = r.stones_fee != null ? (r.stones_fee + "灵") : cpS(cpPk(r, "炉火", "fire")); var kindCn = { pill: "丹药", equip: "法宝" }; var tierBad = (cpPk(r, "境界足", "enough") === false || r.tier_ok === false)? "境界不足": (cpS(cpLab(kindCn, cpPk(r, "kind", "种类")))); return cpRow(cpMain(cpS(r.name) + " · " + cpS(cpPk(r, "产物", "product", "output")), (mats? "材料：" + mats + " · ": "") + "炉火 " + fee), "成率 " + rateStr, tierBad); }
function cpRecipes(data) { var list = data.recipes; if (!Array.isArray(list) ||!list.length) return ""; return cpCard("配方", list.length + " 方", list.map(cpRecipeRow).join(""));}
function cpBodySoul(data) { var d = data.body_soul_detail; if (!d || typeof d!== "object") return ""; var track = function (label, t) { if (!t || typeof t!== "object") return ""; var cost = cpPk(t, "下一层成本", "next_cost"); var costStr = ""; if (typeof cost === "string") costStr = cost; else if (cost && typeof cost === "object") { var parts = []; if (cost.item) parts.push(cost.item + "×" + (cost.item_count || 1)); if (cost.stones != null) parts.push("灵石 " + cost.stones); costStr = parts.join(" + ") || "—"; } return cpSec(label, cpKvs([["层数", cpN(cpPk(t, "level", "层")) + " / 10 层", true], ["成效", esc(cpS(cpPk(t, "成效", "effect"))), false], ["下一层成本", esc(costStr || "—"), false]])); }; return cpCard("炼体 · 炼神", "", track("炼体", d.body) + track("炼神", d.soul)); }
function cpDemon(data) { var d = data.demon; if (!d || typeof d!== "object") return ""; var src = cpPk(d, "来源", "source") || ((d.sin != null || d.blood_marked != null || d.eff_dao_heart != null)? ("业力 " + cpN(d.sin) + "、" + (d.blood_marked ? "血煞缠身" : "血煞已散") + (d.eff_dao_heart != null ? "；有效道心 " + cpN(d.eff_dao_heart) + (d.suppress_mult != null ? "（压制系数 ×" + cpN(d.suppress_mult) + "）" : "") : "")): ""); var kv = cpKvs([["阶段", esc(cpS(cpPk(d, "stage_name", "阶段"))), false], ["魔念", (d.seed != null ? cpN(d.seed) : cpN(cpPk(d, "魔念", "thought"))) + (d.seed_cap != null ? " / 临发 " + cpN(d.seed_cap) : ""), true], ["来源", esc(cpS(src)), false]]); var opts = d["镇压选项"] || d.options || []; var rows = (Array.isArray(opts)? opts: []).map(function (o) { if (typeof o === "string") return cpRow(cpMain(o, ""), null, ""); if (o.kind === "pill") return cpRow(cpMain("服丹 · " + cpS(o.item || "") + (o.count != null ? "×" + o.count : ""), "灵石 " + cpN(o.stones) + (o.seed_delta != null ? " → 魔念 −" + cpN(o.seed_delta) : "")), null, ""); if (o.kind === "calm") return cpRow(cpMain("静坐", "有效道心 ≥" + cpN(o.min_dao) + (o.cooldown_h != null ? " · 冷却 " + cpN(o.cooldown_h) + " 小时" : "") + (o.seed_delta != null ? " → 魔念 −" + cpN(o.seed_delta) : "")), null, ""); return cpRow(cpMain(cpS(o.label || o.name || ""), cpS(o.desc || "")), null, ""); }).join(""); var autoChips = []; if (opts.some(function (o) { return o && o.kind === "pill"; })) autoChips.push({ label: "服丹", cmd: "/镇魔 服丹" }); if (opts.some(function (o) { return o && o.kind === "calm"; })) autoChips.push({ label: "静坐", cmd: "/镇魔 静坐" }); var chips = autoChips.length ? cpChips(autoChips) : cpChips((Array.isArray(opts)? opts: []).filter(function (o) { return o && typeof o === "object" && o.cmd; }).map(function (o) { return { label: o.label || o.name, cmd: o.cmd}; })); return cpCard("镇魔 · 心魔长卷", "", kv + (rows? cpSec("镇压", rows): "") + chips); }
function cpAscend(data) { var list = data.ascend; if (!Array.isArray(list) ||!list.length) return ""; var rows = list.map(function (a) { return cpRow(cpMain(cpS(a.name) + " · " + cpS(a.realm), cpS(cpPk(a, "cause", "死因"))), null, a.score != null ? "分 " + cpN(a.score) : (cpS(cpPk(a, "纪元", "era")) || "")); }).join(""); return cpCard("飞升榜 · 历世纪念碑", list.length + " 位", rows); }
function cpLegacy(data) { var l = (data.legacy_info && typeof data.legacy_info === "object")? data.legacy_info: data; if (!l || typeof l!== "object" || (l.points == null && l.lives == null &&!Array.isArray(l.boosts))) return ""; var head = cpKvs([["道统点", cpN(l.points), true], ["前世", cpN(l.lives) + " 世", true], ["已得", cpN(l.earned), true], ["单世上限", cpN(l.max_boosts) + " 项", true]]); var boosts = Array.isArray(l.boosts)? l.boosts: []; var bHtml = boosts.length? cpSec("出身兑换（单世至多 " + cpN(l.max_boosts) + " 项）", boosts.map(function (b) { return cpRow(cpMain(cpS(b.name), cpS(b.desc)), cpN(b.cost) + " 点", "");}).join("")): ""; var lives = Array.isArray(l.past_lives)? l.past_lives: []; var lHtml = lives.length? cpSec("前世", lives.map(function (r) { return cpRow(cpMain(cpS(r.name || r.title || ""), cpS(r.realm || r.cause || r.text || "")), null, "");}).join("")): ""; var shadow = Array.isArray(l.karma_shadow)? l.karma_shadow: []; var sHtml = shadow.length? cpSec("前世因果影子", shadow.map(function (s) { return cpRow(cpMain(cpS(s.name || s.npc_name || ""), cpS(s.reason || "")), cpG(s.value!= null? s.value: s.attitude), "");}).join("")): ""; var traces = Array.isArray(l.traces)? l.traces: []; var tHtml = traces.length? cpSec("命盘刻痕", traces.map(function (t) { return cpNote("· " + cpS(typeof t === "string"? t: (t.text || t.summary || t.name || "")));}).join("")): ""; return cpCard("道统", l.alive === false? "此身已坐化": "", head + bHtml + lHtml + sHtml + tHtml);}
function cpRecipe(data) { var r = data.recipe; if (!r || typeof r!== "object") return ""; return cpCard("新方 · " + cpS(r.name), cpS(cpPk(r, "kind", "种类") || ""), cpRecipeRow(r));}
function cpCouncil(data) { var c = data.council; if (c == null) return ""; if (!Array.isArray(c) && typeof c === "object" && (c.topic || c.seats)) { var topic = c.topic || {}; var kvRows = []; if (c.sect) kvRows.push(["宗门", esc(cpS(c.sect)), false]); if (c.session_no!= null) kvRows.push(["场次", "第 " + cpN(c.session_no) + " 场", false]); if (c.vault!= null) kvRows.push(["金库", cpN(c.vault) + " 灵石", true]); if (c.prestige!= null) kvRows.push(["声望", cpN(c.prestige), true]); if (c.morale!= null) kvRows.push(["士气", cpN(c.morale), true]); var kv = kvRows.length? cpKvs(kvRows): ""; var topicHtml = topic.name? cpSec("本场议题", cpRow(cpMain(cpS(topic.name), cpS(topic.desc || "")), null, "") + (c.closes_in_s!= null? cpNote("投票截止 " + cpR(Date.now() / 1000 + Number(c.closes_in_s))): "")): ""; var seats = Array.isArray(c.seats)? c.seats: []; var seatRows = seats.map(function (s) { return cpRow(cpMain(cpS(s.name) + (s.rank? "（" + s.rank + "）": ""), cpS(s.line || "")), null, cpS(s.stance_cn || cpLab({ support: "支持", oppose: "反对", neutral: "中立" }, s.stance)));}).join(""); var votes = c.votes || {}; var voteKv = cpKvs([["支持", cpN(votes.support), true], ["反对", cpN(votes.oppose), true], ["你", votes.mine == null? "未投": esc(cpS(votes.mine)), false]]); var chips = cpChips([{ label: "投票 支持", cmd: "/投票 支持"}, { label: "投票 反对", cmd: "/投票 反对"}]); return cpCard("宗门议政", "", kv + topicHtml + (seatRows? cpSec("长老席位", seatRows): "") + cpSec("弟子投票", voteKv) + chips);} var list = Array.isArray(c)? c: (c.proposals || c.motions || c.topics || c.items || []); if (!Array.isArray(list) ||!list.length) return ""; return cpCard("宗门议政", list.length + " 项", list.map(function (x) { return cpRow(cpMain(cpS(x.title || x.topic || x.name || ""), cpS(x.text || x.desc || "")), null, cpS(x.status || ""));}).join(""));}
function cpSwornQuests(data) { var q = data.sworn_quests; if (q == null) return ""; if (!Array.isArray(q) && typeof q === "object") { var task = q.task || {}; var kv = cpKvs([["结义", esc(cpS(q.partner || "")), false]]); var rows = cpRow(cpMain(cpS(task.label || task.title || ""), ""), null, q.done ? "已完成" : "进行中"); var chips = q.done ? "" : cpChips([{ label: "交结义", cmd: "/交结义" }]); return cpCard("结义任务", "1 项", kv + rows + chips); } var list = Array.isArray(q)? q: (q.list || q.quests || []); if (!Array.isArray(list) ||!list.length) return ""; var rows2 = list.map(function (x) { return cpRow(cpMain(cpS(x.title || x.name || ""), cpS(x.desc || x.text || "")), null, x.done? "已完成": ""); }).join(""); return cpCard("结义任务", list.length + " 项", rows2); }
// ---- 移动补齐 CP-46 /探险、CP-47 /挖宝、CP-48 奇遇选项芯片 ----
function cpStatLineM(st) { if (!st || typeof st!== "object") return ""; var o = [["power", "攻伐"], ["phys_atk", "物攻"], ["spell_atk", "法攻"], ["defense", "防御"], ["max_hp", "气血"], ["max_mp", "真元"], ["speed", "身法"], ["phys_def", "物防"], ["spell_def", "法防"], ["crit_rate", "暴击"], ["crit_damage", "暴伤"], ["sense_range", "神识"], ["divine_sense", "神识"], ["illusion_resist", "幻抗"], ["pierce", "破甲"], ["lifesteal", "汲取"], ["mind_guard", "护心"], ["charm", "魅力"]]; for (var i = 0; i < o.length; i++) { var v = st[o[i][0]]; if (typeof v === "number" && isFinite(v) && v > 0) return cpKv(o[i][1], "+" + (Math.floor(v) === v? String(v): String(Math.round(v * 100) / 100)), true);} return "";}
function cpAdventure(data, cmd) { var a = data.adventure; if (!a || typeof a!== "object") return ""; var target = String(cmd || "").trim().split(/\s+/).slice(1).join(" ") || "野外山原"; var kv = cpKvs([["胜负", a.combat_success? "得胜": "未分胜负", false], ["修为", cpG(a.exp_delta), true], ["灵石", cpG(a.stones_delta, " 灵石"), true]]); var loot = (Array.isArray(a.loot)? a.loot: []).map(function (it) { return cpRow(cpMain(typeof it === "string"? it: (it.name || ""), typeof it === "object"? (it.desc || ""): ""), null, "");}).join(""); return cpCard("探险 · " + target, "", kv + cpNarr(a.narrative || "") + (loot? cpSec("收获", loot): ""));}
function cpDig(data) { var eq = data.equipment, pill = data.pill, sg = data.stone_gain, sl = data.stone_loss; if (!eq &&!pill &&!sg &&!sl) return ""; var kv = ""; if (eq) kv += cpKv("法宝", esc(cpS(eq.name || "") + " · " + (["凡品", "人品", "地品", "天品", "仙品"][Number(eq.tier) - 1] || "")), false) + cpStatLineM(eq.stats); if (pill) kv += cpKv("丹药", esc(typeof pill === "string"? pill: (pill.name || "")), false); if (sg) kv += cpKv("发掘灵石", "+" + sg + " 灵石", true); if (sl) kv += cpKv("灵石损耗", "−" + sl + " 灵石", true); return cpCard("挖宝 · 破阵结算", "", kv);}
function buildOmenChipsM(data) { var ch = (data.omen_choices || []).filter(function (c) { return c && c.id!= null;}); if (!ch.length) return ""; return cpCard(data.omen_title || "奇遇", "", '<div class="chiprow">' + ch.map(function (c) { return '<button type="button" class="chip primary" data-cmd="/奇遇 ' + esc(c.id) + '">' + esc(c.label || c.id) + '</button>';}).join("") + '</div>');}
// ---- 分发（与桌面同一 token 表；/legacy 不映射，分发到 /转世）----
var CP_ALIASES_M = { look: "look", "道身": "look", profile: "profile", "人物": "profile", "角色": "profile", here: "here", "同场": "here", "近况": "nearby", "目标": "goals", goals: "goals", "任务": "tasks", tasks: "tasks", quest: "tasks", "榜": "rank", rank: "rank", "榜单": "rank", "秘境": "secret", secret: "secret", "世情": "world", "世界演变": "world", "演变": "world", worldinfo: "world", "寻宝": "clue", clue: "clue", "器灵": "spirit", spirit: "spirit", "功法": "arts", arts: "arts", "图鉴": "gallery", gallery: "gallery", "坊市": "market", market: "market", "拍卖行": "auction", auction: "auction", "除凶": "hunt", hunt: "hunt", "宗门": "sect", sect: "sect", "命途": "fate_thread", fate_thread: "fate_thread", "宝图": "map", map: "map", "看宝图": "map", "帮助": "help", help: "help", helpme: "help", who: "who", "天下": "who", "议程": "agenda", agenda: "agenda", "告示": "bounty", bountyboard: "bounty", "天道": "heaven", heaven: "heaven", "导演": "heaven", "世界弧": "arcs", arc: "arcs", "弧": "arcs", "自创功法": "createart", createart: "createart", "命格": "fate", fate: "fate", "回应": "respond", respond_drama: "respond", "因果": "links", "关系链": "links", "关系": "links", "势力": "faction", faction: "faction", "宗门令": "sectorder", sectorder: "sectorder", "宗门势": "sectpower", sectpower: "sectpower", "贡献": "contribution", "兑换": "contribution", "探查": "scan", scan: "scan", "npc货单": "npcgoods", "频道": "channel", channel: "channel", "传说": "legend", legend: "legend", "典籍": "legend", "纪元回流": "era", era: "era", "史笔回流": "era", "交易": "trade", "师门任务": "sectquests", "名物": "mingwu", "宗门环": "sectring", sectring: "sectring", "大劫": "apocalypse", apocalypse: "apocalypse", ai: "ai", "ai自检": "ai", "ai日志": "ailog", ailog: "ailog", "灵宠": "pet", "洞府": "cave", "心法": "mindart", "钱包": "wallet", "行情": "prices", "版图": "atlas", "墓碑": "tombstone", "因果链": "chains", "委托": "quests", "诺言": "promises", "配方": "recipes", "炼体": "bodysoul", "炼神": "bodysoul", "镇魔": "demon", "飞升榜": "ascend", "道统": "legacy", "悟丹": "recipe", "悟器": "recipe", "议政": "council", "结义任务": "swornquests", "探险": "adventure", adventure: "adventure", "挖宝": "dig", dig: "dig"};
var CP_BUILDERS_M = { profile: cpProfile, look: cpLook, here: cpHere, nearby: cpNearby, goals: cpGoals, tasks: cpTasks, rank: cpRank, secret: cpSecret, world: cpWorld, clue: cpClue, spirit: cpSpirit, arts: cpArts, gallery: cpGallery, market: cpMarket, auction: cpAuction, hunt: cpHunt, sect: cpSect, fate_thread: cpFateThread, map: cpMap, help: cpHelp, who: cpWho, agenda: cpAgenda, bounty: cpBounty, heaven: cpHeaven, arcs: cpArcs, createart: cpCreateArt, fate: cpFate, respond: cpRespond, links: cpLinks, faction: cpFaction, sectorder: cpSectOrder, sectpower: cpSectPower, contribution: cpContribution, scan: cpScan, npcgoods: cpNpcGoods, channel: cpChannel, legend: cpLegend, era: cpEra, trade: cpTrade, sectquests: cpSectQuests, mingwu: cpMingwu, sectring: cpSectRing, apocalypse: cpApocalypse, ai: cpAi, ailog: cpAilog, pet: cpPet, cave: cpCave, mindart: cpMindArt, wallet: cpWallet, prices: cpPrices, atlas: cpAtlas, tombstone: cpTombstone, chains: cpChains, quests: cpQuests, promises: cpPromises, recipes: cpRecipes, bodysoul: cpBodySoul, demon: cpDemon, ascend: cpAscend, legacy: cpLegacy, recipe: cpRecipe, council: cpCouncil, swornquests: cpSwornQuests, adventure: cpAdventure, dig: cpDig};
function buildCommandPanel(cmd, data) { if (!data || typeof data!== "object") return ""; var tok = String(cmd || "").trim().split(/\s+/)[0].replace(/^\//, "").toLowerCase(); var id = CP_ALIASES_M[tok]; if (!id) return ""; var fn = CP_BUILDERS_M[id]; if (typeof fn!== "function") return ""; try { var html = fn(data, cmd); return typeof html === "string"? html: "";} catch (_) { return "";}}
// == command-panels: end ==

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
      if (data.ceremony || data.ceremony_next) maybeShowCeremonyQueueM(data.ceremony, data.ceremony_next);
      // 交谈旧账行（game-feel-phase2 §8.3）：交谈开启响应 old_account 在场才渲染，置于交谈文本之前
      if (data.old_account) pushFeed(oldAccountTextM(data.old_account), "ok");
      // 命令面板（command-panels §3-D1/§11-D2，CP-46/CP-47）：有结构键时卡片替代该条
      // 纯文本块；无结构键（(c) 类 / 后端键未落地）时回落纯文本呈现。
      var panelHtml = buildCommandPanel(c, data);
      if (panelHtml) pushFeedHtml(panelHtml, data.ok === false ? "bad" : undefined);
      else if (data.text) pushFeed(data.text, data.ok === false ? "bad" : undefined, data.omen_image || "");
      else if (data.ok === false && data.error)
        pushFeed("敕令失败：" + data.error, "bad");
      // 奇遇/天象选项芯片（CP-48）：与桌面 inline 条同构，配图保留在上条文本里。
      if (data.omen_inline === true && Array.isArray(data.omen_choices) && data.omen_choices.length)
        pushFeedHtml(buildOmenChipsM(data), "ok");
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
      if (payload.ceremony || payload.ceremony_next) maybeShowCeremonyQueueM(payload.ceremony, payload.ceremony_next);
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
      if (t.closest("[data-ceremony-close]")) { closeCeremonyM(); return; }
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
