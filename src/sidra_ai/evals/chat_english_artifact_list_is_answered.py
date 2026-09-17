"""Is an English "show me what you made" answered with the list, or the corpus?

C-1906. ``_ARTIFACT_LIST_QUERIES`` recognised the Japanese ways of asking to see
what has been made, but not the English ones, so 「show me what you made」「what
have you made」「show my files」 fell through to retrieval and returned unrelated
Japanese corpus fragments. The English sibling of C-1902 (greetings) and C-1904
(help/identity); the third and last of the English conversational-entry set.

The fix adds the English phrasings and answers in the message's language
(rule 6): a Japanese list request keeps the Japanese reply, an English one gets
an English listing. Whole-message match, so a real corpus question is untouched.
Both the empty ("nothing made yet") and non-empty (a real listing) paths are
driven, and a Japanese request is checked to still get the Japanese reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService, _is_artifact_list_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

ENGLISH_LIST_QUERIES: tuple[str, ...] = (
    "show me what you made", "show me what you've made", "what have you made",
    "what did you make", "list what you made", "show my files",
    "show me my files", "what files have you made",
)

#: Real English messages that must NOT be read as a list request.
NOT_A_LIST: tuple[str, ...] = (
    "what is the sales plan?",
    "show me the sales figures for last quarter",
    "how do I use the auth module?",
)

_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


@dataclass(frozen=True)
class EnglishArtifactListResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_english_artifact_list_is_answered() -> EnglishArtifactListResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) each English list phrasing is recognised ---------------------
    for q in ENGLISH_LIST_QUERIES:
        add(_is_artifact_list_query(q), f"A: not recognised: {q!r}")

    # --- (B) no real corpus question is mistaken for one ------------------
    for q in NOT_A_LIST:
        add(not _is_artifact_list_query(q), f"B: wrongly recognised: {q!r}")

    root = Path(scratch_dir("sidra-c1906-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )

    # --- (C) end to end, nothing made: English list request gets an English
    #         "nothing yet" reply, not the corpus abstention -----------------
    empty = service.chat("show me what you made")
    ea = empty.get("answer") or ""
    add(empty.get("refusal") == "artifact_list"
        and bool(re.search(r"[A-Za-z]", ea)) and not _CJK.search(ea),
        f"C: empty English list answered {empty.get('refusal')!r}, cjk={bool(_CJK.search(ea))}")

    # --- (D) with something made, the English listing names it ------------
    service.chat("make a fishing game")
    listed = service.chat("what have you made")
    la = listed.get("answer") or ""
    add(listed.get("refusal") == "artifact_list"
        and not _CJK.search(la) and "/v1/artifacts" in la,
        f"D: non-empty English list answered {listed.get('refusal')!r}, cjk={bool(_CJK.search(la))}")

    # --- (E) a Japanese request still gets the Japanese reply ------------
    jp = service.chat("作ったものを一覧で見せて")
    add(jp.get("refusal") == "artifact_list" and bool(_CJK.search(jp.get("answer") or "")),
        f"E: Japanese list answered {jp.get('refusal')!r}")

    total = len(ENGLISH_LIST_QUERIES) + len(NOT_A_LIST) + 3
    return EnglishArtifactListResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "EnglishArtifactListResult",
    "evaluate_chat_english_artifact_list_is_answered",
    "ENGLISH_LIST_QUERIES",
    "NOT_A_LIST",
]
