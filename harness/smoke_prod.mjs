/** 本番検品(HC-148 / HC-048 / T-037)。
 *
 *   node harness/smoke_prod.mjs https://<本番>.vercel.app
 *
 * **最初に刻印を見る。** 本番検品は「健やかか」しか答えない。デプロイが上限で
 * 失敗しても前の版が健やかに配られ続けるので、健やかさの項目をいくら並べても
 * 反映の有無は分からない(mondo-atlas で古い本番に全項目合格を返した)。
 * 手元の木から計算した刻印と本番の `build-stamp.json` が違えば、**他を一切見ずに止める。**
 *
 * そのあとで、ローカルの出荷物検査では原理的に見えないものを本番に当てて測る:
 *   - 配信の Content-Type(静的配信は拡張子から MIME を推測する)
 *   - フッタの宛先が実際に引けるか(リポジトリを作る前に書いたリンクは 404 になる)
 *   - 地図が本番のタイル配信で描けるか
 */
import { chromium } from "playwright";

import { computeStamp } from "../scripts/build_stamp.mjs";

const base = (process.argv[2] || "").replace(/\/+$/, "");
if (!/^https:\/\//.test(base)) {
  console.error("使い方: node harness/smoke_prod.mjs https://<本番>.vercel.app");
  process.exit(2);
}

const failures = [];
const notes = [];
function check(ok, label, detail = "") {
  if (ok) notes.push(`  OK   ${label}`);
  else failures.push(`  NG   ${label}${detail ? ` — ${detail}` : ""}`);
  return ok;
}

async function get(url) {
  const bust = `${url}${url.includes("?") ? "&" : "?"}_=${Date.now()}`;
  return fetch(bust, { redirect: "follow", headers: { "cache-control": "no-cache" } });
}

// --- 1. 刻印 ------------------------------------------------------------------
const local = computeStamp();
let remote = null;
try {
  const r = await get(`${base}/build-stamp.json`);
  if (r.ok) remote = await r.json();
} catch {
  remote = null;
}
if (!remote || remote.stamp !== local.stamp) {
  console.error("本番は手元の版ではない。他を見ずに止める。");
  console.error(`  手元 ${local.stamp}(${local.count} ファイル)`);
  console.error(`  本番 ${remote ? `${remote.stamp}(${remote.count} ファイル・${remote.generated_at})` : "build-stamp.json を引けない"}`);
  process.exit(3);
}
notes.push(`  OK   刻印が手元と一致 ${local.stamp}(${local.count} ファイル)`);

// --- 2. 配信の中身と Content-Type -------------------------------------------
const PAGES = ["/", "/map/", "/ghg/", "/patterns/", "/compare/", "/about/", "/data-policy/"];
for (const p of PAGES) {
  const r = await get(`${base}${p}`);
  check(r.status === 200, `${p} が 200`, `HTTP ${r.status}`);
  check((r.headers.get("content-type") || "").includes("text/html"),
    `${p} が text/html`, r.headers.get("content-type") || "なし");
}

for (const p of ["/data/manifest.json", "/data/ai/anomaly.json", "/data/weather/2023-08.json",
                 "/data/air/pm25/2023-08.json", "/data/ghg/monthly.json"]) {
  const r = await get(`${base}${p}`);
  check(r.status === 200, `${p} が 200`, `HTTP ${r.status}`);
  check((r.headers.get("content-type") || "").includes("application/json"),
    `${p} が application/json`, r.headers.get("content-type") || "なし");
}

const manifest = await (await get(`${base}/data/manifest.json`)).json();
check(manifest.counts?.weather_stations === 155, "manifest の気象官署が 155",
  String(manifest.counts?.weather_stations));
check(manifest.date_min === "2014-01-01" && manifest.date_max === "2023-12-31",
  "manifest の期間が 2014-01-01〜2023-12-31", `${manifest.date_min}〜${manifest.date_max}`);

// 配ってはならないものが本番に無いこと(.vercelignore が効いているか)
for (const p of ["/data/processed/ghg_monthly.json", "/tests/conftest.py", "/.venv/pyvenv.cfg"]) {
  const r = await get(`${base}${p}`);
  check(r.status === 404, `${p} は配られていない`, `HTTP ${r.status}`);
}

// --- 3. 実ブラウザ: フッタの宛先と地図 -------------------------------------
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(String(e)));

await page.goto(`${base}/`, { waitUntil: "networkidle" });
const footer = await page.$$eval(".site-footer__inner a", (as) =>
  as.map((a) => ({ text: a.textContent.trim(), href: a.href })));
check(footer.length === 5, "フッタが 5 項目", footer.map((f) => f.text).join(" / "));
const appMenu = footer.find((f) => f.text === "App Menu");
check(appMenu?.href.includes("app-menu-amber.vercel.app"), "App Menu の宛先が app-menu-amber",
  appMenu?.href ?? "なし");
// 3・4 番目は解説アーティファクト(T-040 と同じ形)。README や SPEC の暫定リンクは開けるので
// 「引ける」だけでは仮の値を見逃す(HC-271)。
const ARTIFACT = /^https:\/\/claude\.ai\/code\/artifact\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
for (const label of ["アトラスの歩き方", "アトラスの設計図"]) {
  const item = footer.find((f) => f.text === label);
  check(ARTIFACT.test(item?.href ?? ""), `フッタ「${label}」が解説アーティファクトを指す`, item?.href ?? "なし");
}
const body = await page.locator("body").innerText();
check(!body.includes("app-menu.vercel.app"), "本文に他者の app-menu.vercel.app が無い");
for (const f of footer) {
  let status = 0;
  try {
    status = (await fetch(f.href, { redirect: "follow" })).status;
  } catch {
    status = 0;
  }
  check(status > 0 && status < 400, `フッタ「${f.text}」が引ける`, `${f.href} → HTTP ${status}`);
}

await page.goto(`${base}/map/`, { waitUntil: "networkidle" });
await page.waitForTimeout(3000);
const canvas = page.locator('[data-testid="japan-map"]');
const points = Number(await canvas.getAttribute("data-points").catch(() => "0"));
check(points > 0, "本番の地図に地点が載る", `${points} 点`);
const attrib = await page.locator(".maplibregl-ctrl-attrib").innerText().catch(() => "");
check(attrib.includes("地理院タイル"), "本番の地図に地理院タイルの出典が出る", attrib.slice(0, 60));

await page.goto(`${base}/patterns/`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const umapPoints = Number(await page.locator('[data-testid="umap-plot"]').getAttribute("data-points").catch(() => "0"));
check(umapPoints === 3652, "本番のパターン図が 3,652 日", String(umapPoints));

check(pageErrors.length === 0, "本番でスクリプトのエラーが出ない", pageErrors.slice(0, 2).join(" | "));
await browser.close();

console.log(notes.join("\n"));
if (failures.length) {
  console.error(`\n本番検品 NG ${failures.length} 件:`);
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`\n本番検品 OK — ${notes.length} 件すべて通過(${base})`);
