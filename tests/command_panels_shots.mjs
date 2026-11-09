// command-panels §8 截图页生成器（node tests/command_panels_shots.mjs）。
// 用法：node tests/command_panels_shots.mjs
//   → 写 docs/compose/command-panels-shots/*.html（截图源页）
//   → 再跑 node tests/shoot_command_panels.mjs 拍 *.png（CDP 全页实拍）。
// 口径：面板 HTML 由 workbench.js / mobile.js 的真实面板块渲染（与夹具同一抽取口径）；
//   数据 = 合同审计真实抓取 + Spec 附录 A 合成 payload（与夹具同一数据；
//   合成 payload 均取自夹具已断言的 live 形态，非臆测键形）；
//   样式 = 真实 workbench.css / mobile.css 内联；沙盒无法加载 Tailwind CDN，
//   故 Tailwind 工具类（p-4/text-sm/flex 等）不生效——布局比生产环境疏松，
//   内容/数值/颜色以真实 CSS 为准，此局限在报告与页头如实注明。
// 清单（§8，返工 2026-11-09 补齐）：
//   SC-P0（/profile·/look 双端×昼夜 4 页，合页）+ 每面板化对象双端单页
//   （67 个 (b) 条目 × 桌面 1280 + 手机 390；移动另加 CP-46/47/48 共 5 页）
//   + 深蓝抽查（P1/P2/P3/附录每波 3 项 × 双端 = 24 页）
//   + AC-10 空态（/告示·/宗门环·/灵宠·/器灵·/寻宝 × 双端 = 10 页）
//   + SC-回归 (a) 类（/突破·/挖宝·/交谈·/奇遇 桌面各 1 页，分发器回落证据）
//   + 每波代表合页（SC-waves 3 页）与 CP-46/47/48 合页（1 页）保留。
// 生成器内断言：每张面板页双端（或指定端）渲染非空、无 [object Object] /
//   undefined / NaN 泄漏；空态页断言面板确为空、回落真实文本。任一失败即退出非零。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "docs/compose/command-panels-shots");
fs.mkdirSync(OUT, { recursive: true });

function cap(slug) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "docs/compose/contract-audit-captures", slug + ".json"), "utf-8")).response;
}
function extract(file, stubs) {
  const src = fs.readFileSync(path.join(ROOT, file), "utf-8");
  const a = src.indexOf("== command-panels: begin ==");
  const b = src.indexOf("== command-panels: end ==");
  if (a < 0 || b < 0) throw new Error(file + " 无面板块标记");
  const start = src.lastIndexOf("\n", a) + 1;
  const api = {};
  const fn = new Function("api", "esc", "fmtRemYears", "remYearsUnit", "fateThreadHtml", "fateThreadHtmlM", "galleryImg",
    src.slice(start, b) + "\n;api.buildCommandPanel = typeof buildCommandPanel !== 'undefined' ? buildCommandPanel : buildCommandPanelM;\napi.buildOmenChipsM = typeof buildOmenChipsM !== 'undefined' ? buildOmenChipsM : null;\n");
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fateShim = (t) => { const th = t.thread || t; return `<div>${esc(th.title || "")}</div>`; };
  const galleryImg = (n) => "";
  fn(api, esc, (v) => (v == null ? "—" : Number(v).toFixed(1)), (v) => (v == null ? "" : "载"), fateShim, fateShim, galleryImg);
  return api;
}
const desk = extract("web/workbench.js");
const mob = extract("web/mobile.js");
const cssD = fs.readFileSync(path.join(ROOT, "web/workbench.css"), "utf-8");
const cssM = fs.readFileSync(path.join(ROOT, "web/mobile.css"), "utf-8");
const lookStatus = cap("002-ro-look").status;

const FATE_PENDING = { fate: { boons: [{ key: "sword_heart", name: "剑心通明", source_cn: "道韵", from_tier: 2, chosen_at: 1794120908 }], pending: [{ candidates: [{ key: "pure_yang", name: "纯阳烈煞", desc: "纯阳烈煞在身", icon: "☀" }], from_tier: 2 }], power_bonus: 1.1 } };
const BOARDS = { boards: [{ name: "realm", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 5100 }] }, { name: "power", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 63136.25 }] }] };
const DIRECTOR = { director: { last_run: 1794120908, stats: { runs: 1, accepted: 2, attempts: 1, rejected: 0 }, active: [{ type: "sect_tension", type_cn: "宗门紧张", title: "敌门暗涌", narrative: "两宗相争。", expires_at: 1794124508 }] } };
const RECIPES = { recipes: [{ name: "聚气丹方", "产物": "聚气丹", "材料": ["聚灵草", "灵泉水"], "炉火": "文火", "成率": 0.8 }] };
const QUESTS = { quests: [{ npc: "小雀儿", realm: "练气期初期", "环数": 3, "赏": "灵石 100 + 功德 5", "首环": "寻得聚灵草一份" }] };
const MARKET = { status: { stones: 100015, vault: 0, market_listings: [{ name: "聚气丹", price: 40 }] } };
const NOW = Math.floor(Date.now() / 1000);

