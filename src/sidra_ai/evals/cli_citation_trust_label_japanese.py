"""Does the CLI render a citation's trust level in Japanese, not a raw enum?

C-1469. ``sidra-ask`` speaks Japanese everywhere a terminal user reads it - the
refusal guidance (C-1238), the connection errors (C-1233/1243/1278), and the
citation marks 「一部秘匿」「抜粋を秘匿」. But the trust level beside those marks
was appended verbatim: a citation grounded in an issue or PR body - EXTERNAL by
ingestion (normalize.py: third parties can write them) - rendered as
「(external)」, and an UNVERIFIED one as 「(unverified)」. The trust mark is the
safety signal a reader most wants (「this source could be written by anyone」),
and leaving it an English enum beside the Japanese redaction marks is the same
leak the CLI already closed elsewhere.

The level is now shown with a Japanese label; ``internal_repo`` is still
suppressed, the redaction marks are unchanged, and an unknown future value
falls back to its raw form rather than being dropped. ``--json`` is untouched.

The checks capture the real ``render`` output and read the 「引用:」 line.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _render(payload) -> str:
    from sidra_ai.api import ask_cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ask_cli.render(payload)
    return buf.getvalue()


def _payload(citation) -> dict:
    return {
        "refused": False,
        "answer": "索引済みリポジトリの DATA から回答します。",
        "citations": [citation],
        "model": {"backend": "echo"},
    }


def _cite_line(rendered: str) -> str:
    # The [S1] line inside the 「引用:」 block (not any [S#] in the answer body).
    seen_header = False
    for line in rendered.splitlines():
        if line.startswith("引用:"):
            seen_header = True
            continue
        if seen_header and line.strip().startswith("[S1]"):
            return line
    return ""


@dataclass(frozen=True)
class CliTrustLabelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_citation_trust_label_japanese() -> CliTrustLabelResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    base = {"label": "S1", "citation": "tukemen-rgb/site@a:issues/42"}

    # Each non-internal level shows its Japanese label and never the raw enum.
    for level, jp in (("external", "外部"), ("unverified", "未検証"),
                      ("operator", "運用者"), ("system", "システム")):
        line = _cite_line(_render(_payload({**base, "trust_level": level})))
        add(jp in line and level not in line,
            f"{level!r} not shown as {jp!r}: {line!r}")

    # internal_repo carries no trust mark (unchanged).
    internal = _cite_line(_render(_payload({**base, "trust_level": "internal_repo"})))
    add("(" not in internal,
        f"internal_repo grew a trust mark: {internal!r}")

    # The redaction marks are unchanged and coexist with the trust label.
    both = _cite_line(_render(_payload({**base, "trust_level": "external", "redacted": True})))
    add("一部秘匿" in both and "外部" in both,
        f"redaction mark and trust label do not coexist: {both!r}")
    withheld = _cite_line(_render(_payload({**base, "trust_level": "unverified", "excerpt_withheld": True})))
    add("抜粋を秘匿" in withheld and "未検証" in withheld,
        f"withheld mark and trust label do not coexist: {withheld!r}")

    # An unknown future level is not dropped: it falls back to its raw form.
    unknown = _cite_line(_render(_payload({**base, "trust_level": "someday"})))
    add("someday" in unknown,
        f"unknown trust level was dropped: {unknown!r}")

    total = 4 + 1 + 2 + 1
    return CliTrustLabelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliTrustLabelResult", "evaluate_cli_citation_trust_label_japanese"]
