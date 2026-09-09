"""気象庁の観測地点マスタ(SPEC §2.2 / G-03)。

地点選択ページ `select/prefecture.php?prec_no=NN` の中の `viewPoint(...)` 呼び出しが
地点表そのものになっている。**先頭の 1 件が列名を並べた見出し行**なので、
列の意味を推測せずに読める(2026-09-08 実測):

    as, bk_no, ch, ch_kn, lat_d, lat_m, lon_d, lon_m, height,
    f_pre, f_wsp, f_tem, f_sun, f_snc, f_hum, ed_y, ed_m, ed_d, bikou1..bikou5

`lat_m` / `lon_m` は**十進の分**(例 41.5 分)であって度分秒の分ではない。
`ed_y` が 9999 なら現役。`bk_no=47639`(富士山)だけが県境のため 2 つの prec_no に出る。
"""
from __future__ import annotations

import html as htmlmod
import re
from dataclasses import dataclass, field
from typing import Final, Iterable

STATION_HEADER: Final[tuple[str, ...]] = (
    "as", "bk_no", "ch", "ch_kn", "lat_d", "lat_m", "lon_d", "lon_m", "height",
    "f_pre", "f_wsp", "f_tem", "f_sun", "f_snc", "f_hum",
    "ed_y", "ed_m", "ed_d",
    "bikou1", "bikou2", "bikou3", "bikou4", "bikou5",
)

_ACTIVE_SENTINEL: Final = "9999"

_CALL_RE = re.compile(r"viewPoint\(([^)]*)\)")


class StationHeaderError(RuntimeError):
    """見出し行が想定と違う。列の意味を推測せずここで止める。"""


@dataclass(frozen=True)
class Station:
    prec_no: str
    block_no: str
    kind: str                 # 's' = 官署 / 'a' = アメダス
    name: str
    kana: str
    latitude: float
    longitude: float
    elevation_m: float | None
    active: bool
    has_pressure: bool
    has_wind: bool
    has_temperature: bool
    has_sunshine: bool
    has_snow: bool
    has_humidity: bool
    remarks: tuple[str, ...] = ()

    @property
    def is_surface_office(self) -> bool:
        """官署(daily_s1.php で引ける地点)かどうか。"""
        return self.kind == "s"


@dataclass(frozen=True)
class MergedStation:
    block_no: str
    kind: str
    name: str
    kana: str
    latitude: float
    longitude: float
    elevation_m: float | None
    active: bool
    has_pressure: bool
    has_wind: bool
    has_temperature: bool
    has_sunshine: bool
    has_snow: bool
    has_humidity: bool
    prec_nos: list[str] = field(default_factory=list)
    remarks: tuple[str, ...] = ()

    @property
    def is_surface_office(self) -> bool:
        return self.kind == "s"


def _args(call: str) -> list[str]:
    out = []
    for a in call.split(","):
        a = htmlmod.unescape(a.strip())
        if len(a) >= 2 and a[0] == a[-1] and a[0] in "'\"":
            a = a[1:-1]
        out.append(a.strip())
    return out


def _calls(html: str) -> list[list[str]]:
    return [_args(c) for c in _CALL_RE.findall(html)]


def extract_header(html: str) -> list[str]:
    """先頭の viewPoint 呼び出し(見出し行)を返す。"""
    calls = _calls(html)
    if not calls:
        raise StationHeaderError("viewPoint 呼び出しが 1 つも無い")
    return calls[0]


def _flag(value: str) -> bool:
    """要素フラグ。実測では 0/1/2 が出る。1 を『在り』とする。

    2 は日照計の種類違い等で現れるが、日別表に値が出る点では 1 と同じではないため、
    ここでは厳密に 1 のみを True にする(判断を広げない)。
    """
    return value.strip() == "1"


