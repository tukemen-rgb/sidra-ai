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
