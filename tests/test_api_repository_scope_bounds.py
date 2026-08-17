"""Request-shape bounds for repository-scoped private API operations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidra_ai.api.schemas import (
    MAX_REPOSITORY_NAME_CHARS,
    MAX_REPOSITORY_SCOPE_ITEMS,
    AnalyzeRequest,
    ChatRequest,
    RetrieveRequest,
)


@pytest.mark.parametrize(
    ("request_type", "payload"),
    [
        (ChatRequest, {"message": "hi"}),
        (RetrieveRequest, {"query": "hi"}),
        (AnalyzeRequest, {}),
    ],
)
def test_repository_scope_accepts_the_bounded_limit(request_type, payload) -> None:
    repositories = [f"owner/repo-{index}" for index in range(MAX_REPOSITORY_SCOPE_ITEMS)]
    request = request_type(**payload, repositories=repositories)
    assert len(request.repositories or []) == MAX_REPOSITORY_SCOPE_ITEMS


@pytest.mark.parametrize(
    ("request_type", "payload"),
    [
        (ChatRequest, {"message": "hi"}),
        (RetrieveRequest, {"query": "hi"}),
        (AnalyzeRequest, {}),
    ],
)
def test_repository_scope_rejects_unbounded_item_count(request_type, payload) -> None:
    repositories = ["tukemen-rgb/site"] * (MAX_REPOSITORY_SCOPE_ITEMS + 1)
    with pytest.raises(ValidationError):
        request_type(**payload, repositories=repositories)


@pytest.mark.parametrize(
    ("request_type", "payload"),
    [
        (ChatRequest, {"message": "hi"}),
        (RetrieveRequest, {"query": "hi"}),
        (AnalyzeRequest, {}),
    ],
)
def test_repository_scope_rejects_oversized_repository_name(request_type, payload) -> None:
    oversized = "o/" + "r" * MAX_REPOSITORY_NAME_CHARS
    with pytest.raises(ValidationError):
        request_type(**payload, repositories=[oversized])
