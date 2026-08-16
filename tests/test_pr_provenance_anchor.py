"""PR provenance must stay anchored to the allowlisted base repository."""

from __future__ import annotations

from sidra_ai.documents import SourceType, TrustLevel
from sidra_ai.ingestion.normalize import pull_request_document


def _pull_payload(*, head_sha: str) -> dict:
    return {
        "number": 42,
        "title": "External fork proposal",
        "body": "Candidate change from a fork.",
        "state": "open",
        "updated_at": "2026-08-16T10:00:00Z",
        "created_at": "2026-08-16T09:00:00Z",
        "merged_at": None,
        "html_url": "https://github.com/tukemen-rgb/site/pull/42",
        "user": {"login": "outside-contributor", "type": "User"},
        "head": {"sha": head_sha},
    }


def test_pr_citation_uses_allowlisted_base_repository_observation_sha() -> None:
    base_sha = "a" * 40
    fork_head_sha = "b" * 40

    document = pull_request_document(
        _pull_payload(head_sha=fork_head_sha),
        repository="tukemen-rgb/site",
        commit_sha=base_sha,
        license="unknown",
    )

    assert document is not None
    provenance = document.provenance
    assert provenance.source_type is SourceType.PULL_REQUEST
    assert provenance.trust_level is TrustLevel.EXTERNAL
    assert provenance.commit_sha == base_sha
    assert provenance.extra["head_sha"] == fork_head_sha
    assert provenance.citation == "tukemen-rgb/site@aaaaaaa:pull/42"


def test_pr_head_revision_remains_material_provenance_data() -> None:
    base_sha = "a" * 40
    first = pull_request_document(
        _pull_payload(head_sha="b" * 40),
        repository="tukemen-rgb/site",
        commit_sha=base_sha,
        license="unknown",
    )
    second = pull_request_document(
        _pull_payload(head_sha="c" * 40),
        repository="tukemen-rgb/site",
        commit_sha=base_sha,
        license="unknown",
    )

    assert first is not None and second is not None
    assert first.provenance.commit_sha == second.provenance.commit_sha == base_sha
    assert first.provenance.extra["head_sha"] != second.provenance.extra["head_sha"]


def test_pr_without_head_sha_does_not_invent_a_fork_commit() -> None:
    payload = _pull_payload(head_sha="")
    base_sha = "a" * 40

    document = pull_request_document(
        payload,
        repository="tukemen-rgb/site",
        commit_sha=base_sha,
        license="unknown",
    )

    assert document is not None
    assert document.provenance.commit_sha == base_sha
    assert document.provenance.extra["head_sha"] == ""
