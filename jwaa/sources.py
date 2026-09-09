"""外部データ源の所在(SPEC §2 / 構想書 §70)。

URL を 1 か所に集める。取得経路が変わったときに直す場所を 1 つにするため。
すべて 2026-09-08 に到達を確認した。
"""
from __future__ import annotations

from typing import Final

# --- 気象庁 -----------------------------------------------------------------

#: 過去の気象データ検索。構想書 §101 の /obd/stats/etrn/ は 301 でここへ移る。
JMA_ETRN: Final = "https://www.data.jma.go.jp/stats/etrn"
JMA_DAILY: Final = JMA_ETRN + "/view/daily_s1.php"
JMA_MONTHLY: Final = JMA_ETRN + "/view/monthly_s1.php"
JMA_SELECT_TOP: Final = JMA_ETRN + "/select/prefecture00.php"
JMA_SELECT_PREF: Final = JMA_ETRN + "/select/prefecture.php"

#: 値欄の記号の説明(SPEC §2.1 の表の出所)
JMA_REMARK: Final = "https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html"

#: 温室効果ガス(大気・海洋環境観測年報)
JMA_GHG_INDEX: Final = (
    "https://www.data.jma.go.jp/env/data/report/data/download/atm_bg_j.html")
JMA_GHG_ZIP: Final = (
    "https://www.data.jma.go.jp/env/data/report/data/download/atm_bg/{species}.zip")

#: CO2 年平均値(非循環オラクルの相手側)
JMA_CO2_YEARAVE: Final = (
    "https://www.data.jma.go.jp/ghg/kanshi/obs/co2_yearave.html")

JMA_TERMS: Final = "https://www.jma.go.jp/jma/kishou/info/coment.html"

# --- 国立環境研究所 ---------------------------------------------------------

NIES_DOWNLOAD: Final = "https://tenbou.nies.go.jp/download/"
NIES_API: Final = "https://tenbou.nies.go.jp/download/api/"
NIES_SEARCH: Final = NIES_API + "searchfile.php"
NIES_ARCHIVE_DOWNLOAD: Final = NIES_API + "archivedownload.php"
NIES_YEARLIST: Final = NIES_API + "yearlist.php"
NIES_COPYRIGHT: Final = "https://tenbou.nies.go.jp/copyright/"

#: 環境展望台はブラウザ以外の UA を弾くことがある(実測 2026-09-08)
NIES_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

#: 種別コード。**画面の見出しとは対応していない**(SPEC §2.4 の表)
NIES_TYPE_STATION_MASTER: Final = "tm"
NIES_TYPE_ANNUAL_SUMMARY: Final = "td"
NIES_TYPE_HOURLY_BY_PREF: Final = "tj"
NIES_TYPE_HOURLY_NATIONAL: Final = "tk"

#: 時間値(tj)が在る年度。実測 2026-09-08: 2009–2023 の 15 年度。
NIES_HOURLY_FIRST_FY: Final = 2009
NIES_HOURLY_LAST_FY: Final = 2023

# --- 国土地理院 -------------------------------------------------------------

GSI_TILE: Final = "https://cyberjapandata.gsi.go.jp/xyz/{style}/{z}/{x}/{y}.png"
GSI_ATTRIBUTION: Final = "地理院タイル"
GSI_TERMS: Final = (
    "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html")


def jma_daily_url(prec_no: str, block_no: str, year: int, month: int) -> str:
    return (f"{JMA_DAILY}?prec_no={prec_no}&block_no={block_no}"
            f"&year={year}&month={month}&day=&view=")


def jma_monthly_url(prec_no: str, block_no: str, year: int) -> str:
    return (f"{JMA_MONTHLY}?prec_no={prec_no}&block_no={block_no}"
            f"&year={year}&month=&day=&view=")


def jma_pref_url(prec_no: str) -> str:
    return f"{JMA_SELECT_PREF}?prec_no={prec_no}&block_no=&year=&month=&day=&view="
