"""T-014..T-018 — 温室効果ガス(SPEC §2.3 / G-04, G-06)。

非循環オラクル: 気象庁は CO2 の年平均値を別ページで公表している
(https://www.data.jma.go.jp/ghg/kanshi/obs/co2_yearave.html)。
配布 ZIP の月別値から我々が計算した年平均が公表値と一致すれば、
固定長の切り出し・欠測センチネル・品質フラグの解釈が正しいと言える。
気象庁は年平均を独自の手順で出しており、我々の経路を使っていない。
"""
from __future__ import annotations

import itertools

import pytest

from jwaa.ghg import (
    MISSING_SENTINEL,
    STATIONS,
    annual_means,
    parse_monthly_file,
    parse_published_yearave,
)

pytestmark = pytest.mark.unit

SERIES = [(sp, st) for sp in ("co2", "ch4") for st in ("ry", "mi", "yo")]


@pytest.fixture(scope="module")
def series(ghg_dir):
    return {(sp, st): parse_monthly_file((ghg_dir / f"{st}_m.{sp}").read_text("ascii"),
                                         species=sp, station=st)
            for sp, st in SERIES}


# --- T-014 / T-015: 書式そのものの不変量 --------------------------------------

@pytest.mark.parametrize("sp,st", SERIES)
def test_t014_sentinel_and_flag_agree(series, sp, st):
    """T-014 (G-06): 欠測センチネルと品質フラグが全行で整合する。

    readme(同梱)より: 欠測は '99999.99'、月別値のフラグ F は 3 = 有効。
    実測 2026-09-08: 6 系列 計 2,208 行で不一致 0 件。
    ここでは件数を定数で書かず「不一致が無い」という不変量で書く。
    """
    rows = series[(sp, st)]
    assert rows, "行が読めていない"
    bad = [r for r in rows if (r.raw_value >= MISSING_SENTINEL) != (r.flag != 3)]
    assert bad == [], f"{sp}/{st} でセンチネルとフラグが食い違う行: {bad[:3]}"


@pytest.mark.parametrize("sp,st", SERIES)
def test_t015_monthly_files_use_day_99(series, sp, st):
    """T-015 (G-06): 月別ファイルの DD 欄はすべて 99(readme の約束)。"""
    assert {r.day_field for r in series[(sp, st)]} == {99}


@pytest.mark.parametrize("sp,st", SERIES)
def test_t018_time_axis_is_strictly_increasing(series, sp, st):
    """T-018 (F-07): 時刻が単調増加で重複が無い。"""
    keys = [(r.year, r.month) for r in series[(sp, st)]]
    assert len(keys) == len(set(keys)), "同じ年月が二度出ている"
    assert keys == sorted(keys), "年月が昇順でない"


def test_t014b_missing_rows_have_no_usable_value(series):
    """欠測行が value=None になり、集計に混ざらないこと。"""
    for key, rows in series.items():
        for r in rows:
            if r.flag != 3:
                assert r.value is None, f"{key} の欠測行に値が入っている: {r}"


# --- T-016 / T-017: 公表年平均との照合 ----------------------------------------

def test_t016_annual_means_match_published(series, co2_yearave_html):
    """T-016 (G-04): CO2 の年平均が公表値と、公表の丸め(0.1 ppm)まで一致する。

    12 か月そろう年だけを比べる(公表側は欠測年に * を付けており、
    平均の取り方が同じとは限らないため — SPEC の保証粒度を超えない)。
    母集団: 綾里・南鳥島・与那国島 の CO2、1987–2023。
    """
    published = parse_published_yearave(co2_yearave_html)
    assert published, "公表表が読めていない"

    compared = 0
    mismatches = []
    for st in ("ry", "mi", "yo"):
        for year, (mean, n) in annual_means(series[("co2", st)]).items():
            if n != 12 or (st, year) not in published:
                continue
            pub = published[(st, year)]
            if pub.provisional:
                continue
            compared += 1
            if abs(round(mean, 1) - pub.value) > 0.05:
                mismatches.append((st, year, round(mean, 3), pub.value))

    assert compared >= 80, f"照合できた観測点年が少なすぎる: {compared}"
    assert mismatches == [], f"公表年平均と食い違う: {mismatches}"


def test_t017_published_asterisk_means_incomplete_year(series, co2_yearave_html):
    """T-017 (G-04): 公表表の '*' が付く年は、有効月数が 12 未満である。

    これは記号の意味を実測で確かめる検査。'*' の意味を我々が決めているのではなく、
    月別ファイル側の有効月数から独立に確かめている。
    """
    published = parse_published_yearave(co2_yearave_html)
    checked = 0
    wrong = []
    for st in ("ry", "mi", "yo"):
        counts = {y: n for y, (m, n) in annual_means(series[("co2", st)]).items()}
        for (pst, year), pub in published.items():
            if pst != st or year not in counts or pub.provisional:
                continue
            if pub.asterisk:
                checked += 1
                if counts[year] >= 12:
                    wrong.append((st, year, counts[year]))
    assert checked > 0, "'*' の付いた年が 1 つも無いなら、この検査は何も言っていない"
    assert wrong == [], f"'*' が付くのに 12 か月そろっている年: {wrong}"


def test_t016b_station_codes_are_the_three_documented_ones():
    """readme が定める観測点コードから外れていないこと。"""
    assert set(STATIONS) == {"ry", "mi", "yo"}
    assert STATIONS["ry"] == "綾里"
