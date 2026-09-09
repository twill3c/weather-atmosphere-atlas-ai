/** 配信データの契約(SPEC §7 / §11)。
 *
 * 出所の 3 区分は画面でも保つ:
 *   OBSERVED   公式の観測値
 *   DERIVED    平均・偏差・補間など、観測から導いた値
 *   AI_DERIVED 埋め込み・異常度・クラスタ
 */
export type DataClass = "OBSERVED" | "DERIVED" | "AI_DERIVED";

export type WeatherVariable =
  | "temperature_mean"
  | "temperature_max"
  | "temperature_min"
  | "rainfall"
  | "wind_speed_mean"
  | "sunshine"
  | "humidity_mean"
  | "snow_depth_max";

export type AirVariable = "pm25" | "no2" | "so2" | "ox";

export interface Manifest {
  dataset_version: string;
  generated_at: string;
  date_min: string;
  date_max: string;
  sources: string[];
  /** 実際に月別ファイルが在る月(YYYY-MM)。UI はこの一覧の外を要求しない。 */
  weather_months: string[];
  air_months: string[];
  counts: {
    weather_stations: number;
    air_stations: number;
    weather_days: number;
  };
  ai?: {
    model_version: string;
    latent_dim: number;
    embedding_days: number;
    clusters: number;
  };
}

export interface StationBase {
  id: string;
  name: string;
  lat: number;
  lon: number;
  elevation_m: number | null;
}

export interface WeatherStation extends StationBase {
  kana: string;
  prefs: string[];
}

export interface AirStation extends StationBase {
  pref_code: string;
  pref_name: string;
}

export interface StationsFile {
  weather: WeatherStation[];
  air: AirStation[];
}

/** 月別の観測値。列指向([日][地点])で持ち、欠測は null。
 *  **欠測を 0 で埋めない**(SPEC F-15)。 */
export interface MonthlyGrid<V extends string> {
  month: string;
  /** その月の日数 */
  days: number;
  /** 列の並び。値の配列の添字はこの順序に対応する */
  stations: string[];
  variables: Partial<Record<V, (number | null)[][]>>;
}

export type WeatherMonth = MonthlyGrid<WeatherVariable>;
export type AirMonth = MonthlyGrid<AirVariable>;

export interface GhgPoint {
  year: number;
  month: number;
  value: number | null;
}

export interface GhgFile {
  source: string;
  source_url: string;
  note: string;
  stations: Record<string, string>;
  units: Record<string, string>;
  series: Record<string, GhgPoint[]>;
  oracle?: {
    description: string;
    url: string;
    station_years_compared: number;
    mismatches: number;
  };
}

/** AI 由来。すべて AI_DERIVED として表示する(SPEC F-14 / §48)。 */
export interface AnomalyFile {
  model_version: string;
  /** 日付 -> 0..100 の百分位。根拠のない確信度は出さない(SPEC §6) */
  scores: Record<string, number>;
  /** 変数別の再構成誤差への寄与(因果ではない — SPEC §29) */
  contributions?: Record<string, Record<string, number>>;
  coverage?: Record<string, number>;
}

export interface SimilarDay {
  date: string;
  score: number;
}

export interface SimilarFile {
  model_version: string;
  /** 既定は季節を考慮した類似(SPEC §27)。自分自身は含めない */
  mode: string;
  neighbors: Record<string, SimilarDay[]>;
}

export interface ClusterStats {
  days: number;
  /** 季節ごとの日数。割り当てから数えた派生値 */
  seasons: Record<string, number>;
  mean_anomaly: number;
}

export interface ClusterFile {
  model_version: string;
  k: number;
  silhouette: number;
  /** k を選ぶ過程。どの k をどのシルエットで比べたかを残す */
  trials?: { k: number; silhouette: number }[];
  note?: string;
  /** クラスタごとの統計。ラベルを人が付けるための材料(SPEC §30) */
  stats?: Record<string, ClusterStats>;
  /** 人間が統計を見てから付ける説明ラベル。モデルは番号しか出さない(SPEC §30) */
  labels: Record<string, string>;
  assignment: Record<string, number>;
}

export interface UmapPoint {
  date: string;
  x: number;
  y: number;
  cluster: number;
  anomaly: number;
}

export interface UmapFile {
  model_version: string;
  points: UmapPoint[];
}
