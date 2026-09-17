"""Told in English to delete an artifact, does the product say it cannot?

C-1912's sibling for deletion. C-1847 made 「消して」「削除して」 answer honestly -
``refusal="delete_unsupported"``, "nothing was deleted, the files are in
artifacts/". But the English equivalents ("delete the game", "delete it",
"remove the last game", "can you delete my files") were not recognised:
``asks_to_delete`` had only Japanese verbs, so the request fell through to RAG
and came back with an unrelated indexed document (e.g. a repo's "DELETE
/api/auth/me" endpoint). A delete-sounding request answered with unrelated
content leaves the reader unsure whether anything was removed - the worst thing
a destructive-sounding request can do.

The fix adds an English delete pattern (the twin of the Japanese one, an
imperative delete verb acting on an artifact word) and answers the refusal in
the request's language (rule 6). The boundary is kept tight: a corpus question
about deletion ("how do I delete a user account") and a feature/panel request
("delete the accent color") are not deletions of an artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import asks_to_delete
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: English requests to delete the artifact itself.
DELETE_REQUESTS_EN: tuple[str, ...] = (
    "delete the game",
    "remove the last game",
    "delete it",
    "can you delete my files",
    "erase everything",
    "please delete the slides",
)

#: Not deletions of an artifact: a corpus question about deletion, and a
#: feature/panel request. asks_to_delete must stay False for these.
NOT_DELETIONS_EN: tuple[str, ...] = (
    "how do I delete a user account",
    "what does the DELETE endpoint do",
    "delete the accent color",
)

_JP_ONLY = "削除は用意していません"


@dataclass(frozen=True)
class EnglishDeleteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_english_delete_says_it_cannot() -> EnglishDeleteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("sidra-c1915-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("猫のゲームを作って")
    service.chat("海のアートを作って")
    before = {path.name for path in (root / "artifacts").iterdir()}

    answers = {req: service.chat(req) for req in DELETE_REQUESTS_EN}
    after = {path.name for path in (root / "artifacts").iterdir()}

    # (A) nothing was deleted - first, because an apology that deletes is worse.
    add(before <= after, f"A: files disappeared: {sorted(before - after)}")

    # (B) every English phrasing gets the delete_unsupported refusal.
    wrong = {req: r.get("refusal") for req, r in answers.items()
             if r.get("refusal") != "delete_unsupported"}
    add(not wrong, f"B: answered as something else: {wrong}")

    # (C) the answer is in English (rule 6), not the Japanese message.
    for req, r in answers.items():
        answer = r.get("answer") or ""
        english = any(c.isascii() and c.isalpha() for c in answer) \
            and _JP_ONLY not in answer
        add(english, f"C: {req!r} not answered in English: 「{answer}」")

    # (D) the English answer says nothing was removed and where the files are.
    for req, r in answers.items():
        answer = (r.get("answer") or "").lower()
        add("nothing was deleted" in answer and "artifacts/" in answer,
            f"D: {req!r} answer lacks the honest facts: 「{r.get('answer')}」")

    # (E) the absolute data directory is not leaked into the answer.
    add(all(str(root) not in (r.get("answer") or "") for r in answers.values()),
        "E: the absolute data directory is in the answer")

    # (F) a corpus question / feature request is NOT read as a deletion.
    caught = [m for m in NOT_DELETIONS_EN if asks_to_delete(m)]
    add(not caught, f"F: a non-deletion was read as a delete request: {caught}")

    # (G) the Japanese delete request still works (regression guard).
    jp = service.chat("さっきのゲームを消して")
    add(jp.get("refusal") == "delete_unsupported" and _JP_ONLY in (jp.get("answer") or ""),
        "G: the Japanese delete refusal regressed")

    return EnglishDeleteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "DELETE_REQUESTS_EN",
    "NOT_DELETIONS_EN",
    "EnglishDeleteResult",
    "evaluate_chat_english_delete_says_it_cannot",
]
