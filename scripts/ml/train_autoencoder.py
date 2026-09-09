"""Autoencoder を学習する(SPEC §8 / 構想書 §24 / §25)。

守ること:
  * **時系列で分ける。** ランダム分割は使わない(隣り合う日が漏れる)。
  * **欠測を損失から除く。** マスクで重みを掛け、マスクの和で割る。
  * seed を固定し、metadata に刻む(再現性 — 構想書 §65)。

    python scripts/ml/train_autoencoder.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
MODELS = PROCESSED.parent / "models"


class AtmosphericAutoencoder(nn.Module):
    """構想書 §24 の構成。入力全体を受け、値の部分だけを再構成する。"""

    def __init__(self, input_dim: int, output_dim: int, latent_dim: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 512), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 256), nn.ReLU(),
            nn.Linear(256, 512), nn.ReLU(),
            nn.Linear(512, output_dim),
        )

    def forward(self, x):
        z = self.encoder(x)
        return self.decoder(z), z


def masked_mse(pred, target, mask):
    """欠測を除いた平均二乗誤差(構想書 §25.2)。"""
    denom = mask.sum()
    if denom == 0:
        return (pred * 0).sum()
    return ((pred - target) ** 2 * mask).sum() / denom


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", default=str(PROCESSED / "features.npz"))
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--latent-dim", type=int, default=128)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--valid-start", default="2021-01-01")
    ap.add_argument("--test-start", default="2023-01-01")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    data = np.load(args.features, allow_pickle=True)
    matrix = data["matrix"].astype(np.float32)
    dates = [str(d) for d in data["dates"]]
    columns = [str(c) for c in data["columns"]]
    mask = data["mask"].astype(np.float32)
    n_values = len(columns)

    # 時系列で分ける。日付は昇順なので境界で切るだけでよい。
    dates_arr = np.array(dates)
    is_valid = (dates_arr >= args.valid_start) & (dates_arr < args.test_start)
    is_test = dates_arr >= args.test_start
    is_train = ~(is_valid | is_test)
    for name, sel in (("train", is_train), ("valid", is_valid), ("test", is_test)):
        if sel.sum() == 0:
            raise SystemExit(f"{name} が空。分割の境界を見直す")
    # 重ならないこと・順に並ぶことを固定する(G-11)。
    # 日付は文字列なので numpy の max/min ではなく Python の組み込みで比べる。
    def span(sel):
        picked = [d for d, s in zip(dates, sel) if s]
        return min(picked), max(picked)

    assert not (is_train & is_valid).any() and not (is_valid & is_test).any()
    assert not (is_train & is_test).any()
    tr, va, te = span(is_train), span(is_valid), span(is_test)
    assert tr[1] < va[0], f"学習の末尾 {tr[1]} が検証の先頭 {va[0]} より後"
    assert va[1] < te[0], f"検証の末尾 {va[1]} が試験の先頭 {te[0]} より後"
    print(f"学習 {is_train.sum():,}({tr[0]}〜{tr[1]}) / "
          f"検証 {is_valid.sum():,}({va[0]}〜{va[1]}) / "
          f"試験 {is_test.sum():,}({te[0]}〜{te[1]})")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    X = torch.from_numpy(matrix).to(device)
    Y = torch.from_numpy(matrix[:, :n_values]).to(device)
    M = torch.from_numpy(mask).to(device)

    model = AtmosphericAutoencoder(matrix.shape[1], n_values, args.latent_dim).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    idx_train = np.flatnonzero(is_train)
    best = float("inf")
    best_state = None
    since = 0
    started = time.time()
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        perm = np.random.permutation(idx_train)
        total = 0.0
        for k in range(0, len(perm), args.batch_size):
            batch = torch.from_numpy(perm[k:k + args.batch_size]).to(device)
            pred, _ = model(X[batch])
            loss = masked_mse(pred, Y[batch], M[batch])
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.detach().item() * len(batch)
        train_loss = total / len(perm)

        model.eval()
        with torch.no_grad():
            sel = torch.from_numpy(np.flatnonzero(is_valid)).to(device)
            pred, _ = model(X[sel])
            valid_loss = float(masked_mse(pred, Y[sel], M[sel]))
        history.append({"epoch": epoch, "train": train_loss, "valid": valid_loss})
        if epoch % 10 == 0 or epoch == 1:
            print(f"  epoch {epoch:>3}: 学習 {train_loss:.5f} / 検証 {valid_loss:.5f}")

        if valid_loss < best - 1e-6:
            best, since = valid_loss, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            since += 1
            if since >= args.patience:
                print(f"  早期打ち切り(epoch {epoch}、検証が {args.patience} 回改善せず)")
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        losses = {}
        for name, sel in (("train", is_train), ("valid", is_valid), ("test", is_test)):
            ii = torch.from_numpy(np.flatnonzero(sel)).to(device)
            pred, _ = model(X[ii])
            losses[name] = float(masked_mse(pred, Y[ii], M[ii]))
    print(f"最終: {losses}  ({time.time() - started:.0f} 秒)")

    MODELS.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODELS / "autoencoder.pt")
    meta = {
        "model": "AtmosphericAutoencoder",
        "version": "1.0.0",
        "input_dim": int(matrix.shape[1]),
        "output_dim": int(n_values),
        "latent_dim": args.latent_dim,
        "seed": args.seed,
        "epochs_run": len(history),
        "split": {"train": list(tr), "valid": list(va), "test": list(te)},
        "losses": losses,
        "history": history,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    (MODELS / "model_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {MODELS / 'autoencoder.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
