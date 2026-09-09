"use client";

/** パターン画面(SPEC F-11 / F-12 / 構想書 §32)。
 *
 * UMAP の 2 次元は**座標に意味が無い**。近さだけが情報である、と画面にも書く。
 * クラスタの番号はモデルが付けたもので、説明の語は統計から導いて添える。
 */
import { useEffect, useMemo, useState } from "react";

import { DatasetMissing, loadClusters, loadUmap } from "@/lib/data";
import type { ClusterFile, UmapFile } from "@/lib/types";

type ColorBy = "season" | "cluster" | "anomaly";

const SEASON_COLOR: Record<string, string> = {
  春: "#5aa469", 夏: "#cf5f12", 秋: "#a8823a", 冬: "#3b7cae",
};
const CLUSTER_COLORS = [
  "#1f5f8b", "#cf5f12", "#4b8f3f", "#8a4f9e", "#b7472a", "#2f8f8a",
  "#94701f", "#5566b5", "#a8446a", "#3f7f5f", "#7a5c2e", "#6a6f7a",
  "#c07a2a", "#4a7fa8", "#8f5a3f", "#5f8f2a",
];

/** 異常度の塗り。凡例と図で同じ配列を使う(別々に書くとずれる)。 */
const ANOMALY_RAMP = ["#e8eef4", "#c3d8e8", "#93b9d6", "#f2c496", "#dd8b47", "#b7521a"];

const W = 720;
const H = 470;
const PAD = 26;

function seasonOf(date: string): string {
  const m = Number(date.slice(5, 7));
  if (m <= 2 || m === 12) return "冬";
  if (m <= 5) return "春";
  if (m <= 8) return "夏";
  return "秋";
}

