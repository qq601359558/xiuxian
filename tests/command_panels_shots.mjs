// command-panels §8 截图页生成器（node tests/command_panels_shots.mjs）。
// 用法：node tests/command_panels_shots.mjs
// 产出：docs/compose/command-panels-shots/*.html（截图源页，附说明头）
//   + docs/compose/command-panels-shots/*.png（chrome-headless-shell 实拍，需本机另跑
//   scripts/shots.sh；生成器只写 html，png 由 shell 脚本拍）。
// 口径：面板 HTML 由 workbench.js / mobile.js 的真实面板块渲染（与夹具同一抽取口径）；
//   数据 = 合同审计真实抓取 + Spec 附录 A 合成 payload（与夹具同一数据）；
//   样式 = 真实 workbench.css / mobile.css 内联；沙盒无法加载 Tailwind CDN，
//   故 Tailwind 工具类（p-4/text-sm/flex 等）不生效——布局比生产环境疏松，
//   内容/数值/颜色以真实 CSS 为准，此局限在报告与页头如实注明。
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

const FATE_PENDING = { fate: { boons: [{ key: "dao1", name: "道骨天成", from_tier: 2, chosen_at: 1794120908 }], pending: [{ candidates: [{ key: "k1", name: "剑心通明", desc: "剑道悟性大增", icon: "⚔" }], from_tier: 2 }], power_bonus: 1.1 } };
const BOARDS = { boards: [{ name: "realm", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 5100 }] }, { name: "power", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 63136.25 }] }] };
const DIRECTOR = { director: { last_run: 1794120908, stats: { runs: 1, accepted: 2, attempts: 1, rejected: 0 }, active: [{ type: "sect_tension", title: "敌门暗涌", narrative: "两宗相争。", expires_at: 1794124508 }] } };
const RECIPES = { recipes: [{ name: "聚气丹方", "产物": "聚气丹", "材料": ["聚灵草", "灵泉水"], "炉火": "文火", "成率": 0.8 }] };
const QUESTS = { quests: [{ npc: "小雀儿", realm: "练气期初期", "环数": 3, "赏": "灵石 100 + 功德 5", "首环": "寻得聚灵草一份" }] };
const MARKET = { status: { stones: 100015, vault: 0, market_listings: [{ name: "聚气丹", price: 40 }] } };

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
  return `<!DOCTYPE html><html lang="zh-CN" data-theme="${theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title><style>${css}
${TW_SHIM}
body{margin:0;padding:16px;font-family:system-ui,sans-serif;}
.shot-wrap{max-width:${width}px;margin:0 auto;}
.shot-note{font-size:12px;color:#666;margin:0 0 12px;line-height:1.6;}
.shot-item{margin-bottom:18px;}
.shot-echo{font-size:13px;font-weight:700;margin:0 0 6px;}
.shot-text{font-size:13px;line-height:1.7;white-space:pre-wrap;}
</style></head><body class="bg-paper-pattern"><div class="shot-wrap"><p class="shot-note">${note}</p>${items}</div></body></html>`;
}
const NOTE = "命令回复面板化 §8 截图源页：面板 HTML 由真实面板块渲染，数据为合同审计真实抓取 + Spec 附录 A 合成 payload；样式为真实 workbench.css / mobile.css 内联。沙盒无法加载 Tailwind CDN，故工具类由页内垫片实现面板实际用到的 4 个文字色类 + 2 个字号（色值取自 index.html tailwind.config / Tailwind 默认 slate 色板，不随货）；其余间距/布局类不生效，布局比生产环境疏松——内容/数值/颜色以真实 CSS 为准。";
function write(name, html) { fs.writeFileSync(path.join(OUT, name), html, "utf-8"); console.log("wrote", name, html.length + "B"); }

// ---- SC-P0：/profile + /look，双端 × 昼夜 ----
const p0 = [["/profile", cap("018-ro-profile")], ["/look", cap("002-ro-look")]];
for (const [theme, file] of [["light", "sc-p0-desktop-light.html"], ["dark", "sc-p0-desktop-dark.html"]]) {
  write(file, page({ title: "SC-P0 desktop " + theme, css: cssD, theme, width: 720,
    items: p0.map(([c, d]) => feedItem(c, desk.buildCommandPanel(c, d))).join(""), note: NOTE }));
}
for (const [theme, file] of [["light", "sc-p0-mobile-light.html"], ["dark", "sc-p0-mobile-dark.html"]]) {
  write(file, page({ title: "SC-P0 mobile " + theme, css: cssM, theme, width: 390,
    items: p0.map(([c, d]) => feedItem(c, mob.buildCommandPanel(c, d))).join(""), note: NOTE }));
}
// ---- 每波代表：P1 /世情 /图鉴 /榜；P2 /命格 /钱包 /天道导演；P3 /道统；附录 /配方 ----
const waves = [["/世情", cap("092-ro-世情")], ["/图鉴", cap("009-ro-图鉴")], ["/榜", BOARDS],
  ["/命格", FATE_PENDING], ["/钱包", cap("014-ro-wallet")], ["/天道", DIRECTOR],
  ["/道统", cap("005-ro-legacy")], ["/配方", RECIPES]];
