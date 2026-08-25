"""The ingestion judge has to be wrong in the safe direction.

Three failures it exists to prevent, each pinned below:

* a repository quietly degrading to a partial fetch while the document total
  still looks healthy - that is exactly what happened for a day and a half
  while both existing judges printed NO MOVEMENT;
* someone else's push being banked as our progress, because four of the five
  repositories are other people's and their document counts move on their own;
* an environment that cannot reach GitHub printing a zero, which reads
  identically to "the product stopped working".

None of these tests touch the network: ``main`` takes the ingestion callable
so the analyze response can be staged.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_ingestion_regression_under_test",
        REPO_ROOT / "scripts" / "check_ingestion_regression.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def judge():
    return _load()


def _repo(name, indexed, head, skipped_reason="", error=""):
    return {
        "repository": name,
        "indexed": indexed,
        "head_sha": head,
        "skipped_reason": skipped_reason,
        "error": error,
    }


def _ingestion(repositories):
    return {
        "total_indexed": sum(r["indexed"] for r in repositories),
        "repositories": repositories,
    }


FIVE = [
    _repo("owner/a", 110, "c4dd3e40dcf5abcd"),
    _repo("owner/b", 116, "aa4288e3796cabcd"),
    _repo("owner/c", 69, "ddef0a3f4092abcd"),
    _repo("owner/d", 74, "caf112e32458abcd"),
    _repo("owner/e", 113, "c362e7563638abcd"),
]


# --------------------------------------------------------------- snapshot


def test_the_snapshot_counts_documents_repositories_and_complete_fetches(judge):
    snapshot = judge._snapshot(_ingestion(FIVE))

    assert snapshot["github_documents_indexed"] == 482
    assert snapshot["github_repositories_indexed"] == 5
    assert snapshot["github_complete_fetches"] == 5
    assert snapshot["corpus_heads"]["owner/a"] == "c4dd3e40dcf5"


def test_a_head_match_skip_still_counts_as_a_complete_fetch(judge):
    """The second analyze of an unchanged repository is not a degradation.

    `index_rehydrated` means the head matched and the stored index was
    reused - the fetch is as complete as the run that filled it.
    """

    repositories = [dict(r) for r in FIVE]
    for repository in repositories:
        repository["skipped_reason"] = "index_rehydrated"

    assert judge._snapshot(_ingestion(repositories))["github_complete_fetches"] == 5


def test_a_partial_fetch_is_not_a_complete_fetch(judge):
    """The failure this file exists for, in one assertion."""

    repositories = [dict(r) for r in FIVE]
    repositories[0]["skipped_reason"] = "partial_fetch"

    assert judge._snapshot(_ingestion(repositories))["github_complete_fetches"] == 4


def test_a_repository_that_errored_is_not_complete_even_with_documents(judge):
    repositories = [dict(r) for r in FIVE]
    repositories[0]["error"] = "GitHub refused docs/: not authorized"

    assert judge._snapshot(_ingestion(repositories))["github_complete_fetches"] == 4


# ------------------------------------------------------------------ floors


def test_the_floors_sit_under_the_first_real_measurement(judge):
    """482 documents over five repositories, measured 2026-08-24."""

    assert judge.MIN_DOCUMENTS_INDEXED == 400
    assert judge.MIN_REPOSITORIES_INDEXED == 5
    assert not judge._floor_failures(judge._snapshot(_ingestion(FIVE)))


def test_losing_a_repository_breaks_the_floor(judge):
    repositories = [dict(r) for r in FIVE]
    repositories[0]["indexed"] = 0

    failures = judge._floor_failures(judge._snapshot(_ingestion(repositories)))

    assert failures, "a repository dropping to zero has to fail the floor"


# ----------------------------------------------------------------- compare


def test_a_newly_measured_number_banks(judge, capsys):
    now = judge._snapshot(_ingestion(FIVE))

    assert judge._compare({}, now) == judge.EXIT_MOVED
    assert "newly measured" in capsys.readouterr().out


def test_an_unchanged_corpus_reports_no_movement(judge):
    snapshot = judge._snapshot(_ingestion(FIVE))

    assert judge._compare(dict(snapshot), snapshot) == judge.EXIT_NO_MOVEMENT


def test_a_rise_on_the_same_heads_banks(judge):
    before = judge._snapshot(_ingestion(FIVE))
    repositories = [dict(r) for r in FIVE]
    repositories[0]["indexed"] += 5

    now = judge._snapshot(_ingestion(repositories))

    assert judge._compare(before, now) == judge.EXIT_MOVED


def test_a_rise_after_someone_elses_push_is_not_banked(judge, capsys):
    """The whole reason heads are recorded.

    The documents arrived because the repository's owner wrote them. Banking
    that would make "wait for other people to commit" a way to show progress.
    """

    before = judge._snapshot(_ingestion(FIVE))
    repositories = [dict(r) for r in FIVE]
    repositories[0]["indexed"] += 5
    repositories[0]["head_sha"] = "0123456789abdead"

    verdict = judge._compare(before, judge._snapshot(_ingestion(repositories)))

    assert verdict == judge.EXIT_NO_MOVEMENT
    assert "corpus moved" in capsys.readouterr().out


def test_a_fall_is_reported_even_when_the_corpus_moved(judge, capsys):
    """Drift excuses a rise, never a fall.

    A permission lost between two runs shows up as fewer documents, and
    whichever heads moved that is worth stopping for.
    """

    before = judge._snapshot(_ingestion(FIVE))
    repositories = [dict(r) for r in FIVE]
    repositories[0]["indexed"] = 0
    repositories[0]["head_sha"] = "0123456789abdead"

    verdict = judge._compare(before, judge._snapshot(_ingestion(repositories)))

    assert verdict == judge.EXIT_REGRESSED
    assert "WORSE" in capsys.readouterr().out


def test_losing_a_complete_fetch_regresses_even_as_documents_rise(judge):
    """The guard: a healthy-looking total can hide a degraded repository."""

    before = judge._snapshot(_ingestion(FIVE))
    repositories = [dict(r) for r in FIVE]
    repositories[0]["skipped_reason"] = "partial_fetch"
    repositories[1]["indexed"] += 50

    verdict = judge._compare(before, judge._snapshot(_ingestion(repositories)))

    assert verdict == judge.EXIT_REGRESSED


def test_a_changed_repository_scope_does_not_bank(judge, capsys):
    before = judge._snapshot(_ingestion(FIVE[:4]))
    now = judge._snapshot(_ingestion(FIVE))

    verdict = judge._compare(before, now)

    assert verdict == judge.EXIT_NO_MOVEMENT
    assert "repository scope changed" in capsys.readouterr().out


# -------------------------------------------------------------------- main


def test_no_token_cannot_judge(judge, monkeypatch, capsys):
    """An environment gap must not read as a product regression."""

    monkeypatch.delenv("SIDRA_GITHUB_TOKEN", raising=False)

    def _never_called(_repositories):  # pragma: no cover - must not run
        raise AssertionError("ingestion ran without a token")

    assert judge.main([], ingest=_never_called) == judge.EXIT_CANNOT_JUDGE
    assert "CANNOT JUDGE" in capsys.readouterr().err


def test_a_transport_failure_cannot_judge_and_names_the_ca(
    judge, monkeypatch, capsys
):
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)

    def _explodes(_repositories):
        raise RuntimeError("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate")

    assert judge.main([], ingest=_explodes) == judge.EXIT_CANNOT_JUDGE
    err = capsys.readouterr().err
    assert "SIDRA_CA_BUNDLE" in err
    assert "Do not disable verification" in err


def test_every_repository_failing_cannot_judge(judge, monkeypatch, capsys):
    """All five failing is a broken network, not five product bugs."""

    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)
    repositories = [
        _repo(name, 0, "", error="GitHub request failed")
        for name in judge.Settings.from_env().allowed_repositories
    ]

    verdict = judge.main([], ingest=lambda _r: _ingestion(repositories))

    assert verdict == judge.EXIT_CANNOT_JUDGE
    assert "every repository failed" in capsys.readouterr().err


def test_save_then_compare_round_trips(judge, monkeypatch, tmp_path):
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)
    names = list(judge.Settings.from_env().allowed_repositories)
    repositories = [
        _repo(name, count, f"{index}0123456789ab")
        for index, (name, count) in enumerate(zip(names, [110, 116, 69, 74, 113]))
    ]
    staged = _ingestion(repositories)
    path = tmp_path / "ing.json"

    assert judge.main(["--save", str(path)], ingest=lambda _r: staged) == judge.EXIT_MOVED
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["github_documents_indexed"] == 482

    verdict = judge.main(["--compare", str(path)], ingest=lambda _r: staged)
    assert verdict == judge.EXIT_NO_MOVEMENT


def test_the_floor_failure_is_reported_before_any_comparison(
    judge, monkeypatch, tmp_path, capsys
):
    """A run below the floor must not be saved as a new baseline."""

    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)
    names = list(judge.Settings.from_env().allowed_repositories)
    repositories = [_repo(name, 1, "0123456789ab") for name in names]
    path = tmp_path / "ing.json"

    verdict = judge.main(
        ["--save", str(path)], ingest=lambda _r: _ingestion(repositories)
    )

    assert verdict == judge.EXIT_REGRESSED
    assert "BELOW FLOOR" in capsys.readouterr().err
    assert not path.exists(), "a below-floor run was written as a baseline"


# ------------------------------------------- creator questions, real corpus


class _Chunk:
    def __init__(self, content, repository):
        self.content = content
        self.provenance = type("P", (), {"repository": repository})()


class _Result:
    def __init__(self, chunk):
        self.chunk = chunk


class _Doc:
    def __init__(self, content, repository):
        self.content = content
        self.provenance = type("P", (), {"repository": repository})()


class _Service:
    """A store and a retriever, staged - the two things the scorer touches."""

    def __init__(self, documents, ranked):
        self.store = type("S", (), {"documents": lambda _self: documents})()
        self.retriever = type(
            "R",
            (),
            {"search": lambda _self, query, top_k=5: ranked[:top_k]},
        )()


def _first_question(judge):
    return judge._GAME_PRODUCTION[0]


def test_the_creator_questions_are_the_ones_tallied_offline(judge):
    """Same set, so the two corpora produce comparable numbers.

    If this drifts, "the real corpus answers more" could mean nothing but
    "the real corpus was asked fewer questions".
    """

    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    expected = {q.name for q in OUTCOME_QUESTIONS if q.game_production}
    assert {q.name for q in judge._GAME_PRODUCTION} == expected
    assert judge.TOP_K == 5


def test_a_marker_only_counts_from_its_own_repository(judge):
    """A copy of the answer elsewhere is not an answer.

    Without this the corpus grading itself would score rank 1 on every
    question whose text it also contains - the failure the offline judge
    already had once.
    """

    question = _first_question(judge)
    documents = [_Doc(question.answer_marker, question.repository)]
    elsewhere = "tukemen-rgb/marketing"
    assert elsewhere != question.repository
    service = _Service(
        documents, [_Result(_Chunk(question.answer_marker, elsewhere))]
    )

    measured = judge._ask_the_real_index(service)

    assert measured["real_corpus_gp_answered"] == 0
    assert question.name in measured["real_corpus_gp_missed"]


def test_a_hit_in_the_right_repository_counts(judge):
    question = _first_question(judge)
    documents = [_Doc(question.answer_marker, question.repository)]
    service = _Service(
        documents,
        [_Result(_Chunk(question.answer_marker, question.repository))],
    )

    measured = judge._ask_the_real_index(service)

    assert measured["real_corpus_gp_answered"] == 1
    assert question.name not in measured["real_corpus_gp_missed"]


def test_evidence_that_was_never_indexed_is_not_scored_as_a_miss(judge):
    """The distinction the denominator exists for.

    A document that was never fetched and a document that ranked eleventh are
    different failures - one is an ingestion gap, the other is retrieval - and
    a single "answered/asked" rate hides which one you have.
    """

    service = _Service([], [])

    measured = judge._ask_the_real_index(service)

    assert measured["real_corpus_gp_grounded"] == 0
    assert measured["real_corpus_gp_missed"] == []
    assert len(measured["real_corpus_gp_ungrounded"]) == measured[
        "real_corpus_gp_asked"
    ]


def test_the_report_never_prints_the_corpus(judge, capsys):
    """Names and counts. The markers are other people's text."""

    question = _first_question(judge)
    snapshot = judge._snapshot(_ingestion(FIVE))
    snapshot.update(
        judge._ask_the_real_index(
            _Service([_Doc(question.answer_marker, question.repository)], [])
        )
    )

    judge._report(snapshot)

    out = capsys.readouterr().out
    assert question.name in out
    assert question.answer_marker not in out
    assert question.question not in out


