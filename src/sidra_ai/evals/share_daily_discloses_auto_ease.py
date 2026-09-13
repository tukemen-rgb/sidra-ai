"""Does a shared *daily* line disclose that the board was auto-eased?

C-1777. The daily stamp 「今日の{name} {date}」 is safe to paste because it names
a challenge everybody got (§8 事実 7). C-1768 kept that true against hand-set
tuning: ``shareTuned()`` names any panel axis the player moved. But it never saw
the *other* runtime source of a diverged board - adapt's auto-ease (three losses
buy one easier rung, C-1402), which is not a hand-set value and is applied at
load by ``adaptSpeed``. So a daily run played on the eased board was pasted with
the same 「今日の…{date}」 stamp as a clean run, silently breaking the "same
challenge" premise and misleading the recipient, not just the player.

``shareText`` now reads ``ADAPT_EASED`` (set when ``adaptSpeed`` stepped the
speed down at load, and still true after the win that clears the streak) and
adds 「難度自動緩和」 to the daily disclosure. The checks play the real page in
node for four boards and read the copied line.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.share import probe_source

_TEMPLATE = "adventure"  # its board comes from the seed, so the daily stamp is real
_REQUEST = "ゲームを作って"
_STAMP = "2026-09-03"
_EASE_MARK = "難度自動緩和"
_DAILY = "今日の"


def _line(stored: dict) -> str:
    art = generate_game(_REQUEST, template=_TEMPLATE)
    script = re.search(r"<script>(.*?)</script>", art.html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(script, stored=stored, stamp=_STAMP),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run.returncode != 0:
        raise ValueError(run.stderr.strip()[:200])
    return json.loads(run.stdout.strip().splitlines()[-1])["facts"]["text"] or ""


def _daily(**extra) -> dict:
    return {f"sidra.tune.{_TEMPLATE}": {"daily": True, **extra}}


@dataclass(frozen=True)
class ShareAutoEaseResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_share_daily_discloses_auto_ease() -> ShareAutoEaseResult:
    total = 6
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        return ShareAutoEaseResult(False, 0, total, ("node is unavailable",))

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    key = f"sidra.streak.{_TEMPLATE}"
    eased_daily = _line({**_daily(), key: "3"})   # daily board, auto-eased at load
    normal_daily = _line(_daily())                # daily board, nothing eased
    manual_daily = _line(_daily(speed=1.2))       # daily board, hand-set speed
    eased_private = _line({key: "3"})             # eased, but not the daily board

    # --- the fix: the auto-ease is named on the shared daily line ---------
    add(_EASE_MARK in eased_daily,
        f"A: an auto-eased daily is shared without disclosure: {eased_daily!r}")
    # --- the daily premise itself is intact (disclosure added, not swapped) -
    add(_STAMP in eased_daily and _DAILY in eased_daily,
        f"B: the eased daily lost its date/stamp: {eased_daily!r}")
    # --- no false positive on a clean daily ------------------------------
    add(_EASE_MARK not in normal_daily,
        f"C: a clean daily wrongly claims an auto-ease: {normal_daily!r}")
    # --- hand-set tuning is still disclosed, and is not the auto-ease -----
    add("（" in manual_daily and _EASE_MARK not in manual_daily,
        f"D: the manual-tune disclosure regressed or mislabels: {manual_daily!r}")
    # --- a private eased board makes no standardness claim ----------------
    add(_STAMP not in eased_private and _EASE_MARK not in eased_private,
        f"E: a private eased board carries a daily/ease claim: {eased_private!r}")
    # --- the disclosure sits within the daily stamp, not stray -----------
    add(_EASE_MARK in eased_daily and _DAILY in eased_daily
        and eased_daily.index(_EASE_MARK) > eased_daily.index(_DAILY),
        f"F: the auto-ease disclosure is misplaced: {eased_daily!r}")

    return ShareAutoEaseResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ShareAutoEaseResult", "evaluate_share_daily_discloses_auto_ease"]
