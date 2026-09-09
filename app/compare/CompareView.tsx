"use client";

/** 比較画面(SPEC F-13 / 構想書 §33)。
 *
 * 2 つの日を並べ、要素ごとの全国平均の差と、AI 表現どうしの類似度を出す。
 * 差は<span>派生値</span>、類似度は<span>AI 由来</span>として区別して示す。
 */
import { useCallback, useEffect, useState } from "react";

import {
  DatasetMissing,
  dayOf,
  formatJaDate,
  loadAnomaly,
  loadManifest,
  loadSimilar,
  loadWeatherMonth,
  monthOf,
} from "@/lib/data";
import { LAYERS, formatValue } from "@/lib/layers";
import type { AnomalyFile, Manifest, SimilarFile, WeatherVariable } from "@/lib/types";

const WEATHER = LAYERS.filter((l) => l.group === "weather");

interface DaySummary {
  date: string;
  means: Record<string, number | null>;
  stations: number;
}

async function summarize(date: string): Promise<DaySummary> {
  const grid = await loadWeatherMonth(monthOf(date));
  const day = dayOf(date);
  const means: Record<string, number | null> = {};
  let counted = 0;
  for (const def of WEATHER) {
    const table = grid.variables[def.id as WeatherVariable];
    const row = table?.[day - 1];
    if (!row) {
      means[def.id] = null;
      continue;
    }
    const vals = row.filter((v): v is number => v !== null && v !== undefined);
    if (def.id === "temperature_mean") counted = vals.length;
    means[def.id] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }
  return { date, means, stations: counted };
}

