"""T-019..T-023 — 大気汚染(SPEC §2.4 / G-07, F-06)。

NIES の生ファイルは同梱しない(著作権が国立環境研究所に帰属 — SPEC §2.5)。
よってここでは合成フィクスチャを使う。合成物は「知っているつもり」で書きやすいので、
**そのフィクスチャが主張したい性質を実際に持つことをテスト内で assert する**(HC-068)。
書式は実物(j13_2023.zip / TM20230013.zip、2026-09-08 実測)に合わせている。
"""
from __future__ import annotations

import datetime as dt

import pytest

from jwaa.nies import (
    HOURLY_MISSING,
    daily_from_hourly,
    dms_to_degrees,
    fiscal_year_span,
    parse_hourly_file,
    parse_station_master,
)

pytestmark = pytest.mark.unit


# --- T-019: 度分秒 -> 十進 ----------------------------------------------------

def test_t019_dms_conversion_including_fractional_seconds():
    """T-019 (G-07): 秒に小数を含む行も正しく変換する。

    実測 2026-09-08: 東京 FY2023 の 87 局中 2 局が秒に小数を持つ。
    期待値は手計算: 35 + 40/60 + 22.08/3600。
    """
    assert dms_to_degrees("35", "40", "22.08") == pytest.approx(
        35 + 40 / 60 + 22.08 / 3600, abs=1e-12)
    assert dms_to_degrees("35", "40", "22") == pytest.approx(
        35 + 40 / 60 + 22 / 3600, abs=1e-12)


def test_t019b_known_station_lands_where_it_should():
    """国設霞が関 の実測値(35°40'22.0\", 139°45'11.0\")が霞が関の近傍に来る。

    実測 2026-09-08: 変換結果 (35.67278, 139.75306) は霞が関中心から 0.31 km。
    期待の出所は外部知識(霞が関の所在)であって TM ファイルの数字ではない。
    """
    lat = dms_to_degrees("35", "40", "22.0")
    lon = dms_to_degrees("139", "45", "11.0")
    assert lat == pytest.approx(35.6728, abs=5e-4)
    assert lon == pytest.approx(139.7531, abs=5e-4)


# --- T-020: 測定局マスタ ------------------------------------------------------

STATION_HEADER = (
    "年度,国環研局番,国環研局番_以前,自治体局番_1,自治体局番_2,測定局名,８文字名,"
    "自治体名,測定局名_ローマ字 ,緯度_度,緯度_分,緯度_秒,経度_度,経度_分,経度_秒,"
    "標高(m),都道府県コード,都道府県名,都道府県名_ローマ字,市区町村コード,市区町村名,"
    "市区町村名_ローマ字,住所"
)


def _station_row(code, name, lat_dms, lon_dms, pref="13", pref_name="東京都"):
    la_d, la_m, la_s = lat_dms
    lo_d, lo_m, lo_s = lon_dms
    return (f"2023,{code},,,,{name},,{pref_name},,"
            f"{la_d},{la_m},{la_s},{lo_d},{lo_m},{lo_s},"
            f"5,{pref},{pref_name},Tokyo-to,13101,千代田区,Chiyoda-ku,住所")


def test_t020_station_master_coordinates_inside_prefecture_bbox():
    """T-020 (G-07): 測定局の座標が都道府県の外接矩形に入る。"""
    inside = _station_row("13101520", "国設霞が関", ("35", "40", "22.0"),
                          ("139", "45", "11.0"))
    text = STATION_HEADER + "\n" + inside + "\n"
    stations = parse_station_master(text)
    assert len(stations) == 1
    s = stations[0]

    # 合成フィクスチャが主張したい性質を実際に持つことの確認(HC-068)
    assert s.pref_code == "13"
    tokyo_bbox = (35.4, 138.9, 35.9, 139.95)     # 南, 西, 北, 東(本土部)
    assert tokyo_bbox[0] <= s.latitude <= tokyo_bbox[2]
    assert tokyo_bbox[1] <= s.longitude <= tokyo_bbox[3]


def test_t020b_out_of_bbox_station_is_detectable():
    """陽性対照: 矩形の外に置いた局は、検査で捕まること。"""
    outside = _station_row("13999999", "ありえない局", ("43", "0", "0"),
                           ("141", "0", "0"))     # 札幌あたり
    text = STATION_HEADER + "\n" + outside + "\n"
    s = parse_station_master(text)[0]
    tokyo_bbox = (35.4, 138.9, 35.9, 139.95)
    assert not (tokyo_bbox[0] <= s.latitude <= tokyo_bbox[2]), (
        "陽性対照が発火していない。矩形検査は何も検出していない"
    )


