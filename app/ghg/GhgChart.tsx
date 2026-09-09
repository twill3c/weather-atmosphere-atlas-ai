"use client";

/** 温室効果ガスの長期時系列(SPEC F-07 / §36)。
 *
 * 図の中の文字(軸・凡例・注記)は、図を描いたのと同じデータから導く(HC-045)。
 * 座標を決め打ちしない。`viewBox` は軸ラベルの外側まで含める(HC-159)。
 */
import { useMemo, useState } from "react";

import type { GhgFile } from "@/lib/types";

const SPECIES = [
  { id: "co2", label: "二酸化炭素 CO₂", unit: "ppm" },
  { id: "ch4", label: "メタン CH₄", unit: "ppb" },
] as const;

const STATION_COLOR: Record<string, string> = {
  ry: "#1f5f8b",
  mi: "#a8541f",
  yo: "#4b8f3f",
};

// viewBox はデータの範囲ではなく描画領域から決める。軸ラベルは外側に出るので、
// 余白を含めた全体を viewBox にする(HC-159)。
const W = 880;
const H = 380;
const M = { top: 18, right: 130, bottom: 44, left: 62 };
/** 凡例 1 件ぶんの行送り。名前(y)と最新値(y+14)の 2 行が入るので、
 *  14 より十分大きく取る。20 にしていたときは隣と重なった。 */
const LEGEND_STEP = 34;

