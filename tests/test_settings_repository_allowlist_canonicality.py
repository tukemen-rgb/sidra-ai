"""Repository allowlist configuration stays unambiguous before API work."""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings, UnsafeConfigurationError


def test_settings_reject_case_insensitive_duplicate_repositories() -> None:
    settings = Settings(allowed_repositories=("Owner/Repo", "owner/repo"))

    with pytest.raises(UnsafeConfigurationError, match="case-insensitive duplicates"):
        settings.validate()


@pytest.mark.parametrize(
    "repository",
    (
        "owner/",
        "/repo",
        "owner/repo/extra",
        "owner /repo",
        " owner/repo",
        "owner/repo ",
    ),
)
def test_settings_reject_ambiguous_repository_identifiers(repository: str) -> None:
    settings = Settings(allowed_repositories=(repository,))

    with pytest.raises(UnsafeConfigurationError, match="exactly one non-empty"):
        settings.validate()


def test_from_env_rejects_duplicate_default_scope_before_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIDRA_ALLOWED_REPOSITORIES", "Owner/Repo,owner/repo")

    with pytest.raises(UnsafeConfigurationError, match="case-insensitive duplicates"):
        Settings.from_env()


def test_distinct_normal_repository_identifiers_remain_valid() -> None:
    Settings(
        allowed_repositories=("Owner-1/repo.name_2", "other/repo"),
    ).validate()
