"""A revision that changes nothing must not touch the history.

C-1817, next door to C-1816. 「難しくして」 at maximum difficulty already refused
to claim a change - 「変更なし（すでにその設定です）」 - but wrote a version anyway,
because the file was written before the comparison that finds there is nothing
to record. Two such asks left two identical versions, and 「元に戻して」 stepped
through them saying 「一つ前の版に戻しました」 while nothing moved: C-1816's
symptom by another door.

Undo is excluded on purpose - it always restores something - and that
exclusion is asserted here, because breaking it would undo C-1816.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_the_whole_sequence_is_driven() -> None:
    from sidra_ai.evals.no_change_writes_no_version import (
        evaluate_no_change_writes_no_version,
    )

    result = evaluate_no_change_writes_no_version()
    assert result.passed, result.failures
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_the_no_change_reply_does_not_promise_an_old_version() -> None:
    """There is nothing to keep an old version OF, so it must not say so.

    The ordinary revision sign-off ends 「旧版のファイルもそのまま残っています」.
    Printing that after writing nothing would describe a file that was never
    made.
    """

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.evals.scratch import scratch_dir

    svc = SidraService(Settings(data_dir=str(Path(scratch_dir(prefix="nc-t-")) / "s")))
    svc.chat("レースゲームを作って")
    svc.chat("さっきのゲームを難しくして")
    said = svc.chat("さっきのゲームを難しくして").get("answer") or ""

    assert "変更なし" in said
    assert "新しい版は作っていません" in said
    assert "旧版のファイルもそのまま残っています" not in said
