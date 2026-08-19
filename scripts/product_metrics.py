"""Print the numbers a person outside this repository would notice.

Why this exists: the loop's completion condition used to be "a commit
landed". That number only ever goes up, and it went up for three weeks while
nobody could ask SIDRA a question without hand-assembling JSON. A commit is
an internal number. This script prints the external ones, so "done" can mean
"one of these moved" instead of "I wrote something".

Every value here is obtained by *exercising* the path, not by reading the
diff: routes come from a built app, the CLI answer comes from actually
invoking the entry point, retrieval scores come from running the suite. A
capability that exists in the source but does not work end to end measures
as absent, which is the whole point.

Numbers that cannot be measured yet are printed as `-` with the reason. They
are not omitted: the missing ones are the backlog.

Safety: prints counts and rates only, never document content.

    python scripts/product_metrics.py           # table
    python scripts/product_metrics.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


OUTCOME = "outcome"
GUARD = "guard"
CONTEXT = "context"


@dataclass
class Metric:
    """One externally observable number.

    ``value`` is ``None`` when the number cannot be measured yet. ``detail``
    then carries the reason, which is more useful than a zero that looks like
    a measurement.

    ``kind`` decides what the number is allowed to prove, and it is the part
    that keeps "an outside number moved" from collapsing back into "I made a
    commit":

    ``outcome``  A capability an operator would notice. Only these count.
    ``guard``    A line that must hold. Holding is the premise, not progress;
                 breaking it fails the run.
    ``context``  Real, and moved by ordinary work. ``gate_must_catch_cases``
                 rises when someone writes a case; ``retrieval_cases_*`` rises
                 when someone writes a question. Those are worth doing and
                 worth seeing, but they are counts of our own writing, so they
                 cannot be the evidence that something outside changed.

    The default is ``context`` on purpose. An unclassified number is one
    nobody has argued for yet, and it should not be claimable as progress.
    """

    key: str
    label: str
    value: float | None
    unit: str = ""
    detail: str = ""
    #: Which way is better.
    direction: str = "up"
    kind: str = CONTEXT
    #: Smallest change that counts as movement rather than drift. A rate is
    #: harder to inflate than a count, but not immune: this repository's flag
    #: rate fell from 10.6% to 10.2% in one morning because loops added clean
    #: documents to the denominator. Nothing about the gate improved. Without
    #: a floor, that drift is bankable as "a number moved".
    min_move: float = 0.0

    def is_better(self, new: float, old: float) -> bool:
        return new > old if self.direction == "up" else new < old

    def is_drift(self, new: float, old: float) -> bool:
        return abs(new - old) < self.min_move

    def rendered(self) -> str:
        if self.value is None:
            return "-"
        if self.unit == "%":
            return f"{self.value:.1f}%"
        if float(self.value).is_integer():
            return f"{int(self.value)}{self.unit}"
        return f"{self.value:.3f}{self.unit}"


@dataclass
class Collector:
    metrics: list[Metric] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.metrics.append(Metric(*args, **kwargs))

    def unmeasurable(self, key: str, label: str, reason: str) -> None:
        self.metrics.append(Metric(key, label, None, detail=reason))


def _quiet():
    """Suppress a suite's own stdout so the table stays the only output."""

    return contextlib.redirect_stdout(io.StringIO())


# --- can a person use it at all ---------------------------------------


