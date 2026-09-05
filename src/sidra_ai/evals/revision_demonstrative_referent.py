"""Does a demonstrative revision ("その配色を紙にして") reach the reviser?

C-1257: right after making a game, the most natural way to adjust it is a
demonstrative - 「その配色を紙にして」「これをもっと速くして」「それを難しくして」.
None of these routed: ``revise._BACK_REFERENCES`` listed 「さっき」「前の」「ゲーム」…
but not the demonstratives その/これ/それ/この, so ``detect_revision_intent``
vetoed them at the back-reference guard and the message fell to the question
path, which answered a revision request with 「現時点では十分な根拠がありません…
取り込みを管理者に依頼してください」 - pointing the operator at repository
ingestion for a change to a game they just made.

Measured through the real ``chat`` path: a game is created, then each
demonstrative revision is sent, and the response must be a revision outcome
carrying the expected adjustment - not a Q&A answer. Controls confirm the
three existing vetoes still hold: a question that mentions a demonstrative
stays a question, and a creation request stays a creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: (message, adjustment key the revision must carry). Sent after a game exists.
_REVISIONS: tuple[tuple[str, str], ...] = (
    ("その配色を紙にして", "theme"),
    ("これをもっと速くして", "difficulty"),
    ("それを難しくして", "difficulty"),
    ("これのタイトルを「爆走」にして", "title"),
)

#: Messages that must NOT become revisions even though they name a
#: demonstrative - the make-verb and question-marker vetoes still own them.
_CONTROLS: tuple[str, ...] = (
    "それは何ですか",          # a question (question-marker veto)
    "難しいゲームを作って",      # a creation request (make-verb veto)
)


@dataclass(frozen=True)
class RevisionDemonstrativeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    """A real service, echo backend, empty corpus (games need no evidence)."""

    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="revise-demo-"))
    settings = Settings(data_dir=str(tmp / "sidra"))
    return SidraService(settings)


def _revision_of(result: dict) -> dict:
    """The applied adjustments, or ``{}`` if this was not a revision.

    The revision branch of ``chat`` returns ``creation.revision``; a plain
    creation returns ``creation`` without that key, and a Q&A answer has no
    ``creation`` at all. So a non-empty dict here means "routed to the
    reviser", which is exactly what the bug suppressed.
    """

    creation = result.get("creation") or {}
    revision = creation.get("revision")
    return revision if isinstance(revision, dict) else {}


def evaluate_revision_demonstrative_referent() -> RevisionDemonstrativeResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A game to refer back to. Its own routing is a precondition, not a check.
    made = service.chat("レースゲームを作って") or {}
    if not ((made.get("creation") or {}).get("outcome") or {}).get("handled"):
        return RevisionDemonstrativeResult(
            passed=False,
            checks_passed=0,
            checks_total=len(_REVISIONS) + len(_CONTROLS),
            failures=("could not create the game to revise",),
        )

    for message, key in _REVISIONS:
        result = service.chat(message) or {}
        revision = _revision_of(result)
        add(bool(revision) and key in revision,
            f"{message!r}: expected a revision with {key!r}, "
            f"got revision={revision or 'none'} answer={str(result.get('answer'))[:40]!r}")

    for message in _CONTROLS:
        result = service.chat(message) or {}
        add(not _revision_of(result),
            f"{message!r}: wrongly routed to the reviser as {_revision_of(result)}")

    total = len(_REVISIONS) + len(_CONTROLS)
    return RevisionDemonstrativeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "RevisionDemonstrativeResult",
    "evaluate_revision_demonstrative_referent",
]
