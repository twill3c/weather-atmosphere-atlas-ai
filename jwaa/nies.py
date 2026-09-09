"""国立環境研究所 環境展望台 大気汚染常時監視データ(SPEC §2.4 / G-07, F-06)。

実物(2026-09-08 実測):

測定局マスタ(種別 `tm`, `TM{年度}xx{県}.zip`)
  CP932 の CSV、243 列。緯度・経度は **度 / 分 / 秒の 3 列**に分かれる。
  FY2020 以降は秒に小数を含む局がある(東京 FY2023 で 87 局中 2 局)。

時間値(種別 `tj`, `j{県}_{年度}.zip`)
  CP932 の CSV。列は
    測定年度, 測定局コード, 市町村コード, 測定項目コード, 測定単位コード,
    測定月, 測定日, 01h .. 24h
  欠測センチネルは 9999。**年度は 4 月始まり**なので、1〜3 月は翌暦年になる。

列は名前で引く。位置で決め打ちしない(列数が種別と年度で違うため)。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import statistics
from dataclasses import dataclass
from typing import Final, Iterable

# --- センチネル ------------------------------------------------------------
# 出所は公式の書式説明書 TJ_manu.pdf「2. ファイルレイアウト」
# (国立環境研究所 環境情報部 研究情報室、環境展望台のダウンロード画面からリンク):
#
#     9999  欠測値
#     9998  未測値
#     9997  エラー値
#
# および「測定日 … 31日までない月も31まで入力する」「31日までない月は、9998で埋める」。
#
# つまりファイルは 12 か月 x 31 日 = 372 行の固定格子で、暦に無い日は 9998 で埋まる。
# ただし **9998 は暦の詰め物専用ではない**。「未測値」一般なので暦にある日にも出る
# (実測 2026-09-08: 新潟県 FY2014 の 2014-12-01)。1 標本から規則を起こしてはならない。

#: 欠測値
HOURLY_MISSING: Final = 9999
#: 未測値(暦に無い日の詰め物にも使われる)
HOURLY_NOT_MEASURED: Final = 9998
#: エラー値
HOURLY_ERROR: Final = 9997

#: 値として採らないセンチネル。書式説明書が定める 3 つだけ。
SENTINELS: Final[dict[int, str]] = {
    HOURLY_MISSING: "missing",
    HOURLY_NOT_MEASURED: "not_measured",
    HOURLY_ERROR: "error",
}

#: これ以上は観測値ではないとみなす下限。
#: 実測 2026-09-08(東京 FY2023 全 319,920 行): 9000 以上に現れたのは 9998 と 9999 だけ。
SENTINEL_FLOOR: Final = 9000

#: 日値を作るのに必要な最小被覆(SPEC §7)
DEFAULT_MIN_COVERAGE: Final = 0.75

#: 検出限界付近の雑音として許す負値の下限。これを下回る値は `suspect` として
#: 配信と特徴量から外す(消しはしない —— 生の日別値には残す。構想書 §64)。
#:
#: 実測 2026-09-10(取り込み済みの PM2.5 日別値 2,665,884 件)。負値 5,568 件の内訳:
#:   -1 以上 3,850 / -5〜-1 1,674 / -10〜-5 38 / -20〜-10 4 / -20 未満 2
#: -10 を下回るのは 6 日だけで、4 局に散っている(長野県佐久 2 日・兵庫県中島 2 日・
#: 奈良県自排橿原 1 日・千葉県野田桐ケ作 1 日)。うち兵庫県中島の
#: 2020-07-30(-30.73)と 07-31(-52.71)は連日で、雑音ではなく測定系の異常と見る。
#: **雑音の分布はほぼ全部 -10 より上**(99.9998%)なので、そこを境にする。
SUSPECT_FLOOR: Final[dict[str, float]] = {
    "pm25": -10.0,
    "no2": -10.0,
    "so2": -10.0,
    "ox": -10.0,
}


def is_suspect(kind: str, value: float | None) -> bool:
    """検出限界の雑音では説明がつかない値か。"""
    if value is None:
        return False
    floor = SUSPECT_FLOOR.get(kind)
    return floor is not None and value < floor

HOUR_COLUMNS: Final = tuple(f"{h:02d}h" for h in range(1, 25))

#: 物質コード(ダウンロード画面の定義。実測 2026-09-08)
MATERIALS: Final[dict[str, str]] = {
    "01": "SO2", "02": "NO", "03": "NO2", "04": "NOX", "05": "CO",
    "06": "OX", "07": "NMHC", "08": "CH4", "09": "THC",
    "10": "SPM", "11": "SP", "12": "PM25",
}

#: 同じ物質が測定法によって別の項目コードで入る(TJ_manu.pdf コード表 (3))。
#: PM2.5 は項目番号 12 のまま PM25 / PMFL / PMBH の 3 表記があり、
#: PM25 だけを拾うと他の 2 法の測定局を黙って落とす。
ITEM_ALIASES: Final[dict[str, str]] = {
    "PM25": "pm25", "PMFL": "pm25", "PMBH": "pm25",
    "SPM": "spm", "SPMP": "spm", "SPMB": "spm",
    "THC": "thc", "THCP": "thc", "THCM": "thc",
    "SO2": "so2", "NO2": "no2", "OX": "ox", "NO": "no", "NOX": "nox",
    "CO": "co", "NMHC": "nmhc", "CH4": "ch4", "SP": "sp",
}

#: 項目コードごとの単位コード(TJ_manu.pdf コード表 (3))。
#: **倍率つきの単位がある**(CO は 0.1PPM、TEMP は 0.1℃、WS は 0.1m/s)。
#: V1 で使う 4 物質はいずれも倍率 1 だが、単位が想定と違えば落とす。
EXPECTED_UNITS: Final[dict[str, str]] = {
    "SO2": "PPB", "NO2": "PPB", "OX": "PPB",
    "PM25": "UG/M3", "PMFL": "UG/M3", "PMBH": "UG/M3",
}

#: センチネルを厳密に検査する項目。**V1 で実際に配る 4 物質だけ**にする。
#:
#: 理由: 厳密な主張は、意味を確かめた範囲にしか置けない。
#: 実測 2026-09-10 で、汚染物質に 9000 以上として現れたのは 9998 と 9999 だけだった
#: (6 つの県年 zip・CH4/CO/NMHC/NO/NO2/NOX/OX/SO2 の計 1,479,816 行)。
#: ところが**配らない気象項目 `PRS`(気圧)には 9992 が出た** —— 書式説明書に無い値である。
#: 全項目を厳密に検査すると、使いもしないデータで取り込みが止まる(実際に止まった)。
#: 配る物質については引き続き厳密に見て、書式が変わったらその場で落とす。
VERIFIED_ITEMS: Final[frozenset[str]] = frozenset(EXPECTED_UNITS)


@dataclass(frozen=True)
class NiesStation:
    code: str
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    pref_code: str
    pref_name: str
    address: str


@dataclass(frozen=True)
class HourlyRow:
    fiscal_year: int
    station_code: str
    item: str
    unit: str
    month: int
    day: int
    hours: tuple[float | None, ...]
    padding: bool = False

    @property
    def calendar_year(self) -> int:
        """年度と月から暦年を出す。1〜3 月は翌暦年。"""
        return self.fiscal_year if self.month >= 4 else self.fiscal_year + 1

    @property
    def exists_in_calendar(self) -> bool:
        try:
            self.date
        except ValueError:
            return False
        return True

    @property
    def date(self) -> dt.date:
        """暦日。暦に存在しない詰め物の行では ValueError になる。"""
        return dt.date(self.calendar_year, self.month, self.day)


@dataclass(frozen=True)
class DailyValue:
    date: dt.date
    station_code: str
    item: str
    unit: str
    value: float | None
    hours_valid: int

    @property
    def coverage(self) -> float:
        return self.hours_valid / 24.0


def dms_to_degrees(degrees: str | float, minutes: str | float,
                   seconds: str | float) -> float:
    """度分秒を十進度に直す。秒に小数を含む行がある(FY2020 以降)。"""
    d, m, s = float(degrees), float(minutes), float(seconds)
    if not (0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"分・秒が範囲外: {degrees}-{minutes}-{seconds}")
    return d + m / 60.0 + s / 3600.0


def fiscal_year_span(fiscal_year: int) -> tuple[dt.date, dt.date]:
    """年度の暦日の範囲。FY2023 = 2023-04-01 .. 2024-03-31。"""
    return dt.date(fiscal_year, 4, 1), dt.date(fiscal_year + 1, 3, 31)


def _rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("見出し行が無い")
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    return [r for r in reader]


def _need(row: dict[str, str], column: str) -> str:
    if column not in row:
        raise ValueError(f"列『{column}』が無い(書式が変わった)")
    value = row[column]
    return "" if value is None else value.strip()


def parse_station_master(text: str) -> list[NiesStation]:
    """測定局マスタを読む。列は名前で引く。"""
    out: list[NiesStation] = []
    for row in _rows(text):
        code = _need(row, "国環研局番")
        if not code:
            continue
        elevation = _need(row, "標高(m)")
        out.append(NiesStation(
            code=code,
            name=_need(row, "測定局名"),
            latitude=dms_to_degrees(_need(row, "緯度_度"),
                                    _need(row, "緯度_分"),
                                    _need(row, "緯度_秒")),
            longitude=dms_to_degrees(_need(row, "経度_度"),
                                     _need(row, "経度_分"),
                                     _need(row, "経度_秒")),
            elevation_m=float(elevation) if elevation else None,
            pref_code=_need(row, "都道府県コード"),
            pref_name=_need(row, "都道府県名"),
            address=_need(row, "住所"),
        ))
    return out


class SentinelError(ValueError):
    """センチネルの使われ方が実測と違う。仮定が崩れたらここで落ちる。"""


def parse_hourly_file(text: str, *, strict_sentinels: bool = True
                      ) -> list[HourlyRow]:
    """時間値ファイルを読む。

    センチネルは 2 つある(実測 2026-09-08):
      * 9999 — 暦にある日の欠測
      * 9998 — 暦に存在しない日の詰め物(ファイルは 31 日固定の格子)

    `strict_sentinels` が真なら、この対応が崩れたときに落とす。
    9998 を素通しすると「9998 という観測値」として日平均に入る。
    """
    out: list[HourlyRow] = []
    for row in _rows(text):
        code = _need(row, "測定局コード")
        if not code:
            continue
        fiscal_year = int(_need(row, "測定年度"))
        month = int(_need(row, "測定月"))
        day = int(_need(row, "測定日"))
        year = fiscal_year if month >= 4 else fiscal_year + 1
        try:
            dt.date(year, month, day)
            exists = True
        except ValueError:
            exists = False

        item = _need(row, "測定項目コード")
        unit = _need(row, "測定単位コード")
        if strict_sentinels and item in EXPECTED_UNITS:
            if unit != EXPECTED_UNITS[item]:
                raise SentinelError(
                    f"{item} の単位が {unit!r}(書式説明書では "
                    f"{EXPECTED_UNITS[item]!r})。倍率つきの単位を取り違えると"
                    f"桁がずれる"
                )

        hours: list[float | None] = []
        for col in HOUR_COLUMNS:
            raw = _need(row, col)
            if raw == "":
                hours.append(None)
                continue
            value = float(raw)
            if value >= SENTINEL_FLOOR:
                # 未知の大きい値を黙って欠測に丸めない —— ただし
                # **厳密に言えるのは、意味を確かめた項目についてだけ**である。
                # 実測 2026-09-10(1,484 千行・8 項目): 我々が配る汚染物質では
                # 9998 と 9999 しか現れない。一方、配らない気象項目 PRS には
                # 9992 が出た。確かめていない項目にまで例外を投げると、
                # 使いもしないデータで取り込みが止まる(実際に止まった)。
                if strict_sentinels and item in VERIFIED_ITEMS:
                    if int(value) not in SENTINELS:
                        raise SentinelError(
                            f"{year}-{month:02d}-{day:02d} {item} に未知の値 "
                            f"{value} が出た(定義は {sorted(SENTINELS)})"
                        )
                hours.append(None)
                continue
            hours.append(value)

        out.append(HourlyRow(
            fiscal_year=fiscal_year,
            station_code=code,
            item=item,
            unit=unit,
            month=month,
            day=day,
            hours=tuple(hours),
            padding=not exists,
        ))
    return out


def daily_from_hourly(rows: Iterable[HourlyRow], *,
                      min_coverage: float = DEFAULT_MIN_COVERAGE
                      ) -> list[DailyValue]:
    """時間値から日値を作る。

    欠測は平均に混ぜない。被覆が `min_coverage` 未満の日は値を作らず
    `value=None` にする(0 と書かない — SPEC F-15)。
    """
    out: list[DailyValue] = []
    for r in rows:
        if r.padding:
            # 暦に存在しない日(31 日固定の格子の詰め物)。日値を作らない。
            continue
        valid = [h for h in r.hours if h is not None]
        enough = len(valid) / 24.0 >= min_coverage and valid
        out.append(DailyValue(
            date=r.date,
            station_code=r.station_code,
            item=r.item,
            unit=r.unit,
            value=statistics.fmean(valid) if enough else None,
            hours_valid=len(valid),
        ))
    out.sort(key=lambda d: (d.date, d.station_code, d.item))
    return out
