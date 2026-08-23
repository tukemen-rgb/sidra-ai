"""CI gate: fail when the security gate's false-positive rate regresses.

The rate was measured and written down, and nothing enforced it. A change
that doubled it passed CI, so the measurement was a habit rather than a
control - and habits are exactly what stop happening at 3am on a Friday.

This measures the checked-out repository, which CI always has, and compares
against a ceiling rather than an exact figure. An exact match would break on
every ordinary commit that adds a file; a ceiling only moves when something
actually gets noisier.

Raising the ceiling is allowed, but it has to be a deliberate edit to this
file with a reason in the commit message. That is the whole mechanism: make
the regression visible and make accepting it a decision someone signs.

No detected value is ever printed - see scripts/measure_gate_baseline.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.security.decisions import Decision  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

REPOSITORY = "tukemen-rgb/sidra-ai"

#: Ceiling for the share of this repository's own documents the gate refuses
#: to index. Measured at 10.1% on 2026-08-18.
#:
#: This repository is the pessimistic case on purpose: it is a security
#: codebase, so its detectors, envelope and their tests legitimately contain
#: injection strings and synthetic credentials. Documents describing attacks
#: get quarantined, which is correct behaviour and also why the number is high.
#: Ordinary repositories measure between 0% and 3%.
#:
#: The ceiling sits at 13% rather than just above the measurement. Too tight
#: and the build breaks every time someone adds a security test, which trains
#: people to raise the number without reading it - the exact failure this
#: check exists to prevent. 13% still catches the regression that matters: a
#: change that makes the gate meaningfully noisier moves this by several
#: points at once, not by fractions.
MAX_FLAG_RATE = 0.13

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".py", ".toml", ".yml", ".yaml"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", ".sidra"}


def _documents(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if content.strip():
            yield path.relative_to(root).as_posix(), content


#: How many commit messages the flag rate is measured over. They are part of
#: the corpus because the real index holds them, and they are also - measured
#: 2026-08-23 - uniformly clean: 0 of 200 flagged, against 18.0% of the files.
#: The blend is therefore diluted by design, and the number only means what it
#: says when the full window is actually there.
COMMIT_WINDOW = 200

#: Exit code for "this environment cannot judge", kept distinct from 1
#: ("the ceiling was exceeded"). A shallow clone shrinks the denominator
#: without changing the gate, so reporting it as a regression sends whoever
#: reads it looking for a change that does not exist - which is what happened
#: on 2026-08-23, twice, before the cause was found.
EXIT_CANNOT_JUDGE = 3


def _history_depth(root: Path) -> int:
    """How many commits this checkout actually has.

    A fresh CCR container clones shallow (52 commits, measured). The walk
    below then finds 52 clean messages instead of 200, the denominator drops
    by a third, and a gate that has not changed at all posts 14.9% against a
    13% ceiling.
    """

    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        return int(out.stdout.strip() or 0)
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0


def _commit_messages(root: Path, limit: int = COMMIT_WINDOW):
    try:
        out = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%H%x00%s%n%b%x01"],
            cwd=root, capture_output=True, text=True, timeout=120,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return
    for record in out.split("\x01"):
        if "\x00" not in record:
            continue
        sha, message = record.split("\x00", 1)
        if sha.strip() and message.strip():
            yield f"commit/{sha.strip()[:12]}", message


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    depth = _history_depth(root)
    if depth < COMMIT_WINDOW:
        print(
            f"CANNOT JUDGE: this checkout has {depth} commits, fewer than the "
            f"{COMMIT_WINDOW} the flag rate is measured over.",
            file=sys.stderr,
        )
        print(
            "The gate is unchanged; the denominator is short. Measuring "
            "anyway would report a false regression - deepen the clone "
            "(`git fetch --unshallow`) and run this again.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_JUDGE

    gate = SecurityGate(GatePolicy(), allowed_repositories=(REPOSITORY,))

    decisions: Counter[str] = Counter()
    detectors: Counter[str] = Counter()
    flagged: list[tuple[str, str]] = []

    sources = list(_documents(root)) + list(_commit_messages(root))
    for ref, content in sources:
        result = gate.inspect(content, source="github", repository=REPOSITORY)
        decisions[result.decision.value] += 1
        for finding in result.findings:
            detectors[finding.detector] += 1
        if result.decision is not Decision.ALLOW:
            worst = max(
                result.findings,
                key=lambda f: {"critical": 3, "high": 2, "medium": 1, "low": 0}[
                    f.severity.value
                ],
                default=None,
            )
            flagged.append((ref, worst.detector if worst else "?"))

    total = sum(decisions.values())
    if not total:
        print("no documents measured - the corpus walk found nothing", file=sys.stderr)
        return 1

    refused = decisions["quarantine"] + decisions["block"]
    rate = refused / total

    print(f"documents      : {total}")
    print(f"allowed        : {decisions['allow']}")
    print(f"quarantined    : {decisions['quarantine']}")
    print(f"blocked        : {decisions['block']}")
    print(f"flag rate      : {rate:.1%}  (ceiling {MAX_FLAG_RATE:.1%})")
    print("\ntop detectors:")
    for name, count in detectors.most_common(8):
        print(f"  {name:28s} {count}")

    if rate > MAX_FLAG_RATE:
        print(
            f"\nFAILED: the gate now refuses {rate:.1%} of this repository, above "
            f"the {MAX_FLAG_RATE:.1%} ceiling.",
            file=sys.stderr,
        )
        print(
            "A gate that cries wolf gets ignored, and an ignored gate is not a "
            "gate. Either fix the false positives, or raise MAX_FLAG_RATE in "
            "this file with a reason in the commit message.",
            file=sys.stderr,
        )
        print("\nnewly refused documents (values withheld):", file=sys.stderr)
        for ref, detector in flagged[:25]:
            print(f"  {detector:26s} {ref}", file=sys.stderr)
        return 1

    print(f"\nOK: {rate:.1%} is within the {MAX_FLAG_RATE:.1%} ceiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
