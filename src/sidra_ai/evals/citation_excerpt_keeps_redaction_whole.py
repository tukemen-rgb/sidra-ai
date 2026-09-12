"""Does a cited excerpt avoid cutting a [REDACTED:...] placeholder in half?

C-1703. ``citation_excerpt`` caps an excerpt at ``MAX_CITATION_EXCERPT_CHARS``.
When that cut lands inside a redaction placeholder (``[REDACTED:github_token:...]``
or ``[REDACTED:pii_email]``), it left a meaningless ``[REDACT`` fragment. That was
invisible until C-1689/1691 put the excerpt in front of users in the web UI and
CLI; now a reader checking evidence sees ``token=[REDACT…`` and may read the
fragment as document text. No secret leaks (the placeholder already replaced it),
but the excerpt now drops a placeholder whole rather than splitting it.

The checks drive the real ``citation_excerpt``: a boundary-straddling placeholder
is not left as a broken fragment, the prose before it survives, a placeholder that
fits whole is untouched, plain text truncates as before, and the cap still holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _excerpt(content: str, query: str = "") -> str:
    from sidra_ai.api.citations import citation_excerpt
    from sidra_ai.security.output_guard import OutputGuard

    text, _withheld = citation_excerpt(content, OutputGuard(), query)
    return text


def _has_broken_placeholder(text: str) -> bool:
    """A placeholder cut at the end shows as a partial ``[REDACT`` fragment.

    The cut can fall anywhere in ``[REDACTED:label:fp]``, so the tail may be a
    proper prefix of the marker (``[``, ``[REDACT``) or an opened marker with no
    closing ``]`` (``[REDACTED:gi``). Ignore a trailing ``…`` truncation mark.
    """

    body = text[:-1] if text.endswith("…") else text
    i = body.rfind("[")
    if i == -1:
        return False
    tail = body[i:]
    marker = "[REDACTED"
    return marker.startswith(tail) or (tail.startswith(marker) and "]" not in tail)


@dataclass(frozen=True)
class RedactionWholeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_citation_excerpt_keeps_redaction_whole() -> RedactionWholeResult:
    from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS as CAP

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A secret-class placeholder straddling the cap boundary.
    straddle = "あ" * 185 + " token=[REDACTED:github_token:abc12345] の設定です。"
    ex = _excerpt(straddle)

    # --- (A) no broken [REDACT fragment is left at the cut ---
    add(not _has_broken_placeholder(ex),
        f"A: a split [REDACTED placeholder was shown: {ex[-40:]!r}")

    # --- (B) the prose before the placeholder survives ---
    add("あ" * 20 in ex, "B: the prose before the placeholder was lost")

    # --- (C) a whole placeholder inside a truncated window is kept intact
    #         (the trim must not fire on a placeholder that closes) ---
    whole = "[REDACTED:github_token:abc12345] は設定済みです。" + "た" * 250
    ex_whole = _excerpt(whole)
    add("[REDACTED:github_token:abc12345]" in ex_whole,
        f"C: a whole placeholder in a truncated window was dropped: {ex_whole[:40]!r}")

    # --- (D) plain text with no placeholder truncates as before ---
    plain = "本社の定休日は毎週月曜日です。" + "た" * 250
    ex_plain = _excerpt(plain)
    add(len(ex_plain) <= CAP and ex_plain.startswith("本社の定休日は毎週月曜日です。")
        and ex_plain.endswith("…"),
        f"D: plain truncation regressed: {ex_plain[:30]!r}..{ex_plain[-8:]!r}")

    # --- (E) the cap still holds ---
    add(len(ex) <= CAP, f"E: the excerpt exceeded the cap ({len(ex)} > {CAP})")

    # --- (F) a PII placeholder straddling the boundary is also dropped whole ---
    pii = "あ" * 190 + " 連絡先は [REDACTED:pii_email] まで。"
    ex_pii = _excerpt(pii)
    add(not _has_broken_placeholder(ex_pii),
        f"F: a split PII placeholder was shown: {ex_pii[-40:]!r}")

    total = 6
    return RedactionWholeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RedactionWholeResult", "evaluate_citation_excerpt_keeps_redaction_whole"]