function feedItem(cmd, html, text) {
  return `<div class="shot-item"><div class="shot-echo">» ${cmd}</div>${html || `<p class="shot-text">${text || "（面板未触发，回落纯文本）"}</p>`}</div>`;
}
// Tailwind CDN 沙盒不可达；截图页专用垫片，仅实现面板实际用到的 4 个文字色类 +
// text-xs/text-sm 字号：jade 色值逐字取自 web/index.html tailwind.config，
// slate 取 Tailwind 默认色板（index.html 未覆盖）；不随货。页面底色用真实
// .bg-paper-pattern（workbench.css）；桌面深色本就只靠各元素 dark: 变体，
// 无全局深色规则（workbench.css / index.html 均无），故深色页底色与浅色一致。
const TW_SHIM = `.text-jade-950{color:#081d19}.text-slate-400{color:#94a3b8}.text-slate-500{color:#64748b}.text-slate-700{color:#334155}.text-xs{font-size:12px;line-height:1.5}.text-sm{font-size:14px;line-height:1.5}`;
function page({ title, css, theme, width, items, note }) {
  return `<!DOCTYPE html><html lang="zh-CN" data-theme="${theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title><style>${css}\n${TW_SHIM}\nbody{margin:0;padding:16px;font-family:system-ui,sans-serif;}\n.shot-wrap{max-width:${width}px;margin:0 auto;}\n.shot-note{font-size:12px;color:#666;margin:0 0 12px;line-height:1.6;}\n.shot-item{margin-bottom:18px;}\n.shot-echo{font-size:13px;font-weight:700;margin:0 0 6px;}\n.shot-text{font-size:13px;line-height:1.7;white-space:pre-wrap;}\n</style></head><body class="bg-paper-pattern"><div class="shot-wrap"><p class="shot-note">${note}</p>${items}</div></body></html>`;
}
const NOTE = "命令回复面板化 §8 截图源页：面板 HTML 由真实面板块渲染，数据为合同审计真实抓取 + Spec 附录 A 合成 payload；样式为真实 workbench.css / mobile.css 内联。沙盒无法加载 Tailwind CDN，故工具类由页内垫片实现面板实际用到的 4 个文字色类 + 2 个字号（色值取自 index.html tailwind.config / Tailwind 默认 slate 色板，不随货）；其余间距/布局类不生效，布局比生产环境疏松——内容/数值/颜色以真实 CSS 为准。";
const strip = (h) => String(h || "").replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/\s+/g, " ").trim();

const manifest = [];
function write(name, html) { fs.writeFileSync(path.join(OUT, name), html, "utf-8"); console.log("wrote", name, html.length + "B"); }
function checkPanel(label, html) {
  if (!html) throw new Error(label + "：面板渲染为空");
  const t = strip(html);
  for (const bad of ["[object Object]", "undefined", "NaN"]) {
    if (t.includes(bad)) throw new Error(label + "：泄漏 " + bad + " —— " + t.slice(0, 200));
  }
  return html;
}

// ---- SC-P0：/profile + /look，双端 × 昼夜（合页，保留）----
const p0 = [["/profile", cap("018-ro-profile")], ["/look", cap("002-ro-look")]];
for (const [theme, file] of [["light", "sc-p0-desktop-light.html"], ["dark", "sc-p0-desktop-dark.html"]]) {
  write(file, page({ title: "SC-P0 desktop " + theme, css: cssD, theme, width: 1280,
    items: p0.map(([c, d]) => feedItem(c, checkPanel("SC-P0 " + c, desk.buildCommandPanel(c, d)))).join(""), note: NOTE }));
  manifest.push([file, "CP-01/02", "/profile + /look", "desktop", theme]);
}
for (const [theme, file] of [["light", "sc-p0-mobile-light.html"], ["dark", "sc-p0-mobile-dark.html"]]) {
  write(file, page({ title: "SC-P0 mobile " + theme, css: cssM, theme, width: 390,
    items: p0.map(([c, d]) => feedItem(c, checkPanel("SC-P0 " + c, mob.buildCommandPanel(c, d)))).join(""), note: NOTE }));
  manifest.push([file, "CP-01/02", "/profile + /look", "mobile", theme]);
}
// ---- 每波代表（合页，保留）----
const waves = [["/世情", cap("092-ro-世情")], ["/图鉴", cap("009-ro-图鉴")], ["/榜", BOARDS],
  ["/命格", FATE_PENDING], ["/钱包", cap("014-ro-wallet")], ["/天道", DIRECTOR],
  ["/道统", cap("005-ro-legacy")], ["/配方", RECIPES]];