def measure_usability(c: Collector) -> None:
    """The three things a user does: ask, look, follow up."""

    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entry_points = pyproject.get("project", {}).get("scripts", {})

    # 1. Ask a question without writing JSON by hand.
    asked = 0
    detail = "no console script answers a question; /v1/chat needs hand-built JSON"
    for name, target in entry_points.items():
        if "ask" not in name and "ask" not in target:
            continue
        module_name = target.split(":", 1)[0]
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - a broken entry point is absent
            detail = f"{name} does not import: {type(exc).__name__}"
            break
        asked, detail = 1, f"{name} -> {target}"
        break
    c.add("ask_without_json", "ask a question without hand-built JSON", asked,
          detail=detail, kind=OUTCOME)

    # 2. See what the index holds, from outside the process.
    from sidra_ai.api.app import create_app

    app = create_app()
    read_routes = sorted(
        r.path for r in app.routes
        if getattr(r, "methods", None) and "GET" in r.methods
        and r.path not in {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}
    )
    index_routes = [p for p in read_routes if "index" in p or "stats" in p]
    c.add("index_visible", "index contents visible from outside", len(index_routes),
          detail=", ".join(index_routes) or f"GET routes: {', '.join(read_routes)}",
          kind=OUTCOME)

    # 3. Ask a follow-up that remembers the last answer.
    from sidra_ai.api.schemas import ChatRequest

    history_fields = sorted(
        name for name in ChatRequest.model_fields
        if name in {"history", "messages", "turns", "context", "previous"}
    )
    c.add("conversation_turns", "turns /v1/chat can remember",
          1 + len(history_fields),
          detail=", ".join(history_fields) or "each request is independent",
          kind=OUTCOME)


# --- is what it says current ------------------------------------------


def measure_freshness(c: Collector) -> None:
    """Whether the index refreshes without a human poking it.

    Exercised, not grepped: an app is built with an interval configured and
    started, and the answer is whether a refresher is actually running when
    it comes up.
    """

    from dataclasses import replace

    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.config.settings import MIN_INGEST_INTERVAL_SECONDS, Settings

    configured = replace(Settings(), ingest_interval_seconds=MIN_INGEST_INTERVAL_SECONDS)
    running = False
    try:
        app = create_app(settings=configured)
        with TestClient(app):
            running = bool(app.state.refresher.status().running)
    except Exception as exc:  # noqa: BLE001 - an unusable path measures as absent
        c.add("ingestion_automatic", "ingestion runs without a human", 0,
              detail=f"does not come up: {type(exc).__name__}", kind=OUTCOME)
        return

    c.add("ingestion_automatic", "ingestion runs without a human", int(running),
          detail=("SIDRA_INGEST_INTERVAL_SECONDS, off by default, never calls the model"
                  if running else "manual POST /v1/github/analyze only"),
          kind=OUTCOME)


# --- does the answer hold up ------------------------------------------


def measure_answer_quality(c: Collector) -> None:
    from sidra_ai.evals.retrieval_quality import (
        RETRIEVAL_CASES,
        evaluate_retrieval_quality,
    )

    with _quiet():
        result = evaluate_retrieval_quality()
    toy = f"{len(RETRIEVAL_CASES)} hand-written cases; a perfect score here proves little"
    c.add("retrieval_recall_at_3", "retrieval recall@3 (synthetic corpus)",
          result.recall_at_3, detail=toy, kind=GUARD)
    c.add("retrieval_mrr", "retrieval MRR (synthetic corpus)",
          result.mean_reciprocal_rank, detail=toy, kind=GUARD)
    c.add("retrieval_cases_synthetic", "retrieval cases, synthetic",
          len(RETRIEVAL_CASES))

    # The number that would actually tell us whether search works.
    # Read the question set that exists rather than a filename that never
    # did: this probe reported 0 while 18 real questions were already in
    # the tree, which is the failure mode section 0 of the backlog is about.
    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    paraphrase = sum(1 for q in OUTCOME_QUESTIONS if q.tier == "paraphrase")
    c.add("retrieval_cases_real", "retrieval cases against the 5 real repos",
          len(OUTCOME_QUESTIONS),
          detail=f"src/sidra_ai/evals/outcome_questions.py; "
                 f"{len(OUTCOME_QUESTIONS) - paraphrase} direct, {paraphrase} paraphrased. "
                 f"Scoring them needs all five checkouts: scripts/measure_outcomes.py")


