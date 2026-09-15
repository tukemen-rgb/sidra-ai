"""Does ``plain_text`` flatten a Markdown image the way it flattens a link?

C-1840, the image sibling of C-1227. ``plain_text`` turns 「[管理画面](url)」 into
「管理画面」 (link text kept, URL dropped) so a retrieved excerpt reads as prose in
every artifact it reaches - the answer body, the report .md, the deck HTML. But a
Markdown *image* 「![alt](url)」 was left to the link rule, which matched only the
「[alt](url)」 part and left the leading 「!」 behind: 「![logo](…)」 became 「!logo」.
Worse, an image with empty alt text 「![](url)」 - a decorative badge, the common
README shape - matched no rule at all and survived whole, leaking the raw
「![](https://…)」 and its URL into a forwarded document, the very thing C-1227
stops for links. ``plain_text`` now flattens an image to its alt text (empty for a
bare badge) before the link rule runs, and the link rule is unchanged.

Tested on ``plain_text`` directly - the single flattener every surface shares.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import plain_text

#: (input, expected). Images collapse to alt text (or nothing), leaving no 「!」,
#: no 「![」, and no URL. The last two are regression guards: a link still keeps
#: its text and drops its URL, and plain prose is untouched.
_CASES: tuple[tuple[str, str], ...] = (
    ("![logo](https://x/l.png)", "logo"),
    ("![CI passing](https://ci/badge.svg) 稼働中", "CI passing 稼働中"),
    ("![](https://x/img.png)後続", "後続"),
    ("詳細は![図](https://a/i.png)を参照", "詳細は図を参照"),
    ("詳細は[管理画面](https://a/d)を参照", "詳細は管理画面を参照"),
    ("通常のテキスト", "通常のテキスト"),
)


@dataclass(frozen=True)
class PlainTextImageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_plain_text_flattens_image() -> PlainTextImageResult:
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

    # No image input may leak a raw image marker or a URL into the output.
    for raw, _ in _CASES[:4]:
        got = plain_text(raw)
        add("![" not in got and "](http" not in got and "https://" not in got,
            f"plain_text({raw!r}) = {got!r} leaked image markup or a URL")

    total = len(_CASES) + 4
    return PlainTextImageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PlainTextImageResult", "evaluate_plain_text_flattens_image"]
