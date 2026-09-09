"""学習済み Autoencoder から配信用の AI 資産を作る
(SPEC F-08..F-12 / 構想書 §26 §27 §28 §29 §30 §31)。

    .venv/Scripts/python scripts/ml/build_ai_assets.py

出すもの:
    public/data/ai/model.json         モデルの素性(版・次元・分割・損失)
    public/data/ai/anomaly.json       日 -> 異常度 0..100 と変数別の寄与
    public/data/ai/similar_days.json  日 -> 似た日の上位(自分自身は除く)
    public/data/ai/clusters.json      日 -> クラスタ、silhouette で選んだ k
    public/data/ai/umap.json          2 次元に落とした点

守ること:
  * 異常度は再構成誤差の**百分位**であって確率ではない。災害リスクとも呼ばない。
  * 変数別の内訳は「再構成誤差への寄与」。**因果ではない**と明記する。
  * 似た日は自分自身を除く。既定は季節を考慮した比較にする。
  * クラスタのラベルはモデルが付けない。番号だけを出す。
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys

import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from scripts.ml.train_autoencoder import AtmosphericAutoencoder  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "data" / "models"
OUT = ROOT / "public" / "data" / "ai"

VAR_LABEL = {
    "temperature_mean": "平均気温", "temperature_max": "最高気温",
    "temperature_min": "最低気温", "rainfall": "降水量",
    "wind_speed_mean": "風速", "sunshine": "日照時間",
    "humidity_mean": "湿度", "pm25": "PM2.5", "no2": "NO2",
    "so2": "SO2", "ox": "Ox",
}


def season_window(a: str, b: str, days: int = 30) -> bool:
    """暦の上で ±days 日以内か(年をまたぐ回り込みを考える)。"""
    da = dt.date.fromisoformat(a).timetuple().tm_yday
    db = dt.date.fromisoformat(b).timetuple().tm_yday
    diff = abs(da - db)
    return min(diff, 366 - diff) <= days


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", default=str(PROCESSED / "features.npz"))
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--season-days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data = np.load(args.features, allow_pickle=True)
    matrix = data["matrix"].astype(np.float32)
    dates = [str(d) for d in data["dates"]]
    columns = [str(c) for c in data["columns"]]
    mask = data["mask"].astype(np.float32)
    n_values = len(columns)

    meta = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))
    model = AtmosphericAutoencoder(matrix.shape[1], n_values, meta["latent_dim"])
    model.load_state_dict(torch.load(MODELS / "autoencoder.pt", map_location="cpu"))
    model.eval()

    with torch.no_grad():
        X = torch.from_numpy(matrix)
        recon, latent = model(X)
        recon = recon.numpy()
        emb = latent.numpy()

    OUT.mkdir(parents=True, exist_ok=True)

    # --- 異常度は別工程が作る -------------------------------------------------
    # 異常度は `build_anomaly.py` が**時間ブロックの交差適合**で作る。
    # ここで全期間モデルの再構成誤差から作ると、学習した期間だけ誤差が小さくなり、
    # 「学習したかどうか」を測る指標になる(HC-251)。ここでは読むだけ。
    anomaly_path = OUT / "anomaly.json"
    if not anomaly_path.exists():
        raise SystemExit(
            "anomaly.json が無い。先に scripts/ml/build_anomaly.py を実行する"
        )
    anomaly = json.loads(anomaly_path.read_text(encoding="utf-8"))
    score = np.array([anomaly["scores"].get(d, 50.0) for d in dates])
    print(f"異常度を読み込み {len(anomaly['scores']):,} 日 "
          f"(学習期間と held-out の差 {anomaly.get('train_holdout_gap')} 点)")

    # --- 類似日: コサイン類似度、季節を考慮、自分自身は除く --------------------
    norm = emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9)
    doy = np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in dates])
    neighbors: dict[str, list[dict]] = {}
    for i, d in enumerate(dates):
        sims = norm @ norm[i]
        diff = np.abs(doy - doy[i])
        in_season = np.minimum(diff, 366 - diff) <= args.season_days
        in_season[i] = False                      # 自分自身を除く(G-09)
        cand = np.flatnonzero(in_season)
        if len(cand) == 0:
            continue
        top = cand[np.argsort(-sims[cand])[: args.top_k]]
        neighbors[d] = [
            {"date": dates[j], "score": round(float(sims[j]), 4)} for j in top
        ]
    # **年で割る。** 全期間を 1 ファイルにすると 1.4 MB になり、
    # 「巨大な JSON を配らない」(SPEC N-03)に反する。比較画面は
    # 選んだ日の年だけを読めばよい。
    sim_dir = OUT / "similar"
    sim_dir.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict] = collections.defaultdict(dict)
    for d, lst in neighbors.items():
        by_year[d[:4]][d] = lst
    for year, block in sorted(by_year.items()):
        (sim_dir / f"{year}.json").write_text(json.dumps({
            "model_version": meta["version"],
            "mode": f"season-aware (±{args.season_days} 日)",
            "year": year,
            "neighbors": block,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    biggest = max(p.stat().st_size for p in sim_dir.glob("*.json"))
    print(f"類似日 {len(neighbors):,} 日 × 上位 {args.top_k} "
          f"({len(by_year)} 年ファイル・最大 {biggest / 1e3:.0f} KB)")

    # --- クラスタ: silhouette で k を決める -----------------------------------
    best_k, best_score, best_labels = None, -2.0, None
    trials = []
    sample = np.random.default_rng(args.seed).choice(
        len(emb), size=min(2000, len(emb)), replace=False)
    for k in range(6, 17):
        km = KMeans(n_clusters=k, random_state=args.seed, n_init=10).fit(norm)
        s = float(silhouette_score(norm[sample], km.labels_[sample]))
        trials.append({"k": k, "silhouette": round(s, 4)})
        if s > best_score:
            best_k, best_score, best_labels = k, s, km.labels_
    print(f"クラスタ k={best_k}(silhouette {best_score:.4f})")
    print("  " + " ".join(f"{t['k']}:{t['silhouette']:.3f}" for t in trials))

    # ラベルはモデルが付けない。統計を添えて、人が後から言葉にする(構想書 §30)。
    season_of = {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
                 6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}
    stats: dict[str, dict] = {}
    for k in range(best_k):
        sel = best_labels == k
        months = collections.Counter(
            season_of[int(d[5:7])] for d, s in zip(dates, sel) if s)
        stats[str(k)] = {
            "days": int(sel.sum()),
            "seasons": dict(months.most_common()),
            "mean_anomaly": round(float(score[sel].mean()), 1),
        }
    (OUT / "clusters.json").write_text(json.dumps({
        "model_version": meta["version"],
        "k": int(best_k),
        "silhouette": round(best_score, 4),
        "trials": trials,
        "note": "番号はモデルが付けたもの。説明の語は統計を見て人が付ける",
        "stats": stats,
        "labels": {},
        "assignment": {d: int(best_labels[i]) for i, d in enumerate(dates)},
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- UMAP ----------------------------------------------------------------
    import umap

    reducer = umap.UMAP(n_neighbors=30, min_dist=0.1, metric="cosine",
                        random_state=args.seed)
    xy = reducer.fit_transform(norm)
    (OUT / "umap.json").write_text(json.dumps({
        "model_version": meta["version"],
        "points": [
            {"date": d, "x": round(float(xy[i, 0]), 3),
             "y": round(float(xy[i, 1]), 3),
             "cluster": int(best_labels[i]),
             "anomaly": round(float(score[i]), 1)}
            for i, d in enumerate(dates)
        ],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"UMAP {len(dates):,} 点")

    (OUT / "model.json").write_text(json.dumps({
        "model_version": meta["version"],
        "latent_dim": meta["latent_dim"],
        "embedding_days": len(dates),
        "clusters": int(best_k),
        "silhouette": round(best_score, 4),
        "split": meta["split"],
        "losses": meta["losses"],
        "seed": args.seed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(p.stat().st_size for p in OUT.glob("*.json"))
    print(f"AI 資産 {total / 1e6:.1f} MB -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
