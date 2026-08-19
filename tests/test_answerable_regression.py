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
import re
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
    """Measured 2026-08-19 over the 26-question set: 11 answered, 10 direct.

    A floor above its measurement fails on a green tree; a floor far below it
    passes through a real regression. One question of slack absorbs churn in
    the four repositories this project does not own.

    The first floors here (7/6/1) were pinned to a measurement that walked
    426 documents the product never ingests and went red against a green
    main. The second set (6/6/0) was honest but measured over 18 questions;
    the set grew to 26 when CreatorYard and marketing gained coverage, and
    counts are only comparable over the same set - so the floors moved with
    the measurement, in the same commit, as the re-pinning rule requires.
    """
    assert check.MIN_ANSWERED == 10, "measured 11; floor is one question below"
    assert check.MIN_DIRECT == 9, "measured 10; floor is one question below"
    assert check.MIN_DISCRIMINATION_POINTS == pytest.approx(15.0)


def test_the_paraphrase_floor_finally_guards_something(check):
    """One, because one paraphrase question now actually retrieves.

    `para-cy-unfinished-work` finds "完成度で人を落とさない" at rank 2 on the
    product-identical corpus - the first paraphrase hit this project has had.
    The floor is deliberately NOT one-below-measurement: one below one is
    zero, zero guards nothing, and this number exists so the paraphrase rate
    can never return to zero silently. If it goes red on a green main because
    the CreatorYard culture line moved, lowering it back with a reason is the
    documented escape hatch.
    """
    assert check.MIN_PARAPHRASE == 1

    source = (ROOT / "scripts" / "check_answerable_regression.py").read_text(
        encoding="utf-8"
    )
    assert "既知のゼロ" in source, "a zero paraphrase run must still be called out"


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
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=12, direct=10, para=2)
    out = capsys.readouterr().out

    assert code == 0
    assert "この下限を上げること" in out


def test_a_slide_back_to_zero_paraphrase_now_fails(
    check, monkeypatch, tmp_path, capsys
):
    """The old behavior - zero passing with a callout - is retired.

    While the floor was vacuous, a zero run could only be annotated. Now that
    a paraphrase question genuinely retrieves, returning to zero is a
    regression and must say so with a failing exit, not a sad footnote.
    """
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=11, direct=10, para=0)
    captured = capsys.readouterr()

    assert code == 1
    assert "paraphrase 0 < 1" in captured.err
    assert "既知のゼロ" in captured.out


def test_a_real_regression_still_fails(check, monkeypatch, tmp_path, capsys):
    """The floors have to bite, or re-pinning them was just lowering the bar."""
    code = _stub_measurement(check, monkeypatch, tmp_path, answered=4, direct=3, para=0)
    err = capsys.readouterr().err

    assert code == 1
    assert "answered 4 < 10" in err
    assert "direct 3 < 9" in err


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


# --- wired into the pipeline -------------------------------------------
# These read the workflow as text rather than parsing it. PyYAML is not a
# dependency of this project and is absent from a clean CI interpreter, so a
# test that imported it would fail to collect on the very pipeline it is
# meant to protect - while passing locally, where the system image happens to
# ship it.


def _workflow() -> str:
    return (ROOT / ".github" / "workflows" / "integration-v01.yml").read_text(
        encoding="utf-8"
    )


def _job_block(name: str) -> str:
    """Return one job's text, from its key to the next job at the same indent."""
    text = _workflow()
    start = text.index(f"\n  {name}:\n")
    rest = text[start + 1 :]
    following = re.search(r"^  [a-z][a-z0-9_-]*:$", rest[1:], re.MULTILINE)
    return rest if following is None else rest[: following.start() + 1]


def test_ci_runs_the_answerable_check():
    """A check that is not in the pipeline is a habit, not a control.

    This floor spent its first hours exactly where the false-positive rate
    used to be: real, documented, and enforced by whoever remembered.
    """
    assert "check_answerable_regression.py" in _job_block("answerable")


def test_the_offline_job_stays_offline():
    """The network was allowed into a new job, not into the existing one.

    "Same-SHA offline verification" is a claim that job makes about itself.
    Cloning four repositories inside it would quietly make that claim false,
    which is why the approved option was a separate job.
    """
    offline = _job_block("verify")

    assert "Same-SHA offline verification" in offline
    assert "git clone" not in offline, "the offline job now fetches a corpus"
    assert "check_answerable_regression" not in offline


def test_the_corpus_is_cloned_without_credentials():
    """Four repositories do not need the workflow token, so they do not get it.

    actions/checkout persists credentials by default; a plain clone carries
    none. Nothing in this job authenticates, and nothing in it should.
    """
    job = _job_block("answerable")
    # Comments discuss credentials at length; only what the runner executes
    # is evidence about what it does.
    executable = "\n".join(
        line for line in job.splitlines() if not line.lstrip().startswith("#")
    )

    assert "git clone --depth 1" in executable, "a full history is fetched for no reason"
    assert "token" not in executable.lower()
    assert "secrets." not in executable, "a secret reaches a job that needs none"

    # actions/checkout appears once, for this repository, and with the same
    # credential handling as the offline job.
    assert job.count("uses: actions/checkout") == 1
    assert "persist-credentials: false" in job


def test_a_failed_clone_is_not_mistaken_for_a_regression():
    """The two failures need opposite responses.

    A missing corpus is an availability problem; a breached floor is a
    retrieval problem. Answering the first by lowering a floor is how a gate
    gets quietly disarmed.
    """
    job = _job_block("answerable")

    assert "not a retrieval regression" in job
    assert "Do not lower a floor" in job


def test_every_repository_the_questions_name_is_cloned():
    """A partial corpus is refused at exit 2, so a missing clone wastes a run."""
    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    job = _job_block("answerable")

    for repository in {question.repository for question in OUTCOME_QUESTIONS}:
        assert repository in job, f"{repository} is never cloned or passed"
