"""Do the product's refusals follow the rules for writing one?

C-1870, from §33 - a section written the same day, because nine sections of the
knowledge base were compared against the product and all nine held, while every
defect found (C-1847, C-1855, C-1861, C-1866, C-1868) was in the wording of a
refusal and no section covered that.

Two rules out of §33 are measured here, and both were already being kept by
hand on the day this was written:

* 事実 6, Microsoft: 「Write a separate error message for each known cause of
  the error. Do not use a single, generic message to explain every possible
  reason.」 C-1847's symptom - one request getting three different wrong
  answers - is that rule broken from the other side, and nothing forbade it.
* 事実 8, Microsoft, and NN/g 事実 2: 「Do not make the user feel at fault even
  if the problem is the result of a user error」 / avoid 「invalid」「illegal」
  「incorrect」. NN/g gives the reason: 「The proper usage of any system lies
  with its creators and not with the system's users」.

Measured 2026-09-15 20:55 before any of this was written: zero blaming words,
zero sentences shared between causes. So this repairs no defect - it repairs
the absence of a guard. The rules were being followed by a day of hand work,
and nothing would have noticed when that lapsed.

What is NOT forbidden: saying the product cannot do something. Naming a limit
is honesty, not blame. What is forbidden is calling the reader's input invalid,
wrong or mistaken.

「please」 is deliberately not policed. Microsoft avoids it because it can make
a required step read as optional; Japanese 「〜してください」 is the ordinary
polite form and carries no such implication. A rule imported without its reason
is a rule about another language (recorded in §33).
"""

from __future__ import annotations

import io
import contextlib
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.ask_cli import render
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: One message per refusal this loop can reach from an ordinary conversation,
#: and the code it must produce. Driven through the real service: a table of
#: expected sentences would be a copy of the product rather than a check on it.
PROBES: dict[str, str] = {
    "さっきのゲームを消して": "delete_unsupported",
    "さっきのゲームの音量を下げて": "panel_setting",
    "さっきのゲームの配色を変えて": "revision_change",
    "スコアを自慢したい": "artifact_feature_question",
    "さっきのスライドを難しくして": "revision_kind",
    "作ったものを見せて": "artifact_list",
    "使い方": "help",
}

#: Words that call the reader's input wrong. 「できません」 is absent on purpose:
#: naming a limit of the product is honesty, not blame.
BLAMING: tuple[str, ...] = (
    "無効", "不正", "誤り", "間違って", "違反", "不適切", "おかしな",
)


@dataclass(frozen=True)
class RefusalWritingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _next_step_text(code: str) -> str:
    """What the CLI prints for this code - the reader's actual next step."""

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        render({"answer": "", "refused": True, "refusal": code, "citations": []})
    return buffer.getvalue()


def evaluate_refusal_writing_follows_the_rules() -> RefusalWritingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("c1870-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("迷宮を冒険するゲームを作って")

    answers: dict[str, str] = {}
    for message, want in PROBES.items():
        result = service.chat(message)
        got = result.get("refusal") or ""
        add(got == want, f"the probe for {want!r} produced {got!r} ({message!r})")
        if got:
            answers.setdefault(got, result.get("answer") or "")

    # --- (A) 事実 8: no answer calls the reader's input wrong --------------
    for code, answer in sorted(answers.items()):
        found = [word for word in BLAMING if word in answer]
        add(not found, f"A: {code} blames the reader: {found} in 「{answer[:50]}」")

    # --- (B) 事実 6: different causes do not share a sentence --------------
    #     C-1847's symptom is this rule broken the other way round: one cause
    #     wearing three sentences. Both directions are the same contract -
    #     a sentence and a cause belong to each other.
    #     Compared on the FIRST SENTENCE, not the whole answer. Written as
    #     whole-string equality first, and a sabotage that gave two causes the
    #     same opening and then diverged scored full marks - which is exactly
    #     the shape the rule forbids, since the first sentence is what says
    #     what happened and the rest is advice.
    by_text: dict[str, list[str]] = {}
    for code, answer in answers.items():
        opening = answer.strip().split("。", 1)[0]
        by_text.setdefault(opening, []).append(code)
    shared = {text[:40]: codes for text, codes in by_text.items() if len(codes) > 1}
    add(not shared, f"B: one sentence for several causes: {shared}")

    # --- (C) 事実 7: every code a reader can reach has a next step ---------
    #     Read out of the CLI by rendering it, not from a list here: a code
    #     the service can set and the CLI has no words for falls back to
    #     「少し時間をおいて、もう一度試す」, which is advice for none of these.
    for code in sorted(answers):
        step = _next_step_text(code)
        add("少し時間をおいて" not in step,
            f"C: {code} falls back to the generic retry advice")
        add(len(step.strip()) > 10, f"C: {code} prints no next step")

    # --- (D) the sentences are distinct enough to be about their own cause -
    add(len(by_text) == len(answers),
        f"D: {len(answers)} causes produced {len(by_text)} distinct openings")

    return RefusalWritingResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
