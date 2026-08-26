"""The deck generator as the router sees it.

Kept apart from :mod:`sidra_ai.creation.decks` so the builder stays a library
with no opinion about HTTP, artifacts directories or response shapes, and
this file holds the one thing the router needs: a callable that takes the
operator's message and returns a :class:`CreationOutcome`.

The summary it returns names how many sections are still blank. That number
is the honest headline of a generated deck - "4 slides, 2 for you to fill"
tells the owner what they got, where "デッキを作りました" alone would let
them present blanks they never saw.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.decks import Fact, generate_deck, save_deck, save_pptx, validate_deck
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_deck_generator(data_dir: str | Path, facts: list[Fact] | None = None):
    """Return a generator bound to where artifacts are written.

    ``facts`` here are *standing* evidence, fixed when the generator is built.
    The router also hands per-request evidence to every call, and the two are
    combined: a request's own retrieval is what usually fills the slides,
    while a caller that wants a deck always to carry some fixed fact can
    supply it once. Both empty is a supported configuration, not a degraded
    one - the deck renders entirely in blanks, which is the correct artifact
    when nothing was retrieved.
    """

    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        # Per-request evidence first: it is the evidence for *this* request,
        # and `_bullets_for` takes the earliest matches for a section.
        available = list(retrieved or []) + list(facts or [])
        deck = generate_deck(message, facts=available)

        # The generator checks its own output against the evidence it was
        # handed, before writing anything. A deck that failed this would be a
        # deck carrying a figure from somewhere other than the corpus, and
        # the one thing worse than not producing it is producing it and
        # saying it was grounded.
        verdict = validate_deck(deck, available)
        if not verdict["usable"]:
            return CreationOutcome(
                kind=intent.kind,
                handled=False,
                summary=(
                    "デッキを作りましたが、根拠と照合できない内容が含まれていたため"
                    "破棄しました: " + "; ".join(verdict["failures"])
                ),
                details={"failures": verdict["failures"], "facts_available": len(available)},
            )

        path = save_deck(deck, data_dir)
        pptx_path = path.with_suffix(".pptx")
        wrote_pptx, why = save_pptx(deck, pptx_path)

        blanks = len(deck.unfilled)
        summary = (
            f"「{deck.title}」を {len(deck.slides)} 枚で作りました。"
            + (
                f"根拠が見つからなかった {blanks} 枚は空欄のままです"
                f"（{'、'.join(deck.unfilled)}）。数字は推測で埋めません。"
                if blanks
                else "全ての欄に出典があります。"
            )
        )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "outline": deck.outline,
                "slides": len(deck.slides),
                "unfilled": list(deck.unfilled),
                # How much evidence reached the deck. An operator seeing
                # blanks needs to tell "nothing was retrieved" apart from
                # "plenty was retrieved and none of it fit a section".
                "facts_available": len(available),
                # True only because the check above ran and passed, not
                # because the code intends it to be true.
                "numbers_sourced": True,
                # Reported rather than assumed: on a machine without
                # python-pptx the HTML is the only artifact, and saying so
                # is the difference between a fact and a claim.
                "pptx_path": str(pptx_path) if wrote_pptx else "",
                "pptx_reason": why,
            },
        )

    return generate


__all__ = ["build_deck_generator"]
