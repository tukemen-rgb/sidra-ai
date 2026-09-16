"""C-1893: a completion must name a number somebody can still measure.

The rule this pins is narrow on purpose, and the narrowing is measured:
refusing every added line that names an unresolvable metric - which is what
the item proposed - refuses the push that *files* a new metric, and both
items filed on 2026-09-16 were of that shape.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from sidra_ai.evals.board_metric_names_resolve import (
    evaluate_board_metric_names_resolve,
)

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_metric_names.py"
GATE = ROOT / "scripts" / "check_before_push.sh"


def _load():
    spec = importlib.util.spec_from_file_location("_check_metric_names", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_metric_names"] = module
    spec.loader.exec_module(module)
    return module


def test_all_three_cases_hold():
    result = evaluate_board_metric_names_resolve()
    assert result.checks_passed == 3, result.failures
    assert result.passed


def test_the_receipt_is_where_the_claim_is():
    """The first backticked identifier on a completion line, not the brief."""

    check = _load()
    line = (
        "- [x] 完了 2026-09-16 14:21 UTC 辛口クリエイター"
        "（`creation_flash_fades_in_real_time` **新設 10**、判定器 exit 0） "
        "**C-1892: 閃光。**"
    )
    assert check.claimed_metric(line) == "creation_flash_fades_in_real_time"


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] **C-0001: これから作る。** → 動かす数字: `not_built_yet` （新設）",
        "- [~] 作業中 2026-09-16 16:08 UTC ループA **C-0002: 確保した。**",
        "- [記録] 未修正・計測のみ 2026-01-01 ループZ（`never_built` は作らないと決めた）",
    ],
)
def test_only_a_completion_is_read_as_a_claim(line):
    """A filing, a claim and a record are not 「数字が動いた」 claims.

    This is the case the item's literal rule (A) would have broken: a brief
    naming a metric that does not exist yet is how every new number is
    proposed, and refusing it refuses the filing.
    """

    assert _load().claimed_metric(line) is None


def test_a_script_path_is_not_a_metric_name():
    """`verify_gate_recall.py` and `tests/...py` are quoted in receipts too."""

    check = _load()
    line = (
        "- [x] 完了 2026-01-01 00:00 UTC ループZ（`living_metric_name` **1→2**、"
        "`verify_gate_recall.py` exit 0、`tests/test_product_metrics.py` 緑） "
        "**C-0003: 済んだ。**"
    )
    assert check.claimed_metric(line) == "living_metric_name"


def test_the_two_narratives_are_not_evidence():
    """A name may not resolve to the sentence that named it."""

    check = _load()
    assert "docs/BACKLOG.md" in check.NOT_EVIDENCE
    assert "docs/LOOP_LOG.md" in check.NOT_EVIDENCE


def test_the_haystack_is_not_one_script():
    """Five names the filer first called missing live in other judges."""

    check = _load()
    haystack = check.repository_names(ROOT)
    assert haystack
    for name in ("answerable_direct", "boss_q_answered", "game_production"):
        assert name in haystack, name


def test_the_gate_runs_it():
    """Wired into check_before_push.sh, not only available to run by hand."""

    assert "check_metric_names.py" in GATE.read_text(encoding="utf-8")


def test_this_tree_passes_its_own_check():
    done = subprocess.run(
        [sys.executable, str(CHECK)], cwd=ROOT, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
