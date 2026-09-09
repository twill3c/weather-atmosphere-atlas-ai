"""取り込んだデータを Web 配信用の静的資産にする(SPEC §11 / N-02, N-03)。

    python scripts/export/build_web_assets.py

配るもの:
    public/data/manifest.json          期間・件数・出典(実データから生成する)
    public/data/stations.json          気象官署と大気測定局の位置
    public/data/weather/YYYY-MM.json   月別の観測値(列指向・欠測は null)
    public/data/air/YYYY-MM.json       同上(大気汚染)
    public/data/ghg/monthly.json       温室効果ガスの月別値

**巨大な JSON は作らない**(N-03)。月で割る。欠測は 0 で埋めず null にする(F-15)。
manifest の日付は固定値をコードに書かず、実データから求める(構想書 §11.2)。
"""
from __future__ import annotations

import argparse
import calendar
import collections
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa.domain import filter_domestic                     # noqa: E402
from jwaa.nies import is_suspect                            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "public" / "data"

#: 配信する気象変数(SPEC F-02 / F-05)
WEATHER_VARIABLES = [
    "temperature_mean", "temperature_max", "temperature_min",
    "rainfall", "wind_speed_mean", "sunshine", "humidity_mean",
    "snow_depth_max",
]
AIR_VARIABLES = ["pm25", "no2", "so2", "ox"]

SOURCES = [
    "気象庁 過去の気象データ検索",
    "気象庁 大気・海洋環境観測年報",
    "国立環境研究所 環境展望台 大気汚染常時監視データ",
    "国土地理院 地理院タイル",
]


def _round(value, digits=1):
    return None if value is None else round(value, digits)


def load_weather() -> tuple[list[dict], dict[str, dict[str, dict]]]:
    """地点マスタと、月 -> 地点 -> 日付 -> 値 を読む。"""
    master = json.loads((PROCESSED / "jma_stations.json").read_text("utf-8"))
    stations = filter_domestic(
        [s for s in master["stations"] if s["kind"] == "s" and s["active"]])
    by_block = {s["block_no"]: s for s in stations}

    months: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    files = sorted((PROCESSED / "weather").glob("*.jsonl"))
    for path in files:
        block_no = path.stem
        if block_no not in by_block:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            months[rec["date"][:7]].setdefault(block_no, {})[rec["date"]] = rec
    return stations, months


def write_weather(stations: list[dict], months: dict) -> list[str]:
    out_dir = OUT / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    order = [s["block_no"] for s in stations]
    written = []
    for month in sorted(months):
        year, mon = int(month[:4]), int(month[5:7])
        ndays = calendar.monthrange(year, mon)[1]
        per_station = months[month]
        grid = {}
        for var in WEATHER_VARIABLES:
            table = []
            for day in range(1, ndays + 1):
                date = f"{month}-{day:02d}"
                row = []
                for block_no in order:
                    rec = per_station.get(block_no, {}).get(date)
                    row.append(_round(rec.get(var)) if rec else None)
                table.append(row)
            grid[var] = table
        payload = {"month": month, "days": ndays,
                   "stations": order, "variables": grid}
        path = out_dir / f"{month}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False,
                                   separators=(",", ":")), encoding="utf-8")
        written.append(month)
    return written


def load_air_stations() -> list[dict]:
    path = PROCESSED / "nies_stations.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["stations"]


