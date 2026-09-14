"""要約の「から」は、そのゲームが実際に居た段 (C-1744, §9 事実 2).

``games.py`` drops a recorded difficulty its template does not have and
reads the request instead. That is deliberate and stays - a bad sidecar
must not make an artifact unbuildable, and the docstring says so. The
consequence nobody had followed through is that **the recorded word and
the page can disagree**, so anything that *reports* on the page has to
ask the build's rule rather than read the file.

The revision summary read the file. With a sidecar saying
``"impossible"`` it printed 「難易度 impossible→hard」 about a game that
had never been on 「impossible」 - the built page was right, the sentence
about it was not.

Both sides now ask ``games.difficulty_in_force``.

Both directions: a broken record names the real rung, and a healthy one
says exactly what it said before. A summary that simply stopped naming
the 「from」 would pass the first check and tell the operator less.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sidra_ai.creation.games import (
    _DIFFICULTY,
    choose_difficulty,
    difficulty_in_force,
    generate_game,
    save_game,
)
from sidra_ai.creation.revise import (
    build_game_reviser,
    detect_revision_intent,
    save_meta,
)

TEMPLATE = "adventure"
REQUEST = "冒険ゲームを作って"
LINE = "冒険ゲームを難しくして"
#: What a sidecar can say: three real rungs, a word no template has, and
#: a missing value.
RECORDED = ("easy", "normal", "hard", "impossible", "")


def _revise(home: Path, recorded: str) -> tuple[str, str]:
    built = generate_game(REQUEST, template=TEMPLATE)
    page = save_game(built, str(home))
    save_meta(
        page,
        request=REQUEST,
        template=TEMPLATE,
        difficulty=recorded,
        theme="",
        title=built.title,
        panel={},
    )
    art = home / "artifacts"
    before = {p.name for p in art.glob("*.html")}
    out = build_game_reviser(str(home))(LINE, detect_revision_intent(LINE))
    fresh = [p for p in art.glob("*.html") if p.name not in before]
    # C-1817: a revision that changes nothing now writes no version, so
    # 「hard」 (already the top rung, nothing to step to) leaves none. The page
    # the summary describes is then the one already on disk. Still at most
    # one: a revision that wrote two files is a defect either way, and both
    # tests below already return without asserting when the summary names no
    # step, so nothing they actually check is relaxed by this.
    assert len(fresh) <= 1, [p.name for p in fresh]
    target = fresh[0] if fresh else page
    spec = re.search(
        r"const TUNE_SPEC=(\{.*?\});", target.read_text(encoding="utf-8"), re.S
    )
    built_rung = {f["key"]: f["default"] for f in json.loads(spec.group(1))["fields"]}
    return str(getattr(out, "summary", "") or out), built_rung["difficulty"]


def test_the_rule_is_the_builders_own() -> None:
    """...and what it falls back to is the request's own reading.

    Checked against ``choose_difficulty`` rather than only against the
    ladder, because both sides of this item ask the same function: a
    fallback quietly changed to a fixed rung would keep the summary and
    the page agreeing with each other and wrong about the request. The
    destruction battery walked through the version without this line.
    """

    assert difficulty_in_force(TEMPLATE, "hard", REQUEST) == "hard"
    for unusable in ("impossible", ""):
        got = difficulty_in_force(TEMPLATE, unusable, REQUEST)
        assert got in _DIFFICULTY[TEMPLATE], got
        assert got == choose_difficulty(REQUEST), (unusable, got)


@pytest.mark.parametrize("recorded", RECORDED)
def test_the_summary_names_the_rung_the_game_was_on(
    recorded: str, tmp_path: Path
) -> None:
    said, _ = _revise(tmp_path, recorded)
    want = difficulty_in_force(TEMPLATE, recorded, REQUEST)
    named = re.search(r"難易度 (\w+)→(\w+)", said)
    if named is None:
        # Only legitimate when there was no step to take.
        assert "変更なし" in said, said
        assert want == "hard", (recorded, want, said)
        return
    assert named.group(1) == want, (recorded, said)
    assert named.group(1) in _DIFFICULTY[TEMPLATE], said


@pytest.mark.parametrize("recorded", ("easy", "normal"))
def test_a_healthy_record_reads_exactly_as_before(
    recorded: str, tmp_path: Path
) -> None:
    """The half that stops "just do not mention it" from scoring."""

    said, built = _revise(tmp_path, recorded)
    step = {"easy": "normal", "normal": "hard"}[recorded]
    assert f"難易度 {recorded}→{step}" in said, said
    assert built == step


@pytest.mark.parametrize("recorded", ("impossible", ""))
def test_an_unusable_record_builds_what_the_request_asked_for(
    recorded: str, tmp_path: Path
) -> None:
    """The independent half: the request decides, not a fixed rung."""

    said, _built = _revise(tmp_path, recorded)
    named = re.search(r"難易度 (\w+)→(\w+)", said)
    assert named is not None, said
    assert named.group(1) == choose_difficulty(REQUEST), said


@pytest.mark.parametrize("recorded", RECORDED)
def test_the_page_that_was_built_is_the_page_the_summary_describes(
    recorded: str, tmp_path: Path
) -> None:
    """The pair this item is about: the sentence and the artifact.

    Measured rather than assumed - reading the *newest by name* is how I
    first mis-read this defect, because a revision writes ``…-2.html``
    which sorts before the original.
    """

    said, built = _revise(tmp_path, recorded)
    named = re.search(r"難易度 (\w+)→(\w+)", said)
    if named is None:
        return
    assert named.group(2) == built, (said, built)