# --- T-021 / T-022: 時間値 -> 日別値 ------------------------------------------

HOURLY_HEADER = ("測定年度,測定局コード,市町村コード,測定項目コード,測定単位コード,"
                 "測定月,測定日," + ",".join(f"{h:02d}h" for h in range(1, 25)))


def _hourly_row(month, day, values, code="13101010", item="PM25", unit="UG/M3"):
    """実物の書式に合わせる。単位コードは書式説明書と実データの両方で 'UG/M3'。

    実測 2026-09-09(東京 FY2023): 項目と単位の対は
    PM25/PMFL/SPM/SPMB=UG/M3、SO2/NO/NO2/NOX/OX=PPB、CO=0.1PPM、
    TEMP=0.1'C、WS=0.1M/S、SUN=0.01MJ、CH4/NMHC/THC=10PPBC、WD=16DIRC。
    最初この助手は 'UGM3' と書いていた —— 自作のフィクスチャを実物に当てて
    いなかったための誤り(HC-068)。
    """
    assert len(values) == 24, "時間値は 24 個でなければならない"
    return (f"2023,{code},101,{item:<4},{unit:<6},{month:>2},{day:>2}," +
            ",".join(f"{v:>4}" for v in values))


def test_t021_daily_mean_ignores_missing_sentinel():
    """T-021 (F-06): 9999 は欠測。日平均に混ぜない。"""
    vals = [10] * 20 + [HOURLY_MISSING] * 4
    # フィクスチャの性質を確認(HC-068)
    assert vals.count(HOURLY_MISSING) == 4 and len(vals) == 24

    text = HOURLY_HEADER + "\n" + _hourly_row(4, 1, vals) + "\n"
    rows = parse_hourly_file(text)
    daily = daily_from_hourly(rows, min_coverage=0.75)
    assert len(daily) == 1
    d = daily[0]
    assert d.value == pytest.approx(10.0)
    assert d.hours_valid == 20
    assert d.date == dt.date(2023, 4, 1)


def test_t022_positive_control_sentinel_as_number_explodes_the_mean():
    """T-022 (F-06) 陽性対照: 9999 を数値として平均に入れると値が跳ね上がる。

    これが起きないなら、欠測処理の検査は何も守っていない。
    """
    vals = [10] * 20 + [HOURLY_MISSING] * 4
    naive = sum(vals) / len(vals)
    assert naive > 1000, "陽性対照が発火していない"
    text = HOURLY_HEADER + "\n" + _hourly_row(4, 1, vals) + "\n"
    proper = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)[0].value
    assert proper == pytest.approx(10.0)
    assert abs(naive - proper) > 1000


def test_t021b_low_coverage_day_becomes_missing():
    """被覆が閾値未満の日は欠測にする(SPEC §7 の被覆規律)。"""
    vals = [10] * 10 + [HOURLY_MISSING] * 14        # 被覆 10/24 = 0.42
    text = HOURLY_HEADER + "\n" + _hourly_row(4, 1, vals) + "\n"
    daily = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)
    assert daily[0].value is None
    assert daily[0].hours_valid == 10


def test_t021c_all_missing_day_is_missing_not_zero():
    """全欠測の日を 0 と書かない(SPEC F-15)。"""
    vals = [HOURLY_MISSING] * 24
    text = HOURLY_HEADER + "\n" + _hourly_row(4, 1, vals) + "\n"
    d = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)[0]
    assert d.value is None and d.hours_valid == 0


# --- T-023: 年度 -> 暦日 ------------------------------------------------------

def test_t023_fiscal_year_span():
    """T-023 (F-06): 年度は 4 月始まり。FY2023 = 2023-04-01 .. 2024-03-31。"""
    start, end = fiscal_year_span(2023)
    assert start == dt.date(2023, 4, 1)
    assert end == dt.date(2024, 3, 31)


def test_t023b_hourly_rows_map_month_to_correct_calendar_year():
    """年度内の 1〜3 月は翌暦年になる。"""
    text = (HOURLY_HEADER + "\n"
            + _hourly_row(4, 1, [10] * 24) + "\n"
            + _hourly_row(1, 15, [10] * 24) + "\n")
    daily = daily_from_hourly(parse_hourly_file(text), min_coverage=0.75)
    dates = sorted(d.date for d in daily)
    assert dates == [dt.date(2023, 4, 1), dt.date(2024, 1, 15)]
