"""Two first requests must not each build the thing the other is building.

Both of these are "if it is not there yet, make it" under a server that
answers from a thread pool, so two questions arriving together can each find
nothing and each start building. Neither corrupts anything - the loser's copy
is simply thrown away - but what gets thrown away matters:

* the embedding model is ~470 MB of weights loaded onto a card that is already
  mostly occupied by the language model. Two at once on a 6 GB card is not
  waste, it is an out-of-memory error at the worst possible moment.
* a GitHub client owns a connection pool and its own view of the read budget.
  The allowlisted read quota was sized for one.

Both are tested by construction rather than by hoping the race shows up:
the build is made slow on purpose, so every thread is guaranteed to be inside
the window at the same time. A test that only fails when the scheduler
cooperates is a test that will be deleted the first time it flakes.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.retrieval.embedding import SentenceTransformerBackend  # noqa: E402

_THREADS = 8


def test_the_embedding_model_is_loaded_once_however_many_ask(
    monkeypatch, tmp_path
) -> None:
    """Runs the real loader, with only the library underneath it replaced.

    Patching the method that holds the lock would test the stand-in rather
    than the code - the first draft of this did exactly that and passed on
    broken code, because the stub left out the second check the real one
    makes after waiting.
    """

    import types

    loads = {"n": 0}

    class _SlowModel:
        def __init__(self, path, local_files_only=False) -> None:
            loads["n"] += 1
            # Long enough that every thread is certainly inside the window.
            time.sleep(0.05)

    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _SlowModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)

    backend = SentenceTransformerBackend(str(tmp_path))
    ready = threading.Barrier(_THREADS)
    results: list[bool] = []

    def ask() -> None:
        ready.wait(timeout=30)
        results.append(backend.available())

    threads = [threading.Thread(target=ask) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert loads["n"] == 1, "the weights were loaded more than once"
    assert results and all(results)


def test_a_loaded_backend_answers_without_taking_the_lock() -> None:
    """Once loaded this is on every semantic query; it must not serialise."""

    backend = SentenceTransformerBackend("/nonexistent-for-this-test")
    backend._model = object()
    backend._load_lock.acquire()
    try:
        # If `available` took the lock unconditionally this would block until
        # the timeout rather than return.
        done = threading.Event()

        def ask() -> None:
            if backend.available():
                done.set()

        thread = threading.Thread(target=ask)
        thread.start()
        thread.join(timeout=5)
        assert done.is_set()
    finally:
        backend._load_lock.release()


def test_the_github_client_is_built_once_however_many_ask(monkeypatch) -> None:
    from sidra_ai.api import service as service_module

    class _StubService:
        """Only the two attributes the property touches, plus its lock."""

        client = service_module.SidraService.client

        def __init__(self) -> None:
            self._client = None
            self._client_lock = threading.Lock()
            self.settings = object()

    built = {"n": 0}

    class _SlowClient:
        def __init__(self, settings) -> None:
            built["n"] += 1
            time.sleep(0.05)

    monkeypatch.setattr(service_module, "GitHubReadOnlyClient", _SlowClient)

    stub = _StubService()
    ready = threading.Barrier(_THREADS)
    seen: list[object] = []

    def ask() -> None:
        ready.wait(timeout=30)
        seen.append(stub.client)

    threads = [threading.Thread(target=ask) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert built["n"] == 1, "more than one client was created"
    assert seen and all(c is seen[0] for c in seen)
