"""Prompt/API citation provenance must not bypass secret or PII screening."""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.security.data_envelope import build_data_context


_FAKE_GITHUB_TOKEN = "ghp_A1b2C3d4E5f6G7h8I9j0"
_FAKE_EMAIL = "alice.person@example.com"


def _document(
    *,
    repository: str = "tukemen-rgb/site",
    path: str = "docs/readme.md",
    commit_sha: str = "a" * 40,
    license: str = "MIT",
    url: str = "https://github.com/tukemen-rgb/site/blob/main/docs/readme.md",
) -> Document:
    return Document(
        content="ordinary repository text",
        provenance=Provenance(
            source="github",
            repository=repository,
            path=path,
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.EXTERNAL,
            license=license,
            url=url,
        ),
    )


def test_safe_provenance_keeps_existing_citation_shape() -> None:
    context, citations = build_data_context([_document()])

    assert "source: tukemen-rgb/site@aaaaaaa:docs/readme.md" in context
    assert citations == [
        {
            "label": "S1",
            "citation": "tukemen-rgb/site@aaaaaaa:docs/readme.md",
            "repository": "tukemen-rgb/site",
            "path": "docs/readme.md",
            "commit_sha": "a" * 40,
            "source_type": "docs",
            "trust_level": "external",
            "license": "MIT",
            "url": "https://github.com/tukemen-rgb/site/blob/main/docs/readme.md",
            "redacted": False,
        }
    ]


def test_secret_shaped_path_is_replaced_before_prompt_or_api_export() -> None:
    path = f"docs/{_FAKE_GITHUB_TOKEN}.md"
    context, citations = build_data_context([_document(path=path)])

    citation = citations[0]
    assert _FAKE_GITHUB_TOKEN not in context
    assert _FAKE_GITHUB_TOKEN not in repr(citation)
    assert citation["path"] == "<redacted-path>"
    assert citation["citation"] == "tukemen-rgb/site@aaaaaaa:<redacted-path>"
    assert "source: tukemen-rgb/site@aaaaaaa:<redacted-path>" in context


def test_personal_email_in_path_is_replaced_whole() -> None:
    path = f"docs/{_FAKE_EMAIL}/notes.md"
    context, citations = build_data_context([_document(path=path)])

    citation = citations[0]
    assert _FAKE_EMAIL not in context
    assert _FAKE_EMAIL not in repr(citation)
    assert citation["path"] == "<redacted-path>"


def test_secret_shaped_commit_sha_never_leaks_a_short_prefix() -> None:
    context, citations = build_data_context(
        [_document(commit_sha=_FAKE_GITHUB_TOKEN)]
    )

    citation = citations[0]
    assert _FAKE_GITHUB_TOKEN not in context
    assert _FAKE_GITHUB_TOKEN[:7] not in context
    assert _FAKE_GITHUB_TOKEN not in repr(citation)
    assert citation["commit_sha"] == "<redacted-commit-sha>"
    assert citation["citation"] == (
        "tukemen-rgb/site@<redacted-commit-sha>:docs/readme.md"
    )


def test_basic_auth_url_and_sensitive_license_are_not_exported() -> None:
    sensitive_url = "https://viewer:syntheticpass@example.com/private"
    sensitive_license = f"contact {_FAKE_EMAIL} for terms"
    context, citations = build_data_context(
        [_document(url=sensitive_url, license=sensitive_license)]
    )

    citation = citations[0]
    assert sensitive_url not in context
    assert sensitive_url not in repr(citation)
    assert _FAKE_EMAIL not in repr(citation)
    assert citation["url"] == "<redacted-url>"
    assert citation["license"] == "<redacted-license>"