write("sc-waves-desktop-light.html", page({ title: "SC-waves desktop light", css: cssD, theme: "light", width: 1280,
  items: waves.map(([c, d]) => feedItem(c, checkPanel("waves " + c, desk.buildCommandPanel(c, d)))).join(""), note: NOTE }));
manifest.push(["sc-waves-desktop-light.html", "P1/P2/P3/附录代表", "8 项合页", "desktop", "light"]);
write("sc-waves-desktop-dark.html", page({ title: "SC-waves desktop dark", css: cssD, theme: "dark", width: 1280,
  items: waves.map(([c, d]) => feedItem(c, checkPanel("waves " + c, desk.buildCommandPanel(c, d)))).join(""), note: NOTE }));
manifest.push(["sc-waves-desktop-dark.html", "P1/P2/P3/附录代表", "8 项合页", "desktop", "dark"]);
write("sc-waves-mobile-light.html", page({ title: "SC-waves mobile light", css: cssM, theme: "light", width: 390,
  items: waves.map(([c, d]) => feedItem(c, checkPanel("waves " + c, mob.buildCommandPanel(c, d)))).join(""), note: NOTE }));
manifest.push(["sc-waves-mobile-light.html", "P1/P2/P3/附录代表", "8 项合页", "mobile", "light"]);

