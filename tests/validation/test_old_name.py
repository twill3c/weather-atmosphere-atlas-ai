"""T-042: 追跡ファイルに旧名を残さない(loop_003 で公開名 weather-atmosphere-atlas-ai に揃えた)。

旧名を含む行は、その行の中で「旧」と明示している場合だけ許す(SPEC §13 の経緯など)。
logs/ は取得・学習・ループの記録で、過去の事実なので書き換えない。
"""

from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

# 旧名そのものをこのファイルに書くと、このファイルが自分の検査に掛かる
OLD = "japan-" + "weather-atmosphere-atlas"
HISTORY_PREFIXES = ("logs/",)


def _offending(lines_by_path: dict[str, list[str]]) -> list[str]:
    hits = []
    for path, lines in lines_by_path.items():
        if path.startswith(HISTORY_PREFIXES):
            continue
        for no, line in enumerate(lines, 1):
            if OLD in line and "旧" not in line:
                hits.append(f"{path}:{no}: {line.strip()[:120]}")
    return hits


def _tracked_text() -> dict[str, list[str]]:
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    out: dict[str, list[str]] = {}
    for name in names.stdout.decode("utf-8").split("\0"):
        if not name:
            continue
        p = ROOT / name
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue  # バイナリ
        out[name] = data.decode("utf-8", errors="replace").splitlines()
    return out


def test_no_old_name_in_tracked_files():
    tracked = _tracked_text()
    assert "package.json" in tracked and "README.md" in tracked, "追跡ファイルが読めていない"
    hits = _offending(tracked)
    assert not hits, "旧名が残っている:\n" + "\n".join(hits)


def test_old_name_check_positive_controls():
    """T-042 の陽性対照: 旧名の行を拾い、『旧』と明示した行と logs/ は通す。"""
    sample = {
        "package.json": ['  "name": "' + OLD + '",'],
        "SPEC.md": ["旧名 `" + OLD + "` から改名した"],
        "logs/build.log": ["> " + OLD + "@0.1.0 build"],
        "README.md": ["cd weather-atmosphere-atlas-ai"],
    }
    hits = _offending(sample)
    assert len(hits) == 1 and hits[0].startswith("package.json:1:"), hits
