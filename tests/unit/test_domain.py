"""T-026 — 対象範囲の限定(SPEC §3.1 / G-17、HC-241)。

「官署」は観測所の種別であって「日本国内の」という限定を持たない。
名前が含意する限定を述語として書き出し、実物に当てる。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from jwaa.domain import CORNER_STATIONS, JAPAN_BBOX, filter_domestic, in_japan

pytestmark = pytest.mark.unit

MASTER = (pathlib.Path(__file__).resolve().parents[2]
          / "data" / "processed" / "jma_stations.json")


def test_t026_syowa_station_is_outside_japan():
    """T-026 (G-17) 陽性対照: 昭和基地は矩形の外にある。

    実測 2026-09-08: block_no 89532、南緯 68.995 度・東経 39.580 度。
    これが矩形の内側に入るなら、この絞り込みは何も絞っていない。
    """
    assert not in_japan(-68.995, 39.580)


def test_t026b_known_domestic_stations_are_inside():
    """陰性対照: 実在する国内の観測地点は矩形に入る(誤検出 0)。

    期待値の出所は日本の東西南北端として知られた地点(外部知識)。
    座標は 2026-09-08 の地点マスタの実測。
    """
    for lat, lon in ((24.288333, 153.983333),   # 南鳥島(東端・南端)
                     (24.466667, 123.010000),   # 与那国島(西端)
                     (45.415000, 141.678333),   # 稚内(北端)
                     (35.691667, 139.750000)):  # 東京
        assert in_japan(lat, lon), (lat, lon)


@pytest.mark.skipif(not MASTER.exists(),
                    reason="地点マスタが未取得(scripts/ingest/jma_stations.py)")
def test_t026c_domestic_filter_corners_match_known_extremes():
    """T-026 (G-17): 絞り込んだ集合の四隅が、独立に知られた極地点と一致する。

    外れ値 1 件は平均や分布には埋もれるが、極値には必ず出る(HC-241)。
    """
    stations = json.loads(MASTER.read_text(encoding="utf-8"))["stations"]
    offices = [s for s in stations if s["kind"] == "s" and s["active"]]
    domestic = filter_domestic(offices)

    # 前提の固定: 絞り込みが実際に何かを落としていること(HC-079)
    assert len(domestic) < len(offices), (
        "絞り込みが 1 件も落としていない。この検査は何も言っていない"
    )

    corners = {
        "east": max(domestic, key=lambda s: s["lon"]),
        "west": min(domestic, key=lambda s: s["lon"]),
        "north": max(domestic, key=lambda s: s["lat"]),
        "south": min(domestic, key=lambda s: s["lat"]),
    }
    for key, (block_no, name) in CORNER_STATIONS.items():
        assert corners[key]["block_no"] == block_no, (
            f"{key} 端が {corners[key]['name']}({corners[key]['block_no']})。"
            f"想定は {name}({block_no})"
        )
        assert corners[key]["name"] == name


@pytest.mark.skipif(not MASTER.exists(), reason="地点マスタが未取得")
def test_t026d_every_domestic_station_is_inside_the_bbox():
    """絞り込んだ後は全件が矩形に入る(取りこぼしの不在)。"""
    stations = json.loads(MASTER.read_text(encoding="utf-8"))["stations"]
    domestic = filter_domestic([s for s in stations
                                if s["kind"] == "s" and s["active"]])
    south, west, north, east = JAPAN_BBOX
    outside = [s for s in domestic
               if not (south <= s["lat"] <= north and west <= s["lon"] <= east)]
    assert outside == []
