"""テスト共通の道具立て。フィクスチャは配布形のまま読む。"""
from __future__ import annotations

import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
JMA = FIXTURES / "jma"
CACHE = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache"

TOKYO_PREC = "44"
TOKYO_BLOCK = "47662"
TOKYO_YEAR = 2023


@pytest.fixture(scope="session")
def jma_dir() -> pathlib.Path:
    return JMA


@pytest.fixture(scope="session")
def tokyo_daily_html() -> dict[int, str]:
    """東京 2023 年の日別ページ 12 か月ぶん(気象庁・2026-09-08 取得)。"""
    out = {}
    for m in range(1, 13):
        p = JMA / f"daily_tokyo_2023_{m:02d}.html"
        out[m] = p.read_text(encoding="utf-8")
    assert len(out) == 12, "12 か月そろっていないフィクスチャで月別照合はできない"
    return out


@pytest.fixture(scope="session")
def tokyo_monthly_html() -> str:
    return (JMA / "monthly_tokyo_2023.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def pref44_html() -> str:
    return (JMA / "pref44.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def co2_yearave_html() -> str:
    return (JMA / "co2_yearave.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def ghg_dir() -> pathlib.Path:
    return JMA / "ghg_monthly"
