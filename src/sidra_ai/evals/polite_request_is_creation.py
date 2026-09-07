"""Does a politely-phrased request to make something route to a generator?

C-1454: creation intent required a bare imperative ("作って") and treated the
question marker 「ますか」 as a veto. But Japanese business requests are
overwhelmingly polite - 「資料を作成いただけますか」「スライドを作ってもらえますか」
「アートを描いてください」 - and every one of those ends in 「ますか」 or uses a
courtesy auxiliary that the bare verb list misses. So a polite request to build
a deck was answered as a *question* (retrieval Q&A over the corpus), silently
dropping the deck the operator asked for.

The detector now recognises a making stem followed by a benefactive/honorific
auxiliary as a request, exempt from the courtesy veto, while an explanation
question ("作り方を教えて") still stays a question.

The checks call the real ``detect_creation_intent`` and read the route.
"""

from __future__ import annotations

from dataclasses import dataclass


# Polite requests that must route to a generator, with the kind expected.
_REQUESTS = (
    ("スライドを作ってもらえますか", "DECK"),
    ("スライドを作成いただけますか", "DECK"),
    ("プレゼン資料を用意してもらえますか", "DECK"),
    ("レポートを書いてもらえますか", "DOCUMENT"),
    ("3Dモデルを出力していただけますか", "MODEL3D"),
    ("アートを描いてください", "ART"),
    ("ゲームを作っていただけますか", "GAME"),
)

# Genuine questions that must stay on the Q&A path.
_QUESTIONS = (
    "スライドの作り方を教えてもらえますか",
    "デッキはどうやって作りますか",
    "スライドの作成方法を教えて",
    "資料を作ってますか",
)


@dataclass(frozen=True)
class PoliteRequestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_polite_request_is_creation() -> PoliteRequestResult:
    from sidra_ai.creation.intent import detect_creation_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for message, want_kind in _REQUESTS:
        intent = detect_creation_intent(message)
        add(intent.routes and intent.kind.name == want_kind,
            f"polite request not routed to {want_kind}: {message!r} "
            f"(routes={intent.routes}, kind={intent.kind.name})")

    for message in _QUESTIONS:
        intent = detect_creation_intent(message)
        add(not intent.is_creation,
            f"a question was misread as creation: {message!r} "
            f"(kind={intent.kind.name})")

    total = len(_REQUESTS) + len(_QUESTIONS)
    return PoliteRequestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["PoliteRequestResult", "evaluate_polite_request_is_creation"]
