/**
 * ビルドの刻印を作る(HC-148 / T-037)。
 *
 * 本番検品は「本番が健やかか」しか答えない。デプロイが上限で失敗しても
 * 前の版が健やかに配られ続けるので、健やかさの項目をいくら足しても
 * **反映されたかどうか**は分からない(mondo-atlas で古い本番に全項目合格を返した)。
 *
 * そこで配る木の中身から刻印を作り、`public/build-stamp.json` に置く。
 * ビルドは手元でも Vercel でも同じ木から走るので、同じ刻印になる。
 * 検品は本番からこれを引き、手元の値と違えば他を一切見ずに止める。
 *
 * 材料は **画面のソースとデータの両方**。データだけにすると、フッタを直しても
 * 刻印が変わらず、古い本番に「一致」と返した(jinja-origin-atlas-ai)。
 *
 *     node scripts/build_stamp.mjs        public/build-stamp.json を書く(prebuild)
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

/** 画面を作るソース。ここが変われば画面が変わる。 */
const SOURCE_DIRS = ["app", "components", "lib"];
const SOURCE_EXT = new Set([".ts", ".tsx", ".css", ".mjs", ".js"]);
/** 画面が実行時・ビルド時に読むデータ。 */
const DATA_DIR = join("public", "data");
/** 振る舞いを変えるルートの設定。 */
const ROOT_FILES = ["package.json", "next.config.mjs", "tsconfig.json"];

function walk(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function ext(path) {
  const i = path.lastIndexOf(".");
  return i < 0 ? "" : path.slice(i);
}

/**
 * 刻印の材料。一覧を手で書かず、実際に在るファイルから作る ——
 * 書き忘れると刻印がその変化を見落とす。
 */
export function stampedFiles(root = ROOT) {
  const files = [];
  for (const d of SOURCE_DIRS) {
    for (const f of walk(join(root, d))) {
      if (SOURCE_EXT.has(ext(f))) files.push(f);
    }
  }
  for (const f of walk(join(root, DATA_DIR))) {
    if (ext(f) === ".json") files.push(f);
  }
  for (const f of ROOT_FILES) {
    const full = join(root, f);
    if (existsSync(full)) files.push(full);
  }
  return files
    .map((f) => relative(root, f).split(sep).join("/"))
    .sort();
}

/**
 * 改行を揃えてから測る。この機は core.autocrlf=true で、作業ツリーは CRLF・
 * git と配信側は LF になりうる。生のバイト列で測ると同じ内容でも食い違い、
 * 検査が毎回「違う」と言い続ける(狼少年になった検査は何もしないより悪い)。
 */
function normalizeEol(buf) {
  return Buffer.from(buf.toString("utf8").split("\r\n").join("\n"), "utf8");
}

export function computeStamp(root = ROOT) {
  const whole = createHash("sha256");
  const files = [];
  for (const rel of stampedFiles(root)) {
    const buf = normalizeEol(readFileSync(join(root, rel)));
    const sha = createHash("sha256").update(buf).digest("hex").slice(0, 12);
    files.push({ path: rel, bytes: buf.length, sha });
    whole.update(rel).update("\0").update(buf).update("\0");
  }
  return { stamp: whole.digest("hex").slice(0, 16), count: files.length, files };
}

const invokedDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  const { stamp, count, files } = computeStamp();
  const bySection = {};
  for (const f of files) {
    const key = f.path.startsWith("public/data/") ? "data" : f.path.split("/")[0];
    bySection[key] = (bySection[key] ?? 0) + 1;
  }
  const payload = {
    stamp,
    count,
    sections: bySection,
    generated_at: new Date().toISOString(),
  };
  writeFileSync(join(ROOT, "public", "build-stamp.json"), `${JSON.stringify(payload, null, 1)}\n`);
  console.log(`build-stamp ${stamp}(${count} ファイル: ${JSON.stringify(bySection)})`);
}
