"""Is the 3D preview written in the language it was asked in?

C-1953, the third page of the family C-1951 opened (deck) and C-1952
continued (art). C-1930 and C-1932 put this generator's **summary** into
the language of the request; the preview it points at stayed Japanese - the
shape-default note, the colour note, the count note, the canvas fallback
(§36's descriptive identification, the one sentence a screen reader is
handed) and the note saying to keep the .obj and .mtl together.

The notes are why it matters. They exist so the page admits what it did not
do - the default shape (C-1283, C-1805), the ignored colour (C-1818), the
count (C-1832). An admission the reader cannot read is not one.

**A correction this item carries.** C-1952 named "game, model3d and gif" as
what was left. Measured: **gif has no page at all** - the artifact is the
``.gif`` itself - so there were two, not three. The board says so rather
than quietly shipping the smaller number.

Rules, read off the artifact (C-1640): no Japanese outside the operator's
own title, ``<html lang>`` telling the truth, every note the request earns
still present, and the Japanese page still Japanese - as a GUARD, never as
half the score (C-1939).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Asks that earn the same notes on both sides: no shape named, and a colour
#: named. Two notes, not three, and the reason is a defect this item found
#: but does not fix - **the count is heard in Japanese and not in English**.
#: Measured 2026-09-18 through ``models3d.count_note``: 「3 つ」 and 「…を 3 つ
#: 作って」 both produce the admission, while "make 3 3d models of an owl",
#: "make 3 red 3d models of an owl" and "make three 3d models" produce
#: nothing at all. So an English request for three models quietly gets one,
#: with no word of it, where a Japanese one is told.
#:
#: That belongs to the family C-1934/C-1935 worked (「英語の数が聞こえる」),
#: not to this page's language, and it is filed as its own item rather than
#: smuggled in here. Using a three-note ask would have made this judge fail
#: for a defect it is not measuring - and dropping the count from the ask is
#: only honest because the gap is written down where the next reader meets
#: it.
ENGLISH_ASK = "make a red 3d model of an owl"
JAPANESE_ASK = "赤いふくろうの 3D モデルを作って"


@dataclass(frozen=True)
class Model3DPageResult:
    sides_right: int
    sides_total: int = 2
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_model3d_page_matches_the_language_asked() -> Model3DPageResult:
    from sidra_ai.creation.models3d import generate_model3d

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    japanese = generate_model3d(JAPANESE_ASK)
    japanese_notes = sum(
        1
        for tag in ("shape-note", "color-note", "count-note")
        if f'id="{tag}"' in japanese.preview_html
    )

    english = generate_model3d(ENGLISH_ASK)
    page = english.preview_html
    body = page.replace(english.title, " ")
    leftovers = [line for line in body.splitlines() if _JAPANESE.search(line)]
    declared = re.search(r'<html[^>]*\blang="([a-z-]+)"', page)
    notes = sum(
        1 for tag in ("shape-note", "color-note", "count-note") if f'id="{tag}"' in page
    )
    problems: list[str] = []
    if leftovers:
        problems.append(f"{len(leftovers)} lines are still Japanese")
    if not declared or declared.group(1) != "en":
        problems.append(
            f"the page declares lang={declared.group(1) if declared else 'nothing'}"
        )
    # Parity, not a literal: the English page must carry exactly the notes
    # the Japanese page carries for the same request. When the count parser
    # learns English, both sides go to three together and this check needs no
    # edit - and until then, "translating" a note by deleting it fails here.
    if notes != japanese_notes:
        problems.append(
            f"{notes} notes against {japanese_notes} on the Japanese page"
        )
    if "<canvas" not in page or "3D preview" not in page:
        problems.append("the canvas fallback sentence is gone")
    readings.append(f"EN ja-lines={len(leftovers)} notes={notes}")
    if problems:
        failures.append("English: " + "; ".join(problems))
    else:
        right += 1

    jp = japanese.preview_html
    guard: list[str] = []
    declared_ja = re.search(r'<html[^>]*\blang="([a-z-]+)"', jp)
    if not declared_ja or declared_ja.group(1) != "ja":
        guard.append("the Japanese page stopped declaring Japanese")
    for phrase in ("3D プレビュー", "既定の「魚」", "固定の配色"):
        if phrase not in jp:
            guard.append(f"「{phrase}」 is gone from the Japanese page")
    readings.append(
        f"JA ja-lines={len([l for l in jp.splitlines() if _JAPANESE.search(l)])}"
    )
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))
    else:
        right += 1

    return Model3DPageResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "Model3DPageResult",
    "evaluate_model3d_page_matches_the_language_asked",
]
