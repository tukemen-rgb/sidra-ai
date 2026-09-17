"""A message with no content - does it ask back, or point at the corpus wall?

C-1927. The empty-message branch (C-… "質問が空のようです。何について調べます
か") only fired for ``not message.strip()``, so a message that is *only*
punctuation, symbols or emoji ("...", "？？？", "。。。", "🎮") slipped past it,
reached retrieval, matched nothing, and got the no-evidence wall - "資料を索引
した範囲では…対象リポジトリの取り込みを依頼してください". Telling a user who
typed "???" to have a repository ingested is plainly the wrong answer; the
honest reply to no question is to ask for one, exactly as an empty message gets.

The fix widens the empty check to any message with no alphanumeric or CJK
content character (``str.isalnum`` is true for CJK letters and digits), so
「犬」「8080」「OAuth2」 and real questions are untouched and still answered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Messages with no content character: punctuation, symbols, emoji only.
CONTENTLESS: tuple[str, ...] = (
    "...", "？？？", "。。。", "!!!", "…", "?!?!", "、、、", "＊＊＊",
    "🎮", "🎮🎮🎮", "👍",
)
#: Messages that DO carry content and must be processed normally, not asked back.
HAS_CONTENT: tuple[str, ...] = (
    "犬", "8080", "OAuth2", "認証について教えて", "how does auth work",
)
#: Whitespace-only still asks back (the original behaviour).
WHITESPACE: tuple[str, ...] = ("   ", "　　", "\t ")

_WALL = "/v1/github/analyze"
_NO_EVIDENCE = "十分な根拠がありません"


@dataclass(frozen=True)
class ContentlessResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> SidraService:
    root = Path(scratch_dir("sidra-c1927-"))
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def evaluate_chat_contentless_message_asks_back() -> ContentlessResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service = _service()

    # (A) a contentless message asks back and is not sent to the corpus wall.
    for m in CONTENTLESS:
        r = service.chat(m)
        answer = r.get("answer") or ""
        add(r.get("refusal") == "empty" and _WALL not in answer and _NO_EVIDENCE not in answer,
            f"A: {m!r} -> refusal={r.get('refusal')!r}: 「{answer[:80]}」")

    # (B) a message with real content is not swallowed as empty.
    for m in HAS_CONTENT:
        add(service.chat(m).get("refusal") != "empty",
            f"B: {m!r} was wrongly treated as empty")

    # (C) whitespace-only still asks back (unchanged).
    for m in WHITESPACE:
        add(service.chat(m).get("refusal") == "empty",
            f"C: whitespace {m!r} no longer asks back")

    total = len(CONTENTLESS) + len(HAS_CONTENT) + len(WHITESPACE)
    return ContentlessResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "CONTENTLESS",
    "HAS_CONTENT",
    "WHITESPACE",
    "ContentlessResult",
    "evaluate_chat_contentless_message_asks_back",
]
