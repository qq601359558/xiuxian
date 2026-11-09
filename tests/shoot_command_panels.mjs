// command-panels §8 截图实拍（node tests/shoot_command_panels.mjs）。
// 用法：node tests/shoot_command_panels.mjs [--limit N] [--only <子串>]
//   对 docs/compose/command-panels-shots/*.html 全页实拍为同名 *.png。
//   桌面宽 1280、手机宽 390（§8 底线），deviceScaleFactor 1，全页高按内容实测。
// 实现：chrome-headless-shell + CDP（node 内置 fetch/WebSocket，零依赖）。
//   Chrome 选取：$CHROME_BIN > ms-playwright 的 chrome-headless-shell >
//   /opt/meta-chromium/chrome。拍完写 INVENTORY.md（每张 PNG 尺寸/字节）。
// 口径与生成器同（见 tests/command_panels_shots.mjs 头注释）：沙盒无法加载
//   Tailwind CDN，布局比生产环境疏松，内容/数值/颜色以真实 CSS 为准。
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn, execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "docs/compose/command-panels-shots");
const args = process.argv.slice(2);
const limitIdx = args.indexOf("--limit");
const LIMIT = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : Infinity;
const onlyIdx = args.indexOf("--only");
const ONLY = onlyIdx >= 0 ? args[onlyIdx + 1] : "";

function findChrome() {
  const cands = [
    process.env.CHROME_BIN,
    path.join(os.homedir(), ".cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell"),
    "/opt/meta-chromium/chrome",
  ].filter(Boolean);
  for (const c of cands) if (fs.existsSync(c)) return c;
  for (const bin of ["chrome-headless-shell", "chromium", "google-chrome"]) {
    try { const p = execSync(`which ${bin}`, { encoding: "utf-8" }).trim(); if (p) return p; } catch { /* next */ }
  }
  throw new Error("找不到 Chrome/chrome-headless-shell（可设 CHROME_BIN）");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitHttp(url, tries = 50) {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(url); if (r.ok) return await r.json(); } catch { /* retry */ }
    await sleep(200);
  }
  throw new Error("CDP 未就绪：" + url);
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  if (b.readUInt32BE(0) !== 0x89504e47) throw new Error(file + " 不是 PNG");
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), bytes: b.length };
}

async function main() {
  const chrome = findChrome();
  console.log("chrome:", chrome);
  const port = 9333;
  const child = spawn(chrome, [
    `--remote-debugging-port=${port}`, "--no-sandbox", "--disable-gpu",
    "--hide-scrollbars", "about:blank",
  ], { stdio: "ignore" });
  const inventory = [];
  try {
    await waitHttp(`http://127.0.0.1:${port}/json/version`);
    let files = fs.readdirSync(OUT).filter((f) => f.endsWith(".html")).sort();
    if (ONLY) files = files.filter((f) => f.includes(ONLY));
    files = files.slice(0, LIMIT);
    console.log(`${files.length} pages to shoot`);
    for (const file of files) {
      const width = file.includes("-desktop-") ? 1280 : 390;
      const url = "file://" + path.join(OUT, file);
      const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })).json();
      const ws = new WebSocket(target.webSocketDebuggerUrl);
      await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
      let id = 0;
      const pending = new Map();
      const send = (method, params) => new Promise((res, rej) => {
        const mid = ++id;
        pending.set(mid, { res, rej });
        ws.send(JSON.stringify({ id: mid, method, params: params || {} }));
      });
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.id && pending.has(msg.id)) {
          const { res, rej } = pending.get(msg.id);
          pending.delete(msg.id);
          if (msg.error) rej(new Error(JSON.stringify(msg.error))); else res(msg.result);
        }
      };
      try {
        await send("Page.enable");
        await sleep(300); // 等 CSS 内联渲染
        const { result } = await send("Runtime.evaluate", {
          expression: "JSON.stringify({h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth})",
          returnByValue: true,
        });
        const m = JSON.parse(result.value);
        if (m.overflowX) console.warn("WARN 横向溢出", file, "scrollWidth", m.w, "> viewport", width);
        const height = Math.min(Math.max(m.h, 200), 16000);
        await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width <= 390 });
        await sleep(120);
        const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width, height, scale: 1 } });
        const png = file.replace(/\.html$/, ".png");
        fs.writeFileSync(path.join(OUT, png), Buffer.from(shot.data, "base64"));
        const sz = pngSize(path.join(OUT, png));
        inventory.push([png, sz.w, sz.h, sz.bytes]);
        console.log("shot", png, `${sz.w}x${sz.h}`, sz.bytes + "B");
      } finally {
        ws.close();
        try { await fetch(`http://127.0.0.1:${port}/json/close/${target.id}`); } catch { /* ignore */ }
      }
    }
    const lines = ["# 命令回复面板化 §8 截图实拍清单（shoot_command_panels.mjs 产物）", "",
      "拍摄：chrome-headless-shell + CDP 全页实拍；桌面宽 1280、手机宽 390，deviceScaleFactor 1。",
      "口径与 MANIFEST.md 同：沙盒无法加载 Tailwind CDN，布局比生产环境疏松，内容/数值/颜色以真实 CSS 为准。", "",
      `共 ${inventory.length} 张 PNG。`, "", "| PNG | 宽 | 高 | 字节 |", "|---|---|---|---|"];
    for (const [f, w, h, b] of inventory) lines.push(`| ${f} | ${w} | ${h} | ${b} |`);
    fs.writeFileSync(path.join(OUT, "INVENTORY.md"), lines.join("\n") + "\n", "utf-8");
    console.log(`done. ${inventory.length} PNG, INVENTORY.md written`);
  } finally {
    child.kill("SIGKILL");
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