write("sc-waves-desktop-light.html", page({ title: "SC-waves desktop light", css: cssD, theme: "light", width: 720,
  items: waves.map(([c, d]) => feedItem(c, desk.buildCommandPanel(c, d))).join(""), note: NOTE }));
write("sc-waves-desktop-dark.html", page({ title: "SC-waves desktop dark", css: cssD, theme: "dark", width: 720,
  items: waves.map(([c, d]) => feedItem(c, desk.buildCommandPanel(c, d))).join(""), note: NOTE }));
write("sc-waves-mobile-light.html", page({ title: "SC-waves mobile light", css: cssM, theme: "light", width: 390,
  items: waves.map(([c, d]) => feedItem(c, mob.buildCommandPanel(c, d))).join(""), note: NOTE }));
// ---- CP-46/47/48 移动端 ----
const advWin = { adventure: { combat_success: true, exp_delta: 120, stones_delta: -20, narrative: "深入古洞，得见玉简。", loot: ["聚灵草"] } };
const advLose = { adventure: { combat_success: false, exp_delta: 0, stones_delta: -50, narrative: "洞中妖气大盛，仓皇退走。", loot: [] } };
const advNone = { adventure: { combat_success: null, exp_delta: 10, stones_delta: 5, narrative: "一路无事，采得些许灵草。", loot: ["止血草"] } };
const digEquip = { equipment: { name: "九天避火佩", tier: 3, stats: { power: 198 } }, pill: null, stone_gain: 0, stone_loss: 40 };
const digPill = { equipment: null, pill: { name: "聚气丹", tier: 2 }, stone_gain: 0, stone_loss: 40 };
const digStones = { equipment: null, pill: null, stone_gain: 120, stone_loss: 40 };
const omen = { omen_title: "残碑悟道", omen_inline: true, omen_choices: [{ id: "1", label: "上前参悟" }, { id: "2", label: "抽身离去" }] };
write("sc-cp46-47-48-mobile-light.html", page({ title: "SC CP-46/47/48 mobile light", css: cssM, theme: "light", width: 390,
  items: [
    feedItem("/探险 落霞古洞（得胜）", mob.buildCommandPanel("/探险 落霞古洞", advWin)),
    feedItem("/探险 落霞古洞（落败）", mob.buildCommandPanel("/探险 落霞古洞", advLose)),
    feedItem("/探险 落霞古洞（无战）", mob.buildCommandPanel("/探险 落霞古洞", advNone)),
    feedItem("/挖宝（法宝）", mob.buildCommandPanel("/挖宝", digEquip)),
    feedItem("/挖宝（丹药）", mob.buildCommandPanel("/挖宝", digPill)),
    feedItem("/挖宝（灵石）", mob.buildCommandPanel("/挖宝", digStones)),
    `<div class="shot-item"><div class="shot-echo">» /望气（奇遇条选项芯片）</div><div class="shot-text">残碑悟道</div>${mob.buildOmenChipsM(omen) || ""}</div>`,
  ].join(""), note: NOTE }));
// ---- AC-10 空态：面板不触发，回落一行纯文本（真实抓取 text） ----
const emptyCases = [["/命格", cap("010-ro-命格")], ["/洞府", cap("076-ro-洞府")], ["/灵宠", cap("074-ro-灵宠")], ["/坊市", cap("057-ro-market")]];
write("sc-empty-desktop-light.html", page({ title: "SC empty desktop light", css: cssD, theme: "light", width: 720,
  items: emptyCases.map(([c, d]) => feedItem(c, desk.buildCommandPanel(c, d), (d.text || "").slice(0, 400))).join("")
    + feedItem("/委托（空）", desk.buildCommandPanel("/委托", { quests: [] }), "暂无委托。"), note: NOTE + " 空态口径 D6：行集为空时不出空卡，回落一行纯文本。" }));
console.log("done.");
