import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";

import type { Manifest } from "@/lib/types";

export const metadata: Metadata = {
  title: "データの出典 — 日本気象・大気環境アトラス AI",
  description:
    "本アトラスが利用する公開データの出典・種別・取得日・加工の有無・再配布の有無・利用条件。",
};

function readManifest(): Manifest | null {
  try {
    return JSON.parse(
      fs.readFileSync(
        path.join(process.cwd(), "public", "data", "manifest.json"),
        "utf-8",
      ),
    ) as Manifest;
  } catch {
    return null;
  }
}

const ROWS = [
  {
    source: "気象庁",
    kind: "地上気象観測 日別値・月別値、観測地点情報",
    retrieved: "2026-09-08 以降",
    processed: "あり(単位の正規化・記号の解釈・日別値の集計)",
    redistributed: "あり(加工した派生値のみ)",
    terms: "公共データ利用規約(第 1.0 版)",
    url: "https://www.jma.go.jp/jma/kishou/info/coment.html",
  },
  {
    source: "気象庁",
    kind: "大気・海洋環境観測年報(温室効果ガス 月別値)",
    retrieved: "2026-09-08",
    processed: "あり(固定長の解釈・欠測の除外・年平均の算出)",
    redistributed: "あり(月別値と年平均)",
    terms: "公共データ利用規約(第 1.0 版)",
    url: "https://www.data.jma.go.jp/env/data/report/data/download/atm_bg_j.html",
  },
  {
    source: "国立環境研究所 環境展望台",
    kind: "大気汚染常時監視データ(時間値・測定局)",
    retrieved: "2026-09-08 以降",
    processed: "あり(時間値から日別値への集約・座標の十進変換)",
    redistributed: "なし(生ファイルは配らない。日別の派生値のみ)",
    terms: "掲載情報の著作権は国立環境研究所に帰属",
    url: "https://tenbou.nies.go.jp/copyright/",
  },
  {
    source: "国土地理院",
    kind: "地理院タイル(淡色地図)",
    retrieved: "実行時に読み込み",
    processed: "なし",
    redistributed: "なし(利用者のブラウザが直接取得)",
    terms: "国土地理院コンテンツ利用規約",
    url: "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html",
  },
];

export default function Page() {
  const manifest = readManifest();
  return (
    <main className="wrap">
      <h1>データの出典</h1>
      <p className="lede">
        本アトラスは公開されている観測データを<strong>加工して</strong>作成しています。
        アプリ本体のライセンスは MIT ですが、<strong>MIT は外部データには適用されません</strong>。
      </p>

      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th>出典</th>
              <th>種別</th>
              <th>取得</th>
              <th>加工</th>
              <th>再配布</th>
              <th>利用条件</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r, i) => (
              <tr key={i}>
                <th scope="row">{r.source}</th>
                <td>{r.kind}</td>
                <td className="small">{r.retrieved}</td>
                <td className="small">{r.processed}</td>
                <td className="small">{r.redistributed}</td>
                <td className="small">
                  <a href={r.url}>{r.terms}</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>表示の決まり</h2>
      <ul>
        <li>出典:気象庁ホームページ ／ 気象庁のデータを加工して作成</li>
        <li>国立環境研究所 環境展望台 大気汚染常時監視データファイル</li>
        <li>地図には常時「地理院タイル」を表示</li>
      </ul>

      <h2>しないこと</h2>
      <ul>
        <li>
          独自の天気予報・降水確率予測・台風進路予測・警報の発表(気象業務法第 17 条・第 23 条)
        </li>
        <li>PM2.5 等からの個人の健康影響の診断</li>
        <li>観測地点の無い場所の値を「観測値」として見せること</li>
        <li>根拠のない確信度(「AI confidence 97%」のような表示)</li>
        <li>国立環境研究所の生ファイルの再配布</li>
      </ul>

      {manifest && (
        <>
          <h2>この配信物</h2>
          <p className="small muted">
            データ版 {manifest.dataset_version} ／ 生成 {manifest.generated_at}
            <br />
            収録 {manifest.date_min} 〜 {manifest.date_max} ／ 気象官署{" "}
            {manifest.counts.weather_stations} 地点 ／ 大気測定局{" "}
            {manifest.counts.air_stations.toLocaleString()} 局 ／ 収録日数{" "}
            {manifest.counts.weather_days.toLocaleString()}
          </p>
        </>
      )}
    </main>
  );
}
