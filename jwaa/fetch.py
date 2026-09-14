"""外部データの取得(SPEC §2 / N-06)。

この層が守ること:

1. **キャッシュして再開できる。** 2 回目の実行は外部に要求を出さない(N-06)。
2. **間隔を置く。** 公開の閲覧画面を読むので、既定は 1 要求 1 秒。
3. **接続リセットを『データ無し』と解釈しない。** 環境展望台は散発的に接続を
   リセットする(実測 2026-09-08: 数回に 1 回)。再試行する。
4. **応答の中身を確かめてから保存する。** 気象庁は prec_no と block_no の対が
   不整合でも HTTP 200 と短いページを返す(実測 3,814 バイト)。
   状態コードだけを見る取得器はそれを正常として通す。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Final

USER_AGENT: Final = (
    "weather-atmosphere-atlas-ai/0.1 "
    "(research; +https://github.com/twill3c/weather-atmosphere-atlas-ai) "
    "Python-urllib"
)

DEFAULT_DELAY_S: Final = 1.0
DEFAULT_TRIES: Final = 6


class FetchError(RuntimeError):
    """取得に失敗した。呼び手は握りつぶさずに止めること。"""


@dataclass
class Fetcher:
    """キャッシュ付きの取得器。

    `validate` は保存前に本文を検査する述語。False を返した応答は
    **キャッシュに残さず** FetchError にする。壊れた応答をキャッシュすると、
    以後の実行がその壊れた中身を「取得済み」として読んでしまう。
    """

    cache_dir: pathlib.Path
    delay_s: float = DEFAULT_DELAY_S
    tries: int = DEFAULT_TRIES
    user_agent: str = USER_AGENT
    #: 再試行の待ち上限。連続取得を続けると接続を切ってくる相手があるので、
    #: 諦める前に十分待つ(実測 2026-09-09: 環境展望台は 8 回・約 90 秒では復帰しなかった)
    max_backoff_s: float = 300.0
    verbose: bool = False
    _last_request_at: float = 0.0
    requests_made: int = 0
    cache_hits: int = 0
    retries: int = 0

    def __post_init__(self) -> None:
        self.cache_dir = pathlib.Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- キャッシュ ---------------------------------------------------------

    def _path(self, key: str, suffix: str) -> pathlib.Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{digest}{suffix}"

    def _sleep(self) -> None:
        wait = self.delay_s - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    # -- 取得 ---------------------------------------------------------------

    def get(self, url: str, *, suffix: str = ".bin",
            validate: Callable[[bytes], bool] | None = None,
            headers: dict[str, str] | None = None) -> bytes:
        """GET。キャッシュがあればそれを返す。"""
        return self._fetch(url, None, suffix=suffix, validate=validate,
                           headers=headers)

    def post(self, url: str, data: dict[str, str], *, suffix: str = ".bin",
             validate: Callable[[bytes], bool] | None = None,
             headers: dict[str, str] | None = None) -> bytes:
        """POST。キャッシュ鍵は URL と本文の両方から作る。"""
        body = urllib.parse.urlencode(sorted(data.items())).encode()
        return self._fetch(url, body, suffix=suffix, validate=validate,
                           headers=headers)

    def _fetch(self, url: str, body: bytes | None, *, suffix: str,
               validate: Callable[[bytes], bool] | None,
               headers: dict[str, str] | None) -> bytes:
        key = url if body is None else f"{url}|{body.decode()}"
        path = self._path(key, suffix)
        if path.exists():
            self.cache_hits += 1
            return path.read_bytes()

        hdrs = {"User-Agent": self.user_agent}
        if body is not None:
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        if headers:
            hdrs.update(headers)

        last: Exception | None = None
        for attempt in range(self.tries):
            self._sleep()
            req = urllib.request.Request(url, data=body, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    payload = resp.read()
                self._last_request_at = time.monotonic()
                self.requests_made += 1
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                # 接続リセット・一時的な失敗。『データ無し』ではない。
                self._last_request_at = time.monotonic()
                last = exc
                self.retries += 1
                wait = min(2.0 ** attempt, self.max_backoff_s)
                if self.verbose:
                    print(f"    再試行 {attempt + 1}/{self.tries} "
                          f"({type(exc).__name__}) — {wait:.0f} 秒待つ", flush=True)
                time.sleep(wait)
                continue

            if validate is not None and not validate(payload):
                # 壊れた応答はキャッシュに残さない
                raise FetchError(
                    f"応答が検査に通らなかった({len(payload)} バイト): {url}"
                )
            path.write_bytes(payload)
            self._meta(path, url, len(payload))
            return payload

        raise FetchError(f"{self.tries} 回とも取得に失敗: {url} — {last!r}")

    def _meta(self, path: pathlib.Path, url: str, size: int) -> None:
        meta = path.with_suffix(path.suffix + ".meta.json")
        meta.write_text(json.dumps({
            "url": url,
            "bytes": size,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }, ensure_ascii=False), encoding="utf-8")

    # -- 記録 ---------------------------------------------------------------

    def summary(self) -> str:
        return (f"外部要求 {self.requests_made} 件 / "
                f"キャッシュ命中 {self.cache_hits} 件 / "
                f"再試行 {self.retries} 件")
