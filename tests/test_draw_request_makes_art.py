"""A request for a picture must not be declined by a product that makes pictures.

C-1804. 「絵を描いて」 got 「この形式は作れません。いま作れるのは アート・…」 - the
refusal listed the thing the asker wanted - while 「アートを作って」 built the same
generative art. The gap was the word, not the capability: 「絵」 and 「イラスト」,
the ordinary Japanese for it, were missing from the ART cues.

C-1480 is the same defect from the other side, and its comment says why this one
went unnoticed: it added the English cues because the Japanese ones worked, so
「an English speaker was declined for what SIDRA can make」 - and took the
Japanese list for complete. C-1606 then routed 「絵を描いて」 to that decline
deliberately and called it honest. A request naming no subject is exactly what
the generator makes, so there was nothing there to be honest about.

Deliberately unchanged: a request that names a subject. The art is abstract -
「魚の絵」 cannot draw a fish - and that case carries its own disclosure already.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.intent import CreationKind, detect_creation_intent  # noqa: E402

DECLINED = "この形式は作れません"


def kind_of(message: str):
    intent = detect_creation_intent(message)
    return intent.kind if intent else None


@pytest.mark.parametrize(
    "message",
    ["絵を描いて", "絵を作って", "イラストを描いて", "イラストを作って", "青い絵を描いて"],
)
def test_a_picture_request_routes_to_the_picture_generator(message: str) -> None:
    assert kind_of(message) == CreationKind.ART, (
        f"「{message}」 does not reach ART - it is declined by a product that "
        "lists アート as something it makes"
    )


@pytest.mark.parametrize(
    "message, want",
    [
        ("魚の絵柄のGIFを作って", CreationKind.GIF),
        ("絵を描くゲームを作って", CreationKind.GAME),
        ("絵本のようなスライドを作って", CreationKind.DECK),
    ],
    ids=["gif", "game", "deck"],
)
def test_the_neighbours_keep_their_kinds(message: str, want) -> None:
    """The half without which a keyword that swallowed everything would pass.

    The latest-match rule decides these: 絵 sits earlier in each message than
    the cue that should win, so each one is a live check of that rule rather
    than of the keyword alone.
    """

    assert kind_of(message) == want


def test_a_question_containing_the_word_is_still_a_question() -> None:
    """UNKNOWN, not ART: a question is not a making request.

    The detector answers UNKNOWN rather than None here - it recognises the
    message and declines to call it a build - which is what the service reads
    to keep answering it as a question. Asserting None instead would pin a
    shape the detector does not use.
    """

    assert kind_of("絵文字について教えて") == CreationKind.UNKNOWN
    assert kind_of("浮世絵について教えて") == CreationKind.UNKNOWN


def _chat(message: str) -> str:
    """The real service, so these assertions do not go through the eval."""

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.evals.scratch import scratch_dir

    svc = SidraService(Settings(data_dir=str(Path(scratch_dir(prefix="draw-t-")) / "s")))
    return svc.chat(message).get("answer") or ""


def test_the_generator_still_says_what_it_did_not_honour() -> None:
    """Routing a colour request here must not trade one silence for another.

    The palette is fixed, so 「青い」 cannot be applied; C-1271/C-1272 gave that
    its note, and a new way in has to arrive with the note intact.

    Asserted against the service directly rather than through the eval's
    ``passed`` flag. Measured while writing this: weakening the eval's own
    colour check failed no test at all, because ``passed`` only reports what
    the eval chose to look at - the third of the proxies this session has
    caught out ("the tests pass" is not "the instrument is live").
    """

    assert "色は今の配色に反映していません" in _chat("青い絵を描いて")
    assert "色は今の配色に反映していません" not in _chat("絵を描いて")


def test_the_eval_counts_a_failure_into_its_denominator() -> None:
    """The denominator must grow with failures, not just with passes.

    ``checks_total == checks_passed + len(failures)`` is **vacuous while
    everything passes** - both sides are the same number - so it is driven
    here against a deliberately broken route. A hard-coded or pass-only
    denominator lets a failing check report a perfect score, which is the
    shape measured across all 157 evals on 2026-09-14.
    """

    import sidra_ai.creation.intent as intent_mod
    from sidra_ai.evals import draw_request_makes_art as mod

    healthy = mod.evaluate_draw_request_makes_art()
    assert healthy.passed and healthy.checks_total == healthy.checks_passed

    original = intent_mod._ARTIFACTS[CreationKind.ART]
    intent_mod._ARTIFACTS[CreationKind.ART] = tuple(
        w for w in original if w not in ("絵", "イラスト")
    )
    try:
        broken = mod.evaluate_draw_request_makes_art()
    finally:
        intent_mod._ARTIFACTS[CreationKind.ART] = original

    assert not broken.passed, "removing the cues did not fail the eval"
    assert broken.checks_passed < healthy.checks_passed
    assert broken.checks_total == healthy.checks_total, (
        "the denominator shrank with the failures - a partial run would "
        f"report a perfect score ({broken.checks_passed}/{broken.checks_total})"
    )