def _to_float(value: str) -> float | None:
    v = value.strip()
    if v in ("", "-", "--"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_station_page(html: str, *, prec_no: str) -> list[Station]:
    """1 つの都道府県ページから地点を読む。

    見出し行が想定と違えば StationHeaderError。列の意味を推測しない。
    """
    calls = _calls(html)
    if not calls:
        raise StationHeaderError("viewPoint 呼び出しが 1 つも無い")
    header = calls[0]
    if header != list(STATION_HEADER):
        raise StationHeaderError(
            f"見出し行が想定と違う。想定 {list(STATION_HEADER)} / 実際 {header}"
        )

    seen: dict[str, Station] = {}
    for row in calls[1:]:
        if len(row) != len(STATION_HEADER):
            raise StationHeaderError(
                f"列数の違う行がある({len(row)} 列): {row[:4]}"
            )
        d = dict(zip(STATION_HEADER, row))
        block_no = d["bk_no"]
        if block_no in seen:          # 同じページに地図用の重複 area が出る
            continue
        lat_d, lat_m = _to_float(d["lat_d"]), _to_float(d["lat_m"])
        lon_d, lon_m = _to_float(d["lon_d"]), _to_float(d["lon_m"])
        if None in (lat_d, lat_m, lon_d, lon_m):
            raise StationHeaderError(f"座標が読めない行: {row[:4]}")
        remarks = tuple(x for x in (d[f"bikou{i}"] for i in range(1, 6)) if x)
        seen[block_no] = Station(
            prec_no=prec_no,
            block_no=block_no,
            kind=d["as"],
            name=d["ch"],
            kana=d["ch_kn"],
            latitude=lat_d + lat_m / 60.0,
            longitude=lon_d + lon_m / 60.0,
            elevation_m=_to_float(d["height"]),
            active=d["ed_y"].strip() == _ACTIVE_SENTINEL,
            has_pressure=_flag(d["f_pre"]),
            has_wind=_flag(d["f_wsp"]),
            has_temperature=_flag(d["f_tem"]),
            has_sunshine=_flag(d["f_sun"]),
            has_snow=_flag(d["f_snc"]),
            has_humidity=_flag(d["f_hum"]),
            remarks=remarks,
        )
    return list(seen.values())


_IDENTITY_FIELDS: Final = ("kind", "name", "latitude", "longitude",
                           "elevation_m", "active")


def merge_by_block_no(stations: Iterable[Station]) -> dict[str, MergedStation]:
    """block_no で名寄せする。

    富士山(47639)は県境の山頂なので prec_no 49 と 50 の両方に出る。
    同じ block_no で座標や名称が食い違ったら、黙って片方を採らずに落とす。
    """
    merged: dict[str, MergedStation] = {}
    for s in stations:
        cur = merged.get(s.block_no)
        if cur is None:
            merged[s.block_no] = MergedStation(
                block_no=s.block_no, kind=s.kind, name=s.name, kana=s.kana,
                latitude=s.latitude, longitude=s.longitude,
                elevation_m=s.elevation_m, active=s.active,
                has_pressure=s.has_pressure, has_wind=s.has_wind,
                has_temperature=s.has_temperature, has_sunshine=s.has_sunshine,
                has_snow=s.has_snow, has_humidity=s.has_humidity,
                prec_nos=[s.prec_no], remarks=s.remarks,
            )
            continue
        for fname in _IDENTITY_FIELDS:
            a, b = getattr(cur, fname), getattr(s, fname)
            if isinstance(a, float) and isinstance(b, float):
                same = abs(a - b) < 1e-9
            else:
                same = a == b
            if not same:
                raise ValueError(
                    f"block_no={s.block_no} が prec_no {cur.prec_nos} と "
                    f"{s.prec_no} で食い違う: {fname} {a!r} != {b!r}"
                )
        if s.prec_no not in cur.prec_nos:
            cur.prec_nos.append(s.prec_no)
    for m in merged.values():
        m.prec_nos.sort()
    return merged
