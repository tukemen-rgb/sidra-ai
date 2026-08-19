"""The staged verification runner has to be real, and has to stay honest.

`docs/BACKLOG.md` has promised for a day that the real-API verification "runs
the moment a token is placed". That promise was backed by a file in one
session's temporary directory, so every other loop read it as staged work and
could not run it. These tests pin the two properties that make the committed
version worth the promise, and neither of them touches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_real_github_api as verify  # noqa: E402


class _Recorder:
    """Stands in for the HTTP transport; records instead of connecting."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, method, url, headers, timeout):
        self.calls.append(url)
        return verify.Response(status=200, headers={}, body={})


def test_the_budget_refuses_the_call_rather_than_overspending() -> None:
    """An overrun does two kinds of damage, and the second is the subtle one.

    It blocks the next loop, and it makes the failure unreadable: an exhausted
    anonymous quota and a broken client both come back as 403. Stopping at the
    ceiling keeps those two distinguishable.
    """

    inner = _Recorder()
    transport = verify.BudgetedTransport(inner, budget=3)

    for _ in range(3):
        transport("GET", "https://api.github.com/x", {}, 1.0)

    with pytest.raises(verify.QuotaExhausted):
        transport("GET", "https://api.github.com/x", {}, 1.0)

    assert transport.calls == 3
    assert len(inner.calls) == 3, "a refused call must not reach the network"


def test_a_short_window_stops_the_run_instead_of_waiting(monkeypatch, capsys) -> None:
    """Waiting for the anonymous window is not a procedure, it is a coin flip.

    Measured on 2026-08-19: a window read 25/60 and was empty again under a
    minute later, and a same-process five-second poll ran seven minutes
    without catching one. The quota is per egress IP and four loops share it.
    So a short window must end the run immediately, having spent nothing, and
    say what to place instead.
    """

    monkeypatch.setattr(
        verify, "read_quota", lambda ca: {"remaining": 2, "limit": 60}
    )

    exit_code = verify.main([])

    assert exit_code == 2
    out = capsys.readouterr().out
    assert "Spent 0." in out
    assert "SIDRA_GITHUB_TOKEN" in out


def test_pagination_would_actually_be_exercised() -> None:
    """The one setting whose quiet reversion would make the run lie.

    `_iter_list_pages` follows a Link header only when the item limit exceeds
    `per_page`, which caps at 100. Lower the limit to the default 50 and the
    pagination check still prints, still passes its own arithmetic, and never
    requests a second page - a verification that reports success without
    having verified anything.
    """

    source = (ROOT / "scripts" / "verify_real_github_api.py").read_text(encoding="utf-8")
    assert "max_items_per_source=150" in source, (
        "the item limit must stay above per_page's cap of 100, "
        "or the pagination check silently stops testing pagination"
    )


def test_the_runner_the_backlog_points_at_exists() -> None:
    """The gap that made this file necessary, kept closed.

    The backlog names a script and says it is ready to run. If that script
    stops existing, the backlog reverts to promising staged work that nobody
    can execute - which is what it was doing before this commit.
    """

    backlog = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    assert "scripts/verify_real_github_api.py" in backlog
    assert (ROOT / "scripts" / "verify_real_github_api.py").exists()


class _StubClient:
    """A client whose calls fail the way an emptied window fails."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def get_repository(self, repo):  # noqa: D102
        raise self._error

    def get_head_sha(self, repo):  # noqa: D102
        raise self._error

    def list_commits(self, repo):  # noqa: D102
        raise self._error

    def compare(self, repo, base, head):  # noqa: D102
        raise self._error


def _run_with_stub(monkeypatch, error, remaining_after):
    """Drive main() past its quota gate with every request failing."""

    quotas = iter(({"remaining": 60, "limit": 60}, {"remaining": remaining_after, "limit": 60}))
    monkeypatch.setattr(verify, "read_quota", lambda ca: next(quotas, {"remaining": remaining_after, "limit": 60}))
    monkeypatch.setattr(verify, "HttpxTransport", lambda **kw: _Recorder())
    import sidra_ai.ingestion.github_client as gh

    monkeypatch.setattr(gh, "GitHubReadOnlyClient", lambda *a, **kw: _StubClient(error))
    return verify.main([])


def test_a_window_that_empties_mid_run_is_not_reported_as_a_failed_check(
    monkeypatch, capsys
) -> None:
    """The distinction the budget was supposed to protect, where it leaked.

    `BudgetedTransport` counts our own calls, so it cannot see the shared
    window emptying underneath a run that started with room. GitHub answers
    that with the same 403 a broken client draws. Filing it as `failed` is
    what left `payload shape: failed` in the backlog on 2026-08-19 with no
    cause - a defect recorded against code that had nothing wrong with it.
    """

    exit_code = _run_with_stub(
        monkeypatch,
        verify.GitHubAPIError("GitHub rate limited for /repos/x", status=403),
        remaining_after=0,
    )

    out = capsys.readouterr().out
    assert "not run (window emptied)" in out
    assert "failed" not in out, "an emptied window must never read as a failed check"
    assert exit_code == 2, "nothing was determined, which is not the same as failing"


def test_a_real_failure_is_still_called_a_failure(monkeypatch, capsys) -> None:
    """The other half: the escape hatch must not swallow genuine defects.

    If a quota-shaped excuse could absorb any error, the runner would report a
    broken normalizer as weather. With the window still open, a failure is the
    check's own and has to be recorded that way.
    """

    exit_code = _run_with_stub(
        monkeypatch,
        verify.GitHubAPIError("unexpected status 500 for /repos/x", status=500),
        remaining_after=57,
    )

    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "not run (window emptied)" not in out
    assert exit_code == 1
