"""Is a GIF request that names the pulse heard as naming it?

C-1850. The GIF generator draws two motifs. Only one of them - the fish - had
words in ``_MOTIF_WORDS``; the pulse, which is both the default and half the
catalogue, had none. So 「パルスのGIFを作って」 matched nothing, fell through to
the default, and came out as concentric rings: the right picture, announced
with 「依頼に合う絵柄が無かったので、既定の「パルス（同心円）」にしました。いま
絵柄を指定できるのは「魚」です」. The person named the motif, got the motif, and
was told they had named none and pointed at a different one.

The two sibling generators already hold the contract this breaks: ``art`` gives
both of its patterns words and assembles the choice list from
``PATTERN_LABELS``; ``models3d`` gives all three shapes words. The gif's
sentence wrote 「魚」 as a literal, which is why the list could not follow the
catalogue when it grew - the same stale-copy shape as C-1848.

Both directions matter, and the boundary more than the rule:

* naming the pulse must be heard (six phrasings a person actually reaches for);
* naming nothing must still be told so - 「猫」 gets the default and the note;
* 「波」 and 「山脈」 name subjects this generator does not draw, so they keep
  the honest note rather than being read as the pattern;
* 「魚」 still draws the fish, including when the pulse is named alongside it.

The note is read out of ``MOTIF_LABELS`` rather than compared against a list
written here twice: a literal in the eval would pass a product that had gone
stale in exactly the way this item is about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.creation.gifs import (
    DEFAULT_MOTIF,
    MOTIF_LABELS,
    choose_motif,
    named_motif,
)
from sidra_ai.evals.scratch import scratch_dir

#: Ways a person names the concentric-ring motif. Its own label, what it
#: draws, and the English the detail line shows.
PULSE_REQUESTS: tuple[str, ...] = (
    "パルスのGIFを作って",
    "同心円のGIFを作って",
    "脈打つGIFを作って",
    "波紋のGIFを作って",
    "pulse gif を作って",
    "rippleのGIFを作って",
)

#: Requests that name no motif at all. 「波」 and 「山脈」 are the near misses:
#: a wave and a mountain range are subjects, not patterns, and reading either
#: as the pulse would claim the subject was drawn.
NO_MOTIF_REQUESTS: tuple[str, ...] = (
    "猫のGIFを作って",
    "星空のGIFを作って",
    "波のGIFを作って",
    "山脈のGIFを作って",
)

_NOT_NAMED = "依頼に合う絵柄が無かった"
_OFFER_HEAD = "いま絵柄を指定できるのは"


@dataclass(frozen=True)
class GifMotifNamedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    """The sentence a person reads, from the router's own gif generator."""

    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=scratch_dir(prefix="gif-motif-"))
    return router.route(request, detect_creation_intent(request), []).summary


def _motif_of(request: str) -> str:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=scratch_dir(prefix="gif-motif-"))
    out = router.route(request, detect_creation_intent(request), [])
    return str(out.details.get("motif") or "")


def evaluate_gif_motif_named_is_heard() -> GifMotifNamedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) every motif in the catalogue can be asked for by name --------
    #     Read from MOTIF_LABELS, so a motif added without words fails here
    #     rather than waiting for someone to notice the sentence.
    from sidra_ai.creation.gifs import _MOTIF_WORDS

    wordless = [key for key in MOTIF_LABELS if not _MOTIF_WORDS.get(key)]
    add(not wordless, f"A: motifs with no words of their own: {wordless}")

    # --- (B) the six phrasings are heard as the pulse ---------------------
    misheard = {r: named_motif(r) for r in PULSE_REQUESTS if named_motif(r) != "pulse"}
    add(not misheard, f"B: naming the pulse was not heard: {misheard}")

    # --- (C) and the answer drops the 「you named none」 sentence ----------
    #     The picture was always right; this is the half that was a lie.
    still_lying = [r for r in PULSE_REQUESTS if _NOT_NAMED in _summary(r)]
    add(not still_lying, f"C: told it named nothing: {still_lying}")

    # --- (D) naming nothing is still said so ------------------------------
    quiet = [r for r in NO_MOTIF_REQUESTS if _NOT_NAMED not in _summary(r)]
    add(not quiet, f"D: the default was used without saying so: {quiet}")

    # --- (E) and those requests still get the default picture -------------
    wrong = {r: choose_motif(r) for r in NO_MOTIF_REQUESTS
             if choose_motif(r) != DEFAULT_MOTIF}
    add(not wrong, f"E: a subject word changed the drawing: {wrong}")

    # --- (F) the fish keeps its own requests ------------------------------
    add(_motif_of("魚のGIFを作って") == "fish", "F: 「魚」 stopped drawing the fish")
    # --- (G) including when both are named: first match wins, unchanged ---
    add(_motif_of("魚が泳ぐ水槽のパルスGIFを作って") == "fish",
        "G: naming both changed which motif wins")

    # --- (H) the note lists every motif, built from the table -------------
    #     The OFFER, not the whole note. Written as 「every label appears in
    #     the summary」 this passed with the literal 「魚」 put back, because
    #     the sentence before it already names the default motif - a check
    #     the sabotage walked through. Only the span between 「指定できるのは」
    #     and its 「です」 is the list of what a person may ask for.
    note = _summary("猫のGIFを作って")
    head = note.partition(_OFFER_HEAD)[2]
    offer = head.partition("です")[0] if _OFFER_HEAD in note else ""
    add(bool(offer), "H: the note never says what can be asked for")
    absent = [label for label in MOTIF_LABELS.values() if label not in offer]
    add(not absent, f"H: the offer {offer.strip()!r} does not include: {absent}")

    # --- (I) and the file it wrote is a real GIF --------------------------
    #     A sentence check that never opened the artifact would pass a
    #     generator that had stopped writing one.
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=scratch_dir(prefix="gif-motif-"))
    made = router.route(
        "同心円のGIFを作って",
        detect_creation_intent("同心円のGIFを作って"),
        [],
    )
    head = Path(made.artifact_path).read_bytes()[:6] if made.artifact_path else b""
    add(head in (b"GIF87a", b"GIF89a"), f"I: the pulse request wrote {head!r}")

    return GifMotifNamedResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