def write_air(air_stations: list[dict]) -> list[str]:
    """年度別・県別の日値を、暦月ごとの格子に組み直す。"""
    air_dir = PROCESSED / "air"
    if not air_dir.exists():
        return []
    known = {s["code"] for s in air_stations}

    # month -> station -> variable -> {date: value}
    months: dict[str, dict] = collections.defaultdict(
        lambda: collections.defaultdict(dict))
    for path in sorted(air_dir.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for code, by_item in data.items():
            if code not in known:
                continue
            for item, series in by_item.items():
                if item not in AIR_VARIABLES:
                    continue
                for date, value in series.items():
                    # 検出限界の雑音では説明がつかない値は配らない(suspect)
                    if is_suspect(item, value):
                        continue
                    months[date[:7]][code].setdefault(item, {})[date] = value

    out_dir = OUT / "air"
    written = []
    for month in sorted(months):
        year, mon = int(month[:4]), int(month[5:7])
        ndays = calendar.monthrange(year, mon)[1]
        # 物質ごとに別ファイルにし、**その物質を測っている局だけ**を列に置く。
        # 全 1,773 局の密な格子にすると大半が null になり、配信物が数倍に膨らむ(N-03)。
        for var in AIR_VARIABLES:
            codes = sorted(c for c, by_item in months[month].items()
                           if by_item.get(var))
            if not codes:
                continue
            table = []
            for day in range(1, ndays + 1):
                date = f"{month}-{day:02d}"
                table.append([_round(months[month][c].get(var, {}).get(date))
                              for c in codes])
            payload = {"month": month, "days": ndays, "variable": var,
                       "stations": codes, "values": table}
            var_dir = out_dir / var
            var_dir.mkdir(parents=True, exist_ok=True)
            (var_dir / f"{month}.json").write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
        written.append(month)
    return written


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    OUT = pathlib.Path(args.out)
    OUT.mkdir(parents=True, exist_ok=True)

    stations, months = load_weather()
    weather_months = write_weather(stations, months)
    weather_days = sum(len(v) for m in months.values() for v in m.values())
    print(f"気象: 地点 {len(stations)} / 月 {len(weather_months)} / "
          f"地点日 {weather_days:,}")

    air_stations = load_air_stations()
    air_months = write_air(air_stations)
    print(f"大気: 測定局 {len(air_stations):,} / 月 {len(air_months)}")

    # 地点
    (OUT / "stations.json").write_text(json.dumps({
        "weather": [
            {"id": s["block_no"], "name": s["name"], "kana": s["kana"],
             "lat": s["lat"], "lon": s["lon"],
             "elevation_m": s["elevation_m"], "prefs": s["prec_nos"]}
            for s in stations
        ],
        "air": [
            {"id": s["code"], "name": s["name"], "lat": s["lat"],
             "lon": s["lon"], "elevation_m": s["elevation_m"],
             "pref_code": s["pref_code"], "pref_name": s["pref_name"]}
            for s in air_stations
        ],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 温室効果ガス
    ghg_src = PROCESSED / "ghg_monthly.json"
    if ghg_src.exists():
        (OUT / "ghg").mkdir(parents=True, exist_ok=True)
        (OUT / "ghg" / "monthly.json").write_text(
            ghg_src.read_text(encoding="utf-8"), encoding="utf-8")

    # manifest。日付は実データから求める(固定値を書かない)
    all_dates = sorted(d for m in months.values() for s in m.values() for d in s)
    ai_meta = None
    ai_manifest = OUT / "ai" / "model.json"
    if ai_manifest.exists():
        ai_meta = json.loads(ai_manifest.read_text(encoding="utf-8"))

    manifest = {
        "dataset_version": dt.date.today().isoformat(),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "date_min": all_dates[0] if all_dates else None,
        "date_max": all_dates[-1] if all_dates else None,
        "sources": SOURCES,
        "weather_months": weather_months,
        "air_months": air_months,
        "counts": {
            "weather_stations": len(stations),
            "air_stations": len(air_stations),
            "weather_days": len(set(all_dates)),
        },
    }
    if ai_meta:
        manifest["ai"] = ai_meta
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    biggest = max(OUT.rglob("*.json"), key=lambda p: p.stat().st_size)
    print(f"配信物 {total / 1e6:.1f} MB / 最大 {biggest.name} "
          f"{biggest.stat().st_size / 1e6:.2f} MB")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
