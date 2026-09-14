"""When the artifact is named but the change is not read, is the reply useful?

C-1814, the mirror of C-1797. That item covered a change with no artifact
(「もっと難しくして」) and gave the reason this one needs too: such a message
"must not fall through to retrieval - a plain imperative is not a corpus
question, and answering it 「現時点では十分な根拠がありません … POST
/v1/github/analyze …」 sends the operator entirely the wrong way".

The other half was still falling through. 「さっきのゲームの音を消して」 named its
artifact and used a change verb, but 音 is not one of the eight things a
revision can set, so the detector reported not-a-revision and the message
reached the corpus wall - C-1261's mistake. The reader had usually just been
told by the sibling refusal to write 「それ」「さっきの」, so the product's own
advice did not work on the product.

The sharpest check here is that last point turned into a test: the example the
new refusal prints is executed, and has to work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir

_INGEST = "/v1/github/analyze"
_NO_EVIDENCE = "現時点では十分な根拠がありません"


@dataclass(frozen=True)
class RevisionChangeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _fresh_service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    svc = SidraService(Settings(data_dir=str(Path(scratch_dir(prefix="rev-chg-")) / "s")))
    svc.chat("レースゲームを作って")
    return svc


def evaluate_revision_names_what_it_can_change() -> RevisionChangeResult:
    from sidra_ai.creation.revise import CHANGEABLE

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a named artifact with an unreadable change is not a search ----
    for message in ("さっきのゲームの音を消して", "それのBGMを変えて",
                    "さっきのゲームの背景を暗くして", "さっきのゲームのタイトルを変えて"):
        reply = _fresh_service().chat(message)
        answer = reply.get("answer") or ""
        add(_INGEST not in answer and _NO_EVIDENCE not in answer,
            f"A: 「{message}」 was answered as a failed corpus search")
        add(reply.get("refusal") == "revision_change",
            f"A: 「{message}」 refusal is {reply.get('refusal')!r}")
        add(all(label in answer for _key, label in CHANGEABLE),
            f"A: 「{message}」 does not list what can be changed")

    # --- (B) the advice it prints has to work -----------------------------
    # The whole defect was a refusal whose instruction did not work, so the
    # example in the new one is executed rather than trusted.
    svc = _fresh_service()
    printed = svc.chat("さっきのゲームの音を消して").get("answer") or ""
    add("タイトルを「〇〇」にして" in printed, "B: the reply stopped showing an example")
    followed = svc.chat("さっきのゲームのタイトルを「星の道」にして")
    add(not followed.get("refused"), "B: the example the reply prints is itself refused")
    add("星の道" in (followed.get("answer") or ""), "B: following the example changed nothing")

    # --- (C) a change that IS read still happens --------------------------
    done = _fresh_service().chat("さっきのゲームを難しくして")
    add(not done.get("refused") and "hard" in (done.get("answer") or ""),
        "C: an ordinary revision regressed")

    # --- (D) C-1797's side is untouched -----------------------------------
    unpointed = _fresh_service().chat("難しくして")
    add(unpointed.get("refusal") == "revision_target",
        f"D: a change with no artifact is now {unpointed.get('refusal')!r}")

    # --- (E) a real question is still a question --------------------------
    # Without this, routing everything to the new refusal would score full
    # marks above and the Q&A path would be gone.
    asked = _fresh_service().chat("難易度とは何ですか")
    add(asked.get("refusal") != "revision_change", "E: a question became a revision refusal")

    return RevisionChangeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["RevisionChangeResult", "evaluate_revision_names_what_it_can_change"]
