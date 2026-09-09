"use client";

/** 地図画面(SPEC F-01..F-05, F-14..F-17)。
 *
 * 守ること:
 *   * 欠測は「データなし」と出す。0 と書かない(F-15)
 *   * AI 由来の値は観測値と視覚的に区別する(F-14)
 *   * 表示状態は URL に載せて共有できる(F-17)
 *   * 補間はしない。観測点の無い場所に値を描かない(§6 / §20)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

import {
  DatasetMissing,
  addDays,
  clampDate,
  dayOf,
  formatJaDate,
  loadAirMonth,
  loadAnomaly,
  loadManifest,
  loadStations,
  loadWeatherMonth,
  monthOf,
  sliceDay,
} from "@/lib/data";
import {
  CLASS_LABEL,
  CLASS_MODIFIER,
  GROUP_LABEL,
  LAYERS,
  LAYER_BY_ID,
  formatValue,
  legendStops,
  type LayerId,
} from "@/lib/layers";
import type {
  AirVariable,
  AnomalyFile,
  Manifest,
  StationsFile,
  WeatherVariable,
} from "@/lib/types";
import type { MapPoint } from "@/components/JapanMap";

import "maplibre-gl/dist/maplibre-gl.css";
import "./map.css";

const JapanMap = dynamic(() => import("@/components/JapanMap"), {
  ssr: false,
  loading: () => <div className="map-canvas map-canvas--loading">地図を読み込んでいます…</div>,
});

const WEATHER_IDS = new Set(
  LAYERS.filter((l) => l.group === "weather").map((l) => l.id),
);
const AIR_IDS = new Set(LAYERS.filter((l) => l.group === "air").map((l) => l.id));

const SPEEDS = [
  { label: "1 日 / 0.5 秒", ms: 500 },
  { label: "1 日 / 0.2 秒", ms: 200 },
  { label: "1 日 / 1 秒", ms: 1000 },
];

export default function MapExplorer() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [stations, setStations] = useState<StationsFile | null>(null);
  const [anomaly, setAnomaly] = useState<AnomalyFile | null>(null);
  const [layerId, setLayerId] = useState<LayerId>("temperature_mean");
  const [date, setDate] = useState<string | null>(null);
  const [values, setValues] = useState<Map<string, number>>(new Map());
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, number | null> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(SPEEDS[0].ms);
  const [notice, setNotice] = useState<string | null>(null);
  const [booted, setBooted] = useState(false);

  const layer = LAYER_BY_ID.get(layerId)!;

  // --- 起動: manifest と地点、URL からの復元 --------------------------------
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [m, s] = await Promise.all([loadManifest(), loadStations()]);
        if (!alive) return;
        setManifest(m);
        setStations(s);
        const params = new URLSearchParams(window.location.search);
        const wanted = params.get("date");
        const wantedLayer = params.get("layer") as LayerId | null;
        if (wantedLayer && LAYER_BY_ID.has(wantedLayer)) setLayerId(wantedLayer);
        const fallback = m.date_max ?? m.date_min ?? "";
        setDate(
          wanted && m.date_min && m.date_max
            ? clampDate(wanted, m.date_min, m.date_max)
            : fallback,
        );
      } catch (err) {
        setNotice(
          err instanceof DatasetMissing
            ? "データセットがまだ生成されていません。取り込みと書き出しを実行してください。"
            : String(err),
        );
      } finally {
        if (alive) setBooted(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // AI の異常度は 1 ファイルで足りるので、在るときだけ読む
  useEffect(() => {
    loadAnomaly()
      .then(setAnomaly)
      .catch(() => setAnomaly(null));
  }, []);

  // --- 日付とレイヤに応じた値の読み込み -------------------------------------
  useEffect(() => {
    if (!date || !manifest) return;
    let alive = true;
    const month = monthOf(date);
    (async () => {
      try {
        if (layerId === "anomaly") {
          setValues(new Map());
          setNotice(null);
          return;
        }
        if (WEATHER_IDS.has(layerId)) {
          const grid = await loadWeatherMonth(month);
          if (!alive) return;
          setValues(
            sliceDay(grid.stations, grid.variables[layerId as WeatherVariable], dayOf(date)),
          );
        } else if (AIR_IDS.has(layerId)) {
          const grid = await loadAirMonth(layerId as AirVariable, month);
          if (!alive) return;
          setValues(sliceDay(grid.stations, grid.values, dayOf(date)));
        }
        setNotice(null);
      } catch (err) {
        if (!alive) return;
        setValues(new Map());
        setNotice(
          err instanceof DatasetMissing
            ? `${formatJaDate(date)}の${layer.label}のデータはありません。`
            : String(err),
        );
      }
    })();
    return () => {
      alive = false;
    };
  }, [date, layerId, manifest, layer.label]);

  // --- 再生 -----------------------------------------------------------------
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (!playing || !manifest?.date_max || !date) return;
    timer.current = window.setInterval(() => {
      setDate((cur) => {
        if (!cur) return cur;
        const next = addDays(cur, 1);
        if (manifest.date_max && next > manifest.date_max) {
          setPlaying(false);
          return cur;
        }
        return next;
      });
    }, speedMs);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing, speedMs, manifest, date]);

  // --- URL の同期(共有可能にする F-17) -------------------------------------
  useEffect(() => {
    if (!date) return;
    const params = new URLSearchParams(window.location.search);
    params.set("date", date);
    params.set("layer", layerId);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, [date, layerId]);

  // --- 地点の詳細 -----------------------------------------------------------
  useEffect(() => {
    if (!selected || !date || !WEATHER_IDS.has(layerId)) {
      if (!selected) setDetail(null);
      return;
    }
    let alive = true;
    loadWeatherMonth(monthOf(date))
      .then((grid) => {
        if (!alive) return;
        const idx = grid.stations.indexOf(selected);
        if (idx < 0) {
          setDetail(null);
          return;
        }
        const row: Record<string, number | null> = {};
        for (const def of LAYERS) {
          if (def.group !== "weather") continue;
          const table = grid.variables[def.id as WeatherVariable];
          row[def.id] = table?.[dayOf(date) - 1]?.[idx] ?? null;
        }
        setDetail(row);
      })
      .catch(() => setDetail(null));
    return () => {
      alive = false;
    };
  }, [selected, date, layerId]);

  const activeStations = useMemo(() => {
    if (!stations) return [];
    return AIR_IDS.has(layerId) ? stations.air : stations.weather;
  }, [stations, layerId]);

  const points: MapPoint[] = useMemo(() => {
    if (layerId === "anomaly") return [];
    return activeStations.map((s) => ({
      ...s,
      value: values.has(s.id) ? values.get(s.id)! : null,
    }));
  }, [activeStations, values, layerId]);

  const withData = points.filter((p) => p.value !== null).length;
  const coverage = points.length ? withData / points.length : 0;
  const anomalyToday = date ? anomaly?.scores?.[date] : undefined;

  const step = useCallback(
    (delta: number) => {
      if (!date || !manifest?.date_min || !manifest?.date_max) return;
      setDate(clampDate(addDays(date, delta), manifest.date_min, manifest.date_max));
    },
    [date, manifest],
  );

  const selectedStation = activeStations.find((s) => s.id === selected) ?? null;

  if (!booted) {
    return (
      <main className="wrap wrap--wide">
        <p className="muted">読み込んでいます…</p>
      </main>
    );
  }

  if (!manifest || !manifest.date_min) {
    return (
      <main className="wrap wrap--wide">
        <h1>地図</h1>
        <p className="muted">{notice ?? "データセットがありません。"}</p>
        <p className="small muted">
          取り込みと書き出しの手順は README を参照してください。
        </p>
      </main>
    );
  }

  return (
    <main className="map-shell">
      <aside className="map-side" aria-label="レイヤ">
        <h1 className="map-title">地図</h1>
        <p className="small muted map-intro">
          過去の観測を日付で切り替えて見ます。<strong>予報ではありません。</strong>
        </p>

        {(["weather", "air", "ai"] as const).map((group) => (
          <section key={group} className="map-group">
            <h2 className="map-group__title">{GROUP_LABEL[group]}</h2>
            <div className="map-group__items">
              {LAYERS.filter((l) => l.group === group).map((l) => (
                <button
                  key={l.id}
                  type="button"
                  aria-pressed={l.id === layerId}
                  onClick={() => setLayerId(l.id)}
                  className="map-layer-btn"
                >
                  {l.label}
                </button>
              ))}
            </div>
          </section>
        ))}

        <section className="map-group">
          <h2 className="map-group__title">凡例</h2>
          <div className="legend" aria-label={`${layer.label}の凡例`}>
            {legendStops(layer).map((stop) => (
              <div key={stop.label} className="legend__item">
                <span
                  className="legend__swatch"
                  style={{ background: stop.color }}
                  aria-hidden="true"
                />
                <span className="legend__label">{stop.label}</span>
              </div>
            ))}
          </div>
          <p className="small muted legend__unit">単位: {layer.unit}</p>
          <p className="small muted">
            <span className="legend__missing" aria-hidden="true" />
            輪郭だけの点は<strong>データなし</strong>です(0 ではありません)。
          </p>
        </section>
      </aside>

      <section className="map-main">
        <div className="map-bar">
          <span className={`badge badge--${CLASS_MODIFIER[layer.dataClass]}`}>
            {CLASS_LABEL[layer.dataClass]}
          </span>
          <strong>{layer.label}</strong>
          <span className="muted small">
            {date ? formatJaDate(date) : ""}
          </span>
          <span className="muted small">
            観測のあった地点 {withData} / {points.length}
            （被覆 {(coverage * 100).toFixed(0)}%）
          </span>
          {anomalyToday !== undefined && (
            <span className="badge badge--ai" title="Autoencoder の再構成誤差の百分位">
              AI 異常度 {Math.round(anomalyToday)} / 100
            </span>
          )}
        </div>

        {notice && <p className="map-notice">{notice}</p>}

        {layerId === "anomaly" ? (
          <div className="map-canvas map-canvas--message">
            <div>
              <p>
                <span className="badge badge--ai">AI 由来</span>
              </p>
              <p className="muted">
                異常度は「その日の全国の気象が、学習した並びからどれだけ外れているか」を
                日単位で表す値です。地点ごとの量ではないので、地図の色ではなく
                上のバーに数値で出しています。
              </p>
              <p className="muted small">
                {anomaly
                  ? "パターン画面で年ごとの並びを見られます。"
                  : "AI 資産がまだ生成されていません。"}
              </p>
            </div>
          </div>
        ) : (
          <JapanMap
            points={points}
            layer={layer}
            selectedId={selected}
            onSelect={setSelected}
          />
        )}

        <div className="map-timeline">
          <button type="button" onClick={() => step(-1)} aria-label="前の日">
            ◀
          </button>
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            aria-label={playing ? "停止" : "再生"}
          >
            {playing ? "停止" : "再生"}
          </button>
          <button type="button" onClick={() => step(1)} aria-label="次の日">
            ▶
          </button>
          <input
            type="date"
            value={date ?? ""}
            min={manifest.date_min ?? undefined}
            max={manifest.date_max ?? undefined}
            onChange={(e) => setDate(e.target.value)}
            aria-label="日付"
          />
          <input
            className="map-timeline__range"
            type="range"
            min={0}
            max={daysBetween(manifest.date_min!, manifest.date_max!)}
            value={date ? daysBetween(manifest.date_min!, date) : 0}
            onChange={(e) =>
              setDate(addDays(manifest.date_min!, Number(e.target.value)))
            }
            aria-label="日付スライダー"
          />
          <select
            value={speedMs}
            onChange={(e) => setSpeedMs(Number(e.target.value))}
            aria-label="再生速度"
          >
            {SPEEDS.map((s) => (
              <option key={s.ms} value={s.ms}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {selectedStation && (
          <div className="map-detail card">
            <div className="map-detail__head">
              <strong>{selectedStation.name}</strong>
              <span className="muted small">
                {selectedStation.lat.toFixed(3)}, {selectedStation.lon.toFixed(3)}
                {selectedStation.elevation_m !== null &&
                  ` / 標高 ${selectedStation.elevation_m} m`}
              </span>
              <button type="button" onClick={() => setSelected(null)} aria-label="閉じる">
                閉じる
              </button>
            </div>
            {detail ? (
              <div className="scroll-x">
                <table>
                  <tbody>
                    {LAYERS.filter((l) => l.group === "weather").map((l) => (
                      <tr key={l.id}>
                        <th scope="row">{l.label}</th>
                        <td className="num">
                          {detail[l.id] === null ? (
                            <span className="muted">データなし</span>
                          ) : (
                            formatValue(l, detail[l.id])
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted small">
                {AIR_IDS.has(layerId)
                  ? `${formatValue(layer, values.get(selectedStation.id) ?? null)}`
                  : "この地点の詳細はありません。"}
              </p>
            )}
          </div>
        )}

        <p className="small muted map-credit">
          データ: 気象庁 / 国立環境研究所 環境展望台(いずれも加工して作成) ・ 地図:{" "}
          <a href="https://maps.gsi.go.jp/development/ichiran.html">地理院タイル</a> ・{" "}
          <a href="/data-policy/">データの出典</a>
        </p>
      </section>
    </main>
  );
}

function daysBetween(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  return Math.round((b - a) / 86400000);
}
