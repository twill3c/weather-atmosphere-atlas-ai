"""T-006..T-010 — 日別ページの読みと、公表月別値との突き合わせ(SPEC §2.1 / G-02, G-05)。

オラクル: 気象庁は「日ごとの値」と「月ごとの値」を別々に公表している。
日別を集計した値が月別の公表値と一致することは、日別ページの列の切り出しと
記号の解釈が正しいことの、独立した証拠になる(我々の解釈を気象庁側は使っていない)。
"""
from __future__ import annotations

import calendar
import statistics

import pytest

from jwaa.jma_daily import (
    COL,
    MCOL,
    PageStructureError,
    parse_daily_page,
    parse_monthly_page,
)
from jwaa.symbols import parse_cell

pytestmark = pytest.mark.unit


# --- T-006 / T-007: 壊れた応答で止まること ------------------------------------

def test_t006_missing_table_raises(tokyo_daily_html):
    """T-006 (G-02): データ表の無いページは例外。黙って空を返さない。

    実測 2026-09-08: prec_no と block_no の対が不整合だと HTTP 200 と
    3,814 バイトの短いページが返る。状態コードだけを見る取得器はこれを通す。
    """
    stub = "<html><body><p>該当データがありません</p></body></html>"
    with pytest.raises(PageStructureError):
        parse_daily_page(stub, year=2023, month=8)


def test_t007_row_count_mismatch_raises(tokyo_daily_html):
    """T-007 (G-02): 日付行数が当月日数と合わなければ例外。"""
    html = tokyo_daily_html[8]          # 8 月 = 31 日
    with pytest.raises(PageStructureError):
        parse_daily_page(html, year=2023, month=9)   # 9 月 = 30 日 として読む


def test_t007b_control_correct_month_does_not_raise(tokyo_daily_html):
    """T-007 の対照: 正しい月なら通ること(検査が常に落ちるだけではない)。"""
    rows = parse_daily_page(tokyo_daily_html[8], year=2023, month=8)
    assert len(rows) == 31


# --- T-008: 正常な応答の形 ----------------------------------------------------

@pytest.mark.parametrize("month", list(range(1, 13)))
def test_t008_rows_match_calendar(tokyo_daily_html, month):
    """T-008 (G-02): 行数が当月日数と一致し、日が 1..日数の連続になる。"""
    ndays = calendar.monthrange(2023, month)[1]
    rows = parse_daily_page(tokyo_daily_html[month], year=2023, month=month)
    assert [r.day for r in rows] == list(range(1, ndays + 1))
    # 列数は一定(実測 2026-09-08: 東京 2023 の全 12 か月で 21 列)
    assert {len(r.cells) for r in rows} == {21}


# --- T-009 / T-010: 公表月別値との一致 ----------------------------------------

def _published(tokyo_monthly_html):
    rows = parse_monthly_page(tokyo_monthly_html, year=2023)
    return {r.month: r for r in rows}


def test_t009_daily_rainfall_sum_matches_published_monthly_total(
    tokyo_daily_html, tokyo_monthly_html
):
    """T-009 (G-05): 日別降水量の月合計が公表の月合計と一致する。

    期待値の出所: 気象庁公表の「月ごとの値」(2026-09-08 取得)。
    母集団: 東京(block_no 47662)2023 年の 12 か月・365 日。
    """
    pub = _published(tokyo_monthly_html)
    mismatches = []
    for month, html in tokyo_daily_html.items():
        rows = parse_daily_page(html, year=2023, month=month)
        vals = [parse_cell(r.cells[COL.RAIN_TOTAL], absent_is_zero=True).value
                for r in rows]
        assert all(v is not None for v in vals), f"{month} 月に読めない日がある"
        mine = round(sum(vals), 1)
        theirs = parse_cell(pub[month].cells[MCOL.RAIN_TOTAL],
                            absent_is_zero=True).value
        if abs(mine - theirs) > 0.05:
            mismatches.append((month, mine, theirs))
    assert mismatches == [], f"月合計が公表値と食い違う: {mismatches}"


def test_t010_daily_temp_mean_matches_published_monthly_mean(
    tokyo_daily_html, tokyo_monthly_html
):
    """T-010 (G-05): 日別平均気温の月平均が公表の月平均と一致する(丸め 0.1)。

    公表値は 0.1 度に丸められているので、比較は 0.05 の許容で行う。
    SPEC の保証粒度(公表の丸め)を超える精度を要求しない(HC-016)。
    """
    pub = _published(tokyo_monthly_html)
    mismatches = []
    for month, html in tokyo_daily_html.items():
        rows = parse_daily_page(html, year=2023, month=month)
        vals = [parse_cell(r.cells[COL.TEMP_MEAN], absent_is_zero=False).value
                for r in rows]
        assert all(v is not None for v in vals), f"{month} 月に読めない日がある"
        mine = statistics.fmean(vals)
        theirs = parse_cell(pub[month].cells[MCOL.TEMP_MEAN],
                            absent_is_zero=False).value
        if abs(mine - theirs) > 0.05:
            mismatches.append((month, round(mine, 3), theirs))
    assert mismatches == [], f"月平均気温が公表値と食い違う: {mismatches}"


def test_t010b_daily_and_monthly_column_maps_differ(tokyo_monthly_html):
    """月別表に日別用の列定数を当てると、黙って別の量を読むことの対照。

    実測 2026-09-08: 月別表は 0 月 / 3 降水量合計 / 7 平均気温 で、
    日別表の 6 = 平均気温 とはずれる。この違いを固定しておかないと、
    定数を取り違えても『それらしい数』が出て検査を素通りする。
    """
    assert COL.TEMP_MEAN != MCOL.TEMP_MEAN
    pub = _published(tokyo_monthly_html)
    correct = parse_cell(pub[1].cells[MCOL.TEMP_MEAN], absent_is_zero=False).value
    wrong = parse_cell(pub[1].cells[COL.TEMP_MEAN], absent_is_zero=True).value
    # 2023 年 1 月の東京: 平均気温 5.7 度、最大10分間降水量 1.0 mm(公表値)
    assert correct == pytest.approx(5.7)
    assert wrong != pytest.approx(correct), (
        "対照が発火していない。両者が同じ値なら、この取り違えは検出できない"
    )


def test_t009b_column_map_is_anchored_to_header(tokyo_daily_html):
    """列の位置を決め打ちしていないことを、見出し自身に当てて確かめる。

    列の意味を推測で固定すると、表が変わったとき黙って別の量を読む。
    """
    from jwaa.jma_daily import daily_header_labels

    labels = daily_header_labels(tokyo_daily_html[8])
    assert "降水量" in labels[COL.RAIN_TOTAL]
    assert "気温" in labels[COL.TEMP_MEAN]
    assert "日照" in labels[COL.SUNSHINE]
