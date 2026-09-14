"""Is the art page's default-pattern note framed like the chat summary?

C-1800. When a request names no pattern, both the chat summary and the on-page
note disclose that the flow default was used (C-1271/C-1284). But the summary
says 「依頼にパターン名が無かったので…」 while the page note said 「依頼「{題}」に
合うパターン名が無かった」 - bracket-quoting the request as a pattern that could
not be found. For a bare 「アートを作って」 the quoted 「アート」 is the medium
itself, so the forwarded artifact told the reader they had asked for a pattern
named 「アート」 that was missing, while the chat (not forwarded) framed it
honestly. The page note now uses the same subjectless framing as the summary; a
named pattern still gets no note.

The checks read the real ``generate_art`` HTML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.art import generate_art

_NOTE_MARK = '<p class="note">'


@dataclass(frozen=True)
class ArtNoteFramingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _notes(request: str) -> str:
    html = generate_art(request).html
    return " ".join(re.findall(r'<p class="note">(.*?)</p>', html, re.DOTALL))


def evaluate_art_note_matches_summary_framing() -> ArtNoteFramingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    bare = _notes("アートを作って")
    subject = _notes("猫のアートを作って")
    named_html = generate_art("軌道のアートを作って").html

    # --- (A) a bare request still discloses the default ------------------
    add(bare and "既定の「フロー」" in bare,
        "A: a bare art request no longer discloses the flow default on the page")
    # --- (B) the note lists the patterns you can pick -------------------
    add("フロー" in bare and "軌道" in bare,
        "B: the note does not list both selectable patterns")
    # --- (C) a bare request's note does not bracket-quote the request ---
    add("依頼「" not in bare,
        "C: the bare-request note bracket-quotes the medium as a failed pattern")
    # --- (D) a subject request's note does not bracket-quote it either --
    add("依頼「" not in subject,
        "D: the subject note bracket-quotes the request as a failed pattern")
    # --- (E) a subject request still discloses the default --------------
    add(subject and "既定の「フロー」" in subject,
        "E: a subject art request no longer discloses the flow default")
    # --- (F) a named pattern carries no note (no false positive) --------
    add(_NOTE_MARK not in named_html,
        "F: a named-pattern page wrongly carries a default-pattern note")

    total = 6
    return ArtNoteFramingResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtNoteFramingResult",
    "evaluate_art_note_matches_summary_framing",
]