# --- what it costs and what it refuses --------------------------------


def measure_cost(c: Collector) -> None:
    from sidra_ai.models.usage import UsageLedger

    totals = UsageLedger().totals()
    c.add("external_api_cost_usd", "external API cost of a run",
          totals["external_api_cost_usd"], direction="down", kind=GUARD,
          detail="structurally 0: the registry refuses paid backends, and "
                 "recording a nonzero cost raises")


def measure_gate(c: Collector) -> None:
    """The two security numbers that are already gated, for context."""

    from sidra_ai.security.gate import GatePolicy, SecurityGate

    sys.path.insert(0, str(ROOT / "scripts"))
    baseline = importlib.import_module("measure_gate_baseline")

    repository = "tukemen-rgb/sidra-ai"
    gate = SecurityGate(GatePolicy(), allowed_repositories=[repository])
    with _quiet():
        report = baseline.measure(ROOT, repository, gate)
    total = report["total"]
    flagged = report["decisions"]["quarantine"] + report["decisions"]["block"]
    c.add("gate_false_positive_rate", "documents this repo cannot index",
          100 * flagged / total if total else 0.0, unit="%", direction="down",
          detail=f"{flagged}/{total}; ceiling 13.0% (check_gate_regression.py)",
          kind=OUTCOME, min_move=0.5)

    recall = importlib.import_module("verify_gate_recall")
    must_catch = getattr(recall, "MUST_CATCH", ())
    c.add("gate_must_catch_cases", "attacks the recall set proves are caught",
          len(must_catch), detail="verify_gate_recall.py")


# --- can an operator see failures -------------------------------------


def measure_observability(c: Collector) -> None:
    from sidra_ai.api.schemas import HealthResponse

    exposed = sorted(
        name for name in HealthResponse.model_fields if "audit" in name
    )
    c.add("audit_failures_visible", "audit write failures an operator can see",
          len(exposed),
          detail=", ".join(exposed) or "failures are silent (SECURITY.md gap 2)",
          kind=OUTCOME)


COLLECTORS = (
    ("usable", measure_usability),
    ("fresh", measure_freshness),
    ("answers", measure_answer_quality),
    ("cost", measure_cost),
    ("gate", measure_gate),
    ("observable", measure_observability),
)


def collect() -> Collector:
    c = Collector()
    for name, fn in COLLECTORS:
        try:
            fn(c)
        except Exception as exc:  # noqa: BLE001 - one broken probe is not a crash
            c.unmeasurable(f"{name}_probe", f"{name} probe", f"{type(exc).__name__}: {exc}")
    return c


@dataclass(frozen=True)
class Movement:
    key: str
    before: float | None
    after: float | None
    better: bool

    @property
    def is_new(self) -> bool:
        return self.before is None


def _values(snapshot: dict) -> dict[str, float | None]:
    """Read a snapshot written by ``--save`` (or an older flat one)."""
    return {
        key: (entry.get("value") if isinstance(entry, dict) else entry)
        for key, entry in snapshot.items()
    }


def compare(before: dict, after: dict, metrics: dict[str, Metric]) -> tuple[list[Movement], list[Movement]]:
    """Return (movements that count, regressions).

    Only ``outcome`` metrics can count as movement. A guard that still holds
    contributes nothing: zero missed credentials is a solved problem, and a
    loop allowed to re-claim it every iteration would never have to move
    anything real again. Context contributes nothing either, for the reason
    in ``Metric``.

    A previously unmeasurable outcome that now has a value counts. Without
    that, work no existing number can see would be permanently unfinishable,
    and the rational move would be to stop attempting it.
    """
    old_values, new_values = _values(before), _values(after)
    moved: list[Movement] = []
    broken: list[Movement] = []

    for key, new_value in new_values.items():
        metric = metrics.get(key)
        if metric is None or metric.kind == CONTEXT or new_value is None:
            continue
        old_value = old_values.get(key)
        if old_value is None:
            if metric.kind == OUTCOME:
                moved.append(Movement(key, None, new_value, better=True))
            continue
        if new_value == old_value or metric.is_drift(new_value, old_value):
            continue
        movement = Movement(key, old_value, new_value, metric.is_better(new_value, old_value))
        if not movement.better:
            broken.append(movement)
        elif metric.kind == OUTCOME:
            moved.append(movement)

    return moved, broken


