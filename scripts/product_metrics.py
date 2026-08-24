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
sys.path.insert(0, str(Path(__file__).resolve().parent))


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

    def unmeasurable(self, key: str, label: str, reason: str, kind: str = CONTEXT) -> None:
        """Record a number this script cannot produce, and say why.

        ``kind`` matters for outcomes measured somewhere else: ``compare``
        counts a previously unmeasurable outcome that gains a value, so
        classifying one as context would quietly make that transition
        invisible.
        """
        self.metrics.append(Metric(key, label, None, detail=reason, kind=kind))


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

    # 4. Ask from a browser, with nothing installed.
    #
    # Exercised rather than grepped, and the bar is deliberately the whole
    # path: a page that is served but posts nowhere is not a way to ask a
    # question, and neither is one whose script tag lives on a CDN this
    # process cannot reach. So the page has to arrive as HTML, name the
    # endpoint it submits to, carry a text input, and be self-contained.
    from fastapi.testclient import TestClient

    served, detail = 0, "no GET route returns an HTML page"
    for path in ("/", "/ui"):
        with _quiet(), TestClient(create_app()) as client:
            response = client.get(path)
        if response.status_code != 200:
            continue
        if "text/html" not in response.headers.get("content-type", ""):
            detail = f"{path} answers, but not as HTML"
            continue
        body = response.text
        missing = [
            name
            for name, present in (
                ("posts to /v1/chat", "/v1/chat" in body),
                ("a text input", "<input" in body or "<textarea" in body),
                ("no external asset", not _references_external_asset(body)),
            )
            if not present
        ]
        if missing:
            detail = f"{path} is served but is missing: {', '.join(missing)}"
            continue
        served, detail = 1, f"GET {path} -> self-contained page posting to /v1/chat"
        break
    c.add("ask_from_browser", "ask a question from a browser", served,
          detail=detail, kind=OUTCOME)

    # 5. Check the answer against its evidence without leaving the response.
    #
    # Exercised end to end rather than grepped for a field name: a schema that
    # declares `excerpt` and a service that never fills it would score the same
    # as working evidence, and this number exists precisely because
    # repo/path/rank asks the operator to take the answer on faith.
    shown, detail = _measure_citation_evidence()
    c.add("citation_shows_evidence", "citations an operator can verify", shown,
          detail=detail, kind=OUTCOME)


