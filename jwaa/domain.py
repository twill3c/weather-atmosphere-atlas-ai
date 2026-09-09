"""対象範囲の限定(SPEC §1 / §3.1、HC-241)。

SPEC は対象を「日本国内」と書いている。だが気象庁の「官署」は観測所の**種別**であって
国内という限定を持たない —— 現役官署 156 件には昭和基地(南緯 68.995 度)が入っている
(2026-09-08 実測)。名前が含意する限定はデータ側が持っていないので、
**述語として書き出して実物に当てる**。
"""
from __future__ import annotations

from typing import Final, Iterable, TypeVar

#: 日本の国土のおおよその外接矩形(南, 西, 北, 東)。
#: 気象官署の実在範囲(緯度 24.288..45.415 / 経度 123.010..153.983)を余裕をもって囲む。
JAPAN_BBOX: Final[tuple[float, float, float, float]] = (20.0, 122.0, 45.7, 154.5)

#: 絞り込みの検算に使う「四隅」。出所はデータ自身ではなく、
#: 日本の東西南北端として広く知られた地点に観測所が在るという外部知識。
#: 値は 2026-09-08 の地点マスタの実測。
CORNER_STATIONS: Final[dict[str, tuple[str, str]]] = {
    "east": ("47991", "南鳥島"),
    "west": ("47912", "与那国島"),
    "north": ("47401", "稚内"),
    "south": ("47991", "南鳥島"),
}

T = TypeVar("T")


def in_japan(lat: float, lon: float) -> bool:
    south, west, north, east = JAPAN_BBOX
    return south <= lat <= north and west <= lon <= east


def filter_domestic(stations: Iterable[T], *,
                    lat: str = "lat", lon: str = "lon") -> list[T]:
    """国内の地点だけを残す。辞書でもオブジェクトでも受ける。"""
    out = []
    for s in stations:
        if isinstance(s, dict):
            la, lo = s[lat], s[lon]
        else:
            la, lo = getattr(s, "latitude", None), getattr(s, "longitude", None)
        if la is None or lo is None:
            continue
        if in_japan(la, lo):
            out.append(s)
    return out
