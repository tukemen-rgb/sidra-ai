"""The answerable-rate floor: a measurement that finally refuses.

`docs/OUTCOMES.md` recorded 44.4% answerable and nothing enforced it, which is
the state the false-positive rate was in before `check_gate_regression.py`
existed - a habit, not a control. These tests cover the parts of the floor
that can be exercised without the four external checkouts: the refusals, the
comparison logic, and the values of the floors themselves.

The floors are asserted here on purpose. Lowering one is allowed and
sometimes correct, but it has to be a deliberate edit that also updates this
file, rather than something that slides down while nobody is reading.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check():
    return _load("check_answerable_regression")


@pytest.fixture(scope="module")
def measure():
    return _load("measure_outcomes")


# --- refusing to produce a number it cannot stand behind ----------------

def test_a_partial_checkout_is_refused_rather_than_scored(check, tmp_path, capsys):
    """Four repositories out of five would score lower for the wrong reason.

    A floor that fails for a reason unrelated to the change under test gets
    lowered by whoever is unlucky enough to hit it, and then it is not a
    floor any more.
    """
    only_one = tmp_path / "sidra-ai"
    only_one.mkdir()

    code = check.main([f"tukemen-rgb/sidra-ai={only_one}"])
    err = capsys.readouterr().err

    assert code == 2
    assert "refusing to measure" in err
    assert "tukemen-rgb/Fg" in err or "tukemen-rgb/site" in err


def test_a_repository_named_but_absent_is_named_in_the_refusal(check, tmp_path, capsys):
    """"Something was missing" is not actionable; which one is."""
    present = tmp_path / "present"
    present.mkdir()

    code = check.main(
        [f"tukemen-rgb/sidra-ai={present}", "tukemen-rgb/site=/nonexistent-path"]
    )
    err = capsys.readouterr().err

    assert code == 2
    assert "tukemen-rgb/site" in err


def test_no_arguments_is_a_usage_error_not_a_pass(check, capsys):
    """Exiting 0 with nothing measured would make the check a no-op in CI."""
    assert check.main([]) == 2


def test_a_malformed_target_is_rejected(check, capsys):
    assert check.main(["tukemen-rgb/sidra-ai"]) == 2
    assert "expected repo=path" in capsys.readouterr().err


# --- the floors themselves ---------------------------------------------

def test_the_floors_sit_below_the_recorded_measurement(check):
    """Measured 2026-08-19 12:21: 7/18 answerable, 7/11 direct, 0/7 paraphrase.

    A floor above its measurement fails on a green tree; a floor far below it
    passes through a real regression. One question of slack absorbs churn in
    the four repositories this project does not own.

    The earlier version of this test asserted 7 and 1, pinned to a measurement
    that walked 426 documents the product never ingests. When the corpus was
    corrected the floors went red against a green main, which is how a check
    gets switched off.
    """
    assert check.MIN_ANSWERED == 6, "measured 7; floor is one question below"
    assert check.MIN_DIRECT == 6, "measured 7; floor is one question below"
    assert check.MIN_DISCRIMINATION_POINTS == pytest.approx(15.0)


def test_a_vacuous_paraphrase_floor_says_so_instead_of_passing_quietly(
    check, capsys
):
    """Zero is the honest floor, and an honest floor admits it guards nothing.

    Paraphrased questions score 0/7, so their floor cannot protect anything.
    Deleting it would make the failure invisible; leaving it silent would let
    a passing run read as a healthy one. It stays, and it announces itself.
    """
    assert check.MIN_PARAPHRASE == 0, "measured 0; a higher floor would be red on green"

    source = (ROOT / "scripts" / "check_answerable_regression.py").read_text(
        encoding="utf-8"
    )
    assert "既知のゼロ" in source, "a zero paraphrase score must be called out per-line"
    assert "guards nothing" in source, "a passing run must not read as a healthy one"


def _stub_measurement(check, monkeypatch, tmp_path, *, answered, direct, para, control=2):
    """Run main() against a fabricated measurement.

    The five checkouts are not available in the test environment, so ingestion
    and scoring are replaced. What is under test here is the reporting and the
    floor comparison, both of which run for real.
    """
    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    targets = []
    for repository in sorted({q.repository for q in OUTCOME_QUESTIONS}):
        path = tmp_path / repository.replace("/", "_")
        path.mkdir()
        targets.append(f"{repository}={path}")

    monkeypatch.setattr(check, "ingest", lambda *_a, **_k: {})
    monkeypatch.setattr(
        check,
        "measure_answerable",
        lambda *_a, **_k: {
            "scored": 18,
            "answered": answered,
            "mrr": 0.3,
            "by_tier": {
                "direct": {"answered": direct, "scored": 11},
                "paraphrase": {"answered": para, "scored": 7},
            },
            "control_hits": control,
            "discrimination": 0.278,
            "ungrounded": [],
            "rows": [],
        },
    )
    return check.main(targets)


def test_beating_the_paraphrase_floor_demands_that_the_floor_be_raised(
    check, monkeypatch, tmp_path, capsys
):
    """An improvement nobody ratchets is an improvement that regresses unseen.

    The floor is zero because the measurement is zero. The moment a run scores
    higher, the run has to say the floor is now behind reality - otherwise the
    next slide back to zero passes as compliance.
    """
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=9, direct=7, para=2)
    out = capsys.readouterr().out

    assert code == 0
    assert "この下限を上げること" in out


def test_a_zero_paraphrase_run_is_not_reported_as_healthy(
    check, monkeypatch, tmp_path, capsys
):
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=7, direct=7, para=0)
    out = capsys.readouterr().out

    assert code == 0
    assert "既知のゼロ" in out
    assert "guards nothing" in out


def test_a_real_regression_still_fails(check, monkeypatch, tmp_path, capsys):
    """The floors have to bite, or re-pinning them was just lowering the bar."""
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=4, direct=3, para=0)
    err = capsys.readouterr().err

    assert code == 1
    assert "answered 4 < 6" in err
    assert "direct 3 < 6" in err


def test_every_tier_is_floored_separately(check):
    """A blended rate lets a gain on one tier hide a collapse in the other.

    Direct-word and paraphrased questions fail for unrelated reasons -
    ranking versus vocabulary - so one number cannot speak for both.
    """
    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    tiers = {question.tier for question in OUTCOME_QUESTIONS}
    floored = {"direct": check.MIN_DIRECT, "paraphrase": check.MIN_PARAPHRASE}

    assert tiers <= set(floored), f"a tier has no floor: {tiers - set(floored)}"


def test_discrimination_is_floored_so_the_rate_cannot_be_met_by_matching_everything(
    check,
):
    """All five repositories discuss the same business.

    A retriever that returned plausible neighbours for every query would post
    a healthy answerable rate while being useless, so the floor that would
    otherwise be satisfiable by becoming less discriminating is backed by one
    on discrimination itself.
    """
    assert check.MIN_DISCRIMINATION_POINTS > 0


# --- shared parsing ----------------------------------------------------

def test_target_parsing_is_shared_with_the_measurement_script(measure):
    """One parser, so the two tools cannot disagree about what was measured.

    Asserted on the source rather than by identity: these tests load each
    script under its own module name, so the two would hold separate function
    objects even when the import is the same one. What matters is that the
    checker takes the parser from the measurement script instead of keeping a
    copy that can drift.
    """
    source = (ROOT / "scripts" / "check_answerable_regression.py").read_text(
        encoding="utf-8"
    )

    assert "def parse_targets" not in source, "the checker defines its own parser"
    assert "parse_targets," in source, "the checker does not import the shared parser"
    assert hasattr(measure, "parse_targets")


def test_parse_targets_separates_absent_repositories_from_unusable_arguments(
    measure, tmp_path
):
    """"Named but not on disk" and "not a valid argument" need different handling.

    The first is a corpus question the caller decides about; the second is a
    usage error with nothing to decide.
    """
    present = tmp_path / "present"
    present.mkdir()

    targets, missing = measure.parse_targets(
        [f"tukemen-rgb/site={present}", "tukemen-rgb/Fg=/nonexistent-path"]
    )
    assert targets == [("tukemen-rgb/site", present)]
    assert missing == ["tukemen-rgb/Fg"]

    _targets, missing = measure.parse_targets(["no-equals-sign"])
    assert missing is None, "a malformed spec is a usage error, not a missing repo"

    _targets, missing = measure.parse_targets(["tukemen-rgb/site=/nonexistent-path"])
    assert missing is None, "nothing checked out at all leaves nothing to measure"
