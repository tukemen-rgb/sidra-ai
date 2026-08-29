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

    # 2b. Is the index still there after a restart?
    #
    # Exercised by building a service, writing one document, and building a
    # second service over the same directory - which is what a restart is.
    # Measured as a count rather than a flag so a partial reload (the security
    # gate rejecting records under today's detectors) is visible as a smaller
    # number instead of a silent pass.
    survived, detail = _measure_restart_survival()
    c.add("index_survives_restart", "再起動後に索引が残っている文書数", survived,
          detail=detail, kind=OUTCOME)

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

    # 6. Ask for something to be *made* and have it go somewhere else.
    routed, detail = _measure_creation_routing()
    c.add("creation_routed", "creation requests routed away from Q&A", routed,
          detail=detail, kind=OUTCOME)


def _measure_creation_routing() -> tuple[int, str]:
    """Whether a request to make something takes a different path.

    Both halves have to hold, and the second is the one that matters: a
    detector that routed everything would score 1 on creation requests alone
    while quietly destroying the question path. So this sends a real question
    through the same service and requires it to stay a question.

    Exercised through ``SidraService.chat`` rather than by calling the
    detector, because the number is about what an operator gets back, not
    about whether a function returns the right enum.
    """

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.creation.intent import CreationKind
    from sidra_ai.creation.router import CreationOutcome, build_default_router
    from sidra_ai.models.echo import EchoModelAdapter

    def _fake_game(message: str, intent, facts=None) -> CreationOutcome:
        return CreationOutcome(
            kind=CreationKind.GAME, handled=True, summary="probe generator"
        )

    repo = "tukemen-rgb/sidra-ai"
    try:
        with _quiet():
            # The echo backend on purpose: this number is about which path a
            # message takes, and it must be the same number on a machine with
            # no model as on one with weights. Building the runtime model here
            # would also make the probe depend on a backend being reachable.
            service = SidraService(
                Settings(allowed_repositories=(repo,)),
                model=EchoModelAdapter(),
                creation_router=build_default_router({CreationKind.GAME: _fake_game}),
            )
            made = service.chat("釣りゲームを作って")
            asked = service.chat("SIDRA は取得した文書をどう扱いますか")
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0, f"probe failed: {type(exc).__name__}: {exc}"

    made_outcome = (made.get("creation") or {}).get("outcome") or {}
    asked_intent = (asked.get("creation") or {}).get("intent") or {}

    if not made_outcome.get("handled"):
        return 0, "a creation request was not routed to its generator"
    if asked_intent.get("is_creation"):
        return 0, "a question was misrouted as a creation request"
    return 1, (
        f"creation -> {made_outcome.get('kind')} generator; "
        "a question still answers as a question"
    )


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


# --- can it make the thing that was asked for -------------------------


def measure_boss_questions(c: Collector) -> None:
    """Can the owner's twenty questions be re-scored by someone else?

    On 2026-08-26 they were measured once and the questions were not written
    down, so the figure in ``docs/OUTCOMES.md`` could never be reproduced and
    two backlog items were denominated in a number nobody could compute again.

    This counts the questions that are now in the repository and structurally
    runnable - not how many are answered. The answering rate needs the five
    repositories on disk and lives in ``scripts/check_boss_questions.py``;
    what is checked here is the part that made that measurement worthless,
    which is that the questions existed nowhere but in one session's memory.

    The validation is what keeps the count from being padding: a question with
    no text, a duplicate, a marker too short to identify a passage, or a
    repository outside the allowlist is not counted.
    """

    from sidra_ai.evals.boss_questions import BOSS_QUESTIONS, REPOSITORIES

    seen_names: set[str] = set()
    seen_questions: set[str] = set()
    runnable = 0
    rejected = []
    for question in BOSS_QUESTIONS:
        problems = []
        if len(question.question.strip()) < 8:
            problems.append("question too short to be a question")
        if question.name in seen_names or question.question in seen_questions:
            problems.append("duplicate")
        if question.answer_marker is not None:
            if len(question.answer_marker.strip()) < 4:
                problems.append("marker too short to identify a passage")
            if question.repository not in REPOSITORIES:
                problems.append("repository outside the allowlist")
        elif question.repository is not None:
            problems.append("no marker but a repository")
        seen_names.add(question.name)
        seen_questions.add(question.question)
        if problems:
            rejected.append(f"{question.name}: {', '.join(problems)}")
        else:
            runnable += 1

    c.add(
        "boss_questions_runnable",
        "再計算できる社長役の質問",
        float(runnable),
        detail=(
            f"of {len(BOSS_QUESTIONS)} committed"
            + ("; rejected " + "; ".join(rejected) if rejected else "")
        ),
        kind=OUTCOME,
    )
    # The evidence that the set was not chosen to score well. A set written
    # after reading the corpus, picking questions it could already answer,
    # would have none of these.
    unanswerable = [q.name for q in BOSS_QUESTIONS if q.answer_marker is None]
    c.add(
        "boss_questions_unanswerable",
        "コーパスに答えが無い質問（残してある）",
        float(len(unanswerable)),
        detail=", ".join(unanswerable) or "none - check the set was not tuned",
        kind=CONTEXT,
    )


