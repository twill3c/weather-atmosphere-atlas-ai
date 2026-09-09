/** 実ブラウザ検品(SPEC N-05 / G-13 / G-14、HC-041 / HC-078 / HC-080 / HC-138)。
 *
 *   node harness/smoke.mjs            出荷した out/ を配って検品する
 *   node harness/smoke.mjs --shot     画面を shots/ に撮る
 *
 * 規律:
 *   * 検品器は**実装ではなく振る舞い**で書く。要素名や描画経路に依存させない。
 *   * 在存だけでなく**幾何と到達**を測る(HC-138)。
 *   * 検品器にも**陽性対照**を置く。異常を捕まえられることを一度確かめる(HC-080)。
 *   * 失敗は終了コードで知らせる。撮影できても中身が空なら失敗とする。
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(ROOT, "..", "out");
const SHOTS = path.join(ROOT, "..", "shots");
const WANT_SHOTS = process.argv.includes("--shot");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

const failures = [];
const notes = [];
function check(ok, label, detail = "") {
  if (ok) notes.push(`  OK   ${label}`);
  else failures.push(`  NG   ${label}${detail ? ` — ${detail}` : ""}`);
  return ok;
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    let file = path.join(OUT, url);
    if (url.endsWith("/")) file = path.join(file, "index.html");
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      const alt = `${file}.html`;
      if (fs.existsSync(alt)) file = alt;
      else {
        res.writeHead(404).end("not found");
        return;
      }
    }
    res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

/** 横の溢れと縦の伸びすぎ。目視の代わりではなく、目視を忘れたときの網(HC-078)。 */
async function measureOverflow(page) {
  return page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
    scrollH: document.documentElement.scrollHeight,
  }));
}

