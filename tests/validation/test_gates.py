"""T-024 / T-025 — SPEC のゲート表そのものを検査する(HC-157)。

SPEC の品質ゲート表は宣言であって実装でも検査でもない。`G-xx` を書いた時点で
「守られている」と錯覚しやすく、その錯覚を壊す仕掛けが無い。テストは自分が書いた分しか
主張せず、書き忘れたゲートについては沈黙する。だから対応そのものを検査する。
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.validation

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "SPEC.md"
TEST_SPEC = ROOT / "TEST_SPEC.md"
TESTS = ROOT / "tests"


def _spec_gates() -> dict[str, str]:
    """SPEC §9 のゲート表から {G-xx: 判定欄} を取る。"""
    text = SPEC.read_text(encoding="utf-8")
    gates = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(G-\d+)\s*\|(.+)\|(.+)\|\s*$", line)
        if m:
            gates[m.group(1)] = m.group(3).strip()
    return gates


def test_t025a_spec_declares_gates():
    gates = _spec_gates()
    assert gates, "SPEC §9 のゲート表が読めない"
    assert len(gates) >= 10, f"ゲートが少なすぎる: {sorted(gates)}"


def test_t025_every_gate_is_referenced_or_declared_unimplemented():
    """T-025: 各 G-xx は、テストから参照されるか SPEC に「未実装」と書かれているか。

    どちらでもないゲートは、誰も守っていないのに守られて見える。
    """
    gates = _spec_gates()
    body = "\n".join(
        p.read_text(encoding="utf-8")
        for p in TESTS.rglob("test_*.py")
    )
    referenced = set(re.findall(r"G-\d+", body))

    orphans = []
    for gid, verdict in gates.items():
        if gid in referenced:
            continue
        if "未実装" in verdict:
            continue
        orphans.append((gid, verdict))
    assert orphans == [], (
        "テストからも参照されず、SPEC に『未実装』とも書かれていないゲート: "
        f"{orphans}"
    )


def test_t025b_unimplemented_gates_are_not_secretly_referenced():
    """逆向きの検査: 「未実装」と書いたゲートを、実は検査しているのに放置していないか。

    これは緩みではなく、SPEC の表が実態から遅れていることを捕まえる。
    """
    gates = _spec_gates()
    body = "\n".join(
        p.read_text(encoding="utf-8") for p in TESTS.rglob("test_*.py")
    )
    referenced = set(re.findall(r"G-\d+", body))
    stale = [g for g, v in gates.items() if "未実装" in v and g in referenced]
    assert stale == [], f"SPEC が『未実装』としているのにテストが参照している: {stale}"


def test_t025c_test_spec_case_table_covers_every_case_id():
    """TEST_SPEC のケース表の T-xxx が、実際のテストから参照されていること。"""
    spec_cases = set(re.findall(r"\|\s*(T-\d+)\s*\|", TEST_SPEC.read_text("utf-8")))
    assert spec_cases, "TEST_SPEC のケース表が読めない"
    body = "\n".join(p.read_text("utf-8") for p in TESTS.rglob("test_*.py"))
    referenced = set(re.findall(r"T-\d+", body))
    missing = sorted(spec_cases - referenced)
    assert missing == [], f"TEST_SPEC にあるがテストに無いケース: {missing}"


def test_t024_text_hygiene_finds_no_foreign_characters():
    """T-024 (G-15): 日本語本文・ソースに別字種・制御文字が混入していない。"""
    script = ROOT / "harness" / "text_hygiene.py"
    assert script.exists()
    r = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"text_hygiene が違反を報告した:\n{r.stdout}\n{r.stderr}"
