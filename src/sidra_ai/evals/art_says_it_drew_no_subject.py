"""Does the art say it did not draw the subject the asker named?

C-1806. These two patterns - a flow field and orbits - depict nothing. A
request naming a subject gets abstract art titled with the asker's own word:
「猫の絵を描いて」 produced a page titled 「猫」 over a flow field, and neither the
summary nor the page said no cat was drawn. The title makes the promise, and
whoever the file is forwarded to reads the title first (C-1793).

The sibling generators already say it. GIF: 「依頼に合う絵柄が無かったので、既定の
「魚」にしました」 (C-1258). 3D has ``model3d_shape_default_honest``. Art had a
note for the pattern default (C-1256) and one for a colour it could not honour
(C-1271/C-1272, on the page since C-1786) - but none for the subject.

``art_job`` had decided that in writing: "Not a claim the subject can't be
drawn". That was written for a product where 「猫の絵を描いて」 never arrived - it
was declined - and C-1804 widened the cues so that it does.

Both directions throughout, because a note that fires every time is one nobody
reads (measured on the colour-vision caveat: 118 empty warnings would bury it).
A colour is not a subject - it has its own note - and neither is a pattern
word, since 「波の絵」 names one of the two patterns rather than a thing to draw.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir

_NOTE = "題材は描いていません"
_COLOR_NOTE = "色は今の配色に反映していません"


@dataclass(frozen=True)
class ArtSubjectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    return SidraService(Settings(data_dir=str(Path(scratch_dir(prefix="art-subj-")) / "s")))


def evaluate_art_says_it_drew_no_subject() -> ArtSubjectResult:
    import re

    from sidra_ai.creation.art import generate_art

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def page_notes(request: str) -> str:
        html = generate_art(request).html
        return " ".join(re.findall(r'<p class="note">(.*?)</p>', html, re.S))

    svc = _service()

    def summary(request: str) -> str:
        return svc.chat(request).get("answer") or ""

    # --- (A) a named subject is disclosed, in the summary AND on the page --
    # The page half is the one that matters most: it is the artifact that
    # gets forwarded, and it is the half that was silent for colour until
    # C-1786 found the same asymmetry.
    for request in ("猫の絵を描いて", "車のイラストを描いて", "猫の壁紙を作って"):
        add(_NOTE in summary(request), f"A: 「{request}」 summary does not say the subject went undrawn")
        add(_NOTE in page_notes(request), f"A: 「{request}」 page does not say the subject went undrawn")

    # --- (B) ...and a request naming none is not given the note -----------
    # Without this half a generator that always apologised would score full
    # marks, and the note would stop being read.
    for request in ("絵を描いて", "アートを作って", "イラストを描いて"):
        add(_NOTE not in summary(request), f"B: 「{request}」 named no subject but was told one went undrawn")
        add(_NOTE not in page_notes(request), f"B: 「{request}」 page carries an unearned subject note")

    # --- (C) a colour is not a subject ------------------------------------
    # It has carried its own note since C-1271; reporting it twice would be
    # two apologies for one fact.
    coloured = summary("青い絵を描いて")
    add(_COLOR_NOTE in coloured, "C: the colour note was lost")
    add(_NOTE not in coloured, "C: a colour was counted as a subject and apologised for twice")

    # --- (D) a pattern word is not a subject ------------------------------
    # 「波」 and 「円」 name these very patterns, so the pattern note answers
    # them and a subject note would contradict it.
    for request in ("波の絵を描いて", "円のアートを作って"):
        add(_NOTE not in summary(request), f"D: 「{request}」 names a pattern, not a subject")

    # --- (E) the subject is not quoted back into the page -----------------
    # A recovered subject is a fragment of the request, not a phrase worth
    # repeating; the sibling note in gifs quotes nothing either.
    add("「猫」は" not in page_notes("猫の絵を描いて"),
        "E: the note quotes the recovered subject back at the reader")

    return ArtSubjectResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["ArtSubjectResult", "evaluate_art_says_it_drew_no_subject"]
