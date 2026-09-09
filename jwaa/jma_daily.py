"""気象庁「過去の気象データ検索」の日別値・月別値ページを読む(SPEC §2.1 / G-02)。

ページの実物(2026-09-08 実測):
  https://www.data.jma.go.jp/stats/etrn/view/daily_s1.php?prec_no=44&block_no=47662&year=2023&month=8&day=&view=
  データ表は <table id='tablefix1' class='data2_s'>(id は単引用符)。文字コードは UTF-8。
  日別表は 21 列、月別表は 20 列。

**仮定が崩れたら落ちる検算をここに置く**(HC-075):
prec_no と block_no の対が不整合でも HTTP 200 と短いページ(3,814 バイト)が返る。
表の存在と行数を確かめない取得器は、それを「欠測の月」として静かに取り込む。
"""
from __future__ import annotations

import calendar
import html as htmlmod
import re
from dataclasses import dataclass
from typing import Final


class PageStructureError(RuntimeError):
    """ページが想定の構造を持っていない。黙って空を返さずここで止める。"""


_TABLE_RE = re.compile(r"<table[^>]*id=['\"]tablefix1['\"].*?</table>", re.S)
_ROW_RE = re.compile(r"<tr.*?</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


class COL:
    """日別表の列位置。見出しに当てて確かめる(test_t009b)。

    実測 2026-09-08(東京 2023 の全 12 か月で 21 列):
      0 日 / 1 気圧(現地) / 2 気圧(海面) / 3 降水量合計 / 4 降水量最大1時間
      5 降水量最大10分間 / 6 気温平均 / 7 気温最高 / 8 気温最低
      9 湿度平均 / 10 湿度最小 / 11 平均風速 / 12 最大風速 / 13 最大風速の風向
      14 最大瞬間風速 / 15 最大瞬間の風向 / 16 日照時間 / 17 降雪合計 / 18 最深積雪
      19 天気概況(昼) / 20 天気概況(夜)
    """

    DAY: Final = 0
    PRESSURE_LOCAL: Final = 1
    PRESSURE_SEA: Final = 2
    RAIN_TOTAL: Final = 3
    RAIN_MAX_1H: Final = 4
    RAIN_MAX_10MIN: Final = 5
    TEMP_MEAN: Final = 6
    TEMP_MAX: Final = 7
    TEMP_MIN: Final = 8
    HUMIDITY_MEAN: Final = 9
    HUMIDITY_MIN: Final = 10
    WIND_MEAN: Final = 11
    WIND_MAX: Final = 12
    WIND_MAX_DIR: Final = 13
    WIND_GUST: Final = 14
    WIND_GUST_DIR: Final = 15
    SUNSHINE: Final = 16
    SNOWFALL: Final = 17
    SNOW_DEPTH_MAX: Final = 18
    WEATHER_DAY: Final = 19
    WEATHER_NIGHT: Final = 20


class MCOL:
    """月別表の列位置。日別表とは並びが違う。

    実測 2026-09-08(東京 2023、20 列):
      0 月 / 1 気圧(現地) / 2 気圧(海面) / 3 降水量合計 / 4 最大日降水量
      5 最大1時間 / 6 最大10分間 / 7 平均気温 / 8 日最高の平均 / 9 日最低の平均 …

    降水量合計はたまたま日別表と同じ 3 だが、**平均気温は日別 6 に対し月別 7** で
    ずれる。日別用の定数を月別表に当てると、黙って別の量(最大10分間降水量)を読む。
    """

    MONTH: Final = 0
    PRESSURE_LOCAL: Final = 1
    PRESSURE_SEA: Final = 2
    RAIN_TOTAL: Final = 3
    RAIN_MAX_DAY: Final = 4
    RAIN_MAX_1H: Final = 5
    RAIN_MAX_10MIN: Final = 6
    TEMP_MEAN: Final = 7
    TEMP_MAX_MEAN: Final = 8
    TEMP_MIN_MEAN: Final = 9


DAILY_COLUMN_COUNT: Final = 21

#: `--` を 0 と読んでよい列(量的要素)。SPEC §2.1。
ABSENT_IS_ZERO_COLUMNS: Final = frozenset({
    COL.RAIN_TOTAL, COL.RAIN_MAX_1H, COL.RAIN_MAX_10MIN,
    COL.SUNSHINE, COL.SNOWFALL, COL.SNOW_DEPTH_MAX,
})


@dataclass(frozen=True)
class DailyRow:
    day: int
    cells: list[str]


@dataclass(frozen=True)
class MonthlyRow:
    month: int
    cells: list[str]


def _clean(fragment: str) -> str:
    text = _TAG_RE.sub("", fragment)
    return htmlmod.unescape(text).replace("\xa0", " ").strip()


def _table_rows(html: str) -> list[list[str]]:
    m = _TABLE_RE.search(html)
    if not m:
        raise PageStructureError(
            "データ表 (table id='tablefix1') が見つからない。"
            "prec_no と block_no の対が不整合なとき、気象庁は HTTP 200 と "
            "データ表の無い短いページを返す(実測 2026-09-08)"
        )
    rows = []
    for chunk in _ROW_RE.findall(m.group(0)):
        cells = [_clean(c) for c in _CELL_RE.findall(chunk)]
        if cells:
            rows.append(cells)
    return rows


def _leading_int(cell: str) -> int | None:
    return int(cell) if re.fullmatch(r"\d+", cell) else None


def daily_header_labels(html: str) -> list[str]:
    """見出し行を連結して列ごとのラベルを返す。列位置の検算に使う。

    見出しは 3 段(要素 / 種別 / 細目)に分かれ、`colspan` と `rowspan` で
    段ごとに列数が違う。ここでは各段のセルを順に振り分けるのではなく、
    **データ行と同じ列数になるまで段を連結した文字列**を作る。
    位置の意味づけはデータ行の列数を基準にする。
    """
    rows = _table_rows(html)
    header_rows = [r for r in rows if _leading_int(r[0]) is None]
    if not header_rows:
        raise PageStructureError("見出し行が無い")

    labels = [""] * DAILY_COLUMN_COUNT
    # 最上段は colspan で広がるので、そのまま位置には使えない。
    # 実用上は「その列に関係する語がどこかの段に現れるか」を見れば足りる。
    flat = " ".join(" ".join(r) for r in header_rows)
    groups = {
        COL.PRESSURE_LOCAL: "気圧", COL.PRESSURE_SEA: "気圧",
        COL.RAIN_TOTAL: "降水量", COL.RAIN_MAX_1H: "降水量",
        COL.RAIN_MAX_10MIN: "降水量",
        COL.TEMP_MEAN: "気温", COL.TEMP_MAX: "気温", COL.TEMP_MIN: "気温",
        COL.HUMIDITY_MEAN: "湿度", COL.HUMIDITY_MIN: "湿度",
        COL.WIND_MEAN: "風速", COL.WIND_MAX: "風速",
        COL.WIND_MAX_DIR: "風向", COL.WIND_GUST: "風速",
        COL.WIND_GUST_DIR: "風向",
        COL.SUNSHINE: "日照", COL.SNOWFALL: "雪", COL.SNOW_DEPTH_MAX: "雪",
        COL.WEATHER_DAY: "天気", COL.WEATHER_NIGHT: "天気",
        COL.DAY: "日",
    }
    for idx, word in groups.items():
        if word not in flat:
            raise PageStructureError(f"見出しに『{word}』が無い(表の構造が変わった)")
        labels[idx] = word
    return labels


_CAPTION_RE = re.compile(r"([^<>　]+)（([^<>）]+)\)　(\d{4})年\s*(\d{1,2})月")


@dataclass(frozen=True)
class PageCaption:
    station: str
    area: str
    year: int
    month: int


def parse_caption(html: str) -> PageCaption:
    """ページ見出しの「東京（東京都)　2023年8月（日ごとの値）」を読む。

    要求と応答の対応を確かめるために使う(HC-241)。状態コードと URL の形は
    「要求したものが返ってきたこと」を保証しない。
    """
    text = htmlmod.unescape(html)
    m = _CAPTION_RE.search(text)
    if not m:
        raise PageStructureError("ページ見出し(地点名と年月)が読めない")
    return PageCaption(station=m.group(1).strip(), area=m.group(2).strip(),
                       year=int(m.group(3)), month=int(m.group(4)))


def assert_page_matches(html: str, *, year: int, month: int,
                        station_name: str | None = None) -> PageCaption:
    """応答が、要求した地点・年月のものであることを確かめる。"""
    cap = parse_caption(html)
    if (cap.year, cap.month) != (year, month):
        raise PageStructureError(
            f"要求は {year}-{month:02d} だが、応答は {cap.year}-{cap.month:02d}"
        )
    if station_name is not None and cap.station != station_name:
        raise PageStructureError(
            f"要求は {station_name} だが、応答は {cap.station}"
        )
    return cap


def parse_daily_page(html: str, *, year: int, month: int) -> list[DailyRow]:
    """日別値ページを読む。構造が想定と違えば PageStructureError。"""
    rows = _table_rows(html)
    data = []
    for cells in rows:
        day = _leading_int(cells[0])
        if day is None:
            continue
        if len(cells) != DAILY_COLUMN_COUNT:
            raise PageStructureError(
                f"{year}-{month:02d} の {day} 日の列数が {len(cells)}"
                f"(想定 {DAILY_COLUMN_COUNT})"
            )
        data.append(DailyRow(day=day, cells=cells))

    ndays = calendar.monthrange(year, month)[1]
    days = [r.day for r in data]
    if days != list(range(1, ndays + 1)):
        raise PageStructureError(
            f"{year}-{month:02d} の日付行が暦と合わない: "
            f"{len(days)} 行(暦は {ndays} 日)"
        )
    return data


def parse_monthly_page(html: str, *, year: int) -> list[MonthlyRow]:
    """月別値ページ(monthly_s1.php)を読む。

    実測 2026-09-08(東京 2023): 列は
      0 月 / 1 気圧(現地) / 2 気圧(海面) / 3 降水量合計 / 4 最大日降水量
      5 最大1時間 / 6 最大10分間 / 7 平均気温 / 8 日最高の平均 / 9 日最低の平均 ...
    日別表と 0..3 の位置が同じなので COL.RAIN_TOTAL / COL.TEMP_MEAN の
    どちらもそのまま使えるが、7 = 平均気温 は日別表の 6 とずれる点に注意する。
    """
    rows = _table_rows(html)
    data = []
    for cells in rows:
        month = _leading_int(cells[0])
        if month is None or not 1 <= month <= 12:
            continue
        data.append(MonthlyRow(month=month, cells=cells))
    months = [r.month for r in data]
    if months != list(range(1, 13)):
        raise PageStructureError(f"{year} 年の月別表が 12 か月そろわない: {months}")
    return data
