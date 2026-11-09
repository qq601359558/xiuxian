// command-panels fixture harness (node).
// 用法：node tests/command_panels_fixture.mjs
// 从 web/workbench.js 与 web/mobile.js 抽取 == command-panels == 块，在 node 里
// 以桩 esc/fmtRemYears/fateThreadHtml 求值，对真实抓取响应 + 附录 A 合成
// payload 做渲染断言，并逐案比对双端探针（D2 同构）。
// 注意：fateThreadHtml / fateThreadHtmlM 是块外既有函数，此处以同语义小桩
// 代替（只验标题/章节/终局命题三探针）；其本体由既有 game-feel-phase2
// 测试覆盖。块内禁解析 data.text：静态扫描一并在此断言。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const fmtRemYears = (v) => (v == null ? "—" : Number(v).toFixed(1));
const remYearsUnit = (v) => (v == null ? "" : "载");
// 命途段小桩：与既有 fateThreadHtml/fateThreadHtmlM 同语义（标题/章节/终局命题）
function fateThreadShim(fate) {
  const th = fate && fate.thread;
  if (!th || typeof th !== "object") return "";
  const ch = (th.chapters || []).map((c) => `第${(c.idx != null ? c.idx : 0) + 1}章 ${c.title || ""}`).join(" ");
  const fp = th.final_proposition || {};
  return `<div class="panel">命途 · ${th.title || ""} ${ch} 终局命题：${fp.text || ""}</div>`;
}
function extract(file, retExpr, extra) {
  const src = fs.readFileSync(path.join(ROOT, file), "utf-8");
  const a = src.indexOf("== command-panels: begin ==");
  const b = src.indexOf("== command-panels: end ==");
  if (a < 0 || b < 0 || b <= a) throw new Error(file + ": panel block markers missing");
  const code = src.slice(src.lastIndexOf("\n", a) + 1, b);
  const fn = new Function("esc", "fmtRemYears", "remYearsUnit", "fateThreadHtml", "fateThreadHtmlM", code + "\nreturn " + retExpr + ";");
  return { block: code, api: fn(esc, fmtRemYears, remYearsUnit, fateThreadShim, fateThreadShim, ...(extra || [])) };
}
const desk = extract("web/workbench.js", "{ buildCommandPanel, CP_ALIASES, CP_BUILDERS }");
const mob = extract("web/mobile.js", "{ buildCommandPanel, buildOmenChipsM, CP_ALIASES_M, CP_BUILDERS_M }");

const strip = (h) => String(h || "").replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&")
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/\s+/g, " ").trim();

let pass = 0, fail = 0;
const failures = [];
function ok(cond, label, detail) {
  if (cond) { pass++; }
  else { fail++; failures.push(label + (detail ? " :: " + detail : "")); console.error("FAIL:", label, detail || ""); }
}
function check(id, cmd, data, probes, mode) {
  // mode: undefined=双端同探针；"empty"=双端皆 ""；"mobileOnly"=桌面 ""、移动含探针
  const d = desk.api.buildCommandPanel(cmd, data);
  const m = mob.api.buildCommandPanel(cmd, data);
  if (mode === "empty") {
    ok(d === "", id + " [desktop empty]", "got: " + strip(d).slice(0, 120));
    ok(m === "", id + " [mobile empty]", "got: " + strip(m).slice(0, 120));
    return;
  }
  if (mode === "mobileOnly") {
    ok(d === "", id + " [desktop empty]", "got: " + strip(d).slice(0, 120));
    ok(m !== "", id + " [mobile non-empty]");
    for (const p of probes) ok(strip(m).includes(p), id + " [mobile probe]", "missing: " + p + " | got: " + strip(m).slice(0, 200));
    return;
  }
  ok(d !== "", id + " [desktop non-empty]");
  ok(m !== "", id + " [mobile non-empty]");
  for (const p of probes) {
    ok(strip(d).includes(p), id + " [desktop probe]", "missing: " + p + " | got: " + strip(d).slice(0, 200));
    ok(strip(m).includes(p), id + " [mobile probe]", "missing: " + p + " | got: " + strip(m).slice(0, 200));
  }
}

