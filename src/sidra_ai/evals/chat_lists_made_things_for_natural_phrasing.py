"""Does "show me what I made", said naturally, reach the list?

C-1897. ``_is_artifact_list_query`` matched the whole message against a fixed
set, so 「作ったものの一覧を見せて」 - the set's own 「作ったものの一覧」 followed by
the ordinary request 「を見せて」 - did not match, and fell through to corpus
retrieval, which answered a question about this product's own files with an
unrelated sales document. Driven through the real service, 13 of 14 natural
phrasings missed; only 「何を作りましたか？」 hit.

The C-1844/C-1866 family again: a question ABOUT the product's own output sent
to the corpus wall. The fix strips a trailing request verb (を見せて/を教えて/
が見たい…) before the whole-message match, the same shape as the greeting-suffix
strip already there, so a composed phrase reduces to a base the set knows -
without the substring rule C-1844 deliberately avoided, which would swallow a
real corpus query like 「作ったものの一覧をドキュメントから探して」.

Both directions are checked: the natural phrasings must be recognised, and the
corpus queries (C-1844's ``CORPUS_QUESTIONS`` plus two that look close) must
not be. Two checks drive the whole service, so the detector staying wired to
the branch is proven, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService, _is_artifact_list_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.artifact_list_is_answered import CORPUS_QUESTIONS
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Natural ways a person asks to see what this product has made. Each is a
#: made-things noun phrase the set already knows (or a plain kanji/file variant
#: of one) plus an ordinary request verb.
NATURAL_LIST_PHRASINGS: tuple[str, ...] = (
    "作ったものの一覧を見せて",
    "作ったものの一覧を見せてください",
    "作ったものの一覧を教えて",
    "作ったものの一覧が見たい",
    "作った物の一覧を見せて",
    "作ったもの一覧を見せて",
    "成果物の一覧を見せて",
    "成果物一覧を見せて",
    "作ったファイルの一覧を見せて",
)

#: Must NOT be read as a list request: real corpus questions. The two extra
#: ones share the list's words but ask something else - one searches the
#: documents, one asks how a made game plays.
NOT_LIST_PHRASINGS: tuple[str, ...] = CORPUS_QUESTIONS + (
    "作ったものの一覧をドキュメントから探して",
    "作ったゲームの遊び方を教えて",
)


@dataclass(frozen=True)
class ChatListsMadeThingsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_lists_made_things_for_natural_phrasing() -> ChatListsMadeThingsResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) every natural phrasing is recognised as a list request --------
    for phrase in NATURAL_LIST_PHRASINGS:
        add(_is_artifact_list_query(phrase), f"A: not recognised: {phrase!r}")

    # --- (B) no corpus question is mistaken for one ------------------------
    for phrase in NOT_LIST_PHRASINGS:
        add(not _is_artifact_list_query(phrase), f"B: wrongly recognised: {phrase!r}")

    # --- (C) the detector is wired to the branch: the whole service, on a
    #         natural phrasing, returns the artifact_list refusal (not the
    #         no-evidence abstention). ---------------------------------------
    root = Path(scratch_dir("sidra-c1897-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    hit = service.chat("作ったものの一覧を見せて")
    add(hit.get("refusal") == "artifact_list",
        f"C: service answered {hit.get('refusal')!r} for a natural list phrasing")

    # --- (D) and a close-looking corpus query still reaches retrieval ------
    veto = service.chat("作ったものの一覧をドキュメントから探して")
    add(veto.get("refusal") != "artifact_list",
        "D: a corpus query was mistaken for a list request end to end")

    total = len(NATURAL_LIST_PHRASINGS) + len(NOT_LIST_PHRASINGS) + 2
    return ChatListsMadeThingsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ChatListsMadeThingsResult",
    "evaluate_chat_lists_made_things_for_natural_phrasing",
    "NATURAL_LIST_PHRASINGS",
    "NOT_LIST_PHRASINGS",
]
