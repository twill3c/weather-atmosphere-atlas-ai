"""異常度を交差適合で作る(SPEC F-10 / G-19、HC-251)。

    .venv/Scripts/python scripts/ml/build_anomaly.py

**なぜ交差適合か。**
Autoencoder は学習した期間をよく再構成するので、再構成誤差には分割の段差が入る。
全期間の百分位を素朴に取ると、その段差がそのまま異常度になった —— 実測では
学習期間の中央値 36.7 に対し held-out は 85.7 で、差 +48.1 点。
「2022 年のありふれた日が異常度 85」という嘘になる。

そこで時間を K 個の連続ブロックに割り、**各ブロックを、そのブロックを含まないデータで
学習したモデルで採点する**。どの日も自分を見ていないモデルに測られるので、
再構成誤差が期間をまたいで比べられる。

埋め込み(類似日・クラスタ・UMAP)はこの経路を使わない。あちらは
**潜在空間が揃っていること**が要るので、全期間で学習した 1 つのモデルを使う。
用途が違うので分ける。
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from scripts.ml.train_autoencoder import (                  # noqa: E402
    AtmosphericAutoencoder,
    masked_mse,
)

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


def train_fold(matrix, mask, n_values, fit_idx, val_idx, *, latent_dim, epochs,
               batch_size, lr, patience, seed, device):
    """1 つの折を学習する。early stopping には fit の内側の末尾を使う。"""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    X = torch.from_numpy(matrix).to(device)
    Y = torch.from_numpy(matrix[:, :n_values]).to(device)
    M = torch.from_numpy(mask).to(device)

    model = AtmosphericAutoencoder(matrix.shape[1], n_values, latent_dim).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    inner = torch.from_numpy(val_idx).to(device)
    best, best_state, since = float("inf"), None, 0
    for _ in range(epochs):
        model.train()
        perm = rng.permutation(fit_idx)
        for k in range(0, len(perm), batch_size):
            b = torch.from_numpy(perm[k:k + batch_size]).to(device)
            pred, _ = model(X[b])
            loss = masked_mse(pred, Y[b], M[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pred, _ = model(X[inner])
            v = float(masked_mse(pred, Y[inner], M[inner]))
        if v < best - 1e-6:
            best, since = v, 0
            best_state = {k: t.detach().clone() for k, t in model.state_dict().items()}
        else:
            since += 1
            if since >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", default=str(PROCESSED / "features.npz"))
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data = np.load(args.features, allow_pickle=True)
    matrix = data["matrix"].astype(np.float32)
    dates = [str(d) for d in data["dates"]]
    columns = [str(c) for c in data["columns"]]
    mask = data["mask"].astype(np.float32)
    n_values = len(columns)
    meta = json.loads((MODELS / "model_metadata.json").read_text(encoding="utf-8"))
    latent_dim = meta["latent_dim"]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n = len(dates)
    # 時間の連続ブロックに割る。日付は昇順なので添字を等分すればよい。
    bounds = [round(i * n / args.folds) for i in range(args.folds + 1)]
    per_day = np.full(n, np.nan)
    sq_all = np.zeros((n, n_values), dtype=np.float64)

    started = time.time()
    for f in range(args.folds):
        lo, hi = bounds[f], bounds[f + 1]
        held = np.arange(lo, hi)
        rest = np.concatenate([np.arange(0, lo), np.arange(hi, n)])
        # early stopping 用に、学習に使う側の末尾 15% を内側の検証に回す
        cut = int(len(rest) * 0.85)
        fit_idx, inner_idx = rest[:cut], rest[cut:]
        model = train_fold(
            matrix, mask, n_values, fit_idx, inner_idx,
            latent_dim=latent_dim, epochs=args.epochs,
            batch_size=args.batch_size, lr=args.lr, patience=args.patience,
            seed=args.seed + f, device=device)
        with torch.no_grad():
            xb = torch.from_numpy(matrix[held]).to(device)
            pred, _ = model(xb)
            recon = pred.cpu().numpy()
        sq = (recon - matrix[held, :n_values]) ** 2 * mask[held]
        sq_all[held] = sq
        per_day[held] = sq.sum(axis=1) / np.maximum(mask[held].sum(axis=1), 1)
        print(f"  折 {f + 1}/{args.folds}: {dates[lo]}〜{dates[hi - 1]} "
              f"({len(held)} 日) 誤差の中央値 {np.median(per_day[held]):.4f}",
              flush=True)

    assert np.isfinite(per_day).all(), "採点されていない日がある"
    print(f"交差適合 {time.time() - started:.0f} 秒")

    order = per_day.argsort()
    rank = np.empty_like(order, dtype=np.float64)
    rank[order] = np.arange(n)
    score = rank / max(n - 1, 1) * 100.0

    # --- G-19: 期間で割って段差が消えたことを確かめる ------------------------
    split = meta["split"]
    groups = collections.defaultdict(list)
    for i, d in enumerate(dates):
        part = ("train" if d <= split["train"][1]
                else "valid" if d <= split["valid"][1] else "test")
        groups[part].append(score[i])
    med = {k: statistics.median(v) for k, v in groups.items()}
    held_out = groups["valid"] + groups["test"]
    gap = statistics.median(held_out) - med["train"]
    print(f"期間ごとの中央値: "
          + " / ".join(f"{k} {v:.1f}(n={len(groups[k])})" for k, v in med.items()))
    print(f"学習期間と held-out の差: {gap:+.1f} 点")
    if abs(gap) > 10.0:
        raise SystemExit(
            f"G-19 不通過: 学習期間と held-out の異常度の差が {gap:+.1f} 点。"
            f"異常度が『学習したかどうか』を測っている(HC-251)"
        )

    var_of = [c.split(":")[1] for c in columns]
    contributions: dict[str, dict[str, float]] = {}
    for i, d in enumerate(dates):
        by_var: dict[str, float] = collections.defaultdict(float)
        for j, var in enumerate(var_of):
            by_var[var] += float(sq_all[i, j])
        total = sum(by_var.values())
        if total <= 0:
            continue
        top = sorted(by_var.items(), key=lambda kv: -kv[1])[:5]
        contributions[d] = {VAR_LABEL.get(k, k): round(v / total * 100, 1)
                            for k, v in top}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "anomaly.json").write_text(json.dumps({
        "model_version": meta["version"],
        "method": f"時間ブロック {args.folds} 分割の交差適合。"
                  f"どの日もその日を含まないデータで学習したモデルで採点する",
        "note": "再構成誤差の百分位。確率でも災害リスクでもない",
        "period_medians": {k: round(v, 1) for k, v in med.items()},
        "train_holdout_gap": round(gap, 1),
        "scores": {d: round(float(score[i]), 1) for i, d in enumerate(dates)},
        "contributions": contributions,
        "coverage": {d: round(float(mask[i].mean()), 3) for i, d in enumerate(dates)},
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"-> {OUT / 'anomaly.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
