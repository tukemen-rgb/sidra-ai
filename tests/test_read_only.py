"""GitHub write capability must not exist anywhere in v0.1.

Three independent checks, because "we just didn't write that code" is not a
guarantee that survives future edits:

1. The client rejects non-GET methods at the one place requests are made.
2. The default transport rejects them too.
3. A source scan fails if any write verb or mutating endpoint appears in the
   package - so adding one is a red test, not a review miss.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from sidra_ai.ingestion.github_client import (
    ALLOWED_HTTP_METHODS,
    GitHubReadOnlyClient,
    HttpxTransport,
    RepositoryNotAllowedError,
    WriteOperationForbiddenError,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "sidra_ai"


def test_only_get_is_allowed() -> None:
    assert ALLOWED_HTTP_METHODS == {"GET"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post", "MERGE"])
def test_client_refuses_write_methods(client: GitHubReadOnlyClient, method: str) -> None:
    with pytest.raises(WriteOperationForbiddenError):
        client._request("repos/tukemen-rgb/site", method=method)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_default_transport_refuses_write_methods(method: str) -> None:
    with pytest.raises(WriteOperationForbiddenError):
        HttpxTransport()(method, "https://api.github.com/repos/x/y", {}, 5.0)


def test_client_exposes_no_write_methods() -> None:
    """No public method name suggests mutation."""

    forbidden = re.compile(
        r"^(create|update|delete|merge|close|comment|post|put|patch|push|"
        r"dispatch|approve|request_review|add_|set_|write_)"
    )
    offenders = [
        name
        for name in dir(GitHubReadOnlyClient)
        if not name.startswith("_") and forbidden.match(name)
    ]
    assert offenders == [], f"read-only client exposes mutating methods: {offenders}"


def _python_sources() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_no_http_write_calls_in_package() -> None:
    """No module calls a write verb on any HTTP client."""

    write_verbs = {"post", "put", "patch", "delete", "request", "send", "stream"}
    offenders: list[str] = []

    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in write_verbs:
                continue
            owner = func.value
            owner_name = (
                owner.id
                if isinstance(owner, ast.Name)
                else owner.attr
                if isinstance(owner, ast.Attribute)
                else ""
            )
            # `self._post` on a local inference server is not GitHub traffic,
            # and `httpx.post` to a loopback model endpoint is allowed.
            if owner_name in {"httpx"} and "http_backends" not in str(path):
                offenders.append(f"{path.name}:{node.lineno} httpx.{func.attr}")

    assert offenders == [], f"HTTP write calls found: {offenders}"


def test_no_github_write_endpoints_referenced() -> None:
    """No source string points at a mutating GitHub endpoint."""

    mutating = re.compile(
        r"(?i)(git/refs|git/commits\b.*create|/merges\b|/dispatches\b|"
        r"pulls/\{[^}]*\}/(merge|reviews)|issues/\{[^}]*\}/comments)"
    )
    offenders = []
    for path in _python_sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if mutating.search(line):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == [], f"mutating GitHub endpoints referenced: {offenders}"


def test_repository_allowlist_is_enforced_before_any_request(
    client: GitHubReadOnlyClient, fake_github
) -> None:
    with pytest.raises(RepositoryNotAllowedError):
        client.get_repository("attacker/evil-repo")
    assert fake_github.requests == [], "a request was issued for a denied repository"


def test_client_refuses_urls_outside_the_api_base(client: GitHubReadOnlyClient) -> None:
    from sidra_ai.ingestion.github_client import GitHubAPIError

    with pytest.raises(GitHubAPIError):
        client._request("https://evil.example.com/steal")