def test_a_changed_question_set_does_not_bank(judge, capsys):
    """Same rule as a moved head: a new denominator is a new number."""

    before = judge._snapshot(_ingestion(FIVE))
    before.update(
        {
            "real_corpus_gp_answered": 3,
            "real_corpus_gp_grounded": 8,
            "real_corpus_gp_asked": 8,
        }
    )
    now = judge._snapshot(_ingestion(FIVE))
    now.update(
        {
            "real_corpus_gp_answered": 5,
            "real_corpus_gp_grounded": 12,
            "real_corpus_gp_asked": 12,
        }
    )

    verdict = judge._compare(before, now)

    assert verdict == judge.EXIT_NO_MOVEMENT
    assert "question set changed" in capsys.readouterr().out


def test_a_fall_in_answers_on_the_same_questions_regresses(judge):
    before = judge._snapshot(_ingestion(FIVE))
    before.update({"real_corpus_gp_answered": 3, "real_corpus_gp_asked": 8})
    now = judge._snapshot(_ingestion(FIVE))
    now.update({"real_corpus_gp_answered": 2, "real_corpus_gp_asked": 8})

    assert judge._compare(before, now) == judge.EXIT_REGRESSED


def test_losing_indexed_evidence_regresses_even_if_answers_hold(judge):
    """The guard. Documents can leave the index without the rate noticing."""

    before = judge._snapshot(_ingestion(FIVE))
    before.update({"real_corpus_gp_answered": 3, "real_corpus_gp_grounded": 8})
    now = judge._snapshot(_ingestion(FIVE))
    now.update({"real_corpus_gp_answered": 3, "real_corpus_gp_grounded": 6})

    assert judge._compare(before, now) == judge.EXIT_REGRESSED


