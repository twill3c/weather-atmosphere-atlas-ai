"""気象庁の日別気象観測値を取り込む(SPEC §2.1 / §3.1、G-01/G-02)。

国内の現役官署について、指定期間の日別値を 1 地点 1 か月ずつ読み、
地点ごとの JSONL に書く。

    python scripts/ingest/jma_weather.py --from 2014 --to 2023
    python scripts/ingest/jma_weather.py --from 2014 --to 2023 --workers 2

この取り込みが守ること:
  * キャッシュ済み。2 回目の実行は外部に要求を出さない(N-06)
  * 中断しても、済んだ地点はやり直さない
  * 応答は「表があること」「日付行が暦と合うこと」「見出しの地点と年月が
    要求と一致すること」を確かめてから採る(HC-241)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa import sources                                       # noqa: E402
from jwaa.fetch import Fetcher                                 # noqa: E402
from jwaa.jma_daily import (                                   # noqa: E402
    ABSENT_IS_ZERO_COLUMNS,
    COL,
    assert_page_matches,
    parse_daily_page,
)
from jwaa.symbols import Quality, parse_cell, parse_wind_direction  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "jma_stations.json"
OUT_DIR = ROOT / "data" / "processed" / "weather"

#: 出力する変数と、その値がどの列から来るか
NUMERIC_VARIABLES = {
    "pressure_local": COL.PRESSURE_LOCAL,
    "pressure_sea": COL.PRESSURE_SEA,
    "rainfall": COL.RAIN_TOTAL,
    "rainfall_max_1h": COL.RAIN_MAX_1H,
    "rainfall_max_10min": COL.RAIN_MAX_10MIN,
    "temperature_mean": COL.TEMP_MEAN,
    "temperature_max": COL.TEMP_MAX,
    "temperature_min": COL.TEMP_MIN,
    "humidity_mean": COL.HUMIDITY_MEAN,
    "humidity_min": COL.HUMIDITY_MIN,
    "wind_speed_mean": COL.WIND_MEAN,
    "wind_speed_max": COL.WIND_MAX,
    "wind_gust": COL.WIND_GUST,
    "sunshine": COL.SUNSHINE,
    "snowfall": COL.SNOWFALL,
    "snow_depth_max": COL.SNOW_DEPTH_MAX,
}
DIRECTION_VARIABLES = {
    "wind_dir_max": COL.WIND_MAX_DIR,
    "wind_gust_dir": COL.WIND_GUST_DIR,
}

_print_lock = threading.Lock()


def _log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def load_stations() -> list[dict]:
    if not MASTER.exists():
        raise SystemExit(
            "地点マスタが無い。先に scripts/ingest/jma_stations.py を実行する"
        )
    data = json.loads(MASTER.read_text(encoding="utf-8"))["stations"]
    return [s for s in data
            if s["kind"] == "s" and s["active"] and s.get("domestic")]


def _validate_daily(payload: bytes) -> bool:
    return b"tablefix1" in payload and len(payload) > 10_000


def fetch_station(station: dict, years: range, cache_dir: pathlib.Path,
                  delay: float) -> tuple[str, int, int]:
    """1 地点ぶんを取り込み、JSONL に書く。戻り値は (block_no, 日数, 要求数)。"""
    block_no = station["block_no"]
    prec_no = station["prec_nos"][0]
    out_path = OUT_DIR / f"{block_no}.jsonl"
    done_marker = OUT_DIR / f"{block_no}.done.json"

    want = {"block_no": block_no, "years": [years.start, years.stop - 1]}
    if done_marker.exists():
        if json.loads(done_marker.read_text(encoding="utf-8")) == want:
            return block_no, -1, 0          # 済み

    fetcher = Fetcher(cache_dir, delay_s=delay)
    records: list[dict] = []
    for year in years:
        for month in range(1, 13):
            url = sources.jma_daily_url(prec_no, block_no, year, month)
            html = fetcher.get(url, suffix=".html",
                               validate=_validate_daily).decode("utf-8")
            # 要求と応答の対応を確かめる(HC-241)
            assert_page_matches(html, year=year, month=month,
                                station_name=station["name"])
            for row in parse_daily_page(html, year=year, month=month):
                rec = {
                    "date": f"{year:04d}-{month:02d}-{row.day:02d}",
                    "block_no": block_no,
                }
                for name, col in NUMERIC_VARIABLES.items():
                    reading = parse_cell(
                        row.cells[col],
                        absent_is_zero=col in ABSENT_IS_ZERO_COLUMNS)
                    rec[name] = reading.value
                    if reading.quality is not Quality.VALID:
                        rec.setdefault("quality", {})[name] = reading.quality.value
                for name, col in DIRECTION_VARIABLES.items():
                    value, quality = parse_wind_direction(row.cells[col])
                    rec[name] = value
                    if quality is not Quality.VALID:
                        rec.setdefault("quality", {})[name] = quality.value
                records.append(rec)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    done_marker.write_text(json.dumps(want, ensure_ascii=False), encoding="utf-8")
    return block_no, len(records), fetcher.requests_made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="year_from", type=int, default=2014)
    ap.add_argument("--to", dest="year_to", type=int, default=2023)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=None,
                    help="先頭 N 地点だけ(試験用)")
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "jma"))
    args = ap.parse_args()

    stations = load_stations()
    if args.limit:
        stations = stations[:args.limit]
    years = range(args.year_from, args.year_to + 1)
    total_requests = len(stations) * len(years) * 12
    _log(f"対象 {len(stations)} 地点 x {len(years)} 年 x 12 か月 "
         f"= {total_requests:,} 要求(キャッシュ済みは再要求しない)")

    cache_dir = pathlib.Path(args.cache)
    started = time.monotonic()
    done = skipped = rows = requests = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(fetch_station, s, years, cache_dir, args.delay): s
            for s in stations
        }
        for fut in concurrent.futures.as_completed(futures):
            station = futures[fut]
            try:
                block_no, n, reqs = fut.result()
            except Exception as exc:                      # noqa: BLE001
                _log(f"  !! {station['block_no']} {station['name']}: {exc!r}")
                raise
            done += 1
            requests += reqs
            if n < 0:
                skipped += 1
                continue
            rows += n
            elapsed = time.monotonic() - started
            _log(f"  [{done:>3}/{len(stations)}] {block_no} {station['name']:<10} "
                 f"{n:>5} 日  外部要求 {reqs:>4}  経過 {elapsed / 60:.1f} 分")

    _log(f"\n完了: {done} 地点(うち済み {skipped})、{rows:,} 日、"
         f"外部要求 {requests:,} 件、{(time.monotonic() - started) / 60:.1f} 分")
    _log(f"-> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