// ---- 静态契约（§4-K2）：块内不得出现 data.text 解析 / 捏造源 ----
for (const [name, blk] of [["desktop", desk.block], ["mobile", mob.block]]) {
  for (const pat of ["data.text", ".text.split", ".text.match", "text.indexOf", "text.slice", "text.replace", "Math.random", "TODO", "FIXME"]) {
    ok(!blk.includes(pat), `K2 ${name} no ${pat}`);
  }
  ok(blk.includes("buildCommandPanel"), `K2 ${name} exports buildCommandPanel`);
}
// ---- 分发表对齐：桌面别名集 ⊆ 移动别名集（移动多 CP-46/47 两键）；builder 集一致 ----
{
  const dk = Object.keys(desk.api.CP_ALIASES), mk = Object.keys(mob.api.CP_ALIASES_M);
  for (const k of dk) ok(mk.includes(k), "alias parity " + k);
  ok(mk.filter((k) => !dk.includes(k)).sort().join(",") === "adventure,dig,挖宝,探险", "mobile-only aliases are adventure/dig");
  const db = Object.keys(desk.api.CP_BUILDERS).sort(), mb = Object.keys(mob.api.CP_BUILDERS_M).sort();
  for (const k of db) ok(mb.includes(k), "builder parity " + k);
  ok(mb.filter((k) => !db.includes(k)).sort().join(",") === "adventure,dig", "mobile-only builders are adventure/dig");
  for (const [mapName, map, builders] of [["desktop", desk.api.CP_ALIASES, desk.api.CP_BUILDERS], ["mobile", mob.api.CP_ALIASES_M, mob.api.CP_BUILDERS_M]]) {
    for (const [tok, id] of Object.entries(map)) ok(typeof builders[id] === "function", `${mapName} alias ${tok} -> builder ${id} exists`);
  }
}

// ---- 抓取加载 ----
function cap(slug) {
  const j = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/compose/contract-audit-captures", slug + ".json"), "utf-8"));
  return j.response;
}
const lookStatus = cap("002-ro-look").status;

// ---- 真实抓取响应（既有键面板）----
check("CP-01 profile", "/profile", cap("018-ro-profile"), ["个人信息", "审计员", "练气期初期", "70.4", "100000", "吐纳术", "近日账录", "散修"]);
check("CP-02 look", "/look", cap("002-ro-look"), ["观照", "70.4", "100000", "查看同场", "真灵根"]);
check("CP-03 here", "/here", cap("016-ro-here"), ["同场", "金满堂", "金丹期中期", "交谈", "斗法", "中立"]);
check("CP-05 goals", "/目标", cap("023-ro-goals"), ["世间目标", "先站稳脚跟", "进度 0"]);
check("CP-04 nearby", "/近况", cap("025-ro-近况"), ["近况", "世间", "出身牵命", "世间目标"]);
check("CP-20 help", "/帮助", cap("028-ro-帮助"), ["敕令目录", "观照与出入", "/look", "迁跃到指定地点"]);
check("CP-22 agenda", "/议程", cap("053-ro-agenda"), ["NPC 议程", "玄清子", "进度 0/5"]);
check("CP-18 fate_thread", "/命途", cap("011-ro-命途"), ["出身牵命", "千里访旧", "终局命题"]);
check("CP-27 fate-empty", "/命格", cap("010-ro-命格"), [], "empty");
check("CP-52 wallet", "/钱包", cap("014-ro-wallet"), ["账户钱包", "0 灵石", "钱包提取"]);
check("CP-63 legacy", "/道统", cap("005-ro-legacy"), ["道统", "出身灵石", "1 点", "道统点"]);
check("CP-45 ailog", "/AI日志", cap("026-ro-ailog"), ["AI 调用日志", "midplatform", "fail"]);
check("CP-44 ai", "/ai", cap("027-ro-ai"), ["AI 自检", "deepseek-chat", "ai_channel_configured", "✓", "✗"]);
check("CP-34 scan", "/探查", cap("158-scan"), ["神识探查", "苏婉清", "其余 15 条"]);
check("CP-26 createart", "/自创功法 测试", cap("156-create-art"), ["自创功法", "残卷·测试", "人品", "×1.2", "纯阳测试印"]);
check("CP-09 world", "/世情", cap("092-ro-世情"), ["世情", "天道导演", "世界弧", "势力格局", "望气·血煞", "纪元回流", "秘境开启", "NPC 动向"]);
check("CP-06 tasks", "/任务", cap("218-tasks"), ["任务", "初玩教学", "已完成 1 步"]);
check("CP-13 gallery", "/图鉴", cap("009-ro-图鉴"), ["天道图鉴", "6/139", "查看完整图鉴"]);
check("CP-12 arts", "/功法", { arts: [], status: lookStatus}, ["功法", "吐纳术"]);
check("CP-51 mindart", "/心法", cap("075-ro-心法"), ["心法槽位", "主修", "（空）", "吐纳术"]);
check("CP-50 cave-empty", "/洞府", cap("076-ro-洞府"), [], "empty");
check("CP-50 cave-open", "/洞府", { status: { cave: { level: 2, plots_total: 4, plots_used: 3, mature: 1}}}, ["洞府灵田", "2 级", "3/4"]);
check("CP-49 pet-empty", "/灵宠", cap("074-ro-灵宠"), [], "empty");
check("CP-43 apocalypse", "/大劫", cap("162-apocalypse"), ["大劫", "第 1 纪", "84"]);
check("CP-14 market-nostatus", "/坊市", cap("057-ro-market"), [], "empty");
check("CP-14 market", "/坊市", { status: { stones: 100015, vault: 0, market_listings: [{ name: "聚气丹", price: 40}]}}, ["坊市", "100015", "查看完整坊市"]);
// ---- 后端键未落地时回落纯文本（空态口径 D6；非捏造）----
for (const [id, cmd, slug] of [
["CP-07 rank-nokey", "/榜", "047-ro-rank"], ["CP-08 secret-nokey", "/秘境", "066-ro-secret"],
["CP-10 clue-nokey", "/寻宝", "012-ro-寻宝"], ["CP-11 spirit-nokey", "/器灵", "013-ro-器灵"],
["CP-19 map-nokey", "/宝图", "045-ro-map"], ["CP-15 auction-nokey", "/拍卖行", "122-auction-board"],
["CP-16 hunt-nokey", "/除凶", "083-ro-除凶"], ["CP-30 faction-nokey", "/势力", "093-ro-势力"],
["CP-31 sectorder-nokey", "/宗门令", "081-ro-宗门令"], ["CP-32 sectpower-nokey", "/宗门势", "070-ro-宗门势"],
["CP-33 contribution-nokey", "/贡献", "072-ro-贡献"], ["CP-33 redeem-nokey", "/兑换", "073-ro-兑换"],
["CP-21 who-nokey", "/who", "022-ro-who"], ["CP-24 heaven-nokey", "/天道", "163-heaven"],
["CP-25 arcs-nokey", "/世界弧", "091-ro-世界弧"], ["CP-29 links-nokey", "/因果", "043-ro-links"],
["CP-36 channel-nokey", "/频道", "037-ro-channel"], ["CP-37 legend-nokey", "/传说", "041-ro-legend"],
["CP-38 era-nokey", "/纪元回流", "094-ro-纪元回流"], ["CP-39 trade-nokey", "/交易", "202-trade-init"],
["CP-40 sectquests-nokey", "/师门任务", "236-sect-quests"], ["CP-41 mingwu-nokey", "/名物", "219-mingwu"],
["CP-53 prices-nokey", "/行情", "059-ro-行情"], ["CP-54 atlas-nokey", "/版图", "060-ro-atlas"],
["CP-55 tombstone-nokey", "/墓碑 审计员", "007-ro-墓碑"], ["CP-56 chains-nokey", "/因果链", "008-ro-因果链"],
["CP-57 quests-nokey", "/委托", "077-ro-委托"], ["CP-58 promises-nokey", "/诺言", "078-ro-诺言"],
["CP-62 ascend-nokey", "/飞升榜", "049-ro-ascend"], ["CP-65 council-nokey", "/议政", "082-ro-议政"],
["CP-66 sworn-nokey", "/结义任务", "238-sworn-quests"], ["CP-35 npcgoods-nokey", "/npc货单", "198-npc-goods-noargs"],
["CP-28 respond-nokey", "/回应", "214-respond-drama-no-drama"],
]) check(id, cmd, cap(slug), [], "empty");
check("CP-c-class", "/闭关 1", { ok: true, text: "闭关收据"}, [], "empty");
check("CP-unknown", "/购买 聚气丹", { ok: true, text: "收据"}, [], "empty");