def test_a_run_that_could_not_ask_says_nothing_about_the_answers(judge):
    """A staged ingestion with no staged questions must not report a fall.

    ``now`` has no creator numbers at all. Reading that as 3 -> 0 would be the
    same lie this script was written to stop one level up.
    """

    before = judge._snapshot(_ingestion(FIVE))
    before.update({"real_corpus_gp_answered": 3, "real_corpus_gp_grounded": 8})

    assert judge._compare(before, judge._snapshot(_ingestion(FIVE))) == (
        judge.EXIT_NO_MOVEMENT
    )


def test_staged_ingestion_asks_no_questions_by_default(judge, monkeypatch, capsys):
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)
    names = list(judge.Settings.from_env().allowed_repositories)
    staged = _ingestion([_repo(n, 100, "0123456789ab") for n in names])

    assert judge.main([], ingest=lambda _r: staged) == judge.EXIT_NO_MOVEMENT
    assert "creator questions" not in capsys.readouterr().out


def test_a_staged_measurement_reaches_the_snapshot(judge, monkeypatch, tmp_path):
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "ghp_" + "0" * 36)
    names = list(judge.Settings.from_env().allowed_repositories)
    staged = _ingestion([_repo(n, 100, "0123456789ab") for n in names])
    path = tmp_path / "ing.json"

    verdict = judge.main(
        ["--save", str(path)],
        ingest=lambda _r: staged,
        measure=lambda: {
            "real_corpus_gp_answered": 3,
            "real_corpus_gp_grounded": 8,
            "real_corpus_gp_asked": 8,
            "real_corpus_gp_missed": [],
            "real_corpus_gp_ungrounded": [],
        },
    )

    assert verdict == judge.EXIT_MOVED
    assert json.loads(path.read_text(encoding="utf-8"))["real_corpus_gp_answered"] == 3
