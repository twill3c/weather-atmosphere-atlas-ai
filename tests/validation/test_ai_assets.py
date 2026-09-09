"""T-030..T-034 — 配信した AI 資産の検査(SPEC G-08..G-11, G-19)。

出荷物そのものに当てる。資産が未生成なら skip するが、**skip を成功と読み替えない**
(実行時に件数を報告する)。

T-034 は HC-251 の再発防止である。異常度は「学習したかどうか」ではなく
「気象がどれだけ外れているか」を測っていなければならない。
"""
from __future__ import annotations

import json
import pathlib
import statistics

import pytest

pytestmark = pytest.mark.validation

ROOT = pathlib.Path(__file__).resolve().parents[2]
AI = ROOT / "public" / "data" / "ai"
MODELS = ROOT / "data" / "models"

needs_ai = pytest.mark.skipif(
    not (AI / "anomaly.json").exists(),
    reason="AI 資産が未生成(scripts/ml/build_anomaly.py と build_ai_assets.py)",
)


def _load(name: str):
    return json.loads((AI / name).read_text(encoding="utf-8"))


def _all_neighbors() -> dict[str, list[dict]]:
    """類似日は年ごとのファイルに分かれている(1 本にすると 1.4 MB になる — N-03)。
    検査は全年をまとめて見る。"""
    out: dict[str, list[dict]] = {}
    files = sorted((AI / "similar").glob("*.json"))
    assert files, "類似日のファイルが 1 つも無い"
    for f in files:
        out.update(json.loads(f.read_text(encoding="utf-8"))["neighbors"])
    return out


@needs_ai
def test_t032_anomaly_scores_are_in_range():
    """T-032 (G-10): 異常度が 0..100 に収まる。"""
    scores = _load("anomaly.json")["scores"]
    assert scores, "異常度が空"
    bad = {d: v for d, v in scores.items() if not (0.0 <= v <= 100.0)}
    assert bad == {}, f"0..100 を外れる異常度: {list(bad.items())[:5]}"


@needs_ai
def test_t034_anomaly_does_not_track_the_training_split():
    """T-034 (G-19): 異常度が「学習期間かどうか」を測っていない。

    Autoencoder は学習した期間をよく再構成するので、素朴に全期間で百分位を取ると
    held-out の平凡な日が高い異常度になる。**実測 2026-09-10 でこれが起きた**:
    学習期間の中央値 36.7 に対し held-out 85.7、差 +48.1 点(HC-251)。
    交差適合に直したので、差は 10 点以内でなければならない。
    """
    data = _load("anomaly.json")
    scores = data["scores"]
    split = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))["split"]

    train, held = [], []
    for date, v in scores.items():
        (train if date <= split["train"][1] else held).append(v)

    # 対照が成り立つ前提を固定する(HC-079)
    assert len(train) > 100 and len(held) > 100, (
        f"どちらかの期間が小さすぎて比較にならない: 学習 {len(train)} / held-out {len(held)}"
    )

    gap = statistics.median(held) - statistics.median(train)
    assert abs(gap) <= 10.0, (
        f"学習期間と held-out の異常度の中央値の差が {gap:+.1f} 点。"
        f"異常度が『学習したかどうか』を測っている(HC-251)。"
        f"学習 {statistics.median(train):.1f} / held-out {statistics.median(held):.1f}"
    )


@needs_ai
def test_t034b_method_is_recorded():
    """どうやって作ったかが資産に書いてあること(後から読む人のため)。"""
    data = _load("anomaly.json")
    assert "交差適合" in data.get("method", ""), data.get("method")
    assert "train_holdout_gap" in data


@needs_ai
def test_t031_similar_days_never_include_the_day_itself():
    """T-031 (G-09): 類似日に自分自身が入らない。"""
    neighbors = _all_neighbors()
    assert neighbors, "類似日が空"
    self_hits = [d for d, lst in neighbors.items()
                 if any(n["date"] == d for n in lst)]
    assert self_hits == [], f"自分自身を返した日: {self_hits[:5]}"


@needs_ai
def test_t031b_similar_scores_are_cosine_similarities():
    """類似度は -1..1 に収まる(コサイン類似度である)。"""
    neighbors = _all_neighbors()
    bad = [(d, n) for d, lst in neighbors.items() for n in lst
           if not (-1.0001 <= n["score"] <= 1.0001)]
    assert bad == [], f"範囲外の類似度: {bad[:3]}"


@needs_ai
def test_t030_assets_share_one_set_of_dates():
    """T-030 (G-08): 異常度・クラスタ・UMAP が同じ日の集合を扱っている。

    別々の日を扱っていると、画面で突き合わせたときに黙って食い違う。
    """
    anomaly = set(_load("anomaly.json")["scores"])
    clusters = set(_load("clusters.json")["assignment"])
    umap = {p["date"] for p in _load("umap.json")["points"]}
    assert anomaly == clusters == umap, (
        f"日の集合が違う: 異常度 {len(anomaly)} / クラスタ {len(clusters)} / "
        f"UMAP {len(umap)}"
    )


@needs_ai
def test_t030b_no_nan_in_shipped_ai_assets():
    """T-030 (G-08): 配信物に NaN / Infinity が混ざっていない。

    JSON の仕様には NaN が無いので、混ざるとブラウザの JSON.parse が落ちる。
    """
    targets = [AI / n for n in ("anomaly.json", "clusters.json", "umap.json")]
    targets += sorted((AI / "similar").glob("*.json"))
    assert len(targets) > 3, "類似日のファイルが見えていない"
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in ("NaN", "Infinity", "-Infinity"):
            assert token not in text, f"{path.name} に {token} が入っている"


@needs_ai
def test_t030c_umap_points_are_finite_and_labelled():
    points = _load("umap.json")["points"]
    assert len(points) > 100
    k = _load("clusters.json")["k"]
    for p in points:
        assert isinstance(p["x"], (int, float)) and isinstance(p["y"], (int, float))
        assert 0 <= p["cluster"] < k, f"クラスタ番号が範囲外: {p}"
        assert 0.0 <= p["anomaly"] <= 100.0


@pytest.mark.skipif(not (MODELS / "model_metadata.json").exists(),
                    reason="モデルが未学習")
def test_t033_splits_are_ordered_and_disjoint():
    """T-033 (G-11): 学習・検証・試験が時系列順に並び、重ならない。"""
    split = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))["split"]
    train, valid, test = split["train"], split["valid"], split["test"]
    assert train[0] <= train[1] < valid[0] <= valid[1] < test[0] <= test[1], split


@needs_ai
def test_t030d_similar_days_are_split_by_year():
    """T-030 (N-03): 類似日が年ごとに分かれ、どれも 1 MB を超えない。

    1 本にまとめると 1.4 MB になり「巨大な JSON を配らない」に反した(実測)。
    """
    files = sorted((AI / "similar").glob("*.json"))
    assert len(files) >= 5, f"年ファイルが少なすぎる: {len(files)}"
    assert not (AI / "similar_days.json").exists(), "分割前のファイルが残っている"
    too_big = [f.name for f in files if f.stat().st_size > 1_000_000]
    assert too_big == [], f"1 MB を超える類似日ファイル: {too_big}"
    # 年ファイルの日付が、その年のものだけであること
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        stray = [d for d in data["neighbors"] if not d.startswith(data["year"])]
        assert stray == [], f"{f.name} に別の年の日付: {stray[:3]}"
