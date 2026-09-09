"""気象庁の値欄の記号を読む(SPEC §2.1 / G-01)。

出所は気象庁の公式凡例:
https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html (2026-09-08 取得)

    --   該当現象、または該当現象による量等がない場合
    0    量はあるが 1 に足りない
    0.0  量はあるが 0.1 に足りない(降水量は 0.5 mm に足りない)
    )    準正常値(資料が許容範囲で欠けている。全体の 80% が基準)
    ]    資料不足値(値そのものを信用できない)
    ×    欠測
    ///  欠測または未観測
    空白 未観測
    #    値にかなり疑問があるため表示していない

**`--` は欠測ではない。** 降水量で `--` を欠測として扱うと、雨の降らなかった日が
すべて消える。実測(東京 2023)ではそれが 365 日中 189 日に当たり、
月別の被覆率が 80% を割る月が出る —— 気象庁の公表月別値には資料不足の記号が
付いていないので、その解釈は公表値と矛盾する。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class Quality(enum.Enum):
    """観測値の品質。SPEC §7 の `quality` へ写す前の内部表現。"""

    VALID = "valid"
    NO_PHENOMENON = "no_phenomenon"   # '--' 現象が無かった(欠測ではない)
    QUASI_NORMAL = "quasi_normal"     # ')' 準正常値。値は使える
    INSUFFICIENT = "insufficient"     # ']' 資料不足値。値は使わない
    MISSING = "missing"               # '×' '///' 空白
    DOUBTFUL = "doubtful"             # '#' 疑問値


@dataclass(frozen=True)
class Reading:
    """1 つの値欄の読み。`raw` は記号つきの原文を必ず残す(SPEC §7)。"""

    value: float | None
    quality: Quality
    raw: str

    @property
    def is_usable(self) -> bool:
        return self.value is not None


# 値を持たない記号。空白(未観測)は別に扱う。
_MISSING_TOKENS = {"×", "x", "✕", "///", "//", "－"}
_ABSENT = "--"
_DOUBTFUL = "#"


def parse_cell(raw: str, *, absent_is_zero: bool) -> Reading:
    """値欄 1 つを読む。

    `absent_is_zero` は「その要素で `--` が 0 を意味するか」。
    降水量・降雪・積雪・日照時間のような量的要素では真(現象が無い = 0)。
    気温・気圧のような状態量では偽(`--` が出ても 0 ではない)。

    未知の記号は黙って欠測にせず ValueError で落とす。仮定が外れた日に
    実装のほうが教えてくれるようにするため(HC-075)。
    """
    if raw is None:
        raise ValueError("値欄が None")
    s = raw.replace("\xa0", " ").strip()

    if s == "":
        return Reading(None, Quality.MISSING, raw)
    if s == _ABSENT:
        return Reading(0.0 if absent_is_zero else None, Quality.NO_PHENOMENON, raw)
    if s in _MISSING_TOKENS:
        return Reading(None, Quality.MISSING, raw)
    if s == _DOUBTFUL:
        return Reading(None, Quality.DOUBTFUL, raw)

    quality = Quality.VALID
    body = s
    if body.endswith(")"):
        quality, body = Quality.QUASI_NORMAL, body[:-1].strip()
    elif body.endswith("]"):
        quality, body = Quality.INSUFFICIENT, body[:-1].strip()

    # 極値の起日に付く '*' は値そのものには影響しない
    body = body.rstrip("*").strip()

    if body == _ABSENT:
        return Reading(0.0 if absent_is_zero else None, Quality.NO_PHENOMENON, raw)
    if body == "" or body in _MISSING_TOKENS:
        return Reading(None, Quality.MISSING, raw)

    try:
        value = float(body)
    except ValueError as exc:
        raise ValueError(f"値欄を数として読めない: {raw!r}") from exc

    if quality is Quality.INSUFFICIENT:
        # 資料不足値は「値そのものを信用できない」(公式凡例)。値は採らない。
        return Reading(None, quality, raw)
    return Reading(value, quality, raw)


def parse_wind_direction(raw: str) -> tuple[str | None, Quality]:
    """風向欄(十六方位の日本語)。数にはできないので文字のまま返す。"""
    s = (raw or "").replace("\xa0", " ").strip()
    if s in ("", _ABSENT):
        return None, Quality.NO_PHENOMENON if s == _ABSENT else Quality.MISSING
    if s in _MISSING_TOKENS:
        return None, Quality.MISSING
    quality = Quality.VALID
    if s.endswith(")"):
        quality, s = Quality.QUASI_NORMAL, s[:-1].strip()
    elif s.endswith("]"):
        quality, s = Quality.INSUFFICIENT, s[:-1].strip()
    return (s or None), quality
