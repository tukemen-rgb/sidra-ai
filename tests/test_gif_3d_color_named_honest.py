"""C-1272: GIF and 3D admit when a requested colour was not applied.

C-1271 gave the art generator this honesty; the GIF and 3D generators had the
same gap - 「青いGIFを作って」/「青い3Dモデルを作って」 drew the usual palette and
quoted the colour back. Both now carry the note when a colour is named and none
when it is not, reusing art.names_color. The palettes are unchanged.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.gif_3d_color_named_honest import (
    evaluate_gif_3d_color_named_honest,
)

_MARKER = "色は今の配色に反映していません"


def _svc():
    return SidraService(Settings(data_dir=str(Path(tempfile.mkdtemp(prefix="g3c-")) / "sidra")))


def test_gif_3d_color_named_honest_eval_passes():
    result = evaluate_gif_3d_color_named_honest()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_gif_colour_note_only_when_a_colour_is_named():
    svc = _svc()
    colored = (svc.chat("青いGIFを作って") or {}).get("answer") or ""
    plain = (svc.chat("魚のGIFを作って") or {}).get("answer") or ""
    assert _MARKER in colored
    assert _MARKER not in plain


def test_model3d_colour_note_only_when_a_colour_is_named():
    svc = _svc()
    colored = (svc.chat("青い3Dモデルを作って") or {}).get("answer") or ""
    plain = (svc.chat("魚の3Dモデルを作って") or {}).get("answer") or ""
    assert _MARKER in colored
    assert _MARKER not in plain