export default function CompareView() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [dateA, setDateA] = useState<string>("");
  const [dateB, setDateB] = useState<string>("");
  const [a, setA] = useState<DaySummary | null>(null);
  const [b, setB] = useState<DaySummary | null>(null);
  const [similar, setSimilar] = useState<SimilarFile | null>(null);
  const [anomaly, setAnomaly] = useState<AnomalyFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    loadManifest()
      .then((m) => {
        setManifest(m);
        const params = new URLSearchParams(window.location.search);
        const max = m.date_max ?? "";
        const fallbackA = params.get("a") ?? max;
        const prev = max ? `${Number(max.slice(0, 4)) - 1}${max.slice(4)}` : "";
        setDateA(fallbackA);
        setDateB(params.get("b") ?? (prev >= (m.date_min ?? "") ? prev : (m.date_min ?? "")));
      })
      .catch((err) =>
        setError(
          err instanceof DatasetMissing
            ? "データセットがまだ生成されていません。"
            : String(err),
        ),
      )
      .finally(() => setLoaded(true));
    loadAnomaly().then(setAnomaly).catch(() => setAnomaly(null));
  }, []);

  // 類似日は年ごとのファイル。A の年だけ読む(N-03)。
  useEffect(() => {
    if (!dateA) return;
    let alive = true;
    loadSimilar(dateA.slice(0, 4))
      .then((s) => alive && setSimilar(s))
      .catch(() => alive && setSimilar(null));
    return () => {
      alive = false;
    };
  }, [dateA]);

  const refresh = useCallback(async () => {
    if (!dateA || !dateB) return;
    try {
      const [sa, sb] = await Promise.all([summarize(dateA), summarize(dateB)]);
      setA(sa);
      setB(sb);
      setError(null);
    } catch (err) {
      setA(null);
      setB(null);
      setError(
        err instanceof DatasetMissing
          ? "選んだ日のデータがありません。別の日を選んでください。"
          : String(err),
      );
    }
  }, [dateA, dateB]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!dateA || !dateB) return;
    const params = new URLSearchParams();
    params.set("a", dateA);
    params.set("b", dateB);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, [dateA, dateB]);

  if (!loaded) {
    return (
      <main className="wrap">
        <p className="muted">読み込んでいます…</p>
      </main>
    );
  }
  if (!manifest?.date_min) {
    return (
      <main className="wrap">
        <h1>比較</h1>
        <p className="muted">{error ?? "データセットがありません。"}</p>
      </main>
    );
  }

  // 似た日の表に相手が載っていれば、その類似度を出す(自前で計算し直さない)
  const pairScore = similar?.neighbors?.[dateA]?.find((n) => n.date === dateB)?.score;

  return (
    <main className="wrap">
      <h1>比較</h1>
      <p className="lede">
        2 つの日を選んで、全国の観測がどう違ったかを並べます。
      </p>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: "1rem" }}>
        {(
          [
            ["A", dateA, setDateA],
            ["B", dateB, setDateB],
          ] as [string, string, (v: string) => void][]
        ).map(([label, value, set]) => (
          <label key={label} className="card">
            <span className="small muted">日付 {label}</span>
            <br />
            <input
              type="date"
              value={value}
              min={manifest.date_min ?? undefined}
              max={manifest.date_max ?? undefined}
              onChange={(e) => set(e.target.value)}
              aria-label={`日付 ${label}`}
              style={{ marginTop: "0.3rem" }}
            />
            {anomaly?.scores?.[value] !== undefined && (
              <div style={{ marginTop: "0.4rem" }}>
                <span className="badge badge--ai">
                  AI 異常度 {Math.round(anomaly.scores[value])} / 100
                </span>
              </div>
            )}
          </label>
        ))}
      </div>

      {error && <p className="muted">{error}</p>}

      {a && b && (
        <>
          <div className="scroll-x">
            <table>
              <caption className="small muted" style={{ textAlign: "left", paddingBottom: "0.3rem" }}>
                全国の観測地点の平均(A は {a.stations} 地点、B は {b.stations} 地点)。
                差は <span className="badge badge--derived">派生値</span> です。
              </caption>
              <thead>
                <tr>
                  <th>要素</th>
                  <th className="num">{formatJaDate(a.date)}</th>
                  <th className="num">{formatJaDate(b.date)}</th>
                  <th className="num">差(A − B)</th>
                </tr>
              </thead>
              <tbody>
                {WEATHER.map((def) => {
                  const va = a.means[def.id];
                  const vb = b.means[def.id];
                  const diff = va !== null && vb !== null ? va - vb : null;
                  return (
                    <tr key={def.id}>
                      <th scope="row">{def.label}</th>
                      <td className="num">
                        {va === null ? <span className="muted">データなし</span> : formatValue(def, va)}
                      </td>
                      <td className="num">
                        {vb === null ? <span className="muted">データなし</span> : formatValue(def, vb)}
                      </td>
                      <td className="num">
                        {diff === null ? (
                          <span className="muted">—</span>
                        ) : (
                          `${diff > 0 ? "+" : ""}${diff.toFixed(def.digits)} ${def.unit}`
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <h2>AI から見た近さ</h2>
          {pairScore !== undefined ? (
            <p>
              <span className="badge badge--ai">AI 由来</span> この 2 日の表現の
              コサイン類似度は <strong>{(pairScore * 100).toFixed(1)}%</strong> です。
            </p>
          ) : (
            <p className="small muted">
              この 2 日は、似た日の表(各日の上位 10 件・同じ時期どうし)に
              互いが入っていません。似ている度合いが低いか、季節が離れています。
            </p>
          )}

          {similar?.neighbors?.[dateA] && (
            <>
              <h3>{formatJaDate(dateA)} に似た日</h3>
              <ul className="small">
                {similar.neighbors[dateA].slice(0, 6).map((n) => (
                  <li key={n.date}>
                    <a href={`/map/?date=${n.date}`}>{n.date}</a>{" "}
                    <span className="muted">{(n.score * 100).toFixed(1)}%</span>{" "}
                    <button
                      type="button"
                      style={{ fontSize: "0.75rem", padding: "0 0.35rem" }}
                      onClick={() => setDateB(n.date)}
                    >
                      B に入れる
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          {anomaly?.contributions?.[dateA] && (
            <>
              <h3>異常度への寄与({formatJaDate(dateA)})</h3>
              <p className="small muted">
                再構成誤差のうち、どの要素が大きかったかの割合です。
                <strong>原因の説明ではありません。</strong>
              </p>
              <ul className="small">
                {Object.entries(anomaly.contributions[dateA]).map(([k, v]) => (
                  <li key={k}>
                    {k} <span className="muted">{v}%</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </main>
  );
}