async function main() {
  if (!fs.existsSync(OUT)) {
    console.error(`out/ がありません。先に npm run build を実行してください。`);
    process.exit(1);
  }
  const server = await serve();
  const { port } = server.address();
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  // 応答の失敗は URL つきで拾う。「404 が 3 件」だけでは、どれが欠けたか分からない。
  const consoleErrors = [];
  const httpFailures = [];
  page.on("console", (m) => {
    // 資源の 404 は response で URL つきに拾うので、ここでは重複させない
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) {
      consoleErrors.push(m.text());
    }
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
  page.on("response", (r) => {
    if (r.status() >= 400) httpFailures.push(`${r.status()} ${new URL(r.url()).pathname}`);
  });

  /** AI 資産はモデルを学習してから作る。未生成なら 404 になるが、
   *  画面は「まだありません」と出して壊れない設計にしてある(SPEC F-15)。
   *  未生成であることは失敗ではなく**状態**なので、件数を報告して区別する。 */
  const OPTIONAL = /^\/data\/ai\//;

  if (WANT_SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

  const PAGES = [
    { path: "/", heading: "日本気象・大気環境アトラス AI" },
    { path: "/map/", heading: "地図" },
    { path: "/ghg/", heading: "温室効果ガス" },
    { path: "/patterns/", heading: "パターン" },
    { path: "/compare/", heading: "比較" },
    { path: "/about/", heading: "このアトラスについて" },
    { path: "/data-policy/", heading: "データの出典" },
  ];

  for (const spec of PAGES) {
    const res = await page.goto(base + spec.path, { waitUntil: "networkidle" });
    check(res?.ok(), `${spec.path} が開く`, `HTTP ${res?.status()}`);
    const h1 = (await page.locator("h1").first().innerText().catch(() => "")).trim();
    check(h1.includes(spec.heading), `${spec.path} の見出し`, `実際 "${h1}"`);

    // フリート共通フッタ: 5 項目・下部固定(規約)
    const footer = page.locator(".site-footer__inner");
    const links = await footer.locator("a").allInnerTexts();
    check(links.length === 5, `${spec.path} のフッタが 5 項目`, `実際 ${links.length}`);
    check(
      links[0] === "MIT License" && links[4] === "App Menu",
      `${spec.path} のフッタの並び`,
      links.join(" / "),
    );
    const copy = await footer.locator(".site-footer__copy").innerText().catch(() => "");
    check(copy.includes("2026 坂田哲朗"), `${spec.path} のフッタの著作権表示`, copy);

    // 出典と data-policy への到達(G-14)
    const policyReachable = await page
      .locator('a[href="/data-policy/"], a[href*="data-policy"]')
      .count();
    if (spec.path !== "/data-policy/") {
      check(policyReachable > 0, `${spec.path} から出典へ辿れる`);
    }

    // 本文に記法の生残りが出ていないこと。
    // JSX は Markdown を解釈しないので、`**強調**` と書くとアスタリスクが
    // そのまま画面に出る。型検査もテストも実ブラウザ検品も緑のまま通り、
    // **スクリーンショットを開いて初めて見つかった**(HC-041)。
    const bodyText = await page.locator("body").innerText();
    for (const [pattern, label] of [
      [/\*\*/, "Markdown の強調(**)"],
      [/\{\s*["'`]/, "JSX の式が文字列のまま"],
      [/undefined|NaN/, "undefined / NaN"],
      [/\[object Object\]/, "[object Object]"],
    ]) {
      const hit = bodyText.match(pattern);
      check(
        !hit,
        `${spec.path} の本文に ${label} が出ていない`,
        hit ? bodyText.slice(Math.max(0, hit.index - 30), hit.index + 30) : "",
      );
    }

    // 複数の幅で横溢れを見る(HC-078)
    for (const width of [1280, 900, 600, 380]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(120);
      const m = await measureOverflow(page);
      check(
        m.scrollW <= m.clientW + 2,
        `${spec.path} が幅 ${width} で横に溢れない`,
        `scrollW ${m.scrollW} > clientW ${m.clientW}`,
      );
      check(
        m.scrollH < 16000,
        `${spec.path} が幅 ${width} で縦に伸びすぎない`,
        `scrollH ${m.scrollH}`,
      );
    }
    await page.setViewportSize({ width: 1280, height: 900 });

    if (WANT_SHOTS) {
      const name = spec.path.replace(/\//g, "_") || "_root";
      await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
    }
  }

  // --- 地図: 幾何と到達を測る(HC-138) ------------------------------------
  await page.goto(`${base}/map/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  const canvas = page.locator('[data-testid="japan-map"]');
  const hasCanvas = (await canvas.count()) > 0;
  check(hasCanvas, "地図の描画領域がある");

  if (hasCanvas) {
    const box = await canvas.boundingBox();
    check(
      !!box && box.width > 320 && box.height > 240,
      "地図が実寸を持つ",
      box ? `${Math.round(box.width)}x${Math.round(box.height)}` : "なし",
    );
    const points = Number(await canvas.getAttribute("data-points"));
    const missing = Number(await canvas.getAttribute("data-missing"));
    check(points > 0, "地図に地点が載っている", `${points} 点`);
    check(
      missing <= points,
      "欠測の数が地点数を超えない",
      `${missing}/${points}`,
    );
    // 出典は地図表示中つねに出る(国土地理院コンテンツ利用規約 / G-14)
    const attrib = await page.locator(".maplibregl-ctrl-attrib").innerText().catch(() => "");
    check(attrib.includes("地理院タイル"), "地図に地理院タイルの出典が出る", attrib.slice(0, 60));
  }

  // レイヤを切り替えると、実際に何かが変わることを確かめる(空振りの検出)
  const before = await canvas.getAttribute("data-points").catch(() => null);
  const rainBtn = page.getByRole("button", { name: "降水量" });
  if (await rainBtn.count()) {
    await rainBtn.first().scrollIntoViewIfNeeded();
    await rainBtn.first().click();
    await page.waitForTimeout(1200);
    const pressed = await rainBtn.first().getAttribute("aria-pressed");
    check(pressed === "true", "レイヤの切り替えが届いた", `aria-pressed=${pressed}`);
    const after = await canvas.getAttribute("data-points").catch(() => null);
    check(after !== null, "切り替え後も地点が載っている", `${before} -> ${after}`);
  }

  // 日付を送ると URL が変わる(F-17)。
  // **「次の日」は収録の最終日では動かない**(clampDate で止まるのが正しい)。
  // 初期表示は最終日なので、動くことを確かめるなら「前の日」を押す。
  const dateInput = page.locator('input[type="date"]').first();
  const dateBefore = await dateInput.inputValue();
  const prevBtn = page.getByRole("button", { name: "前の日" });
  if (await prevBtn.count()) {
    await prevBtn.first().click();
    await page.waitForTimeout(600);
    const dateAfter = await dateInput.inputValue();
    check(dateAfter !== dateBefore, "前の日に送ると日付が変わる", `${dateBefore} -> ${dateAfter}`);
    check(page.url().includes(dateAfter), "日付が URL に反映される", page.url());
  }
  // 最終日で「次の日」を押しても飛び出さない(範囲の外へ行かない)
  const maxDate = await dateInput.getAttribute("max");
  if (maxDate) {
    await dateInput.fill(maxDate);
    await page.waitForTimeout(400);
    await page.getByRole("button", { name: "次の日" }).first().click();
    await page.waitForTimeout(400);
    check(
      (await dateInput.inputValue()) === maxDate,
      "収録の最終日より先には進まない",
      await dateInput.inputValue(),
    );
  }

  // 「0 と表示しない」— 欠測の凡例が出ていること(G-13)
  const legendText = await page.locator(".map-side").innerText().catch(() => "");
  check(legendText.includes("データなし"), "欠測の説明が凡例にある");

  // --- 図の中の文字が重なっていないか(HC-159) ------------------------------
  // 横溢れも縦伸びも要素数も緑のまま、**凡例の文字どうしが重なる**ことがあった
  // (温室効果ガスの図で「南鳥島」と「422.7 ppm」が同じ場所に描かれていた)。
  // 目視は再現性のある防御ではないので、境界矩形で測る。
  // `expectText` は「図の内側に文字を置く設計か」。UMAP は軸に意味が無いので
  // 目盛りを描かず、凡例は SVG の外に HTML で置いている。**設計に合わせて測る。**
  for (const [path, testid, expectText] of [
    ["/ghg/", "ghg-chart", true],
    ["/patterns/", "umap-plot", false],
  ]) {
    await page.goto(base + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1800);
    const svg = page.locator(`[data-testid="${testid}"]`);
    if ((await svg.count()) === 0) {
      check(false, `${path} に図がある`, testid);
      continue;
    }
    const report = await svg.evaluate((node) => {
      const texts = [...node.querySelectorAll("text")].filter(
        (t) => (t.textContent || "").trim().length > 0,
      );
      const boxes = texts.map((t) => {
        const b = t.getBBox();
        return { s: (t.textContent || "").trim(), x: b.x, y: b.y, w: b.width, h: b.height };
      });
      const vb = node.viewBox.baseVal;
      const overlaps = [];
      for (let i = 0; i < boxes.length; i += 1) {
        for (let j = i + 1; j < boxes.length; j += 1) {
          const a = boxes[i];
          const c = boxes[j];
          const ox = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
          const oy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
          if (ox > 1 && oy > 1) overlaps.push(`${a.s} × ${c.s}`);
        }
      }
      const outside = boxes.filter(
        (b) =>
          b.x < vb.x - 1 ||
          b.y < vb.y - 1 ||
          b.x + b.w > vb.x + vb.width + 1 ||
          b.y + b.h > vb.y + vb.height + 1,
      );
      return { count: boxes.length, overlaps, outside: outside.map((b) => b.s) };
    });
    if (expectText) {
      check(report.count > 0, `${path} の図に文字がある`, `${report.count} 個`);
    } else {
      // 図の中に文字を置かない代わりに、凡例が図の外にあること。
      const swatches = await page.locator(".legend--row .legend__swatch").count();
      check(swatches > 0, `${path} の凡例が図の外にある`, `${swatches} 色`);
    }
    check(
      report.overlaps.length === 0,
      `${path} の図の文字が重なっていない`,
      report.overlaps.slice(0, 3).join(" / "),
    );
    check(
      report.outside.length === 0,
      `${path} の図の文字が viewBox に収まっている`,
      report.outside.slice(0, 3).join(" / "),
    );
  }
  await page.goto(`${base}/map/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  // --- 検品器の陽性対照(HC-080) -------------------------------------------
  // 存在しないはずの見出しを探して「捕まえられる」ことを一度確かめる。
  const controlOk = (await page.locator("h1:has-text('存在しない見出しXYZ')").count()) === 0;
  check(controlOk, "陽性対照: 偽の見出しは見つからない");
  const overflowControl = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.cssText = "width:5000px;height:1px";
    document.body.appendChild(probe);
    const w = document.documentElement.scrollWidth;
    const c = document.documentElement.clientWidth;
    probe.remove();
    return w > c;
  });
  check(overflowControl, "陽性対照: 横溢れの検査が実際に発火する");

  check(
    consoleErrors.length === 0,
    "コンソールにエラーが出ない",
    consoleErrors.slice(0, 3).join(" | "),
  );

  const optional = [...new Set(httpFailures.filter((f) => OPTIONAL.test(f.split(" ")[1])))];
  const required = [...new Set(httpFailures.filter((f) => !OPTIONAL.test(f.split(" ")[1])))];
  check(
    required.length === 0,
    "必須の配信物がすべて取得できる",
    required.slice(0, 5).join(" | "),
  );
  if (optional.length) {
    notes.push(
      `  --   AI 資産が未生成(${optional.length} 件): ${optional.join(" | ")}`,
    );
  }

  await browser.close();
  server.close();

  console.log(notes.join("\n"));
  if (failures.length) {
    console.error(`\n検品 NG ${failures.length} 件:`);
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log(`\n検品 OK — ${notes.length} 件すべて通過`);
}

main().catch((err) => {
  console.error("検品器そのものが落ちた:", err);
  process.exit(1);
});
