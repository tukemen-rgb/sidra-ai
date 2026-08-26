"""The art pages must be seeded, self-contained, and honestly validated.

The promise under test is the caption each page prints on itself: same
request, same seed, same picture. So determinism is pinned, ``Math.random``
is banned by the validator (and the ban itself is tested against a page
that cheats), and the page follows the same rules the game pages proved
out - inline everything, fetch nothing, honour less motion.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.art import (
    BG,
    CYAN,
    MAGENTA,
    PATTERNS,
    GeneratedArt,
    choose_pattern,
    generate_art,
    save_art,
    validate_art,
)
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.creation.router import build_default_router


@pytest.mark.parametrize("pattern", PATTERNS)
def test_every_pattern_generates_a_valid_page(pattern: str) -> None:
    art = generate_art("アートを作って", pattern=pattern)
    verdict = validate_art(art)
    assert verdict["valid"], verdict["failures"]


def test_generation_is_deterministic_for_the_same_request() -> None:
    assert generate_art("アートを作って").html == generate_art("アートを作って").html


def test_different_requests_vary_the_seed_and_the_page() -> None:
    a = generate_art("アートを作って")
    b = generate_art("波のアートを作って")
    assert a.seed != b.seed
    assert a.html != b.html


def test_pattern_is_chosen_from_the_request() -> None:
    assert choose_pattern("流れのアート") == "flow"
    assert choose_pattern("惑星の軌道のアート") == "orbits"
    assert choose_pattern("なにかアートを") == "flow"


def test_the_page_stays_on_the_gameyard_palette() -> None:
    art = generate_art("アートを作って")
    assert BG in art.html and CYAN in art.html and MAGENTA in art.html


def test_the_page_is_self_contained_and_motion_aware() -> None:
    art = generate_art("アートを作って")
    assert "http://" not in art.html
    assert "https://" not in art.html
    assert "prefers-reduced-motion" in art.html


def test_the_page_never_draws_from_math_random() -> None:
    """The seed caption would be a lie on a page that draws differently

    each open, so the validator bans the unseeded source - and the ban has
    to actually fire, or it is decoration."""

    for pattern in PATTERNS:
        assert "Math.random" not in generate_art("x を作って", pattern=pattern).html

    honest = generate_art("アートを作って")
    cheat = GeneratedArt(
        title=honest.title,
        pattern=honest.pattern,
        seed=honest.seed,
        html=honest.html.replace("rng(SEED)", "Math.random.bind(Math)"),
    )
    verdict = validate_art(cheat)
    assert not verdict["valid"]
    assert any("Math.random" in failure for failure in verdict["failures"])


def test_an_unknown_pattern_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        generate_art("アートを作って", pattern="mystery")


def test_save_writes_a_name_the_listing_will_carry(tmp_path) -> None:
    from sidra_ai.api.artifacts import SAFE_NAME

    art = generate_art("波のアートを作って")
    path = save_art(art, tmp_path)

    assert path.exists()
    assert path.parent == tmp_path / "artifacts"
    assert SAFE_NAME.match(path.name)
    assert re.match(r"art-flow-\d{8}T\d{6}Z\.html$", path.name)


def test_intent_routes_art_requests_but_not_questions() -> None:
    assert detect_creation_intent("ジェネラティブアートを作って").kind is CreationKind.ART
    assert detect_creation_intent("壁紙を作って").kind is CreationKind.ART
    assert not detect_creation_intent("ジェネラティブアートとは").is_creation
    # Neighbours keep their ground.
    assert detect_creation_intent("釣りゲームを作って").kind is CreationKind.GAME
    assert detect_creation_intent("魚のGIFを作って").kind is CreationKind.GIF


def test_router_builds_art_end_to_end(tmp_path) -> None:
    router = build_default_router(data_dir=str(tmp_path))
    request = "軌道のアートを作って"
    outcome = router.route(request, detect_creation_intent(request))

    assert outcome.handled
    assert outcome.details["valid"] is True
    assert outcome.details["pattern"] == "orbits"
    assert outcome.artifact_path.endswith(".html")
