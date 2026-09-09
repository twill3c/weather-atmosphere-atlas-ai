"""気象庁 温室効果ガス観測値(SPEC §2.3 / G-04, G-06)。

書式の出所は配布 ZIP 同梱の readme_j.txt(UTF-8。CP932 ではない)。

月別値・日別値:
    YYYY MM DD RRRRR.RR     NNN SS.SSS F
      YYYY 観測年 / MM 観測月 / DD 観測日(月別値では 99)
      RRRRR.RR 濃度(欠測は 99999.99)
      NNN      算出に用いた下位の値の数
      SS.SSS   標準偏差(欠測は 99.999)
      F        3 = 有効 / 2 = 期間内に有効な値なし / 9 = 欠測

観測点コードは readme が定める 3 つだけ。
2023 年に標準ガスのスケールを統一し、観測開始以降の値が最大 +0.3 ppm 程度
修正されている(readme の注記)。データ版として記録する。
"""
from __future__ import annotations

import html as htmlmod
import re
import statistics
from dataclasses import dataclass
from typing import Final

#: 濃度の欠測センチネル(readme より)
MISSING_SENTINEL: Final = 99999.99
#: 標準偏差の欠測センチネル
SD_MISSING_SENTINEL: Final = 99.999
#: 月別値・日別値で「有効」を意味する品質フラグ
VALID_FLAG: Final = 3

STATIONS: Final[dict[str, str]] = {
    "ry": "綾里",
    "mi": "南鳥島",
    "yo": "与那国島",
}

#: 公表年平均表の欄の並び(実測 2026-09-08)
_PUBLISHED_COLUMN_ORDER: Final = ("ry", "mi", "yo")

UNITS: Final[dict[str, str]] = {"co2": "ppm", "ch4": "ppb"}


@dataclass(frozen=True)
class GhgRow:
    species: str
    station: str
    year: int
    month: int
    day_field: int
    raw_value: float
    n: int
    sd: float | None
    flag: int

    @property
    def value(self) -> float | None:
        """有効なときだけ濃度を返す。欠測行に値を持たせない。"""
        return self.raw_value if self.flag == VALID_FLAG else None


@dataclass(frozen=True)
class PublishedAnnual:
    station: str
    year: int
    value: float
    provisional: bool     # 括弧つき = 速報
    asterisk: bool        # * = 有効月数が 12 未満(実測で確認)


def parse_monthly_file(text: str, *, species: str, station: str) -> list[GhgRow]:
    """月別ファイル(`{st}_m.{species}`)を読む。

    書式が想定と違えば例外にして止める(黙って別の列を読む道を残さない)。
    """
    if station not in STATIONS:
        raise ValueError(f"未知の観測点コード: {station}")
    rows: list[GhgRow] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 7:
            raise ValueError(
                f"{species}/{station} の {lineno} 行目が 7 欄でない({len(parts)} 欄): {line!r}"
            )
        yyyy, mm, dd, conc, nnn, sd, flag = parts
        row = GhgRow(
            species=species,
            station=station,
            year=int(yyyy),
            month=int(mm),
            day_field=int(dd),
            raw_value=float(conc),
            n=int(nnn),
            sd=(None if float(sd) >= SD_MISSING_SENTINEL else float(sd)),
            flag=int(flag),
        )
        if not 1 <= row.month <= 12:
            raise ValueError(f"月が範囲外: {line!r}")
        rows.append(row)
    if not rows:
        raise ValueError(f"{species}/{station} に行が無い")
    return rows


def annual_means(rows: list[GhgRow]) -> dict[int, tuple[float, int]]:
    """年ごとの (有効月の単純平均, 有効月数)。

    欠測行は混ぜない。12 か月そろわない年も返すが、有効月数を添えるので
    呼び手が「そろった年だけ比べる」判断をできる。
    """
    buckets: dict[int, list[float]] = {}
    for r in rows:
        v = r.value
        if v is None:
            continue
        buckets.setdefault(r.year, []).append(v)
    return {y: (statistics.fmean(vs), len(vs)) for y, vs in sorted(buckets.items())}


_YEAR_LINE_RE = re.compile(r"^((?:19|20)\d\d)\s+(.*)$")
_CELL_RE = re.compile(r"\(?\d{3}\.\d\)?\*?")


def parse_published_yearave(html: str) -> dict[tuple[str, int], PublishedAnnual]:
    """気象庁が公表する CO2 年平均表を読む(非循環オラクルの相手側)。

    https://www.data.jma.go.jp/ghg/kanshi/obs/co2_yearave.html
    欄は 綾里 / 南鳥島 / 与那国島 の順(実測 2026-09-08)。
    括弧つきは速報、`*` は有効月数が 12 未満の年に付く。
    """
    text = re.sub(r"<[^>]+>", " ", html)
    text = htmlmod.unescape(text).replace("\xa0", " ")
    out: dict[tuple[str, int], PublishedAnnual] = {}
    for line in text.splitlines():
        m = _YEAR_LINE_RE.match(line.strip())
        if not m:
            continue
        year = int(m.group(1))
        cells = _CELL_RE.findall(m.group(2))
        if not cells:
            continue
        if len(cells) > len(_PUBLISHED_COLUMN_ORDER):
            raise ValueError(f"{year} 年の欄が想定より多い: {cells}")
        for station, cell in zip(_PUBLISHED_COLUMN_ORDER, cells):
            out[(station, year)] = PublishedAnnual(
                station=station,
                year=year,
                value=float(cell.strip("()*")),
                provisional=cell.startswith("("),
                asterisk=cell.endswith("*"),
            )
    return out
