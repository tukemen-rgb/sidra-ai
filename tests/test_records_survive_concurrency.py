"""C-1862: the creation record has to survive being written by two threads.

Both appenders in ``creation/records.py`` read the whole log, splice one
line in and write the whole log back. Nothing held those two halves
together, so the second writer read the log before the first record was in
it and then wrote that record away.

What it cost, measured before the fix - twelve threads, eight records each,
five runs: **11, 4, 7, 3 and 15 of 96 records kept**. The
``UnicodeDecodeError`` that got this filed appeared in 3 of the 5 runs. The
silent loss of about nine records in ten appeared in 5 of 5, which is the
part nobody would have noticed: the module exists so that 「この game.html
はいつ・何から作られたか」 has an answer a week later.
"""

from __future__ import annotations

import threading
from pathlib import Path

from sidra_ai.creation.records import (
    LOG_NAME,
    RECORDS_HEADING,
    STANDALONE_LOG_NAME,
    append_record,
    append_standalone_record,
)
from sidra_ai.evals.records_survive_concurrency import (
    evaluate_records_survive_concurrency,
)


def _storm(work, threads: int = 8, each: int = 6) -> list[str]:
    errors: list[str] = []
    guard = threading.Lock()
    ready = threading.Barrier(threads)

    def worker(index: int) -> None:
        try:
            ready.wait(timeout=30)
            for step in range(each):
                work(index, step)
        except Exception as exc:  # noqa: BLE001 - the failure is the finding
            with guard:
                errors.append(f"{type(exc).__name__}: {exc}")

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join(timeout=60)
    return errors


def _kept(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().startswith("- "))


def test_no_standalone_record_is_lost_when_threads_write_at_once(tmp_path) -> None:
    errors = _storm(
        lambda i, k: append_standalone_record(
            str(tmp_path), made=[f"game-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
        )
    )

    assert not errors, errors[0]
    kept = _kept((tmp_path / STANDALONE_LOG_NAME).read_text("utf-8", errors="replace"))
    assert kept == 48, (
        f"{kept} of 48 records survived - a record written and then silently "
        "thrown away is worse than one that fails loudly"
    )


def test_the_project_log_has_the_same_protection(tmp_path) -> None:
    """Fixing only the appender that happened to be caught is half a fix."""

    (tmp_path / LOG_NAME).write_text(f"# log\n\n{RECORDS_HEADING}\n\n", encoding="utf-8")

    errors = _storm(
        lambda i, k: append_record(
            str(tmp_path), made=[f"made-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
        )
    )

    assert not errors, errors[0]
    assert _kept((tmp_path / LOG_NAME).read_text("utf-8", errors="replace")) == 48


def test_a_reader_never_sees_the_log_shrink(tmp_path) -> None:
    """The atomic replace, not the lock: readers take no lock at all.

    Written this way after the first version - which waited for a
    ``UnicodeDecodeError`` - passed on a build that kept the lock and went
    back to writing in place. The truncate window is microseconds and a
    reader almost never lands in it; a reader that watches the record count
    *shrink* catches it every time.
    """

    log_path = Path(tmp_path) / STANDALONE_LOG_NAME
    seed = "\n".join(f"- seeded {i} " + "x" * 80 for i in range(400))
    log_path.write_text(f"# log\n\n{RECORDS_HEADING}\n\n{seed}\n", encoding="utf-8")
    floor = _kept(log_path.read_text("utf-8"))

    torn: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        seen = 0
        while not stop.is_set():
            try:
                now = _kept(log_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, UnicodeDecodeError) as exc:
                torn.append(f"a reader saw a half-written log: {exc}")
                return
            if now < seen:
                torn.append(f"the log shrank from {seen} records to {now}")
                return
            seen = max(seen, now)

    watchers = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
    for watcher in watchers:
        watcher.start()
    errors = _storm(
        lambda i, k: append_standalone_record(
            str(tmp_path), made=[f"game-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
        )
    )
    stop.set()
    for watcher in watchers:
        watcher.join(timeout=30)

    assert not errors, errors[0]
    assert not torn, torn[0]
    assert _kept(log_path.read_text("utf-8")) == floor + 48


def test_the_judge_agrees_and_says_so() -> None:
    result = evaluate_records_survive_concurrency()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total == 3


def test_the_appender_leaves_no_temp_file_beside_the_log(tmp_path) -> None:
    """The atomic write writes a neighbour first; it must not stay one."""

    _storm(
        lambda i, k: append_standalone_record(
            str(tmp_path), made=[f"game-{i}-{k}.html"], evidence=[], parameters={}
        )
    )

    leftovers = [p.name for p in Path(tmp_path).iterdir() if p.name != STANDALONE_LOG_NAME]
    assert not leftovers, f"litter beside the log a person reads: {leftovers}"
