"""国立環境研究所の大気汚染時間値を取り込み、日別値にする(SPEC §2.4 / F-06, G-07)。

    python scripts/ingest/nies_air.py --inventory --from 2014 --to 2023
    python scripts/ingest/nies_air.py --from 2014 --to 2023

注意(すべて 2026-09-08 実測):
  * 種別コードは画面の見出しと対応していない。時間値は `tj`、測定局マスタは `tm`。
  * 時間値が在るのは 2009 年度以降。
  * 環境展望台は接続を散発的にリセットする。リセットは「データ無し」ではない。
  * 生ファイルは再配布しない(著作権は国立環境研究所に帰属)。
    リポジトリに残すのは日別に集約した派生値だけ。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa import sources                                    # noqa: E402
from jwaa.fetch import Fetcher                              # noqa: E402
from jwaa.nies import (                                     # noqa: E402
    ITEM_ALIASES,
    daily_from_hourly,
    parse_hourly_file,
    parse_station_master,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "processed" / "air"
STATION_OUT = ROOT / "data" / "processed" / "nies_stations.json"

PREFS = [f"{i:02d}" for i in range(1, 48)]

#: V1 で扱う物質(SPEC §4 F-06)。ファイル内の 測定項目コード は空白で詰められている。
#: PM2.5 は測定法によって PM25 / PMFL / PMBH の 3 表記があるので、別名表から引く
#: (PM25 だけを拾うと他の 2 法の測定局を黙って落とす — TJ_manu.pdf コード表 (3))。
TARGET_KINDS = {"pm25", "no2", "so2", "ox"}
TARGET_ITEMS = {code: kind for code, kind in ITEM_ALIASES.items()
                if kind in TARGET_KINDS}


def _headers() -> dict[str, str]:
    return {"User-Agent": sources.NIES_USER_AGENT,
            "Referer": sources.NIES_DOWNLOAD}


def search(fetcher: Fetcher, dtype: str, prefs: list[str],
           years: list[str], materials: list[str]) -> list[dict]:
    payload = fetcher.post(
        sources.NIES_SEARCH,
        {"type": dtype, "prefs": json.dumps(prefs),
         "years": json.dumps(years), "materials": json.dumps(materials)},
        suffix=".json",
        validate=lambda b: b.lstrip()[:1] == b"{",
        headers=_headers(),
    )
    return json.loads(payload.decode("utf-8")).get("files", [])


def download(fetcher: Fetcher, dtype: str, name: str) -> bytes:
    return fetcher.post(
        sources.NIES_ARCHIVE_DOWNLOAD, {"type": dtype, "file": name},
        suffix=".zip",
        validate=lambda b: b[:2] == b"PK",
        headers=_headers(),
    )


def inventory(fetcher: Fetcher, years: list[int]) -> None:
    """取得量を先に測る。見積もりではなく在庫の実サイズを足す。"""
    grand = 0
    for year in years:
        files = search(fetcher, sources.NIES_TYPE_HOURLY_BY_PREF,
                       PREFS, [str(year)], [])
        total = sum(f["size"] for f in files)
        grand += total
        print(f"  FY{year}: {len(files):>2} ファイル / {total / 1e6:>7.1f} MB")
    print(f"合計 {grand / 1e6:,.0f} MB")


def load_station_master(fetcher: Fetcher, year: int) -> dict[str, dict]:
    """測定局マスタ(tm)を全県ぶん読む。座標はここにしかない。"""
    stations: dict[str, dict] = {}
    files = search(fetcher, sources.NIES_TYPE_STATION_MASTER,
                   PREFS, [str(year)], [])
    print(f"測定局マスタ FY{year}: {len(files)} ファイル")
    for meta in sorted(files, key=lambda f: f["name"]):
        blob = download(fetcher, sources.NIES_TYPE_STATION_MASTER, meta["name"])
        zf = zipfile.ZipFile(io.BytesIO(blob))
        member = [i for i in zf.infolist() if not i.is_dir()][0]
        text = zf.read(member.filename).decode("cp932", errors="replace")
        for s in parse_station_master(text):
            stations[s.code] = {
                "code": s.code, "name": s.name,
                "lat": round(s.latitude, 6), "lon": round(s.longitude, 6),
                "elevation_m": s.elevation_m,
                "pref_code": s.pref_code, "pref_name": s.pref_name,
            }
    return stations


def ingest_year(fetcher: Fetcher, year: int, min_coverage: float) -> None:
    """1 年度ぶんの時間値を日別に集約する。生ファイルは残さない。

    都道府県ごとに書き出す。使う記憶を 1 県ぶんに抑え、中断しても
    済んだ県はやり直さないため。
    """
    files = search(fetcher, sources.NIES_TYPE_HOURLY_BY_PREF,
                   PREFS, [str(year)], [])
    year_dir = OUT_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    counts = collections.Counter()
    stations_seen = 0

    for meta in sorted(files, key=lambda f: f["name"]):
        pref = meta["name"].removeprefix("j").split("_")[0]
        out_path = year_dir / f"{pref}.json"
        if out_path.exists():
            stations_seen += len(json.loads(out_path.read_text("utf-8")))
            continue

        blob = download(fetcher, sources.NIES_TYPE_HOURLY_BY_PREF, meta["name"])
        zf = zipfile.ZipFile(io.BytesIO(blob))
        pref_out: dict[str, dict[str, dict[str, float | None]]] = {}
        for member in [i for i in zf.infolist() if not i.is_dir()]:
            text = zf.read(member.filename).decode("cp932", errors="replace")
            rows = [r for r in parse_hourly_file(text)
                    if r.item.strip() in TARGET_ITEMS]
            for d in daily_from_hourly(rows, min_coverage=min_coverage):
                item = TARGET_ITEMS[d.item.strip()]
                bucket = pref_out.setdefault(d.station_code, {}).setdefault(item, {})
                bucket[d.date.isoformat()] = (
                    None if d.value is None else round(d.value, 2))
                counts[item] += 1
        out_path.write_text(
            json.dumps(pref_out, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        stations_seen += len(pref_out)
        print(f"    {meta['name']}: {meta['size'] / 1e6:>5.1f} MB -> "
              f"局 {len(pref_out):>4} -> {out_path.name}", flush=True)

    print(f"  FY{year}: 局 {stations_seen:,} / 日別値 {sum(counts.values()):,} "
          f"({dict(counts)})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="year_from", type=int, default=2014)
    ap.add_argument("--to", dest="year_to", type=int, default=2023)
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--min-coverage", type=float, default=0.75)
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "nies"))
    args = ap.parse_args()

    years = list(range(args.year_from, args.year_to + 1))
    for y in years:
        if not (sources.NIES_HOURLY_FIRST_FY <= y <= sources.NIES_HOURLY_LAST_FY):
            raise SystemExit(
                f"FY{y} の時間値は無い(在るのは "
                f"{sources.NIES_HOURLY_FIRST_FY}-{sources.NIES_HOURLY_LAST_FY})"
            )

    fetcher = Fetcher(pathlib.Path(args.cache), delay_s=args.delay,
                      tries=12, max_backoff_s=300.0, verbose=True)

    if args.inventory:
        inventory(fetcher, years)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = load_station_master(fetcher, args.year_to)
    STATION_OUT.write_text(json.dumps({
        "source": "国立環境研究所 環境展望台 大気汚染常時監視データ",
        "source_url": sources.NIES_DOWNLOAD,
        "note": "生ファイルは再配布しない。座標は度分秒を十進に変換した派生値",
        "fiscal_year": args.year_to,
        "stations": sorted(stations.values(), key=lambda s: s["code"]),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {STATION_OUT} ({len(stations):,} 局)")

    for year in years:
        ingest_year(fetcher, year, args.min_coverage)

    print(" ", fetcher.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
