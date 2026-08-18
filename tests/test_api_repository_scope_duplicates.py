from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidra_ai.api.schemas import AnalyzeRequest, ChatRequest, RetrieveRequest


@pytest.mark.parametrize(
    ("request_type", "kwargs"),
    [
        (ChatRequest, {"message": "status"}),
        (RetrieveRequest, {"query": "status"}),
        (AnalyzeRequest, {}),
    ],
)
def test_repository_scopes_reject_case_insensitive_duplicates(
    request_type: type[ChatRequest] | type[RetrieveRequest] | type[AnalyzeRequest],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="repositories must not contain duplicates"):
        request_type(
            repositories=["tukemen-rgb/site", "TUKEMEN-RGB/SITE"],
            **kwargs,
        )


@pytest.mark.parametrize(
    ("request_type", "kwargs"),
    [
        (ChatRequest, {"message": "status"}),
        (RetrieveRequest, {"query": "status"}),
        (AnalyzeRequest, {}),
    ],
)
def test_repository_scopes_preserve_distinct_ordered_values(
    request_type: type[ChatRequest] | type[RetrieveRequest] | type[AnalyzeRequest],
    kwargs: dict[str, object],
) -> None:
    repositories = ["tukemen-rgb/site", "tukemen-rgb/sidra-ai"]
    request = request_type(repositories=repositories, **kwargs)
    assert request.repositories == repositories
