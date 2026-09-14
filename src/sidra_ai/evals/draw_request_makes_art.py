"""Does a request for a picture reach the generator that makes pictures?

C-1804. 「絵を描いて」「絵を作って」「イラストを描いて」 were declined with 「この形式は
作れません。いま作れるのは アート・スライド・…」 - a refusal that lists, inside its own
sentence, the thing the asker wanted. 「アートを作って」 built the very same generative
art. The product could make it; only the word was missing.

This is C-1480 from the other side. That item added "wallpaper"/"abstract art"
because 「壁紙」「アート」 routed here and the English did not, "so an English
speaker was declined for what SIDRA can make" - and it assumed the Japanese
list was already whole. 「絵」 and 「イラスト」, the ordinary Japanese for the
thing, were not in it.

C-1606 sent 「絵を描いて」 to that decline on purpose and recorded it as the
honest outcome. The decline is where the reasoning breaks: a request naming no
subject is exactly what this generator makes. A request that DOES name one is
a different question - the art is abstract, 「魚の絵」 cannot draw a fish - and
is deliberately not touched here; it already carries its own disclosure.

Both directions, because a routing change is only safe if what used to go
elsewhere still does: the latest-match rule has to keep 絵柄→GIF, 絵を描くゲーム
→GAME, 絵本のようなスライド→DECK, and a question about 絵文字 a question.

Driven through the real ``SidraService.chat``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.evals.scratch import scratch_dir

_DECLINED = "この形式は作れません"
_ART = "ジェネラティブアート"
_COLOR_NOTE = "色は今の配色に反映していません"


@dataclass(frozen=True)
class DrawRequestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(scratch_dir(prefix="draw-art-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def evaluate_draw_request_makes_art() -> DrawRequestResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    svc = _service()

    def answer(message: str) -> str:
        return svc.chat(message).get("answer") or ""

    # --- (A-C) the user's word reaches the generator ---------------------
    for request in ("絵を描いて", "絵を作って", "イラストを描いて"):
        said = answer(request)
        add(_DECLINED not in said and _ART in said,
            f"A: 「{request}」 did not make art: {said[:60]}")

    # --- (D) ...and the honesty that route already had is not lost -------
    # A colour cannot be honoured by a fixed palette. Routing a colour
    # request into the generator without that note would trade one silence
    # for another (C-1271/C-1272).
    coloured = answer("青い絵を描いて")
    add(_ART in coloured and _COLOR_NOTE in coloured,
        f"D: 「青い絵を描いて」 lost the colour note: {coloured[:80]}")

    # --- (E) a request with no colour must NOT carry the note ------------
    plain = answer("絵を描いて")
    add(_COLOR_NOTE not in plain,
        "E: a request naming no colour was given the colour note anyway")

    # --- (F-I) what belonged elsewhere still goes there -------------------
    # The latest-match rule decides these; 絵 sits earlier than each of the
    # cues that should win. Without this half, adding a keyword that
    # swallowed every neighbouring kind would score full marks above.
    gif = answer("魚の絵柄のGIFを作って")
    add("GIF" in gif and _ART not in gif, f"F: 絵柄 GIF became art: {gif[:60]}")

    game = answer("絵を描くゲームを作って")
    add(_ART not in game, f"G: 絵を描くゲーム became art: {game[:60]}")

    deck = answer("絵本のようなスライドを作って")
    add(_ART not in deck, f"H: 絵本のスライド became art: {deck[:60]}")

    question = answer("絵文字について教えて")
    add(_ART not in question, f"I: a question about 絵文字 built art: {question[:60]}")

    # Derived, never a literal: a hard-coded denominator that drifts from the
    # checks lets a failing check report a perfect score (measured across the
    # 157 evals 2026-09-14 - none had drifted, but none was protected either).
    return DrawRequestResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = ["DrawRequestResult", "evaluate_draw_request_makes_art"]