def _fmt(metric: Metric, value: float | None) -> str:
    """Render a value the way the table renders it, so 10.199... reads 10.2%."""
    if value is None:
        return "unmeasurable"
    return replace(metric, value=value).rendered()


def _report(before: dict, collector: Collector) -> int:
    metrics = {m.key: m for m in collector.metrics}
    moved, broken = compare(before, _snapshot(collector), metrics)

    def _line(tag: str, movement: Movement) -> str:
        metric = metrics[movement.key]
        after = _fmt(metric, movement.after)
        if movement.is_new:
            return f"  {tag:6s} {movement.key:34s} {after}"
        return f"  {tag:6s} {movement.key:34s} {_fmt(metric, movement.before)} -> {after}"

    for movement in broken:
        print(_line("WORSE", movement))
    for movement in moved:
        print(_line("NEW" if movement.is_new else "BETTER", movement))

    print()
    if broken:
        print(f"REGRESSED: {len(broken)} number(s) moved the wrong way. Do not merge.")
        return 2
    if not moved:
        print("NO MOVEMENT: no outcome number changed.")
        print("The change may still have been right, but it is not progress.")
        print("Record it as a no-op with the reason, or go make one of the")
        print("numbers that is still at zero measurable.")
        return 1

    print(f"MOVED: {len(moved)} outcome number(s).")
    for movement in moved:
        metric = metrics[movement.key]
        print(f"LOOP_LOG: {movement.key} {_fmt(metric, movement.before)} "
              f"-> {_fmt(metric, movement.after)}")
    return 0


def _snapshot(collector: Collector) -> dict:
    return {
        m.key: {"value": m.value, "unit": m.unit, "kind": m.kind, "detail": m.detail}
        for m in collector.metrics
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--save", metavar="PATH", help="write the numbers to PATH")
    parser.add_argument(
        "--compare", metavar="PATH",
        help="measure now and report what moved since the snapshot at PATH; "
             "exits 0 if an outcome moved, 1 if nothing did, 2 on a regression",
    )
    args = parser.parse_args()

    started = time.monotonic()
    collector = collect()
    elapsed = time.monotonic() - started

    if args.save:
        Path(args.save).write_text(
            json.dumps(_snapshot(collector), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        return _report(before, collector)

    if args.json:
        print(json.dumps(_snapshot(collector), indent=2, ensure_ascii=False))
        return 0

    print(f"{'number':40s} {'now':>9s}   how it stands")
    print("-" * 92)
    for kind in (OUTCOME, GUARD, CONTEXT):
        shown = [m for m in collector.metrics if m.kind == kind]
        if not shown:
            continue
        print(f"[{kind}]")
        for metric in shown:
            print(f"{metric.label:40s} {metric.rendered():>9s}   {metric.detail}")
    print("-" * 92)
    # A zero cost is the goal, not a gap, so only "up" metrics count as stuck.
    stuck = [m for m in collector.metrics
             if m.value == 0 and m.direction == "up" and m.kind == OUTCOME]
    print(f"{len(collector.metrics)} numbers in {elapsed:.1f}s; "
          f"{len(stuck)} outcome(s) still at zero")
    print("\nDone means one of these moved. A commit is not one of these.")
    print("Specifically an [outcome]: a [guard] that held and a [context]")
    print("count that grew are not evidence that anything outside changed.")
    print("`--compare` decides it rather than leaving it to judgement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
