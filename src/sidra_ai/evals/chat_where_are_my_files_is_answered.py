"""Asked where the files it made are, does the product say - or search the corpus?

C-1917. The artifact-list handler (C-1897/C-1906) answers "what have you made"
and, in doing so, already says where the files are: 「ファイルは /v1/artifacts
から取得できます」 / "Fetch them from /v1/artifacts". But it only recognised
list phrasings, not the whereabouts phrasings a user reaches for right after
making something: 「作ったファイルはどこにありますか」, "where are my files",
"list my files". Those fell through to RAG and came back with an unrelated
indexed document (a repo's notes on Ren'Py web export, a download page), leaving
the reader no closer to their own files.

The fix adds those location phrasings to the same recogniser, so they get the
same honest answer in the request's language (rule 6). It stays a whole-message
match scoped to the user's OWN output ("my"/「作った」): a corpus question about
where some files live ("where are the config files") and the download-ambiguous
"how do I download the game" are deliberately left to the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService, _is_artifact_list_query
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Whereabouts questions about the user's own artifacts (JP + EN).
LOCATION_QUERIES: tuple[str, ...] = (
    "作ったファイルはどこにありますか",
    "作ったファイルはどこ",
    "作ったものはどこ",
    "作ったものはどこにありますか",
    "作った物はどこ",
    "where are my files",
    "where are my artifacts",
    "where are my creations",
    "list my files",
    "list my artifacts",
)

#: Not whereabouts-of-my-artifacts: a corpus question about some files, and the
#: download-ambiguous phrasing (the corpus can be about distribution). These
#: must NOT be swallowed by the recogniser.
NOT_LOCATION_QUERIES: tuple[str, ...] = (
    "where are the config files",
    "how do i download the game",
    "where is the deploy script",
    "設定ファイルはどこにありますか",
)

_FETCH = "/v1/artifacts"
_WALL = "/v1/github/analyze"


@dataclass(frozen=True)
class WhereAreMyFilesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1917-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("猫のゲームを作って")
    return service


def evaluate_chat_where_are_my_files_is_answered() -> WhereAreMyFilesResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # (A) each location question routes to the artifact-list answer, which names
    #     where the files are (/v1/artifacts) and does not send them to the wall.
    for q in LOCATION_QUERIES:
        r = service.chat(q)
        answer = r.get("answer") or ""
        add(r.get("refusal") == "artifact_list" and _FETCH in answer and _WALL not in answer,
            f"A: {q!r} -> refusal={r.get('refusal')!r}, fetch={_FETCH in answer}: 「{answer[:120]}」")

    # (B) answered in the request's language (rule 6).
    jp = service.chat("作ったファイルはどこにありますか").get("answer") or ""
    add("取得" in jp or "件" in jp, f"B: JP location not answered in Japanese: 「{jp[:120]}」")
    en = service.chat("where are my files").get("answer") or ""
    add(any(c.isascii() and c.isalpha() for c in en) and "取得" not in en,
        f"B: EN location not answered in English: 「{en[:120]}」")

    # (C) a corpus/download question is NOT read as an artifact-list request.
    caught = [q for q in NOT_LOCATION_QUERIES if _is_artifact_list_query(q)]
    add(not caught, f"C: a corpus/download question was swallowed: {caught}")

    # (D) the existing list phrasings still route to the artifact-list answer.
    for q in ("作ったものの一覧", "show me what you made"):
        add(service.chat(q).get("refusal") == "artifact_list",
            f"D: existing list phrasing {q!r} regressed")

    total = len(LOCATION_QUERIES) + 2 + 1 + 2
    return WhereAreMyFilesResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "LOCATION_QUERIES",
    "NOT_LOCATION_QUERIES",
    "WhereAreMyFilesResult",
    "evaluate_chat_where_are_my_files_is_answered",
]