// ---- 每面板化对象双端单页（§8 底线：67 个 (b) 条目 × 桌面 1280 + 手机 390）----
// payload 来源：cap() = 合同审计真实抓取；行内对象 = 夹具已断言的 live 形态。
const SHOTS = [
["cp01-profile", "CP-01", "/profile", cap("018-ro-profile")],
["cp02-look", "CP-02", "/look", cap("002-ro-look")],
["cp03-here", "CP-03", "/here", cap("016-ro-here")],
["cp04-nearby", "CP-04", "/近况", cap("025-ro-近况")],
["cp05-goals", "CP-05", "/目标", cap("023-ro-goals")],
["cp06-tasks", "CP-06", "/任务", cap("218-tasks")],
["cp07-rank", "CP-07", "/榜", BOARDS],
["cp08-secret", "CP-08", "/秘境", { realms: [{ name: "落霞古洞", location: "落霞山灵泉", "门槛": "境界 1+", "危险%": 35, "状态": "已开启", "描述": "残破古洞" }] }],
["cp09-world", "CP-09", "/世情", cap("092-ro-世情")],
["cp10-clue", "CP-10", "/寻宝", { clue: { map_name: "古修遗图", chain_status: "active", current_step: 1, total_steps: 2, current: { kind: "guard", kind_cn: "守卫", node_name: "黑水沼泽", riddle: "何物无声却传千里？", options: [] }, can_abandon: true } }],
["cp11-spirit", "CP-11", "/器灵", { spirit: { items: [{ name: "联调剑", tier: 5, tier_name: "天品", spirit: null, can_awaken: true }], awakenable: ["联调剑"] } }],
["cp12-arts", "CP-12", "/功法", { arts: [], status: lookStatus }],
["cp13-gallery", "CP-13", "/图鉴", cap("009-ro-图鉴")],
["cp14-market", "CP-14", "/坊市", MARKET],
["cp15-auction", "CP-15", "/拍卖行", { auction: { lots: [{ id: "a1", name: "聚气丹", start_price: 100, current_price: 100, leader: "（暂无）", seller: "联调客", buyout_price: 500, remaining_s: 7199, bid_count: 0, status: "OPEN" }] } }],
["cp16-hunt", "CP-16", "/除凶", { hunt: [{ name: "血煞散修", realm: "筑基期中期", mark: "血煞", sin: 500, location: "黑水沼泽", is_npc: true, hunters: 0 }] }],
["cp17-sect", "CP-17", "/宗门", { sects: [{ name: "青云宗", alignment: "正道", members: 120, players: 3, monthly_salary: 25, headquarters: "青云宗外门山门", rules_tip: "门规森严", top: [{ name: "玄清子", rank: "掌门", realm: "元婴期" }] }] }],
["cp18-fatethread", "CP-18", "/命途", cap("011-ro-命途")],
["cp19-map", "CP-19", "/宝图", { treasure_map: { name: "古图·坎水", tier: 3, bagua: "坎", coords: "东三里", riddle: "枯井之下有玄光。", clue: "井边三尺", target_node: "落霞古洞", archetype: "解谜" } }],
["cp20-help", "CP-20", "/帮助", cap("028-ro-帮助")],
["cp21-who", "CP-21", "/who", { who: { groups: [{ place: "青云坊市客栈", members: [{ name: "金满堂", realm: "金丹期中期" }] }] } }],
["cp22-agenda", "CP-22", "/议程", cap("053-ro-agenda")],
["cp23-bounty", "CP-23", "/告示", { bounties: [{ id: "b1", target: "悬赏测试丁", reward: 100, status: "OPEN", status_cn: "待猎", issuer: "联调客", anonymous: false, reason: "面板测试" }] }],
["cp24-heaven", "CP-24", "/天道", { director: { last_run_ts: 1794187092, last_trigger: "tick", last_source: "local", last_error: null, stats: { runs: 60, accepted: 3, rejected: 0, attempts: 60 }, active: [{ type: "sect_tension", type_cn: "宗门紧张", title: "敌门暗涌", location: "青云宗", expires_in_s: 3180, narrative: "测试叙事", applied: {} }] } }],
["cp25-arcs", "CP-25", "/世界弧", { arcs: { stats: { spawned: 2, advanced: 0, climaxed: 0 }, arcs: [{ id: "a1", kind: "sect_crisis", title: "敌门暗涌·青云宗×九幽天魔宗", location: "青云宗", stage: "prophesy", stage_cn: "预兆", deadline_in_s: 480, last_log: "" }], history: ["1794186677|spawn|sect_crisis|敌门暗涌·青云宗×九幽天魔宗|a_499025f6"], modifiers: { heat_by_location: { "落霞山灵泉": 1.2 }, blood_tide_locations: [], sect_tensions: [["青云宗", "九幽天魔宗"]], realm_pressure_ids: [], calamity_forecast: {}, hunt_heat: {}, active_arc_kinds: ["sect_crisis"], n_arcs: 2 } } }],
["cp26-createart", "CP-26", "/自创功法", cap("156-create-art")],
["cp27-fate", "CP-27", "/命格", FATE_PENDING],
["cp28-respond", "CP-28", "/回应", { drama_pending: [{ id: "dr_1", npc_name: "铁算盘", text: "旧怨未消，今日便要讨个说法！", options: [{ key: "fight", label: "应战" }, { key: "avoid", label: "避走" }] }] }],
["cp29a-links", "CP-29", "/因果", { links: [{ kind: "仇", "名": "铁算盘", "强度": 1, "缘由": "出身旧怨：背案在身" }] }],
["cp29b-relation", "CP-29", "/关系", { links: [{ kind: "gratitude", name: "联调牵缠", strength: 30, note: "联调测试牵缠" }] }],
["cp30-faction", "CP-30", "/势力", { factions: { relations: [], orders: [{ id: "f1", sect: "青云宗", title: "巡山", kind: "patrol", reward_contrib: 5 }], sieges: [], stats: {} } }],
["cp31-sectorder", "CP-31", "/宗门令", { sect_orders: [{ id: "o1", sect: "青云宗", title: "巡山", kind: "patrol", reward_contrib: 8 }] }],
["cp32-sectpower", "CP-32", "/宗门势", { sect_power: { sects: [{ sect: "青云宗", members: 120, score: 46.8 }], hostile_pairs: [["青云宗", "九幽天魔宗"]], tense_pairs: [], sieges: [], open_missions: 2 } }],
["cp33a-contribution", "CP-33", "/贡献", { contribution: { sect: "散修", points: 0, catalog: [{ name: "聚气丹", cost: 8 }, { name: "玄元聚气丹", cost: 80, "需连环": 3 }] } }],
["cp33b-redeem", "CP-33", "/兑换", { contribution: { sect: "散修", points: 0, catalog: [{ name: "聚气丹", cost: 8 }, { name: "玄元聚气丹", cost: 80, "需连环": 3 }] } }],
["cp34-scan", "CP-34", "/探查", cap("158-scan")],
["cp35-npcgoods", "CP-35", "/npc货单 金满堂", { npc_goods: [{ name: "聚气丹", price: 40, "描述": "行气丹药" }] }],
["cp36-channel", "CP-36", "/频道", { channel: [{ severity: "major", type: "bond", type_cn: "结缘", text: "联调频道探针消息", actor: "联调客", location: "青云坊市客栈", ts: 1794187095 }] }],
["cp37-legend", "CP-37", "/传说", { legends: { legends: [{ title: "联调史笔", text: "联调传说文本", season: 1, actor: "联调客", weight: 1 }], total: 2, active_bias: {} } }],
["cp38-era", "CP-38", "/纪元回流", { era_flow: { current_season: 1, last_reentry_ts: 1794187092, active_bias: {}, anchors: [], completed_eras: [], cited_count: 0 } }],
["cp39-trade", "CP-39", "/交易", { trade: { partner: "联调客", location: "青云坊市客栈", status: "OPEN", created_at: NOW, a: { name: "联调客", stones: 10, items: [], agreed: false }, b: { name: "联调交易乙", stones: 0, items: [], agreed: false } } }],
["cp40-sectquests", "CP-40", "/师门任务", { sect_quests: { master: "联调师父", task: { id: "sq1", label: "巡山", need_visit: "青云宗外门山门" }, done: false } }],
["cp41-mingwu", "CP-41", "/名物", { relics: [{ name: "联调名物", type: "丹药", status: "known", desc: "联调名物描述", source: "联调", confidence: 1 }] }],
["cp42-sectring", "CP-42", "/宗门环", { status: { sect_ring: { day: "甲子日", accepted: false, done: false, themes: [{ id: 1, label: "洒扫", lore: "洒扫山门", need_item: "", need_streak: 0 }] } } }],
["cp43-apocalypse", "CP-43", "/大劫", cap("162-apocalypse")],
["cp44-ai", "CP-44", "/ai", cap("027-ro-ai")],
["cp45-ailog", "CP-45", "/AI日志", cap("026-ro-ailog")],
["cp49-pet", "CP-49", "/灵宠", { pets: [{ name: "青鳞蟒", species: "蟒", tendency: "水", level: 3, growth: 250, intimacy: 42, state: "出战中" }] }],
["cp50-cave", "CP-50", "/洞府", { status: { cave: { level: 2, plots_total: 4, plots_used: 3, mature: 1 } } }],
["cp51-mindart", "CP-51", "/心法", cap("075-ro-心法")],
["cp52-wallet", "CP-52", "/钱包", cap("014-ro-wallet")],
["cp53-prices", "CP-53", "/行情", { prices: { as_of: "2026-11-09", current_region: "青云坊市", regions: [{ name: "青云坊市", current: true, rows: [{ name: "灵谷种子", kind: "seed", price: 10, sell_price: 5, base_price: 10, origin: "青云坊市", factor: 1.0, desc: "" }] }] } }],
["cp54-atlas", "CP-54", "/版图", { atlas: [{ region: "青云坊市", dominant: "青云宗", dominant_value: 120.0, mine: "青云宗", influence: {} }] }],
["cp55-tombstone", "CP-55", "/墓碑 审计员", { tombstone: { name: "审计员", realm: "练气期初期", cause: "渡劫陨落", points: 3, "评语": "谨慎求生，终归尘土。" } }],
["cp56-chains", "CP-56", "/因果链", { karma_chains: [{ kind: "en", kind_cn: "恩", status: "fermenting", status_cn: "发酵", counterparty: "联调因果", origin: "联调", strength: 7, elapsed_days: 1, total_days: 9, ferment_pct: 11, direction: "对象念恩" }] }],
["cp57-quests", "CP-57", "/委托", { quests: { active: { publisher: "凶名测试丁", publisher_id: "u1", rings_total: 4, ring_index: 0, ring: { kind: "slay", kind_cn: "除妖", desc: "剿除妖兽", progress: 0, need: 1, deliver_npc_name: "凶名测试丁", item_name: null }, reward_stones: 130, reward_merit: 5, expires_in_s: 86399 }, offers: [{ npc: "凶名测试丁", realm: "练气期初期", rings: 4, reward_stones: 130, reward_merit: 5, first_ring: { kind: "fetch", kind_cn: "寻物", desc: "寻聚灵草" } }] } }],
["cp58-promises", "CP-58", "/诺言", { promises: [{ bucket: "我立之诺", desc: "3 日内赠", kind: "gift", promiser: "联调客", promisee: "联调诺言", status: "ACTIVE", left_s: 259200, deadline: NOW + 259200, settle_note: "" }] }],
["cp59-recipes", "CP-59", "/配方", { recipes: [{ id: "r1", name: "聚气丹方", kind: "pill", output: "聚气丹", materials: { "百年灵芝": 1, "聚灵草": 2 }, stones_fee: 15, base_rate: 0.83, rate: 0.83, req_tier: 1, tier_ok: true, can_craft: true }] }],
["cp60a-bodysoul", "CP-60", "/炼体", { body_soul_detail: { body: { track: "body", track_cn: "炼体", level: 2, cap: 10, effect: "气血+10", next_cost: { item: "妖兽内丹", item_count: 1, stones: 20, have_item: 0, have_stones: 5015 }, other_level: 1 }, soul: { track: "soul", track_cn: "炼神", level: 1, cap: 10, effect: "神识+5", next_cost: { item: "百年灵芝", item_count: 1, stones: 10, have_item: 0, have_stones: 5015 }, other_level: 2 } } }],
["cp60b-bodysoul", "CP-60", "/炼神", { body_soul_detail: { body: { track: "body", track_cn: "炼体", level: 2, cap: 10, effect: "气血+10", next_cost: { item: "妖兽内丹", item_count: 1, stones: 20, have_item: 0, have_stones: 5015 }, other_level: 1 }, soul: { track: "soul", track_cn: "炼神", level: 1, cap: 10, effect: "神识+5", next_cost: { item: "百年灵芝", item_count: 1, stones: 10, have_item: 0, have_stones: 5015 }, other_level: 2 } } }],
["cp61-demon", "CP-61", "/镇魔", { demon: { stage: 2, stage_name: "滋长", seed: 50.0, seed_cap: 90.0, sin: 0, blood_marked: false, eff_dao_heart: 100, suppress_mult: 0.25, eruption: { breakthrough_pct: 0.35, meditation_pct: 0.25 }, options: [{ kind: "pill", item: "百年灵芝", count: 1, stones: 30, seed_delta: 35.0 }, { kind: "calm", min_dao: 50, cooldown_h: 20, seed_delta: 20.0 }] } }],
["cp62-ascend", "CP-62", "/飞升榜", { ascend: [{ user_id: "u1", name: "飞升测试故人", realm: "元婴期", tier: 5, sub_tier: 0, cause: "天劫陨落", cause_category: "tribulation", lifespan_lived: 210, points_gained: 100, died_at: 1794100463, season: 1, score: 4355.0, rank: 1 }] }],
["cp63-legacy", "CP-63", "/道统", cap("005-ro-legacy")],
["cp64a-recipe", "CP-64", "/悟丹 随机", { recipe: { id: "rx1", name: "止血散方", output_pill: "止血散", output: "止血散", kind: "pill", materials: { "止血灵叶": 3 }, stones_fee: 8, desc: "止血散方", base_rate: 0.9 } }],
["cp64b-recipe", "CP-64", "/悟器 随机", { recipe: { id: "rx2", name: "残卷·测试器", output: "测试法宝", kind: "equip", materials: { "玄铁": 2 }, stones_fee: 12, desc: "测试法宝方", base_rate: 0.85 } }],
["cp65-council", "CP-65", "/议政", { council: { sect: "青云宗", session_no: 1, vault: 1000, prestige: 50, morale: 50, topic: { id: "mining", name: "开矿增收", desc: "开矿增收描述" }, settled: false, closes_in_s: 6985, seats: [{ name: "丹霞子", rank: "长老", stance: "support", stance_cn: "支持", lobbied: false, virtual: false, line: "老夫赞成。" }], votes: { support: 0, oppose: 0, mine: null } } }],
["cp66-swornquests", "CP-66", "/结义任务", { sworn_quests: { partner: "联调结义乙", task: { id: "sw1", label: "历练", need_visit: "落霞古洞" }, done: false } }],
];
for (const [slug, cp, cmd, data] of SHOTS) {
  for (const [end, api, css, width] of [["desktop", desk, cssD, 1280], ["mobile", mob, cssM, 390]]) {
    const file = `sc-${slug}-${end}-light.html`;
    write(file, page({ title: `SC ${cp} ${end} light ${cmd}`, css, theme: "light", width,
      items: feedItem(cmd, checkPanel(`${slug} ${end}`, api.buildCommandPanel(cmd, data))), note: NOTE }));
    manifest.push([file, cp, cmd, end, "light"]);
  }
}
// ---- 深蓝抽查：P1/P2/P3/附录每波 3 项 × 双端 ----
for (const [slug, cp, cmd, data] of SHOTS.filter(([s]) => ["cp07-rank", "cp09-world", "cp17-sect", "cp27-fate", "cp24-heaven", "cp31-sectorder", "cp38-era", "cp43-apocalypse", "cp44-ai", "cp53-prices", "cp59-recipes", "cp63-legacy"].includes(s))) {
  for (const [end, api, css, width] of [["desktop", desk, cssD, 1280], ["mobile", mob, cssM, 390]]) {
    const file = `sc-${slug}-${end}-dark.html`;
    write(file, page({ title: `SC ${cp} ${end} dark ${cmd}`, css, theme: "dark", width,
      items: feedItem(cmd, checkPanel(`${slug} ${end} dark`, api.buildCommandPanel(cmd, data))), note: NOTE }));
    manifest.push([file, cp, cmd, end, "dark"]);
  }
}
// ---- CP-46/47/48 移动端（合页，保留；另见下方单页）----
const advWin = { adventure: { combat_success: true, exp_delta: 120, stones_delta: -20, narrative: "深入古洞，得见玉简。", loot: ["聚灵草"] } };
const advLose = { adventure: { combat_success: false, exp_delta: 0, stones_delta: -50, narrative: "洞中妖气大盛，仓皇退走。", loot: [] } };
const advNone = { adventure: { combat_success: null, exp_delta: 10, stones_delta: 5, narrative: "一路无事，采得些许灵草。", loot: ["止血草"] } };
const digEquip = { equipment: { name: "九天避火佩", tier: 3, stats: { power: 198 } }, pill: null, stone_gain: 0, stone_loss: 40 };
const digPill = { equipment: null, pill: { name: "聚气丹", tier: 2 }, stone_gain: 0, stone_loss: 40 };
const digStones = { equipment: null, pill: null, stone_gain: 120, stone_loss: 40 };
const omen = { omen_title: "残碑悟道", omen_inline: true, omen_choices: [{ id: "1", label: "上前参悟" }, { id: "2", label: "抽身离去" }] };
write("sc-cp46-47-48-mobile-light.html", page({ title: "SC CP-46/47/48 mobile light", css: cssM, theme: "light", width: 390,
  items: [
    feedItem("/探险 落霞古洞（得胜）", checkPanel("advWin", mob.buildCommandPanel("/探险 落霞古洞", advWin))),
    feedItem("/探险 落霞古洞（落败）", checkPanel("advLose", mob.buildCommandPanel("/探险 落霞古洞", advLose))),
    feedItem("/探险 落霞古洞（无战）", checkPanel("advNone", mob.buildCommandPanel("/探险 落霞古洞", advNone))),
    feedItem("/挖宝（法宝）", checkPanel("digEquip", mob.buildCommandPanel("/挖宝", digEquip))),
    feedItem("/挖宝（丹药）", checkPanel("digPill", mob.buildCommandPanel("/挖宝", digPill))),
    feedItem("/挖宝（灵石）", checkPanel("digStones", mob.buildCommandPanel("/挖宝", digStones))),
    `<div class="shot-item"><div class="shot-echo">» /望气（奇遇条选项芯片）</div><div class="shot-text">残碑悟道</div>${mob.buildOmenChipsM(omen) || ""}</div>`,
  ].join(""), note: NOTE }));
