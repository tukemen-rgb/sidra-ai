"""Told in English to make something it can't, does it decline in English?

C-1919. When a creation request names a kind no generator builds (an Excel
sheet, a mobile app, a video), the product honestly declines and lists what it
CAN make (C-1261). But the decline was Japanese-only: an English request -
"make an excel spreadsheet", "build me a mobile app" - got 「制作のご依頼と
受け取りましたが、この形式は作れません。いま作れるのは アート・スライド…」, a
Japanese sentence with Japanese kind labels, for an English speaker. This breaks
SYSTEM_PROMPT rule 6 (answer in the question's language), the same gap the
conversational-entry family closed for greetings/help/lists/delete
(C-1902/1904/1906/1915).

The fix language-branches the decline and adds English kind labels. The
Japanese decline is unchanged, and the ``creation`` metadata (declined, offered)
is unchanged - only the answer text's language follows the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: English requests to make a kind no generator builds.
ENGLISH_UNSUPPORTED: tuple[str, ...] = (
    "make an excel spreadsheet",
    "build me a mobile app",
    "make a video of a cat",
    "create a spreadsheet for me",
)
#: The Japanese decline must keep working.
JAPANESE_UNSUPPORTED: tuple[str, ...] = (
    "エクセルを作って",
    "動画を作って",
)

_JP_DECLINE = "この形式は作れません"
_JP_ASK = "制作のご依頼"


@dataclass(frozen=True)
class EnglishUnsupportedCreationResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1919-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_english_unsupported_creation_declined_in_english() -> (
    EnglishUnsupportedCreationResult
):
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # (A) each English unsupported request is declined in English: the answer has
    #     Latin letters, is not the Japanese decline, and still lists a kind.
    for req in ENGLISH_UNSUPPORTED:
        r = service.chat(req)
        answer = r.get("answer") or ""
        english = any(c.isascii() and c.isalpha() for c in answer) \
            and _JP_DECLINE not in answer and _JP_ASK not in answer
        offers = "game" in answer.lower() or "report" in answer.lower() \
            or "slides" in answer.lower()
        add(english and offers,
            f"A: {req!r} not declined in English with offers: 「{answer[:140]}」")

    # (B) each English request is still recognised as a declined creation, not
    #     routed to RAG (the metadata contract from C-1261 is unchanged).
    for req in ENGLISH_UNSUPPORTED:
        outcome = (service.chat(req).get("creation") or {}).get("outcome") or {}
        add(outcome.get("declined") is True and bool(outcome.get("offered")),
            f"B: {req!r} lost its declined-creation metadata: {outcome}")

    # (C) the Japanese decline is unchanged (regression guard).
    for req in JAPANESE_UNSUPPORTED:
        answer = service.chat(req).get("answer") or ""
        add(_JP_DECLINE in answer, f"C: {req!r} lost the Japanese decline: 「{answer[:120]}」")

    total = len(ENGLISH_UNSUPPORTED) * 2 + len(JAPANESE_UNSUPPORTED)
    return EnglishUnsupportedCreationResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ENGLISH_UNSUPPORTED",
    "JAPANESE_UNSUPPORTED",
    "EnglishUnsupportedCreationResult",
    "evaluate_chat_english_unsupported_creation_declined_in_english",
]
