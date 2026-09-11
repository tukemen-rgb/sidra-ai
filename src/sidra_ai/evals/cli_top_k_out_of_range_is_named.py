"""Does ``sidra-ask`` name ``--top-k`` when its value is out of range?

C-1661. ``ChatRequest.top_k`` is bounded ``1..20`` (schemas.py). A terminal
user who tries the most inviting flag - ``--top-k 50`` for more context,
``--top-k 0`` to turn retrieval off - used to get the request sent, rejected
with 422, and rendered as "入力が長すぎるか形式が不正。短くして再送する"
("your input is too long or malformed; shorten it and resend"). Editing the
*question* can never fix a bad ``--top-k``, so the one next step the CLI
offered pointed at the wrong thing - the same misdirection C-1223/C-1278 fixed
for other knobs. The bound is a fixed client-visible contract, so the CLI now
rejects an out-of-range value itself, before sending, naming the range.

The checks drive ``ask_cli.main`` with an injected client that records whether
a request was sent: an out-of-range value must fail as bad usage (exit 2)
without sending anything, and name the range; a valid value must pass through
to the request unchanged.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


class _RecordingClient:
    """Stands in for httpx.Client and records the requests main() sends."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.posts: list[dict] = []

    def post(self, url: str, json: dict):  # noqa: A002 - mirrors httpx signature
        self.posts.append(json)
        return _RecordingResponse()

    def close(self) -> None:  # pragma: no cover - injected clients are not owned
        pass


class _RecordingResponse:
    status_code = 200

    def json(self) -> dict:
        return {"answer": "ok", "citations": []}


def _run(argv: list[str]):
    """Run the CLI with a recording client; return (exit_code, stderr, client)."""
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import Settings

    # A loopback host with no token: authorization_header adds nothing and does
    # not refuse, so the only thing under test is the top-k gate.
    settings = Settings(host="127.0.0.1", port=8000)
    original = ask_cli.get_settings
    ask_cli.get_settings = lambda: settings
    client = _RecordingClient()
    err = io.StringIO()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = ask_cli.main(argv, client=client)
    finally:
        ask_cli.get_settings = original
    return code, err.getvalue(), client


@dataclass(frozen=True)
class TopKResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_top_k_out_of_range_is_named() -> TopKResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- out of range: bad usage (exit 2), nothing sent, the range named ---
    for value in (0, -1, 21, 100):
        code, err, client = _run(["質問", "--top-k", str(value)])
        add(code == 2, f"--top-k {value}: exit {code}, expected 2 (bad usage)")
        add(
            not client.posts,
            f"--top-k {value}: a request was sent for an out-of-range value",
        )
        add(
            "1" in err and "20" in err,
            f"--top-k {value}: the message does not name the 1..20 range: {err!r}",
        )

    # --- valid values (incl. the boundaries and the default): passed through ---
    for argv, expected in (
        (["質問"], 5),
        (["質問", "--top-k", "1"], 1),
        (["質問", "--top-k", "20"], 20),
    ):
        code, err, client = _run(argv)
        add(code == 0, f"{argv}: exit {code}, expected 0")
        add(
            len(client.posts) == 1 and client.posts[0].get("top_k") == expected,
            f"{argv}: request not sent with top_k={expected}: {client.posts}",
        )

    total = 18
    return TopKResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["TopKResult", "evaluate_cli_top_k_out_of_range_is_named"]
