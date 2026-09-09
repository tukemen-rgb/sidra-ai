"""Do the flat generators keep both files when two save in the same second?

C-1509. The generators stamp artifact names to the second. Two artifacts of
one kind written inside one second reduce to the same name, and an
unconditional write silently overwrote the first - ``save_game`` guards this
with a serial suffix, but ``save_gif``/``save_art``/``save_document``/
``save_deck``/``save_model3d`` did not. Each now routes through
``unique_path``, so the second save becomes ``…-2`` instead of clobbering the
first.

Each check freezes the clock, saves two different subjects of one kind, and
asserts the two land on distinct paths with the first file's bytes intact.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


@dataclass(frozen=True)
class FlatArtifactCollisionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


_FIXED = datetime(2026, 9, 9, 2, 15, 30, tzinfo=timezone.utc)


def evaluate_flat_artifacts_survive_same_second_save() -> FlatArtifactCollisionResult:
    from sidra_ai.creation import art, decks, documents, gifs, models3d
    from sidra_ai.creation.art import generate_art, save_art
    from sidra_ai.creation.decks import generate_deck, save_deck
    from sidra_ai.creation.documents import generate_document, save_document
    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.gifs import generate_gif, save_gif
    from sidra_ai.creation.models3d import generate_model3d, save_model3d

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    facts = [Fact(text="事実A。", source="repo@aaaaaaa:docs/x.md")]

    def _run(kind: str, module, save_two) -> None:
        """save_two(dir) -> (path1, path2) with the clock frozen to one second."""
        tmp = Path(tempfile.mkdtemp(prefix=f"collide-{kind}-"))
        with mock.patch.object(module, "datetime") as m:
            m.now.return_value = _FIXED
            p1, p2 = save_two(tmp)
        original = p1.read_bytes()
        add(p1 != p2, f"{kind}: two same-second saves reused one path")
        add(p1.exists() and p1.read_bytes() == original and p2.exists(),
            f"{kind}: first artifact was overwritten (data loss)")

    _run("gif", gifs, lambda d: (
        save_gif(generate_gif("猫のGIFを作って"), d),
        save_gif(generate_gif("海のGIFを作って"), d),
    ))
    _run("art", art, lambda d: (
        save_art(generate_art("猫のアートを作って"), d),
        save_art(generate_art("海のアートを作って"), d),
    ))
    _run("document", documents, lambda d: (
        save_document(generate_document("犬のレポートを作って", facts=facts), d),
        save_document(generate_document("猫のレポートを作って", facts=facts), d),
    ))
    _run("deck", decks, lambda d: (
        save_deck(generate_deck("進捗のデッキを作って", facts=facts, outline="status"), d),
        save_deck(generate_deck("計画のデッキを作って", facts=facts, outline="status"), d),
    ))
    # model3d writes obj/mtl/preview under one stem; the .obj reserves it.
    _run("model3d", models3d, lambda d: (
        save_model3d(generate_model3d("猫の3Dモデルを作って"), d)["obj"],
        save_model3d(generate_model3d("海の3Dモデルを作って"), d)["obj"],
    ))

    total = 10
    return FlatArtifactCollisionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "FlatArtifactCollisionResult",
    "evaluate_flat_artifacts_survive_same_second_save",
]
