/** 配信データの読み込み(SPEC §39 / §40)。
 *
 * すべて静的 asset の fetch。API ルートは持たない(N-01)。
 * 月別ファイルは LRU で持ち、上限を超えたら古いものから捨てる(§40)。
 */
import type {
  AirMonth,
  AirVariable,
  AnomalyFile,
  ClusterFile,
  GhgFile,
  Manifest,
  SimilarFile,
  StationsFile,
  UmapFile,
  WeatherMonth,
} from "./types";

const BASE = "/data";
const MAX_CACHED_MONTHS = 24;

const cache = new Map<string, unknown>();

function remember<T>(key: string, value: T): T {
  cache.set(key, value);
  while (cache.size > MAX_CACHED_MONTHS) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
  return value;
}

async function getJson<T>(path: string): Promise<T> {
  const hit = cache.get(path);
  if (hit !== undefined) return hit as T;
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new DatasetMissing(`${BASE}${path}`, res.status);
  }
  return remember(path, (await res.json()) as T);
}

/** 「そのデータが無い」ことを、通信の失敗と区別できる形にする(SPEC F-15 / §68)。 */
export class DatasetMissing extends Error {
  readonly url: string;
  readonly status: number;
  constructor(url: string, status: number) {
    super(`データがありません: ${url} (HTTP ${status})`);
    this.name = "DatasetMissing";
    this.url = url;
    this.status = status;
  }
}

export const loadManifest = () => getJson<Manifest>("/manifest.json");
export const loadStations = () => getJson<StationsFile>("/stations.json");
export const loadGhg = () => getJson<GhgFile>("/ghg/monthly.json");

export const loadWeatherMonth = (month: string) =>
  getJson<WeatherMonth>(`/weather/${month}.json`);

/** 大気は物質ごとに別ファイル。測っている局だけが列に入る。 */
export const loadAirMonth = (variable: AirVariable, month: string) =>
  getJson<AirMonth & { variable: AirVariable; values: (number | null)[][] }>(
    `/air/${variable}/${month}.json`,
  );

export const loadAnomaly = () => getJson<AnomalyFile>("/ai/anomaly.json");
/** 類似日は年ごとに分けて配る(1 ファイルにすると 1.4 MB になる — N-03)。 */
export const loadSimilar = (year: string) =>
  getJson<SimilarFile>(`/ai/similar/${year}.json`);
export const loadClusters = () => getJson<ClusterFile>("/ai/clusters.json");
export const loadUmap = () => getJson<UmapFile>("/ai/umap.json");

// --- 日付の道具 -------------------------------------------------------------

export const monthOf = (date: string) => date.slice(0, 7);
export const dayOf = (date: string) => Number(date.slice(8, 10));

export function addDays(date: string, delta: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

export function clampDate(date: string, min: string, max: string): string {
  if (date < min) return min;
  if (date > max) return max;
  return date;
}

export function formatJaDate(date: string): string {
  const [y, m, d] = date.split("-");
  return `${y}年${Number(m)}月${Number(d)}日`;
}

/** 月別格子から、ある日の値を地点 ID で引ける表にする。 */
export function sliceDay(
  stations: string[],
  table: (number | null)[][] | undefined,
  day: number,
): Map<string, number> {
  const out = new Map<string, number>();
  if (!table) return out;
  const row = table[day - 1];
  if (!row) return out;
  for (let i = 0; i < stations.length; i += 1) {
    const v = row[i];
    if (v !== null && v !== undefined) out.set(stations[i], v);
  }
  return out;
}
