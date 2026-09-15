"""Does the creation record survive being written by several threads?

C-1862. Both appenders in ``creation/records.py`` read the whole log, splice
one line in, and write the whole log back, with nothing holding those two
halves together. Measured before anything was changed - twelve threads
appending eight records each, five times over:

    records kept: 11/96, 4/96, 7/96, 3/96, 15/96
    UnicodeDecodeError raised in 3 of the 5 runs

So the crash that got this filed was the quiet part. The loud part is that
about nine records in ten were **silently thrown away**: the second thread
to write had read the log before the first thread's record was in it. The
module exists so that 「この game.html はいつ・何から作られたか」 has an
answer a week later, and under concurrency it mostly answered "no record" -
with nothing raised, nothing logged and nothing to notice.

Two separate properties are measured, because two separate things were
wrong and one fix does not imply the other:

* **A and B** - every record survives. That is the lock's job.
* **C** - a reader never sees a half-written log. That is the atomic
  replace's job, and the lock does not provide it: readers do not take the
  lock, so a truncating write is visible to them however well the writers
  are serialised.

The counts are deliberately the judge rather than the exception: "it did not
crash" was true of 2 of the 5 broken runs, and both of those had lost more
than eighty records.
"""

from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

#: Enough contention to lose records reliably on the broken version (five
#: runs out of five), small enough to cost a collector run milliseconds.
_THREADS = 8
_EACH = 6


@dataclass(frozen=True)
class RecordsConcurrencyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _storm(work) -> list[str]:
    """Run ``work(i, k)`` on every thread at once; return what went wrong."""

    errors: list[str] = []
    guard = threading.Lock()
    ready = threading.Barrier(_THREADS)

    def worker(index: int) -> None:
        try:
            ready.wait(timeout=30)
            for step in range(_EACH):
                work(index, step)
        except Exception as exc:  # noqa: BLE001 - the failure is the finding
            with guard:
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    still = [t for t in threads if t.is_alive()]
    if still:
        errors.append(f"{len(still)} thread(s) never finished - a lock cycle looks like this")
    return errors


def _kept(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().startswith("- "))


def evaluate_records_survive_concurrency() -> RecordsConcurrencyResult:
    from sidra_ai.creation.records import (
        LOG_NAME,
        RECORDS_HEADING,
        STANDALONE_LOG_NAME,
        append_record,
        append_standalone_record,
    )

    failures: list[str] = []
    passed = 0
    wanted = _THREADS * _EACH

    # A. the standalone log - the path the concurrency test actually walked.
    with tempfile.TemporaryDirectory() as home:
        errors = _storm(
            lambda i, k: append_standalone_record(
                home, made=[f"game-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
            )
        )
        kept = _kept(Path(home, STANDALONE_LOG_NAME).read_text("utf-8", errors="replace"))
        if errors:
            failures.append(f"standalone: {errors[0]}")
        elif kept != wanted:
            failures.append(f"standalone: {kept} of {wanted} records survived")
        else:
            passed += 1

    # B. and the project log, which has the same shape and the same race.
    #    Fixing only the one that happened to be caught is half a fix.
    with tempfile.TemporaryDirectory() as home:
        log = Path(home) / LOG_NAME
        log.write_text(f"# log\n\n{RECORDS_HEADING}\n\n", encoding="utf-8")
        errors = _storm(
            lambda i, k: append_record(
                home, made=[f"made-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
            )
        )
        kept = _kept(log.read_text("utf-8", errors="replace"))
        if errors:
            failures.append(f"project log: {errors[0]}")
        elif kept != wanted:
            failures.append(f"project log: {kept} of {wanted} records survived")
        else:
            passed += 1

    # C. ...and a reader running beside the writers never sees a partial
    #    log. Readers take no lock, so this is the atomic replace being
    #    measured, not the lock.
    #
    #    The first version of this rule watched for a UnicodeDecodeError and
    #    **did not catch** a version that kept the lock and went back to
    #    writing in place: the truncate-to-write window is microseconds, and
    #    a reader almost never lands inside it on a small file. It scored
    #    3/3 on code with the defect restored - a rule that cannot fail.
    #
    #    What does catch it is asking whether the log a reader sees ever
    #    **shrinks**. An in-place write truncates first, so a reader sees
    #    zero lines where it had just seen four hundred; an atomic replace
    #    can only ever show a complete version. Measured on a stand-in
    #    writer before it was written here: 3 of 3 with in-place writes, 0
    #    of 3 with the replace. The log is seeded large for the same reason
    #    - a bigger file spends longer between truncate and complete.
    with tempfile.TemporaryDirectory() as home:
        log_path = Path(home) / STANDALONE_LOG_NAME
        seed = "\n".join(f"- seeded {i} " + "x" * 80 for i in range(400))
        log_path.write_text(f"# log\n\n{RECORDS_HEADING}\n\n{seed}\n", encoding="utf-8")
        floor = _kept(log_path.read_text("utf-8"))
        torn: list[str] = []
        stop = threading.Event()

        def reader() -> None:
            seen = 0
            while not stop.is_set():
                try:
                    kept_now = _kept(log_path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    torn.append("the log was not there at all while it was being replaced")
                    return
                except UnicodeDecodeError as exc:
                    torn.append(f"a reader saw a half-written log: {exc}")
                    return
                if kept_now < seen:
                    torn.append(
                        f"a reader watched the log shrink from {seen} records to "
                        f"{kept_now} - it was being written in place"
                    )
                    return
                seen = max(seen, kept_now)

        watchers = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
        for watcher in watchers:
            watcher.start()
        errors = _storm(
            lambda i, k: append_standalone_record(
                home, made=[f"game-{i}-{k}.html"], evidence=[], parameters={"t": f"{i}-{k}"}
            )
        )
        stop.set()
        for watcher in watchers:
            watcher.join(timeout=30)
        final = _kept(log_path.read_text("utf-8", errors="replace"))
        if errors:
            failures.append(f"while a reader watched: {errors[0]}")
        elif torn:
            failures.append(torn[0])
        elif final != floor + wanted:
            failures.append(
                f"with readers watching, {final - floor} of {wanted} records survived"
            )
        else:
            passed += 1

    return RecordsConcurrencyResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=3,
        failures=tuple(failures),
    )
