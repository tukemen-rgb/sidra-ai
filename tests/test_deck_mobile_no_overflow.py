"""C-1239: a generated deck wraps long tokens so it fits a phone screen.

The deck shell had no overflow-wrap, so a long source path did not break and the
content measured wider than a phone screen (482px vs 390px on an iPhone 12),
forcing a horizontal scroll. The shell now carries overflow-wrap:anywhere on
body, inherited by every bullet, source line and footer.
"""

from __future__ import annotations

import re

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_mobile_no_overflow import evaluate_deck_mobile_no_overflow


def _head_css(html: str) -> str:
    return re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)


def test_deck_mobile_no_overflow_eval_passes():
    result = evaluate_deck_mobile_no_overflow()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5


def test_deck_shell_wraps_long_tokens_always():
    html = generate_deck(
        "紹介スライドを作って",
        facts=[Fact("展開できる。", "tukemen-rgb/site@0eedf95:docs/a-very-long-path.md")],
    ).html
    css = _head_css(html)
    base = css.split("@media", 1)[0]
    m = re.search(r"body\{[^{}]*overflow-wrap\s*:\s*(anywhere|break-word)", base)
    assert m, "body has no always-on wrapping rule"
    # The long path is present, so the rule has something to break.
    assert "a-very-long-path.md" in html
