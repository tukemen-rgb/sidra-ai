"""Motion can be reduced from inside the page (§4 GAG 増築, C-1393).

REDUCED read only the OS's prefers-reduced-motion; GAG's "Provide an
option to turn off / hide background movement" (intermediate, Cognitive
AND Vision) had no in-page answer. Now the tuning panel's 「動きを減らす」
flag ORs into REDUCED on the next load - it can only raise the OS's
promise, never lower it.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.tuning import motion_probe


def _drive(*, seeded: bool) -> dict:
    html = generate_game("ゲームを作って", template="catch").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=motion_probe(script, template="catch", seeded=seeded),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_bare_page_keeps_full_motion_and_the_switch_writes() -> None:
    got = _drive(seeded=False)
    assert not got["reduced"], "the bare page already reduces"
    assert got["frameBeat"] == 1, "FRAME does not beat on the bare page"
    assert got["wrote"] and got["storedFlag"], "the switch never reaches storage"
    assert got["reloads"] == 1, "the change never asks for the reload"


def test_the_stored_flag_reduces_the_next_load() -> None:
    got = _drive(seeded=True)
    assert got["reduced"], "the stored flag never reduces the next load"
    assert got["frameBeat"] == 0, "FRAME still beats under the stored flag"
