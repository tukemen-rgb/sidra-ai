"""Does the 3D preview page disclose that a requested colour was not applied?

C-1818. ``model3d_job`` returns the preview HTML as the primary artifact, so the
page is what a user reopens or forwards. A request that names a colour
(「赤い魚の3Dモデル」) is titled 「赤い魚」 over a fixed-palette mesh that is not red.
The chat summary says the colour was not applied (C-1272, via ``names_color``),
but the preview HTML carried no such note - so the forwarded page claimed 「赤い
魚」 with nothing to say the colour is not there, less honest than the chat.

The preview now carries the colour caveat under the title whenever the request
named a colour, the sibling of the shape-default note (C-1805) and the .mtl
colour note (C-1784). A request that names no colour gets no note.

The checks read the real ``generate_model3d`` preview HTML.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.models3d import generate_model3d

_COLOR_MARK = "反映していません"
_NOTE_MARK = '<p id="shape-note">'


@dataclass(frozen=True)
class Model3DColorNoteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_model3d_preview_discloses_color_not_applied() -> Model3DColorNoteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A named colour on a named shape: the preview discloses the colour was not
    # applied, and keeps the subject in the title.
    red_fish = generate_model3d("赤い魚の3Dモデルを作って")
    add(_COLOR_MARK in red_fish.preview_html,
        "a colour request is not disclosed as unapplied in the preview")
    add("<h1>赤い魚</h1>" in red_fish.preview_html,
        "the coloured subject was dropped from the preview title")

    # A named colour on the default (unnamed) shape: both notes appear - the
    # shape-default note (C-1805) and the colour caveat.
    blue_cat = generate_model3d("青い猫の3Dモデルを作って")
    add(_COLOR_MARK in blue_cat.preview_html,
        "colour caveat missing when the shape also defaulted")
    add("既定の「魚」" in blue_cat.preview_html,
        "the C-1805 shape-default note regressed")

    # A request with no colour gets no colour caveat (no false positive).
    plain_boat = generate_model3d("舟の3Dモデルを作って")
    add(_COLOR_MARK not in plain_boat.preview_html,
        "a colourless request wrongly shows the colour caveat")

    # The caveat names the fixed palette, not a fabricated colour, and carries
    # no digit (the disclosure must not itself invent a figure).
    note = ""
    if '<p id="color-note">' in red_fish.preview_html:
        note = red_fish.preview_html.split('<p id="color-note">', 1)[1].split("</p>", 1)[0]
    add("固定の配色" in note and not any(ch.isdigit() for ch in note),
        f"the colour caveat is malformed or carries a digit: {note!r}")

    total = 6
    return Model3DColorNoteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "Model3DColorNoteResult",
    "evaluate_model3d_preview_discloses_color_not_applied",
]
