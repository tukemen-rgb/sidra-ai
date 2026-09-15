"""Does the advice the product prints actually work when sent back?

C-1873, §33 事実 3 (reduce the reader's correction effort) and 事実 7 (provide a
solution). Measured 2026-09-15 22:45: the refusal printed

    「難易度は変えられます——easy / normal / hard の 3 段です。その言い方で、
     もう一度送ってください。」

and all three of those words came back with the same sentence. A reader doing
exactly what they were told went round in a circle. The colour advice worked,
so only the difficulty was broken - and worse than a wording problem: the
ladder could only be STEPPED, so there was no phrasing at all for 「set it to
normal」 and returning from hard meant counting rungs.

This eval exists because C-1868's own check did not catch it. That check was
named "the advice WORKS" and ran 「さっきのゲームを難しくして」 - a phrase the
advice does not print. Running *a* working phrase is not running *the* advice,
and the difference is the whole check. So here the values are lifted out of
``field_values`` - the function that writes the sentence - and sent back
verbatim. Nothing in this file names a rung or a colour.

A new variant for the catalogue of hollow checks, alongside "the eval builds
its input from the function it is testing", "a sabotage that deletes a check
nothing triggers", and "full marks against a sabotage": **a check that says it
measures the advice while measuring something else that happens to work.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import field_values
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: The fields whose advice names values a reader can send straight back.
#: 「title」 is excluded: its advice is a shape (「「〇〇」にして」), not a list of
#: values, and the eval would be inventing a name to fill the blank.
VALUE_FIELDS: tuple[tuple[str, str], ...] = (
    ("difficulty", "さっきのゲームの難易度を{value}にして"),
    ("accent", "さっきのゲームの差し色を{value}にして"),
    ("theme", "さっきのゲームを{value}のテーマにして"),
)

#: Values are pulled out of the printed sentence, not listed here. Anything
#: separated by 「/」 in what field_values returns is offered to the reader.
_OFFERED = re.compile(r"[^/。]+")


def offered_values(key: str, template: str) -> tuple[str, ...]:
    """Exactly the words the advice puts in front of the reader."""

    said = field_values(key, template)
    head = said.split("の 3 段")[0].split("の 4 つ")[0].split("から選べます")[0]
    return tuple(
        part.strip() for part in head.split("/") if part.strip()
    )


@dataclass(frozen=True)
class PrintedAdviceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_printed_advice_actually_works() -> PrintedAdviceResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("c1873-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("迷宮を冒険するゲームを作って")

    # --- (A) every value the advice names is accepted ---------------------
    for key, shape in VALUE_FIELDS:
        values = offered_values(key, "adventure")
        add(len(values) >= 2, f"A: {key}: the advice offered {values}")
        for value in values:
            result = service.chat(shape.format(value=value))
            add(result.get("refused") is False,
                f"A: {key}: the advice named {value!r} and it was refused: "
                f"{(result.get('answer') or '')[:60]}")

    # --- (B) a rung can be named, not only stepped toward -----------------
    #     hard -> normal in one message. Before this there was no phrasing
    #     for it at all, which is a missing capability rather than a wording
    #     problem, and no amount of rewording the advice would have fixed it.
    service.chat("さっきのゲームの難易度を hard にして")
    back = service.chat("さっきのゲームの難易度を normal にして")
    add(back.get("refused") is False, "B: naming a rung was refused")
    add("→normal" in (back.get("answer") or "").replace(" ", ""),
        f"B: hard did not land on normal: {(back.get('answer') or '')[:70]}")

    # --- (B2) a Japanese rung name lands ABSOLUTELY, not one step ---------
    #     The ordering hazard the code claims to handle: 「むずかしい」 shares a
    #     stem with 「難しく」, so the relative rule would swallow it and step
    #     one rung instead of landing on hard. Added after a sabotage that
    #     broke exactly that ordering scored full marks - the probes above are
    #     all in English, so nothing reached the case the comment describes.
    service.chat("さっきのゲームの難易度を easy にして")
    jumped = service.chat("さっきのゲームの難易度をむずかしいにして")
    #     Asserted on the CHANGE, not on the word. Written as 「hard in the
    #     answer」 first, and the refusal advice itself reads 「easy / normal /
    #     hard の 3 段です」 - so the check was satisfied by the very sentence it
    #     was meant to rule out, and the sabotage that broke the ordering
    #     scored full marks. The transition line is the only proof.
    add(jumped.get("refused") is False,
        f"B2: a Japanese rung name was refused: {(jumped.get('answer') or '')[:70]}")
    add("easy→hard" in (jumped.get("answer") or "").replace(" ", ""),
        f"B2: a named rung stepped instead of landing: "
        f"{(jumped.get('answer') or '')[:70]}")

    # --- (B3) a colour word alone does not repaint the whole palette ------
    #     The theme cue guard, probed. 「白」 is one of paper's words, so
    #     without the cue 「白くして」 would swap the entire theme when the
    #     reader asked for an accent. Added after a sabotage that removed the
    #     guard scored full marks - every probe above says 「テーマ」, so
    #     nothing reached the case the guard exists for.
    white = service.chat("さっきのゲームを白くして")
    add("配色" not in (white.get("answer") or ""),
        f"B3: a bare colour word repainted the theme: "
        f"{(white.get('answer') or '')[:70]}")

    # --- (C) the relative words are untouched -----------------------------
    service.chat("さっきのゲームの難易度を normal にして")
    harder = service.chat("さっきのゲームを難しくして")
    add("hard" in (harder.get("answer") or ""),
        f"C: 「難しくして」 stopped stepping up: {(harder.get('answer') or '')[:70]}")
    easier = service.chat("さっきのゲームを簡単にして")
    add("normal" in (easier.get("answer") or ""),
        f"C: 「簡単にして」 stopped stepping down: {(easier.get('answer') or '')[:70]}")

    # --- (D) naming the field alone still asks, rather than guessing ------
    #     C-1868's answer, unchanged: a field with no value is a question,
    #     not a licence to pick a rung on the reader's behalf.
    asked = service.chat("さっきのゲームの難易度を変えて")
    add(asked.get("refusal") == "revision_change",
        "D: naming the field alone stopped asking which value")

    return PrintedAdviceResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
