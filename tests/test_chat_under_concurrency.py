"""The whole answer path, from many threads at once, must finish and agree.

Five locks were added across the service in one day - the index, the vector
memo, the model load, the rate limiter, the GitHub client. Each is correct on
its own; locks are dangerous in combination, and the combination is what a
thread pool exercises. The orders that exist are index -> shortlist and
load -> nothing, with the memo taken alone, so there is no cycle to find by
reading. This is the reading checked against what actually runs.

Two things are asserted, and neither is a timing measurement: every call
returns (a deadlock shows up as a thread that never finishes), and the index
still describes itself afterwards. A future lock that introduces a cycle
fails the first; one that lets the rebuild interleave again fails the second.

Creation and revision requests are in the mix on purpose - they take different
paths through the same service, and a lock ordering that only holds for
questions would be a lock ordering that holds by luck.
"""

from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.config.settings import Settings  # noqa: E402
from sidra_ai.documents import (  # noqa: E402
    Document,
    Provenance,
    SourceType,
    TrustLevel,
)
from sidra_ai.api.service import SidraService  # noqa: E402
from sidra_ai.ingestion.state import StateStore  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPO = "owner/alpha"
_THREADS = 10
_EACH = 4

_ASKS = [
    "競合はどこですか",
    "収益化の方針を教えて",
    "審査の基準は",
    "釣りゲームを作って",
    "さっきのゲームを難しくして",
    "個人情報の扱い",
]


def _store() -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for i in range(12):
        store.add(
            Document(
                content=(
                    f"第 {i} 章。収益化の方針と審査の基準について。"
                    + "掲載順は売らない。個人情報は公開の場所へ置かない。" * 8
                ),
                provenance=Provenance(
                    source="github",
                    repository=_REPO,
                    path=f"docs/part{i}.md",
                    commit_sha="0" * 40,
                    timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    return store


def test_many_threads_asking_at_once_all_finish_and_agree(tmp_path) -> None:
    store = _store()
    settings = Settings(
        data_dir=str(tmp_path),
        model_backend="echo",
        allowed_repositories=(_REPO,),
    )
    service = SidraService(
        settings,
        store=store,
        gate=store._gate if hasattr(store, "_gate") else None,
        state_store=StateStore(tmp_path / "state.json"),
    )
    service.chat(_ASKS[0])  # warm, so the storm is not all first-index

    errors: list[str] = []
    answered: list[str] = []
    guard = threading.Lock()
    ready = threading.Barrier(_THREADS)

    def worker(index: int) -> None:
        try:
            ready.wait(timeout=60)
            for step in range(_EACH):
                ask = _ASKS[(index + step) % len(_ASKS)]
                result = service.chat(ask)
                with guard:
                    answered.append(ask)
                assert isinstance(result, dict)
        except Exception as exc:  # noqa: BLE001 - the failure is the finding
            with guard:
                errors.append(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        # Generous: this is a deadlock detector, not a speed limit.
        thread.join(timeout=180)

    still_running = [t for t in threads if t.is_alive()]
    assert not still_running, (
        f"{len(still_running)} thread(s) never finished - a lock cycle would "
        "look exactly like this"
    )
    assert not errors, errors[0]
    assert len(answered) == _THREADS * _EACH

    lexical = getattr(service.retriever, "_lexical", service.retriever)
    assert len(lexical._term_frequencies) == len(lexical._chunks)
    assert len(lexical._lengths) == len(lexical._chunks)


def test_ingesting_during_the_storm_does_not_wedge_it(tmp_path) -> None:
    """Background ingestion writes while the answer path reads."""

    store = _store()
    settings = Settings(
        data_dir=str(tmp_path),
        model_backend="echo",
        allowed_repositories=(_REPO,),
    )
    service = SidraService(
        settings,
        store=store,
        gate=store._gate if hasattr(store, "_gate") else None,
        state_store=StateStore(tmp_path / "state.json"),
    )
    service.chat(_ASKS[0])

    stop = threading.Event()
    errors: list[str] = []

    def writer() -> None:
        i = 100
        while not stop.is_set() and i < 130:
            store.add(
                Document(
                    content=f"後から足した第 {i} 章。審査の基準について。" * 6,
                    provenance=Provenance(
                        source="github",
                        repository=_REPO,
                        path=f"docs/late{i}.md",
                        commit_sha="0" * 40,
                        timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                        source_type=SourceType.DOCS,
                        trust_level=TrustLevel.INTERNAL_REPO,
                        license="proprietary",
                    ),
                )
            )
            i += 1

    def asker() -> None:
        try:
            for _ in range(6):
                service.chat("審査の基準は")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=asker) for _ in range(6)]
    scribe = threading.Thread(target=writer)
    scribe.start()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    stop.set()
    scribe.join(timeout=60)

    assert not [t for t in threads if t.is_alive()]
    assert not errors, errors[0]

    lexical = getattr(service.retriever, "_lexical", service.retriever)
    service.chat("審査の基準は")
    assert len(lexical._term_frequencies) == len(lexical._chunks)
    assert len(lexical._chunks) == len(tuple(store.chunks()))