def measure_creation(c: Collector) -> None:
    """Does "釣りゲームを作って" produce a page that actually runs?

    Generated on every run rather than checked in, because a committed
    artifact proves the generator worked once. The number an operator cares
    about is whether it works now, on this checkout.
    """

    from sidra_ai.creation import generate_game, validate_game_html

    results = {}
    for key in ("fishing", "catch"):
        game = generate_game("ゲームを作って", template=key)
        results[key] = validate_game_html(game.html)
    playable = all(r["playable"] for r in results.values())
    failures = [f"{k}: {f}" for k, r in results.items() for f in r["failures"]]
    checkers = sorted({r["js_checker"] for r in results.values()})
    c.add(
        "creation_game_playable",
        "生成したゲームが遊べる",
        1.0 if playable else 0.0,
        detail=(
            f"{len(results)} templates, js checked by {', '.join(checkers)}"
            if playable
            else "; ".join(failures)
        ),
        kind=OUTCOME,
    )
    # The page is only an entry point if a creation request reaching it comes
    # back as a made thing and the file is listable. Checked through the real
    # app, because "the HTML contains the word 作って" would pass on a page
    # whose button posts to an endpoint that does not exist.
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app

    reasons = []
    with _quiet(), TestClient(create_app()) as client:
        page = client.get("/")
        if page.status_code != 200:
            reasons.append(f"GET / -> {page.status_code}")
        elif "/v1/artifacts" not in page.text or "作って" not in page.text:
            reasons.append("the page does not offer creation or a file list")
        made = client.post("/v1/chat", json={"message": "釣りゲームを作って"})
        routed = made.status_code == 200 and (
            made.json().get("creation", {}).get("outcome", {}).get("handled")
        )
        if not routed:
            reasons.append("a creation request came back as an answer")
        listing = client.get("/v1/artifacts")
        if listing.status_code != 200 or not listing.json().get("artifacts"):
            reasons.append(f"listing -> {listing.status_code}")
        else:
            name = listing.json()["artifacts"][0]["name"]
            got = client.get(f"/v1/artifacts/{name}")
            if got.status_code != 200:
                reasons.append(f"download -> {got.status_code}")
            elif "attachment" not in got.headers.get("content-disposition", ""):
                # Served inline, it would run in the origin holding the token.
                reasons.append("artifact served inline rather than as a download")
    c.add(
        "creation_ui_available",
        "ブラウザから制作して受け取れる",
        1.0 if not reasons else 0.0,
        detail="GET / -> /v1/chat -> /v1/artifacts -> download" if not reasons else "; ".join(reasons),
        kind=OUTCOME,
    )

    # Scaffolded documents that say 〔未記入〕 under every heading read as
    # finished, which is why this counts *specific* stages rather than
    # written ones: a stage scores only when it carries a number or an input
    # key that this production actually ships with.
    import tempfile

    from sidra_ai.creation import story
    from sidra_ai.creation.projects import count_substantive_stages, scaffold_project

    request = "企画から難しい釣りゲームを一通り作って"
    with tempfile.TemporaryDirectory() as scratch:
        project = scaffold_project(request, scratch)
        substantive = count_substantive_stages(project, story.plan_for(request))
    c.add(
        "creation_story_stages",
        "中身のある制作文書",
        float(substantive),
        detail=(
            "scenario / structure / features, each carrying this production's "
            "own controls or difficulty numbers (read off disk)"
        ),
        kind=OUTCOME,
    )

    # Two halves, because either alone passes while the feature is broken:
    # sprites on disk that no page loads are decoration, and a page
    # referencing files that were never written is a broken image.
    from sidra_ai.creation import sprites as sprite_lib

    reasons_a: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        project = scaffold_project("企画から釣りゲームを一通り作って", scratch)
        written = sorted((project.root / "assets").glob("*.svg"))
        if not written:
            reasons_a.append("no sprite was written")
        page = (project.root / "game.html").read_text(encoding="utf-8")
        for path in written:
            if sprite_lib.off_palette(path.read_text(encoding="utf-8")):
                # A generator inventing colours rebuilds the second design
                # system DESIGN.md §2 exists to prevent, one file at a time.
                reasons_a.append(f"{path.name}: colour outside the palette")
            if f"assets/{path.name}" not in page:
                reasons_a.append(f"{path.name}: written but never referenced")
    c.add(
        "creation_assets_generated",
        "生成した素材がページから参照されている",
        1.0 if written and not reasons_a else 0.0,
        detail=(
            f"{len(written)} SVG in assets/, palette-clean, referenced by game.html"
            if not reasons_a
            else "; ".join(reasons_a)
        ),
        kind=OUTCOME,
    )

    # Counted per format, and only when the file both exists and opens as
    # the package its extension claims. "The export worked" as one boolean
    # would hide the likeliest case by far: two writers installed, one not.
    from sidra_ai.creation.decks import generate_deck
    from sidra_ai.creation.office import write_office

    with tempfile.TemporaryDirectory() as scratch:
        results = write_office(generate_deck("デッキを作って", facts=[]), scratch, "deck")
    ok = [fmt for fmt, r in results.items() if r["valid"]]
    missing = [f"{fmt}: {r['reason']}" for fmt, r in results.items() if not r["valid"]]
    c.add(
        "creation_office_formats",
        "実ファイルで出せる Office 形式",
        float(len(ok)),
        detail=(
            f"{', '.join(sorted(ok))} written and structurally valid "
            "(OOXML package, required parts, XML parses; not a claim about Word itself)"
            if not missing
            else "; ".join(missing)
        ),
        kind=OUTCOME,
    )

    # A template that stops being reachable from ordinary wording is a
    # regression the playability number cannot see: both templates would still
    # generate, and nobody would get the second one.
    from sidra_ai.creation.games import choose_template

    reachable = len(
        {
            choose_template(text)
            for text in (
                "釣りゲームを作って",
                "キャッチゲームを作って",
                "冒険ゲームを作って",
                "ビームの撃ち合いゲームを作って",
                "シューティングゲームを作って",
                "パズルゲームを作って",
            )
        }
    )
    c.add(
        "creation_game_templates",
        "依頼文から届くゲームの型",
        float(reachable),
        detail="distinct templates chosen by one ordinary request each",
        kind=GUARD,
    )

    # Asking for a genre we cannot build gets a playable page either way, so
    # playability cannot tell "we made a shooter" from "we made a fishing game
    # and called it a shooter". This number asks the generator both questions:
    # does it own up when it substituted, and does it stay quiet when it did
    # not? Half a pass is a fail - a build that caveats every request is as
    # useless a narrator as one that never does.
    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.games import TEMPLATES as _GAME_TEMPLATES
    from sidra_ai.creation.games import detect_genre
    from sidra_ai.creation.intent import detect_creation_intent

    honesty_failures = []
    unsupported = next(
        (
            text
            for text in ("シューティングゲームを作って", "パズルゲームを作って", "レースゲームを作って")
            if (g := detect_genre(text)) is not None and not g.supported
        ),
        "",
    )
    supported = next(
        (
            text
            for text in ("釣りゲームを作って", "キャッチゲームを作って")
            if (g := detect_genre(text)) is not None and g.supported
        ),
        "",
    )
    if not unsupported:
        # Every genre in the table has a template: the caveat has nothing left
        # to describe, which is a good state but not one this number can prove.
        honesty_failures.append("no unsupported genre left to test the wording on")
    if not supported:
        honesty_failures.append("no supported genre left to test the silence on")
    if unsupported and supported:
        with tempfile.TemporaryDirectory() as tmp:
            generate = build_game_generator(tmp)
            missed = generate(unsupported, detect_creation_intent(unsupported))
            named = detect_genre(unsupported)
            if not missed.details.get("genre_substituted"):
                honesty_failures.append(f"{unsupported}: substitution not recorded")
            if named is not None and named.genre not in missed.summary:
                honesty_failures.append(
                    f"{unsupported}: the summary does not name the genre asked for"
                )
            built = str(missed.details.get("built_template", ""))
            if built not in _GAME_TEMPLATES:
                honesty_failures.append(f"{unsupported}: built_template={built!r}")
            elif _GAME_TEMPLATES[built].default_title not in missed.summary:
                honesty_failures.append(
                    f"{unsupported}: the summary does not name what was built instead"
                )

            kept = generate(supported, detect_creation_intent(supported))
            if kept.details.get("genre_substituted"):
                honesty_failures.append(f"{supported}: reported as a substitution")
            if "まだ作れない" in kept.summary:
                honesty_failures.append(f"{supported}: apologised for a genre it built")
    # A page that opens on a phone and cannot be played there is the same
    # shape of quiet wrong as a fishing game called a shooter: nothing fails,
    # the artifact just is not what was claimed. Counted per template, and a
    # template only counts when the pad is on the page *and* every key its
    # own handlers read is one a pad button can send - a pad missing the
    # action button would otherwise score full marks for being present.
    from sidra_ai.creation.games import TEMPLATES as _TOUCH_TEMPLATES
    from sidra_ai.creation.touchpad import (
        BUTTON_CSS_PX,
        GAP_CSS_PX,
        unreachable_keys,
    )

    touch_ok, touch_gaps = [], []
    for key, spec in sorted(_TOUCH_TEMPLATES.items()):
        page = generate_game("ゲームを作って", template=key).html
        missing = sorted(unreachable_keys(spec.script))
        if "drawPad" not in page or "pointerdown" not in page:
            touch_gaps.append(f"{key}: no pad on the page")
        elif missing:
            touch_gaps.append(f"{key}: no pad button for {', '.join(missing)}")
        else:
            touch_ok.append(key)
    if BUTTON_CSS_PX < 48 or GAP_CSS_PX < 8:
        # §4's floor. Buttons drawn below it are on the page and still cannot
        # be hit, so the count would be describing something untrue.
        touch_gaps.append(f"targets {BUTTON_CSS_PX}px/gap {GAP_CSS_PX}px below 48/8")
        touch_ok = []
    c.add(
        "creation_touch_playable",
        "スマホで遊べるゲームの型",
        float(len(touch_ok)),
        detail=(
            f"{', '.join(touch_ok)}: {BUTTON_CSS_PX}px targets, {GAP_CSS_PX}px apart, "
            "every key each template reads has a button"
            if not touch_gaps
            else "; ".join(touch_gaps)
        ),
        kind=OUTCOME,
    )

    c.add(
        "creation_genre_honest",
        "作れない型を名乗らない",
        0.0 if honesty_failures else 1.0,
        detail=(
            "; ".join(honesty_failures)
            if honesty_failures
            else f"{unsupported} names the gap and the substitute; {supported} does not"
        ),
        kind=OUTCOME,
    )

    # --- the adventure, judged like every game: generated fresh, script
    # parsed, and the request that motivated it routed to the right template
    # with the trademark swapped out rather than shipped ------------------
    from sidra_ai.creation.games import generate_game, validate_game_html

    adventure_ok = 0.0
    directive = "ゼルダの伝説 不思議なぼうしを作って"
    game = generate_game(directive)
    verdict = validate_game_html(game.html)
    reasons = []
    if game.template != "adventure":
        reasons.append(f"routed to {game.template}")
    if not verdict.get("playable", verdict.get("valid")):
        reasons.append("; ".join(str(f) for f in verdict.get("failures", ())) or "invalid page")
    if "ゼルダ" in game.title:
        reasons.append("the trademark reached the title")
    if "オリジナル版" not in game.tagline:
        reasons.append("the rename is silent")
    for marker in ("rooms", "hero", "swing", "鍵", "Math.max(hero.inv,45)"):
        if marker not in game.html:
            reasons.append(f"script lost its {marker}")
    if not reasons:
        adventure_ok = 1.0
    c.add(
        "creation_adventure_playable",
        "見下ろし型の冒険が作れる",
        adventure_ok,
        detail=(
            "3 rooms / sword / key / chest, trademark renamed honestly"
            if adventure_ok
            else "; ".join(reasons)
        ),
        kind=OUTCOME,
    )

    # --- the duel, same bar as the adventure: the directive's own request
    # routes, plays, and ships without the franchise name -----------------
    duel_ok = 0.0
    duel_game = generate_game("ドラゴンボールのゲームを作って")
    duel_verdict = validate_game_html(duel_game.html)
    duel_reasons = []
    if duel_game.template != "duel":
        duel_reasons.append(f"routed to {duel_game.template}")
    if not duel_verdict.get("playable"):
        duel_reasons.append(
            "; ".join(str(f) for f in duel_verdict.get("failures", ())) or "invalid page"
        )
    if "ドラゴンボール" in duel_game.title or "ドラゴンボール" in duel_game.html:
        duel_reasons.append("the franchise name reached the artifact")
    if "オリジナル版" not in duel_game.tagline:
        duel_reasons.append("the rename is silent")
    for marker in ("charge", "spark", "押し合い", "hitLock"):
        if marker not in duel_game.html:
            duel_reasons.append(f"script lost its {marker}")
    if not duel_reasons:
        duel_ok = 1.0
    c.add(
        "creation_versus_playable",
        "ビームの撃ち合いが作れる",
        duel_ok,
        detail=(
            "charge / fire / lane dodge / beam clash, franchise renamed honestly"
            if duel_ok
            else "; ".join(duel_reasons)
        ),
        kind=OUTCOME,
    )

    # --- sound: the cheapest half of game feel, per the knowledge base ---
    #
    # Counted per template off the generated page: AudioContext present, at
    # least two sfx() calls beyond the definition, and no external audio
    # reference - a template that went silent again drops the count by one
    # instead of hiding behind the three that still ring.
    from sidra_ai.creation.games import TEMPLATES as _ALL_TEMPLATES

    audible = 0
    audio_reasons = []
    for template_key in _ALL_TEMPLATES:
        page = generate_game(f"{template_key} を作って", template=template_key).html
        calls = page.count("sfx(") - 1  # minus the definition itself
        if "AudioContext" not in page:
            audio_reasons.append(f"{template_key}: no AudioContext")
        elif calls < 2:
            audio_reasons.append(f"{template_key}: only {calls} sfx call(s)")
        elif ".mp3" in page or ".wav" in page or ".ogg" in page:
            audio_reasons.append(f"{template_key}: references an audio file")
        else:
            audible += 1
    c.add(
        "creation_game_audio",
        "音が鳴るゲームの型",
        float(audible),
        detail=(
            f"{audible} of {len(_ALL_TEMPLATES)} templates synthesise their own SFX"
            if not audio_reasons
            else "; ".join(audio_reasons)
        ),
        kind=OUTCOME,
    )

    # --- map readability: walls, doors and water must read by form -------
    #
    # The knowledge base's accessibility rule is "never convey essential
    # information by fixed colour alone". The instrument checks the page for
    # the form-carrying code: wall edge highlights, the door chevron path,
    # and the pond actually carved into the map (the water tile shipped as
    # dead code once; 'defined' and 'placed' are different facts).
    from sidra_ai.creation.themes import THEMES as _READ_THEMES

    _read_tokens = _READ_THEMES["gameyard"].tokens
    readable_page = generate_game("冒険ゲームを作って").html
    readable_reasons = []
    if "pond(forest)" not in readable_page:
        readable_reasons.append("no pond is carved into the map")
    if "closePath" not in readable_page:
        readable_reasons.append("no door chevron")
    if "#ffffff2e" not in readable_page:
        readable_reasons.append("walls have no edge highlight (colour-only)")
    if _read_tokens["border"] == _read_tokens["surface"]:
        readable_reasons.append("wall and floor share a colour token")
    if not validate_game_html(readable_page)["playable"]:
        readable_reasons.append("page no longer parses")
    c.add(
        "creation_map_readable",
        "地形が読める（壁・扉・水）",
        0.0 if readable_reasons else 1.0,
        detail=(
            "walls carry form, doors carry a chevron, the pond is real"
            if not readable_reasons
            else "; ".join(readable_reasons)
        ),
        kind=OUTCOME,
    )

    # --- the duel has a decision in it now ------------------------------
    #
    # Holding the charge at maximum used to be free, which made "let go" a
    # formality rather than a choice, and the opponent behaved the same way
    # whatever the request said. Both are checked by playing in node: hold
    # and never release, and see whether it costs anything; then compare
    # seeds and see whether the temperament changes behaviour or only a
    # label. The clash gauge is checked structurally, not behaviourally - a
    # clash needs both fighters firing into one lane on the same frame, and
    # forcing that would be testing the harness rather than the game.
    import re as _duel_re
    import subprocess as _duel_sp

    from sidra_ai.creation.duel import probe_source as _duel_probe

    duel_reasons = []
    duel_seen = {}
    for request in (
        "ビームの撃ち合いゲームを作って",
        "エネルギー波バトル作って",
        "必殺技の対戦ゲーム作って",
        "気弾の撃ち合いを作って",
    ):
        page = generate_game(request).html
        script = _duel_re.search(r"<script>(.*?)</script>", page, _duel_re.S)
        if script is None:
            duel_reasons.append(f"{request}: no script")
            continue
        try:
            probe = _duel_sp.run(
                ["node", "-"],
                input=_duel_probe(script.group(1)),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if probe.returncode != 0:
                duel_reasons.append(f"{request}: {probe.stderr.strip()[:60]}")
                continue
            duel_seen[request] = json.loads(probe.stdout)
        except (OSError, _duel_sp.SubprocessError, ValueError) as exc:
            duel_reasons.append(f"probe unavailable ({type(exc).__name__})")
            break
    if duel_seen:
        never_punished = [
            r for r, seen in duel_seen.items() if seen["stunFrames"] == 0
        ]
        if never_punished:
            duel_reasons.append(
                f"holding at maximum costs nothing ({len(never_punished)} seeds)"
            )
        styles = {seen["style"] for seen in duel_seen.values()}
        if len(styles) < 2:
            duel_reasons.append(f"every seed gives the same opponent ({styles})")
        else:
            thresholds = {seen["style"]: tuple(seen["fire"]) for seen in duel_seen.values()}
            if len(set(thresholds.values())) < 2:
                duel_reasons.append("the temperaments are a label, not a behaviour")
        duel_page = generate_game("ビームの撃ち合いゲームを作って").html
        if "spark/60" not in duel_page:
            duel_reasons.append("the clash has no gauge")
        if not validate_game_html(duel_page)["playable"]:
            duel_reasons.append("page no longer parses")
    c.add(
        "creation_duel_depth",
        "対戦に読み合いがある",
        0.0 if duel_reasons or not duel_seen else 1.0,
        detail=(
            "holding at maximum overloads; seeds reach both a quick draw and a "
            "charger with different fire thresholds; the clash push is on a gauge"
            if duel_seen and not duel_reasons
            else "; ".join(duel_reasons) or "no seed could be played"
        ),
        kind=OUTCOME,
    )

    # --- nobody is playing before they have read anything --------------
    #
    # Every template used to start on load, which put the instructions below
    # the fold on a phone and made the first sound arrive with no user
    # gesture behind it. Counted per template by *driving the page in node*:
    # ten frames with the gate shut have to reach the game zero times, and
    # ten after one press have to reach it every time. A gate that merely
    # drew a title over a running game would pass a source check and fail
    # this one.
    import re as _gate_re
    import subprocess as _gate_sp

    from sidra_ai.creation.games import TEMPLATES as _GATE_TEMPLATES
    from sidra_ai.creation.startscreen import probe_source as _gate_probe

    gated, gate_gaps = [], []
    for key in sorted(_GATE_TEMPLATES):
        page = generate_game("ゲームを作って", template=key).html
        script = _gate_re.search(r"<script>(.*?)</script>", page, _gate_re.S)
        if script is None:
            gate_gaps.append(f"{key}: no script")
            continue
        try:
            probe = _gate_sp.run(
                ["node", "-"],
                input=_gate_probe(script.group(1)),
                capture_output=True,
                text=True,
                timeout=40,
            )
            if probe.returncode != 0:
                gate_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout)
        except (OSError, _gate_sp.SubprocessError, ValueError) as exc:
            gate_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
            continue
        if seen["framesBeforePress"] != 0:
            gate_gaps.append(f"{key}: ran {seen['framesBeforePress']} frames unasked")
        elif seen["stateAfter"] != "playing" or seen["framesAfterPress"] == 0:
            gate_gaps.append(f"{key}: one press does not start it")
        elif not validate_game_html(page)["playable"]:
            gate_gaps.append(f"{key}: page no longer parses")
        else:
            gated.append(key)
    c.add(
        "creation_start_screen",
        "読んでから始められるゲームの型",
        float(len(gated)),
        detail=(
            f"{', '.join(gated)}: zero frames before the press, "
            "every frame after it"
            if not gate_gaps
            else "; ".join(gate_gaps)
        ),
        kind=OUTCOME,
    )

    # --- gems that buy something, and a door nobody has to open --------
    #
    # Two knowledge-base rules, and they fail in the same silent way. §5: a
    # collectible with no sink is a number going up, and the grass was being
    # cut for one. §3: a dungeon whose mission graph is a single line has no
    # decisions in it. Both were true here and neither showed in any number,
    # because the game was playable and winnable throughout.
    #
    # The world is built by running the real page in node rather than by
    # reading its source. "The tile is defined" and "the tile is on the map"
    # have already been different facts once (C-1018's pond), and a check
    # that greps cannot tell them apart.
    import re as _re
    import subprocess as _sp

    from sidra_ai.creation.adventure import world_probe

    sink_page = generate_game("冒険ゲームを作って").html
    sink_script = _re.search(r"<script>(.*?)</script>", sink_page, _re.S)
    sink_reasons = []
    world = {}
    if sink_script is None:
        sink_reasons.append("no script on the page")
    else:
        try:
            probe = _sp.run(
                ["node", "-"],
                input=world_probe(sink_script.group(1)),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if probe.returncode != 0:
                sink_reasons.append(f"world did not build: {probe.stderr.strip()[:80]}")
            else:
                world = json.loads(probe.stdout)
        except (OSError, _sp.SubprocessError, ValueError) as exc:
            sink_reasons.append(f"probe unavailable: {type(exc).__name__}")
    if world:
        tiles = world.get("tiles", {})
        for code, what in (("9", "shrine"), ("10", "optional door"), ("11", "reward")):
            if not tiles.get(code):
                sink_reasons.append(f"no {what} on the map")
        neighbours = world.get("charmNeighbours") or []
        if neighbours.count(10) != 1:
            sink_reasons.append("the reward is not reached through the door")
        elif any(n != 1 for n in neighbours if n != 10):
            sink_reasons.append("the reward has a second way in; the door is decoration")
    # A sink is only a sink if gems leave. Two outlets: the shrine and the
    # door - one that converts them, one that spends them on the branch.
    if sink_page.count("hero.gems-=") < 2:
        sink_reasons.append("gems are never spent")
    if not validate_game_html(sink_page)["playable"]:
        sink_reasons.append("page no longer parses")
    c.add(
        "creation_gem_sink",
        "宝石に使い道がある",
        0.0 if sink_reasons else 1.0,
        detail=(
            "shrine trades 3 gems for a heart; an optional door costs 2 and is "
            "the only way to the charm behind it"
            if not sink_reasons
            else "; ".join(sink_reasons)
        ),
        kind=OUTCOME,
    )

    # --- the 3D model, generated fresh so the number describes this
    # checkout rather than the day the generator was written ----------
    from sidra_ai.creation.models3d import generate_model3d, validate_model3d

    model_results = {}
    for shape in ("fish", "boat", "terrain"):
        model = generate_model3d("3Dモデルを作って", shape=shape)
        model_results[shape] = validate_model3d(model)
    model_valid = all(r["valid"] for r in model_results.values())
    model_failures = [
        f"{shape}: {f}" for shape, r in model_results.items() for f in r["failures"]
    ]
    c.add(
        "creation_3d_model_valid",
        "生成した 3D モデルが開ける",
        1.0 if model_valid else 0.0,
        detail=(
            "; ".join(
                f"{shape} v{r['vertices']}/f{r['faces']}"
                for shape, r in model_results.items()
            )
            if model_valid
            else "; ".join(model_failures)
        ),
        kind=OUTCOME,
    )

    # --- the animated GIF, judged by parsing its actual bytes ----------
    #
    # The instrument is a real block-walker over the generated file, so a
    # writer that truncated a frame, dropped the loop extension, or left
    # unread bytes after the trailer scores 0 the same way a foreign decoder
    # would fail to open it. Both motifs run, because a motif that stops
    # generating is a capability lost even while the other still passes.
    from sidra_ai.creation.gifs import generate_gif, validate_gif

    gif_results = {}
    for probe in ("魚のGIFを作って", "GIFを作って"):
        gif = generate_gif(probe)
        gif_results[gif.motif] = validate_gif(gif)
    gif_valid = all(r["valid"] for r in gif_results.values()) and len(gif_results) >= 2
    gif_failures = [
        f"{motif}: {f}" for motif, r in gif_results.items() for f in r["failures"]
    ]
    if len(gif_results) < 2:
        gif_failures.append("both probes chose the same motif")
    c.add(
        "creation_gif_generated",
        "生成した GIF が動く",
        1.0 if gif_valid else 0.0,
        detail=(
            "; ".join(
                f"{motif} {r['frames']}f/{r['bytes']}B loop"
                for motif, r in gif_results.items()
            )
            if gif_valid
            else "; ".join(gif_failures)
        ),
        kind=OUTCOME,
    )

    # --- generative art: count the patterns that actually hold up ------
    #
    # The number is how many patterns generate a page that passes the full
    # validator (canvas, parseable script, nothing external, reduced-motion
    # honoured, seeded - never Math.random). Counting patterns rather than
    # reporting a single 0/1 keeps a half-regression visible: one broken
    # pattern reads as 2 -> 1, not as "still fine".
    from sidra_ai.creation.art import PATTERNS, generate_art, validate_art

    art_failures: list[str] = []
    art_valid = 0
    for pattern in PATTERNS:
        verdict = validate_art(generate_art("アートを作って", pattern=pattern))
        if verdict["valid"]:
            art_valid += 1
        else:
            art_failures += [f"{pattern}: {f}" for f in verdict["failures"]]
    c.add(
        "creation_art_patterns",
        "生成アートの型が揃う",
        float(art_valid),
        detail=(
            f"{art_valid} of {len(PATTERNS)} patterns pass the page validator"
            if not art_failures
            else "; ".join(art_failures)
        ),
        kind=OUTCOME,
    )

    # --- how many kinds of thing can actually be asked for --------------
    #
    # Counted off a built router, not off the enum: a kind in the detector
    # with no registered generator answers "生成器がまだ登録されていません",
    # which is honest but is not a capability. This number is what the C-0
    # sprint grew - it was 3 (deck, game, project) when the sprint started.
    import tempfile as _tempfile

    from sidra_ai.creation.router import build_default_router

    kinds = build_default_router(data_dir=_tempfile.mkdtemp()).registered_kinds()
    c.add(
        "creation_kinds_routable",
        "作ってと頼める種類",
        float(len(kinds)),
        detail=", ".join(kinds),
        kind=OUTCOME,
    )

    # --- and the deck, where the danger is different ------------------
    #
    # A deck that renders is not the bar. A deck is dangerous when it looks
    # authoritative and carries a figure nobody retrieved, so the number here
    # is "usable *and* every figure on it traces to evidence". The probe feeds
    # real facts and then checks the deck against exactly those facts, which
    # is the same check that would fail if a generator ever started writing
    # numbers of its own.
    from sidra_ai.creation.decks import Fact, generate_deck, save_pptx, validate_deck

    facts = [
        Fact("課題: 索引した文書を人手で読み切れない", "tukemen-rgb/sidra-ai docs/BACKLOG.md"),
        Fact("解決: 引用付きで答え、根拠の抜粋も返す", "tukemen-rgb/sidra-ai docs/ARCHITECTURE.md"),
    ]
    deck = generate_deck("営業用のデッキを作って", facts=facts)
    verdict = validate_deck(deck, facts)
    c.add(
        "creation_deck_generated",
        "生成したデッキが使える（数字は全部出典つき）",
        1.0 if verdict["usable"] else 0.0,
        detail=(
            f"{verdict['slides']} slides, {len(verdict['unfilled'])} left blank"
            " for the owner to fill"
            if verdict["usable"]
            else "; ".join(verdict["failures"])
        ),
        kind=OUTCOME,
    )

    # An empty-evidence deck must still be honest rather than absent. This is
    # the case a generator is tempted to "improve" by writing plausible
    # filler, and the guard says how many sections it left for a human.
    bare = generate_deck("デッキを作って")
    c.add(
        "creation_deck_blanks_kept",
        "根拠が無い欄を空のまま残す",
        float(len(bare.unfilled)),
        detail="sections left blank when nothing was retrieved (filler would read as fact)",
        kind=GUARD,
    )

    # pptx is optional on purpose: the HTML artifact is what always exists.
    # Reported so "we made a pptx" is never claimed on a machine without it.
    written, why = save_pptx(deck, Path("/tmp/sidra-metrics-probe.pptx"))
    c.add(
        "creation_deck_pptx",
        "pptx も書けたか（任意）",
        1.0 if written else 0.0,
        detail=why,
        kind=CONTEXT,
    )

    # --- does the page move, and does it stop when asked? --------------
    animated, detail = _measure_animation()
    c.add(
        "creation_animation_present",
        "生成ページが動き、reduced-motion で止まる",
        animated,
        detail=detail,
        kind=OUTCOME,
    )

    # --- does a hit feel like one? -------------------------------------
    juiced, juice_detail = _measure_juice()
    c.add(
        "creation_game_juice",
        "当たった感じがする",
        juiced,
        detail=juice_detail,
        kind=OUTCOME,
    )

    # --- the whole production, not just the playable page --------------
    #
    # Two halves again, and the second is the one that keeps this honest: a
    # scaffolder that always wrote six files would score full marks on the
    # first while destroying "脚本だけ作って", which has to produce exactly
    # one file. So the probe asks for a whole project and for one stage, and
    # requires both to match what was asked.
    scaffolded, detail = _measure_project_scaffold()
    c.add(
        "creation_project_scaffolded",
        "企画から作った制作一式が揃う",
        scaffolded,
        detail=detail,
        kind=OUTCOME,
    )

    # --- the record: is a generation traceable afterwards? -------------
    #
    # Three claims, each checked against the disk rather than the code that
    # makes them: the log carries a parseable record of when/what/evidence/
    # parameters, the record never quotes retrieved content, and the project
    # is reachable through the same listing the browser uses - slug, files,
    # and the log itself downloadable by the name the listing printed.
    recorded, detail = _measure_record_written()
    c.add(
        "creation_record_written",
        "生成の記録が残り、辿れる",
        recorded,
        detail=detail,
        kind=OUTCOME,
    )

    # --- and does a real request actually reach the index? ------------
    grounded, detail = _measure_deck_grounding()
    c.add(
        "creation_deck_grounded",
        "デッキが索引の根拠で埋まる",
        grounded,
        detail=detail,
        kind=OUTCOME,
    )

    # --- the palette a request asked for, and the one it did not ---------
    #
    # Counted by generating with each theme and looking at the page, not by
    # len(THEMES): a catalogue entry that no generator reads is a theme in
    # name only. The gate before the count is the other direction - a request
    # naming no theme still renders in the site's own palette. Without it a
    # "themed" generator that had quietly redecorated the default would score
    # full marks here while having changed the product's identity.
    themed, detail = _measure_themes()
    c.add(
        "creation_themes_available",
        "テーマを指定すると配色が変わり、指定しなければ変わらない",
        themed,
        detail=detail,
        kind=OUTCOME,
    )




def _measure_animation() -> tuple[float, str]:
    """Whether the generated page animates and honours reduced motion.

    Run, not grepped. The helpers are executed in node under both settings,
    so this reports what a viewer would get rather than whether the source
    contains the word "transition" - a page could match every keyword and
    still animate nothing, or animate through the setting.

    Both directions have to hold. A page that never animates would satisfy
    "stops when asked" trivially, so the unreduced run must produce distinct
    frames; and the reduced run must produce exactly one, while the game loop
    itself keeps running (which is why FRAME collapses rather than the loop).
    """

    import subprocess

    from sidra_ai.creation.animation import probe_source
    from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html

    results = {}
    try:
        for reduced in (False, True):
            finished = subprocess.run(
                ["node", "-"],
                input=probe_source(reduced=reduced),
                capture_output=True,
                text=True,
                timeout=20,
            )
            if finished.returncode != 0:
                return 0.0, f"probe did not run: {finished.stderr.strip()[:80]}"
            results[reduced] = json.loads(finished.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # No node means this cannot be measured here. Reported as 0 with the
        # reason rather than as a pass, because "we could not check" and "it
        # works" are different facts.
        return 0.0, f"probe unavailable: {type(exc).__name__}"

    moving, still = results[False], results[True]
    if moving["distinctFrames"] < 2:
        return 0.0, "the page does not animate at all"
    if still["distinctFrames"] != 1:
        return 0.0, "decorative frames still advance under prefers-reduced-motion"
    if moving["easeMid"] == still["easeMid"]:
        return 0.0, "easing is unchanged under prefers-reduced-motion"

    # And the pages that ship with it still parse: an animated page that no
    # longer runs is a worse artifact than a static one.
    for key in TEMPLATES:
        verdict = validate_game_html(generate_game("ゲームを作って", template=key).html)
        if not verdict["playable"]:
            return 0.0, f"{key} stopped being playable: {verdict['failures']}"

    return 1.0, (
        f"{moving['distinctFrames']} decorative frames normally, "
        f"{still['distinctFrames']} under reduced motion; "
        f"{len(TEMPLATES)} templates still playable"
    )


def _measure_juice() -> tuple[float, str]:
    """Whether hits land: shake, hitstop and particles, and the switch.

    Run in node like the animation probe, and for the same reason - a page
    can contain the word ``shake`` and never move. Two directions again:
    normally the effects have to do something, and under
    ``prefers-reduced-motion`` the decorative two have to do nothing.

    ``hitstop`` is deliberately excluded from the reduced case and checked to
    survive it. It withholds motion rather than adding any, and a person who
    asked for less movement did not ask for hits to feel weightless. Written
    down as an assertion here so the choice is visible rather than an
    oversight someone later "fixes".

    Being wired matters as much as existing: every template has to call all
    three, or the feel belongs to whichever game somebody got round to.
    """

    import subprocess

    from sidra_ai.creation.games import TEMPLATES, generate_game, validate_game_html
    from sidra_ai.creation.juice import probe_source

    results = {}
    try:
        for reduced in (False, True):
            finished = subprocess.run(
                ["node", "-"],
                input=probe_source(reduced=reduced),
                capture_output=True,
                text=True,
                timeout=20,
            )
            if finished.returncode != 0:
                return 0.0, f"probe did not run: {finished.stderr.strip()[:80]}"
            results[reduced] = json.loads(finished.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return 0.0, f"probe unavailable: {type(exc).__name__}"

    moving, still = results[False], results[True]
    if moving["shake"] <= 0 or moving["particles"] <= 0:
        return 0.0, "the effects do nothing even with motion allowed"
    if still["shake"] != 0 or still["particles"] != 0:
        return 0.0, "shake or particles survive prefers-reduced-motion"
    if still["hitstop"] <= 0:
        return 0.0, "hitstop was disabled by reduced motion; it moves nothing"

    unwired = [
        f"{key}: no {name}()"
        for key, spec in sorted(TEMPLATES.items())
        for name in ("shake", "hitstop", "burst")
        if f"{name}(" not in spec.script
    ]
    if unwired:
        return 0.0, "; ".join(unwired)

    for key in TEMPLATES:
        verdict = validate_game_html(generate_game("ゲームを作って", template=key).html)
        if not verdict["playable"]:
            return 0.0, f"{key} stopped being playable: {verdict['failures']}"

    return 1.0, (
        f"shake {moving['shake']} -> 0 and {moving['particles']} particles -> 0 "
        f"under reduced motion, hitstop kept; all {len(TEMPLATES)} templates "
        "call shake, hitstop and burst"
    )


def _measure_themes() -> tuple[float, str]:
    """How many themes a request can actually reach, default held fixed.

    Two directions, and the order matters. The default is checked first and
    fails the whole metric, because "three themes work" is worthless if the
    fourth thing that changed was the palette every unthemed artifact gets.

    Each theme is then counted only if naming it changes both artifacts a
    theme applies to. Checking the deck alone would let a generator that
    themed slides and ignored games report the same number.
    """

    from sidra_ai.creation.decks import generate_deck
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.themes import DEFAULT_THEME, THEMES, select_theme, validate_theme

    plain_game = generate_game("ゲームを作って").html
    plain_deck = generate_deck("デッキを作って").html
    if select_theme("釣りゲームを作って") is not DEFAULT_THEME:
        return 0.0, "テーマを指定していない依頼が既定以外の配色になった"
    for name, html in (("game", plain_game), ("deck", plain_deck)):
        if DEFAULT_THEME.tokens["bg"] not in html:
            return 0.0, f"既定の{name}が DESIGN.md の背景色で描かれていない"

    working, broken = [], []
    for key, theme in THEMES.items():
        verdict = validate_theme(theme)
        if not verdict["readable"]:
            broken.append(f"{key}: {verdict['failures'][0]}")
            continue
        request = f"{theme.words[0]}のテーマで"
        game = generate_game(f"{request}ゲームを作って").html
        deck = generate_deck(f"{request}デッキを作って").html
        if select_theme(request) is not theme:
            broken.append(f"{key}: 依頼文から選ばれない")
        elif theme.tokens["bg"] not in game or theme.tokens["bg"] not in deck:
            broken.append(f"{key}: 生成物に配色が届いていない")
        elif key != DEFAULT_THEME.key and (game == plain_game or deck == plain_deck):
            broken.append(f"{key}: 指定しても既定と同じものが出る")
        else:
            working.append(key)

    note = f"{len(working)} themes reach both artifacts: {', '.join(working)}"
    return float(len(working)), note + ("; " + "; ".join(broken) if broken else "")


def _measure_restart_survival() -> tuple[float, str]:
    """How many documents a second process finds after the first indexed them.

    Zero was the measured value before the store was given a path: the whole
    corpus lived in one process and a restart dropped it, so the operator had
    to re-fetch five repositories from GitHub before asking anything.
    """

    import tempfile
    from datetime import datetime, timezone

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter

    document = Document(
        content="投稿できるファイルは 200MB までです。",
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/site",
            path="docs/upload.md",
            commit_sha="a" * 40,
            timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )
    try:
        with _quiet(), tempfile.TemporaryDirectory() as scratch:
            settings = Settings(data_dir=scratch)
            first = SidraService(settings=settings, model=EchoModelAdapter())
            first.store.add(document)
            written = len(list(first.store.documents()))

            second = SidraService(settings=settings, model=EchoModelAdapter())
            found = len(list(second.store.documents()))
            error = second.index_load_error
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0.0, f"probe failed: {type(exc).__name__}: {exc}"

    if error:
        return 0.0, f"the reload reported: {error}"
    return float(found), (
        f"{found} of {written} document(s) found by a second service over the "
        "same data directory"
    )


def _measure_project_scaffold() -> tuple[float, str]:
    """Whether "企画から作って" produces the whole production on disk.

    Checked against the directory, not against the summary: the summary is
    what a scaffolder would get right by accident, and the file that was
    never written is what an operator finds later.
    """

    import tempfile

    from sidra_ai.creation.intent import CreationKind, detect_creation_intent
    from sidra_ai.creation.project_job import build_project_generator
    from sidra_ai.creation.projects import STAGE_ORDER

    try:
        with _quiet():
            data_dir = tempfile.mkdtemp()
            generate = build_project_generator(data_dir)

            whole_request = "釣りゲームを企画から作って"
            whole_intent = detect_creation_intent(whole_request)
            whole = generate(whole_request, whole_intent)

            one_request = "宇宙ゲームの脚本だけ作って"
            one = generate(one_request, detect_creation_intent(one_request))
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0.0, f"probe failed: {type(exc).__name__}: {exc}"

    if whole_intent.kind is not CreationKind.PROJECT:
        return 0.0, f"a whole-production request routed to {whole_intent.kind.value}"
    if whole.details.get("missing"):
        return 0.0, "stages claimed but not written: " + ", ".join(whole.details["missing"])
    if len(whole.details.get("stages") or ()) != len(STAGE_ORDER):
        return 0.0, f"{len(whole.details.get('stages') or ())} of {len(STAGE_ORDER)} stages"
    if list(one.details.get("stages") or ()) != ["scenario"]:
        return 0.0, (
            "a single-stage request produced "
            f"{one.details.get('stages')} instead of just the scenario"
        )

    return 1.0, (
        f"{len(STAGE_ORDER)} stages written to one directory; "
        "a single-stage request still produces one file"
    )


def _measure_record_written() -> tuple[float, str]:
    """Whether a generation leaves a record that can be found again.

    The probe scaffolds a whole production with one retrieved fact, then
    checks the C-999 chain end to end: ``production-log.md`` holds a record
    line that parses back (time, files, evidence path, parameters), the
    record carries the fact's *path* but never its *text*, and the project
    listing the browser uses names the slug, lists the log among its files,
    and hands the log back by that name.
    """

    import tempfile

    from sidra_ai.api.artifacts import list_projects, read_project_file
    from sidra_ai.creation.evidence import Fact
    from sidra_ai.creation.projects import scaffold_project
    from sidra_ai.creation.records import LOG_NAME, read_records

    secret = "索引の中身 9481 を写してはいけない"
    fact = Fact(secret, "owner/repo docs/OUTCOMES.md")
    try:
        with _quiet():
            data_dir = tempfile.mkdtemp()
            project = scaffold_project(
                "釣りゲームを企画から作って", data_dir, facts=[fact]
            )
            records = read_records(project.root)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0.0, f"probe failed: {type(exc).__name__}: {exc}"

    if not records:
        return 0.0, "no record line in production-log.md"
    record = records[-1]
    if "T" not in record.when or not record.when.endswith("Z"):
        return 0.0, f"record time is not a UTC stamp: {record.when!r}"
    if LOG_NAME not in record.made or "game.html" not in record.made:
        return 0.0, f"record does not name what was made: {record.made}"
    if fact.source not in record.evidence:
        return 0.0, "record does not carry the evidence path"
    if "template" not in record.parameters or "speed" not in record.parameters:
        return 0.0, f"record does not carry parameters: {record.parameters}"
    log_text = (project.root / LOG_NAME).read_text(encoding="utf-8")
    if "9481" in log_text:
        # The one failure this metric must never trade away: retrieved text
        # in a file that reads as metadata.
        return 0.0, "record leaked retrieved content into the log"

    listed = {p.slug: p for p in list_projects(data_dir)}
    if project.slug not in listed:
        return 0.0, "project is not in the listing the browser uses"
    names = {artifact.name for artifact in listed[project.slug].files}
    if LOG_NAME not in names:
        return 0.0, f"listing does not include {LOG_NAME}"
    payload, _ = read_project_file(data_dir, project.slug, LOG_NAME)
    if not payload:
        return 0.0, "the log came back empty through the download route"

    return 1.0, (
        "one parseable record (time / files / evidence path / parameters), "
        "no retrieved text, and the log is listed and downloadable per project"
    )


def _measure_deck_grounding() -> tuple[float, str]:
    """Whether a deck asked for over HTTP comes back filled from the corpus.

    Two things have to hold, and the second is why this is separate from
    ``creation_deck_generated``: a deck that is honest but entirely blank
    passes that number and is useless. So this one requires evidence to have
    reached the slides *and* the generator's own fabrication check to have
    passed - filling slides by loosening the check would score worse, not
    better, because the check refusing is a failure here too.
    """

    import importlib.util

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    spec = importlib.util.spec_from_file_location(
        "_measure_outcomes_for_decks",
        Path(__file__).resolve().parent / "measure_outcomes.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    repo = "tukemen-rgb/sidra-ai"
    try:
        with _quiet():
            gate = module.SecurityGate(module.GatePolicy(), allowed_repositories=[repo])
            store = module.DocumentStore(gate)
            module.ingest([(repo, Path(__file__).resolve().parents[1])], store, gate)
            import tempfile

            service = SidraService(
                Settings(allowed_repositories=(repo,), data_dir=tempfile.mkdtemp()),
                model=EchoModelAdapter(),
                store=store,
                gate=gate,
            )
            answer = service.chat("SIDRA の課題と解決のデッキを作って")
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0.0, f"probe failed: {type(exc).__name__}: {exc}"

    creation = answer.get("creation") or {}
    outcome = creation.get("outcome") or {}
    details = outcome.get("details") or {}
    if not outcome.get("handled"):
        return 0.0, f"the deck was not produced: {outcome.get('summary', '')[:80]}"
    if not details.get("numbers_sourced"):
        return 0.0, "the deck did not pass its own evidence check"

    slides = int(details.get("slides") or 0)
    unfilled = len(details.get("unfilled") or [])
    if not creation.get("facts"):
        return 0.0, "no evidence was retrieved for the request"
    if unfilled >= slides:
        return 0.0, f"{creation['facts']} facts retrieved, every one of {slides} slides still blank"
    return 1.0, (
        f"{creation['facts']} facts retrieved; {slides - unfilled}/{slides} slides filled "
        f"from the index, {unfilled} left for the owner"
    )


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
    ("boss", measure_boss_questions),
    ("creation", measure_creation),
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
