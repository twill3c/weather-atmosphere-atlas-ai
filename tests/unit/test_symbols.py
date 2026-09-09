"""T-001..T-005 — 気象庁の値欄の記号の読み(SPEC §2.1 / G-01)。

期待値の出所: 気象庁公式凡例
https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html (2026-09-08 取得、
tests/fixtures/jma/remark.html に同梱)。凡例の文言そのものを対照に使う。
"""
from __future__ import annotations

import pytest

from jwaa.symbols import Quality, parse_cell

pytestmark = pytest.mark.unit


# --- T-001 / T-002: '--' と '0.0' は別物 -------------------------------------

def test_t001_dash_is_zero_for_amount_variables():
    """T-001 (G-01): '--' = 該当現象がない。降水量では 0 mm という観測値。"""
    r = parse_cell("--", absent_is_zero=True)
    assert r.value == 0.0
    assert r.quality is Quality.NO_PHENOMENON
    assert r.raw == "--"


def test_t002_explicit_zero_is_trace_not_absence():
    """T-002 (G-01): '0.0' は「量はあるが 0.5 mm に満たない」。'--' と区別できること。"""
    r = parse_cell("0.0", absent_is_zero=True)
    assert r.value == 0.0
    assert r.quality is Quality.VALID
    # 値は同じでも品質で区別できなければ、微量と無降水を取り違える
    assert r.quality is not parse_cell("--", absent_is_zero=True).quality


def test_t001b_dash_without_zero_semantics_is_not_a_number():
    """'--' を 0 と読んでよいのは量的要素だけ。気温などでは値を作らない。"""
    r = parse_cell("--", absent_is_zero=False)
    assert r.value is None
    assert r.quality is Quality.NO_PHENOMENON


# --- T-003: 公式凡例の全記号 -------------------------------------------------

@pytest.mark.parametrize(
    "raw, expect_value, expect_quality",
    [
        ("26.0", 26.0, Quality.VALID),
        ("0", 0.0, Quality.VALID),
        ("0.0", 0.0, Quality.VALID),
        ("--", 0.0, Quality.NO_PHENOMENON),      # absent_is_zero=True で呼ぶ
        ("12.5)", 12.5, Quality.QUASI_NORMAL),   # 準正常値: 値は採る
        ("12.5]", None, Quality.INSUFFICIENT),   # 資料不足値: 値は採らない
        ("×", None, Quality.MISSING),
        ("///", None, Quality.MISSING),
        ("", None, Quality.MISSING),
        ("#", None, Quality.DOUBTFUL),
    ],
)
def test_t003_official_symbol_table(raw, expect_value, expect_quality):
    """T-003 (G-01): SPEC §2.1 の記号表は公式凡例に一致する。"""
    r = parse_cell(raw, absent_is_zero=True)
    assert r.value == expect_value
    assert r.quality is expect_quality


def test_t003b_unknown_symbol_raises():
    """未知の記号を黙って欠測にしない。仮定が崩れたらその場で落ちる(HC-075)。"""
    with pytest.raises(ValueError):
        parse_cell("なにか", absent_is_zero=True)


# --- T-004 / T-005: '--'=欠測 説を実データで否定する --------------------------

def _rain_coverage(tokyo_daily_html, *, dash_is_zero: bool) -> dict[int, float]:
    """東京 2023 の月ごとの降水量被覆率を、'--' の解釈を変えて計算する。"""
    from jwaa.jma_daily import parse_daily_page

    cov = {}
    for month, html in tokyo_daily_html.items():
        rows = parse_daily_page(html, year=2023, month=month)
        readings = [
            parse_cell(r.cells[3], absent_is_zero=dash_is_zero) for r in rows
        ]
        have = sum(1 for x in readings if x.value is not None)
        cov[month] = have / len(readings)
    return cov


def test_t004_positive_control_dash_as_missing_breaks_80pct_rule(tokyo_daily_html):
    """T-004 (G-01) 陽性対照。

    '--' を欠測と解釈すると、東京 2023 の降水量被覆率が 80% を割る月が出る。
    気象庁の凡例では、資料が全体の 80% を下回れば月別値に ')' か ']' が付く。
    実際の公表月別値には 12 か月とも記号が付いていない(2026-09-08 実測)。
    よってこの解釈は公表値と矛盾する。
    """
    cov = _rain_coverage(tokyo_daily_html, dash_is_zero=False)
    below = {m: c for m, c in cov.items() if c < 0.80}
    assert below, (
        "陽性対照が発火していない。'--'=欠測 でも 80% を割る月が出ないなら、"
        "この対照は G-01 を検査していない"
    )


def test_t005_negative_control_dash_as_zero_keeps_full_coverage(tokyo_daily_html):
    """T-005 (G-01) 陰性対照: '--'=0 なら全 12 か月が満被覆になる。"""
    cov = _rain_coverage(tokyo_daily_html, dash_is_zero=True)
    assert set(cov) == set(range(1, 13))
    assert all(c == 1.0 for c in cov.values()), (
        f"満被覆にならない月がある: "
        f"{ {m: c for m, c in cov.items() if c != 1.0} }"
    )


def test_t004b_published_monthly_values_carry_no_shortage_marks(tokyo_monthly_html):
    """T-004 の前提を固定する(HC-079: 対照が成り立つ前提を assert する)。

    公表の月合計降水量に ')' も ']' も付いていないこと。これが崩れると
    T-004 の議論は成立しない。
    """
    from jwaa.jma_daily import parse_monthly_page

    rows = parse_monthly_page(tokyo_monthly_html, year=2023)
    marks = [r.cells[3] for r in rows if ")" in r.cells[3] or "]" in r.cells[3]]
    assert marks == [], f"公表月値に資料不足の記号が付いている: {marks}"
