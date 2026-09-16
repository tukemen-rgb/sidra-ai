"""Does the revision answer call a panel row what the panel calls it?

C-1880. The page's tuning panel has a row labelled 「毎回ブリーフィングを見る」.
The revision vocabulary called the same field 「ブリーフィング」, and the two are
not the same promise: the first is about *every* visit, the second sounds like
an on/off for the screen. It is not an on/off - the page shows the briefing on
a first visit whatever the flag says (``startscreen.py``: skipping needs
``gateSeen()`` as well), and ``tuning.py`` says so in its own comment.

Measured on the real service before the fix, straight after making a game:

    「さっきのゲームのブリーフィングをオフにして」
      -> 「変更なし（すでにその設定です）」

The flag was already False, so nothing changed - and the briefing will appear
again on the next first visit. Somebody who has just read the briefing and
asked to turn it off is told it is already off, and it is not.

Two halves, and the second is the one that matters: the name, and the claim.
Renaming the row while still telling a person their briefing is off would fix
nothing they can see.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO = "tukemen-rgb/sidra-ai"


@dataclass(frozen=True)
class PanelFieldNameResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _panel_label(key: str) -> str | None:
    """What the page's own panel calls this row, read from the live schema."""

    from sidra_ai.creation.games import _DIFFICULTY
    from sidra_ai.creation.tuning import panel_schema

    schema = panel_schema(
        "racing", _DIFFICULTY["racing"], difficulty="normal", accent="#ff0000"
    )
    for field in schema.get("fields", ()):
        if field.get("key") == key:
            return field.get("label")
    return None


def _service(home: str):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    store.add(
        Document(
            content="第 1 章。収益化の方針について。" + "掲載順は売らない。" * 8,
            provenance=Provenance(
                source="github",
                repository=_REPO,
                path="docs/p0.md",
                commit_sha="0" * 40,
                timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                source_type=SourceType.DOCS,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            ),
        )
    )
    settings = Settings(
        data_dir=home, model_backend="echo", allowed_repositories=(_REPO,)
    )
    return SidraService(
        settings,
        store=store,
        gate=gate,
        state_store=StateStore(Path(home) / "state.json"),
    )


def _play(turns: list[str]) -> list[str]:
    """Run the turns on one page; return each answer."""

    with tempfile.TemporaryDirectory() as home:
        service = _service(home)
        history: list[tuple[str, str]] = []
        answers: list[str] = []
        for message in turns:
            out = service.chat(message, history=list(history))
            answer = (out.get("answer") or "").replace("\n", " ")
            history.append((message, answer))
            answers.append(answer)
        return answers


def evaluate_revision_calls_the_panel_field_what_the_panel_calls_it() -> PanelFieldNameResult:
    from sidra_ai.creation.revise import CHANGEABLE

    failures: list[str] = []
    passed = 0
    label = _panel_label("brief")

    # A: the two vocabularies agree, read from the live panel schema rather
    # than from a copy of the string.
    if not label:
        failures.append("the panel schema has no brief row to compare against")
    elif dict(CHANGEABLE).get("brief") != label:
        failures.append(
            f"the revision vocabulary says 「{dict(CHANGEABLE).get('brief')}」 "
            f"where the panel says 「{label}」"
        )
    else:
        passed += 1

    # B: and the confirmation a person reads uses it.
    _make, turned_on = _play(
        ["レースゲームを作って", "さっきのゲームのブリーフィングをオンにして"]
    )
    if label and label not in turned_on:
        failures.append(f"the confirmation does not use 「{label}」: {turned_on[:80]}")
    elif "修正しました" not in turned_on:
        failures.append(f"turning it on no longer changes anything: {turned_on[:80]}")
    else:
        passed += 1

    # C: the claim. Already False, so nothing changes - and the answer has to
    # say what that leaves true, because the briefing still appears on a first
    # visit. This is the half a rename alone would not fix.
    _make2, off_on_new = _play(
        ["レースゲームを作って", "さっきのゲームのブリーフィングをオフにして"]
    )
    if "すでにその設定です" not in off_on_new:
        failures.append(f"the no-change case changed shape: {off_on_new[:80]}")
    elif "初回" not in off_on_new:
        failures.append(
            "「すでにその設定です」 is all it says, so the briefing they just read "
            f"reads as turned off: {off_on_new[:100]}"
        )
    else:
        passed += 1

    # D: ...and the note is not printed where it would be false. Turning it
    # off when it is ON is a real change; saying 「切のままです」 there would be
    # a sentence about a state the request just left.
    _m3, _on, off_after_on = _play(
        [
            "レースゲームを作って",
            "さっきのゲームのブリーフィングをオンにして",
            "さっきのゲームのブリーフィングをオフにして",
        ]
    )
    if "切のままです" in off_after_on:
        failures.append(
            f"the 「unchanged」 note was printed on a real change: {off_after_on[:90]}"
        )
    elif "修正しました" not in off_after_on:
        failures.append(f"turning it off after on no longer works: {off_after_on[:90]}")
    else:
        passed += 1

    # E: the other flag is untouched - the note belongs to this field only.
    _m4, daily = _play(
        ["レースゲームを作って", "さっきのゲームの今日の挑戦をオフにして"]
    )
    if "初回" in daily or "切のままです" in daily:
        failures.append(f"the briefing note leaked onto 今日の挑戦: {daily[:90]}")
    else:
        passed += 1

    # F: the guard that keeps the note off a state the request just left,
    # checked by calling it rather than through the service. Measured: that
    # state cannot be reached end to end - turning the flag off when it is on
    # IS a change, so the no-change branch the note lives in never runs - and
    # a probe that removed the guard scored full marks against the four
    # checks above. Weaker evidence than a real run, and recorded as such;
    # the alternative was a check that cannot fail.
    from sidra_ai.creation.revise import _flag_already_note

    if _flag_already_note({"brief": "off"}, {"brief": True}) != "":
        failures.append(
            "the note is produced for a page whose briefing flag is on, which "
            "would describe a state the request had just changed"
        )
    elif _flag_already_note({"brief": "off"}, {"brief": False}) == "":
        failures.append("the note is not produced for the case it exists for")
    else:
        passed += 1

    return PanelFieldNameResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=6,
        failures=tuple(failures),
    )