export default function PatternMap() {
  const [umap, setUmap] = useState<UmapFile | null>(null);
  const [clusters, setClusters] = useState<ClusterFile | null>(null);
  const [colorBy, setColorBy] = useState<ColorBy>("season");
  const [hover, setHover] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([loadUmap(), loadClusters()])
      .then(([u, c]) => {
        setUmap(u);
        setClusters(c);
      })
      .catch((err) => {
        setError(
          err instanceof DatasetMissing
            ? "AI 資産がまだ生成されていません。特徴量の作成・学習・書き出しを実行してください。"
            : String(err),
        );
      })
      .finally(() => setLoaded(true));
  }, []);

  const bounds = useMemo(() => {
    if (!umap?.points.length) return null;
    const xs = umap.points.map((p) => p.x);
    const ys = umap.points.map((p) => p.y);
    return {
      x0: Math.min(...xs), x1: Math.max(...xs),
      y0: Math.min(...ys), y1: Math.max(...ys),
    };
  }, [umap]);

  if (!loaded) {
    return (
      <main className="wrap">
        <p className="muted">読み込んでいます…</p>
      </main>
    );
  }
  if (error || !umap || !bounds) {
    return (
      <main className="wrap">
        <h1>パターン</h1>
        <p className="muted">{error ?? "データがありません。"}</p>
      </main>
    );
  }

  const sx = (x: number) =>
    PAD + ((x - bounds.x0) / (bounds.x1 - bounds.x0 || 1)) * (W - PAD * 2);
  const sy = (y: number) =>
    H - PAD - ((y - bounds.y0) / (bounds.y1 - bounds.y0 || 1)) * (H - PAD * 2);

  const colorOf = (p: UmapFile["points"][number]) => {
    if (colorBy === "season") return SEASON_COLOR[seasonOf(p.date)];
    if (colorBy === "cluster") return CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length];
    const t = Math.min(1, Math.max(0, p.anomaly / 100));
    return ANOMALY_RAMP[Math.min(ANOMALY_RAMP.length - 1, Math.floor(t * ANOMALY_RAMP.length))];
  };

  const hovered = hover ? umap.points.find((p) => p.date === hover) : null;
  const stats = clusters?.stats;

  return (
    <main className="wrap wrap--wide">
      <h1>パターン</h1>
      <p className="lede">
        日ごとの全国の気象を Autoencoder が 128 次元の表現に直し、それを 2 次元に
        落として並べたものです。<strong>軸そのものに意味はありません</strong>
        —— 近くにある点どうしが「似た日」です。
      </p>
      <p className="small muted">
        <span className="badge badge--ai">AI 由来</span>{" "}
        {umap.points.length.toLocaleString()} 日 ／ クラスタ {clusters?.k ?? "—"} 個
        {clusters && `(silhouette ${clusters.silhouette}）`}
      </p>

      {clusters && clusters.silhouette < 0.15 && (
        <div className="card" style={{ margin: "0.8rem 0" }}>
          <strong>群はきれいには分かれていません。</strong>
          <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
            k を 6 から 16 まで変えてシルエット係数を測りましたが、最大でも{" "}
            {clusters.silhouette}(k={clusters.k})で、どの k でもほとんど変わりません
            {clusters.trials && (
              <>
                (
                {clusters.trials
                  .map((t) => `k=${t.k}:${t.silhouette.toFixed(3)}`)
                  .join(" ")}
                )
              </>
            )}
            。日本の日々の気象は<strong>いくつかの型に分かれるというより連続体</strong>で、
            クラスタは便宜的な区切りだと考えてください。下の表の季節の内訳を見ると、
            どの群も複数の季節を含んでいます。
          </p>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", margin: "0.8rem 0" }}>
        {(
          [
            ["season", "季節で塗る"],
            ["cluster", "クラスタで塗る"],
            ["anomaly", "異常度で塗る"],
          ] as [ColorBy, string][]
        ).map(([id, label]) => (
          <button key={id} type="button" aria-pressed={colorBy === id} onClick={() => setColorBy(id)}>
            {label}
          </button>
        ))}
      </div>

      {/* 凡例。**図を塗ったのと同じ規則から導く**(HC-045)。
          色だけで意味を伝えないよう、語と数を必ず添える。 */}
      <div className="legend legend--row" aria-label={`塗り分けの凡例(${colorBy}）`}>
        {colorBy === "season" &&
          Object.entries(SEASON_COLOR).map(([label, color]) => (
            <span key={label} className="legend__item">
              <span className="legend__swatch" style={{ background: color }} aria-hidden="true" />
              {label}
            </span>
          ))}
        {colorBy === "cluster" &&
          Object.entries(stats ?? {})
            .sort((a, b) => b[1].days - a[1].days)
            .map(([k, s]) => (
              <span key={k} className="legend__item">
                <span
                  className="legend__swatch"
                  style={{ background: CLUSTER_COLORS[Number(k) % CLUSTER_COLORS.length] }}
                  aria-hidden="true"
                />
                クラスタ {k}
                <span className="muted">（{s.days.toLocaleString()} 日）</span>
              </span>
            ))}
        {colorBy === "anomaly" &&
          ANOMALY_RAMP.map((color, i) => (
            <span key={color} className="legend__item">
              <span className="legend__swatch" style={{ background: color }} aria-hidden="true" />
              {Math.round((i / ANOMALY_RAMP.length) * 100)}–
              {Math.round(((i + 1) / ANOMALY_RAMP.length) * 100)}
            </span>
          ))}
      </div>

      <div className="scroll-x">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          style={{ minWidth: 560, display: "block", background: "var(--surface-1)",
                   border: "1px solid var(--border)", borderRadius: 8 }}
          role="img"
          aria-label="AI が並べた日のパターン地図"
          data-testid="umap-plot"
          data-points={umap.points.length}
        >
          {umap.points.map((p) => (
            <circle
              key={p.date}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={hover === p.date ? 5 : 2.1}
              fill={colorOf(p)}
              opacity={hover && hover !== p.date ? 0.35 : 0.85}
              onMouseEnter={() => setHover(p.date)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: "pointer" }}
            >
              <title>{`${p.date} / 異常度 ${p.anomaly} / クラスタ ${p.cluster}`}</title>
            </circle>
          ))}
        </svg>
      </div>

      <p className="small muted" style={{ marginTop: "0.5rem" }}>
        {hovered ? (
          <>
            <strong>{hovered.date}</strong> ／ 異常度 {hovered.anomaly} / 100 ／ クラスタ{" "}
            {hovered.cluster} ／{" "}
            <a href={`/map/?date=${hovered.date}`}>この日の地図を開く</a>
          </>
        ) : (
          "点にカーソルを合わせると日付が出ます。"
        )}
      </p>

      {clusters && stats && (
        <>
          <h2>クラスタごとの内訳</h2>
          <p className="small muted">
            {clusters.note}。下の「季節の内訳」と「平均異常度」は、割り当てられた日から
            数えた<span className="badge badge--derived">派生値</span>です。
          </p>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>クラスタ</th>
                  <th className="num">日数</th>
                  <th>季節の内訳</th>
                  <th className="num">平均異常度</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats)
                  .sort((a, b) => b[1].days - a[1].days)
                  .map(([k, s]) => (
                    <tr key={k}>
                      <th scope="row">
                        <span
                          style={{
                            display: "inline-block", width: 10, height: 10,
                            borderRadius: "50%", marginRight: 6,
                            background: CLUSTER_COLORS[Number(k) % CLUSTER_COLORS.length],
                          }}
                          aria-hidden="true"
                        />
                        {k}
                      </th>
                      <td className="num">{s.days.toLocaleString()}</td>
                      <td className="small">
                        {Object.entries(s.seasons)
                          .map(([season, n]) => `${season} ${n}`)
                          .join(" ／ ")}
                      </td>
                      <td className="num">{s.mean_anomaly}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>読み方の注意</h2>
      <ul className="small muted">
        <li>UMAP の座標は近さを保つための配置で、軸の値そのものに意味はありません。</li>
        <li>
          異常度は「学習した並びからの外れ具合」の順位です。<strong>災害の危険度ではありません。</strong>
        </li>
        <li>クラスタの番号は付けられた順で、大小に意味はありません。</li>
        <li>
          シルエット係数が小さいので、<strong>クラスタの境界は強い主張ではありません</strong>。
          「この日はクラスタ 3 だから〇〇だ」とは読まないでください。
        </li>
        <li>
          異常度は、その日を学習に使っていないモデルで採点しています
          (時間ブロックを 5 つに割った交差適合)。そうしないと、
          <strong>学習した期間だけ異常度が低く出る</strong>という別物の指標になります。
        </li>
      </ul>
    </main>
  );
}
