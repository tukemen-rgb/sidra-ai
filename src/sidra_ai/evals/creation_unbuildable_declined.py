"""Is an unbuildable make request declined honestly, not answered as a question?

C-1261: 「Excelを作って」「アプリを作って」「動画を作って」 are read by the detector
as genuine creation requests (is_creation, kind=UNKNOWN, weak), but service.chat
only routed strong intents, so these fell through to the Q&A path and came back
「現時点では十分な根拠がありません…取り込み（POST /v1/github/analyze）を管理者に
依頼してください」 - repository-ingestion advice for a make request. Game-genre
declines (RPG/クイズ) route (strong) and were already honest; only the non-game
unbuildable kinds went to the wall.

Now such a request is named as a creation ask and answered with what *can* be
made. Measured through the real chat path: the unbuildable requests get the
kinds list and not the Q&A wall, a buildable request still creates, and a real
question still reaches the question path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Explicit make requests for kinds no generator builds.
_UNBUILDABLE: tuple[str, ...] = (
    "Excelを作って",
    "アプリを作って",
    "動画を作って",
    "曲を作って",
    "スプレッドシートを作って",
)

#: The tell of the Q&A no-evidence wall - a raw endpoint no make request
#: should be pointed at.
_QA_WALL = "/v1/github/analyze"

#: The decline lists what can be made; these two kinds must appear.
_KIND_MARKERS = ("ゲーム", "レポート")
_OFFER_MARKER = "作れるのは"


@dataclass(frozen=True)
class CreationUnbuildableDeclinedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="unbuildable-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def evaluate_creation_unbuildable_declined() -> CreationUnbuildableDeclinedResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def answer(text: str) -> str:
        return str((service.chat(text) or {}).get("answer") or "")

    for request in _UNBUILDABLE:
        a = answer(request)
        # 1: not the Q&A ingestion wall.
        add(_QA_WALL not in a, f"{request!r}: fell to the Q&A wall: 「{a[:60]}」")
        # 2: names what can be made instead.
        add(_OFFER_MARKER in a and all(m in a for m in _KIND_MARKERS),
            f"{request!r}: does not list buildable kinds: 「{a[:80]}」")

    # Control: a buildable request still creates, not declines.
    made = answer("レースゲームを作って")
    add("作りました" in made and "作れません" not in made,
        f"a buildable request no longer creates: 「{made[:60]}」")

    # Control: a real question still reaches the question path, not the decline.
    asked = answer("GAMEYARDの理念を教えて")
    add(_QA_WALL in asked and "作れません" not in asked,
        f"a question was diverted from the question path: 「{asked[:60]}」")

    total = 2 * len(_UNBUILDABLE) + 2
    return CreationUnbuildableDeclinedResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "CreationUnbuildableDeclinedResult",
    "evaluate_creation_unbuildable_declined",
]
