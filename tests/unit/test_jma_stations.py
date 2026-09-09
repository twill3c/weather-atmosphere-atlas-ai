"""T-011..T-013 — 観測地点マスタ(SPEC §2.2 / G-03)。

期待値の出所: 地点選択ページの viewPoint() 呼び出しの先頭が、列名そのものを並べた
見出し行になっている(2026-09-08 実測)。列の意味を推測せずに、この見出しに当てて読む。
"""
from __future__ import annotations

import pytest

from jwaa.jma_stations import (
    STATION_HEADER,
    StationHeaderError,
    merge_by_block_no,
    parse_station_page,
)

pytestmark = pytest.mark.unit


def test_t011_unexpected_header_raises():
    """T-011 (G-03): 見出し行が想定と違えば例外。列の意味を推測しない。"""
    html = (
        "<area onmouseover=\"javascript:viewPoint('as','bk_no','ch','SOMETHING_ELSE')\">"
        "<area onmouseover=\"javascript:viewPoint('a','0365','小河内','オゴウチ')\">"
    )
    with pytest.raises(StationHeaderError):
        parse_station_page(html, prec_no="44")


def test_t011b_header_constant_matches_fixture(pref44_html):
    """定数 STATION_HEADER が実物の見出しと一致すること(取り違えの防止)。"""
    from jwaa.jma_stations import extract_header

    assert extract_header(pref44_html) == list(STATION_HEADER)


def test_t012_parses_tokyo_station(pref44_html):
    """T-012 (G-03): 東京(官署 47662)が取れ、座標・標高・要素フラグが読める。

    実測 2026-09-08: viewPoint の引数は
    ('s','47662','東京','トウキヨウ','35','41.5','139','45.0','25.2', ...)。
    lat_m / lon_m は「十進の分」なので 60 で割る。
    """
    stations = parse_station_page(pref44_html, prec_no="44")
    by_block = {s.block_no: s for s in stations}
    tokyo = by_block["47662"]

    assert tokyo.kind == "s"
    assert tokyo.name == "東京"
    assert tokyo.latitude == pytest.approx(35 + 41.5 / 60, abs=1e-9)
    assert tokyo.longitude == pytest.approx(139 + 45.0 / 60, abs=1e-9)
    assert tokyo.elevation_m == pytest.approx(25.2)
    assert tokyo.active is True
    # 官署なので主要要素をすべて持つ
    assert tokyo.has_pressure and tokyo.has_temperature and tokyo.has_sunshine


def test_t012b_page_yields_both_kinds(pref44_html):
    """官署とアメダスが両方取れること(片方しか読めていない故障を捕まえる)。"""
    stations = parse_station_page(pref44_html, prec_no="44")
    kinds = {s.kind for s in stations}
    assert kinds == {"s", "a"}, f"種別が揃っていない: {kinds}"


def test_t013_fuji_merges_across_two_prefectures():
    """T-013 (G-03): 富士山は 2 つの prec_no に出るが、block_no で 1 件に名寄せされる。

    実測 2026-09-08: bk_no=47639 が prec_no 49(山梨)と 50(静岡)の両方に現れる。
    県境の山頂であるため。座標・標高は両者で同一。
    """
    header = "','".join(STATION_HEADER)
    fuji = ("'s','47639','富士山','フジサン','35','21.6','138','43.6','3775.1',"
            "'1','1','1','1','1','1','9999','99','99','','','','',''")
    page = (
        f"<area onmouseover=\"javascript:viewPoint('{header}')\">"
        f"<area onmouseover=\"javascript:viewPoint({fuji})\">"
    )
    a = parse_station_page(page, prec_no="49")
    b = parse_station_page(page, prec_no="50")
    # 前提の固定: 対照が成り立つこと(HC-079)
    assert len(a) == len(b) == 1
    assert a[0].prec_no != b[0].prec_no

    merged = merge_by_block_no(a + b)
    assert list(merged) == ["47639"]
    assert merged["47639"].prec_nos == ["49", "50"]
    assert merged["47639"].latitude == pytest.approx(35 + 21.6 / 60)


def test_t013b_differing_coordinates_for_same_block_raises():
    """同じ block_no で座標が食い違ったら黙って片方を採らない。"""
    header = "','".join(STATION_HEADER)

    def page(lat_m):
        row = (f"'s','47639','富士山','フジサン','35','{lat_m}','138','43.6','3775.1',"
               "'1','1','1','1','1','1','9999','99','99','','','','',''")
        return (f"<area onmouseover=\"javascript:viewPoint('{header}')\">"
                f"<area onmouseover=\"javascript:viewPoint({row})\">")

    a = parse_station_page(page("21.6"), prec_no="49")
    b = parse_station_page(page("99.9"), prec_no="50")
    with pytest.raises(ValueError):
        merge_by_block_no(a + b)
