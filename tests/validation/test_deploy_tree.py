"""T-036..T-039 — 配る木の検査(SPEC N-01 / N-04、HC-062 / HC-148)。

公開のときに踏みやすい罠を、デプロイする前に機械で押さえる。

- **`.vercelignore` の無印パターンは深い階層にも当たる。** folksound-atlas は
  `data` と書いて `public/data` を消し、画面が空になった(memory vercel-deploy-quirks)。
  パターンは先頭 `/` で固定する。
- **ビルド刻印は画面のソースも測る。** データだけから作ると、フッタを直しても刻印が
  変わらず、古い本番に「一致」と返した(jinja-origin-atlas-ai)。
- **刻印は改行を揃えてから測る。** この機は core.autocrlf=true で、作業ツリーと
  配信側で改行が食い違う(mondo-atlas)。
- **git が作業途中の出力を追跡していた。** `.gitignore` が `*.parquet` しか見ておらず、
  実際の出力(JSONL / JSON)785 ファイル・637 MB に当たっていなかった(実測 2026-09-14)。
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.validation

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERCELIGNORE = ROOT / ".vercelignore"
STAMP_SCRIPT = ROOT / "scripts" / "build_stamp.mjs"

#: 配ってはならないもの(実測 2026-09-14 の大きさ)
MUST_EXCLUDE = [
    "data/cache/jma/0123456789abcdef.html",     # 1.8 GB・38,718 ファイル
    "data/processed/air/2014/12.json",          # 637 MB
    "data/models/autoencoder.pt",
    ".venv/Lib/site-packages/torch/__init__.py",  # 1.3 GB
    "node_modules/next/package.json",            # 461 MB
    ".next/cache/x.json",
    "out/index.html",
    "shots/_map_.png",
]
#: 配らなければ画面が壊れるもの
MUST_INCLUDE = [
    "public/data/manifest.json",
    "public/data/weather/2023-08.json",
    "public/data/air/pm25/2023-08.json",
    "public/data/ai/anomaly.json",
    "app/page.tsx",
    "app/map/MapExplorer.tsx",
    "components/JapanMap.tsx",
    "lib/data.ts",
    "package.json",
    "next.config.mjs",
    # prebuild が Vercel 上で走らせる。消すとビルドが落ちる(HC-062)
    "scripts/build_stamp.mjs",
]


def _git_ignored(patterns_file: pathlib.Path, paths: list[str], tmp_path) -> set[str]:
    """gitignore と同じ規則で、patterns_file に当たる経路を返す。

    実リポジトリの .gitignore が混ざらないよう、**空のリポジトリ**で測る
    (混ざると data/processed が .gitignore のほうで除外され、.vercelignore の
    漏れを隠す)。
    """
    repo = tmp_path / f"probe-repo-{len(list(tmp_path.glob('probe-repo-*')))}"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    # **標準入力はバイト列で渡す。** text=True だと Windows では \n が \r\n に
    # 変換され、最後の 1 本以外の経路が 'path\r' になって何にも当たらない。
    # 実際にそれで偽の赤(T-036c / T-039)と偽の緑(T-036d)が出た(2026-09-14)。
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", f"core.excludesFile={patterns_file}",
         "check-ignore", "--no-index", "--stdin"],
        input=("\n".join(paths) + "\n").encode("utf-8"), capture_output=True,
    )
    # 終了コード 1 は「どれも当たらなかった」。それ以外の非 0 は道具の故障。
    assert r.returncode in (0, 1), f"git check-ignore が落ちた: {r.stderr!r}"
    return {line.strip() for line in r.stdout.decode("utf-8").splitlines() if line.strip()}


# --- T-036: .vercelignore ---------------------------------------------------

def test_t036_vercelignore_exists():
    assert VERCELIGNORE.exists(), ".vercelignore が無い(初回デプロイの前に書く)"


def test_t036b_patterns_are_anchored():
    """T-036 (N-04): パターンは先頭 / で固定する。無印は深い階層にも当たる。"""
    bad = []
    for n, raw in enumerate(VERCELIGNORE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        # 拡張子だけのパターン(*.pyc 等)はどこに在っても除外したい意図なので許す
        if line.startswith("*."):
            continue
        if not line.startswith("/"):
            bad.append(f"{n}: {line}")
    assert bad == [], f"先頭 / で固定されていないパターン: {bad}"


def test_t036c_excludes_heavy_and_private_paths(tmp_path):
    ignored = _git_ignored(VERCELIGNORE, MUST_EXCLUDE + MUST_INCLUDE, tmp_path)
    leaked = [p for p in MUST_EXCLUDE if p not in ignored]
    assert leaked == [], f".vercelignore が除外していない: {leaked}"


def test_t036d_keeps_everything_the_screen_needs(tmp_path):
    """T-036 (HC-062): 画面が要るものを消していない。"""
    ignored = _git_ignored(VERCELIGNORE, MUST_EXCLUDE + MUST_INCLUDE, tmp_path)
    lost = [p for p in MUST_INCLUDE if p in ignored]
    assert lost == [], f".vercelignore が配るべきものまで消している: {lost}"


def test_t036e_positive_control_bare_data_pattern_eats_public_data(tmp_path):
    """陽性対照: 無印の `data/` は public/data に当たる(folksound-atlas で起きた罠)。

    これが当たらないなら、上の検査は罠を検出できない。
    """
    bad = tmp_path / "bad.vercelignore"
    bad.write_text("data/\n", encoding="utf-8")
    # **経路を複数渡し、最後でない経路が当たることを要求する。**
    # 1 本だけで書いていたときは、標準入力の改行が \r\n に化けて最後以外の経路が
    # 全部すり抜ける故障を、この対照が捕まえられなかった(2026-09-14)。
    probe = ["public/data/manifest.json", "public/data/ai/anomaly.json", "app/page.tsx"]
    ignored = _git_ignored(bad, probe, tmp_path)
    assert "public/data/manifest.json" in ignored, "陽性対照が発火していない(最初の経路)"
    assert "public/data/ai/anomaly.json" in ignored, "陽性対照が発火していない(中の経路)"
    assert "app/page.tsx" not in ignored, "無関係な経路まで当たっている"


# --- T-037: ビルド刻印 ------------------------------------------------------

def _node_stamp(root: pathlib.Path) -> dict:
    script = (
        "import { pathToFileURL } from 'node:url';"
        f"const m = await import(pathToFileURL({json.dumps(str(STAMP_SCRIPT))}).href);"
        f"console.log(JSON.stringify(m.computeStamp({json.dumps(str(root))})));"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", script],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"刻印の計算が落ちた: {r.stderr}"
    return json.loads(r.stdout)


def _mini_tree(base: pathlib.Path) -> pathlib.Path:
    files = {
        "app/page.tsx": "export default function P(){return null}\n",
        "components/X.tsx": "export const X = 1;\n",
        "lib/data.ts": "export const y = 2;\n",
        "app/globals.css": "body{margin:0}\n",
        "public/data/manifest.json": '{"date_min":"2014-01-01"}\n',
        "package.json": '{"name":"t"}\n',
        "next.config.mjs": "export default {};\n",
    }
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return base


def test_t037_stamp_script_exists():
    assert STAMP_SCRIPT.exists(), "scripts/build_stamp.mjs が無い"


def test_t037b_stamp_is_deterministic(tmp_path):
    root = _mini_tree(tmp_path / "a")
    assert _node_stamp(root)["stamp"] == _node_stamp(root)["stamp"]


def test_t037c_stamp_ignores_line_endings(tmp_path):
    """T-037 (HC-148): CRLF と LF で同じ刻印になる。"""
    lf = _mini_tree(tmp_path / "lf")
    crlf = tmp_path / "crlf"
    shutil.copytree(lf, crlf)
    for p in crlf.rglob("*"):
        if p.is_file():
            p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    # 前提の固定: 本当にバイト列が違うこと(HC-079)
    assert (lf / "app/page.tsx").read_bytes() != (crlf / "app/page.tsx").read_bytes()
    assert _node_stamp(lf)["stamp"] == _node_stamp(crlf)["stamp"]


@pytest.mark.parametrize("rel", ["app/page.tsx", "components/X.tsx", "lib/data.ts",
                                 "app/globals.css", "public/data/manifest.json"])
def test_t037d_stamp_changes_when_screen_source_or_data_changes(tmp_path, rel):
    """陽性対照: 画面のソースやデータを変えると刻印が変わる。

    データだけを測る刻印は、フッタを直しても変わらなかった(jinja-origin-atlas-ai)。
    """
    a = _mini_tree(tmp_path / "a")
    before = _node_stamp(a)["stamp"]
    p = a / rel
    p.write_bytes(p.read_bytes() + b"/* changed */\n" if not rel.endswith(".json")
                  else b'{"date_min":"2015-01-01"}\n')
    assert _node_stamp(a)["stamp"] != before, f"{rel} を変えても刻印が変わらない"


def test_t037e_stamp_ignores_files_that_are_not_shipped(tmp_path):
    """配らないもの(キャッシュ・テスト)を足しても刻印は変わらない。"""
    a = _mini_tree(tmp_path / "a")
    before = _node_stamp(a)["stamp"]
    for rel in ("data/cache/x.html", "tests/test_x.py", "logs/build.log"):
        p = a / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("noise", encoding="utf-8")
    assert _node_stamp(a)["stamp"] == before


def test_t037f_real_tree_stamp_covers_every_screen_area():
    """実際の木で、刻印の材料に app / components / lib / public/data がすべて入っている。"""
    files = [f["path"] for f in _node_stamp(ROOT)["files"]]
    for prefix in ("app/", "components/", "lib/", "public/data/"):
        assert any(f.startswith(prefix) for f in files), f"刻印が {prefix} を測っていない"
    assert not any(f.startswith(("data/", "tests/", "out/", ".next/")) for f in files)


# --- T-038: 画面が読む経路の境界 ---------------------------------------------

_FORBIDDEN_PATH = re.compile(r"""["'`][^"'`]*\b(data/(cache|processed|models|raw)|tests/)""")


def test_t038_screen_code_reads_only_public_data():
    """T-038 (N-01): 画面のコードは配られない経路を読まない。"""
    hits = []
    for base in ("app", "components", "lib"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix not in {".ts", ".tsx", ".mjs", ".js"}:
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if _FORBIDDEN_PATH.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert hits == [], f"配られない経路を読んでいる: {hits}"


def test_t038b_positive_control_pattern_catches_a_forbidden_read():
    assert _FORBIDDEN_PATH.search('readFileSync("data/processed/ghg_monthly.json")')
    assert not _FORBIDDEN_PATH.search('path.join(process.cwd(), "public", "data")')


# --- T-039: git が作業途中の出力を追わない -------------------------------------

def test_t039_gitignore_rule_excludes_intermediate_outputs(tmp_path):
    ignored = _git_ignored(ROOT / ".gitignore", [
        "data/processed/air/2014/12.json",
        "data/processed/weather/47401.jsonl",
        "data/processed/features.npz",
        "data/models/model_metadata.json",
    ], tmp_path)
    missing = [p for p in ("data/processed/air/2014/12.json",
                           "data/processed/weather/47401.jsonl",
                           "data/processed/features.npz") if p not in ignored]
    assert missing == [], f".gitignore が作業途中の出力に当たっていない: {missing}"


def test_t039b_intermediate_outputs_are_not_tracked():
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "data/processed"],
                       capture_output=True, text=True, check=True)
    tracked = [x for x in r.stdout.splitlines() if x.strip()]
    assert tracked == [], f"data/processed がまだ追跡されている({len(tracked)} ファイル)"


def test_t039c_footer_points_to_the_real_app_menu_and_repository():
    """フッタの宛先が本物であること(公開の直前に書いたまま忘れやすい)。

    app-menu.vercel.app は他者の別サービス。本番は app-menu-amber.vercel.app。
    """
    layout = (ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "app-menu-amber.vercel.app" in layout
    assert "https://app-menu.vercel.app" not in layout
    # 公開名は app-menu の登録簿の id に合わせる(先例: jinja-origin-atlas-ai / fishing-port-atlas-ai)。
    # ローカルのディレクトリ名 japan-weather-atmosphere-atlas とは違う。
    assert "github.com/twill3c/weather-atmosphere-atlas-ai" in layout
    assert "github.com/twill3c/japan-weather-atmosphere-atlas" not in layout
