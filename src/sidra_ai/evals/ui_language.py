"""Is the browser entry page written in the operator's language?

C-1207: the page declared ``<html lang="ja">`` and then spoke English -
intro, labels, button, statuses, error prefixes - with one Japanese
paragraph patched in. Rule 6 of the system prompt (born from the
2026-08-27 incident) keeps *answers* in the question's language; this eval
keeps the doorway consistent with it.

Checked on the rendered page string in both directions: the English
boilerplate must be gone, and the Japanese labels must actually be there -
deleting a label entirely should not count as translating it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: English strings that used to face the operator. Each one's absence is a
#: check; substrings are chosen to not match code (ids, attributes).
_ENGLISH = (
    "Ask a question",
    "API token",
    ">Question<",
    ">Ask<",
    "Generated files",
    ">Refresh<",
    '"Sources"',
    '"Refused"',
    '"Asking',
    '"Failed: "',
    "Listing failed",
    "Download failed",
    "(redacted)",
)

#: The Japanese that must stand in their place.
_JAPANESE = (
    "索引済みリポジトリについて質問できます",
    # The full label markup: 「質問」 alone also appears in the intro prose,
    # so a deleted label would otherwise still count as translated.
    '<label for="q">質問</label>',
    "アクセストークン",
    "送信",
    "生成ファイル",
    "更新",
    "出典",
    "問い合わせ中",
    "拒否されました",
    "失敗",
    "伏せ字",
)


@dataclass(frozen=True)
class UiLanguageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_language() -> UiLanguageResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    for english in _ENGLISH:
        if english not in ASK_PAGE:
            checks += 1
        else:
            failures.append(f"english remains: {english}")
    for japanese in _JAPANESE:
        if japanese in ASK_PAGE:
            checks += 1
        else:
            failures.append(f"japanese label missing: {japanese}")
    if 'lang="ja"' in ASK_PAGE:
        checks += 1
    else:
        failures.append("the page no longer declares lang=ja")

    total = len(_ENGLISH) + len(_JAPANESE) + 1
    return UiLanguageResult(
        passed=not failures, checks_passed=checks, checks_total=total,
        failures=tuple(failures),
    )