manifest.push(["sc-cp46-47-48-mobile-light.html", "CP-46/47/48", "/探险·/挖宝·/望气", "mobile", "light"]);
// ---- CP-46/47/48 移动端单页 ----
for (const [slug, cp, cmd, data] of [
  ["cp46-adventure", "CP-46", "/探险 落霞古洞", advWin],
  ["cp47-dig", "CP-47", "/挖宝", digEquip],
]) {
  const file = `sc-${slug}-mobile-light.html`;
  write(file, page({ title: `SC ${cp} mobile light ${cmd}`, css: cssM, theme: "light", width: 390,
    items: feedItem(cmd, checkPanel(slug, mob.buildCommandPanel(cmd, data))), note: NOTE }));
  manifest.push([file, cp, cmd, "mobile", "light"]);
}
for (const [slug, cp, cmd] of [["cp48-wangqi", "CP-48", "/望气"], ["cp48-qiyu", "CP-48", "/奇遇"], ["cp48-jiyuan", "CP-48", "/机缘"]]) {
  const chips = mob.buildOmenChipsM(omen);
  if (!chips || !strip(chips).includes("上前参悟")) throw new Error(slug + "：选项芯片未渲染");
  const file = `sc-${slug}-mobile-light.html`;
  write(file, page({ title: `SC ${cp} mobile light ${cmd}`, css: cssM, theme: "light", width: 390,
    items: `<div class="shot-item"><div class="shot-echo">» ${cmd}（奇遇条选项芯片）</div><div class="shot-text">残碑悟道</div>${chips}</div>`, note: NOTE }));
  manifest.push([file, cp, cmd, "mobile", "light"]);
}
// ---- AC-10 空态：面板不触发，回落一行纯文本（真实抓取 text）----
const emptyCases = [
  ["gaoshi", "/告示", "056-ro-告示"], ["zongmenhuan", "/宗门环", "071-ro-宗门环"],
  ["lingchong", "/灵宠", "074-ro-灵宠"], ["qiling", "/器灵", "013-ro-器灵"],
  ["xunbao", "/寻宝", "012-ro-寻宝"],
];
for (const [slug, cmd, capSlug] of emptyCases) {
  const d = cap(capSlug);
  for (const [end, api, css, width] of [["desktop", desk, cssD, 1280], ["mobile", mob, cssM, 390]]) {
    const html = api.buildCommandPanel(cmd, d);
    if (html !== "") throw new Error(`空态 ${slug} ${end}：面板应为空，实际渲染了卡片`);
    const text = (d.text || "").slice(0, 400);
    if (!text) throw new Error(`空态 ${slug}：抓取无 text 可回落`);
    const file = `sc-empty-${slug}-${end}-light.html`;
    write(file, page({ title: `SC empty ${cmd} ${end} light`, css, theme: "light", width,
      items: feedItem(cmd, "", text), note: NOTE + " 空态口径 D6：行集为空时不出空卡，回落一行纯文本。" }));
    manifest.push([file, "AC-10", cmd + "（空态）", end, "light"]);
  }
}
// 旧空态合页（保留，与上表同口径）
const emptyOld = [["/命格", cap("010-ro-命格")], ["/洞府", cap("076-ro-洞府")], ["/灵宠", cap("074-ro-灵宠")], ["/坊市", cap("057-ro-market")]];
write("sc-empty-desktop-light.html", page({ title: "SC empty desktop light", css: cssD, theme: "light", width: 1280,
  items: emptyOld.map(([c, d]) => feedItem(c, desk.buildCommandPanel(c, d), (d.text || "").slice(0, 400))).join("")
    + feedItem("/委托（空）", desk.buildCommandPanel("/委托", { quests: [] }), "暂无委托。"), note: NOTE + " 空态口径 D6：行集为空时不出空卡，回落一行纯文本。" }));
