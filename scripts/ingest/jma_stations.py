"""気象庁の観測地点マスタを作る(SPEC §2.2 / G-03)。

61 の prec_no ページを読み、block_no で名寄せして
`data/processed/jma_stations.json` に書く。

    python scripts/ingest/jma_stations.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa import sources                                    # noqa: E402
from jwaa.domain import CORNER_STATIONS, filter_domestic    # noqa: E402
from jwaa.fetch import Fetcher                              # noqa: E402
from jwaa.jma_stations import (                             # noqa: E402
    merge_by_block_no,
    parse_station_page,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "jma_stations.json"


def _looks_like_pref_page(payload: bytes) -> bool:
    """地点ページらしいこと。短い代替ページを取り込まないための検算。"""
    return b"viewPoint(" in payload and len(payload) > 2000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "jma"))
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    fetcher = Fetcher(pathlib.Path(args.cache), delay_s=args.delay)

    top = fetcher.get(
        f"{sources.JMA_SELECT_TOP}?prec_no=&block_no=&year=&month=&day=&view=",
        suffix=".html",
        validate=lambda b: b"prec_no=" in b,
    ).decode("utf-8")
    prec_nos = sorted({p for p in re.findall(r"prec_no=(\d+)", top) if p != "00"})
    if not prec_nos:
        raise SystemExit("prec_no が 1 つも取れない。ページ構造が変わった")
    print(f"prec_no: {len(prec_nos)} 件")

    all_stations = []
    for prec_no in prec_nos:
        page = fetcher.get(sources.jma_pref_url(prec_no), suffix=".html",
                           validate=_looks_like_pref_page).decode("utf-8")
        stations = parse_station_page(page, prec_no=prec_no)
        all_stations.extend(stations)
        print(f"  prec {prec_no}: {len(stations):>3} 地点")

    merged = merge_by_block_no(all_stations)
    offices = [s for s in merged.values() if s.is_surface_office]
    active_offices = [s for s in offices if s.active]
    # 「官署」は種別であって国内という限定を持たない(HC-241 / G-17)
    domestic = filter_domestic(active_offices)
    excluded = [s for s in active_offices if s not in domestic]

    print(f"\n地点 {len(merged)} 件(ページ上の延べ {len(all_stations)} 件)")
    print(f"  官署 {len(offices)} / うち現役 {len(active_offices)}")
    print(f"  国内の現役官署 {len(domestic)}")
    for s in excluded:
        print(f"    国外として除外: {s.block_no} {s.name} "
              f"({s.latitude:.3f}, {s.longitude:.3f})")
    print(f"  複数の prec に出る地点: "
          f"{[s.block_no for s in merged.values() if len(s.prec_nos) > 1]}")

    corners = {
        "east": max(domestic, key=lambda s: s.longitude),
        "west": min(domestic, key=lambda s: s.longitude),
        "north": max(domestic, key=lambda s: s.latitude),
        "south": min(domestic, key=lambda s: s.latitude),
    }
    for key, station in corners.items():
        expected = CORNER_STATIONS[key]
        mark = "OK" if station.block_no == expected[0] else "!! 想定と違う"
        print(f"  {key:>6}端: {station.block_no} {station.name}  {mark}")
        if station.block_no != expected[0]:
            raise SystemExit(
                f"四隅の検算に失敗: {key} 端が {station.name} "
                f"({station.block_no})。想定は {expected[1]} ({expected[0]})"
            )
    print(" ", fetcher.summary())

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "気象庁 過去の気象データ検索 地点選択ページ",
        "source_url": sources.JMA_SELECT_PREF,
        "note": "気象庁のデータを加工して作成",
        "stations": [
            {
                "block_no": s.block_no,
                "prec_nos": s.prec_nos,
                "kind": s.kind,
                "name": s.name,
                "kana": s.kana,
                "lat": round(s.latitude, 6),
                "lon": round(s.longitude, 6),
                "elevation_m": s.elevation_m,
                "active": s.active,
                "domestic": s in domestic,
                "elements": {
                    "pressure": s.has_pressure,
                    "wind": s.has_wind,
                    "temperature": s.has_temperature,
                    "sunshine": s.has_sunshine,
                    "snow": s.has_snow,
                    "humidity": s.has_humidity,
                },
                "remarks": list(s.remarks),
            }
            for s in sorted(merged.values(), key=lambda x: x.block_no)
        ],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
