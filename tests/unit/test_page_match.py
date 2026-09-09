"""T-027 — 要求と応答の対応(SPEC §2.1 / G-02、HC-241)。

状態コードと URL の形は「要求したものが返ってきたこと」を保証しない。
要求に入れた鍵(地点・年月)が応答の本文に現れることを確かめる。
"""
from __future__ import annotations

import pytest

from jwaa.jma_daily import PageStructureError, assert_page_matches, parse_caption

pytestmark = pytest.mark.unit


def test_t027_caption_is_readable(tokyo_daily_html):
    """T-027 (G-02): 見出しから地点名と年月が読める。

    実測 2026-09-08: 「東京（東京都)　2023年8月（日ごとの値）　主な要素」。
    """
    cap = parse_caption(tokyo_daily_html[8])
    assert cap.station == "東京"
    assert cap.area == "東京都"
    assert (cap.year, cap.month) == (2023, 8)


@pytest.mark.parametrize("month", list(range(1, 13)))
def test_t027b_every_fixture_matches_its_request(tokyo_daily_html, month):
    """全 12 か月で、応答が要求した年月のものであること。"""
    cap = assert_page_matches(tokyo_daily_html[month], year=2023, month=month,
                              station_name="東京")
    assert cap.month == month


def test_t027c_wrong_month_is_detected(tokyo_daily_html):
    """陽性対照: 別の月の応答は検出される。"""
    with pytest.raises(PageStructureError):
        assert_page_matches(tokyo_daily_html[8], year=2023, month=9)


def test_t027d_wrong_station_is_detected(tokyo_daily_html):
    """陽性対照: 別の地点の応答は検出される。

    取り違えた応答を保存すると、以後の実行はそれを『取得済み』として読む。
    """
    with pytest.raises(PageStructureError):
        assert_page_matches(tokyo_daily_html[8], year=2023, month=8,
                            station_name="大阪")


def test_t027e_stub_page_has_no_caption():
    """データ表の無い短いページは見出しも持たない。"""
    with pytest.raises(PageStructureError):
        parse_caption("<html><body>該当データがありません</body></html>")