manifest.push(["sc-empty-desktop-light.html", "AC-10", "/命格·/洞府·/灵宠·/坊市·/委托（空态合页）", "desktop", "light"]);
// ---- SC-回归：(a) 类形态未动——分发器回落证据（桌面）----
// buildCommandPanel 对 (a) 类命令返回 ""（夹具已断言 /奇遇双端 ""；/突破·/挖宝·
// /交谈无 builder），面板分支不拦截，仍走既有仪式/对话框/交谈面板/奇遇条。
// 静态源页无法复现全屏仪式与对话框，故本页证据为：分发器回落判定 + 未改动
// 的既有处理锚点；页内文字为核查注记，非游戏文本。
const regress = [
  ["tupo", "/突破", "仪式双幕（ceremony + ceremony_next），web/workbench.js maybeShowCeremonyQueue；桌面 fallback dialog 在 sendCmd 内 /突破 分支。"],
  ["wabao", "/挖宝", "宝图 dialog（#treasureStageBox）+ 结算面板，web/workbench.js handleTreasureAction；移动端结算面板见 sc-cp47-dig。"],
  ["jiaotan", "/交谈", "交谈面板，web/workbench.js openChat / renderChat；会话内 /说·/挂断同流。"],
  ["qiyu", "/奇遇", "奇遇 inline 条 + 选项芯片，web/workbench.js renderInlineOmenBar / applyOmenPayload；移动端芯片见 sc-cp48-qiyu。"],
];
for (const [slug, cmd, note] of regress) {
  const html = desk.buildCommandPanel(cmd, { ok: true, text: "" });
  if (html !== "") throw new Error(`回归 ${slug}：(a) 类命令不应出面板`);
  const file = `sc-regress-${slug}-desktop-light.html`;
  write(file, page({ title: `SC regress ${cmd} desktop light`, css: cssD, theme: "light", width: 1280,
    items: `<div class="shot-item"><div class="shot-echo">» ${cmd}</div><p class="shot-text">回归核查注记（非游戏文本）：面板分发器对该命令返回空，feed 不出命令面板，形态未动。既有流：${note}</p></div>`,
    note: NOTE + " (a) 类回归口径：静态源页只验分发器不拦截；仪式/对话框/交谈面板本体由既有流程覆盖，本轮零改动。" }));
  manifest.push([file, "SC-回归", cmd + "（(a) 类形态未动）", "desktop", "light"]);
}
// ---- 清单 ----
const manLines = ["# 命令回复面板化 §8 截图清单（生成器产物，返工 2026-11-09）", "",
  "口径：面板 HTML 由真实面板块渲染，数据为合同审计真实抓取 + Spec 附录 A 合成 payload；",
  "样式为真实 workbench.css / mobile.css 内联。沙盒无法加载 Tailwind CDN，工具类由页内",
  "垫片实现面板实际用到的 4 个文字色类 + 2 个字号，布局比生产环境疏松——内容/数值/",
  "颜色以真实 CSS 为准。PNG 由 node tests/shoot_command_panels.mjs 全页实拍（CDP）。",
  "", `共 ${manifest.length} 页（HTML + PNG 各一）。`, "",
  "| 源页 | 任务 | 命令 | 端 | 主题 |", "|---|---|---|---|---|"];
for (const [f, cp, cmd, end, theme] of manifest) manLines.push(`| ${f} | ${cp} | ${cmd} | ${end} | ${theme} |`);
fs.writeFileSync(path.join(OUT, "MANIFEST.md"), manLines.join("\n") + "\n", "utf-8");
console.log(`done. ${manifest.length} pages listed in MANIFEST.md`);
