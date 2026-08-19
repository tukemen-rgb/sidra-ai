#!/usr/bin/env python3
"""Exercise the product's ingestion client against the real GitHub API.

Why this is a committed script and not a snippet someone retypes: the backlog
has said "the verification script is written, it runs the moment a token is
placed" since 2026-08-19, while the script itself only ever existed in one
session's temporary directory. Every loop that read that line believed the
work was staged, and none of them could run it. A promise in the backlog that
nothing in the repository backs is the same failure class as a metric nobody
enforces - it reads as done and is not.

Scope is deliberately narrow. The backlog names three things that have never
been checked against real GitHub: the payload shape, pagination, and
incremental compare. A full `analyze` over the five repositories would spend
far more than the anonymous window and leave the verification half-finished,
which is worse than a narrow one that completes.

Two rules are baked in because loops kept relearning them the expensive way:

  * Never spend more requests than the budget. `BudgetedTransport` refuses the
    call rather than letting a run drain the window, so a failure is always
    readable as "it broke" and never ambiguous with "it ran out".
  * Never wait for the anonymous window. It is per egress IP and shared; a
    window observed at 25/60 was empty again inside a minute, and a same-
    process 5-second poll ran seven minutes without ever catching one. If the
    quota is not already there, this exits and says what to place.

Prints no credentials. The token, when present, is read from the environment
by `Settings.github_token` and never echoed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sidra_ai.config.settings import Settings  # noqa: E402
from sidra_ai.ingestion.github_client import (  # noqa: E402
    GitHubAPIError,
    HttpxTransport,
    Response,
)

#: Enough for the three checks with headroom, and far under the anonymous 60
#: so a run that starts can always finish. Raising this without also raising
#: the quota check below is how a run becomes unreadable.
REQUEST_BUDGET = 14

#: The repository to read. Public and already in the default allow-list.
DEFAULT_REPO = "tukemen-rgb/sidra-ai"


class QuotaExhausted(RuntimeError):
    """Raised instead of issuing a request the budget does not cover."""


class BudgetedTransport:
    """Wrap a transport with a hard call ceiling.

    The anonymous quota is 60 requests per hour per source IP, shared by every
    loop on this host. A verification run that overruns it does two kinds of
    damage: it blocks the next loop, and it makes its own failure
    uninterpretable, because an exhausted quota and a broken client both
    surface as a 403. Refusing the call keeps those two apart.
    """

    def __init__(self, inner: Any, budget: int = REQUEST_BUDGET) -> None:
        self._inner = inner
        self.budget = budget
        self.calls = 0

    def __call__(
        self, method: str, url: str, headers: Any, timeout: float
    ) -> Response:
        if self.calls >= self.budget:
            raise QuotaExhausted(
                f"request budget of {self.budget} exhausted; refusing to spend "
                "more of a quota that is shared with the other loops"
            )
        self.calls += 1
        return self._inner(method, url, headers, timeout)


def resolve_ca_bundle() -> str:
    """The CA to verify against.

    `HttpxTransport` uses `trust_env=False` so bearer credentials never reach
    an ambient proxy, which also means `SSL_CERT_FILE` is not consulted. On a
    network that terminates TLS, not naming the CA is a total failure
    (`CERTIFICATE_VERIFY_FAILED`, status 0), not a degraded one.
    """

    configured = os.environ.get("SIDRA_CA_BUNDLE", "").strip()
    if configured:
        return configured
    fallback = "/root/.ccr/ca-bundle.crt"
    return fallback if Path(fallback).exists() else ""


def read_quota(ca_bundle: str) -> dict[str, int]:
    """Current core quota. `/rate_limit` does not itself consume core."""

    transport = HttpxTransport(ca_bundle=ca_bundle)
    response = transport(
        "GET",
        "https://api.github.com/rate_limit",
        {"Accept": "application/vnd.github+json"},
        20.0,
    )
    if not isinstance(response.body, dict):
        raise GitHubAPIError(f"/rate_limit returned {response.body!r}")
    core = response.body.get("resources", {}).get("core")
    if not isinstance(core, dict):
        raise GitHubAPIError("/rate_limit response had no core resource")
    return core


def check_payload_shape(client: Any, repo: str, out: dict[str, Any]) -> bool:
    """The fields the normalizer reads must be the fields GitHub sends.

    Deliberately checked against the live API rather than a recorded fixture:
    the `mcp__github__*` tools return a *projection* with renamed fields
    (`profile_url` where the API sends `html_url`). A fixture built from those
    would test the shape of the MCP layer while reporting that real data
    passed.
    """

    repository = client.get_repository(repo)
    out["repository_fields"] = sorted(
        k for k in ("full_name", "default_branch", "private", "owner", "license")
        if k in repository
    )
    out["default_branch"] = repository.get("default_branch")

    head = client.get_head_sha(repo)
    out["head_sha_len"] = len(head)
    out["head_sha_is_hex"] = all(c in "0123456789abcdef" for c in head)
    out["head_sha"] = head

    ok = (
        repository.get("full_name", "").lower() == repo.lower()
        and out["head_sha_len"] == 40
        and out["head_sha_is_hex"]
    )
    print(
        f"  payload shape: full_name={repository.get('full_name')!r} "
        f"default_branch={out['default_branch']!r} "
        f"head_sha={out['head_sha_len']} hex chars -> {'OK' if ok else 'FAILED'}"
    )
    return bool(ok)


def check_pagination(client: Any, repo: str, out: dict[str, Any]) -> bool:
    """A Link header must actually be followed, not stopped at page one.

    `_iter_list_pages` only reaches a second page when the requested item
    limit exceeds `per_page`, which caps at 100 - hence the settings below.
    Fewer than 101 commits returned means the repository is too small to
    prove this, which is a skip and not a pass.
    """

    commits = client.list_commits(repo)
    out["commits_fetched"] = len(commits)
    out["commit_shas_unique"] = len({c.get("sha") for c in commits})
    crossed = len(commits) > 100
    out["crossed_page_boundary"] = crossed
    verdict = "OK" if crossed else "INCONCLUSIVE (repo has one page of commits)"
    print(
        f"  pagination: {len(commits)} commits, "
        f"{out['commit_shas_unique']} unique -> {verdict}"
    )
    return crossed


def check_incremental(client: Any, repo: str, out: dict[str, Any]) -> bool:
    """Compare is the differential-ingestion core; an empty diff means no work.

    The backlog's own acceptance is that a second pass reports
    `inference_skipped`. The mechanism under that is compare(head, head)
    returning no files - checked directly here so the result does not depend
    on standing an API up.
    """

    head = out.get("head_sha")
    if not head:
        print("  incremental: SKIPPED (no head sha)")
        return False

    identical = client.compare(repo, head, head)
    out["identical_status"] = identical.get("status")
    out["identical_files"] = len(identical.get("files", []))
    out["identical_ahead_by"] = identical.get("ahead_by")
    empty = out["identical_files"] == 0 and identical.get("ahead_by") == 0

    print(
        f"  incremental: compare(head,head) status={out['identical_status']!r} "
        f"ahead_by={out['identical_ahead_by']} files={out['identical_files']} "
        f"-> {'OK' if empty else 'FAILED'}"
    )
    return bool(empty)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    repo = argv[0] if argv else DEFAULT_REPO

    ca_bundle = resolve_ca_bundle()
    print(f"repository: {repo}")
    print(f"CA bundle:  {ca_bundle or '(system default)'}")

    try:
        core = read_quota(ca_bundle)
    except GitHubAPIError as exc:
        print(f"cannot read /rate_limit: {exc}")
        return 2

    authenticated = int(core.get("limit", 0)) > 60
    print(
        f"quota:      {core.get('remaining')}/{core.get('limit')} "
        f"({'authenticated' if authenticated else 'anonymous'})"
    )

    if int(core.get("remaining", 0)) < REQUEST_BUDGET:
        print(
            f"\nNOT STARTING: need {REQUEST_BUDGET} requests, "
            f"{core.get('remaining')} available. Spent 0.\n"
            "Do not wait for the anonymous window. It is per egress IP and\n"
            "shared, and was measured opening and emptying inside a minute.\n"
            "Place a read-only SIDRA_GITHUB_TOKEN in the environment; that\n"
            "raises the ceiling to 5000/hour and this runs to completion."
        )
        return 2

    settings = Settings(
        allowed_repositories=(repo,),
        ca_bundle=ca_bundle,
        # Must exceed per_page's cap of 100, or pagination is never exercised.
        max_items_per_source=150,
    )
    from sidra_ai.ingestion.github_client import GitHubReadOnlyClient

    transport = BudgetedTransport(HttpxTransport(ca_bundle=ca_bundle))
    client = GitHubReadOnlyClient(settings, transport=transport)

    results: dict[str, Any] = {}
    checks = (
        ("payload shape", check_payload_shape),
        ("pagination", check_pagination),
        ("incremental compare", check_incremental),
    )
    verdicts: dict[str, str] = {}

    print("\nchecks:")
    for name, check in checks:
        try:
            verdicts[name] = "confirmed" if check(client, repo, results) else "not confirmed"
        except QuotaExhausted as exc:
            print(f"  {name}: STOPPED - {exc}")
            verdicts[name] = "not run (budget)"
        except GitHubAPIError as exc:
            print(f"  {name}: FAILED - {exc}")
            verdicts[name] = "failed"

    print(f"\nrequests spent: {transport.calls} (budget {transport.budget})")
    for name, verdict in verdicts.items():
        print(f"  {name}: {verdict}")
    results["verdicts"] = verdicts
    results["requests_spent"] = transport.calls
    print("RESULTS " + json.dumps(results, ensure_ascii=False, sort_keys=True))

    return 0 if all(v == "confirmed" for v in verdicts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
