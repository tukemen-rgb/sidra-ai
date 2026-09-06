"""C-1271: art admits when a requested colour was not applied.

The palette is fixed to the GAMEYARD brand (cyan on dark), so 「青い海のアート」 was
drawn cyan and pink with no word that the colour was ignored. The summary now
says the colour was not applied and names the fixed palette; a request naming no
colour draws no such note. The palette itself is unchanged.
"""

from __future__ import annotations

from sidra_ai.creation.art import names_color
from sidra_ai.evals.art_color_named_honest import evaluate_art_color_named_honest


def test_art_color_named_honest_eval_passes():
    result = evaluate_art_color_named_honest()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 11


def test_names_color_spots_a_colour_request():
    assert names_color("青い海のアートを作って")
    assert names_color("赤い炎のアートを作って")
    assert names_color("緑の森のアートを作って")
    assert names_color("ブルーの抽象アートを作って")
    assert names_color("a red abstract piece")


def test_names_color_does_not_fire_on_unrelated_words():
    # no colour intended - these must not read as a colour request
    assert not names_color("アートを作って")
    assert not names_color("フローのアートを作って")
    assert not names_color("金曜のアートを作って")  # 金曜 is Friday, not gold
    assert not names_color("赤字のレポート")  # 赤字 is a deficit, not "red"


def test_colour_note_only_when_a_colour_is_named():
    import tempfile
    from pathlib import Path

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    svc = SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="art-c-"))/"sidra")))
    colored = (svc.chat("青い海のアートを作って") or {}).get("answer") or ""
    plain = (svc.chat("フローのアートを作って") or {}).get("answer") or ""
    assert "色は今の配色に反映していません" in colored
    assert "シアン" in colored
    assert "色は今の配色に反映していません" not in plain