export default function GhgChart({ data }: { data: GhgFile }) {
  const [species, setSpecies] = useState<"co2" | "ch4">("co2");
  const [smooth, setSmooth] = useState(true);

  const stations = useMemo(
    () => Object.keys(data.stations).filter((s) => data.series[`${species}:${s}`]),
    [data, species],
  );

  const series = useMemo(() => {
    return stations.map((st) => {
      const raw = (data.series[`${species}:${st}`] ?? []).filter(
        (p) => p.value !== null,
      );
      const points = raw.map((p) => ({
        t: p.year + (p.month - 0.5) / 12,
        v: p.value as number,
      }));
      // 12 か月の中央移動平均。季節変動を均した「趨勢」であって、予測ではない。
      const trend: { t: number; v: number }[] = [];
      for (let i = 6; i < points.length - 6; i += 1) {
        let sum = 0;
        for (let k = i - 6; k <= i + 6; k += 1) sum += points[k].v;
        trend.push({ t: points[i].t, v: sum / 13 });
      }
      return { station: st, name: data.stations[st], points, trend };
    });
  }, [data, species, stations]);

  const bounds = useMemo(() => {
    const all = series.flatMap((s) => s.points);
    if (!all.length) return null;
    const ts = all.map((p) => p.t);
    const vs = all.map((p) => p.v);
    const vMin = Math.min(...vs);
    const vMax = Math.max(...vs);
    const pad = (vMax - vMin) * 0.06;
    return {
      tMin: Math.min(...ts),
      tMax: Math.max(...ts),
      vMin: vMin - pad,
      vMax: vMax + pad,
    };
  }, [series]);

  if (!bounds) return <p className="muted">この物質のデータがありません。</p>;

  const x = (t: number) =>
    M.left + ((t - bounds.tMin) / (bounds.tMax - bounds.tMin)) * (W - M.left - M.right);
  const y = (v: number) =>
    H - M.bottom - ((v - bounds.vMin) / (bounds.vMax - bounds.vMin)) * (H - M.top - M.bottom);

  // 目盛りもデータの範囲から導く
  const yTicks = niceTicks(bounds.vMin, bounds.vMax, 6);
  const xTicks = niceYears(bounds.tMin, bounds.tMax);
  const unit = SPECIES.find((s) => s.id === species)!.unit;

  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", margin: "0 0 0.8rem" }}>
        {SPECIES.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={s.id === species}
            onClick={() => setSpecies(s.id)}
          >
            {s.label}
          </button>
        ))}
        <button type="button" aria-pressed={smooth} onClick={() => setSmooth((v) => !v)}>
          12 か月移動平均を重ねる
        </button>
      </div>

      <div className="scroll-x">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          style={{ minWidth: 620, display: "block" }}
          role="img"
          aria-label={`${SPECIES.find((s) => s.id === species)!.label}の月別濃度(観測地点別)`}
          data-testid="ghg-chart"
        >
          {yTicks.map((v) => (
            <g key={v}>
              <line
                x1={M.left}
                x2={W - M.right}
                y1={y(v)}
                y2={y(v)}
                stroke="var(--border)"
                strokeWidth={1}
              />
              <text
                x={M.left - 8}
                y={y(v)}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={11}
                fill="var(--text-muted)"
              >
                {v}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text
              key={t}
              x={x(t)}
              y={H - M.bottom + 18}
              textAnchor="middle"
              fontSize={11}
              fill="var(--text-muted)"
            >
              {t}
            </text>
          ))}
          <text
            x={M.left - 46}
            y={M.top + 4}
            fontSize={11}
            fill="var(--text-muted)"
          >
            {unit}
          </text>

          {series.map((s) => (
            <g key={s.station}>
              <path
                d={pathOf(s.points, x, y)}
                fill="none"
                stroke={STATION_COLOR[s.station] ?? "var(--text-muted)"}
                strokeWidth={smooth ? 0.9 : 1.4}
                opacity={smooth ? 0.45 : 1}
              />
              {smooth && (
                <path
                  d={pathOf(s.trend, x, y)}
                  fill="none"
                  stroke={STATION_COLOR[s.station] ?? "var(--text-muted)"}
                  strokeWidth={2}
                />
              )}
            </g>
          ))}

          {series.map((s, i) => {
            const last = s.points[s.points.length - 1];
            // 1 件が 2 行(名前と最新値)なので、行送りより広い間隔で置く。
            // 20px にしていたときは隣の件と重なって読めなかった。
            const y = M.top + 14 + i * LEGEND_STEP;
            return (
              <g key={`legend-${s.station}`}>
                <line
                  x1={W - M.right + 10}
                  x2={W - M.right + 28}
                  y1={y}
                  y2={y}
                  stroke={STATION_COLOR[s.station]}
                  strokeWidth={2.5}
                />
                <text
                  x={W - M.right + 34}
                  y={y}
                  dominantBaseline="middle"
                  fontSize={11}
                  fill="var(--text)"
                >
                  {s.name}
                </text>
                <text
                  x={W - M.right + 34}
                  y={y + 14}
                  dominantBaseline="middle"
                  fontSize={10}
                  fill="var(--text-muted)"
                >
                  {last ? `${last.v.toFixed(1)} ${unit}` : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="scroll-x" style={{ marginTop: "1rem" }}>
        <table>
          <caption className="small muted" style={{ textAlign: "left", paddingBottom: "0.3rem" }}>
            観測地点ごとの収録範囲(有効な月のみを数えた)
          </caption>
          <thead>
            <tr>
              <th>観測地点</th>
              <th>期間</th>
              <th className="num">有効な月</th>
              <th className="num">最初</th>
              <th className="num">最後</th>
            </tr>
          </thead>
          <tbody>
            {series.map((s) => {
              const first = s.points[0];
              const last = s.points[s.points.length - 1];
              return (
                <tr key={s.station}>
                  <th scope="row">{s.name}</th>
                  <td>
                    {fmt(first?.t)} 〜 {fmt(last?.t)}
                  </td>
                  <td className="num">{s.points.length}</td>
                  <td className="num">
                    {first ? `${first.v.toFixed(1)} ${unit}` : "—"}
                  </td>
                  <td className="num">{last ? `${last.v.toFixed(1)} ${unit}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="small muted" style={{ marginTop: "0.8rem" }}>
        <span className="badge badge--observed">観測値</span> 細い線が月別値、
        太い線は 12 か月の移動平均です(移動平均は
        <span className="badge badge--derived">派生値</span>)。
        {data.oracle && (
          <>
            {" "}月別値から算出した年平均は、気象庁が別途公表している年平均値と{" "}
            {data.oracle.station_years_compared} 観測点年で照合し、不一致は{" "}
            {data.oracle.mismatches} 件でした。
          </>
        )}
      </p>
      <p className="small muted">{data.note} ／ 出典: {data.source}</p>
    </>
  );
}

function pathOf(
  pts: { t: number; v: number }[],
  x: (t: number) => number,
  y: (v: number) => number,
): string {
  return pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
}

function fmt(t: number | undefined): string {
  if (t === undefined) return "—";
  const year = Math.floor(t);
  const month = Math.round((t - year) * 12 + 0.5);
  return `${year}-${String(month).padStart(2, "0")}`;
}

function niceTicks(min: number, max: number, count: number): number[] {
  const span = max - min;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) {
    out.push(Number(v.toFixed(6)));
  }
  return out;
}

function niceYears(min: number, max: number): number[] {
  const span = max - min;
  const step = span > 30 ? 5 : span > 12 ? 2 : 1;
  const out: number[] = [];
  for (let y = Math.ceil(min / step) * step; y <= max; y += step) out.push(y);
  return out;
}
