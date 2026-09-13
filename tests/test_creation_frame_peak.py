"""山場（p95）の仕事量にも天井がある (§32 学び 4, C-1783).

C-1752 put a ratchet on the *median* frame. §32's own reading of its table
says the median is not where the risk is:

    p95 と中央値が大きく離れる型（fishing 33→112・shooter 147→245）は、
    山場で仕事が 3 倍以上になる。§1 の juice がそこに乗っているので、
    粒子を増やす変更はこの列を見てから。

Nobody was watching that column. The probe had been returning ``p95`` in the
same JSON since it was written; the judge read ``median`` and dropped it.

The gap this closes is specific. Juice - particles, bursts, shake - costs
nothing on a quiet frame and a great deal on the frame of the hit. Out of
1200 frames a few dozen are loud, so a change that doubles the peak moves
the median hardly at all and walks past a median-only ceiling.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.framecost import (
    FRAME_MEDIAN,
    FRAME_P95,
    count_probe,
    frame_ceiling,
    frame_peak_ceiling,
)
from sidra_ai.creation.games import TEMPLATES, generate_game

#: The two templates §32 named as spiking hardest, plus one that does not
#: (adventure is 530 -> 532). Pinning a flat one keeps the test honest about
#: what the column does and does not say.
SAMPLE = ("fishing", "shooter", "adventure")


def _run(template: str, frames: int = 1200) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the frames")
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S)
    assert body is not None
    probe = subprocess.run(
        ["node", "-"],
        input=count_probe(body.group(1), frames=frames),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_peak_table_covers_every_template() -> None:
    """A template missing here has no ceiling on its loudest frames."""

    assert sorted(FRAME_P95) == sorted(TEMPLATES)


def test_every_peak_ceiling_is_above_its_measurement() -> None:
    for template, peak in FRAME_P95.items():
        assert frame_peak_ceiling(template) > peak, template


def test_the_peak_is_never_below_the_middle() -> None:
    """p95 < median would mean the table was built from a different run."""

    for template, peak in FRAME_P95.items():
        assert peak >= FRAME_MEDIAN[template], (template, peak)


@pytest.mark.parametrize("template", SAMPLE)
def test_the_loud_frames_stay_under_their_ceiling(template: str) -> None:
    seen = _run(template)
    assert seen["frames"] >= 500, seen
    assert seen["p95"] <= frame_peak_ceiling(template), (
        seen,
        frame_peak_ceiling(template),
    )


@pytest.mark.parametrize("template", SAMPLE)
def test_the_peak_ceiling_is_still_about_this_page(template: str) -> None:
    """Without this, a ceiling of a hundred thousand is green forever."""

    seen = _run(template)
    assert seen["p95"] * 2 >= FRAME_P95[template], (seen["p95"], FRAME_P95[template])


def test_the_median_alone_would_not_have_caught_the_spike() -> None:
    """The reason this file exists, stated as an assertion.

    fishing's peak is more than three times its middle, and sits above the
    ceiling the *median* ratchet enforces - so a change that lifted the loud
    frames to that shape again would pass a median-only judge, because the
    median never moved.
    """

    assert FRAME_P95["fishing"] > FRAME_MEDIAN["fishing"] * 3
    assert FRAME_P95["fishing"] > frame_ceiling("fishing")
