"""Does the ask page say what to do when a listed file is already gone?

C-1228: clicking 開く on a generated file that was removed or renamed between
the list and the click returns 404, and the catch showed 「ダウンロードに失敗:
HTTP 404」 - a bare code. C-1211's guidance map covered 401/403/413/422/429/
5xx but not 404, the status most likely on the download/list path. ``explain``
now maps 404 to 「見つかりません。一覧を更新してください（…）」, with the code
still printed and the response body still unread.

Layout and the live fetch cannot be computed offline, so the checks pin the
mechanics on the page source; the end-to-end proof (a real 404 fetch, the
served page carrying the guidance) ran at fix time and is in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UiMissingArtifactGuidanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_missing_artifact_guidance() -> UiMissingArtifactGuidanceResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    # A 404 branch exists in explain().
    if re.search(r"status\s*===\s*404", ASK_PAGE):
        checks += 1
    else:
        failures.append("explain() has no 404 branch")

    # Its guidance names the next step (refresh the list).
    if "見つかりません" in ASK_PAGE and "一覧を更新" in ASK_PAGE:
        checks += 1
    else:
        failures.append("the 404 guidance does not tell the operator to refresh the list")

    # The 404 branch sits before the bare-code fallthrough, so it is reached.
    m404 = ASK_PAGE.find("status === 404")
    fallthrough = ASK_PAGE.find('return why ?')
    if 0 <= m404 < fallthrough:
        checks += 1
    else:
        failures.append("the 404 branch is after the bare-code fallthrough")

    # The status code is still printed for debugging.
    if "（HTTP " in ASK_PAGE:
        checks += 1
    else:
        failures.append("the status code is no longer printed for debugging")

    # The pre-existing classes still have guidance (no regression).
    for needle in ("アクセストークンを確認してください", "サーバ側で問題が起きました"):
        if needle in ASK_PAGE:
            checks += 1
        else:
            failures.append(f"a pre-existing guidance class was lost: {needle}")

    return UiMissingArtifactGuidanceResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
