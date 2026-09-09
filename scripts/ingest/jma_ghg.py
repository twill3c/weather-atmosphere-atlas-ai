"""気象庁の温室効果ガス月別値を取り込む(SPEC §2.3 / G-04, G-06)。

    python scripts/ingest/jma_ghg.py

取り込みの最後に、気象庁が別ページで公表する CO2 年平均値と突き合わせる。
これは非循環のオラクルで、固定長の切り出し・欠測センチネル・品質フラグの
解釈が正しいことの独立した証拠になる。合わなければ落とす。
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa import sources                                    # noqa: E402
from jwaa.fetch import Fetcher                              # noqa: E402
from jwaa.ghg import (                                      # noqa: E402
    STATIONS,
    UNITS,
    annual_means,
    parse_monthly_file,
    parse_published_yearave,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "ghg_monthly.json"

SPECIES = ("co2", "ch4")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "jma"))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    fetcher = Fetcher(pathlib.Path(args.cache), delay_s=2.0)
    series: dict[tuple[str, str], list] = {}

    for species in SPECIES:
        blob = fetcher.get(sources.JMA_GHG_ZIP.format(species=species),
                           suffix=".zip",
                           validate=lambda b: b[:2] == b"PK" and len(b) > 100_000)
        zf = zipfile.ZipFile(io.BytesIO(blob))
        print(f"{species}.zip: {len(blob):,} バイト / {len(zf.namelist())} 要素")
        for station in STATIONS:
            name = f"{species}/{species}/monthly/{station}_m.{species}"
            if name not in zf.namelist():
                print(f"  {station}: 月別ファイルが無い")
                continue
            rows = parse_monthly_file(zf.read(name).decode("ascii"),
                                      species=species, station=station)
            series[(species, station)] = rows
            valid = [r for r in rows if r.value is not None]
            print(f"  {station} ({STATIONS[station]}): {len(rows)} 行 / "
                  f"有効 {len(valid)} / "
                  f"{rows[0].year}-{rows[0].month:02d}..{rows[-1].year}-{rows[-1].month:02d}")

    # --- 非循環オラクル: 公表 CO2 年平均との突き合わせ ---
    published = parse_published_yearave(
        fetcher.get(sources.JMA_CO2_YEARAVE, suffix=".html",
                    validate=lambda b: b"co2" in b.lower()).decode("utf-8"))
    compared, mismatches = 0, []
    for station in STATIONS:
        rows = series.get(("co2", station))
        if not rows:
            continue
        for year, (mean, n) in annual_means(rows).items():
            key = (station, year)
            if n != 12 or key not in published or published[key].provisional:
                continue
            compared += 1
            if abs(round(mean, 1) - published[key].value) > 0.05:
                mismatches.append((station, year, round(mean, 3),
                                   published[key].value))
    print(f"\n公表年平均との照合: {compared} 観測点年、不一致 {len(mismatches)} 件")
    if mismatches:
        raise SystemExit(f"公表値と食い違う: {mismatches[:5]}")

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "気象庁 大気・海洋環境観測年報",
        "source_url": sources.JMA_GHG_INDEX,
        "note": "気象庁のデータを加工して作成",
        "oracle": {
            "description": "公表の CO2 年平均値と自前の年平均が一致することを確認",
            "url": sources.JMA_CO2_YEARAVE,
            "station_years_compared": compared,
            "mismatches": len(mismatches),
        },
        "stations": {k: v for k, v in STATIONS.items()},
        "units": UNITS,
        "series": {
            f"{species}:{station}": [
                {"year": r.year, "month": r.month,
                 "value": r.value, "n": r.n, "sd": r.sd, "flag": r.flag}
                for r in rows
            ]
            for (species, station), rows in sorted(series.items())
        },
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(" ", fetcher.summary())
    print(f"-> {out_path} ({out_path.stat().st_size:,} バイト)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
