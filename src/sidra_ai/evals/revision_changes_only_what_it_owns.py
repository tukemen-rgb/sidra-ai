"""Does a revision leave alone the things it was not asked about?

§9 事実 2 records the market's three standing complaints about AI game
generators. Two of them - being charged for failed generations, and not
being able to take your output anywhere - cannot happen here by
construction: inference is local and the artifact is plain HTML. The
third, 「意図理解の低さと修正の副作用」, has no structural defence. A
reviser that repaints the palette while renaming the game is doing
exactly what the forums complain about, and nothing about running
locally prevents it.

It has happened here. C-1779 found that `detect_revision_intent` scanned
for accent words across the whole message, so a title containing a colour
word - 「赤い彗星」 - silently repainted the accent. That was fixed, and
`revision_rename_does_not_bleed_into_accent` holds that one pair.

There are eight axes a sentence can turn, so there are 56 ordered pairs
of "turn this, do not turn that", and until now one of them was guarded.
`creation_revision_axes` covers the other direction for all eight - each
sentence does move what it names - which is why the gap is easy to miss:
the axes look thoroughly measured, and they are, in one direction only.

This asks the second direction for every axis: revise, then read the
rebuilt page's own `TUNE_SPEC` and require that nothing outside the
sentence's ownership moved. One of the cases is C-1779's own sentence,
because a plain rename does not reproduce that bug - the new title has to
carry a colour word for the accent scan to find one. Restoring the old
whole-message scan left the eight ordinary cases green; only 「赤い彗星」
turns it red.

Ownership is written down rather than inferred, because one axis really
does own more than its name. 「難しくして」 moves `band` and `speed` too -
the difficulty ladder sets them together, and `creation_revision_axes`
says so itself (「速さは難易度ラダーが持つので別軸にしない」). A judge that
called that a leak would be reporting the design as a defect.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir

#: One sentence per axis, matching `creation_revision_axes` so the two
#: directions are asked of the same words.
AXIS_CASES: tuple[tuple[str, str], ...] = (
    ("difficulty", "さっきのゲームを難しくして"),
    ("band", "さっきのゲームの敵を減らして"),
    ("band_up", "さっきのゲームの敵を増やして"),
    ("accent", "さっきのゲームを赤にして"),
    ("daily", "さっきのゲームを日替わりにして"),
    ("brief", "さっきのゲームのブリーフィングを毎回出して"),
    ("theme", "さっきのゲームを紙のテーマにして"),
    ("title", "さっきのゲームのタイトルを「海」にして"),
    # C-1779's own sentence. A plain rename cannot reproduce that bug -
    # the title has to CARRY a colour word for the accent scan to catch
    # it - so the ordinary rename above is not a test of the leak this
    # judge exists to hold. Re-introducing the bug left the other eight
    # cases green, which is how this case came to be written.
    ("title_colour", "さっきのゲームのタイトルを「赤い彗星」にして"),
)

#: Which panel fields each sentence is allowed to move, and why when the
#: answer is more than one. Anything outside this is a side effect.
AXIS_OWNS: dict[str, frozenset[str]] = {
    "difficulty": frozenset({"difficulty", "band", "speed"}),
    "band": frozenset({"band"}),
    "band_up": frozenset({"band"}),
    "accent": frozenset({"accent"}),
    "daily": frozenset({"daily"}),
    "brief": frozenset({"brief"}),
    "theme": frozenset({"accent", "theme"}),
    "title": frozenset(),
    "title_colour": frozenset(),
}

#: The one axis that owns more than its own name, and the reason, kept
#: next to the table so widening it is a decision someone has to write.
WIDE_OWNERSHIP: dict[str, str] = {
    "difficulty": (
        "難易度ラダーが速さと敵の数を一緒に決めるため"
        "（`creation_revision_axes` の「速さは難易度ラダーが持つので別軸にしない」）"
    ),
    "theme": "テーマは配色一式なので差し色を連れて動く",
}


@dataclass(frozen=True)
class RevisionOwnershipResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    clean: tuple[str, ...] = ()


def _panel(path: str | Path) -> dict | None:
    """The schema the rebuilt page actually embeds.

    Read from the page rather than from the reviser's report: a panel
    value that never reached the artifact is not a fact about the product
    (the lesson C-1119 left, and the reason `creation_revision_axes`
    drives the page for `daily` and `brief`).
    """

    text = Path(path).read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", text, re.S)
    if script is None:
        return None
    spec = re.search(r"const TUNE_SPEC=(\{.*?\});", script.group(1), re.S)
    if spec is None:
        return None
    return {f["key"]: f["default"] for f in json.loads(spec.group(1))["fields"]}


def evaluate_revision_changes_only_what_it_owns() -> RevisionOwnershipResult:
    from sidra_ai.creation.games import generate_game, save_game
    from sidra_ai.creation.revise import (
        build_game_reviser,
        detect_revision_intent,
        save_meta,
    )

    failures: list[str] = []
    clean: list[str] = []
    checks = 0

    for axis, sentence in AXIS_CASES:
        home = scratch_dir("sidra-revision-owns-")
        built = generate_game("冒険ゲームを作って", template="adventure")
        page = save_game(built, home)
        save_meta(
            page,
            request="冒険ゲームを作って",
            template="adventure",
            difficulty=built.difficulty,
            theme="",
            title=built.title,
            panel={},
        )
        before = _panel(page)
        intent = detect_revision_intent(sentence)
        if not intent.is_revision:
            failures.append(f"{axis}: 「{sentence}」 was not read as a revision")
            continue
        outcome = build_game_reviser(home)(sentence, intent)
        if not outcome.artifact_path:
            failures.append(f"{axis}: the revision produced no page")
            continue
        after = _panel(outcome.artifact_path)
        if before is None or after is None:
            failures.append(f"{axis}: the page carries no panel schema")
            continue

        moved = {key for key in before if before[key] != after.get(key)}
        strayed = moved - AXIS_OWNS[axis]
        if strayed:
            failures.append(
                f"{axis}: 「{sentence}」 also moved "
                + "・".join(
                    f"{key} {before[key]}→{after.get(key)}" for key in sorted(strayed)
                )
            )
            continue
        checks += 1
        clean.append(f"{axis}({'・'.join(sorted(moved)) or '盤面のみ'})")

    # The two tables must name the same axes. Without this, the cheapest
    # way to a clean sheet is to stop driving a sentence - the loop would
    # simply score one case fewer and still report `passed` (C-1887 and
    # C-1891 were both written under this rule).
    _cased = {axis for axis, _ in AXIS_CASES}
    for axis in sorted(_cased ^ set(AXIS_OWNS)):
        failures.append(
            f"{axis}: named in "
            + ("AXIS_CASES but not AXIS_OWNS" if axis in _cased else "AXIS_OWNS but not AXIS_CASES")
        )
    if not _cased ^ set(AXIS_OWNS):
        checks += 1

    # The table may not quietly widen. Every axis that owns more than its
    # own name has to carry a written reason, so "just add it to OWNS" is
    # not a way to make a leak disappear.
    for axis, owns in sorted(AXIS_OWNS.items()):
        # Both band sentences own the one field named `band`; every other
        # axis is named after the field it turns.
        its_own = "band" if axis == "band_up" else axis
        extra = owns - {its_own}
        if not extra or axis in WIDE_OWNERSHIP:
            checks += 1
        else:
            failures.append(
                f"{axis} claims {sorted(extra)} without a reason in WIDE_OWNERSHIP"
            )

    return RevisionOwnershipResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        clean=tuple(clean),
    )
