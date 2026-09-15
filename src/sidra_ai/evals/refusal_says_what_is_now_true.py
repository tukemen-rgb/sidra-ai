"""When a change is declined, does the answer say the artifact is untouched?

C-1871, from §33 事実 5 (Microsoft): a good message answers 「What happened and
why? / **What is the end result for the user?** / What can the user do?」. The
refusals answered the first and the third.

Measured across eight refusals: three said what is true now
(``delete_unsupported``, ``panel_setting``, and the no-change revision), five
did not. But the rule only genuinely applies to one of those five, and the
exclusions are the substance of this item rather than an afterthought:

* ``artifact_feature_question`` is a QUESTION, not a change request. Nothing
  was going to change, so saying so is noise.
* ``revision_kind`` (「さっきのスライドを難しくして」) names an artifact that does
  not exist. 「スライドは変えていません」 reports the state of nothing.
* ``revision_target`` (「もっと難しくして」) never resolved a target, so
  「何も変えていません」 does not answer the worry - which thing?
* the no-change revision already says it.

That leaves ``revision_change``: the artifact IS identified, the message WAS
read as a change, and the change was declined. Only when those three hold does
「then what state is it in?」 become a real question for the reader.

Adding the sentence everywhere would be the rule applied by machine, and §33
事実 4 warns that a line met over and over goes stale. So this eval checks both
that the sentence is there and that it stayed out of the other four.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: The sentence that answers §33 事実 5's middle question.
STATE_SENTENCE = "いまのゲームはそのままです"

#: A change to a named artifact, declined: both ways of reaching it.
MUST_SAY: tuple[str, ...] = (
    "さっきのゲームの配色を変えて",
    "さっきのゲームの音を消して",
)

#: Refusals with nothing to report the state OF. Each is excluded for its own
#: reason, written in this module's docstring.
MUST_NOT_SAY: dict[str, str] = {
    "スコアを自慢したい": "artifact_feature_question",
    "さっきのスライドを難しくして": "revision_kind",
    "もっと難しくして": "revision_target",
}


@dataclass(frozen=True)
class NowTrueResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_refusal_says_what_is_now_true() -> NowTrueResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("c1871-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("迷宮を冒険するゲームを作って")
    before = {path.name for path in (root / "artifacts").iterdir()}

    # --- (A) a declined change says what is true now ----------------------
    for message in MUST_SAY:
        result = service.chat(message)
        answer = result.get("answer") or ""
        add(result.get("refusal") == "revision_change",
            f"A: {message!r} no longer reaches revision_change")
        add(STATE_SENTENCE in answer,
            f"A: {message!r} does not say what is true now: {answer[:60]}")

    # --- (B) and it is true: nothing moved --------------------------------
    #     Said AND so. A sentence claiming the artifact is untouched, next to
    #     a version quietly written, would be worse than saying nothing.
    after = {path.name for path in (root / "artifacts").iterdir()}
    add(before == after, f"B: files changed: {sorted(after ^ before)}")

    # --- (C) the four with nothing to report keep quiet -------------------
    #     The exclusions are the item. A line every refusal carries is the
    #     rule applied by machine, and §33 事実 4 says such a line goes stale.
    for message, code in MUST_NOT_SAY.items():
        result = service.chat(message)
        got = result.get("refusal")
        add(got == code, f"C: {message!r} produced {got!r}, not {code!r}")
        add(STATE_SENTENCE not in (result.get("answer") or ""),
            f"C: {code} gained a sentence about state it has nothing to report")

    # --- (D) the neighbours this sits inside are untouched -----------------
    changed = service.chat("さっきのゲームを難しくして")
    add(changed.get("refused") is False, "D: a genuine revision stopped working")
    add(STATE_SENTENCE not in (changed.get("answer") or ""),
        "D: a successful revision claims the game is unchanged")
    deleted = service.chat("さっきのゲームを消して")
    add("何も消していません" in (deleted.get("answer") or ""),
        "D: the deletion answer lost its own statement of what is true now")

    return NowTrueResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
