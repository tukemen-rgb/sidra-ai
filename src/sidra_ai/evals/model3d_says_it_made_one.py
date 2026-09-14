"""Does the 3D model say it is not the number of models that was asked for?

C-1832. One request builds one mesh and there is no count to set, so
「魚の3Dモデルを3つ作って」 built one, titled it 「魚3つ」 and said nothing at all:
the shape existed, so the shape-fallback note (C-1283) stayed silent too, and
that request carried no disclosure anywhere while its own title claimed three.

This generator already admits the shape it substituted and the colour it could
not apply (C-1818) - on the preview page and in the chat summary both. The
count was the one left out, the same asymmetry the deck had about its slides
(C-1821) and the GIF about its length (C-1823).

``count_note`` is the one source for both, and both are checked here: the page
is the artifact that gets forwarded and reopened, the summary is what the
person reads now.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.model3d_job import build_model3d_generator
from sidra_ai.creation.models3d import (
    count_note,
    generate_model3d,
    requested_count,
)
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "個数は指定できません"
_SHAPE_NOTE = "依頼に合う形状が無かった"
_COLOR_NOTE = "依頼にあった色は今の配色に反映していません"


@dataclass(frozen=True)
class Model3DCountResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _summary(request: str) -> str:
    generate = build_model3d_generator(scratch_dir("sidra-c1832-"))
    outcome = generate(request, detect_creation_intent(request))
    return getattr(outcome, "summary", "") or ""


def _page(request: str) -> str:
    return generate_model3d(request).preview_html


def evaluate_model3d_says_it_made_one() -> Model3DCountResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    three = "魚の3Dモデルを3つ作って"
    plain = "魚の3Dモデルを作って"
    one = "3Dモデルを1つ作って"
    ten_cubes = "立方体を10個の3Dモデルで作って"
    red_three = "赤い魚の3Dモデルを3つ作って"
    a_year = "2026年の3Dモデルを作って"

    # --- (A) the summary says the count is not the one asked for ----------
    add(_NOTE in _summary(three),
        "A: 「3つ」 is not told that one model was made")
    # --- (B) and so does the preview page, from the same source -----------
    #     The page is what gets forwarded; a title reading 「魚3つ」 over one
    #     fish is exactly the silent artifact C-1818 closed for colour.
    add(_NOTE in _page(three),
        "B: the preview page carries no count disclosure")
    # --- (C) a request with no count gets no note -------------------------
    add(_NOTE not in _summary(plain) and _NOTE not in _page(plain),
        "C: a bare 「魚の3Dモデルを作って」 reports a count it was never asked for")
    # --- (D) the count actually made is not a substitution ----------------
    add(_NOTE not in _summary(one) and _NOTE not in _page(one),
        "D: 「1つ」 - the number actually made - wrongly gets a note")
    # --- (E) additive with the shape-default note (C-1283) ----------------
    add(_NOTE in _page(ten_cubes) and _SHAPE_NOTE in _page(ten_cubes),
        "E: the count note replaced the shape-default disclosure")
    # --- (F) additive with the colour note (C-1818), both channels --------
    add(_NOTE in _page(red_three) and _COLOR_NOTE in _page(red_three)
        and _NOTE in _summary(red_three) and _COLOR_NOTE in _summary(red_three),
        "F: the count and colour notes do not coexist")
    # --- (G) a number that is not a count is not a request ----------------
    #     The unit word carries this: 「2026年」 has no digits in front of
    #     個/つ/体/匹/台/点, so it never matches.
    add(_NOTE not in _summary(a_year) and requested_count(a_year) is None,
        "G: a year was read as a count of models")
    # --- (H) the note reports the number it was given, not a constant -----
    add("2 体" in count_note("魚の3Dモデルを3つ作って", 2)
        and "3 つ" in count_note("魚の3Dモデルを3つ作って", 2),
        "H: the note does not name the number actually made")

    return Model3DCountResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "Model3DCountResult",
    "evaluate_model3d_says_it_made_one",
]
