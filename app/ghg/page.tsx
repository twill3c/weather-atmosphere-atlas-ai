import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";

import GhgChart from "./GhgChart";
import type { GhgFile } from "@/lib/types";

export const metadata: Metadata = {
  title: "温室効果ガス — 日本気象・大気環境アトラス AI",
  description:
    "綾里・南鳥島・与那国島で観測された二酸化炭素とメタンの月別濃度。気象庁のデータを加工して作成。",
};

function readGhg(): GhgFile | null {
  const p = path.join(process.cwd(), "public", "data", "ghg", "monthly.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8")) as GhgFile;
  } catch {
    return null;
  }
}

export default function Page() {
  const data = readGhg();
  if (!data) {
    return (
      <main className="wrap">
        <h1>温室効果ガス</h1>
        <p className="muted">
          データがまだ生成されていません。
          <code>python scripts/ingest/jma_ghg.py</code> を実行してください。
        </p>
      </main>
    );
  }
  return (
    <main className="wrap">
      <h1>温室効果ガス</h1>
      <p className="lede">
        気象庁は綾里(岩手)・南鳥島・与那国島の 3 地点で大気を採り続けています。
        <strong>3 地点しかないので、面的な分布としては描きません</strong>
        —— ここに出るのは観測地点における値です。
      </p>
      <GhgChart data={data} />
    </main>
  );
}
