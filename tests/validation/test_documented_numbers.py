"""T-035 — 文書に書いた数を、出荷物と突き合わせる(HC-152)。

**文書中の数値は実装のテストでは守られない。** テストは実装を守るが、
SPEC・MODEL_CARD・README に書いた数を守るものは何も無い。
しかも数値は具体的なので、後から読むと実測値として振る舞う。

実際にこのプロジェクトで起きた: 大気汚染の全年度がそろって再学習したとき、
SPEC と MODEL_CARD に書いてあった 8 個の数がいっせいに古くなった
(損失・異常度の段差・シルエット・配信物の大きさ・事例との照合)。
検査は全部緑のままだった。

だから**数を生んだ走査をここで再実行して突き合わせる**。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

pytestmark = pytest.mark.validation

ROOT = pathlib.Path(__file__).resolve().parents[2]
AI = ROOT / "public" / "data" / "ai"
MODELS = ROOT / "data" / "models"

needs_ai = pytest.mark.skipif(
    not (AI / "anomaly.json").exists() or not (MODELS / "model_metadata.json").exists(),
    reason="AI 資産またはモデルが未生成",
)


def _docs() -> dict[str, str]:
    return {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in ("SPEC.md", "MODEL_CARD.md", "README.md")
        if (ROOT / name).exists()
    }


def _appears(value: str, *, where: dict[str, str], allow: tuple[str, ...] = ()) -> list[str]:
    """その数が出てくる文書の名前。`allow` に挙げた文書は無視する。"""
    return [n for n, t in where.items() if value in t and n not in allow]


@needs_ai
def test_t035_anomaly_gap_in_docs_matches_the_asset():
    """異常度の「学習と held-out の差」が、資産の値と文書で一致する。"""
    gap = json.loads((AI / "anomaly.json").read_text(encoding="utf-8"))["train_holdout_gap"]
    docs = _docs()
    # 符号つき・小数 1 桁で書いている(例: −6.7)。全角マイナスも許す。
    literal = f"{abs(gap):.1f}"
    hits = _appears(literal, where=docs)
    assert hits, (
        f"資産の train_holdout_gap = {gap} が、どの文書にも書かれていない。"
        f"文書を更新したか確認する(SPEC §8.1 / MODEL_CARD)"
    )


@needs_ai
def test_t035b_silhouette_in_docs_matches_the_asset():
    """シルエット係数が資産と文書で一致する。"""
    cl = json.loads((AI / "clusters.json").read_text(encoding="utf-8"))
    docs = _docs()
    literal = f"{cl['silhouette']:.4f}"
    hits = _appears(literal, where=docs)
    assert hits, f"資産の silhouette = {literal} がどの文書にも無い"

    sils = [t["silhouette"] for t in cl["trials"]]
    lo, hi = f"{min(sils):.4f}", f"{max(sils):.4f}"
    assert _appears(lo, where=docs), f"シルエットの下限 {lo} がどの文書にも無い"
    assert _appears(hi, where=docs), f"シルエットの上限 {hi} がどの文書にも無い"


@needs_ai
def test_t035c_losses_in_model_card_match_the_metadata():
    """MODEL_CARD の最終損失が model_metadata と一致する。"""
    losses = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))["losses"]
    card = (ROOT / "MODEL_CARD.md").read_text(encoding="utf-8")
    for name, value in losses.items():
        literal = f"{value:.4f}"
        assert literal in card, (
            f"{name} の損失 {literal} が MODEL_CARD に無い(古い数が残っている可能性)"
        )


@needs_ai
def test_t035d_epochs_and_split_match():
    meta = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))
    card = (ROOT / "MODEL_CARD.md").read_text(encoding="utf-8")
    assert f"{meta['epochs_run']} epoch" in card, (
        f"epoch 数 {meta['epochs_run']} が MODEL_CARD に無い"
    )
    for period in ("train", "valid", "test"):
        start, end = meta["split"][period]
        assert start in card and end in card, f"{period} の期間 {start}〜{end} が MODEL_CARD に無い"


def test_t035e_delivery_size_in_spec_matches_the_files():
    """SPEC が書いている配信物の大きさが、実際のファイルと一致する。"""
    data_dir = ROOT / "public" / "data"
    if not data_dir.exists():
        pytest.skip("配信物が未生成")
    files = list(data_dir.rglob("*.json"))
    total_mb = sum(f.stat().st_size for f in files) / 1e6
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")

    assert f"{len(files)}" in spec, f"ファイル数 {len(files)} が SPEC に無い"
    assert f"{total_mb:.1f} MB" in spec, (
        f"合計 {total_mb:.1f} MB が SPEC に無い(古い数が残っている可能性)"
    )
    # 1 MB を超えるものが無いという主張も、実物に当てる
    too_big = [f.name for f in files if f.stat().st_size > 1_000_000]
    assert too_big == [], f"1 MB を超える配信物: {too_big}"


def test_t035f_station_counts_in_docs_match_the_manifest():
    """地点数・収録日数が manifest と文書で一致する。"""
    mf_path = ROOT / "public" / "data" / "manifest.json"
    if not mf_path.exists():
        pytest.skip("manifest が未生成")
    counts = json.loads(mf_path.read_text(encoding="utf-8"))["counts"]
    docs = _docs()
    for key, value in counts.items():
        # 3 桁区切りありとなしの両方を許す
        plain, grouped = str(value), f"{value:,}"
        assert _appears(plain, where=docs) or _appears(grouped, where=docs), (
            f"{key} = {value} がどの文書にも書かれていない"
        )
