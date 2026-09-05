"""Do art and GIF titles drop the kind word, or echo it into a doubled summary?

C-1265: documents (C-1246), decks (C-1249), 3D models and games all strip the
kind noun from the title, but art and GIF did not. 「螺旋のアートを作って」 came
back 「『螺旋のアート』のジェネラティブアートを作りました」 - アート twice - and
「猫のGIFを作って」 → 「『猫のGIF』のアニメ GIF を作りました」. The title should be the
subject alone (「螺旋」, 「猫」), like every other generator.

Measured through the real chat path: a named-subject request shows the subject
alone in its summary and never the doubled form; a bare kind word still produces
a handled artifact; and model3d (which already strips) is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: (request, subject, doubled-form-that-must-not-appear)
_NAMED: tuple[tuple[str, str, str], ...] = (
    ("螺旋のアートを作って", "螺旋", "螺旋のアート"),
    ("フローアートを作って", "フロー", "フローアート"),
    ("猫のGIFを作って", "猫", "猫のGIF"),
    ("鳥のアニメGIFを作って", "鳥", "鳥のアニメGIF"),
)


@dataclass(frozen=True)
class ArtGifTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    return SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="art-gif-title-")) / "s")))


def evaluate_art_gif_title_no_kind_echo() -> ArtGifTitleResult:
    service = _service()
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

    for request, subject, doubled in _NAMED:
        a = answer(request)
        # The subject stands alone in the title, and the kind is not echoed into
        # it (no 「<subject><kind>」 in the summary).
        add(f"「{subject}」" in a and f"「{doubled}」" not in a,
            f"{request!r}: title echoes the kind word: 「{a[:60]}」")

    # A bare kind word still produces a handled artifact (fallback title).
    bare = service.chat("アートを作って") or {}
    handled = ((bare.get("creation") or {}).get("outcome") or {}).get("handled")
    add(bool(handled) and "作りました" in str(bare.get("answer") or ""),
        "a bare 「アートを作って」 was not handled")

    # Non-regression: model3d already strips the kind word.
    m3d = answer("魚の3Dモデルを作って")
    add("「魚」" in m3d and "「魚の3Dモデル」" not in m3d,
        f"model3d title regressed: 「{m3d[:60]}」")

    total = len(_NAMED) + 2
    return ArtGifTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ArtGifTitleResult", "evaluate_art_gif_title_no_kind_echo"]
