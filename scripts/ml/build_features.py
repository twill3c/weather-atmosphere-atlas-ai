"""日別の特徴量を作る(SPEC §8 / §22 / 構想書 §99)。

守ること:
  * **季節性を除く。** 気温は day-of-year の気候値からの偏差にする。
    生の絶対値を入れると、埋め込みは「その日が何月か」を測るだけになる。
  * **欠測を 0 で埋めない。** 補完値と欠測マスクを連結して渡す(§22.3)。
  * **気候値は学習期間だけから作る。** 検証・試験の期間を混ぜると漏れになる。
  * 地点は都道府県に集約する。気象官署と大気測定局は分布が違うので、
    同じ土俵に載せてから結合する(SPEC §8)。

    python scripts/ml/build_features.py
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa.nies import is_suspect                            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "features.npz"

WEATHER_VARS = [
    "temperature_mean", "temperature_max", "temperature_min",
    "rainfall", "wind_speed_mean", "sunshine", "humidity_mean",
]
#: 平年偏差にする変数(季節性が強いもの)
ANOMALY_VARS = {"temperature_mean", "temperature_max", "temperature_min",
                "sunshine", "humidity_mean"}
#: log1p を掛ける変数(裾が長いもの)
LOG_VARS = {"rainfall"}
AIR_VARS = ["pm25", "no2", "so2", "ox"]

PREFS = [f"{i:02d}" for i in range(1, 48)]


def load_station_prefs() -> dict[str, str]:
    path = PROCESSED / "station_prefectures.json"
    data = json.loads(path.read_text(encoding="utf-8"))["stations"]
    return {k: v["pref_code"] for k, v in data.items()}


def load_weather_by_pref(station_pref: dict[str, str]):
    """date -> pref -> var -> [値] を作る。"""
    table: dict[str, dict[str, dict[str, list[float]]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    files = sorted((PROCESSED / "weather").glob("*.jsonl"))
    for path in files:
        pref = station_pref.get(path.stem)
        if pref is None:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            for var in WEATHER_VARS:
                v = rec.get(var)
                if v is not None:
                    table[rec["date"]][pref][var].append(v)
    return table, len(files)


def load_air_by_pref():
    """date -> pref -> var -> [値]。測定局コードの先頭 2 桁が都道府県。"""
    table: dict[str, dict[str, dict[str, list[float]]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    air_dir = PROCESSED / "air"
    if not air_dir.exists():
        return table
    for path in sorted(air_dir.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for code, by_item in data.items():
            pref = code[:2]
            for item, series in by_item.items():
                if item not in AIR_VARS:
                    continue
                for date, value in series.items():
                    if value is not None and not is_suspect(item, value):
                        table[date][pref][item].append(value)
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-end", default="2020-12-31",
                    help="気候値をこの日までのデータだけから作る")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--min-prefs", type=int, default=40,
                    help="この数の都道府県に気象が無い日は捨てる")
    args = ap.parse_args()

    station_pref = load_station_prefs()
    weather, n_files = load_weather_by_pref(station_pref)
    air = load_air_by_pref()
    print(f"気象: 地点ファイル {n_files} / 日数 {len(weather):,}")
    print(f"大気: 日数 {len(air):,}")

    # 日ごとに都道府県平均を取る
    dates = sorted(weather)
    usable = []
    for d in dates:
        covered = sum(1 for p in PREFS if weather[d][p].get("temperature_mean"))
        if covered >= args.min_prefs:
            usable.append(d)
    print(f"都道府県 {args.min_prefs} 以上に気温がある日: {len(usable):,} / {len(dates):,}")
    if not usable:
        raise SystemExit("使える日がない。取り込みが終わっているか確認する")

    columns: list[str] = []
    for var in WEATHER_VARS:
        columns += [f"w:{var}:{p}" for p in PREFS]
    has_air = bool(air)
    if has_air:
        for var in AIR_VARS:
            columns += [f"a:{var}:{p}" for p in PREFS]

    n, m = len(usable), len(columns)
    raw = np.full((n, m), np.nan, dtype=np.float64)
    for i, d in enumerate(usable):
        j = 0
        for var in WEATHER_VARS:
            for p in PREFS:
                vals = weather[d][p].get(var)
                if vals:
                    raw[i, j] = float(np.mean(vals))
                j += 1
        if has_air:
            for var in AIR_VARS:
                for p in PREFS:
                    vals = air.get(d, {}).get(p, {}).get(var)
                    if vals:
                        raw[i, j] = float(np.mean(vals))
                    j += 1

    mask = np.isfinite(raw)
    print(f"行列 {raw.shape} / 観測のある割合 {mask.mean():.3f}")

    # --- 変換: log1p と 平年偏差 ---------------------------------------------
    doy = np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in usable])
    is_train = np.array([d <= args.train_end for d in usable])
    print(f"気候値の母集団: {is_train.sum():,} 日({usable[0]} 〜 {args.train_end})")

    work = raw.copy()
    for j, col in enumerate(columns):
        var = col.split(":")[1]
        if var in LOG_VARS:
            work[:, j] = np.log1p(np.clip(work[:, j], 0, None))

    # day-of-year の気候値。前後 7 日の窓で平滑化し、学習期間だけから作る。
    clim_mean = np.full((367, m), np.nan)
    clim_std = np.full((367, m), np.nan)
    for day in range(1, 367):
        diff = np.abs(doy - day)
        near = np.minimum(diff, 366 - diff) <= 7
        sel = near & is_train
        if sel.sum() < 5:
            sel = near
        block = work[sel]
        with np.errstate(invalid="ignore"):
            clim_mean[day] = np.nanmean(np.where(np.isfinite(block), block, np.nan), axis=0)
            clim_std[day] = np.nanstd(np.where(np.isfinite(block), block, np.nan), axis=0)

    feats = work.copy()
    for j, col in enumerate(columns):
        var = col.split(":")[1]
        if var in ANOMALY_VARS:
            mu = clim_mean[doy, j]
            sd = clim_std[doy, j]
            sd = np.where(np.isfinite(sd) & (sd > 1e-6), sd, 1.0)
            feats[:, j] = (feats[:, j] - mu) / sd

    # 標準化は学習期間の統計で(漏れを作らない)
    train_block = np.where(mask & is_train[:, None], feats, np.nan)
    with np.errstate(invalid="ignore"):
        col_mean = np.nanmean(train_block, axis=0)
        col_std = np.nanstd(train_block, axis=0)
    col_mean = np.where(np.isfinite(col_mean), col_mean, 0.0)
    col_std = np.where(np.isfinite(col_std) & (col_std > 1e-6), col_std, 1.0)
    z = (feats - col_mean) / col_std

    # 欠測は 0 で埋めるが、**同時にマスクを渡す**ので「0 という観測」とは区別される
    x = np.where(mask, z, 0.0)
    x = np.clip(x, -8, 8)

    # 季節の位相。偏差を取っても残る年周の効果を明示的に渡す。
    month_sin = np.sin(2 * np.pi * doy / 365.25)
    month_cos = np.cos(2 * np.pi * doy / 365.25)

    matrix = np.hstack([x, mask.astype(np.float64),
                        month_sin[:, None], month_cos[:, None]]).astype(np.float32)
    feature_names = (columns + [f"mask:{c}" for c in columns]
                     + ["season_sin", "season_cos"])
    assert matrix.shape[1] == len(feature_names)
    assert np.isfinite(matrix).all(), "特徴量に非有限値が残っている"

    out_path = pathlib.Path(args.out)
    np.savez_compressed(
        out_path,
        matrix=matrix,
        dates=np.array(usable),
        columns=np.array(columns),
        feature_names=np.array(feature_names),
        mask=mask,
        raw=raw.astype(np.float32),
        train_end=np.array(args.train_end),
    )
    print(f"特徴量 {matrix.shape} (値 {m} + マスク {m} + 季節 2)")
    print(f"-> {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
