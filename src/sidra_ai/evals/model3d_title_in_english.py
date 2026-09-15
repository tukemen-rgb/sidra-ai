"""Does an English request for a 3D model get a title a person could have written?

C-1839. ``models3d._STRIP`` is built entirely from optional groups, so it
matches the empty string at every position and its ``\\s*`` matches every space
on its own. Japanese has no spaces and looked right; English came back with
its spaces removed, and 「make a 3D model of a fish」 was titled ``makeaofafish``
- a string nobody wrote, carried into the ``<title>``, the ``<h1>``, the chat
summary and the record. The smallest reproduction has neither 3D nor model in
it: ``a fish`` became ``afish``.

Two things are held here. The substitution must drop only what actually
matched, and the English frame - the verb the sentence opens with, the article
after it, the ``of`` that says which half is the subject - has to come off, the
way games.py has done it since C-1516.

The Japanese path is driven in the same eval, because a fix that quietly moved
a Japanese title would be a worse trade than the bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.models3d import (
    _strip_kind_words,
    generate_model3d,
)
from sidra_ai.creation.vocabulary import drop_english_frame

#: Japanese titles that must come out of this byte-identical.
JAPANESE: dict[str, str] = {
    "魚の3Dモデルを作って": "魚",
    "船の3Dモデルを作って": "船",
    "地形の3Dモデルを作って": "地形",
    "魚の3Dモデルを3つ作って": "魚",
    "魚の3Dモデルを今すぐ作って": "魚",
}


@dataclass(frozen=True)
class Model3DEnglishTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_model3d_title_in_english() -> Model3DEnglishTitleResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) the subject, not the sentence --------------------------------
    add(generate_model3d("make a 3D model of a fish").title == "fish",
        f"A: titled {generate_model3d('make a 3D model of a fish').title!r}")
    # --- (B) and no title is the request with its spaces removed ----------
    #     The shape of the old failure, stated as a property: whatever the
    #     title is, it must not be the operator's words glued together.
    glued = [
        request
        for request in (
            "make a 3D model of a fish",
            "make 3 3D models of a fish",
            "make a 3d model of a boat please",
        )
        if generate_model3d(request).title == request.replace(" ", "")
    ]
    add(not glued, f"B: the title is the request with its spaces eaten: {glued}")
    # --- (C) the smallest reproduction ------------------------------------
    #     No 3D, no model, nothing to strip - and it used to lose its space.
    add(_strip_kind_words("a fish") == "a fish",
        f"C: an empty match still removes text: {_strip_kind_words('a fish')!r}")
    # --- (D) every Japanese title is unchanged ----------------------------
    moved = {
        request: generate_model3d(request).title
        for request, expected in JAPANESE.items()
        if generate_model3d(request).title != expected
    }
    add(not moved, f"D: a Japanese title moved: {moved}")
    # --- (E) the English tail marker comes off ----------------------------
    add(generate_model3d("make a 3d model of a boat please").title == "boat",
        "E: 「please」 is part of the title")
    # --- (F) an English request naming no subject takes the default -------
    add(generate_model3d("make a model").title == "魚",
        f"F: titled {generate_model3d('make a model').title!r} with no subject named")
    # --- (G) the count and adverb rules still hold ------------------------
    add(generate_model3d("make 3 3D models of a fish").title == "fish"
        and generate_model3d("魚の3Dモデルを3つ作って").title == "魚",
        "G: the count rule (C-1832/C-1833) changed behaviour")
    # --- (H) the English pass cannot reach a Japanese request -------------
    #     It runs unconditionally: measured across ten Japanese requests, it
    #     changes none of their titles, because every pattern needs an English
    #     word a Japanese sentence does not contain. The property is held here
    #     rather than by a guard, since a guard that decides nothing is dead
    #     code (the same measurement that deleted one in C-1821).
    #     C-1841 moved the three patterns into ``vocabulary`` so five
    #     generators share them; the property is the same and is now asked of
    #     the shared function rather than of this module's own copies.
    add(_strip_kind_words("魚の3Dモデルを作って").strip() == "魚"
        and drop_english_frame("魚の3Dモデル") == "魚の3Dモデル",
        "H: the English frame rule matched a Japanese request")

    return Model3DEnglishTitleResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "JAPANESE",
    "Model3DEnglishTitleResult",
    "evaluate_model3d_title_in_english",
]
