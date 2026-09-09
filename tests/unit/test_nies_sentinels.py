"""T-028 / T-029 — NIES 時間値のセンチネルと項目コード(SPEC §2.4 / G-18)。

期待値の出所は**公式の書式説明書** `TJ_manu.pdf`
(国立環境研究所 環境情報部 研究情報室、環境展望台のダウンロード画面からリンク。
2026-09-09 取得)の「2. ファイルレイアウト」:

    9999 欠測値 / 9998 未測値 / 9997 エラー値
    測定日 … 31日までない月も31まで入力する
    31日までない月は、9998で埋める

およびコード表 (3): PM2.5 は測定法によって PM25 / PMFL / PMBH の 3 表記がある
(いずれも項目番号 12)。

**この規則は実物の標本からではなく書式説明書から取っている。**
最初は東京 FY2023 の 1 標本から「9998 は暦に無い日にしか出ない」と読んだが、
新潟県 FY2014 の 2014-12-01(暦にある日)に 9998 が出て崩れた。
"""
from __future__ import annotations

import datetime as dt

import pytest

from jwaa.nies import (
    HOURLY_ERROR,
    HOURLY_MISSING,
    HOURLY_NOT_MEASURED,
    ITEM_ALIASES,
    SENTINELS,
    SentinelError,
    daily_from_hourly,
    parse_hourly_file,
)

pytestmark = pytest.mark.unit

HEADER = ("測定年度,測定局コード,市町村コード,測定項目コード,測定単位コード,"
          "測定月,測定日," + ",".join(f"{h:02d}h" for h in range(1, 25)))


def _row(month, day, values, fy=2023, code="13101010", item="PM25",
         unit="UG/M3"):
    assert len(values) == 24
    return (f"{fy},{code},101,{item:<4},{unit:<6},{month:>2},{day:>2}," +
            ",".join(str(v) for v in values))


# --- センチネル 3 種 ---------------------------------------------------------

def test_t028_three_sentinels_are_all_no_value():
    """T-028 (G-18): 9997 / 9998 / 9999 はいずれも値にしない。"""
    assert set(SENTINELS) == {HOURLY_MISSING, HOURLY_NOT_MEASURED, HOURLY_ERROR}
    text = "\n".join([
        HEADER,
        _row(4, 1, [HOURLY_MISSING] * 24),
        _row(4, 2, [HOURLY_NOT_MEASURED] * 24),
        _row(4, 3, [HOURLY_ERROR] * 24),
    ])
    daily = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)
    assert len(daily) == 3
    assert all(d.value is None and d.hours_valid == 0 for d in daily)


def test_t028b_positive_control_sentinel_as_value_wrecks_the_mean():
    """陽性対照: センチネルを観測値として通すと物理的にありえない平均になる。

    PM2.5 の実測最大は 314(東京 FY2023)。9998 はその 30 倍以上。
    """
    naive = sum([HOURLY_NOT_MEASURED] * 24) / 24
    assert naive > 9000, "陽性対照が発火していない"
    text = "\n".join([HEADER, _row(4, 2, [HOURLY_NOT_MEASURED] * 24)])
    d = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)[0]
    assert d.value is None


def test_t028c_not_measured_may_appear_on_a_real_date():
    """9998 は暦にある日にも出る(書式説明書の『未測値』)。例外にしない。

    実測 2026-09-08: 新潟県 FY2014 の 2014-12-01。
    1 標本から『詰め物専用』と決めつけると、ここで落ちる。
    """
    text = "\n".join([HEADER, _row(12, 1, [HOURLY_NOT_MEASURED] * 24, fy=2014)])
    rows = parse_hourly_file(text)
    assert rows[0].padding is False          # 12/1 は暦にある
    daily = daily_from_hourly(rows, min_coverage=0.75)
    assert daily[0].date == dt.date(2014, 12, 1)
    assert daily[0].value is None


def test_t028d_unknown_large_value_raises():
    """書式説明書に無い大きい値は、黙って欠測に丸めず例外にする(HC-075)。"""
    text = "\n".join([HEADER, _row(4, 1, [9996] * 24)])
    with pytest.raises(SentinelError):
        parse_hourly_file(text)


def test_t028e_relaxed_mode_does_not_raise():
    """検算を外せる口はあるが、既定では閉じていること。"""
    rows = parse_hourly_file("\n".join([HEADER, _row(4, 1, [9996] * 24)]),
                             strict_sentinels=False)
    assert rows[0].hours == (None,) * 24


# --- 暦の詰め物 --------------------------------------------------------------

def test_t028f_padding_rows_are_dropped():
    """T-028 (G-18): 暦に存在しない日(4/31)は日値にしない。"""
    text = "\n".join([
        HEADER,
        _row(4, 30, [12] * 24),
        _row(4, 31, [HOURLY_NOT_MEASURED] * 24),
    ])
    rows = parse_hourly_file(text)
    assert [r.padding for r in rows] == [False, True]
    daily = daily_from_hourly(rows, min_coverage=0.75)
    assert [d.date for d in daily] == [dt.date(2023, 4, 30)]
    assert daily[0].value == pytest.approx(12.0)


def test_t028g_february_30_is_padding_in_a_leap_year_too():
    """FY2023 の 2 月は暦年 2024(閏年)。2/29 は在り 2/30 は無い。"""
    text = "\n".join([
        HEADER,
        _row(2, 29, [8] * 24),
        _row(2, 30, [HOURLY_NOT_MEASURED] * 24),
    ])
    rows = parse_hourly_file(text)
    assert [r.padding for r in rows] == [False, True]
    daily = daily_from_hourly(rows, min_coverage=0.75)
    assert [d.date for d in daily] == [dt.date(2024, 2, 29)]


# --- 項目コードの別名と単位 ---------------------------------------------------

@pytest.mark.parametrize("item", ["PM25", "PMFL", "PMBH"])
def test_t029_pm25_has_three_item_codes(item):
    """T-029 (G-18): PM2.5 は測定法によって 3 つの項目コードで入る。

    PM25 だけを拾うと、フィルター振動法・ハイブリッド法の測定局を黙って落とす。
    """
    assert ITEM_ALIASES[item] == "pm25"
    text = "\n".join([HEADER, _row(4, 1, [15] * 24, item=item)])
    rows = parse_hourly_file(text)
    assert ITEM_ALIASES[rows[0].item.strip()] == "pm25"
    assert daily_from_hourly(rows, min_coverage=0.75)[0].value == pytest.approx(15.0)


def test_t029b_unexpected_unit_raises():
    """単位が書式説明書と違えば落とす。倍率つきの単位で桁がずれるのを防ぐ。

    書式説明書のコード表 (3) には 0.1PPM(CO)・0.1'C(TEMP)・0.1M/S(WS)のような
    倍率つきの単位がある。PM2.5 は UG/M3。
    """
    text = "\n".join([HEADER, _row(4, 1, [15] * 24, item="PM25", unit="PPB")])
    with pytest.raises(SentinelError):
        parse_hourly_file(text)


def test_t029c_expected_units_cover_the_v1_materials():
    """V1 で使う 4 物質がすべて単位検査の対象になっていること。"""
    from jwaa.nies import EXPECTED_UNITS
    for item in ("SO2", "NO2", "OX", "PM25", "PMFL", "PMBH"):
        assert item in EXPECTED_UNITS
