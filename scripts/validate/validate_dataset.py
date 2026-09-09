"""取り込んだデータを検証する(SPEC §9 / 構想書 §64)。

    .venv/Scripts/python scripts/validate/validate_dataset.py

**外れ値を即座に除かない。** 極値そのものが対象なので、疑わしい値は
「疑い」として数え、範囲を外れたものだけを失敗にする。
文書に書いた数を守るものは何も無いので、**この工程で数を取り直して突き合わせる**
(HC-152)。
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa.domain import filter_domestic, in_japan           # noqa: E402
from jwaa.nies import SUSPECT_FLOOR, is_suspect             # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

#: 物理的にありえない値。**これを外れたら失敗**。極端だが実在する値は通す。
#: 日本の観測記録の実績を余裕をもって囲む(最高 41.1 度・最低 -41.0 度・
#: 日降水量 1,317 mm・最大瞬間風速 85.3 m/s・最深積雪 1,182 cm)。
RANGES = {
    "temperature_mean": (-45.0, 42.0),
    "temperature_max": (-40.0, 45.0),
    "temperature_min": (-50.0, 40.0),
    "rainfall": (0.0, 1500.0),
    "wind_speed_mean": (0.0, 60.0),
    "wind_speed_max": (0.0, 95.0),
    "wind_gust": (0.0, 110.0),
    "sunshine": (0.0, 24.0),
    "humidity_mean": (0.0, 100.0),
    "humidity_min": (0.0, 100.0),
    "snowfall": (0.0, 400.0),
    "snow_depth_max": (0.0, 1300.0),
    # 現地気圧は標高で決まるので、定数の範囲では測れない。下の
    # `expected_local_pressure` で標高から求めて当てる。
    "pressure_sea": (850.0, 1080.0),
}

# --- 大気汚染の範囲について ------------------------------------------------
#
# ここは「壊れていると言い切れる」外側の範囲である。雑音と測定系の異常は
# `SUSPECT_FLOOR` で分けるので、この範囲はそれより外に置く。
# 疑わしい値を即座に削らない(構想書 §64 —— 極値そのものが対象でありうる)。
#
# (1) **検出限界付近では負の値が出る。** 実測 2026-09-10(PM2.5 日別値 2,739,979 件):
#     負値は pm25 5,834(0.213%)/ so2 1,414(0.053%)/ no2 19(0.000%)/ ox 0。
#     大きさの分布は -1 以上 3,850・-5〜-1 1,674・-10〜-5 38・-20〜-10 4・-20 未満 2 で、
#     **99.9998% が -10 より上**。0 に丸めると平均が上に偏るのでそのまま採る。
#
# (2) **SO2 の上限は火山性の噴煙を通す。** 実測 2026-09-10: 日平均が 100 ppb を
#     超えた 114 件のうち 113 件が鹿児島県の桜島周辺 4 局(有村・赤水・黒神・
#     桜島支所)に集中し、最大は有村の 1,780.2 ppb(2015-01-23)。
#     残る 1 件は箱根町宮城野の 107.2 ppb(2015-07-14)で、箱根の 2015 年の噴火期に
#     あたる。火山を「壊れた値」として捨てない。
AIR_RANGES = {
    "pm25": (-100.0, 1000.0),
    "no2": (-100.0, 500.0),
    "so2": (-100.0, 2500.0),
    "ox": (-100.0, 500.0),
}

#: 気圧の許容幅。天気による変動はせいぜい ±60 hPa なので、余裕をみて ±80。
PRESSURE_TOLERANCE = 80.0


def expected_local_pressure(elevation_m: float) -> float:
    """標準大気の気圧(高度 h m)。国際標準大気の式。

    実測 2026-09-10: 富士山(標高 3,775.1 m)の現地気圧は 605.9〜655.8 hPa で、
    この式の予想 634.7 hPa を挟む。奥日光(1,291.9 m)は 844.8〜849.7 hPa に対し
    予想 867.4 hPa。どちらも誤りではなく標高の効果である。
    """
    return 1013.25 * (1 - 2.25577e-5 * elevation_m) ** 5.25588

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def check_stations() -> list[dict]:
    path = PROCESSED / "jma_stations.json"
    stations = json.loads(path.read_text(encoding="utf-8"))["stations"]
    active = [s for s in stations if s["kind"] == "s" and s["active"]]
    domestic = filter_domestic(active)
    print(f"地点: 全 {len(stations):,} / 現役官署 {len(active)} / 国内 {len(domestic)}")

    for s in stations:
        if not (-90 <= s["lat"] <= 90) or not (-180 <= s["lon"] <= 180):
            fail(f"座標が範囲外: {s['block_no']} {s['name']}")
    for s in domestic:
        if not in_japan(s["lat"], s["lon"]):
            fail(f"国内としたのに矩形外: {s['block_no']} {s['name']}")

    ids = [s["block_no"] for s in stations]
    if len(ids) != len(set(ids)):
        dup = [k for k, v in collections.Counter(ids).items() if v > 1]
        fail(f"block_no が重複: {dup}")
    return domestic


def check_weather(domestic: list[dict]) -> None:
    known = {s["block_no"] for s in domestic}
    files = sorted((PROCESSED / "weather").glob("*.jsonl"))
    print(f"気象: ファイル {len(files)}")
    if not files:
        warn("気象の取り込みがまだ無い")
        return

    by_block = {s["block_no"]: s for s in domestic}
    out_of_range: collections.Counter = collections.Counter()
    total = 0
    dates_per_station: dict[str, set] = {}
    pressure_dev: list[tuple[str, float]] = []
    for path in files:
        if path.stem not in known:
            warn(f"国内の官署でないファイル: {path.name}")
        station = by_block.get(path.stem)
        elev = (station or {}).get("elevation_m")
        p_expected = (expected_local_pressure(elev) if elev is not None else None)
        seen = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            total += 1
            if rec["date"] in seen:
                fail(f"{path.stem} に同じ日が二度: {rec['date']}")
            seen.add(rec["date"])
            for var, (lo, hi) in RANGES.items():
                v = rec.get(var)
                if v is None:
                    continue
                if not (lo <= v <= hi):
                    out_of_range[var] += 1
                    if out_of_range[var] <= 3:
                        fail(f"{var} が範囲外: {v} ({path.stem} {rec['date']})")
            # 現地気圧は標高から求めた予想と比べる
            pv = rec.get("pressure_local")
            if pv is not None and p_expected is not None:
                dev = pv - p_expected
                if abs(dev) > PRESSURE_TOLERANCE:
                    out_of_range["pressure_local"] += 1
                    if out_of_range["pressure_local"] <= 3:
                        fail(f"現地気圧が標高から見て外れる: {pv} hPa "
                             f"(標高 {elev} m の予想 {p_expected:.1f} hPa、"
                             f"差 {dev:+.1f}) {path.stem} {rec['date']}")
                pressure_dev.append((path.stem, dev))
        dates_per_station[path.stem] = seen

    if pressure_dev:
        devs = [d for _, d in pressure_dev]
        print(f"  現地気圧と標準大気の差: 最小 {min(devs):+.1f} / "
              f"最大 {max(devs):+.1f} hPa(n={len(devs):,})")

    print(f"  地点日 {total:,}")
    if out_of_range:
        fail(f"範囲外の値: {dict(out_of_range)}")

    lengths = collections.Counter(len(v) for v in dates_per_station.values())
    print(f"  1 地点あたりの日数の分布: {dict(sorted(lengths.items()))}")
    if len(lengths) > 1:
        warn(f"地点によって日数が違う: {dict(sorted(lengths.items()))}")

    # 気温の順序。最低 <= 平均 <= 最高 が崩れたら読み違えている。
    bad_order = 0
    for path in files[: min(len(files), 40)]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            lo, mid, hi = (r.get("temperature_min"), r.get("temperature_mean"),
                           r.get("temperature_max"))
            if None in (lo, mid, hi):
                continue
            if not (lo <= mid <= hi):
                bad_order += 1
                if bad_order <= 3:
                    fail(f"気温の順序が崩れた: {path.stem} {r['date']} "
                         f"min={lo} mean={mid} max={hi}")
    print(f"  気温の順序(最低<=平均<=最高)の違反: {bad_order}")


def check_air() -> None:
    path = PROCESSED / "nies_stations.json"
    if not path.exists():
        warn("大気の測定局マスタがまだ無い")
        return
    stations = json.loads(path.read_text(encoding="utf-8"))["stations"]
    print(f"大気: 測定局 {len(stations):,}")
    for s in stations:
        if not in_japan(s["lat"], s["lon"]):
            fail(f"測定局が国内の矩形外: {s['code']} {s['name']} "
                 f"({s['lat']}, {s['lon']})")
        if s["code"][:2] != s["pref_code"]:
            fail(f"測定局コードの先頭 2 桁と県コードが違う: "
                 f"{s['code']} vs {s['pref_code']}")

    air_dir = PROCESSED / "air"
    if not air_dir.exists():
        warn("大気の日別値がまだ無い")
        return
    counts: collections.Counter = collections.Counter()
    out_of_range: collections.Counter = collections.Counter()
    negative: collections.Counter = collections.Counter()
    suspect: collections.Counter = collections.Counter()
    suspect_examples: list[str] = []
    for p in sorted(air_dir.rglob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for code, by_item in data.items():
            for item, series in by_item.items():
                lo, hi = AIR_RANGES.get(item, (None, None))
                for date, v in series.items():
                    counts[item] += 1
                    if v is None or lo is None:
                        continue
                    if v < 0:
                        negative[item] += 1
                    if is_suspect(item, v):
                        suspect[item] += 1
                        suspect_examples.append(f"{item} {v} ({code} {date})")
                    if not (lo <= v <= hi):
                        out_of_range[item] += 1
                        if sum(out_of_range.values()) <= 3:
                            fail(f"{item} が範囲外: {v} ({code} {date})")
    print(f"  日別値 {sum(counts.values()):,} {dict(counts)}")
    # 負値は検出限界付近の雑音。0 に丸めると平均が上に偏るのでそのまま採るが、
    # **黙って通さず数える**。割合が跳ねたら測定系の変化を疑う手がかりになる。
    if negative:
        share = {k: f"{v:,}({v / counts[k]:.3%})" for k, v in sorted(negative.items())}
        print(f"  検出限界付近の負値: {share}")
        for item, n in negative.items():
            if n / counts[item] > 0.02:
                warn(f"{item} の負値が 2% を超えた({n:,}/{counts[item]:,})。"
                     f"測定系の変化を疑う")
    if suspect:
        # 配信と特徴量からは外れるが、生の日別値には残す。数だけは必ず出す。
        print(f"  suspect(検出限界の雑音では説明がつかない値・"
              f"下限 {SUSPECT_FLOOR}): {dict(suspect)}")
        for ex in suspect_examples[:6]:
            print(f"      {ex}")
        warn(f"suspect が {sum(suspect.values())} 件。配信からは外している")
    if out_of_range:
        fail(f"範囲外の大気の値: {dict(out_of_range)}")


def check_ghg() -> None:
    path = PROCESSED / "ghg_monthly.json"
    if not path.exists():
        warn("温室効果ガスがまだ無い")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"温室効果ガス: 系列 {len(data['series'])}")
    for key, rows in data["series"].items():
        species = key.split(":")[0]
        lo, hi = (250.0, 600.0) if species == "co2" else (1200.0, 2600.0)
        keys = [(r["year"], r["month"]) for r in rows]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            fail(f"{key} の時刻が単調増加でない")
        for r in rows:
            v = r["value"]
            if v is None:
                continue
            if not (lo <= v <= hi):
                fail(f"{key} の値が範囲外: {v} ({r['year']}-{r['month']:02d})")
    oracle = data.get("oracle")
    if oracle:
        print(f"  公表年平均との照合: {oracle['station_years_compared']} 観測点年 / "
              f"不一致 {oracle['mismatches']}")
        if oracle["mismatches"] != 0:
            fail(f"公表年平均と不一致 {oracle['mismatches']} 件")
    else:
        warn("公表年平均との照合の記録が無い")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="警告も失敗として扱う")
    args = ap.parse_args()

    domestic = check_stations()
    check_weather(domestic)
    check_air()
    check_ghg()

    print()
    for w in warnings:
        print(f"  警告: {w}")
    if failures:
        print(f"\n検証 NG {len(failures)} 件:")
        for f in failures[:20]:
            print(f"  {f}")
        return 1
    if args.strict and warnings:
        print(f"\n--strict のため警告 {len(warnings)} 件を失敗とする")
        return 1
    print(f"検証 OK(警告 {len(warnings)} 件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
