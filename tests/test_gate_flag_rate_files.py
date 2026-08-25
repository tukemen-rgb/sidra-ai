"""The blend is the headline; the files alone are the number people mean.

Measured 2026-08-23: files 44/244 = 18.0%, commit messages 0/200 = 0.0%,
blended 44/444 = 9.9%. Two hundred uniformly clean messages were halving the
rate, so "9.9% of this repository cannot be indexed" was answering a question
nobody had asked - the documents are refused at nearly twice that.

The owner's decision (2026-08-25, option (c)) was to report both rather than
redefine the existing one. These tests hold that shape: the blended ceiling is
untouched, the files get a ceiling of their own, breaking either one fails,
and the report says out loud what each rate is counted over.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_gate_regression_files_under_test",
        REPO_ROOT / "scripts" / "check_gate_regression.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def judge():
    return _load()


# ---------------------------------------------------------------- ceilings


def test_the_blended_ceiling_is_untouched(judge) -> None:
    """Option (c) was "add a number", not "move the existing one"."""

    assert judge.MAX_FLAG_RATE == 0.13


def test_the_file_ceiling_sits_above_the_higher_observation(judge) -> None:
    """18.0% was measured once; a ceiling under it would fail on arrival.

    The upper bound is here so the ceiling cannot be quietly widened into
    something that no longer catches anything.
    """

    assert judge.MAX_FILE_FLAG_RATE > 0.18
    assert judge.MAX_FILE_FLAG_RATE <= 0.25


def test_a_healthy_run_reports_no_failures(judge) -> None:
    assert judge._ceiling_failures(0.09, 0.138) == []


def test_the_blended_ceiling_still_fails_on_its_own(judge) -> None:
    failures = judge._ceiling_failures(0.20, 0.10)

    assert len(failures) == 1
    assert "blended" in failures[0]


def test_the_files_can_fail_while_the_blend_looks_healthy(judge) -> None:
    """The regression the split exists to catch.

    Files at 30% with a blend at 12% is not a hypothetical shape: the messages
    are half the corpus and never flagged, so a doubling of file refusals
    lands inside the old ceiling.
    """

    failures = judge._ceiling_failures(0.12, 0.30)

    assert len(failures) == 1
    assert "files" in failures[0]


def test_both_are_named_when_both_break(judge) -> None:
    failures = judge._ceiling_failures(0.40, 0.60)

    assert len(failures) == 2


# ------------------------------------------------------------------ report


def test_the_report_shows_each_rate_with_its_denominator(judge, capsys) -> None:
    """A percentage on its own is what hid the dilution in the first place.

    This runs the real walk over this repository - the same thing CI runs -
    because a report tested against a stub would not catch the walk and the
    reporting disagreeing about what was counted.
    """

    verdict = judge.main()
    if verdict == judge.EXIT_CANNOT_JUDGE:
        pytest.skip("shallow clone: the flag rate cannot be judged here")
    assert verdict == 0

    out = capsys.readouterr().out
    files = re.search(r"files\s+:\s+(\d+)/(\d+) = ([\d.]+)%", out)
    commits = re.search(r"commit messages:\s+(\d+)/(\d+) = ([\d.]+)%", out)
    blended = re.search(r"blended\s+:\s+(\d+)/(\d+) = ([\d.]+)%", out)

    assert files and commits and blended, out

    # The same refusals, three denominators. If these ever stop adding up the
    # populations have started overlapping or something is counted twice.
    assert int(files.group(1)) + int(commits.group(1)) == int(blended.group(1))
    assert int(files.group(2)) + int(commits.group(2)) == int(blended.group(2))

    assert "The blend is what the real index holds" in out, (
        "the report has to explain the difference, not just print it"
    )


def test_the_detector_table_prints_names_and_counts_only(judge, capsys) -> None:
    """Same rule as the rest of this instrument: never the matched text.

    A false-positive report that quoted what it matched would publish the
    secrets and personal data it is counting. The table is the one place that
    could drift into doing so, because it is generated per finding.
    """

    verdict = judge.main()
    if verdict == judge.EXIT_CANNOT_JUDGE:
        pytest.skip("shallow clone: the flag rate cannot be judged here")

    out = capsys.readouterr().out
    assert "top detectors:" in out
    # The table runs to the blank line before the verdict.
    rest = out.split("top detectors:", 1)[1].lstrip("\n").splitlines()
    table = []
    for line in rest:
        if not line.strip():
            break
        table.append(line)
    assert table, "the detector table is empty"
    for line in table:
        assert re.fullmatch(r"\S+\s+\d+", line.strip()), (
            f"the detector table printed something other than a name and a "
            f"count: {line!r}"
        )
