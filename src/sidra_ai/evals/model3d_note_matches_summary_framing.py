"""Does the 3D preview note frame the fallback the way the chat summary does?

C-1805. ``generate_model3d`` discloses the fish default on the preview page
(C-1283), but the note bracket-quoted the request: ``依頼「{title}」に合う形状が
無かったため``. For a bare 「3Dモデルを作って」 the title falls back to the default
shape's own name 「魚」, so the note read 「依頼「魚」に合う形状が無かったため、既定の
「魚」で表示しています」 - self-contradictory (asked for 魚, 魚 unavailable, showing
魚) and attributing a 魚 request the user never made. The chat summary
(``model3d_job``) frames the same fallback without a subject - 「依頼に合う形状が
無かったので、既定の…」 - so the forwardable preview was less honest than the chat.

The fix drops the bracket quote, matching the summary's subject-less framing.
The subject survives in ``<title>``/``<h1>``, the default disclosure and the
shape list are unchanged, and a named shape still carries no note. This is the
3D sibling of C-1801 (the art note's identical bracket quote).

The checks read ``generate_model3d(request).preview_html`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.models3d import generate_model3d

_NOTE_MARK = '<p id="shape-note">'


@dataclass(frozen=True)
class Model3DNoteFramingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _note(html: str) -> str:
    if _NOTE_MARK not in html:
        return ""
    return html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0]


def evaluate_model3d_note_matches_summary_framing() -> Model3DNoteFramingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A bare request: the title falls back to the default shape name, so the old
    # note read 「依頼「魚」…既定の「魚」」 - the defect case.
    bare = generate_model3d("3Dモデルを作って")
    bare_note = _note(bare.preview_html)
    # A: subject-less framing, matching the chat summary.
    add("依頼に合う形状が無かった" in bare_note, "bare note lost the subject-less framing")
    # B: no self-contradicting false attribution of a 魚 request.
    add("依頼「魚」" not in bare_note, "bare note still quotes 依頼「魚」 (self-contradiction)")
    # C: the default disclosure is unchanged.
    add("既定の「魚」" in bare_note, "bare note no longer names the fish default")

    # A named-but-unavailable subject: quoting it read as accurate, but the
    # summary is subject-less, so the artifact should match.
    dragon = generate_model3d("ドラゴンの3Dモデルを作って")
    dragon_note = _note(dragon.preview_html)
    # D: no bracket quote of the subject in the note.
    add("依頼「ドラゴン」" not in dragon_note, "dragon note still bracket-quotes 依頼「ドラゴン」")
    # E: the subject is not lost - it stays in the title, and the default is
    #    still disclosed.
    add("<h1>ドラゴン</h1>" in dragon.preview_html and "既定の「魚」" in dragon_note,
        "dragon subject dropped from title or default no longer disclosed")

    # F: a named, available shape carries no note (no false positive).
    boat = generate_model3d("舟の3Dモデルを作って")
    add(_NOTE_MARK not in boat.preview_html, "a named shape wrongly carries a fallback note")

    total = 6
    return Model3DNoteFramingResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3DNoteFramingResult",
    "evaluate_model3d_note_matches_summary_framing",
]