// ---- 附录 A 合成 payload（后端键形态；集成联调时以后端真实响应复核）----
check("CP-07 rank", "/榜", { boards: [{ name: "realm", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 5100}]}, { name: "power", rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 63136.25}]}]}, ["天道榜单", "境界榜", "幽冥老祖", "5100", "63136.25"]);
check("CP-07 rank-single", "/榜 战力", { board_rows: [{ rank: 1, name: "幽冥老祖", realm: "化神期中期", sect: "九幽天魔宗", is_npc: true, score: 63136.25}]}, ["榜单", "幽冥老祖", "63136.25"]);
check("CP-08 secret", "/秘境", { realms: [{ name: "落霞古洞", location: "落霞山灵泉", "门槛": "境界 1+", "危险%": 35, "状态": "已开启", "描述": "残破古洞"}]}, ["秘境天机", "落霞古洞", "危险 35%", "已开启"]);
check("CP-10 clue", "/寻宝", { clue: { chain: "古图·坎水", current_step: { title: "东行三里", text: "向东行三里，见枯井。"}, options: [{ key: "east", label: "向东"}, { key: "west", label: "向西"}]}}, ["寻宝", "古图·坎水", "东行三里", "向东"]);
check("CP-11 spirit", "/器灵", { spirit: { item: { name: "九天避火佩", tier: 3}, "成长": 12, "状态": "苏醒", "可唤灵列表": [{ name: "火灵"}]}}, ["器灵", "九天避火佩", "唤灵", "温养"]);
check("CP-15 auction", "/拍卖行", { auction: { lots: [{ id: "8c12f579", name: "审计试剑", "当前价": 100, "起拍": 100, "领先": "", "剩余": "120 分", "挂单人": "审计员"}]}}, ["拍卖行", "审计试剑", "100 灵石"]);
check("CP-16 hunt", "/除凶", { hunt: [{ name: "幽冥老祖", realm: "化神期中期", "血煞": true, "业力": 500, "地点": "九幽天魔宗坛", "被盯人数": 0}]}, ["除凶榜", "幽冥老祖", "业力 500"]);
check("CP-17 sect", "/宗门", { sects: [{ name: "青云宗", alias: "青云", "人数": 9, "月俸": 50, "门槛": "道心≥30", "高层": ["玄清子"], "总坛": "青云峰"}], status: { sect: "散修", rank: "散修"}}, ["天下仙门", "青云宗", "月俸 50"]);
check("CP-19 map", "/宝图", { treasure_map: { name: "古图·坎水", tier: 3, bagua: "坎", coords: "东三里", riddle: "枯井之下有玄光。", clue: "井边三尺", target_node: "落霞古洞", archetype: "解谜"}}, ["宝图研读", "古图·坎水", "坎", "枯井之下有玄光"]);
check("CP-21 who", "/who", { who: { groups: [{ place: "青云坊市客栈", members: [{ name: "金满堂", realm: "金丹期中期"}]}]}}, ["天下名录", "青云坊市客栈", "金满堂"]);
check("CP-23 bounty", "/告示", { bounties: [{ id: 1, target: "血衣侯", "赏金": 500, "缘由": "血煞缠身", "匿": false}]}, ["悬赏告示", "血衣侯", "赏金 500"]);
check("CP-24 heaven", "/天道", { director: { last_run: 1794120908, stats: { runs: 1, accepted: 2, attempts: 1, rejected: 0}, active: [{ type: "sect_tension", title: "敌门暗涌", narrative: "两宗相争。", expires_at: 1794124508}]}}, ["天道导演", "提案 1", "敌门暗涌"]);
check("CP-25 arcs", "/世界弧", { arcs: { "累计": { started: 2, upgraded: 0, resolved: 0}, "弧": [{ title: "敌门暗涌", stage: "prophesy", stage_deadline: 1794121808}], "近史": ["起弧·敌门暗涌"], "弧修饰": "热度地=落霞山灵泉"}}, ["世界弧", "预兆", "起弧 2", "敌门暗涌"]);
check("CP-27 fate-pending", "/命格", { fate: { boons: [{ key: "dao1", name: "道骨天成", from_tier: 2, chosen_at: 1794120908}], pending: [{ candidates: [{ key: "k1", name: "剑心通明", desc: "剑道悟性大增", icon: "⚔"}], from_tier: 2}], power_bonus: 1.1}}, ["命格", "道骨天成", "剑心通明", "择 剑心通明", "×1.1"]);
check("CP-28 respond", "/回应", { drama_pending: [{ id: "dr_1", npc_name: "铁算盘", text: "旧怨未消，今日便要讨个说法！", options: [{ key: "fight", label: "应战"}, { key: "avoid", label: "避走"}]}]}, ["待回应之事", "铁算盘", "应战"]);
check("CP-29 links", "/因果", { links: [{ kind: "仇", "名": "铁算盘", "强度": 1, "缘由": "出身旧怨：背案在身"}]}, ["因果牵缠", "铁算盘", "强度 1"]);
check("CP-30 faction", "/势力", { factions: { relations: [{ a: "九幽天魔宗", b: "青云宗", status: "hostile", score: -67, note: "天道导演·宗门紧张"}], orders: [], sieges: []}}, ["天下势力", "敌对", "−67"]);
check("CP-31 sectorder", "/宗门令", { sect_orders: [{ sect: "青云宗", id: "f_c72a58e8", "内容": "抵制九幽天魔宗", "贡献": 5}]}, ["宗门令", "抵制九幽天魔宗", "贡献 +5"]);
check("CP-32 sectpower", "/宗门势", { sect_power: { rows: [{ "宗门": "青云宗", "人数": 9, "分": 39}], hostile: [["九幽天魔宗", "青云宗"]]}}, ["宗门实力", "青云宗", "分 39"]);
check("CP-33 contribution", "/贡献", { contribution: { sect: "散修", points: 0, catalog: [{ name: "聚气丹", cost: 8}, { name: "玄元聚气丹", cost: 80, "需连环": 3}]}}, ["宗门贡献", "聚气丹", "8 贡献", "需连环≥3"]);
check("CP-33 redeem-args", "/兑换 聚气丹", { contribution: { sect: "散修", points: 0, catalog: [{ name: "聚气丹", cost: 8}]}}, [], "empty");
check("CP-35 npcgoods", "/npc货单 金满堂", { npc_goods: [{ name: "聚气丹", price: 40, "描述": "行气丹药"}]}, ["NPC 货单", "聚气丹", "40 灵石"]);
check("CP-36 channel", "/频道", { channel: [{ severity: 2, type: "天象", text: "天象沉静如水。"}]}, ["世界频道", "天象", "★★"]);
check("CP-37 legend", "/传说", { legends: { "近史": ["大劫之后自有记载"], "活跃权重": "暂无", "引用累计": 0}}, ["传说", "引用累计", "0"]);
check("CP-38 era", "/纪元回流", { era_flow: { "上次回流": "11-08 06:55", "活跃权重": "暂无", "近传说": [], "引用累计": 0}}, ["纪元回流", "上次回流", "引用累计"]);
check("CP-39 trade", "/交易", { trade: { partner: "审计员乙", status: "等待报价", offers: { me: { stones: 100, items: ["聚气丹"]}, partner: { stones: 0, items: []}}}}, ["当面交易", "审计员乙", "同意成交", "拒绝"]);
check("CP-40 sectquests", "/师门任务", { sect_quests: [{ title: "洒扫山门", desc: "洒扫外门三日"}]}, ["师门任务", "洒扫山门"]);
check("CP-41 mingwu", "/名物", { relics: [{ name: "轩辕剑", "线索": "传闻在剑冢"}]}, ["名物", "轩辕剑"]);
check("CP-42 sectring", "/宗门环", { status: { sect_ring: { day: "甲子日", accepted: false, done: false, themes: [{ id: 1, label: "洒扫", lore: "洒扫山门", need_item: "", need_streak: 0}]}}}, ["宗门环", "洒扫", "接取此环"]);
check("CP-49 pet", "/灵宠", { pets: [{ name: "青鳞蟒", "种": "蟒", "境界": "练气期", "状态": "温顺", "出战": false, "成长": 5}], status: { pets_count: 1}}, ["灵宠", "青鳞蟒", "出战"]);
check("CP-53 prices", "/行情", { prices: { as_of: "2026-11-08", regions: [{ name: "东荒·青州", rows: [{ name: "灵谷种子", "买入": 10, "回收": 5, "产地系数": 0}]}]}}, ["天下行情", "东荒·青州", "灵谷种子", "买 10"]);
check("CP-54 atlas", "/版图", { atlas: [{ region: "东荒·青州", "主导": "无主", "本宗声威": 0}]}, ["天下版图", "东荒·青州", "无主"]);
check("CP-55 tombstone", "/墓碑 审计员", { tombstone: { name: "审计员", realm: "练气期初期", cause: "渡劫陨落", points: 3, "评语": "谨慎求生，终归尘土。"}}, ["墓碑", "审计员", "道统点", "谨慎求生"]);
check("CP-56 chains", "/因果链", { karma_chains: [{ kind: "血仇", "对方": "铁算盘", "发酵进度": 0.5, "近史": ["旧怨"], "上限": 120}]}, ["因果链", "铁算盘", "血仇", "50%"]);
check("CP-57 quests", "/委托", { quests: [{ npc: "小雀儿", realm: "练气期初期", "环数": 3, "赏": "灵石 100 + 功德 5", "首环": "寻得聚灵草一份"}]}, ["NPC 委托", "小雀儿", "3 环", "接取委托"]);
check("CP-58 promises", "/诺言", { promises: [{ "对象": "金满堂", "类型": "赠物", "内容": "赠聚气丹一枚", "状态": "未结", "期限": 1794124508}]}, ["诺言账", "金满堂", "赠物"]);
check("CP-59 recipes", "/配方", { recipes: [{ name: "聚气丹方", kind: "丹药", "产物": "聚气丹", "材料": ["聚灵草", "灵谷"], "炉火": "文火", "成率": 0.8, "境界足": true}]}, ["配方", "聚气丹方", "成率 80%"]);
check("CP-60 bodysoul", "/炼体", { body_soul_detail: { body: { level: 0, "成效": "斗法战力 +0%", "下一层成本": "妖兽内丹×1 + 灵石 20"}, soul: { level: 0, "成效": "神识 +0", "下一层成本": "灵石 20"}}}, ["炼体 · 炼神", "炼体", "炼神", "下一层成本"]);
check("CP-61 demon", "/镇魔", { demon: { stage_name: "蛰伏", "魔念": 0, "来源": "业力 20、血煞缠身", "镇压选项": ["服丹", "静坐"]}}, ["镇魔", "蛰伏", "魔念"]);
check("CP-62 ascend", "/飞升榜", { ascend: [{ name: "剑圣·独孤败", realm: "化神期初期", cause: "飞升", "纪元": "第 1 纪"}]}, ["飞升榜", "剑圣·独孤败"]);
check("CP-64 recipe", "/悟丹 测试", { recipe: { name: "残卷·测试丹", kind: "丹药", "产物": "测试丹", "材料": ["聚灵草"], "炉火": "文火", "成率": 0.9}}, ["新方", "残卷·测试丹", "成率 90%"]);
check("CP-65 council", "/议政", { council: [{ title: "开山门", text: "是否开山收徒", status: "表决中"}]}, ["宗门议政", "开山门"]);
check("CP-66 swornquests", "/结义任务", { sworn_quests: [{ title: "巡山", desc: "同巡山门"}]}, ["结义任务", "巡山"]);
// ---- 缺失显 "—"、零值显 0（D6；不得以假缺省掩盖）----
{
const d = desk.api.buildCommandPanel("/profile", { profile: { name: "试剑", realm: "练气期初期", rem_years: null, stones: 0, merit: null, dao_heart: 0, skills: [], recent: []}});
const m = mob.api.buildCommandPanel("/profile", { profile: { name: "试剑", realm: "练气期初期", rem_years: null, stones: 0, merit: null, dao_heart: 0, skills: [], recent: []}});
for (const [nm, h] of [["desktop", d], ["mobile", m]]) {
const t = strip(h);
ok(t.includes("试剑"), "D6 " + nm + " name");
ok(t.includes("—"), "D6 " + nm + " missing shows —", t.slice(0, 200));
ok(t.includes("0 灵石"), "D6 " + nm + " zero stones shows 0", t.slice(0, 200));
ok(!t.includes("3650"), "D6 " + nm + " no fake default 3650");
}
}
// ---- 移动补齐 CP-46 /探险、CP-47 /挖宝（桌面已有 dialog，本轮移动 feed 卡）----
check("CP-46 adventure", "/探险 落霞古洞", { adventure: { combat_success: true, exp_delta: 120, stones_delta: -20, narrative: "深入古洞，得见玉简。", loot: ["聚灵草"]}}, ["探险 · 落霞古洞", "得胜", "+120", "聚灵草"], "mobileOnly");
check("CP-47 dig", "/挖宝", { equipment: { name: "九天避火佩", tier: 3, stats: { power: 198}}, pill: null, stone_gain: 0, stone_loss: 40}, ["挖宝", "九天避火佩", "攻伐 +198", "−40"], "mobileOnly");
{
const omen = { omen_title: "残碑悟道", omen_inline: true, omen_choices: [{ id: "1", label: "上前参悟"}, { id: "2", label: "抽身离去"}]};
const h = mob.api.buildOmenChipsM(omen);
const t = strip(h);
ok(t.includes("残碑悟道") && t.includes("上前参悟") && h.includes('data-cmd="/奇遇 1"'), "CP-48 omen chips", t.slice(0, 200));
ok(desk.api.buildCommandPanel("/奇遇", omen) === "", "CP-48 desktop /奇遇 stays inline bar (no panel)");
ok(mob.api.buildCommandPanel("/奇遇", omen) === "", "CP-48 mobile /奇遇 no panel (chips are separate)");
}

