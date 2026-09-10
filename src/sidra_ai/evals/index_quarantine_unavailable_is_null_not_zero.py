"""Does ``GET /v1/index`` distinguish "quarantine log unreadable" from "zero held"?

C-1631. The index report's contract (the closed item that built it) is explicit:
「quarantine ログが読めないときは 0 ではなく ``available: false`` を返す。0 は
『何も止まっていない』と読め、読めない監査ログの意味と正反対になる」. The service
honours it - ``_quarantine_summary`` returns only ``{"available": False}`` on a
read failure - but the Pydantic ``QuarantineSummary`` response model re-injects
its ``int = 0`` / ``{}`` defaults, so the HTTP body an operator sees carries
``available: false`` **and** ``total: 0, pending: 0, …`` - exactly the zeros the
contract, and the test ``…reports_unavailable_not_zero``'s own name, forbid.

The fix makes the count fields nullable: an unreadable log reports the counts as
``null`` (unknown), distinct from a readable-but-empty log's genuine ``0``.

The checks drive the real ``GET /v1/index`` over two states: a quarantine log
that cannot be read (a directory where the file belongs) and a readable-empty
one (no file yet).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

_COUNT_FIELDS = ("total", "releasable", "released", "pending")
_DICT_FIELDS = ("by_decision", "by_finding_category")


def _index_body(data_dir: str):
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    settings = Settings(allowed_repositories=("tukemen-rgb/sidra-ai",), data_dir=data_dir)
    service = SidraService(settings, model=EchoModelAdapter())
    api = TestClient(create_app(service, settings))
    return api.get("/v1/index").json()


@dataclass(frozen=True)
class IndexQuarantineNullResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_index_quarantine_unavailable_is_null_not_zero() -> IndexQuarantineNullResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- unreadable quarantine log: a directory where the file belongs ---
    unreadable = tempfile.mkdtemp()
    (Path(unreadable) / "quarantine.jsonl").mkdir()
    body = _index_body(unreadable)
    q = body.get("quarantine", {})

    add(q.get("available") is False, f"unreadable: available not False: {q.get('available')!r}")
    for field in _COUNT_FIELDS:
        add(q.get(field, 0) is None,
            f"unreadable: {field} is {q.get(field, 0)!r}, expected null (0 reads as 'nothing held')")
    for field in _DICT_FIELDS:
        add(q.get(field, {}) is None,
            f"unreadable: {field} is {q.get(field, {})!r}, expected null")
    # The rest of the report still works when quarantine cannot be read.
    add(body.get("documents") == 0, f"unreadable: documents not reported: {body.get('documents')!r}")

    # --- readable, empty quarantine log: a genuine zero, an int not null ---
    readable = tempfile.mkdtemp()
    body2 = _index_body(readable)
    q2 = body2.get("quarantine", {})
    add(q2.get("available") is True, f"readable: available not True: {q2.get('available')!r}")
    add(q2.get("total") == 0 and isinstance(q2.get("total"), int),
        f"readable-empty: total not int 0: {q2.get('total')!r}")
    add(q2.get("pending") == 0 and isinstance(q2.get("pending"), int),
        f"readable-empty: pending not int 0: {q2.get('pending')!r}")
    add(q2.get("by_decision") == {} and q2.get("by_decision") is not None,
        f"readable-empty: by_decision not empty dict: {q2.get('by_decision')!r}")

    total = 1 + len(_COUNT_FIELDS) + len(_DICT_FIELDS) + 1 + 1 + 1 + 1 + 1
    return IndexQuarantineNullResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "IndexQuarantineNullResult",
    "evaluate_index_quarantine_unavailable_is_null_not_zero",
]
