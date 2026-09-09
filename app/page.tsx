import fs from "node:fs";
import path from "node:path";

import type { Manifest } from "@/lib/types";

/** 配信 manifest をビルド時に読む。無ければ null(取り込み前でもビルドは通す)。 */
function readManifest(): Manifest | null {
  const p = path.join(process.cwd(), "public", "data", "manifest.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8")) as Manifest;
  } catch {
    return null;
  }
}

const CARDS = [
  {
    href: "/map/",
    title: "地図で日を送る",
    body: "気温・降水量・風速・日照・積雪と、PM2.5・NO₂・SO₂・Ox を日本地図に重ね、日付を送って眺めます。",
  },
  {
    href: "/ghg/",
    title: "温室効果ガスの長期変化",
    body: "綾里・南鳥島・与那国島で観測された CO₂ と CH₄ を、1987 年からの月別値で見ます。",
  },
  {
    href: "/patterns/",
    title: "AI が並べたパターン",
    body: "日ごとの気象を Autoencoder で表現に直し、似た日・異常度・クラスタとして並べます。",
  },
  {
    href: "/compare/",
    title: "2 つの日を比べる",
    body: "同じ縮尺の地図を並べ、要素ごとの差と、AI 表現どうしの類似度を出します。",
  },
];

export default function Page() {
  const manifest = readManifest();
  return (
    <main className="wrap">
      <h1>日本気象・大気環境アトラス AI</h1>
      <p className="lede">
        日本の過去の空を、地図と時系列で辿る。気象庁と国立環境研究所が公開している
        観測データを重ね、そこに深層学習で作った表現を添えています。
      </p>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <strong>これは天気予報ではありません。</strong>
        <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
          扱うのは過去の観測データだけです。独自の予報・警報は出しません
          (気象業務法第 17 条・第 23 条)。画面の値は
          <span className="badge badge--observed">観測値</span>{" "}
          <span className="badge badge--derived">派生値</span>{" "}
          <span className="badge badge--ai">AI 由来</span> を区別して表示します。
        </p>
      </div>

      {manifest?.date_min && (
        <p className="muted small">
          収録期間 {manifest.date_min} 〜 {manifest.date_max} ／ 気象官署{" "}
          {manifest.counts.weather_stations} 地点 ／ 大気測定局{" "}
          {manifest.counts.air_stations.toLocaleString()} 局 ／ データ版{" "}
          {manifest.dataset_version}
        </p>
      )}

      <div className="grid" style={{ marginTop: "1.5rem" }}>
        {CARDS.map((c) => (
          <a key={c.href} href={c.href} className="card" style={{ textDecoration: "none" }}>
            <strong>{c.title}</strong>
            <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
              {c.body}
            </p>
          </a>
        ))}
      </div>

      <h2>出典</h2>
      <p className="small muted">
        気象庁のデータを加工して作成 ／ 国立環境研究所 環境展望台 大気汚染常時監視データ ／
        地図は<a href="https://maps.gsi.go.jp/development/ichiran.html">地理院タイル</a>。
        詳しくは<a href="/data-policy/">データの出典</a>を参照してください。
      </p>
    </main>
  );
}
