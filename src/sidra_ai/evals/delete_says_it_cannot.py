"""Told to delete an artifact, does the product say it cannot?

C-1847. Deletion is not implemented - it is a destructive operation and needs
the owner's decision, which is why it sits in the E section rather than in a
loop cycle. What was wrong is that nothing said so. Measured across six
phrasings, one request got three different answers about something else:

* 「さっきのゲームを消して」「削除して」「作ったものを全部消して」 → the list of
  things that CAN be changed (difficulty, theme, accent colour) - a colour menu
  for someone asking to delete;
* 「さっきのスライドを消して」 → the kind refusal (C-1835);
* 「さっきのゲームを捨てて」 → the no-evidence boilerplate that asks for a
  repository to be ingested.

The boundary matters as much as the rule. 「さっきのゲームの音を消して」 is
C-1814's own example - turning a feature off - and must keep its answer, so
only a delete verb acting on the artifact itself counts.

The check that matters is the directory: this eval counts files before and
after, because an answer that says 「何も消していません」 while removing one is
the worst outcome of all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import asks_to_delete
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

DELETE_REQUESTS: tuple[str, ...] = (
    "さっきのゲームを消して",
    "さっきのゲームを削除して",
    "作ったものを全部消して",
    "さっきのスライドを消して",
    "さっきのゲームを捨てて",
)

#: Deleting something INSIDE the artifact is a change request, not this.
NOT_DELETIONS: tuple[str, ...] = (
    "さっきのゲームの音を消して",
    "BGMを消して",
    "効果音を消して",
)


@dataclass(frozen=True)
class DeleteRefusalResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_delete_says_it_cannot() -> DeleteRefusalResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("sidra-c1847-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("猫のゲームを作って")
    service.chat("海のアートを作って")
    before = {path.name for path in (root / "artifacts").iterdir()}

    answers = {request: service.chat(request) for request in DELETE_REQUESTS}
    after = {path.name for path in (root / "artifacts").iterdir()}

    # --- (A) nothing was deleted ------------------------------------------
    #     First, because an apology that deletes is worse than silence.
    add(before <= after, f"A: files disappeared: {sorted(before - after)}")
    # --- (B) every phrasing gets the same, true answer --------------------
    wrong = {
        request: result.get("refusal")
        for request, result in answers.items()
        if result.get("refusal") != "delete_unsupported"
    }
    add(not wrong, f"B: answered as something else: {wrong}")
    # --- (C) and the answer says nothing was removed ----------------------
    add(all("何も消していません" in (result.get("answer") or "")
            for result in answers.values()),
        "C: the answer does not say that nothing was deleted")
    # --- (D) it says where the files are ----------------------------------
    add(all("artifacts/" in (result.get("answer") or "")
            for result in answers.values()),
        "D: the answer does not say where the files are")
    # --- (E) and does not print the machine's own path --------------------
    #     This sentence goes into chat logs and screenshots.
    add(all(str(root) not in (result.get("answer") or "")
            for result in answers.values()),
        "E: the absolute data directory is in the answer")
    # --- (F) turning a feature off is not deleting the artifact -----------
    add(not any(asks_to_delete(message) for message in NOT_DELETIONS),
        f"F: a feature request read as a deletion: "
        f"{[m for m in NOT_DELETIONS if asks_to_delete(m)]}")
    # --- (G) and still gets its old answer --------------------------------
    add(service.chat("さっきのゲームの音を消して").get("refusal") == "revision_change",
        "G: 「音を消して」 changed which refusal it gets")
    # --- (H) a real revision still works ----------------------------------
    add(service.chat("さっきのゲームを難しくして").get("refused") is False,
        "H: a genuine revision stopped working")

    return DeleteRefusalResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "DELETE_REQUESTS",
    "DeleteRefusalResult",
    "NOT_DELETIONS",
    "evaluate_delete_says_it_cannot",
]
