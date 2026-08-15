"""Commit-SHA differential ingestion, and the no-change/no-inference rule."""

from __future__ import annotations

from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore

REPO = "tukemen-rgb/site"


def _pipeline(client, store, gate, tmp_path, settings: Settings) -> GitHubIngestionPipeline:
    return GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )


def test_first_run_ingests_and_records_the_sha(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    report = pipeline.ingest_repository(REPO)

    assert report.changed is True
    assert report.head_sha == fake_github.head_sha
    assert report.previous_sha == ""
    assert report.indexed > 0

    state = pipeline.state_store.load().get(REPO)
    assert state.last_commit_sha == fake_github.head_sha
    assert state.document_count == report.indexed


def test_second_run_with_no_new_commits_is_skipped(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    pipeline.ingest_repository(REPO)

    fake_github.requests.clear()
    report = pipeline.ingest_repository(REPO)

    assert report.changed is False
    assert report.skipped_reason == "no_new_commits"
    assert report.indexed == 0
    assert report.requires_inference is False

    # Only the two cheap metadata calls: repo metadata and HEAD.
    paths = [path for _, path in fake_github.requests]
    assert len(paths) == 2, f"unchanged repo issued extra requests: {paths}"
    assert not any("readme" in p or "contents" in p or "issues" in p for p in paths)


def test_new_commit_triggers_a_differential_fetch(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    pipeline.ingest_repository(REPO)

    fake_github.head_sha = "e" * 40
    fake_github.requests.clear()
    report = pipeline.ingest_repository(REPO)

    assert report.changed is True
    assert report.previous_sha == "a" * 40
    assert report.head_sha == "e" * 40
    assert any("compare" in path for _, path in fake_github.requests), (
        "expected the compare endpoint to be used for the incremental fetch"
    )


def test_unchanged_repository_never_invokes_the_model(
    client, store, gate, tmp_path, settings, model
) -> None:
    """The cost control: idle repositories must not reach inference."""

    from sidra_ai.api.service import SidraService

    service = SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )

    first = service.analyze_github([REPO])
    assert first["ingestion"]["changed"] is True
    calls_after_first = model.calls
    assert calls_after_first == 1, "the first, changed run should run inference once"

    second = service.analyze_github([REPO])
    assert second["inference_skipped"] is True
    assert second["analysis"] is None
    assert "no new commits" in second["reason"]
    assert model.calls == calls_after_first, "model was invoked with no changes"


def test_force_reingests_even_without_new_commits(
    client, store, gate, tmp_path, settings
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    pipeline.ingest_repository(REPO)
    report = pipeline.ingest_repository(REPO, force=True)
    assert report.changed is True
    assert report.indexed > 0


def test_state_survives_a_corrupt_file(tmp_path) -> None:
    """A corrupt state file must degrade to a re-ingest, not a crash."""

    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert StateStore(path).load().repositories == {}


def test_state_write_is_atomic(tmp_path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.mark_ingested(REPO, commit_sha="f" * 40, document_count=3)
    assert store.load().get(REPO).last_commit_sha == "f" * 40
    # No temp files left behind.
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_denied_repository_is_reported_not_fetched(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    report = pipeline.ingest_repository("attacker/evil-repo")
    assert report.changed is False
    assert report.skipped_reason == "not_allowed"
    assert fake_github.requests == []
