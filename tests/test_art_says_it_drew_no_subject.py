"""Art that depicts nothing must say so when a subject was asked for.

C-1806. 「猫の絵を描いて」 built a flow field on a page titled 「猫」, and nothing -
not the summary, not the page - said no cat was drawn. The title is the
promise, and the page is the half that gets forwarded (C-1793).

Two things met here. The subject note never existed: ``art_job`` had decided
"Not a claim the subject can't be drawn", which was written when this request
was declined rather than built. And C-1804 - the same loop, the cycle before -
widened the ART cues so that it is built, without updating
``_TITLE_KIND_SUFFIX`` with them, so 「猫の絵」 kept its 絵 where 「猫の壁紙」
correctly became 「猫」. That was C-1604's defect made a second time, one cue
set later, and the comment above the pattern says "Strip the whole cue set".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.art import _title_from, generate_art, subject_of  # noqa: E402

NOTE = "題材は描いていません"


def notes_of(request: str) -> str:
    html = generate_art(request).html
    return " ".join(re.findall(r'<p class="note">(.*?)</p>', html, re.S))


@pytest.mark.parametrize(
    "request_text, want",
    [
        ("猫の絵を描いて", "猫"),
        ("猫のイラストを描いて", "猫"),
        ("猫の壁紙を作って", "猫"),
        ("海の生成アートを作って", "海"),
    ],
)
def test_every_art_cue_is_stripped_from_the_title(request_text: str, want: str) -> None:
    """C-1604's rule, re-applied to the cues C-1804 added.

    The four spellings must agree: whichever word the asker used for "a
    picture", the title keeps only what they asked to be depicted.
    """

    assert _title_from(request_text) == want


@pytest.mark.parametrize("request_text", ["猫の絵を描いて", "車のイラストを描いて", "猫の壁紙を作って"])
def test_a_named_subject_is_disclosed_on_the_page(request_text: str) -> None:
    assert NOTE in notes_of(request_text)


@pytest.mark.parametrize("request_text", ["絵を描いて", "アートを作って", "イラストを描いて"])
def test_a_request_naming_no_subject_is_not_apologised_to(request_text: str) -> None:
    """The half that stops this being satisfied by apologising every time.

    A caveat that fires on every request is one nobody reads - measured on
    the colour-vision caveat, where 118 empty warnings would have buried it.
    """

    assert NOTE not in notes_of(request_text)


@pytest.mark.parametrize(
    "request_text, reason",
    [("青い絵を描いて", "a colour has its own note since C-1271"),
     ("波の絵を描いて", "波 names the flow pattern"),
     ("円のアートを作って", "円 names the orbits pattern")],
)
def test_what_is_not_a_subject(request_text: str, reason: str) -> None:
    assert subject_of(request_text) == "", reason
    assert NOTE not in notes_of(request_text)


def test_the_colour_note_still_fires_on_its_own() -> None:
    """Excluding colour from "subject" must not switch the colour note off."""

    assert "色は今の配色に反映していません" in notes_of("青い絵を描いて")


def test_the_eval_counts_a_failure_into_its_denominator() -> None:
    """Driven against a broken route: the equality is vacuous while all pass."""

    import sidra_ai.creation.art as art_mod
    from sidra_ai.evals import art_says_it_drew_no_subject as mod

    healthy = mod.evaluate_art_says_it_drew_no_subject()
    assert healthy.passed and healthy.checks_total == healthy.checks_passed

    original = art_mod.subject_of
    art_mod.subject_of = lambda _request: ""       # never disclose
    try:
        broken = mod.evaluate_art_says_it_drew_no_subject()
    finally:
        art_mod.subject_of = original

    assert not broken.passed, "silencing the note did not fail the eval"
    assert broken.checks_passed < healthy.checks_passed
    assert broken.checks_total == healthy.checks_total, (
        "the denominator shrank with the failures, so a partial run would "
        f"report a perfect score ({broken.checks_passed}/{broken.checks_total})"
    )