def _measure_citation_evidence() -> tuple[int, str]:
    """Whether a real /v1/chat citation carries readable evidence.

    Runs against sidra-ai's own checkout, the one corpus that is always
    present. Returns 1 only when a citation comes back with a non-empty
    excerpt inside the declared cap - a withheld excerpt is honest but is not
    something an operator can verify, so it does not count.
    """

    import importlib.util

    from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    spec = importlib.util.spec_from_file_location(
        "_measure_outcomes_for_citations",
        Path(__file__).resolve().parent / "measure_outcomes.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    repo = "tukemen-rgb/sidra-ai"
    targets = [(repo, Path(__file__).resolve().parents[1])]
    try:
        with _quiet():
            gate = module.SecurityGate(
                module.GatePolicy(), allowed_repositories=[repo]
            )
            store = module.DocumentStore(gate)
            module.ingest(targets, store, gate)
            service = SidraService(
                Settings(allowed_repositories=(repo,)), store=store, gate=gate
            )
            response = service.chat("How does SIDRA treat retrieved content?")
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0, f"probe failed: {type(exc).__name__}: {exc}"

    citations = response.get("citations") or []
    if not citations:
        return 0, "chat returned no citations to carry evidence"
    with_text = [c for c in citations if c.get("excerpt")]
    if not with_text:
        withheld = sum(1 for c in citations if c.get("excerpt_withheld"))
        return 0, (
            f"{len(citations)} citation(s), none showing evidence"
            + (f" ({withheld} withheld by the output guard)" if withheld else "")
        )
    longest = max(len(c["excerpt"]) for c in with_text)
    return 1, (
        f"{len(with_text)}/{len(citations)} citations carry an excerpt; "
        f"longest {longest} chars, cap {MAX_CITATION_EXCERPT_CHARS}"
    )


def _references_external_asset(html: str) -> bool:
    """Whether the page would fetch anything off this host to work.

    A localhost-bound, CORS-free service that pulls a script from a CDN is
    broken exactly where it matters: on the operator's air-gapped machine,
    where the page loads and the button does nothing.
    """

    import re

    for match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", html):
        target = match.group(1).strip().lower()
        if target.startswith(("http://", "https://", "//")):
            return True
    return False


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


def _measure_self_grounded_locally() -> float:
    """Score the self-grounded questions against sidra-ai's own checkout.

    These are the one part of the outcome set whose evidence is in this
    repository, so unlike the rest of the set they can be scored without
    anybody else's clone being present.
    """

    import importlib.util

    from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS

    questions = [q for q in OUTCOME_QUESTIONS if q.self_grounded]
    if not questions:
        return 0.0

    spec = importlib.util.spec_from_file_location(
        "_measure_outcomes_for_self", Path(__file__).resolve().parent / "measure_outcomes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    targets = [("tukemen-rgb/sidra-ai", Path(__file__).resolve().parents[1])]
    with _quiet():
        gate = module.SecurityGate(
            module.GatePolicy(), allowed_repositories=["tukemen-rgb/sidra-ai"]
        )
        store = module.DocumentStore(gate)
        module.ingest(targets, store, gate)
        result = module.measure_answerable(module.BM25Retriever(store), targets)
    return float(result["self_grounded"]["answered"])


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

    # Count the headline set only. The self-grounded questions are scored
    # against sidra-ai, not against the five, so folding them in here would
    # overstate how much outside material the set actually covers.
    headline = [q for q in OUTCOME_QUESTIONS if not q.self_grounded]
    paraphrase = sum(1 for q in headline if q.tier == "paraphrase")
    # Named by a backlog item, and deliberately absent from this script: it
    # needs the four external checkouts, and cloning them here would make the
    # quick local report depend on somebody else's repositories being up. It
    # is registered rather than omitted because an item cannot promise to move
    # a number that does not exist, and because `compare` counts an outcome
    # that becomes measurable.
    # Read the enforced floor rather than restating a measurement. The line
    # used to end "(last measured 0/7)", which was true when written and
    # wrong within a day: the set grew to 26 questions and a paraphrase
    # question started retrieving. A number copied into a report has nothing
    # keeping it honest, and this one is read to decide whether the paraphrase
    # problem still exists - the worst place to be a day stale. A floor cannot
    # drift the same way; CI fails when it stops matching.
    import check_answerable_regression as answerable

    c.unmeasurable(
        "answerable_paraphrase",
        "paraphrased questions SIDRA can answer",
        "needs all five checkouts: scripts/check_answerable_regression.py "
        f"(enforced floor: {answerable.MIN_PARAPHRASE})",
        kind=OUTCOME,
    )

    # Same reason, one step further along the pipeline: `answered` says the
    # evidence came back, this says the operator can read the answer inside
    # the 200-character excerpt the citation carries. Scoring it needs the
    # same five checkouts, so it is unmeasurable here rather than approximated
    # from a corpus of one repository - an excerpt rate measured over sidra-ai
    # alone would describe a different corpus while wearing the same name.
    # GAMEYARD's design document: is it in the corpus, and does the question
    # it exists to answer return it. Both need the site checkout, so both are
    # unmeasurable here rather than approximated - and the second is the one
    # that matters, because an indexed document nobody can retrieve is the
    # failure this project keeps finding.
    c.unmeasurable(
        "design_source_cited",
        "GAMEYARD design principles citable",
        "needs all five checkouts: scripts/check_answerable_regression.py "
        "(reported as `design source`; cited at rank 1 with weights, rank 6 "
        "without - see C-986)",
        kind=OUTCOME,
    )

    # Ingestion against the real API. `ingestion_automatic` below says the
    # refresher runs; it says nothing about whether a run produces an index.
    # Between 2026-08-23 and 2026-08-24 every repository came back
    # `partial_fetch` with `indexed 0` because the token could not read pulls
    # or issues, and no number here moved - the instrument had nothing to say
    # about the one thing that was broken. Registering the name does not fix
    # that, but it stops the gap being invisible: whoever measures it against
    # the real API banks a value here.
    #
    # Not measured in this script on purpose. It needs a token and the
    # network, and this instrument is the one that has to run offline in
    # seconds; approximating it from a local corpus would report a number
    # about a program nobody runs.
    c.unmeasurable(
        "github_documents_indexed",
        "documents the real ingestion path indexed",
        "needs SIDRA_GITHUB_TOKEN and network: POST /v1/github/analyze over "
        "the five repositories (measured 482 on 2026-08-24; see "
        "docs/OUTCOMES.md)",
        kind=OUTCOME,
    )

    c.unmeasurable(
        "excerpt_hits_marker",
        "cited excerpts that contain the answer",
        "needs all five checkouts: scripts/check_answerable_regression.py "
        "(reported as `excerpt hit`; measured over answered questions only)",
        kind=OUTCOME,
    )

    # Unlike the four numbers above, this one needs only sidra-ai's own
    # checkout - the questions are grounded in docs/SECURITY.md - so it is
    # measured here for real rather than registered as unmeasurable.
    #
    # Measured over the sidra-ai corpus alone, which is the same rank the
    # five-repository run reports for these two questions (both rank 1;
    # checked 2026-08-21). If that ever stops being true the honest number is
    # the five-repository one, and this probe should go back to being
    # `unmeasurable` rather than quietly reporting the easier corpus.
    c.add("answerable_self", "self-grounded questions SIDRA can answer",
          _measure_self_grounded_locally(),
          detail="GDP #372 の 2 問。docs/SECURITY.md が根拠。"
                 "answerable_total / direct / paraphrase には入れない別集計 "
                 "(scripts/measure_outcomes.py)",
          kind=OUTCOME)

    c.add("retrieval_cases_real", "retrieval cases against the 5 real repos",
          len(headline),
          detail=f"src/sidra_ai/evals/outcome_questions.py; "
                 f"{len(headline) - paraphrase} direct, {paraphrase} paraphrased. "
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
    """Whether a lost audit record is visible anywhere an operator looks.

    Both responses are inspected, not just ``/health``. This probe predates
    ``/v1/index``, so ``/health`` was the only place a durability signal could
    have appeared; reading only ``/health`` now would score one on the
    authenticated endpoint as absent, and push the next person to publish it
    on the unauthenticated one to make the number move.
    """

    from sidra_ai.api.schemas import HealthResponse, IndexResponse

    exposed = sorted(
        f"{endpoint}:{name}"
        for endpoint, model in (("/health", HealthResponse), ("/v1/index", IndexResponse))
        for name in model.model_fields
        if "audit" in name
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
