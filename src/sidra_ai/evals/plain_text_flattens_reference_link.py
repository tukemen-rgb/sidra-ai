"""Does ``plain_text`` flatten a Markdown reference link and drop its URL def?

C-1863, a sibling of C-1227 (inline link URL dropped), C-1840 (image) and
C-1860 (HTML comment). A *reference* link has two halves:

* the inline use 「[仕様書][spec]」, which the inline-link rule (which needs
  「(url)」) never matched, so the reader saw the raw 「[…][…]」 brackets; and
* the definition line 「[spec]: https://example.com/spec」, which is invisible in
  rendered Markdown (it only tells the renderer where 「[spec]」 points) yet its
  URL surfaced verbatim in a flattened excerpt - the very URL leak C-1227 closes
  for inline links.

``plain_text`` now flattens 「[text][label]」 to its text and drops a definition
line, and the drop is deliberately scoped to a real link target (a 「http(s)://」
or 「mailto:」 destination) so a prose line that merely looks like 「[INFO]:
started the server」 is never removed.

Tested on ``plain_text`` directly - the single flattener every surface shares.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import plain_text

#: The first four are reference-link cases (brackets gone, URL gone); the last
#: five are regression guards - a prose line that resembles a definition is kept,
#: an inline link still flattens (C-1227), a bare 「[1]」 shortcut ref is left
#: alone, and plain prose is untouched.
_CASES: tuple[tuple[str, str], ...] = (
    ("詳しくは [仕様書][spec] を見よ。\n\n[spec]: https://example.com/spec", "詳しくは 仕様書 を見よ。"),
    ("See [the doc][1] and [guide][2].\n[1]: https://a.example/x\n[2]: https://b.example/y", "See the doc and guide."),
    ("collapsed [ref][] link", "collapsed ref link"),
    ("連絡は [メール][m]。\n[m]: mailto:admin@example.com", "連絡は メール。"),
    ("[INFO]: started the server successfully", "[INFO]: started the server successfully"),
    ("[注記]: 重要な話がある", "[注記]: 重要な話がある"),
    ("詳細は[管理画面](https://a/d)を参照", "詳細は管理画面を参照"),
    ("参照 [1] を見よ", "参照 [1] を見よ"),
    ("通常のテキスト", "通常のテキスト"),
)

#: Number of leading reference-link cases (for the leak guards).
_REF_CASES = 4

#: Destination text that must never survive from a dropped definition line.
_MUST_NOT_LEAK: tuple[str, ...] = (
    "https://", "mailto:", "example.com/spec", "a.example", "admin@example.com",
)


@dataclass(frozen=True)
class PlainTextReferenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_plain_text_flattens_reference_link() -> PlainTextReferenceResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for raw, expected in _CASES:
        got = plain_text(raw)
        add(got == expected, f"plain_text({raw!r}) = {got!r} != {expected!r}")

    # A reference-link case may leak neither the 「][」 bracket join nor any URL.
    for raw, _ in _CASES[:_REF_CASES]:
        got = plain_text(raw)
        add("][" not in got, f"plain_text({raw!r}) = {got!r} leaked a reference bracket")
    joined = " ".join(plain_text(raw) for raw, _ in _CASES[:_REF_CASES])
    for token in _MUST_NOT_LEAK:
        add(token not in joined, f"reference definition target leaked: {token!r}")

    total = len(_CASES) + _REF_CASES + len(_MUST_NOT_LEAK)
    return PlainTextReferenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PlainTextReferenceResult", "evaluate_plain_text_flattens_reference_link"]