// ---- 真实后端形态回归（2026-11-09 联调；真实 payload 驱动，非附录 A 合成键形）----
// 根因：前端按附录 A 展示键写映射，后端按 §4-K8 模型字段出键；以下用真实键形锁定映射。
const nowSec = Math.floor(Date.now() / 1000);
const liveCases = [
["live hunt", "/除凶", { hunt: [{ name: "血煞散修", realm: "筑基期中期", mark: "血煞", sin: 500, location: "黑水沼泽", is_npc: true, hunters: 0}]}, ["除凶榜", "血煞", "业力 500", "被 0 人盯上"]],
["live sect", "/宗门", { sects: [{ name: "青云宗", alignment: "正道", members: 120, players: 3, monthly_salary: 25, headquarters: "青云宗外门山门", rules_tip: "门规森严", top: [{ name: "玄清子", rank: "掌门", realm: "元婴期"}]}]}, ["天下仙门", "月俸 25", "玄清子", "青云宗外门山门"]],
["live bounty", "/告示", { bounties: [{ id: "b1", target: "悬赏测试丁", reward: 100, status: "OPEN", status_cn: "待猎", issuer: "联调客", anonymous: false, reason: "面板测试"}]}, ["悬赏告示", "赏金 100", "待猎"]],
["live sectorder", "/宗门令", { sect_orders: [{ id: "o1", sect: "青云宗", title: "巡山", kind: "patrol", reward_contrib: 8}]}, ["宗门令", "巡山", "贡献 +8"]],
["live sectpower", "/宗门势", { sect_power: { sects: [{ sect: "青云宗", members: 120, score: 46.8}], hostile_pairs: [["青云宗", "九幽天魔宗"]], tense_pairs: [], sieges: [], open_missions: 2}}, ["宗门实力", "青云宗", "分 46.8", "敌对"]],
["live trade", "/交易", { trade: { partner: "联调客", location: "青云坊市客栈", status: "OPEN", created_at: nowSec, a: { name: "联调客", stones: 10, items: [], agreed: false}, b: { name: "联调交易乙", stones: 0, items: [], agreed: false}}}, ["当面交易", "进行中", "灵石 10"]],
["live sectquests", "/师门任务", { sect_quests: { master: "联调师父", task: { id: "sq1", label: "巡山", need_visit: "青云宗外门山门"}, done: false}}, ["师门任务", "联调师父", "巡山", "进行中"]],
["live council", "/议政", { council: { sect: "青云宗", session_no: 1, vault: 1000, prestige: 50, morale: 50, topic: { id: "mining", name: "开矿增收", desc: "开矿增收描述"}, settled: false, closes_in_s: 6985, seats: [{ name: "丹霞子", rank: "长老", stance: "support", stance_cn: "支持", lobbied: false, virtual: false, line: "老夫赞成。"}], votes: { support: 0, oppose: 0, mine: null}}}, ["宗门议政", "开矿增收", "丹霞子", "支持 0"]],
["live swornquests", "/结义任务", { sworn_quests: { partner: "联调结义乙", task: { id: "sw1", label: "历练", need_visit: "落霞古洞"}, done: false}}, ["结义任务", "联调结义乙", "历练"]],
["live quests", "/委托", { quests: { active: { publisher: "凶名测试丁", publisher_id: "u1", rings_total: 4, ring_index: 0, ring: { kind: "slay", kind_cn: "除妖", desc: "剿除妖兽", progress: 0, need: 1, deliver_npc_name: "凶名测试丁", item_name: null}, reward_stones: 130, reward_merit: 5, expires_in_s: 86399}, offers: [{ npc: "凶名测试丁", realm: "练气期初期", rings: 4, reward_stones: 130, reward_merit: 5, first_ring: { kind: "fetch", kind_cn: "寻物", desc: "寻聚灵草"}}]}}, ["NPC 委托", "凶名测试丁", "第 1/4 环", "灵石 130"]],
["live legend", "/传说", { legends: { legends: [{ title: "联调史笔", text: "联调传说文本", season: 1, actor: "联调客", weight: 1}], total: 2, active_bias: {}}}, ["传说", "联调史笔", "收录 2"]],
["live era", "/纪元回流", { era_flow: { current_season: 1, last_reentry_ts: 1794187092, active_bias: {}, anchors: [], completed_eras: [], cited_count: 0}}, ["纪元回流", "第 1 纪", "引用累计 0"]],
["live clue", "/寻宝", { clue: { map_name: "古修遗图", chain_status: "active", current_step: 1, total_steps: 2, current: { kind: "guard", kind_cn: "守卫", node_name: "黑水沼泽", riddle: "何物无声却传千里？", options: []}, can_abandon: true}}, ["寻宝", "古修遗图", "第 1/2 步", "黑水沼泽"]],
["live spirit", "/器灵", { spirit: { items: [{ name: "联调剑", tier: 5, tier_name: "天品", spirit: null, can_awaken: true}], awakenable: ["联调剑"]}}, ["器灵", "联调剑", "天品", "可唤灵"]],
["live auction", "/拍卖行", { auction: { lots: [{ id: "a1", name: "聚气丹", start_price: 100, current_price: 100, leader: "（暂无）", seller: "联调客", buyout_price: 500, remaining_s: 7199, bid_count: 0, status: "OPEN"}]}}, ["拍卖行", "聚气丹", "当前 100", "约 2 小时"]],
["live mingwu", "/名物", { relics: [{ name: "联调名物", type: "丹药", status: "known", desc: "联调名物描述", source: "联调", confidence: 1}]}, ["名物", "联调名物", "丹药", "联调名物描述"]],
["live chains", "/因果链", { karma_chains: [{ kind: "en", kind_cn: "恩", status: "fermenting", status_cn: "发酵", counterparty: "联调因果", origin: "联调", strength: 7, elapsed_days: 1, total_days: 9, ferment_pct: 11, direction: "对象念恩"}]}, ["因果链", "联调因果", "恩", "11%"]],
["live promises", "/诺言", { promises: [{ bucket: "我立之诺", desc: "3 日内赠", kind: "gift", promiser: "联调客", promisee: "联调诺言", status: "ACTIVE", left_s: 259200, deadline: nowSec + 259200, settle_note: ""}]}, ["诺言账", "联调诺言", "赠物", "进行中"]],
["live recipes", "/配方", { recipes: [{ id: "r1", name: "聚气丹方", kind: "pill", output: "聚气丹", materials: { "百年灵芝": 1, "聚灵草": 2}, stones_fee: 15, base_rate: 0.83, rate: 0.83, req_tier: 1, tier_ok: true, can_craft: true}]}, ["配方", "聚气丹方", "聚气丹", "百年灵芝×1", "炉火 15灵", "成率 83%"]],
["live recipe64", "/悟丹 随机", { recipe: { id: "rx1", name: "止血散方", output_pill: "止血散", output: "止血散", kind: "pill", materials: { "止血灵叶": 3}, stones_fee: 8, desc: "止血散方", base_rate: 0.9}}, ["新方", "止血散方", "止血散", "止血灵叶×3", "炉火 8灵", "成率 90%"]],
["live bodysoul", "/炼体", { body_soul_detail: { body: { track: "body", track_cn: "炼体", level: 2, cap: 10, effect: "气血+10", next_cost: { item: "妖兽内丹", item_count: 1, stones: 20, have_item: 0, have_stones: 5015}, other_level: 1}, soul: { track: "soul", track_cn: "炼神", level: 1, cap: 10, effect: "神识+5", next_cost: { item: "百年灵芝", item_count: 1, stones: 10, have_item: 0, have_stones: 5015}, other_level: 2}}}, ["炼体 · 炼神", "妖兽内丹×1", "灵石 20"]],
["live demon", "/镇魔", { demon: { stage: 2, stage_name: "滋长", seed: 50.0, seed_cap: 90.0, sin: 0, blood_marked: false, eff_dao_heart: 100, suppress_mult: 0.25, eruption: { breakthrough_pct: 0.35, meditation_pct: 0.25}, options: [{ kind: "pill", item: "百年灵芝", count: 1, stones: 30, seed_delta: 35.0}, { kind: "calm", min_dao: 50, cooldown_h: 20, seed_delta: 20.0}]}}, ["镇魔", "滋长", "魔念 50", "百年灵芝", "静坐"]],
["live ascend", "/飞升榜", { ascend: [{ user_id: "u1", name: "飞升测试故人", realm: "元婴期", tier: 5, sub_tier: 0, cause: "天劫陨落", cause_category: "tribulation", lifespan_lived: 210, points_gained: 100, died_at: 1794100463, season: 1, score: 4355.0, rank: 1}]}, ["飞升榜", "飞升测试故人", "分 4355"]],
["live heaven", "/天道", { director: { last_run_ts: 1794187092, last_trigger: "tick", last_source: "local", last_error: null, stats: { runs: 60, accepted: 3, rejected: 0, attempts: 60}, active: [{ type: "sect_tension", title: "敌门暗涌", location: "青云宗", expires_in_s: 3180, narrative: "测试叙事", applied: {}}]}}, ["天道导演", "敌门暗涌", "约 53 分"]],
["live arcs", "/世界弧", { arcs: { stats: { spawned: 2, advanced: 0, climaxed: 0}, arcs: [{ id: "a1", kind: "sect_crisis", title: "敌门暗涌·青云宗×九幽天魔宗", location: "青云宗", stage: "prophesy", stage_cn: "预兆", deadline_in_s: 480, last_log: ""}], history: ["1794186677|spawn|sect_crisis|敌门暗涌·青云宗×九幽天魔宗|a_499025f6"], modifiers: { heat_by_location: { "落霞山灵泉": 1.2}, blood_tide_locations: [], sect_tensions: [["青云宗", "九幽天魔宗"]], realm_pressure_ids: [], calamity_forecast: {}, hunt_heat: {}, active_arc_kinds: ["sect_crisis"], n_arcs: 2}}}, ["世界弧", "起弧 2", "敌门暗涌", "在弧 2"]],
["live prices", "/行情", { prices: { as_of: "2026-11-09", current_region: "青云坊市", regions: [{ name: "青云坊市", current: true, rows: [{ name: "灵谷种子", kind: "seed", price: 10, sell_price: 5, base_price: 10, origin: "青云坊市", factor: 1.0, desc: ""}]}]}}, ["天下行情", "灵谷种子", "买 10", "回 5"]],
["live atlas", "/版图", { atlas: [{ region: "青云坊市", dominant: "青云宗", dominant_value: 120.0, mine: "青云宗", influence: {}}]}, ["天下版图", "主导 青云宗", "本宗声威 青云宗"]],
["live pet", "/灵宠", { pets: [{ name: "青鳞蟒", species: "蟒", tendency: "水", level: 3, growth: 250, intimacy: 42, state: "出战中"}]}, ["灵宠", "青鳞蟒", "3 级", "出战中"]],
["live channel", "/频道", { channel: [{ severity: "major", type: "bond", text: "联调频道探针消息", actor: "联调客", location: "青云坊市客栈", ts: 1794187095}]}, ["世界频道", "★★"]],
["live links", "/关系", { links: [{ kind: "gratitude", name: "联调牵缠", strength: 30, note: "联调测试牵缠"}]}, ["因果牵缠", "联调牵缠", "联调测试牵缠"]],
["live secret", "/秘境", { realms: [{ id: "r1", name: "落霞古洞", location: "落霞山灵泉", desc: "残破古洞", min_tier: 1, danger: 0.35, is_open: true, remain_hours: 72}]}, ["秘境天机", "落霞古洞", "危险 35%", "已开启"]],
["live faction", "/势力", { factions: { relations: [], orders: [{ id: "f1", sect: "青云宗", title: "巡山", kind: "patrol", reward_contrib: 5}], sieges: [], stats: {}}}, ["天下势力", "宗门令", "巡山", "贡献 +5"]],
];
for (const [id, cmd, data, probes] of liveCases) check(id, cmd, data, probes);
// 真实形态渲染不得泄漏 [object Object] / undefined / NaN
for (const [id, cmd, data] of liveCases) {
for (const [nm, h] of [["desktop", desk.api.buildCommandPanel(cmd, data)], ["mobile", mob.api.buildCommandPanel(cmd, data)]]) {
const t = strip(h);
for (const bad of ["[object Object]", "undefined", "NaN"]) ok(!t.includes(bad), id + " [" + nm + " no " + bad + "]", t.slice(0, 200));
}
}

console.log(`\ncommand-panels fixture: ${pass} passed, ${fail} failed`);
if (fail) { console.error("failures:\n" + failures.join("\n")); process.exit(1);}
