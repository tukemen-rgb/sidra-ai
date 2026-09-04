"""Does a cited Markdown link read as text, not bracketed URL syntax?

C-1227: the corpus cross-references its own files, so a generated document
carried 「[SPEC.md](../[REDACTED:high_entropy:31d60b69].md) — …」 - the link
brackets and URL leaked in, and because the URL tripped the output guard's
entropy check it showed an alarming 「[REDACTED:high_entropy:…]」 placeholder
in what is just a relative path. ``plain_text`` now keeps the link text and
drops the URL, including a link the excerpt window cut mid-URL, while a bare
「[1]」/「[S1]」 reference (no 「(」 after it) is left alone.

The checks run ``plain_text`` over links of each shape and confirm the text
survives, the brackets and URL are gone, and bracketed references are kept.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import plain_text


@dataclass(frozen=True)
class AnswerLinksFlattenedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_answer_links_flattened() -> AnswerLinksFlattenedResult:
    checks = 0
    failures: list[str] = []

    complete = plain_text("[SPEC.md](../SPEC.md) を参照。")
    if complete == "SPEC.md を参照。":
        checks += 1
    else:
        failures.append(f"complete link not flattened: {complete!r}")

    redacted = plain_text("[SPEC.md](../[REDACTED:high_entropy:31d60b69].md) — 現状")
    if "REDACTED" not in redacted and "](" not in redacted and "SPEC.md" in redacted:
        checks += 1
    else:
        failures.append(f"redacted URL survived: {redacted!r}")

    dangling = plain_text("参照: [docs/autonomous-loop.md](..")
    if dangling == "参照: docs/autonomous-loop.md":
        checks += 1
    else:
        failures.append(f"window-cut link not flattened: {dangling!r}")

    # No bracket+paren link syntax remains anywhere.
    mixed = plain_text("[a](x) と [b](y) の 2 つ")
    if "](" not in mixed and mixed == "a と b の 2 つ":
        checks += 1
    else:
        failures.append(f"multiple links not all flattened: {mixed!r}")

    # A bare bracketed reference is content here (citation label, backlog
    # marker) and must not lose its brackets.
    if plain_text("根拠は [1] にある") == "根拠は [1] にある":
        checks += 1
    else:
        failures.append("a bare [1] reference lost its brackets")
    if plain_text("出典 [S1] を参照") == "出典 [S1] を参照":
        checks += 1
    else:
        failures.append("a bare [S1] reference lost its brackets")

    return AnswerLinksFlattenedResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
