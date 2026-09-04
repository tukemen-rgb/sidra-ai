"""Does a generated deck wrap long tokens so it fits a phone screen?

C-1239: the deck shell had no overflow-wrap/word-break, so a long source path
(「出典: tukemen-rgb/site@sha:docs/… / …」) or a file-path token in a bullet did
not wrap - on an iPhone 12 the content measured 482px against a 390px screen,
forcing a horizontal scroll or a zoomed-out page. The ask page solved the same
thing with overflow-wrap:anywhere; the deck shell now carries it too.

Layout cannot be computed offline, so the checks pin the wrapping rule on the
shell CSS - present, breaking, always-on (not media-gated), and reaching the
slide text; the iPhone-emulation proof (scrollWidth <= clientWidth) runs at fix
time and is recorded in the loop log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WRAP_VALUES = ("anywhere", "break-word", "break-all")


@dataclass(frozen=True)
class DeckMobileNoOverflowResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _head_css(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    return m.group(1) if m else ""


def evaluate_deck_mobile_no_overflow() -> DeckMobileNoOverflowResult:
    from sidra_ai.creation.decks import generate_deck
    from sidra_ai.creation.evidence import Fact

    # A fact whose source is a long, unbreakable path - the token that overflows.
    facts = [
        Fact(
            "検査エンジンは 3 種類の圧縮を展開できる。",
            "tukemen-rgb/site@0eedf95:docs/research/case-studies-and-a-very-long-name.md",
        ),
    ]
    html = generate_deck("検査エンジンの紹介スライドを作って", facts=facts).html
    css = _head_css(html)

    checks = 0
    failures: list[str] = []

    # 1: a wrapping declaration exists in the shell CSS.
    wrap = re.search(r"(overflow-wrap|word-break)\s*:\s*([a-z-]+)", css)
    if wrap:
        checks += 1
    else:
        failures.append("no overflow-wrap/word-break in the deck shell")

    # 2: its value actually breaks long tokens.
    if wrap and wrap.group(2) in _WRAP_VALUES:
        checks += 1
    else:
        failures.append("the wrapping value does not break long tokens")

    # 3: it is not gated behind a media query - overflow must never happen.
    before_media = css.split("@media", 1)[0]
    if re.search(r"(overflow-wrap|word-break)\s*:\s*(anywhere|break-word|break-all)", before_media):
        checks += 1
    else:
        failures.append("the wrapping rule is only inside a media query")

    # 4: it reaches the slide text - either on body/main (inherited) or on a
    #    selector covering the bullets and the source line.
    rule = re.search(
        r"(?P<sel>[^{}]+)\{[^{}]*(?:overflow-wrap|word-break)\s*:\s*(?:anywhere|break-word|break-all)[^{}]*\}",
        before_media,
    )
    sel = rule.group("sel") if rule else ""
    covers = ("body" in sel or "main" in sel or "*" in sel
              or ("li" in sel and "src" in sel))
    if covers:
        checks += 1
    else:
        failures.append(f"the wrapping rule does not reach the slide text (selector: {sel.strip()[:40]})")

    # 5: the long source path is actually present in the artifact (so the rule
    #    has something to act on - the fix is not just cosmetic CSS).
    if "case-studies-and-a-very-long-name.md" in html:
        checks += 1
    else:
        failures.append("the long source path did not reach the deck")

    return DeckMobileNoOverflowResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )
