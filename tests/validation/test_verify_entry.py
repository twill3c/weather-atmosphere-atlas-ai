"""T-041: 検査の入口 `npm run verify` が、実在するテストまで届くこと。

loop_000 から loop_002 まで、verify の 2 段目は `vitest run` だったが、vitest のテストファイルは
1 本も無く、`No test files found` で exit 1 を返してチェーンが止まっていた。実際の検査は
pytest と smoke を個別に叩いていたので気づかなかった。README はこの入口を案内している。
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

TEST_FILE = re.compile(r"\.(test|spec)\.(ts|tsx|js|mjs|cjs|jsx)$")


def _leaves(scripts: dict[str, str], name: str, seen: frozenset[str] = frozenset()) -> list[str]:
    """`npm run X` を再帰的に展開し、末端のコマンドを並び順で返す。"""
    assert name in scripts, f"scripts に {name} が無い"
    assert name not in seen, f"scripts が循環している: {name}"
    out: list[str] = []
    for part in re.split(r"\s*&&\s*", scripts[name].strip()):
        m = re.fullmatch(r"npm run ([\w:.-]+)", part)
        if m:
            out.extend(_leaves(scripts, m.group(1), seen | {name}))
        else:
            out.append(part)
    return out


def _dead_steps(leaves: list[str], tracked: list[str]) -> list[str]:
    """走らせても対象が無く落ちる段を返す。"""
    has_js_tests = any(TEST_FILE.search(p) for p in tracked)
    return [c for c in leaves if "vitest" in c and "--passWithNoTests" not in c and not has_js_tests]


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, check=True)
    return out.stdout.decode("utf-8").splitlines()


def test_verify_chain_reaches_real_tests():
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    leaves = _leaves(scripts, "verify")
    assert not _dead_steps(leaves, _tracked()), f"対象の無いテスト段: {_dead_steps(leaves, _tracked())}"
    assert any("pytest" in c for c in leaves), f"verify に pytest が無い: {leaves}"
    assert any("smoke.mjs" in c for c in leaves), f"verify に実ブラウザ検品が無い: {leaves}"
    # ビルドは検品より前に要る
    build = next(i for i, c in enumerate(leaves) if c.startswith("next build"))
    smoke = next(i for i, c in enumerate(leaves) if "smoke.mjs" in c)
    assert build < smoke, leaves


def test_verify_chain_positive_controls():
    """T-041 の陽性対照: 以前の形(テストファイルの無い vitest)を拒み、展開が入れ子と循環を扱う。"""
    old = {"verify": "npm run typecheck && npm run test", "typecheck": "tsc --noEmit", "test": "vitest run"}
    assert _dead_steps(_leaves(old, "verify"), ["app/page.tsx", "tests/x/test_a.py"]) == ["vitest run"]
    assert _dead_steps(_leaves(old, "verify"), ["lib/a.test.ts"]) == []
    nested = {"verify": "npm run a && echo z", "a": "npm run b && echo y", "b": "echo x"}
    assert _leaves(nested, "verify") == ["echo x", "echo y", "echo z"]
    loop = {"verify": "npm run a", "a": "npm run verify"}
    try:
        _leaves(loop, "verify")
    except AssertionError as e:
        assert "循環" in str(e)
    else:
        raise AssertionError("循環を検出しなかった")
