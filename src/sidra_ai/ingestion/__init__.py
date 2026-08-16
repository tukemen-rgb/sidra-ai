"""GitHub read-only ingestion. No write capability exists in v0.1."""

from sidra_ai.ingestion.github_client import (
    ALLOWED_HTTP_METHODS,
    GitHubAPIError,
    GitHubReadOnlyClient,
    RepositoryNotAllowedError,
    Response,
    WriteOperationForbiddenError,
)
from sidra_ai.ingestion.pipeline import (
    GitHubIngestionPipeline,
    IngestionReport,
    RepositoryReport,
)
from sidra_ai.ingestion.state import IngestionState, RepositoryState, StateStore

__all__ = [
    "ALLOWED_HTTP_METHODS",
    "GitHubAPIError",
    "GitHubIngestionPipeline",
    "GitHubReadOnlyClient",
    "IngestionReport",
    "IngestionState",
    "RepositoryNotAllowedError",
    "RepositoryReport",
    "RepositoryState",
    "Response",
    "StateStore",
    "WriteOperationForbiddenError",
]
