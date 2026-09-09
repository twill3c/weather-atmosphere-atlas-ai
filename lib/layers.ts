/** レイヤの定義と色(SPEC §9 / §62)。
 *
 * 色は連続量には連続スケール、量的な累積量には単一色系列を使う。
 * **「赤 = 危険」と固定的に意味づけない**(§62)。異常度は色だけで伝えず、
 * 数値と語を必ず併記する(N-05)。
 */
import type { AirVariable, DataClass, WeatherVariable } from "./types";

export type LayerId = WeatherVariable | AirVariable | "anomaly";

export interface LayerDef {
  id: LayerId;
  group: "weather" | "air" | "ai";
  label: string;
  unit: string;
  dataClass: DataClass;
  /** 色付けの下端・上端。実データの分布から決めた(下の note を参照) */
  domain: [number, number];
  scale: "diverging" | "sequential";
  /** 値の丸め桁 */
  digits: number;
}

/** 色域は 2026-09-09 時点の取り込み済みデータの分位から決めた暫定値。
 *  データが増えたら `scripts/validate/report_ranges.py` で測り直す。 */
export const LAYERS: LayerDef[] = [
  {
    id: "temperature_mean", group: "weather", label: "平均気温",
    unit: "℃", dataClass: "OBSERVED", domain: [-10, 32],
    scale: "diverging", digits: 1,
  },
  {
    id: "temperature_max", group: "weather", label: "最高気温",
    unit: "℃", dataClass: "OBSERVED", domain: [-5, 38],
    scale: "diverging", digits: 1,
  },
  {
    id: "temperature_min", group: "weather", label: "最低気温",
    unit: "℃", dataClass: "OBSERVED", domain: [-15, 28],
    scale: "diverging", digits: 1,
  },
  {
    id: "rainfall", group: "weather", label: "降水量",
    unit: "mm", dataClass: "OBSERVED", domain: [0, 80],
    scale: "sequential", digits: 1,
  },
  {
    id: "wind_speed_mean", group: "weather", label: "平均風速",
    unit: "m/s", dataClass: "OBSERVED", domain: [0, 12],
    scale: "sequential", digits: 1,
  },
  {
    id: "sunshine", group: "weather", label: "日照時間",
    unit: "h", dataClass: "OBSERVED", domain: [0, 13],
    scale: "sequential", digits: 1,
  },
  {
    id: "humidity_mean", group: "weather", label: "平均湿度",
    unit: "%", dataClass: "OBSERVED", domain: [20, 100],
    scale: "sequential", digits: 0,
  },
  {
    id: "snow_depth_max", group: "weather", label: "最深積雪",
    unit: "cm", dataClass: "OBSERVED", domain: [0, 120],
    scale: "sequential", digits: 0,
  },
  {
    id: "pm25", group: "air", label: "PM2.5",
    unit: "µg/m³", dataClass: "OBSERVED", domain: [0, 45],
    scale: "sequential", digits: 1,
  },
  {
    id: "no2", group: "air", label: "二酸化窒素 NO₂",
    unit: "ppb", dataClass: "OBSERVED", domain: [0, 40],
    scale: "sequential", digits: 1,
  },
  {
    id: "so2", group: "air", label: "二酸化硫黄 SO₂",
    unit: "ppb", dataClass: "OBSERVED", domain: [0, 12],
    scale: "sequential", digits: 1,
  },
  {
    id: "ox", group: "air", label: "光化学オキシダント Ox",
    unit: "ppb", dataClass: "OBSERVED", domain: [0, 80],
    scale: "sequential", digits: 1,
  },
  {
    id: "anomaly", group: "ai", label: "AI 異常度",
    unit: "/100", dataClass: "AI_DERIVED", domain: [0, 100],
    scale: "sequential", digits: 0,
  },
];

export const LAYER_BY_ID = new Map(LAYERS.map((l) => [l.id, l]));

export const GROUP_LABEL: Record<LayerDef["group"], string> = {
  weather: "気象",
  air: "大気汚染",
  ai: "AI",
};

export const CLASS_LABEL: Record<DataClass, string> = {
  OBSERVED: "観測値",
  DERIVED: "派生値",
  AI_DERIVED: "AI 由来",
};

export const CLASS_MODIFIER: Record<DataClass, string> = {
  OBSERVED: "observed",
  DERIVED: "derived",
  AI_DERIVED: "ai",
};

const SEQUENTIAL = ["#e8eef4", "#c3d8e8", "#93b9d6", "#5f95bf", "#3a74a3", "#1f5382"];
// 発散スケール(寒色 -> 暖色)。中央は淡い灰にして、正負の別が形でも分かるようにする。
const DIVERGING = [
  "#2f6fa8", "#5e9bc6", "#a8c8de", "#e9e6df", "#f2c496", "#dd8b47", "#b7521a",
];

function clamp01(t: number) {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/** 値 -> 色。欠測は呼び手が別に扱う(色を与えない)。 */
export function colorFor(layer: LayerDef, value: number): string {
  const [lo, hi] = layer.domain;
  const t = clamp01((value - lo) / (hi - lo));
  const ramp = layer.scale === "diverging" ? DIVERGING : SEQUENTIAL;
  const idx = Math.min(ramp.length - 1, Math.floor(t * ramp.length));
  return ramp[idx];
}

/** 凡例の刻み。色だけに頼らないよう、必ず数値を添えて出す。 */
export function legendStops(layer: LayerDef): { color: string; label: string }[] {
  const [lo, hi] = layer.domain;
  const ramp = layer.scale === "diverging" ? DIVERGING : SEQUENTIAL;
  return ramp.map((color, i) => {
    const v = lo + ((hi - lo) * i) / (ramp.length - 1);
    return { color, label: v.toFixed(layer.digits) };
  });
}

export function formatValue(layer: LayerDef, value: number | null | undefined) {
  if (value === null || value === undefined) return "データなし";
  return `${value.toFixed(layer.digits)} ${layer.unit}`;
}
