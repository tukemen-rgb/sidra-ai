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

    # 2c. Does the index file also stop growing without bound?
    compacted, detail = _measure_index_compaction()
    c.add("index_compacts", "再取り込みの死骸が掃除される", compacted,
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

    # C-1201: when the corpus knows nothing about the subject, chat must end
    # in the no-evidence answer instead of composing citations out of
    # cross-word bigram glue (「天気を教えて」 came back as marketing copy).
    # 10 needs both directions: every off-topic probe refused AND every
    # on-topic probe still answered - a floor that silences answerable
    # questions is a worse product than the one that bluffed.
    from sidra_ai.evals.qa_honesty import PROBES, evaluate_qa_honesty

    # C-1202: the canned no-evidence reply used to be English with an internal
    # API instruction regardless of the question's language - the exact
    # failure SYSTEM_PROMPT rule 6 was written against (2026-08-27 incident).
    # Measured through the real chat path over an empty corpus, both
    # directions, plus proof each reply still counts as abstention in the
    # grounding eval.
    from sidra_ai.evals.qa_honesty import evaluate_no_evidence_language

    language = evaluate_no_evidence_language()
    c.add(
        "qa_error_language_match",
        "no-evidence reply speaks the question's language",
        10.0 * language.checks_passed / language.checks_total,
        detail=f"{language.checks_passed}/{language.checks_total} checks; "
               "src/sidra_ai/evals/qa_honesty.py evaluate_no_evidence_language",
        kind=OUTCOME,
    )

    # C-1212: slide bullets carried the corpus's Markdown decoration as
    # literal ## / ** / > characters. Facts are flattened at the seam that
    # makes them; both directions measured - decoration gone, words intact.
    from sidra_ai.evals.fact_text_plain import evaluate_fact_text_plain

    plain = evaluate_fact_text_plain()
    c.add(
        "creation_fact_text_plain",
        "decks and documents quote evidence as prose",
        10.0 * plain.checks_passed / plain.checks_total,
        detail=f"{plain.checks_passed}/{plain.checks_total} checks; "
               "src/sidra_ai/evals/fact_text_plain.py"
               + ("" if plain.passed else "; " + "; ".join(plain.failures)),
        kind=OUTCOME,
    )

    # C-1203: every generated document labelled every fact 「出典不明」 while
    # its sources section said nothing was retrieved - the provenance was
    # read off the chunk instead of chunk.provenance. Measured through the
    # real chat path: the saved artifact must name repository+path for its
    # facts and contain no 出典不明.
    from sidra_ai.evals.document_provenance import evaluate_document_provenance

    provenance_result = evaluate_document_provenance()
    c.add(
        "creation_document_provenance",
        "generated documents name their sources",
        10.0 * provenance_result.checks_passed / provenance_result.checks_total,
        detail=f"{provenance_result.checks_passed}/{provenance_result.checks_total} checks; "
               "src/sidra_ai/evals/document_provenance.py",
        kind=OUTCOME,
    )

    # C-1403: C-1201 put a subject-term floor under the *answer* path and
    # the generators never got it, so a weekly-report request printed
    # jam-making steps under 「わかっていること」 with a repository path
    # beside each one - the shape a reader trusts most. Measured through
    # the real chat path over a corpus that knows two unrelated subjects,
    # both asked for in turn. Three checks per request, and the third is
    # what keeps this honest: a run where retrieval handed over no
    # unrelated evidence at all scores 0, because the other two would pass
    # with the filter deleted.
    from sidra_ai.evals.document_topicality import evaluate_document_topicality

    topicality = evaluate_document_topicality()
    c.add(
        "document_fact_topicality",
        "レポートが依頼の主題だけを根拠に挙げる",
        10.0 * topicality.checks_passed / topicality.checks_total,
        detail=f"{topicality.checks_passed}/{topicality.checks_total} checks "
               f"(clean {topicality.clean}, kept {topicality.kept}, "
               f"mixed {topicality.mixed} of {topicality.mixed_total}); "
               "src/sidra_ai/evals/document_topicality.py",
        kind=OUTCOME,
    )

    # C-1204: every game rendered 2x horizontally squashed on a phone while
    # desktop happened to hit the intrinsic width and looked perfect. The
    # distortion is fully decided by the artifact's canvas attributes vs its
    # canvas CSS rule, so it is checkable offline for the three canvas
    # surfaces (game shell, 3D preview, art).
    from sidra_ai.evals.mobile_aspect import evaluate_mobile_aspect

    aspect = evaluate_mobile_aspect()
    c.add(
        "creation_mobile_aspect",
        "generated canvases keep their shape on a phone",
        10.0 * aspect.checks_passed / aspect.checks_total,
        detail=f"{aspect.checks_passed}/{aspect.checks_total} surfaces; "
               "src/sidra_ai/evals/mobile_aspect.py"
               + ("" if aspect.passed else "; " + "; ".join(aspect.failures)),
        kind=OUTCOME,
    )

    # C-1205: a subject request that fell to the default template used to be
    # announced as satisfied (「「猫」を作りました」 about a fishing page with
    # no cat). Five shapes through the real router: the fallback admitted,
    # three satisfied shapes uncaveated, the genre message intact.
    from sidra_ai.evals.subject_honesty import evaluate_subject_honesty

    subject = evaluate_subject_honesty()
    c.add(
        "creation_subject_honesty",
        "unbuildable subjects are admitted, not renamed",
        10.0 * subject.checks_passed / subject.checks_total,
        detail=f"{subject.checks_passed}/{subject.checks_total} shapes; "
               "src/sidra_ai/evals/subject_honesty.py"
               + ("" if subject.passed else "; " + "; ".join(subject.failures)),
        kind=OUTCOME,
    )

    # C-1209: every generation doubled the file list with its revision
    # sidecar; the listing now shows deliverables only while the sidecar
    # stays downloadable by name for the revise path and debugging.
    from sidra_ai.evals.artifact_listing import evaluate_artifact_listing

    listing = evaluate_artifact_listing()
    c.add(
        "ui_artifact_list_clean",
        "the file list shows deliverables, not plumbing",
        10.0 * listing.checks_passed / listing.checks_total,
        detail=f"{listing.checks_passed}/{listing.checks_total} checks; "
               "src/sidra_ai/evals/artifact_listing.py"
               + ("" if listing.passed else "; " + "; ".join(listing.failures)),
        kind=OUTCOME,
    )

    # C-1211: failures surfaced as bare HTTP codes; the page now maps the
    # reachable classes to Japanese guidance while the error body stays
    # hidden and the code stays printed.
    from sidra_ai.evals.ui_error_guidance import evaluate_ui_error_guidance

    guidance = evaluate_ui_error_guidance()
    c.add(
        "ui_error_guidance",
        "a failed request says what to do next",
        10.0 * guidance.checks_passed / guidance.checks_total,
        detail=f"{guidance.checks_passed}/{guidance.checks_total} checks; "
               "src/sidra_ai/evals/ui_error_guidance.py"
               + ("" if guidance.passed else "; " + "; ".join(guidance.failures)),
        kind=OUTCOME,
    )

    # C-1210: the server carried chat history; the browser page never sent
    # it, so every follow-up question abstained. Mechanics pinned on the
    # page source; the end-to-end run lives in the loop log.
    from sidra_ai.evals.ui_followup import evaluate_ui_followup

    followup = evaluate_ui_followup()
    c.add(
        "ui_followup_capable",
        "the browser can ask a follow-up question",
        10.0 * followup.checks_passed / followup.checks_total,
        detail=f"{followup.checks_passed}/{followup.checks_total} checks; "
               "src/sidra_ai/evals/ui_followup.py"
               + ("" if followup.passed else "; " + "; ".join(followup.failures)),
        kind=OUTCOME,
    )

    # C-1207: the browser entry declared lang=ja and spoke English. Both
    # directions on the rendered page: boilerplate gone AND the Japanese
    # labels present, so deleting a label cannot pass as translating it.
    from sidra_ai.evals.ui_language import evaluate_ui_language

    ui_language = evaluate_ui_language()
    c.add(
        "ui_entry_japanese",
        "the browser entry speaks the operator's language",
        10.0 * ui_language.checks_passed / ui_language.checks_total,
        detail=f"{ui_language.checks_passed}/{ui_language.checks_total} strings; "
               "src/sidra_ai/evals/ui_language.py"
               + ("" if ui_language.passed else "; " + "; ".join(ui_language.failures[:3])),
        kind=OUTCOME,
    )

    # C-1208: the with-evidence framing (the line every answered question
    # opens with) also follows the question's language now; C-1202 covered
    # only the no-evidence reply. Both languages through real chat, plus
    # proof both answers still pass the grounding eval.
    from sidra_ai.evals.qa_honesty import evaluate_answer_language

    answer_language = evaluate_answer_language()
    c.add(
        "qa_answer_language_match",
        "answered questions are framed in their language",
        10.0 * answer_language.checks_passed / answer_language.checks_total,
        detail=f"{answer_language.checks_passed}/{answer_language.checks_total} checks; "
               "src/sidra_ai/evals/qa_honesty.py evaluate_answer_language",
        kind=OUTCOME,
    )

    honesty = evaluate_qa_honesty()
    c.add(
        "qa_offtopic_honesty",
        "off-topic questions honestly refused",
        10.0 * (honesty.refused_offtopic + honesty.kept_ontopic) / len(PROBES),
        detail=f"{honesty.refused_offtopic}/{honesty.offtopic_total} off-topic refused, "
               f"{honesty.kept_ontopic}/{honesty.ontopic_total} on-topic kept; "
               "src/sidra_ai/evals/qa_honesty.py (synthetic corpus)",
        kind=OUTCOME,
    )

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


#: Plays a generated fishing page in node with a *recording* 2D context and
#: reports whether a filled body+tail land inside the band the page painted.
#: The environment stub mirrors sidra_ai.creation.duel.PROBE; the context
#: records instead of swallowing, because this metric is about what is drawn.
_FISHING_DRAW_PROBE = """
const calls=[];let path=[],ell=null,style='';
const recorder={
  get fillStyle(){return style},set fillStyle(v){style=String(v)},
  fillRect(x,y,w,h){calls.push({t:'rect',x,y,w,h})},
  beginPath(){path=[];ell=null},
  moveTo(x,y){path.push([x,y])},lineTo(x,y){path.push([x,y])},
  ellipse(x,y){ell={x:x,y:y}},closePath(){},
  fill(){if(ell){calls.push({t:'body',x:ell.x,y:ell.y});ell=null}
    else if(path.length){const xs=path.map(p=>p[0]),ys=path.map(p=>p[1]);
      calls.push({t:'tail',x:(Math.min(...xs)+Math.max(...xs))/2,
        y:(Math.min(...ys)+Math.max(...ys))/2});path=[]}},
};
const cxProxy=new Proxy(recorder,{
  get:(t,k)=>k in t?t[k]:()=>{},set:(t,k,v)=>{if(k in t){t[k]=v}return true}});
const keyHandlers=[];
globalThis.matchMedia=()=>({matches:false});
globalThis.performance={now:()=>0};
globalThis.addEventListener=(type,fn)=>{if(type==='keydown')keyHandlers.push(fn)};
globalThis.Image=function(){return {}};
globalThis.document={getElementById:()=>({
  width:720,height:320,style:{},addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:720,height:320}),
  getContext:()=>cxProxy})};
let queued=null;
globalThis.requestAnimationFrame=(fn)=>{queued=fn;return 1};
SCRIPT_PLACEHOLDER
function run(n){for(let i=0;i<n&&queued;i++){const fn=queued;queued=null;fn(i*16)}}
const press={key:' ',code:'Space',preventDefault(){},stopImmediatePropagation(){}};
keyHandlers.forEach(fn=>fn(press));
run(4);
/* The band: the page's own zone highlight - on the line (y=134, h=52) but
   narrower than the full 640px line it sits on. */
const band=calls.find(c=>c.t==='rect'&&Math.round(c.y)===134&&Math.round(c.h)===52
  &&c.w>0&&c.w<600&&c.x>40);
let bodyInBand=false,tailInBand=false;
if(band){
  bodyInBand=calls.some(c=>c.t==='body'&&c.x>=band.x-20&&c.x<=band.x+band.w+20
    &&Math.abs(c.y-160)<24);
  tailInBand=calls.some(c=>c.t==='tail'&&c.x>=band.x-30&&c.x<=band.x+band.w+30
    &&Math.abs(c.y-160)<24);
}
console.log(JSON.stringify({band:!!band,bodyInBand:bodyInBand,tailInBand:tailInBand}));
"""


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
                "巨大な怪獣と戦うゲームを作って",
                "レースゲームを作って",
                "横スクロールのゲームを作って",
                "3D のゲームを作って",
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
            # レース left this list when its template landed; 格闘 is still
            # on the apology side of the table, so the wording keeps having
            # a real gap to describe.
            for text in ("シューティングゲームを作って", "パズルゲームを作って", "格闘ゲームを作って")
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

    # --- the fishing target is actually drawn ---------------------------
    #
    # C-1206: the default template's target was `sprite('target',...,'')` -
    # nothing at all on a standalone page - while the code computed a bob
    # animation for it. Checked by *playing the page in node* with a
    # recording context, because the cheap fake here is a fish drawn
    # anywhere: the fill has to land inside the band the page itself painted.
    import re as _fish_re
    import subprocess as _fish_sp

    fish_page = generate_game("ゲームを作って").html
    fish_reasons = []
    fish_script = _fish_re.search(r"<script>(.*?)</script>", fish_page, _fish_re.S)
    if fish_script is None:
        fish_reasons.append("no script")
    else:
        try:
            probe = _fish_sp.run(
                ["node", "-"],
                input=_FISHING_DRAW_PROBE.replace(
                    "SCRIPT_PLACEHOLDER", fish_script.group(1)
                ),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if probe.returncode != 0:
                fish_reasons.append(probe.stderr.strip()[:80])
            else:
                seen = json.loads(probe.stdout)
                if not seen.get("band"):
                    fish_reasons.append("the band itself was not painted")
                elif not seen.get("bodyInBand"):
                    fish_reasons.append("no filled body lands inside the band")
                elif not seen.get("tailInBand"):
                    fish_reasons.append("the body has no tail (a bare blob)")
        except (OSError, _fish_sp.SubprocessError, ValueError) as exc:
            fish_reasons.append(f"probe unavailable: {type(exc).__name__}")
    if not validate_game_html(fish_page)["playable"]:
        fish_reasons.append("page no longer parses")
    c.add(
        "creation_fishing_target_drawn",
        "釣りの的（魚）が描かれている",
        0.0 if fish_reasons else 1.0,
        detail=(
            "a filled body and tail land inside the page's own band"
            if not fish_reasons
            else "; ".join(fish_reasons)
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

    # --- a fight against something bigger than the player ---------------
    #
    # Every enemy this generator could build was the player's own size and
    # arrived in quantity; the owner's viewing notes (§6) say scale is a set
    # of rules, not a sprite size. All three load-bearing ones are checked by
    # *playing the page in node*, because each has a cheap fake that a source
    # check would pass: a huge sprite (rather than a withheld body), a boss
    # that dies to any shot (rather than to the leg-then-head cycle), and an
    # attack clock invented instead of taken from the measurement.
    import re as _kaiju_re
    import subprocess as _kaiju_sp

    from sidra_ai.creation.kaiju import probe_source as _kaiju_probe

    kaiju_reasons = []
    kaiju_seen = None
    kaiju_game = generate_game("巨大な怪獣と戦うゲームを作って")
    if kaiju_game.template != "kaiju":
        kaiju_reasons.append(f"routed to {kaiju_game.template}")
    if not validate_game_html(kaiju_game.html)["playable"]:
        kaiju_reasons.append("page does not parse")
    # The genre is buildable now, so a franchise request routes instead of
    # apologising - which makes the name guard the only thing between it and
    # an artifact carrying the name.
    named = generate_game("ゴジラのゲームを作って")
    if named.template != "kaiju":
        kaiju_reasons.append(f"the franchise request routed to {named.template}")
    if "ゴジラ" in named.html:
        kaiju_reasons.append("the franchise name reached the artifact")
    if "オリジナル版" not in named.tagline:
        kaiju_reasons.append("the rename is silent")
    script = _kaiju_re.search(r"<script>(.*?)</script>", kaiju_game.html, _kaiju_re.S)
    if script is None:
        kaiju_reasons.append("no script")
    else:
        try:
            probe = _kaiju_sp.run(
                ["node", "-"],
                input=_kaiju_probe(script.group(1)),
                capture_output=True,
                text=True,
                timeout=90,
            )
            if probe.returncode != 0:
                kaiju_reasons.append(f"probe failed: {probe.stderr.strip()[:60]}")
            else:
                kaiju_seen = json.loads(probe.stdout)
        except (OSError, _kaiju_sp.SubprocessError, ValueError) as exc:
            kaiju_reasons.append(f"probe unavailable ({type(exc).__name__})")
    if kaiju_seen is not None:
        # 観察 1: the body is what you do not draw. Never while it lives;
        # once, when it is down. A metric that only checked the second half
        # would pass a page that drew the whole monster the entire time.
        if kaiju_seen["bodyWhileAlive"]:
            kaiju_reasons.append("the whole body was drawn while the boss was alive")
        if not kaiju_seen["shown"]:
            kaiju_reasons.append("the body is never shown, even beaten")
        # The leg phase is a decision only if missing it costs the shot.
        if kaiju_seen["cyclesAfterMisses"] or (
            kaiju_seen["legHpAfterMisses"] != kaiju_seen["legHpStart"]
        ):
            kaiju_reasons.append("shots that hit nothing still hurt the boss")
        if not kaiju_seen["sawOpen"]:
            kaiju_reasons.append("the weak point never opens")
        # 3 cycles, not 1: the fight has a shape or it is a health bar.
        if kaiju_seen["cycles"] != 3 or kaiju_seen["kills"] != 3:
            kaiju_reasons.append(
                f"took {kaiju_seen['cycles']} cycle(s), not 3"
            )
        if kaiju_seen["state"] != "won":
            kaiju_reasons.append(f"the fight ended {kaiju_seen['state']}")
        # The measured cut length, ported as a number rather than a mood.
        if kaiju_seen["beat"] != 126:
            kaiju_reasons.append(
                f"attack interval {kaiju_seen['beat']} frames, not the measured 126"
            )
    c.add(
        "creation_kaiju_playable",
        "自分より大きいものと戦える",
        0.0 if kaiju_reasons or kaiju_seen is None else 1.0,
        detail=(
            "the body is withheld while it lives and shown once beaten; wasted "
            "shots cost nothing; leg then weak point, three cycles; attacks on "
            "the measured 126-frame (2.1s) beat; the franchise name is renamed"
            if kaiju_seen is not None and not kaiju_reasons
            else "; ".join(kaiju_reasons) or "the fight could not be played"
        ),
        kind=OUTCOME,
    )

    # C-1404 (b): easy's three laps outlasted the shared sixty-second clock,
    # so the gentlest rung was the one nobody finishes. The ladder's paces
    # stay and easy runs two laps; every rung is driven for real and counted
    # finishable only if it reaches the goal with one time per lap.
    from sidra_ai.evals.race_rungs import evaluate_race_rungs

    rungs = evaluate_race_rungs()
    c.add(
        "creation_race_rungs_finishable",
        "レースの全難度がクロック内に完走できる",
        float(rungs.finishable),
        detail=f"{rungs.finishable}/{rungs.rungs} rungs driven to the goal; "
               "src/sidra_ai/evals/race_rungs.py"
               + ("" if not rungs.failures else "; " + "; ".join(rungs.failures)),
        kind=OUTCOME,
    )

    # --- a race against the clock, judged by driving it ------------------
    #
    # レース sat on the apology side of the genre table. What separates a
    # race from a scroller with a car drawn on it is checked by *driving the
    # page in node*, because each rule has a cheap fake a source check would
    # pass: steering that moves nothing, obstacles that are scenery (contact
    # must cost speed, and only speed - 即死 would make the lap timer
    # decoration), and a lap counter that is a label rather than a finish.
    # The one source check kept is the honest-silence rule: a game with no
    # combat must not raise the combat loudness step.
    import re as _race_re
    import subprocess as _race_sp

    from sidra_ai.creation.games import TEMPLATES as _RACE_TEMPLATES
    from sidra_ai.creation.racing import probe_source as _race_probe

    race_reasons = []
    race_seen = None
    race_game = generate_game("レースゲームを作って")
    if race_game.template != "racing":
        race_reasons.append(f"routed to {race_game.template}")
    if not validate_game_html(race_game.html)["playable"]:
        race_reasons.append("page does not parse")
    if "combat(" in _RACE_TEMPLATES["racing"].script:
        race_reasons.append("a game with no combat claims the combat step")
    race_script = _race_re.search(r"<script>(.*?)</script>", race_game.html, _race_re.S)
    if race_script is None:
        race_reasons.append("no script")
    else:
        try:
            probe = _race_sp.run(
                ["node", "-"],
                input=_race_probe(race_script.group(1)),
                capture_output=True,
                text=True,
                timeout=90,
            )
            if probe.returncode != 0:
                race_reasons.append(f"probe failed: {probe.stderr.strip()[:60]}")
            else:
                race_seen = json.loads(probe.stdout)
        except (OSError, _race_sp.SubprocessError, ValueError) as exc:
            race_reasons.append(f"probe unavailable ({type(exc).__name__})")
    if race_seen is not None:
        if not (race_seen["leftMoved"] < -30 and race_seen["rightMoved"] > 30):
            race_reasons.append("steering does not move the car both ways")
        # Contact is a time penalty: the pace is cut and the run continues.
        if race_seen["spdAfterHit"] >= race_seen["base"] * 0.55:
            race_reasons.append("an obstacle costs no speed")
        if race_seen["graceAfterHit"] <= 0:
            race_reasons.append("the hit never registered")
        if race_seen["state"] != "goal" or race_seen["lapTimes"] != 3:
            race_reasons.append(
                f"finished {race_seen['state']} with "
                f"{race_seen['lapTimes']} lap time(s), not 3"
            )
        # §7 観察 6 at lap scale: the final lap is the brightest frame.
        scenes = race_seen["scenes"]
        if len(scenes) != 3 or not (
            scenes[2]["lum"] > scenes[0]["lum"] and scenes[2]["lum"] >= scenes[1]["lum"]
        ):
            race_reasons.append("the final lap is not the brightest scene")
    c.add(
        "creation_racing_playable",
        "周回レースが作れる",
        0.0 if race_reasons or race_seen is None else 1.0,
        detail=(
            "steering moves both ways; an obstacle costs speed and not the "
            "run; three counted laps with a time each; the final lap is the "
            "brightest; no combat step claimed"
            if race_seen is not None and not race_reasons
            else "; ".join(race_reasons) or "the race could not be driven"
        ),
        kind=OUTCOME,
    )

    # --- the platformer, same bar: the jump is judged by playing it ------
    #
    # The genre's craft is two deliberate non-physics rules - coyote frames
    # after a ledge and a jump cut on early release - and each has a cheap
    # fake a source check would pass: a window that never closes is a double
    # jump, a cut that never fires makes the press length a label, and a
    # "respawn" could be a reload. So the course is driven in node: a late
    # edge jump, a mid-fall jump, two falls, the gem-lit lantern (§5's sink)
    # and the flag, with the scene walk (§7) read off the same run. The one
    # negative claim is checked at the source, because it is about absence:
    # this template has no fight, so it must never call combat().
    import re as _plat_re
    import subprocess as _plat_sp

    from sidra_ai.creation.games import TEMPLATES as _PLAT_TEMPLATES
    from sidra_ai.creation.platformer import probe_source as _plat_probe

    plat_reasons = []
    plat_seen = None
    plat_game = generate_game("横スクロールのゲームを作って")
    if plat_game.template != "platformer":
        plat_reasons.append(f"routed to {plat_game.template}")
    if not validate_game_html(plat_game.html)["playable"]:
        plat_reasons.append("page does not parse")
    if "combat(" in _PLAT_TEMPLATES["platformer"].script:
        plat_reasons.append("a template with no fight claims the combat step")
    script = _plat_re.search(r"<script>(.*?)</script>", plat_game.html, _plat_re.S)
    if script is None:
        plat_reasons.append("no script")
    else:
        try:
            probe = _plat_sp.run(
                ["node", "-"],
                input=_plat_probe(script.group(1)),
                capture_output=True,
                text=True,
                timeout=90,
            )
            if probe.returncode != 0:
                plat_reasons.append(f"probe failed: {probe.stderr.strip()[:60]}")
            else:
                plat_seen = json.loads(probe.stdout)
        except (OSError, _plat_sp.SubprocessError, ValueError) as exc:
            plat_reasons.append(f"probe unavailable ({type(exc).__name__})")
    if plat_seen is not None:
        # The window has to be a real handful of frames, open just after the
        # ledge and closed a few frames later.
        if not 5 <= plat_seen["window"] <= 7:
            plat_reasons.append(f"coyote window is {plat_seen['window']} frames")
        if not plat_seen["coyoteJump"]:
            plat_reasons.append("a jump just after the ledge is eaten")
        if not plat_seen["lateJumpRefused"]:
            plat_reasons.append("a jump ten frames into the fall still works")
        # Early release lowers the arc, or the press length decides nothing.
        if not plat_seen["tapMin"] - plat_seen["heldMin"] > 10:
            plat_reasons.append("holding and tapping jump reach the same height")
        # Falling is a walk back, never the run.
        if plat_seen["firstRespawnState"] != "play":
            plat_reasons.append("a fall ends the game instead of respawning")
        # §5: the gems leave when the lantern lights, and the respawn moves.
        if plat_seen["gemsAfterOrb"] != plat_seen["gemsBefore"] + 1:
            plat_reasons.append("a gem does not count")
        if not plat_seen["lampLit"] or plat_seen["gemsAfterLamp"] != 0:
            plat_reasons.append("the lantern is not a sink")
        if plat_seen["thirdRespawnX"] != plat_seen["lampX"]:
            plat_reasons.append("the lit lantern does not move the respawn")
        if plat_seen["state"] != "goal":
            plat_reasons.append(f"the flag left the run {plat_seen['state']}")
        # §7: three stretches, told apart by hue, brightest kept for last.
        scenes = plat_seen.get("scenes") or []
        if len({s["floor"] for s in scenes}) != 3:
            plat_reasons.append(f"{len(scenes)} scene(s), or shared floors")
        elif max(range(3), key=lambda i: scenes[i]["lum"]) != 2:
            plat_reasons.append("the goal stretch is not the brightest")
        if plat_seen["combatOn"]:
            plat_reasons.append("the combat step came on with no fight to raise it")
    c.add(
        "creation_platformer_playable",
        "横スクロールで跳んで渡れる",
        0.0 if plat_reasons or plat_seen is None else 1.0,
        detail=(
            "coyote frames land a late edge jump and expire mid-fall; an early "
            "release lowers the arc; falls respawn at the start or the gem-lit "
            "lantern; the flag completes; three palettes with the goal brightest; "
            "no combat step claimed"
            if plat_seen is not None and not plat_reasons
            else "; ".join(plat_reasons) or "the course could not be played"
        ),
        kind=OUTCOME,
    )

    # --- the model finally touches something it makes -------------------
    #
    # `with_copy` was the designed and only hole for a local model, and for
    # its whole life nothing called it: the model's contribution to every
    # artifact was zero bits (C-1027). Wiring it is easy to fake - a metric
    # that only checked "a title changed" would pass on a generator that
    # ignored the model and renamed pages by itself. So this drives the real
    # generator with injected backends and asks for **both directions**: a
    # model that answers gets its wording onto the saved page, and a model
    # that fails, names a franchise, or is the echo default gets nothing,
    # with the deterministic page still playable underneath.
    import tempfile as _copy_tmp
    from pathlib import Path as _CopyPath

    from sidra_ai.creation.copy_writer import build_copy_writer as _build_copy
    from sidra_ai.creation.game_job import build_game_generator as _build_game_gen
    from sidra_ai.creation.intent import detect_creation_intent as _copy_intent
    from sidra_ai.models.base import GenerationResult as _CopyResult
    from sidra_ai.models.base import LocalModelAdapter as _CopyAdapter
    from sidra_ai.models.echo import EchoModelAdapter as _CopyEcho

    class _CopyFake(_CopyAdapter):
        """A backend that is not echo and says exactly what it is told to."""

        backend = "fake-local"

        def __init__(self, text: str, *, fail: bool = False) -> None:
            super().__init__("fake-local-1")
            self.text = text
            self.fail = fail
            self.calls = 0

        def generate(self, request):  # noqa: ANN001 - metric-local stub
            self.calls += 1
            if self.fail:
                raise RuntimeError("backend down")
            return _CopyResult(text=self.text, backend=self.backend, model=self.model)

    copy_reasons = []
    with _copy_tmp.TemporaryDirectory() as _copy_dir:
        _copy_ask = "釣りゲームを作って"
        _copy_it = _copy_intent(_copy_ask)

        def _run(writer):
            return _build_game_gen(_copy_dir, writer)(_copy_ask, _copy_it)

        plain = _run(None)
        answered = _CopyFake('{"title": "朝凪の一本", "tagline": "潮が動く前に。"}')
        spoken = _run(_build_copy(answered))
        if not spoken.details.get("model_copy"):
            copy_reasons.append("a model that answered was not consulted")
        elif spoken.details.get("model_title") != "朝凪の一本":
            copy_reasons.append("the model's title did not reach the outcome")
        elif "朝凪の一本" not in _CopyPath(spoken.artifact_path).read_text(encoding="utf-8"):
            copy_reasons.append("the model's title did not reach the saved page")
        if not spoken.details.get("playable"):
            copy_reasons.append("the page stopped being playable once copy was applied")

        # Every way of failing has to look like the no-model page, which is
        # the property that makes a missing model cost wording and nothing
        # else. Compared against `plain` rather than against a constant.
        for label, backend in (
            ("prose instead of JSON", _CopyFake("Sure! How about Fishing Time?")),
            ("a franchise name", _CopyFake('{"title": "ゼルダの釣り", "tagline": "剣を置け"}')),
            ("a title of 400 characters", _CopyFake('{"title": "' + "あ" * 400 + '"}')),
            ("markup in the title", _CopyFake('{"title": "<script>x</script>"}')),
            ("an unreachable backend", _CopyFake("", fail=True)),
            ("the echo default", _CopyEcho()),
        ):
            got = _run(_build_copy(backend))
            if got.details.get("model_copy"):
                copy_reasons.append(f"{label} was accepted as copy")
            elif got.summary != plain.summary:
                copy_reasons.append(f"{label} changed the page anyway")
            elif not got.details.get("playable"):
                copy_reasons.append(f"{label} cost the page its playability")
        # The echo default must be refused *before* the call: asking it and
        # discarding the answer would spend a generation on every request on
        # every clean checkout.
        counted = _CopyFake('{"title": "朝凪の一本"}')
        _run(_build_copy(counted))
        if counted.calls != 1:
            copy_reasons.append(f"the writer called the backend {counted.calls} times")
    c.add(
        "creation_model_copy",
        "モデルが作ったものに触れる",
        0.0 if copy_reasons else 1.0,
        detail=(
            "an injected model names the saved page; prose, a franchise name, an "
            "oversized title, markup, an unreachable backend and the echo default "
            "all leave the deterministic page exactly as it was"
            if not copy_reasons
            else "; ".join(copy_reasons)
        ),
        kind=OUTCOME,
    )

    # --- and the deck, on the deck's own terms ---------------------------
    #
    # `GeneratedDeck.with_copy` takes a title and no bullets, because a
    # bullet is where a number gets reworded into existence. So the deck's
    # instrument asks for one thing the game's does not: that the model's
    # title carries no figure, and that nothing below the title moved. A
    # metric that only checked "the title changed" would pass a deck whose
    # heading now claims 3億円 nobody retrieved.
    from sidra_ai.creation.deck_job import build_deck_generator as _build_deck_gen
    from sidra_ai.creation.decks import Fact as _CopyFact

    deck_copy_reasons = []
    with _copy_tmp.TemporaryDirectory() as _deck_dir:
        _deck_ask = "この製品の提案資料を作って"
        _deck_it = _copy_intent(_deck_ask)
        _deck_facts = [
            _CopyFact(
                text="SIDRA AI は 5 リポジトリを索引し、外部 API を使わない。",
                source="docs/OUTCOMES.md",
            )
        ]

        def _deck_run(writer):
            return _build_deck_gen(_deck_dir, None, writer)(_deck_ask, _deck_it, _deck_facts)

        deck_plain = _deck_run(None)
        deck_named = _deck_run(_build_copy(_CopyFake('{"title": "自前で答える索引"}')))
        if not deck_named.details.get("model_copy"):
            deck_copy_reasons.append("a model that answered was not consulted")
        elif "自前で答える索引" not in _CopyPath(deck_named.artifact_path).read_text(
            encoding="utf-8"
        ):
            deck_copy_reasons.append("the model's title did not reach the saved deck")
        # Renaming a deck may not change what is on it, or how much of it is
        # still blank: those are the numbers an operator presents from.
        for field in ("outline", "slides", "unfilled", "numbers_sourced"):
            if deck_named.details.get(field) != deck_plain.details.get(field):
                deck_copy_reasons.append(f"renaming the deck changed {field}")

        for label, backend in (
            ("a figure in the title", _CopyFake('{"title": "3億円の計画"}')),
            ("a franchise name", _CopyFake('{"title": "マリオの提案"}')),
            ("prose instead of JSON", _CopyFake("How about The Big Pitch?")),
            ("an unreachable backend", _CopyFake("", fail=True)),
            ("the echo default", _CopyEcho()),
        ):
            got = _deck_run(_build_copy(backend))
            if got.details.get("model_copy"):
                deck_copy_reasons.append(f"{label} was accepted as a deck title")
            elif got.summary != deck_plain.summary:
                deck_copy_reasons.append(f"{label} changed the deck anyway")
    c.add(
        "creation_deck_model_copy",
        "モデルが資料の題も書ける",
        0.0 if deck_copy_reasons else 1.0,
        detail=(
            "an injected model names the saved deck while its slides, blanks and "
            "sourcing are untouched; a figure in the title, a franchise name, prose, "
            "an unreachable backend and the echo default are all refused"
            if not deck_copy_reasons
            else "; ".join(deck_copy_reasons)
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

    gated, gate_gaps, briefings = [], [], {}
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
        briefings[key] = seen.get("brief")
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

    # --- and the screen says what you are for, not only which keys ------
    #
    # §6 観察 3: the escalation the owner's episode uses opens on a briefing
    # table, and that scene is why the shooting afterwards reads as something
    # going wrong rather than as noise. A title plus a control list says which
    # buttons exist; it does not say what the player is *for*.
    #
    # Counted off the same running page as the gate above, so a briefing
    # constant that never reached the screen cannot pass. Three further
    # things are checked, because each is how a briefing goes hollow: a line
    # that is blank, a control line naming keys the template does not have,
    # and one boilerplate objective pasted across every template.
    from sidra_ai.creation.story import CONTROLS as _BRIEF_CONTROLS

    briefed, brief_gaps = [], []
    objectives = []
    for key in sorted(_GATE_TEMPLATES):
        lines = briefings.get(key)
        if key not in gated:
            brief_gaps.append(f"{key}: the screen it would print on is not gated")
            continue
        if not isinstance(lines, list) or len(lines) != 3:
            brief_gaps.append(f"{key}: no briefing reached the screen")
            continue
        if any(not str(line).strip() for line in lines):
            brief_gaps.append(f"{key}: a briefing line is blank")
            continue
        # The control line has to name a key this template actually reads.
        # Two tables of the same fact drift; this asks rather than copies.
        keys = [k for k, _ in _BRIEF_CONTROLS.get(key, ())]
        tokens = [t for k in keys for t in k.replace("/", " ").split() if t]
        if tokens and not any(token in lines[1] for token in tokens):
            brief_gaps.append(f"{key}: the control line names none of {keys}")
            continue
        objectives.append(lines[0])
        briefed.append(key)
    if len(set(objectives)) != len(objectives):
        brief_gaps.append("the objective line is boilerplate shared by templates")
        briefed = []
    c.add(
        "creation_briefing_screens",
        "何をする番かを先に言う開始画面",
        float(len(briefed)),
        detail=(
            f"{', '.join(briefed)}: 目標 / 操作 / 敵 on the title screen, each "
            "template's own, control line agreeing with its key table"
            if not brief_gaps
            else "; ".join(brief_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the fight is louder than the walking around ---------------------
    #
    # §6 観察 4: the episode's combat windows sit at -13.8..-16.5 LUFS and
    # are audibly louder than its dialogue - the film does not only play
    # different sounds when the fighting starts, it plays them louder.
    #
    # Three ways this goes wrong, all checked on the running page with a
    # recording AudioContext rather than by reading the source: the step is
    # declared and never reaches the gain, it quietly overrides the
    # operator's mute, or it lets a fight clip. A fourth is the one a source
    # check cannot see at all - `combat(true)` sitting behind a condition
    # that is never true - so the templates with a fight have to turn it on
    # by themselves while being played, and the templates without one have
    # to leave it off rather than claim a fight they do not have.
    import re as _loud_re
    import subprocess as _loud_sp

    from sidra_ai.creation.audio import COMBAT_GAIN, MAX_GAIN
    from sidra_ai.creation.audio import probe_source as _loud_probe

    #: Templates whose play state *is* a fight, so the step has to be on
    #: while they are simply being played.
    fights = {"duel", "kaiju", "shooter"}
    #: The adventure raises the step only while an enemy is near - the better
    #: design, because the quiet stretches are what make the loud ones read as
    #: loud. It therefore reports "off" when merely played, which is
    #: indistinguishable from a clause that can never fire, so the probe puts
    #: an enemy on the hero and asks again (C-1035).
    conditional = {"adventure"}
    quiet = {"fishing", "catch", "puzzle", "platformer"}
    loud_reasons = []
    loud_verified = []
    for key in sorted(_GATE_TEMPLATES):
        page = generate_game("ゲームを作って", template=key).html
        script = _loud_re.search(r"<script>(.*?)</script>", page, _loud_re.S)
        if script is None:
            loud_reasons.append(f"{key}: no script")
            continue
        try:
            probe = _loud_sp.run(
                ["node", "-"],
                input=_loud_probe(script.group(1)),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if probe.returncode != 0:
                loud_reasons.append(f"{key}: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout)
        except (OSError, _loud_sp.SubprocessError, ValueError) as exc:
            loud_reasons.append(f"{key}: probe unavailable ({type(exc).__name__})")
            continue
        if not seen["hasCombat"]:
            loud_reasons.append(f"{key}: no combat step on the page")
            continue
        if not seen["calm"] or not seen["loud"]:
            loud_reasons.append(f"{key}: nothing was played")
        elif seen["loud"] <= seen["calm"]:
            loud_reasons.append(f"{key}: combat is not louder ({seen['loud']})")
        elif abs(seen["loud"] - min(MAX_GAIN, seen["calm"] * COMBAT_GAIN)) > 1e-6:
            loud_reasons.append(f"{key}: the step is not the declared one")
        # Mute is the operator's, not the game's.
        if seen["mutedPlayed"]:
            loud_reasons.append(f"{key}: muted, and the fight played anyway")
        if seen["backToCalm"] != seen["calm"]:
            loud_reasons.append(f"{key}: the step does not come back down")
        if seen["peak"] > MAX_GAIN + 1e-6:
            loud_reasons.append(f"{key}: a fight can reach {seen['peak']}")
        if key in fights and not seen["combatDuringPlay"]:
            loud_reasons.append(f"{key}: has a fight and never raises the step")
        if key in quiet and seen["combatDuringPlay"]:
            loud_reasons.append(f"{key}: claims a fight it does not have")
        if key in conditional and seen.get("nearEnemy") is not True:
            loud_reasons.append(
                f"{key}: the near-enemy clause never fired ({seen.get('nearEnemy')})"
            )
        if not any(key in reason for reason in loud_reasons):
            loud_verified.append(key)
    c.add(
        "creation_combat_loudness",
        "戦闘だけ音が大きい",
        0.0 if loud_reasons else 1.0,
        detail=(
            f"every page raises the gain x{COMBAT_GAIN:g} in combat and comes back "
            f"down, never past {MAX_GAIN:g}, never past M; "
            f"{', '.join(sorted(fights))} turn it on while played, "
            f"{', '.join(sorted(conditional))} when an enemy is on the hero, and "
            f"{', '.join(sorted(quiet))} leave it off"
            if not loud_reasons
            else "; ".join(loud_reasons)
        ),
        kind=OUTCOME,
    )
    c.add(
        "creation_combat_verified",
        "戦闘の音量規則を実測できた型",
        float(len(loud_verified)),
        detail=(
            f"{', '.join(loud_verified)}: gain step, mute, ceiling and the "
            "template's own use of it, all read off the running page"
        ),
        kind=OUTCOME,
    )

    # --- a room you can tell from the last room --------------------------
    #
    # §7 観察 5-6, from the machine-extracted colour script of the episode:
    # scenes are told apart by one accent hue over a shared neutral base, and
    # the brightest frame of the whole episode is spent on the climax. SIDRA
    # had neither - three adventure rooms on one palette, one kaiju backdrop
    # for every phase.
    #
    # Both halves are read off the running page. "The palette table exists"
    # and "the page paints with it" are different facts, and the second is
    # the one worth a number, so the probe asks the page for the colour it
    # would actually fill with in each scene and for that colour's
    # luminance. The peak has to be the LAST scene, not merely present.
    #
    # Themed pages are measured too. A scene palette that replaced the theme
    # instead of shifting it would still show three colours here while
    # having quietly undone 「テーマを指定すると配色が変わる」, and a step
    # taken in HSL lightness rather than luminance did let a green room
    # outshine the climax on the light theme - both were caught by running
    # all four themes rather than the default one.
    import re as _scene_re
    import subprocess as _scene_sp

    from sidra_ai.creation.adventure import world_probe as _adv_probe
    from sidra_ai.creation.kaiju import probe_source as _kaiju_scene_probe
    from sidra_ai.creation.marble import probe_source as _marble_scene_probe
    from sidra_ai.creation.shooter import probe_source as _shooter_scene_probe
    from sidra_ai.creation.themes import select_theme as _scene_theme

    #: request phrase -> (template key, probe builder). The templates with
    #: more than one scene to tell apart, and only those: rooms for the
    #: adventure, phases for the kaiju, acts of the round for the shooter
    #: (C-1301), thirds of the corridor for the marble (C-1307). A
    #: single-scene template would inflate the count.
    _scene_targets = (
        ("迷宮を冒険するゲームを作って", "adventure", _adv_probe),
        ("巨大怪獣と戦うゲームを作って", "kaiju", _kaiju_scene_probe),
        ("シューティングゲームを作って", "shooter", _shooter_scene_probe),
        ("玉転がしゲームを作って", "marble", _marble_scene_probe),
    )
    #: One request per theme, so the default is measured alongside the three
    #: named ones. The default is the empty suffix.
    _scene_themes = ("", "紙のテーマで", "ターミナルのテーマで", "dusk のテーマで")

    def _srgb_lum(hexcolour: str) -> float:
        raw = hexcolour.lstrip("#")
        parts = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def _wcag(a: float, b: float) -> float:
        hi, lo = max(a, b), min(a, b)
        return (hi + 0.05) / (lo + 0.05)

    scene_gaps: list[str] = []
    scene_ok: list[str] = []
    for request, key, builder in _scene_targets:
        for suffix in _scene_themes:
            label = f"{key}/{suffix or 'default'}"
            page = generate_game(f"{request} {suffix}".strip()).html
            script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
            if script is None:
                scene_gaps.append(f"{label}: no script")
                continue
            try:
                probe = _scene_sp.run(
                    ["node", "-"],
                    input=builder(script.group(1)),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if probe.returncode != 0:
                    scene_gaps.append(f"{label}: {probe.stderr.strip()[:60]}")
                    continue
                seen = json.loads(probe.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                scene_gaps.append(f"{label}: probe unavailable ({type(exc).__name__})")
                continue
            scenes = seen.get("scenes") or []
            if len(scenes) < 3:
                scene_gaps.append(f"{label}: {len(scenes)} scene(s) reported")
                continue
            if len({s["floor"] for s in scenes}) != len(scenes):
                scene_gaps.append(f"{label}: two scenes paint the same floor")
                continue
            peak = max(range(len(scenes)), key=lambda i: scenes[i]["lum"])
            if peak != len(scenes) - 1:
                scene_gaps.append(f"{label}: the brightest scene is #{peak}, not last")
                continue
            # The palette carries mood; the terrain is still shape and value.
            # A tint that flattened the wall against the floor would be a
            # safety number traded for a decorative one.
            tokens = _scene_theme(f"{request} {suffix}".strip()).tokens
            floors = _wcag(
                _srgb_lum(tokens["surface"]), _srgb_lum(tokens["border"])
            )
            worst = min(_wcag(s["lum"], s["wallLum"]) for s in scenes)
            if worst < floors - 0.02:
                scene_gaps.append(
                    f"{label}: wall/floor value gap falls to {worst:.2f} "
                    f"(untinted {floors:.2f})"
                )
                continue
            scene_ok.append(label)
    c.add(
        "creation_scene_palettes",
        "場面ごとに色が変わる型",
        float(len({label.split("/")[0] for label in scene_ok}))
        if not scene_gaps
        else 0.0,
        detail=(
            "adventure の部屋間・kaiju の phase 間・shooter の幕間・marble の"
            "コース 3 分割で実際の描画色が変わり、最も明るい場面が最終部に"
            "ある。4 テーマすべてで確認、壁と床の明度差はテーマ既定値のまま"
            if not scene_gaps
            else "; ".join(scene_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the crescendo is in the fight, not only in the paint ----------
    #
    # §6 観察 3: escalation has a shape - the same fight, re-accelerated.
    # C-1301 gave the shooter's round three acts of sky; this number asks
    # whether the fight itself escalates. Measured off the flown page: the
    # probe pilots the round into the final act and reads back, per act,
    # how many waves actually spawned and how fast they actually fell. A
    # palette stepping over a flat fight passes the scene number and fails
    # this one - the docstring's "waves ... get faster" has to be a fact
    # about the running page.
    esc_gaps: list[str] = []
    esc_page = generate_game("シューティングゲームを作って").html
    esc_script = _scene_re.search(r"<script>(.*?)</script>", esc_page, _scene_re.S)
    if esc_script is None:
        esc_gaps.append("no script on the page")
    else:
        try:
            esc_probe = _scene_sp.run(
                ["node", "-"],
                input=_shooter_scene_probe(esc_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if esc_probe.returncode != 0:
                raise ValueError(esc_probe.stderr.strip()[:60])
            flown = json.loads(esc_probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            flown = None
            esc_gaps.append(f"probe unavailable ({exc})")
        if flown is not None:
            spawns = flown.get("actSpawn") or []
            vy = flown.get("actVyAvg") or []
            if flown.get("state") != "play" or flown.get("t", 0) < 3400:
                # A dead pilot has not seen the final act, so the numbers
                # below would describe a fight nobody reached.
                esc_gaps.append(
                    f"the pilot did not reach the final act "
                    f"(state={flown.get('state')}, t={flown.get('t')})"
                )
            elif len(spawns) != 3 or min(spawns) < 1 or len(vy) != 3:
                esc_gaps.append(f"per-act spawn log incomplete: {spawns}")
            else:
                pace0 = 1200 / spawns[0]
                pace2 = (flown["t"] - 2400) / spawns[2]
                if vy[2] < vy[0] * 1.15:
                    esc_gaps.append(
                        f"the final act falls no faster ({vy[0]:.2f} -> {vy[2]:.2f})"
                    )
                if pace2 > pace0 * 0.85:
                    esc_gaps.append(
                        f"the final act spawns no denser ({pace0:.0f}f -> {pace2:.0f}f)"
                    )
    c.add(
        "creation_combat_escalation",
        "戦闘が幕ごとに強くなる型",
        0.0 if esc_gaps else 1.0,
        detail=(
            "; ".join(esc_gaps)
            if esc_gaps
            else "shooter を最終幕まで実際に操縦: 降下速度と出現密度が"
            "幕ごとに実測で上がる（最終幕が最速・最密）"
        ),
        kind=OUTCOME,
    )

    # --- the fall is seen, not teleported ------------------------------
    #
    # §1's technique list - sound, shake, hitstop, particles - was wired
    # long ago; the tween was wired nowhere. For a SameGame the collapse
    # IS the juice, and until C-1303 the board snapped in one frame. This
    # number pops one guaranteed-to-fall group on the running page and
    # watches the board: moving right after the pop, strictly less but
    # still moving mid-flight (an ease, not a delayed snap), at rest by
    # the end - and under reduced motion, never moving at all.
    from sidra_ai.creation.puzzle import probe_source as _puzzle_probe

    tween_gaps: list[str] = []
    tween_page = generate_game("パズルゲームを作って").html
    tween_script = _scene_re.search(r"<script>(.*?)</script>", tween_page, _scene_re.S)
    if tween_script is None:
        tween_gaps.append("no script on the page")
    else:
        for label, reduced in (("normal", False), ("reduced", True)):
            try:
                tween_probe = _scene_sp.run(
                    ["node", "-"],
                    input=_puzzle_probe(tween_script.group(1), reduced=reduced),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if tween_probe.returncode != 0:
                    raise ValueError(tween_probe.stderr.strip()[:60])
                seen = json.loads(tween_probe.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                tween_gaps.append(f"{label}: probe unavailable ({exc})")
                continue
            if not seen.get("hadTarget") or seen.get("scoreAfter", 0) <= seen.get(
                "scoreBefore", 0
            ):
                tween_gaps.append(f"{label}: the measured pop did not happen")
                continue
            if reduced:
                if seen["movingAtPop"] != 0 or seen["movingMid"] != 0:
                    tween_gaps.append(
                        f"reduced motion still animates ({seen['movingAtPop']}px)"
                    )
            else:
                if seen["movingAtPop"] <= 0:
                    tween_gaps.append("the board teleports: no offset at the pop")
                elif not (0 < seen["movingMid"] < seen["movingAtPop"]):
                    tween_gaps.append(
                        f"not an ease: {seen['movingAtPop']}px -> "
                        f"{seen['movingMid']}px mid-flight"
                    )
                elif seen["movingSettled"] != 0:
                    tween_gaps.append(
                        f"never comes to rest ({seen['movingSettled']}px left)"
                    )
    c.add(
        "creation_puzzle_tween",
        "盤面の落下が見える型",
        0.0 if tween_gaps else 1.0,
        detail=(
            "; ".join(tween_gaps)
            if tween_gaps
            else "puzzle で 1 手を実際に消して計測: 直後は動き、途中は減衰し、"
            "静止する。reduced-motion では最初から動かない"
        ),
        kind=OUTCOME,
    )

    # --- the other half of 効果音と音楽 --------------------------------
    #
    # §1 names sound AND music; C-1017 shipped the sound and nothing
    # shipped the music. §10's three facts make a safe, self-contained
    # loop possible (two-clock scheduling, four repeated bars, a
    # pentatonic walk that cannot land on a wrong note). Counted only if
    # every template carries the preamble, and judged by watching a page
    # play: quiet before the first input, reserving notes after it, dead
    # the moment M mutes, and the same request humming the same tune.
    from sidra_ai.creation.music import probe_source as _music_probe

    music_gaps: list[str] = []
    unwired = [
        key
        for key in sorted(_TOUCH_TEMPLATES)
        if "musicTick" not in generate_game("ゲームを作って", template=key).html
    ]
    if unwired:
        music_gaps.append(f"no music on: {', '.join(unwired)}")
    music_page = generate_game("パズルゲームを作って").html
    music_script = _scene_re.search(r"<script>(.*?)</script>", music_page, _scene_re.S)
    if music_script is None:
        music_gaps.append("no script on the page")
    else:
        heard = []
        for _ in range(2):
            try:
                music_run = _scene_sp.run(
                    ["node", "-"],
                    input=_music_probe(music_script.group(1)),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if music_run.returncode != 0:
                    raise ValueError(music_run.stderr.strip()[:60])
                heard.append(json.loads(music_run.stdout.strip().splitlines()[-1]))
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                music_gaps.append(f"probe unavailable ({exc})")
                break
        if len(heard) == 2:
            seen, again = heard
            if seen["beforeOn"] or seen["beforeN"] != 0:
                music_gaps.append("hums before the first input")
            if seen["playingN"] <= 0:
                music_gaps.append("armed and still silent")
            if seen["afterN"] != seen["atMuteN"]:
                music_gaps.append(
                    f"M does not stop it ({seen['atMuteN']} -> {seen['afterN']})"
                )
            if seen["mel"] != again["mel"] or seen["bass"] != again["bass"]:
                music_gaps.append("the same request is not the same tune")
    c.add(
        "creation_game_music",
        "BGM が流れるゲームの型",
        0.0 if music_gaps else float(len(_TOUCH_TEMPLATES)),
        detail=(
            "; ".join(music_gaps)
            if music_gaps
            else "全型にシード由来のペンタトニック 4 小節ループ。実走行で"
            "「入力前は無音・入力後に予約・M で停止・同依頼同曲」を確認"
        ),
        kind=OUTCOME,
    )

    # --- the song knows the fight --------------------------------------
    #
    # §6 定量: combat cuts run at half the length of talk (2.1s vs 4.4s),
    # so combat keeps time twice as fast. The sky (C-1301) and the gain
    # (C-1034) already know the climax; C-1312 teaches the music: the same
    # four bars reserve about twice the notes over the same frames while
    # combat is on, and M still silences everything. Read off the same
    # driven run as the music number above.
    density_gaps: list[str] = []
    if music_gaps:
        density_gaps.append("the music itself is not passing")
    elif len(heard) == 2:
        seen = heard[0]
        calm_n, fight_n = seen.get("calmN", 0), seen.get("fightN", 0)
        if calm_n <= 0:
            density_gaps.append("no calm baseline to compare against")
        elif fight_n < calm_n * 1.6:
            density_gaps.append(
                f"combat does not quicken the pulse ({calm_n} -> {fight_n})"
            )
        elif fight_n > calm_n * 2.6:
            density_gaps.append(
                f"combat floods rather than doubles ({calm_n} -> {fight_n})"
            )
        if seen.get("afterN") != seen.get("atMuteN"):
            density_gaps.append("M no longer silences the fight's music")
    c.add(
        "creation_music_combat_density",
        "音楽が戦闘で倍速になる",
        0.0 if density_gaps else 1.0,
        detail=(
            "; ".join(density_gaps)
            if density_gaps
            else "同一走行で計測: 同じ 300 フレームの予約数が combat 中は"
            "約 2 倍（§6 定量の 2.1s/4.4s）。M ミュートは戦闘中も勝つ"
        ),
        kind=OUTCOME,
    )

    # --- the fifth §4 basic: controls can be re-assigned ---------------
    #
    # Contrast, shape-not-colour, touch targets and the flash budget all
    # landed; "allow control re-assignment" had not, anywhere. Judged by
    # driving the page: a key with no assignment does nothing, the same
    # key moves the game once assigned to a control it reads, the
    # canonical key survives, and the assignment lands in this-device
    # storage. Counted per template only when the preamble is on all of
    # them and the driven page obeys.
    from sidra_ai.creation.remap import probe_source as _remap_probe

    remap_gaps: list[str] = []
    remap_unwired = [
        key
        for key in sorted(_TOUCH_TEMPLATES)
        if "remapSet" not in generate_game("ゲームを作って", template=key).html
    ]
    if remap_unwired:
        remap_gaps.append(f"no remap on: {', '.join(remap_unwired)}")
    remap_page = generate_game("パズルゲームを作って").html
    remap_script = _scene_re.search(r"<script>(.*?)</script>", remap_page, _scene_re.S)
    if remap_script is None:
        remap_gaps.append("no script on the page")
    else:
        try:
            remap_run = _scene_sp.run(
                ["node", "-"],
                input=_remap_probe(remap_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if remap_run.returncode != 0:
                raise ValueError(remap_run.stderr.strip()[:60])
            held = json.loads(remap_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            held = None
            remap_gaps.append(f"probe unavailable ({exc})")
        if held is not None:
            if held["afterRaw"] != held["start"]:
                remap_gaps.append("an unassigned key already steers the game")
            if not held["accepted"] or held["refused"]:
                remap_gaps.append("the assignment API accepts the wrong things")
            if held["afterMapped"] != held["afterRaw"] + 1:
                remap_gaps.append("the assigned key does not steer the game")
            if held["afterCanon"] != held["afterMapped"] + 1:
                remap_gaps.append("the canonical key stopped working")
            if not held["stored"]:
                remap_gaps.append("the assignment is not kept on this device")
    c.add(
        "creation_key_remap",
        "キーを割り当て直せる型",
        0.0 if remap_gaps else float(len(_TOUCH_TEMPLATES)),
        detail=(
            "; ".join(remap_gaps)
            if remap_gaps
            else "全型で操作の再割り当て（§4）。実走行で「未設定キーは無反応・"
            "割り当てたキーで実際に動く・元のキーも生きる・この端末にのみ保存」"
            "を確認"
        ),
        kind=OUTCOME,
    )

    # --- the boss behind the boss key ----------------------------------
    #
    # §3's modern-Zelda floor is rooms -> boss key -> boss; the adventure's
    # climax was a keyhole. Judged by fighting the guardian on the running
    # page (C-1306): the chest refuses the key while it stands, two blows
    # a frame apart count as one, phase 2 measurably re-accelerates (§6
    # 観察 3), both beats of its grammar (wind-up, charge) actually occur,
    # and the win only follows the fall.
    from sidra_ai.creation.adventure import guard_probe as _guard_probe

    boss_gaps: list[str] = []
    boss_page = generate_game("迷宮を冒険するゲームを作って").html
    boss_script = _scene_re.search(r"<script>(.*?)</script>", boss_page, _scene_re.S)
    if boss_script is None:
        boss_gaps.append("no script on the page")
    else:
        try:
            boss_run = _scene_sp.run(
                ["node", "-"],
                input=_guard_probe(boss_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if boss_run.returncode != 0:
                raise ValueError(boss_run.stderr.strip()[:60])
            fought = json.loads(boss_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            fought = None
            boss_gaps.append(f"probe unavailable ({exc})")
        if fought is not None:
            if not fought["firstAlive"] or fought["firstHp"] < 4:
                boss_gaps.append("no guardian standing in the altar")
            if fought["lockedState"] != "play":
                boss_gaps.append("the key opens the chest over the guardian's head")
            if fought["hpA"] != fought["hpB"] or fought["hpA"] != fought["firstHp"] - 1:
                boss_gaps.append("mashing lands more than one blow")
            if not fought["sawWind"] or not fought["sawCharge"]:
                boss_gaps.append("the grammar is missing a beat (wind-up or charge)")
            if not fought["p2"]:
                boss_gaps.append("no second phase was ever reached")
            elif not (
                fought["p2"]["speed"] > fought["p1"]["speed"]
                and fought["p2"]["wind"] < fought["p1"]["wind"]
            ):
                boss_gaps.append("phase 2 does not re-accelerate")
            if fought["fallenAlive"] or fought["finalState"] != "win":
                boss_gaps.append("the fall does not open the chest")
    c.add(
        "creation_adventure_boss",
        "祭壇に番人がいる",
        0.0 if boss_gaps else 1.0,
        detail=(
            "; ".join(boss_gaps)
            if boss_gaps
            else "実際に戦って計測: 番人存命中は鍵でも開かず、連打は 1 発、"
            "予兆→突進の文法があり、hp 半分で実測の歩幅と予兆が変わり、"
            "撃破後にだけ勝てる"
        ),
        kind=OUTCOME,
    )

    # --- the explosion is not a buzzer ---------------------------------
    #
    # §2's sfxr palette is more than three oscillator shapes: the
    # explosion/hit family is white noise through a falling low-pass, and
    # until C-1308 every impact in every game was a tone. Read off the
    # driven page's own AudioContext: the hurt effect must build a noise
    # source and a low-pass filter, the melodic gem must still be an
    # oscillator, and the loudness contract (combat step, mute) must be
    # exactly what it was.
    from sidra_ai.creation.audio import PROBE as _sfx_probe

    texture_gaps: list[str] = []
    texture_page = generate_game("シューティングゲームを作って").html
    texture_script = _scene_re.search(
        r"<script>(.*?)</script>", texture_page, _scene_re.S
    )
    if texture_script is None:
        texture_gaps.append("no script on the page")
    else:
        try:
            texture_run = _scene_sp.run(
                ["node", "-"],
                input=_sfx_probe.replace("SCRIPT_PLACEHOLDER", texture_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if texture_run.returncode != 0:
                raise ValueError(texture_run.stderr.strip()[:60])
            timbre = json.loads(texture_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            timbre = None
            texture_gaps.append(f"probe unavailable ({exc})")
        if timbre is not None:
            hurt = timbre.get("hurtNodes") or []
            gem = timbre.get("gemNodes") or []
            if "noise->lowpass" not in hurt or "lowpass->out" not in hurt:
                texture_gaps.append(f"the hit is not noise through a low-pass ({hurt})")
            if "oscillator" in hurt or "noise->direct" in hurt:
                texture_gaps.append(f"the hit's wiring is wrong ({hurt})")
            if gem != ["oscillator"]:
                texture_gaps.append(f"the melodic family changed texture ({gem})")
            if timbre.get("mutedPlayed") != 0 or not timbre.get("loud"):
                texture_gaps.append("the loudness contract moved")
    c.add(
        "creation_sfx_texture",
        "打撃がノイズで鳴る",
        0.0 if texture_gaps else 1.0,
        detail=(
            "; ".join(texture_gaps)
            if texture_gaps
            else "実走行の AudioContext で確認: hurt/lose は白色雑音＋下降"
            "ローパス（§2 の explosion 系）、旋律系は従来の oscillator、"
            "戦闘音圧段とミュートは不変"
        ),
        kind=OUTCOME,
    )

    # --- the telegraph tells you where, not only when ------------------
    #
    # The duel's own rule is "dodge by reading the aura" (C-1022), but the
    # lane used to be re-rolled onto the player at the trigger - a coin
    # flip no human reaction answers. Judged by playing one aimed volley
    # each way (C-1309): the shot goes down the locked lane at least 15
    # frames after the lock, leaving that lane in the window is a dodge,
    # staying in it is a hit.
    from sidra_ai.creation.duel import aim_probe as _duel_aim_probe

    aim_gaps: list[str] = []
    aim_page = generate_game("対戦ゲームを作って").html
    aim_script = _scene_re.search(r"<script>(.*?)</script>", aim_page, _scene_re.S)
    if aim_script is None:
        aim_gaps.append("no script on the page")
    else:
        try:
            aim_run = _scene_sp.run(
                ["node", "-"],
                input=_duel_aim_probe(aim_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if aim_run.returncode != 0:
                raise ValueError(aim_run.stderr.strip()[:60])
            volleys = json.loads(aim_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            volleys = None
            aim_gaps.append(f"probe unavailable ({exc})")
        if volleys is not None:
            dodged, stayed = volleys.get("dodged"), volleys.get("stayed")
            if not dodged or not stayed:
                aim_gaps.append("the opponent never locked an aim")
            else:
                for label, v in (("dodged", dodged), ("stayed", stayed)):
                    if v["beamLane"] != v["aimed"]:
                        aim_gaps.append(f"{label}: the shot left the locked lane")
                    if v["lockToFire"] < 15:
                        aim_gaps.append(
                            f"{label}: only {v['lockToFire']} frames to react"
                        )
                if dodged and dodged["hpAfter"] != dodged["hpBefore"]:
                    aim_gaps.append("leaving the locked lane still hits")
                if stayed and stayed["hpAfter"] != stayed["hpBefore"] - 1:
                    aim_gaps.append("staying in the locked lane does not hit")
    c.add(
        "creation_duel_fair_telegraph",
        "予兆が場所も教える",
        0.0 if aim_gaps else 1.0,
        detail=(
            "; ".join(aim_gaps)
            if aim_gaps
            else "実際に 1 発ずつ受けて計測: 照準はロックしたレーンに固定、"
            "ロック→発射は 15 フレーム以上、避ければ外れ、残れば当たる"
        ),
        kind=OUTCOME,
    )

    # --- the other half of the coyote window ---------------------------
    #
    # §12: a jump pressed and held a few frames before landing fires on
    # the exact landing frame instead of being dropped (Celeste's jump
    # buffering; ~4 frames is the trade's number). Judged by playing it
    # (C-1310): the held press is airborne when it lands in the buffer,
    # the jump fires within a handful of frames of touching down, a press
    # released before landing is discarded, and a press in open air still
    # never jumps on the spot.
    from sidra_ai.creation.platformer import buffer_probe as _plat_buffer_probe

    jb_gaps: list[str] = []
    jb_page = generate_game("プラットフォーマーを作って").html
    jb_script = _scene_re.search(r"<script>(.*?)</script>", jb_page, _scene_re.S)
    if jb_script is None:
        jb_gaps.append("no script on the page")
    else:
        try:
            jb_run = _scene_sp.run(
                ["node", "-"],
                input=_plat_buffer_probe(jb_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if jb_run.returncode != 0:
                raise ValueError(jb_run.stderr.strip()[:60])
            played = json.loads(jb_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            played = None
            jb_gaps.append(f"probe unavailable ({exc})")
        if played is not None:
            held, rel = played.get("held") or {}, played.get("released") or {}
            if not held.get("airborneAtPress") or held.get("bufferAtPress", 0) <= 0:
                jb_gaps.append("the early press is not kept")
            if not held.get("jumped") or held.get("frames", 99) > 6:
                jb_gaps.append("the kept press does not fire on landing")
            if rel.get("jumped"):
                jb_gaps.append("a released press still jumps")
            if not played.get("openAirNoJump"):
                jb_gaps.append("open air grew a jump")
    c.add(
        "creation_jump_buffer",
        "着地直前のジャンプが拾われる",
        0.0 if jb_gaps else 1.0,
        detail=(
            "; ".join(jb_gaps)
            if jb_gaps
            else "実際に跳んで計測: 着地数フレーム前の押しっぱなしは着地"
            "フレームで跳び、離せば破棄、空中の即ジャンプは従来どおり無い"
        ),
        kind=OUTCOME,
    )

    # --- the second blow is kept, not dropped --------------------------
    #
    # §12's attack side (C-1311): a press during the sword's swing or the
    # cannon's cooldown queues exactly one follow-up that fires the frame
    # the weapon is free. Judged by playing both fighters: the mid-swing
    # press restarts the swing at its end, the mid-cool press re-arms the
    # cooldown eleven frames later, and a single press acts exactly once.
    from sidra_ai.creation.adventure import combo_probe as _adv_combo_probe
    from sidra_ai.creation.kaiju import queue_probe as _kaiju_queue_probe

    ab_gaps: list[str] = []

    def _drive(request: str, builder) -> dict | None:
        page_ = generate_game(request).html
        script_ = _scene_re.search(r"<script>(.*?)</script>", page_, _scene_re.S)
        if script_ is None:
            ab_gaps.append(f"{request}: no script")
            return None
        try:
            run_ = _scene_sp.run(
                ["node", "-"],
                input=builder(script_.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if run_.returncode != 0:
                raise ValueError(run_.stderr.strip()[:60])
            return json.loads(run_.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            ab_gaps.append(f"{request}: probe unavailable ({exc})")
            return None

    sworded = _drive("迷宮を冒険するゲームを作って", _adv_combo_probe)
    if sworded is not None:
        if not sworded["keptQueue"]:
            ab_gaps.append("adventure: the mid-swing press is dropped")
        if sworded["secondSwing"] < 8:
            ab_gaps.append("adventure: the queued blow never fires")
        if sworded["afterSingle"] != 0 or sworded["ghostQueue"]:
            ab_gaps.append("adventure: a single press does not act exactly once")
    gunned = _drive("巨大怪獣と戦うゲームを作って", _kaiju_queue_probe)
    if gunned is not None:
        if not gunned["keptQueue"]:
            ab_gaps.append("kaiju: the mid-cool press is dropped")
        if gunned["coolAfterQueue"] <= 0:
            ab_gaps.append("kaiju: the queued shot never fires")
        if gunned["coolAfterSingle"] != 0 or gunned["ghostQueue"]:
            ab_gaps.append("kaiju: a single press does not act exactly once")
    c.add(
        "creation_attack_buffer",
        "連撃の 2 発目が拾われる",
        0.0 if ab_gaps else 1.0,
        detail=(
            "; ".join(ab_gaps)
            if ab_gaps
            else "剣と砲を実際に連打して計測: cooldown 中の押しは 1 発だけ"
            "キューされ、明けたフレームで発火。1 押しは 1 回だけ"
        ),
        kind=OUTCOME,
    )

    # --- the page carries its own form ---------------------------------
    #
    # §9 学び (4): every generator on the market loses the person at the
    # same moment - the result is nearly right and there is no way to
    # finish it by hand. C-1112 answered half of that by making a request
    # edit the parameters. This is the half that needs nobody: the
    # artifact ships a panel.
    #
    # Judged by driving the panel the page actually built, in node, for
    # every template. Grepping for "<input" would say nothing about
    # whether moving the slider changes the game - so the probe reads back
    # the template's own binding for SPEED_TOKEN, and the number has to be
    # the one storage held.
    from sidra_ai.creation.games import (
        TEMPLATES as _tune_templates,
        _DIFFICULTY as _tune_ladder,
        generate_game as _tune_generate,
        validate_game_html as _tune_validate,
    )
    from sidra_ai.creation.tuning import (
        SPEED_BINDING as _tune_binding,
        TUNE_PREAMBLE as _tune_preamble,
        panel_schema as _tune_schema,
        probe_source as _tune_probe,
    )

    tune_gaps: list[str] = []
    tune_ok: list[str] = []
    # Checked once, not per template: a panel that phoned home would be a
    # different product, and the artifact's whole claim is that it is one
    # local file. The reload is the only thing it is allowed to trigger.
    for banned in ("fetch(", "XMLHttpRequest", "://", "navigator.sendBeacon"):
        if banned in _tune_preamble:
            tune_gaps.append(f"the panel contains {banned!r}")
    for key in sorted(_tune_templates):
        if key not in _tune_binding:
            tune_gaps.append(f"{key}: no SPEED binding recorded for the judge")
            continue
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            tune_gaps.append(f"{key}: no script")
            continue
        speeds = [pair[0] for pair in _tune_ladder[key].values()]
        stored, target = max(speeds), min(speeds)
        want = [f["key"] for f in _tune_schema(
            key, _tune_ladder[key], difficulty="normal", accent="#000000"
        )["fields"]]
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_tune_probe(
                    script.group(1),
                    stored={f"sidra.tune.{key}": {"speed": stored}},
                    target=target,
                    speed_expr=_tune_binding[key],
                ),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if probe.returncode != 0:
                tune_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            tune_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
            continue
        if not seen.get("panel"):
            tune_gaps.append(f"{key}: no panel in the page")
            continue
        if seen.get("controls") != want:
            tune_gaps.append(f"{key}: controls {seen.get('controls')} != {want}")
            continue
        if not seen.get("buttons"):
            tune_gaps.append(f"{key}: no way back to the defaults")
            continue
        # The direction that matters: a value the browser remembered has to
        # reach the game body, not just the panel's own readout.
        if seen.get("speedSeen") != stored:
            tune_gaps.append(
                f"{key}: stored {stored} but the game runs on {seen.get('speedSeen')}"
            )
            continue
        if seen.get("moved") != target:
            tune_gaps.append(f"{key}: moving the slider stored {seen.get('moved')!r}")
            continue
        if not seen.get("cleared"):
            tune_gaps.append(f"{key}: 既定に戻す left the override in place")
            continue
        if not seen.get("reloads"):
            tune_gaps.append(f"{key}: a change never asked the page to re-run")
            continue
        verdict = _tune_validate(page)
        if not verdict["playable"]:
            tune_gaps.append(f"{key} stopped being playable: {verdict['failures']}")
            continue
        tune_ok.append(key)
    c.add(
        "creation_param_panel",
        "生成ページ内で自分で直せる型",
        float(len(tune_ok)) if not tune_gaps else 0.0,
        detail=(
            "難度・2 軸のスライダー・差し色を artifact 内のフォームで変更でき、"
            "保存値がゲーム本体に届き、既定に戻せる。"
            "作者の easy..hard の範囲に丸められ、通信は無し"
            if not tune_gaps
            else "; ".join(tune_gaps)
        ),
        kind=OUTCOME,
    )

    # --- a picture can be swapped for a better one ---------------------
    #
    # C-1116. §9 学び (2): the generators people rate highest are the ones
    # whose art can be replaced. Installing a local image model is the
    # owner's own machine and their own decision (recorded in E); what a
    # loop can build is the receptacle, so that the day a model exists the
    # art is a file drop rather than a rewrite.
    #
    # Counted: templates with at least one *working* replaceable slot -
    # declared with a role, filled by the procedural generator today,
    # resolved from the directory, beaten by a file an operator drops in,
    # and harmless when the file is gone. Templates that deliberately draw
    # everything as paths are not counted: three of them have written
    # reasons (the kaiju silhouette, the race's per-lap relight, the
    # platform lip), and inflating this number by overriding them would be
    # trading a design decision for a number.
    import tempfile as _slot_tmp
    from pathlib import Path as _SlotPath

    from sidra_ai.creation.sprites import (
        LOADER_PROBE as _slot_loader_probe_src,
        contract_gaps as _slot_gaps,
        generate_sprites as _slot_generate,
        loader_probe as _slot_probe,
        resolve_slots as _slot_resolve,
        save_sprites as _slot_save,
        seed_for as _slot_seed,
        slots_for as _slot_slots,
    )

    slot_gaps: list[str] = []
    slot_ok: list[str] = []
    # The declaration and the page have to agree for *every* template,
    # including the ones with no slots at all: a call nobody declared is a
    # picture nobody can replace, which is the failure this whole item is
    # about, and it is invisible in a screenshot.
    for key in sorted(_tune_templates):
        slot_gaps += [f"{key}: {gap}" for gap in _slot_gaps(key, _tune_templates[key].script)]
    # The fallback claim, run in node in both directions.
    for decoded in (False, True):
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_slot_probe(decoded=decoded),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if probe.returncode != 0:
                slot_gaps.append(f"loader probe did not run: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            slot_gaps.append(f"loader probe unavailable ({type(exc).__name__})")
            continue
        if decoded and (seen["drawn"] != 1 or seen["painted"]):
            slot_gaps.append("a decoded picture did not replace the flat shape")
        if not decoded and seen["painted"] != ["#abcdef"]:
            slot_gaps.append("a picture that never decoded lost the flat shape")

    with _slot_tmp.TemporaryDirectory() as _slot_dir:
        for key in sorted(_tune_templates):
            filled = [slot for slot in _slot_slots(key) if slot.generated]
            if not filled:
                continue
            root = _SlotPath(_slot_dir) / key
            assets = root / "assets"
            _slot_save(_slot_generate(key, seed=_slot_seed(key)), assets)
            resolved = _slot_resolve(key, assets)
            missing = [slot.name for slot in filled if slot.name not in resolved]
            if missing:
                slot_gaps.append(f"{key}: generated but unresolvable: {missing}")
                continue
            if any(not slot.role for slot in _slot_slots(key)):
                slot_gaps.append(f"{key}: a slot with no role written down")
                continue
            # The receptacle itself: a file an operator drops in has to win
            # over the procedural SVG without anything being regenerated.
            first = filled[0].name
            (assets / f"{first}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            again = _slot_resolve(key, assets)
            if not again.get(first, "").endswith(f"{first}.png"):
                slot_gaps.append(f"{key}: a dropped-in picture lost to the generated one")
                continue
            page = _tune_generate("ゲームを作って", template=key, sprites=again).html
            if again[first] not in page:
                slot_gaps.append(f"{key}: the page does not load {again[first]}")
                continue
            if "http://" in page or "https://" in page:
                slot_gaps.append(f"{key}: the page reaches outside the machine")
                continue
            # And with the directory emptied, the game is still a game.
            bare = _tune_validate(_tune_generate("ゲームを作って", template=key).html)
            if not bare["playable"]:
                slot_gaps.append(f"{key}: unplayable without its pictures: {bare['failures']}")
                continue
            slot_ok.append(key)
    c.add(
        "creation_sprite_slots",
        "絵を差し替えられる型",
        float(len(slot_ok)) if not slot_gaps else 0.0,
        detail=(
            "assets/<slot>.png を置くだけで手続き生成 SVG を上書きでき、"
            "ファイルが無くても遊べる。9 型すべてで sprite() 呼び出しと"
            "スロット宣言が一致（duel の fighter は未充填として理由つきで宣言）。"
            "数えないのは 5 型: kaiju / racing / platformer / puzzle は"
            "絵を持たない理由が書かれており、duel は宣言だけで未充填"
            if not slot_gaps
            else "; ".join(slot_gaps)
        ),
        kind=OUTCOME,
    )

    # --- every go reaches a break ---------------------------------------
    #
    # C-1104, §8 事実 1. A page that runs forever is not endless content;
    # it is a page with no moment to stop at, and "how long is a go?" had
    # no answer at all for two of the nine templates.
    #
    # Judged by leaving the real page alone in node: press start once - the
    # gate exists to be pressed - and then touch nothing for longer than
    # the bound. A break is either the template's own end screen or the
    # shared clock; both count, and which one it was is reported, because a
    # clock that fired over a template that had already finished would be a
    # bound nobody needed.
    from sidra_ai.creation.round import (
        ROUND_SECONDS as _round_seconds,
        live_gaps as _round_live_gaps,
        probe_source as _round_probe,
    )

    round_gaps: list[str] = []
    round_ok: list[str] = []
    round_by: dict[str, float] = {}
    for key in sorted(_tune_templates):
        round_gaps += [f"{key}: {gap}" for gap in _round_live_gaps(key, _tune_templates[key].script)]
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            round_gaps.append(f"{key}: no script")
            continue
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_round_probe(script.group(1), warmup=600),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if probe.returncode != 0:
                round_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            round_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
            continue
        at = seen.get("breakAt")
        if at is None:
            round_gaps.append(f"{key}: no break in {_round_seconds}s of play")
            continue
        if at > seen["limit"] + 100:
            round_gaps.append(f"{key}: the break came at {at / 1000:.1f}s")
            continue
        # Held, not stopped. A loop that was dropped could not be handed
        # back, and the page would be a still image with a banner on it.
        if not seen.get("running"):
            round_gaps.append(f"{key}: the loop stopped rather than held")
            continue
        if seen.get("gatedMs"):
            round_gaps.append(f"{key}: the title screen burned {seen['gatedMs']:.0f}ms of the round")
            continue
        # Coming back has to exist, and has to belong to whoever ended the
        # round: the clock re-runs the page, a template's own end screen
        # keeps its own restart and must not be reloaded over. Counted as
        # "any" rather than "exactly one" since C-1106, because the probe
        # now offers a tap before the key and a clock break answers both.
        reloaded = seen.get("reloads") or 0
        if (reloaded < 1) if seen["reason"] == "time" else (reloaded != 0):
            round_gaps.append(
                f"{key}: coming back after a {seen['reason']} break reloaded "
                f"{reloaded} time(s)"
            )
            continue
        round_ok.append(key)
        round_by[key] = at / 1000
    by_clock = sorted(k for k in round_ok if round_by[k] >= _round_seconds - 1)
    c.add(
        "creation_round_within_60s",
        "60 秒以内に区切りが来る型",
        float(len(round_ok)) if not round_gaps else 0.0,
        detail=(
            f"起動して 1 入力だけ与え、あとは無操作で {_round_seconds}s 以上回した"
            f"実測。{len(round_ok) - len(by_clock)} 型はテンプレ自身の終了画面で、"
            f"{len(by_clock)} 型は共有クロックで区切られる（{', '.join(by_clock)}）。"
            "区切ってもループは止めずに保持しているので再開できる"
            if not round_gaps
            else "; ".join(round_gaps)
        ),
        kind=OUTCOME,
    )

    # --- losing a round has a shape ------------------------------------
    #
    # C-1105, §8 事実 2. Being hit had juice from C-1017; losing the *go*
    # felt the same as being hit, so the one moment the player is asked to
    # decide whether to try again had no punctuation. One shared beat -
    # heavier shake, a longer hold, a burst, the losing sound - called from
    # each template's own losing path and from the clock's timeout, which
    # is the only failure the templates with no losing state have.
    #
    # Driven to a real failure rather than grepped, three ways at once:
    # the beat has to fire on a loss, it has to stay silent on a win, and
    # under prefers-reduced-motion it has to keep firing with the shake at
    # exactly zero - the hitstop is what carries it for someone who asked
    # for less movement.
    from sidra_ai.creation.daily import DAILY_PREAMBLE as _daily_preamble
    from sidra_ai.creation.juice import FAIL_SHAKE as _fail_shake
    from sidra_ai.creation.round import probe_source as _fail_probe

    # The beat has to be heavier than any *hit*, or it is not a beat, it is
    # another hit - which is exactly the state §8 事実 2 recorded. Measured
    # against the templates' own literal weights rather than against
    # FAIL_SHAKE, because a threshold derived from the number it is
    # checking moves whenever that number does.
    _hit_weights = [
        float(weight)
        for spec in _tune_templates.values()
        for weight in _scene_re.findall(r"\bshake\(\s*([0-9.]+)\s*\)", spec.script)
    ]
    _heaviest_hit = max(_hit_weights) if _hit_weights else 0.0

    def _fail_run(key, *, reduced=False, slow=True):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, f"{key}: no script"
        # The slowest pace the author shipped, through the panel: it makes
        # every template's round outlast the clock, so a *failure* is what
        # is being watched rather than whichever ending came first.
        gentle = min(pair[0] for pair in _tune_ladder[key].values())
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_fail_probe(
                    script.group(1),
                    reduced=reduced,
                    stored={f"sidra.tune.{key}": {"speed": gentle}} if slow else None,
                ),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if probe.returncode != 0:
                return None, f"{key}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    fail_gaps: list[str] = []
    fail_ok: list[str] = []
    for key in sorted(_tune_templates):
        lost, problem = _fail_run(key)
        if problem:
            fail_gaps.append(problem)
            continue
        if lost["breakAt"] is None:
            fail_gaps.append(f"{key}: never reached a break")
            continue
        if not lost["beatsAtBreak"]:
            fail_gaps.append(f"{key}: a lost round produced no beat")
            continue
        if not lost["shakeAtBreak"]:
            fail_gaps.append(f"{key}: the beat did not move the screen at all")
            continue
        said = [line for line in lost["saidAfter"] if "もう一度" in line or "やり直" in line]
        if not said:
            fail_gaps.append(f"{key}: nothing offered a retry after the failure")
            continue
        quiet, problem = _fail_run(key, reduced=True)
        if problem:
            fail_gaps.append(problem)
            continue
        if not quiet["beatsAtBreak"]:
            fail_gaps.append(f"{key}: reduced motion silenced the beat entirely")
            continue
        if quiet["shakeAtBreak"] != 0:
            fail_gaps.append(f"{key}: shake {quiet['shakeAtBreak']} survived reduced motion")
            continue
        fail_ok.append(key)
    # The other direction, once: a template that reaches its goal must not
    # get a failure beat. Racing is the one that finishes on its own with
    # no input, which is what makes it the case that can prove it.
    if _fail_shake <= _heaviest_hit:
        fail_gaps.append(
            f"the beat shakes {_fail_shake}, no more than the heaviest hit ({_heaviest_hit:g})"
        )
    won, problem = _fail_run("racing", slow=False)
    if problem:
        fail_gaps.append(problem)
    elif won["reason"] != "template" or won["endState"] != "goal":
        fail_gaps.append("racing no longer reaches its goal, so a win cannot be checked")
    # Counted over the whole run, not at the break: the beat would fire on
    # the tick *after* the one where the ending first shows, so reading it
    # at the break alone would miss a beat that went off on a win.
    elif won["beatsTotal"]:
        fail_gaps.append(f"a won round fired the failure beat {won['beatsTotal']} time(s)")
    c.add(
        "creation_fail_beat",
        "負けの瞬間に形がある型",
        float(len(fail_ok)) if not fail_gaps else 0.0,
        detail=(
            f"実際に負けるまで動かして確認。揺れ {_fail_shake}・ヒットストップ・"
            "粒子・音が 1 回だけ鳴り、直後にリトライ表示が出る。"
            "reduced-motion では揺れ 0 のままビートは残る（止めるのではなく"
            "動きを差し引く hitstop が担う）。ゴールに着いた回では鳴らない"
            if not fail_gaps
            else "; ".join(fail_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the result leads back in ---------------------------------------
    #
    # C-1106, §8 事実 3. A result screen that only says what happened is a
    # place to stop; what turns one go into the next is knowing how far off
    # you were and being one tap from trying again. Both halves are local:
    # the best is this device's own localStorage, and there is no URL and
    # nothing sent anywhere.
    #
    # Driven, not grepped, and the "あと n" branch is driven twice: once
    # against an empty store (a first go is always a record) and once
    # against a best nobody beat, because a strip that only ever printed
    # 自己ベスト更新 would pass the first run alone.
    fresh_gaps: list[str] = []
    fresh_ok: list[str] = []
    for key in sorted(_tune_templates):
        runs = {}
        for label, best in (("first", None), ("chased", 10**6)):
            page = _tune_generate("ゲームを作って", template=key).html
            script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
            if script is None:
                fresh_gaps.append(f"{key}: no script")
                break
            gentle = min(pair[0] for pair in _tune_ladder[key].values())
            source = _fail_probe(
                script.group(1), stored={f"sidra.tune.{key}": {"speed": gentle}}
            )
            if best is not None:
                source = source.replace(
                    "const roundStore = {",
                    'const roundStore = {"sidra.best.%s": "%d",' % (key, best),
                    1,
                )
            try:
                probe = _scene_sp.run(
                    ["node", "-"], input=source, capture_output=True, text=True, timeout=180
                )
                if probe.returncode != 0:
                    fresh_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                    break
                runs[label] = json.loads(probe.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                fresh_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
                break
        if len(runs) != 2:
            continue
        first, chased = runs["first"], runs["chased"]
        if first["score"] is None:
            fresh_gaps.append(f"{key}: the round ended with no score to show")
            continue
        if not first["record"]:
            fresh_gaps.append(f"{key}: a first go was not a personal best")
            continue
        strip = [line for line in chased["strip"] if "自己ベスト" in line and "あと" in line]
        if not strip:
            fresh_gaps.append(f"{key}: no 「あと n」 on the result: {chased['strip'][:3]}")
            continue
        if chased["record"]:
            fresh_gaps.append(f"{key}: a beaten score still claimed a record")
            continue
        if not [line for line in chased["strip"] if "もう一度" in line]:
            fresh_gaps.append(f"{key}: the result offers no way back in")
            continue
        # One tap, from the result, back into play - the thing §8 asks for
        # and the thing a phone has. Reloading the page counts: the round
        # after it is a round.
        tap = chased["afterTap"]
        if not (tap["live"] and not tap["ended"]) and not tap["reloads"]:
            fresh_gaps.append(f"{key}: one tap on the result did not start another go")
            continue
        for line in chased["strip"]:
            if "http" in line or "://" in line:
                fresh_gaps.append(f"{key}: the result points somewhere outside")
                break
        else:
            fresh_ok.append(key)
    c.add(
        "creation_result_rechallenge",
        "結果から次の 1 回へ戻れる型",
        float(len(fresh_ok)) if not fresh_gaps else 0.0,
        detail=(
            "終了画面に「<数え方> N / 自己ベスト M（あと k）」と"
            "「R / タップでもう一度」が出る。自己ベストは端末内 localStorage のみで、"
            "URL も外部遷移も無い。1 タップで実際に次の回が始まることまで実測"
            if not fresh_gaps
            else "; ".join(fresh_gaps)
        ),
        kind=OUTCOME,
    )

    # --- everyone gets the same board today -----------------------------
    #
    # C-1107, §8 事実 4・7. What brings people back is a shared attempt,
    # and the obvious way to build one - a server handing out a puzzle - is
    # not available to a page that talks to nothing. A date is already
    # shared, so a seed derived from it is a seed everyone derives the same
    # way at no coordination cost.
    #
    # The claim is exactly three comparisons on the running page, so all
    # three are made: two different requests on the same day get the same
    # world, the next day is a different one, and with the switch off each
    # request keeps its own world (or the daily seed would have quietly
    # replaced the thing that makes a generated game that person's).
    from sidra_ai.creation.daily import PREAMBLE_NAMES as _daily_names

    def _daily_run(request, template, *, on, stamp):
        page = _tune_generate(request, template=template).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, f"{template}: no script"
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_fail_probe(
                    script.group(1),
                    # The seed is read at load; a full round per template
                    # would cost minutes to learn nothing more.
                    frames=40,
                    stamp=stamp,
                    stored={f"sidra.tune.{template}": {"daily": on}},
                ),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    daily_gaps: list[str] = []
    daily_ok: list[str] = []
    # Every template, and the *board* rather than the seed.
    #
    # C-1107's judge drove one template and compared the seed value, and
    # both halves of that were too weak. C-1118 found catch and fishing
    # claiming a shared board while laying theirs out with Math.random -
    # their seed matched because every page binds one, whether or not
    # anything reads it. So this compares what was drawn: two requests on
    # the same day have to draw the same board, tomorrow a different one,
    # and with the switch off each request keeps its own.
    #
    # Two more things make that question answerable. Each run is pinned to
    # a *different* Math.random stream, so a board that comes from chance
    # rather than from the seed shows up as a difference. And each run asks
    # for reduced motion, because particle bursts draw with Math.random and
    # fire on their own in half the templates - without it the traces
    # differ for reasons that have nothing to do with the board.
    from sidra_ai.creation.together import probe_source as _board_probe
    from sidra_ai.creation.tuning import SPEED_BINDING as _board_binding

    _daily_pairs = ("迷宮を冒険するゲームを作って", "べつの冒険ゲームを作って")

    def _daily_board(template, request, *, on, stamp, pin):
        page = _tune_generate(request, template=template).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, f"{template}: no script"
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_board_probe(
                    script.group(1),
                    speed_expr=_board_binding[template],
                    frames=120,
                    quiet=True,
                    reduced=True,
                    random_pin=pin,
                    stamp=stamp,
                    stored={
                        f"sidra.tune.{template}": {"daily": on},
                        f"sidra.seen.{template}": "1",
                    },
                ),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1])["geometry"], None
        except (OSError, _scene_sp.SubprocessError, ValueError, KeyError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    for key in sorted(_tune_templates):
        boards = {}
        trouble = None
        for label, request, on, stamp, pin in (
            ("todayA", _daily_pairs[0], True, "2026-09-03", 111),
            ("todayB", _daily_pairs[1], True, "2026-09-03", 222),
            ("tomorrow", _daily_pairs[0], True, "2026-09-04", 111),
            ("offA", _daily_pairs[0], False, "2026-09-03", 111),
            ("offB", _daily_pairs[1], False, "2026-09-03", 222),
        ):
            drawn, problem = _daily_board(key, request, on=on, stamp=stamp, pin=pin)
            if problem:
                trouble = problem
                break
            boards[label] = drawn
        if not trouble:
            if boards["todayA"] != boards["todayB"]:
                trouble = f"{key}: two requests drew different boards on the same day"
            elif boards["todayA"] == boards["tomorrow"]:
                trouble = f"{key}: tomorrow draws the same board as today"
            elif boards["offA"] == boards["offB"]:
                trouble = f"{key}: with the switch off, every request drew the same world"
            elif boards["offA"] == boards["todayA"]:
                trouble = f"{key}: the daily board applies with the switch off"
        if trouble:
            daily_gaps.append(trouble)
        else:
            daily_ok.append(key)
    # The point of deriving it locally: a shared board that cost a request
    # would be a different product and a broken promise.
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon"):
        if banned in _daily_preamble:
            daily_gaps.append(f"the daily seed reaches out: {banned!r}")
    for name in _daily_names:
        if any(f"function {name}(" in spec.script for spec in _tune_templates.values()):
            daily_gaps.append(f"a template shadows {name}")
    c.add(
        "creation_daily_seed",
        "日付だけで盤面が共有される型",
        float(len(daily_ok)) if not daily_gaps else 0.0,
        detail=(
            "描いた盤面そのものを比較。依頼文が違っても同じ日は同じ盤面、"
            "翌日は別、切れば依頼ごとの世界。各走行は Math.random の系列を"
            "変えて回すので、種ではなく偶然で決まる盤面は一致しない。"
            "日付→ハッシュをページ内で計算するだけで、通信は 0"
            if not daily_gaps
            else "; ".join(daily_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the first ten seconds contain one win --------------------------
    #
    # C-1108, §8 事実 5・8. What decides whether someone plays a second
    # round is whether the first gave them anything, and the pages had no
    # rule about their opening at all.
    #
    # The claim is about a player, so the judge is one: a masher that
    # presses the action, leans on a direction, taps the canvas, and knows
    # nothing about any particular game. It *wanders* rather than travels -
    # which is the point. An opening that requires walking across the field
    # to find the first target is an opening that asks for intent the
    # player has not formed yet, so the first success has to come to them.
    #
    # Run over several requests per template: the seed decides the layout,
    # and "guaranteed" that held for one seed would be a coincidence.
    from sidra_ai.creation.opening import (
        FIRST_SUCCESS as _open_success,
        OPENING_SECONDS as _open_seconds,
        probe_source as _open_probe,
    )

    _open_requests = ("ゲームを作って", "楽しいゲームを作って", "難しいゲームを作って")
    open_gaps: list[str] = []
    open_ok: list[str] = []
    open_worst = 0.0
    for key in sorted(_tune_templates):
        if key not in _open_success:
            open_gaps.append(f"{key}: no first success declared")
            continue
        slowest = 0.0
        for request in _open_requests:
            page = _tune_generate(request, template=key).html
            script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
            if script is None:
                open_gaps.append(f"{key}: no script")
                break
            try:
                probe = _scene_sp.run(
                    ["node", "-"],
                    input=_open_probe(script.group(1), key),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if probe.returncode != 0:
                    open_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                    break
                seen = json.loads(probe.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                open_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
                break
            # A success that was already true before anyone played is not a
            # success, it is a mistake in the expression - and the number
            # would then be measuring nothing at all.
            if seen.get("wonBeforePlaying"):
                open_gaps.append(f"{key}: the win was already true before playing")
                break
            if seen.get("firstWinMs") is None:
                open_gaps.append(
                    f"{key}: no {_open_success[key][1]} in {_open_seconds}s "
                    f"of 「{request}」"
                )
                break
            slowest = max(slowest, seen["firstWinMs"] / 1000)
        else:
            open_ok.append(key)
            open_worst = max(open_worst, slowest)
    c.add(
        "creation_first_success_10s",
        "最初の 10 秒に成功がある型",
        float(len(open_ok)) if not open_gaps else 0.0,
        detail=(
            f"何も知らないプレイヤー（連打＋方向キーを握るだけ）で実プレイ。"
            f"依頼文 3 種＝シード 3 種すべてで {_open_seconds} 秒以内に最初の成功。"
            f"いちばん遅い型で {open_worst:.1f} 秒"
            if not open_gaps
            else "; ".join(open_gaps)
        ),
        kind=OUTCOME,
    )

    # --- a score buys a colour, and never anything else ----------------
    #
    # C-1109, §8 事実 6. Somewhere for the time already spent to go is
    # what brings people back, and the usual way of building it is the way
    # that ruins a game: unlock the faster ship and everyone who arrives
    # later plays a worse game than the people who arrived early.
    #
    # So the number is not "unlocks exist". Each template is played out
    # twice by the same masher, on the same seed, with the same inputs and
    # the same cumulative total - once wearing the earned skin and once
    # not - and the two runs have to draw **the same shapes in different
    # colours**. The geometry trace is what makes the fairness claim
    # measurable: a skin that touched a speed, a size or a spawn interval
    # would move something, and the traces would stop matching.
    from sidra_ai.creation.skins import (
        PREAMBLE_NAMES as _skin_names,
        canonical_colour as _skin_colour,
        SKIN_PREAMBLE as _skin_preamble,
        probe_source as _skin_probe,
        skin_spec as _skin_spec,
        stray_calls as _skin_stray,
    )

    def _skin_run(template, *, stored, pick=None):
        page = _tune_generate("ゲームを作って", template=template).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, f"{template}: no script"
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_skin_probe(script.group(1), stored=stored, pick=pick),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    def _skin_script(template):
        page = _tune_generate("ゲームを作って", template=template).html
        found = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        return found.group(1) if found else ""

    skin_gaps: list[str] = []
    skin_ok: list[str] = []
    for key in sorted(_tune_templates):
        spec = _skin_spec(key)
        earned = spec["skins"][1]
        total_key, pick_key = f"sidra.total.{key}", f"sidra.skin.{key}"
        # Nothing played yet: only the free colour, and the rest priced.
        zero, problem = _skin_run(key, stored={})
        if problem:
            skin_gaps.append(problem)
            continue
        # The same earned total in both runs, so the only difference
        # between them is which colour is being worn. Picking happens
        # after the round, so this run doubles as the picker check.
        plain, problem = _skin_run(key, stored={total_key: str(earned["at"])}, pick=earned["id"])
        if problem:
            skin_gaps.append(problem)
            continue
        worn, problem = _skin_run(
            key, stored={total_key: str(earned["at"]), pick_key: earned["id"]}
        )
        if problem:
            skin_gaps.append(problem)
            continue
        locked_at_zero = [p["id"] for p in zero["pickers"] if p["locked"]]
        banked = float(zero["storedTotal"] or 0)
        if zero["facts"]["unlocked"] != ["base"]:
            skin_gaps.append(f"{key}: a skin was open before anything was played")
        elif earned["id"] not in locked_at_zero:
            skin_gaps.append(f"{key}: {earned['id']} was not shown as locked")
        elif banked <= 0:
            skin_gaps.append(f"{key}: a round of play banked nothing")
        elif banked >= earned["at"]:
            # A skin one round hands over is not a reason to play a second.
            skin_gaps.append(f"{key}: one round opened a skin ({banked} >= {earned['at']})")
        elif plain["picked"] != earned["id"] or plain["reloads"] < 1:
            skin_gaps.append(f"{key}: pressing an earned colour did not apply it")
        elif worn["facts"]["current"] != earned["id"]:
            skin_gaps.append(f"{key}: the picked colour is not the one worn")
        elif worn["accent"] != earned["accent"]:
            skin_gaps.append(f"{key}: the page paints with {worn['accent']}, not the skin")
        elif earned["accent"].lower() not in {_skin_colour(c) for c in worn["colours"]}:
            skin_gaps.append(f"{key}: the skin colour was never drawn")
        elif earned["accent"].lower() in {_skin_colour(c) for c in plain["colours"]}:
            skin_gaps.append(f"{key}: the skin colour was drawn without the skin")
        # The fairness invariant, and the only reason the number is worth
        # anything: same shapes, same score, different colours.
        elif worn["geometry"] != plain["geometry"]:
            skin_gaps.append(f"{key}: the skin changed what was drawn where")
        elif worn["scores"] != plain["scores"]:
            skin_gaps.append(f"{key}: the skin changed how the round went")
        elif {_skin_colour(c) for c in worn["colours"]} == {
            _skin_colour(c) for c in plain["colours"]
        }:
            skin_gaps.append(f"{key}: the skin changed nothing at all")
        # The traces can only see an axis the masher exercises, and it
        # cannot exercise all of them - the adventure keeps its enemies in
        # a room this player never reaches. So the same claim is made a
        # second way, from the assembled page: nothing outside the three
        # sanctioned call sites can reach a skin at all.
        elif _skin_stray(_skin_script(key), key):
            skin_gaps.append(
                f"{key}: the skin is reached from outside its three call sites - "
                + "; ".join(_skin_stray(_skin_script(key), key))
            )
        else:
            skin_ok.append(key)
    # The total is the player's own and stays on the player's own machine.
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        if banned in _skin_preamble:
            skin_gaps.append(f"the unlock reaches out: {banned!r}")
    for name in _skin_names:
        if any(f"function {name}(" in spec.script for spec in _tune_templates.values()):
            skin_gaps.append(f"a template shadows {name}")
    c.add(
        "creation_cosmetic_unlock",
        "性能を変えずに見た目だけが開く型",
        float(len(skin_ok)) if not skin_gaps else 0.0,
        detail=(
            "同じシード・同じ入力・同じ累計で 2 回実プレイし、"
            "描いた図形とスコアが完全一致・色だけが違うことを確認。"
            "加えて組み上がったページを読み、スキンに触れる箇所が"
            "色・加算・告知の 3 か所しかないことを確認（速さ等には届かない）。"
            "累計はラウンド終了時に端末内へ加算（通信 0）、"
            "1 ラウンドでは開かない価格"
            if not skin_gaps
            else "; ".join(skin_gaps)
        ),
        kind=OUTCOME,
    )

    # --- a result you can paste, that gives nothing away ----------------
    #
    # C-1110, §8 事実 7. What spreads a game is a result its player wants
    # to show; what makes showing it safe for everybody else is that the
    # result cannot be read backwards into the answer.
    #
    # So the number is about the characters that reach the clipboard, and
    # the judge reads them off the running page: it plays a round out,
    # waits for the result to come up, presses the page's own button, and
    # then asks what was copied. Three things must be absent from that
    # string - a URL, the person (their words, their title, their device)
    # and the board (above all the seed) - and the score must be present,
    # in a row whose length is derived from it rather than decorative.
    import zlib as _share_zlib

    from sidra_ai.creation.share import (
        PREAMBLE_NAMES as _share_names,
        SHARE_MAX as _share_max,
        SHARE_PREAMBLE as _share_preamble,
        leaks as _share_leaks,
        probe_source as _share_probe,
        share_spec as _share_spec,
    )

    _share_request = "ゲームを作って"
    _share_stamp = "2026-09-03"
    _share_seed = _share_zlib.crc32(_share_request.encode("utf-8"))

    def _share_run(template, *, daily):
        art = _tune_generate(_share_request, template=template)
        script = _scene_re.search(r"<script>(.*?)</script>", art.html, _scene_re.S)
        if script is None:
            return None, None, f"{template}: no script"
        stored = {f"sidra.tune.{template}": {"daily": True}} if daily else {}
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_share_probe(script.group(1), stored=stored, stamp=_share_stamp),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if probe.returncode != 0:
                return None, None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), art.title, None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, None, f"{template}: probe unavailable ({type(exc).__name__})"

    share_gaps: list[str] = []
    share_ok: list[str] = []
    for key in sorted(_tune_templates):
        spec = _share_spec(key)
        trouble = None
        for daily in (False, True):
            seen, title, problem = _share_run(key, daily=daily)
            if problem:
                trouble = problem
                break
            facts = seen["facts"]
            copied = seen["afterClick"]
            where = f"{key} (daily {'on' if daily else 'off'})"
            if not seen["button"]:
                trouble = f"{where}: no copy button on the page"
            # Before there is a result there is nothing to copy. A button
            # that answered mid-round would be sharing a number nobody
            # finished scoring.
            elif seen["early"]["ready"] or seen["early"]["text"] is not None:
                trouble = f"{where}: a result was copyable while the round was running"
            elif len(copied) != 1 or copied[0] != facts["text"]:
                trouble = f"{where}: pressing the button copied {copied!r}"
            elif facts["copies"] < 2:
                trouble = f"{where}: the keyboard route does not copy"
            else:
                text = copied[0]
                found = _share_leaks(
                    text, request=_share_request, title=title or "", seed=_share_seed
                )
                score = facts["score"]
                want = (
                    ""
                    if not (score and score > 0)
                    else facts["emoji"]
                    * max(1, min(facts["max"], round(score / facts["per"])))
                )
                if found:
                    trouble = f"{where}: {'; '.join(found)}"
                elif str(score) not in text:
                    trouble = f"{where}: the line does not carry the score"
                elif facts["bar"] != want:
                    trouble = f"{where}: the row is not derived from the score"
                elif len(facts["bar"]) and facts["bar"] not in text:
                    trouble = f"{where}: the row was not in the copied line"
                # The daily stamp is safe to paste precisely because it is
                # everybody's; saying it on a board that is not shared
                # would make the claim meaningless.
                # Only a page whose board comes from the seed has a board
                # to share. Two templates lay theirs out with Math.random
                # and have none, so for them the switch can be on and the
                # line must still not say 今日の. (C-1118 found the page
                # saying it anyway; this judge asked for it.)
                elif daily and seen["round"]["seed"] is not None and _share_stamp not in text:
                    trouble = f"{where}: today's board is not named"
                elif daily and seen["round"]["seed"] is None and _share_stamp in text:
                    trouble = f"{where}: a board nobody else has is dated as today's"
                elif not daily and _share_stamp in text:
                    trouble = f"{where}: a private board is dated as today's"
            if trouble:
                break
        if trouble:
            share_gaps.append(trouble)
        else:
            share_ok.append(key)
    # The line is pasted by hand, into whatever the person chooses. Nothing
    # about it goes anywhere by itself.
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket", "share("):
        if banned in _share_preamble:
            share_gaps.append(f"the share line reaches out: {banned!r}")
    for name in _share_names:
        if any(f"function {name}(" in spec.script for spec in _tune_templates.values()):
            share_gaps.append(f"a template shadows {name}")
    c.add(
        "creation_share_text",
        "ネタバレなしで貼れる結果の行がある型",
        float(len(share_ok)) if not share_gaps else 0.0,
        detail=(
            f"実プレイでラウンドを終わらせ、ページ自身のボタンを押して"
            f"クリップボードに載った文字列を検査。絵文字は最大 {_share_max} 個で"
            "スコアから導出。URL・依頼文・タイトル・シード・端末情報のいずれも"
            "含まない。日替わりが入のときだけ日付が付く"
            if not share_gaps
            else "; ".join(share_gaps)
        ),
        kind=OUTCOME,
    )

    # --- open it, press once, play ---------------------------------------
    #
    # C-1111, §8 事実 8. The briefing screen (C-1033) is worth having and
    # it is in tension with "playable the moment it opens". The resolution
    # is not to drop one of them: the first visit gets the three lines and
    # one input of *any* kind starts the game, and every visit after that
    # opens straight into play, because the briefing is only news once.
    #
    # Measured from load, in frames, on the running page. "Playable" is
    # not a state name here - it is the template's own callback receiving
    # frames, which is the thing a player can actually act on.
    from sidra_ai.creation.startscreen import (
        FIRST_INPUTS as _start_inputs,
        INSTANT_FRAMES as _start_frames,
        start_probe_source as _start_probe,
    )

    def _start_run(template, script, **kw):
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_start_probe(script, **kw),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    start_gaps: list[str] = []
    start_ok: list[str] = []
    start_worst = 0.0
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            start_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        seen = {f"sidra.seen.{key}": "1"}
        trouble = None
        # A first visit is gated: the three lines are what the controls are.
        fresh, problem = _start_run(key, body)
        if problem:
            start_gaps.append(problem)
            continue
        if fresh["untouched"]["frames"] != 0 or fresh["untouched"]["state"] != "title":
            trouble = f"{key}: the first visit skipped its own briefing"
        # ...and one input of any kind opens it, within one frame.
        for kind, pressed in _start_inputs:
            if trouble:
                break
            after, problem = _start_run(key, body, kind=kind, key=pressed)
            if problem:
                trouble = problem
                break
            name = "tap" if kind == "tap" else repr(pressed)
            if after["frames"][0] < 1:
                trouble = f"{key}: {name} did not start the game"
            elif after["frames"][0] != _start_frames:
                trouble = f"{key}: {name} took {after['frames'][0]} frames, not {_start_frames}"
            elif not after["stored"]:
                trouble = f"{key}: starting was not remembered for next time"
            else:
                start_worst = max(start_worst, after["frames"][0] * 50 / 3)
        if not trouble:
            # A return visit opens straight into play, with no input at all.
            back, problem = _start_run(key, body, stored=dict(seen))
            if problem:
                trouble = problem
            elif not back["untouched"]["skipped"] or back["untouched"]["frames"] < 1:
                trouble = f"{key}: a return visit still had to be pressed through"
            # And it has made no sound, because no gesture has happened. A
            # page that opened playing and played a sound anyway would be
            # asking the browser for something it refuses.
            elif back["untouched"]["gesture"]:
                trouble = f"{key}: a sound was played before anyone touched anything"
        if not trouble:
            touched, problem = _start_run(key, body, stored=dict(seen), kind="key", key=" ")
            if problem:
                trouble = problem
            elif not touched["afterInput"]["gesture"]:
                trouble = f"{key}: the first input on a skipped start unlocked no sound"
        if not trouble:
            # The way back to the briefing, for somebody who wants it.
            asked, problem = _start_run(
                key, body, stored={**seen, f"sidra.tune.{key}": {"brief": True}}
            )
            if problem:
                trouble = problem
            elif asked["untouched"]["skipped"] or asked["untouched"]["frames"] != 0:
                trouble = f"{key}: the briefing cannot be asked for again"
        if trouble:
            start_gaps.append(trouble)
        else:
            start_ok.append(key)
    c.add(
        "creation_instant_start",
        "1 入力で遊べて、2 回目は待たされない型",
        float(len(start_ok)) if not start_gaps else 0.0,
        detail=(
            f"ロードから実プレイで計測。初回はブリーフィングが出て、"
            f"キー 5 種＋タップのどれでも 1 入力・{_start_frames} フレーム"
            f"（{start_worst:.0f}ms）で操作可能に。2 回目以降は無入力で"
            "そのまま遊べ、かつジェスチャ前に音は鳴らさない。"
            "毎回見たい人は調整パネルで戻せる"
            if not start_gaps
            else "; ".join(start_gaps)
        ),
        kind=OUTCOME,
    )

    # --- all ten of them at once, on the same frame ---------------------
    #
    # C-1118. C-1104 to C-1116 landed in twelve hours and every one has a
    # judge that says 1 - each driving the page with its own feature on and
    # the rest at their defaults. Nobody had run the clock, the failure
    # beat, the result strip, the daily seed, the unlock, the share line,
    # the panel and the instant start together, which is the only way a
    # person will ever run them.
    #
    # The sweep found two real defects and this number is what keeps them
    # fixed: the strip had grown to ~800px on a 720px canvas (centred, so
    # it lost both ends), and two templates that have no seed at all were
    # claiming 今日の挑戦 - on screen and in the line people paste.
    from sidra_ai.creation.together import (
        CANVAS_WIDTH as _all_width,
        key_gaps as _all_keys,
        probe_source as _all_probe,
        text_width as _all_text_width,
    )
    from sidra_ai.creation.share import leaks as _all_leaks
    from sidra_ai.creation.skins import skin_spec as _all_skin
    from sidra_ai.creation.tuning import SPEED_BINDING as _all_binding

    _all_stamp = "2026-09-03"
    _all_request = "ゲームを作って"
    together_gaps: list[str] = []
    together_ok: list[str] = []
    for key in sorted(_tune_templates):
        art = _tune_generate(_all_request, template=key)
        found = _scene_re.search(r"<script>(.*?)</script>", art.html, _scene_re.S)
        if found is None:
            together_gaps.append(f"{key}: no script")
            continue
        body = found.group(1)
        earned = _all_skin(key)["skins"][1]
        hardest = max(pair[0] for pair in _tune_ladder[key].values())
        stored = {
            f"sidra.seen.{key}": "1",
            f"sidra.skin.{key}": earned["id"],
            f"sidra.total.{key}": str(earned["at"]),
            f"sidra.best.{key}": "999999",
            f"sidra.tune.{key}": {"daily": True, "speed": hardest},
        }
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_all_probe(
                    body,
                    speed_expr=_all_binding[key],
                    stored=stored,
                    stamp=_all_stamp,
                ),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if probe.returncode != 0:
                together_gaps.append(f"{key}: {probe.stderr.strip()[:60]}")
                continue
            seen = json.loads(probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            together_gaps.append(f"{key}: probe unavailable ({type(exc).__name__})")
            continue
        gate, strip = seen["atLoad"]["gate"], seen["strip"]
        lines = sorted({item["text"] for item in strip})
        # The strip's own two lines, told apart from the clock's banner and
        # from the template's own ending by where they are drawn. Without
        # this, emptying the strip's retry hint still passed: four templates
        # print a 「もう一度」 of their own somewhere higher up.
        band = sorted({item["text"] for item in strip if item["y"] >= 280})
        # A page whose board is not seed-derived has no shared board, so
        # neither the strip nor the copied line may say it has one.
        shared = seen["facts"]["round"]["seed"] is not None
        said_today = [line for line in band if "今日の挑戦" in line]
        copied = seen["clipboard"][0] if seen["clipboard"] else ""
        wide = [line for line in lines if _all_text_width(line) > _all_width]
        problems = _all_keys(body)
        if not gate["skipped"] or gate["frames"] < 1:
            problems.append("the briefing was not skipped on a return visit")
        elif gate["gesture"]:
            problems.append("a sound was played before anyone touched anything")
        if seen["atLoad"]["speed"] != hardest:
            problems.append(f"the panel's speed did not reach the game ({seen['atLoad']['speed']})")
        if seen["atLoad"]["accent"] != earned["accent"]:
            problems.append("the earned colour is not the one being painted with")
        if not (seen["atBreak"]["round"]["done"] or seen["atBreak"]["round"]["ended"]):
            problems.append("the round never reached a break")
        if seen["stripAt"] is None:
            problems.append("the result screen never drew anything")
        if wide:
            problems.append(f"the result strip runs off the canvas: {wide[0][:40]}…")
        if not [line for line in band if "もう一度" in line]:
            problems.append("the result strip does not say how to go again")
        if shared and not said_today:
            problems.append("today's board is not named on a page that has one")
        if not shared and said_today:
            problems.append("a board nobody else has is called today's")
        if not copied:
            problems.append("nothing was copied from the result screen")
        else:
            problems += _all_leaks(
                copied,
                request=_all_request,
                title=art.title,
                seed=_share_zlib.crc32(_all_request.encode("utf-8")),
            )
            if shared != (_all_stamp in copied):
                problems.append("the copied line disagrees with the screen about today")
        stray = [k for k in seen["writes"] if not k.endswith("." + key)]
        if stray:
            problems.append(f"a write escaped this template's namespace: {stray}")
        if problems:
            together_gaps.append(f"{key}: " + "; ".join(problems[:3]))
        else:
            together_ok.append(key)
    c.add(
        "creation_features_together",
        "10 機能を同時に入れても壊れない型",
        float(len(together_ok)) if not together_gaps else 0.0,
        detail=(
            "即時開始・ブリーフィング既読・日替わり・手動の速度・獲得スキン・"
            "60 秒区切り・失敗演出・リザルト帯・共有文を全部入れて 9 型を実プレイ。"
            "帯が canvas に収まること、日替わりを名乗るのは種のある盤面だけ、"
            "localStorage の鍵が型ごとに分かれていることを同時に確認"
            if not together_gaps
            else "; ".join(together_gaps)
        ),
        kind=OUTCOME,
    )

    # --- how many of the page's own dials a sentence can turn -----------
    #
    # C-1117. C-1112 gave the revision loop three axes (difficulty, theme,
    # title) while C-1113 put six adjustable parameters in every page. The
    # gap was the interesting part: a person could move a slider the words
    # could not reach, which is the "ask again and get something different"
    # trap §9 records, one level down.
    #
    # Counted by running the real detector and the real reviser and then
    # reading the rebuilt artifact - the schema the page embeds, its
    # palette, its title. A vocabulary that parses and changes nothing
    # would score zero here.
    import tempfile as _axis_tf

    from sidra_ai.creation.games import save_game as _axis_save
    from sidra_ai.creation.revise import (
        build_game_reviser as _axis_reviser,
        detect_revision_intent as _axis_detect,
        save_meta as _axis_meta,
    )

    #: One sentence per axis, and what has to be different afterwards. Both
    #: band directions are here because a judge that only ever narrowed
    #: would not notice the widening words being deleted.
    _AXIS_CASES = (
        ("difficulty", "さっきのゲームを難しくして"),
        ("band", "さっきのゲームの敵を減らして"),
        ("band_up", "さっきのゲームの敵を増やして"),
        ("accent", "さっきのゲームを赤にして"),
        ("daily", "さっきのゲームを日替わりにして"),
        ("brief", "さっきのゲームのブリーフィングを毎回出して"),
        ("theme", "さっきのゲームを紙のテーマにして"),
        ("title", "さっきのゲームのタイトルを「海」にして"),
    )

    def _axis_body(path):
        """What the *game* got, not what the panel declares it got."""

        text = Path(path).read_text(encoding="utf-8")
        script = _scene_re.search(r"<script>(.*?)</script>", text, _scene_re.S)
        if script is None:
            return None, None, text
        body = script.group(1)
        spec = _scene_re.search(r"const TUNE_SPEC=(\{.*?\});", body, _scene_re.S)
        if spec is None:
            return None, None, text
        return (
            {f["key"]: f["default"] for f in json.loads(spec.group(1))["fields"]},
            body,
            text,
        )

    def _axis_running(body, *, flag):
        """Drive the page and ask it, rather than reading the declaration.

        The declaration was not enough: a schema default that never reached
        ``dailyOn`` still looked like a change. Same lesson as C-1119 -
        a value nothing reads is not a fact about the product.
        """

        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_board_probe(
                    body,
                    speed_expr="0",
                    frames=6,
                    quiet=True,
                    reduced=True,
                    stored={"sidra.seen.adventure": "1"},
                ),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if probe.returncode != 0:
                return None
            seen = json.loads(probe.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError, KeyError):
            return None
        if flag == "daily":
            return bool(seen["atLoad"]["round"]["daily"])
        # The briefing is asked for: a page that has been read before opens
        # straight into play unless this switch says otherwise.
        return not bool(seen["atLoad"]["gate"]["skipped"])

    axis_gaps: list[str] = []
    axis_ok: list[str] = []
    for axis, sentence in _AXIS_CASES:
        with _axis_tf.TemporaryDirectory() as home:
            built = _tune_generate("冒険ゲームを作って", template="adventure")
            page = _axis_save(built, home)
            _axis_meta(
                page,
                request="冒険ゲームを作って",
                template="adventure",
                difficulty=built.difficulty,
                theme="",
                title=built.title,
                panel={},
            )
            before, before_body, before_text = _axis_body(page)
            intent = _axis_detect(sentence)
            if not intent.is_revision:
                axis_gaps.append(f"{axis}: 「{sentence}」 was not read as a revision")
                continue
            outcome = _axis_reviser(home)(sentence, intent)
            if not outcome.artifact_path:
                axis_gaps.append(f"{axis}: the revision produced no page")
                continue
            after, after_body, after_text = _axis_body(outcome.artifact_path)
            if before is None or after is None:
                axis_gaps.append(f"{axis}: the page carries no panel schema")
                continue
            if axis == "title":
                moved = "海" in after_text and "海" not in before_text
            elif axis == "theme":
                moved = after["accent"] != before["accent"] and after_text != before_text
            elif axis in ("daily", "brief"):
                was = _axis_running(before_body, flag=axis)
                now = _axis_running(after_body, flag=axis)
                moved = was is False and now is True
            elif axis == "band_up":
                moved = after["band"] > before["band"]
            elif axis == "band":
                moved = after["band"] < before["band"]
            else:
                moved = after.get(axis) != before.get(axis)
            if not moved:
                axis_gaps.append(f"{axis}: 「{sentence}」 changed nothing in the page")
                continue
            # A second sentence must build on the first. Without the panel in
            # the sidecar the rebuild goes back to the ladder and quietly
            # undoes whatever the first sentence turned - which is the
            # failure this whole item exists to avoid.
            if axis in ("band", "band_up", "accent", "daily", "brief"):
                follow = "さっきのゲームのタイトルを「続き」にして"
                chained = _axis_reviser(home)(follow, _axis_detect(follow))
                kept, _, _ = _axis_body(chained.artifact_path or "")
                if kept is None or kept.get(axis if axis != "band_up" else "band") != after.get(
                    axis if axis != "band_up" else "band"
                ):
                    axis_gaps.append(f"{axis}: a later sentence undid it")
                    continue
            axis_ok.append(axis)
    c.add(
        "creation_revision_axes",
        "言葉で回せるページの軸",
        float(len(axis_ok)) if not axis_gaps else 0.0,
        detail=(
            "本物の検出器と修正器を通し、組み上がったページを読んで確認。"
            "今日の挑戦とブリーフィングは実際にページを走らせて聞く"
            "（宣言された既定値では、どこにも届いていなくても変わって見える）。"
            "帯は増減の両方向。どの軸も、次の一文のあとも残っていることを確認。"
            f"{len(axis_ok)} 軸。速さは難易度ラダーが持つので別軸にしない"
            if not axis_gaps
            else "; ".join(axis_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the best run, played back beside this one ----------------------
    #
    # C-1401, §11 事実 1. The personal best existed as a number on a strip
    # (C-1106) and there was no way to play *with* the run that set it.
    #
    # Two real runs, and the second one gets what the first one saved. The
    # interesting assertions are the two that say the ghost is a memory
    # rather than a second car: with it switched off the page draws exactly
    # what it drew before there was one, and with it on the race comes out
    # the same - it is drawn, and it touches nothing.
    from sidra_ai.creation.ghost import (
        GHOST_PREAMBLE as _ghost_preamble,
        GHOST_TEMPLATES as _ghost_templates,
        PREAMBLE_NAMES as _ghost_names,
    )

    def _ghost_run(template, script, stored):
        source = _board_probe(
            script,
            speed_expr=_board_binding[template],
            frames=3800,
            stored=stored,
        ).replace(
            "  writes: [...new Set(allWrites)].sort(),",
            "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
            f" trail: allStored['sidra.ghost.{template}']||null,",
        )
        try:
            probe = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=300
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    ghost_gaps: list[str] = []
    ghost_ok: list[str] = []
    for key in _ghost_templates:
        page = _tune_generate("レースゲームを作って", template=key).html
        found = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if found is None:
            ghost_gaps.append(f"{key}: no script")
            continue
        body = found.group(1)
        base = {f"sidra.seen.{key}": "1"}
        first, problem = _ghost_run(key, body, dict(base))
        if problem:
            ghost_gaps.append(problem)
            continue
        if first["ghost"]["had"] or first["ghost"]["drawn"]:
            ghost_gaps.append(f"{key}: a ghost appeared before anyone had played")
            continue
        if not first["trail"] or first["ghost"]["saved"] < 1:
            ghost_gaps.append(f"{key}: the run that set the record saved no trail")
            continue
        carried = {**base, f"sidra.ghost.{key}": first["trail"]}
        second, problem = _ghost_run(key, body, dict(carried))
        if problem:
            ghost_gaps.append(problem)
            continue
        off, problem = _ghost_run(
            key, body, {**carried, f"sidra.tune.{key}": {"ghost": False}}
        )
        if problem:
            ghost_gaps.append(problem)
            continue
        if not second["ghost"]["had"] or second["ghost"]["drawn"] < 1:
            ghost_gaps.append(f"{key}: the second run did not replay the first")
        elif second["geometry"] == first["geometry"]:
            ghost_gaps.append(f"{key}: the ghost was never drawn on screen")
        # Drawn, and nothing else. A past run that changed this one would be
        # a second car rather than a memory.
        # The car's own path, not the lap count: a ghost that quietly drags
        # the car keeps the lap count and changes the race, which is what a
        # deliberate break showed before this compared the right thing.
        elif second["ghost"]["runHash"] != off["ghost"]["runHash"]:
            ghost_gaps.append(f"{key}: the ghost changed how the race went")
        elif off["ghost"]["drawn"]:
            ghost_gaps.append(f"{key}: the switch does not put the ghost away")
        elif off["geometry"] != first["geometry"]:
            ghost_gaps.append(f"{key}: with the ghost off the page still drew differently")
        else:
            ghost_ok.append(key)
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        if banned in _ghost_preamble:
            ghost_gaps.append(f"the ghost reaches out: {banned!r}")
    for name in _ghost_names:
        if any(f"function {name}(" in spec.script for spec in _tune_templates.values()):
            ghost_gaps.append(f"a template shadows {name}")
    c.add(
        "creation_ghost_replay",
        "過去の自分と走れる型",
        float(len(ghost_ok)) if not ghost_gaps else 0.0,
        detail=(
            "実走行 2 回。1 回目はゴースト無しで走って軌跡を保存し、2 回目に"
            "だけ半透明のゴーストが現れる（描画差で確認）。コース位置で索引"
            "するので速い走行でもずれない。当たり判定なし——2 回目のスコアは"
            "1 回目と同じで、パネルで切ると描画は 1 回目と完全一致。通信は 0"
            if not ghost_gaps
            else "; ".join(ghost_gaps)
        ),
        kind=OUTCOME,
    )

    # --- three losses in a row buy one step toward the player -----------
    #
    # C-1402, §11 事実 2-3. A player who keeps failing leaves, and the
    # difficulty dial does not help them because reaching for it means
    # admitting to a setting. §11's warning comes with it: hidden dynamic
    # difficulty makes players distrust their wins and lets others farm it,
    # so this one says which step it is on and never argues with a value
    # the person set by hand.
    #
    # Driven on two templates because one cannot show both halves: the
    # shooter can be lost by a masher and the race can be won by one.
    from sidra_ai.creation.adapt import (
        ADAPT_AFTER as _adapt_after,
        ADAPT_PREAMBLE as _adapt_preamble,
        PREAMBLE_NAMES as _adapt_names,
    )

    def _adapt_run(template, request, stored):
        page = _tune_generate(request, template=template).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, f"{template}: no script"
        source = _board_probe(
            script.group(1),
            speed_expr=_board_binding[template],
            frames=3800,
            stored=stored,
        ).replace(
            "  writes: [...new Set(allWrites)].sort(),",
            "  writes: [...new Set(allWrites)].sort(), adapt: adaptFacts(),"
            f" streakAfter: allStored['sidra.streak.{template}']||null,"
            " said: (function(){const n=(function w(e){return [e].concat("
            "(e.children||[]).flatMap(w))})(allBody).filter(x=>x.id==='adapt')[0];"
            " return n?n.textContent:null})(),",
        )
        try:
            probe = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=300
            )
            if probe.returncode != 0:
                return None, f"{template}: {probe.stderr.strip()[:60]}"
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{template}: probe unavailable ({type(exc).__name__})"

    adapt_gaps: list[str] = []
    _adapt_loser, _adapt_winner = "shooter", "racing"
    _adapt_ladder = [pair[0] for pair in _tune_ladder[_adapt_loser].values()]
    _adapt_base = {f"sidra.seen.{_adapt_loser}": "1"}
    runs = {}
    for label, streak in (("fresh", None), ("two", 2), ("three", 3)):
        stored = dict(_adapt_base)
        if streak is not None:
            stored[f"sidra.streak.{_adapt_loser}"] = str(streak)
        seen, problem = _adapt_run(_adapt_loser, "シューティングゲームを作って", stored)
        if problem:
            adapt_gaps.append(problem)
            break
        runs[label] = seen
    if len(runs) == 3:
        fresh, two, three = runs["fresh"], runs["two"], runs["three"]
        if fresh["adapt"]["eased"] or two["adapt"]["eased"]:
            adapt_gaps.append(f"eased before {_adapt_after} losses in a row")
        elif fresh["atLoad"]["speed"] != two["atLoad"]["speed"]:
            adapt_gaps.append("the speed drifted while nothing had happened")
        elif not three["adapt"]["eased"]:
            adapt_gaps.append(f"{_adapt_after} losses in a row bought nothing")
        # One step, to a value the author shipped - not a percentage.
        elif three["atLoad"]["speed"] not in _adapt_ladder:
            adapt_gaps.append(f"eased to {three['atLoad']['speed']}, which is not on the ladder")
        elif _adapt_ladder.index(three["atLoad"]["speed"]) != max(
            0, _adapt_ladder.index(fresh["atLoad"]["speed"]) - 1
        ):
            adapt_gaps.append("eased by more or less than one step")
        # §11 事実 3: it has to say so.
        elif not three["said"] or "やさしく" not in three["said"]:
            adapt_gaps.append(f"the page does not say it is helping: {three['said']!r}")
        elif fresh["said"] and "やさしく" in fresh["said"]:
            adapt_gaps.append("the page claims to be helping when it is not")
        else:
            # A hand-set value is a decision, and this never argues with one.
            manual, problem = _adapt_run(
                _adapt_loser,
                "シューティングゲームを作って",
                {
                    **_adapt_base,
                    f"sidra.streak.{_adapt_loser}": "3",
                    f"sidra.tune.{_adapt_loser}": {"speed": max(_adapt_ladder)},
                },
            )
            if problem:
                adapt_gaps.append(problem)
            elif manual["atLoad"]["speed"] != max(_adapt_ladder) or manual["adapt"]["eased"]:
                adapt_gaps.append("a hand-set speed was overruled")
            else:
                # And the help lasts exactly as long as the trouble.
                won, problem = _adapt_run(
                    _adapt_winner,
                    "レースゲームを作って",
                    # The pace is pinned by hand so this measures the
                    # streak and nothing else: left to ease, the race drops
                    # to a rung that cannot finish inside C-1104's clock,
                    # which is racing's defect (C-1404), not this rule's.
                    {
                        f"sidra.seen.{_adapt_winner}": "1",
                        f"sidra.streak.{_adapt_winner}": "3",
                        f"sidra.tune.{_adapt_winner}": {
                            "speed": _tune_ladder[_adapt_winner]["normal"][0]
                        },
                    },
                )
                if problem:
                    adapt_gaps.append(problem)
                elif won["atBreak"]["beats"]:
                    adapt_gaps.append("the round meant to be won was lost")
                elif won["streakAfter"] != "0":
                    adapt_gaps.append(f"a win left the streak at {won['streakAfter']}")
    for banned in ("fetch(", "XMLHttpRequest", "://", "sendBeacon", "WebSocket"):
        if banned in _adapt_preamble:
            adapt_gaps.append(f"the adjustment reaches out: {banned!r}")
    for name in _adapt_names:
        if any(f"function {name}(" in spec.script for spec in _tune_templates.values()):
            adapt_gaps.append(f"a template shadows {name}")
    c.add(
        "creation_adaptive_difficulty",
        "連敗したら 1 段だけ寄り添う",
        0.0 if adapt_gaps else 1.0,
        detail=(
            f"実走行で確認。{_adapt_after} 連敗までは何も変わらず、"
            "そこで作者のラダーの 1 段だけやさしい値に移る（％ではなく、"
            "作者が出荷した値）。勝てば連敗は 0 に戻る。手で設定した値には"
            "触れない。そして隠さない——今どの段かをページが表示する"
            if not adapt_gaps
            else "; ".join(adapt_gaps)
        ),
        kind=OUTCOME,
    )

    # --- "make it harder" edits the game instead of replacing it -------
    #
    # §9's chronic market failure, measured as a roundtrip through the real
    # generator and reviser rather than the detector alone: the number is
    # about what an operator gets back. Four things must hold at once - the
    # revision changes exactly the named parameter, the original file
    # survives untouched, a second revision builds on the first (not on the
    # original), and the detector steals nothing from the creation path.
    import tempfile as _tf

    from sidra_ai.creation.game_job import build_game_generator as _gen_builder
    from sidra_ai.creation.intent import detect_creation_intent as _detect_creation
    from sidra_ai.creation.revise import (
        build_game_reviser as _rev_builder,
        detect_revision_intent as _detect_revision,
    )

    revision_reasons: list[str] = []
    with _tf.TemporaryDirectory() as _rev_dir:
        _made = _gen_builder(_rev_dir)(
            "釣りゲームを作って", _detect_creation("釣りゲームを作って")
        )
        _original = Path(_made.artifact_path)
        _original_bytes = _original.read_bytes() if _original.exists() else b""
        _reviser = _rev_builder(_rev_dir)
        _harder = _reviser(
            "さっきのゲームをもっと難しくして",
            _detect_revision("さっきのゲームをもっと難しくして"),
        )
        if _harder.details.get("difficulty") != "hard":
            revision_reasons.append("difficulty did not step normal->hard")
        if not _harder.details.get("playable"):
            revision_reasons.append("revised page is not playable")
        if not (_original.exists() and _original.read_bytes() == _original_bytes):
            revision_reasons.append("the original file did not survive the revision")
        if Path(_harder.artifact_path or "") == _original:
            revision_reasons.append("revision overwrote the original path")
        _easier = _reviser(
            "さっきのゲームをやさしくして",
            _detect_revision("さっきのゲームをやさしくして"),
        )
        if "hard→normal" not in _easier.summary:
            revision_reasons.append("second revision did not build on the first")
    if _detect_revision("難しいゲームを作って").is_revision:
        revision_reasons.append("reviser steals creation requests")
    if _detect_revision("ゲームを難しくできますか").is_revision:
        revision_reasons.append("reviser steals questions")
    c.add(
        "creation_revision_roundtrip",
        "生成済みゲームを言葉で修正できる",
        0.0 if revision_reasons else 1.0,
        detail=(
            "「難しくして」で難易度だけが変わり、旧版は残り、"
            "2 回目の修正は 1 回目の続きから、質問と新規作成は奪わない"
            if not revision_reasons
            else "; ".join(revision_reasons)
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

    # --- spelling robustness: the AI must be the same program per script --
    #
    # Measured before fixed: 「ぜるだみたいなげーむつくって」 fell through to
    # the fishing default because the vocabulary is katakana and the request
    # was hiragana. Twelve fixed paraphrases, each scored on both decisions
    # (kind, and template where the kind is game).
    from sidra_ai.creation.intent import detect_creation_intent as _detect_kana

    _PARAPHRASES = (
        ("ぜるだみたいなげーむつくって", "game", "adventure"),
        ("どらごんぼーるのばとるつくって", "game", "duel"),
        ("しゅーてぃんぐげーむ作って", "game", "shooter"),
        ("ぱずるつくって", "game", "puzzle"),
        ("つりげーむつくって", "game", "fishing"),
        ("きゃっちげーむつくって", "game", "catch"),
        ("ダンジョンたんけんゲームを作って", "game", "adventure"),
        ("ビームでたいせんするゲーム作って", "game", "duel"),
        ("れぽーとつくって", "document", None),
        ("じふつくって", "gif", None),
        ("あーとつくって", "art", None),
        ("でっきつくって", "deck", None),
    )
    kana_ok = 0
    kana_misses = []
    for text, kind, template_key in _PARAPHRASES:
        intent = _detect_kana(text)
        good = intent.kind.value == kind and (
            template_key is None or choose_template(text) == template_key
        )
        if good:
            kana_ok += 1
        else:
            kana_misses.append(
                f"{text} -> {intent.kind.value}"
                + (f"/{choose_template(text)}" if kind == "game" else "")
            )
    c.add(
        "creation_intent_paraphrase",
        "表記ゆれでも正しく届く依頼",
        float(kana_ok),
        detail=(
            f"{kana_ok} of {len(_PARAPHRASES)} spellings routed correctly"
            if not kana_misses
            else "; ".join(kana_misses[:4])
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

    # Directly, or through C-1105's shared failure kit: failBeat *is* the
    # three, and creation_fail_beat proves it by driving every template to
    # an actual loss and watching the screen. A template whose only freeze
    # is the one it loses on is wired; inventing a second hitstop so this
    # grep would pass would be padding rather than weight.
    unwired = [
        f"{key}: no {name}()"
        for key, spec in sorted(TEMPLATES.items())
        for name in ("shake", "hitstop", "burst")
        if f"{name}(" not in spec.script and "failBeat(" not in spec.script
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
        "reach shake, hitstop and burst (directly or through failBeat)"
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


def _measure_index_compaction() -> tuple[float, str]:
    """Whether restarting over a bloated index file shrinks it to the truth.

    Seventy versions of one logical document leave seventy records in an
    append-only file; the next service start must rewrite it down to the one
    that is live, atomically, keeping 0600. Measured through the real service
    constructor because that is where the compaction hook lives.
    """

    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path as _Path

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.models.echo import EchoModelAdapter

    try:
        with _quiet(), tempfile.TemporaryDirectory() as scratch:
            settings = Settings(data_dir=scratch)
            first = SidraService(settings=settings, model=EchoModelAdapter())
            for i in range(70):
                first.store.add(
                    Document(
                        content=f"版 {i} の内容。",
                        provenance=Provenance(
                            source="github",
                            repository="tukemen-rgb/site",
                            path="docs/x.md",
                            commit_sha="a" * 40,
                            timestamp=datetime(2026, 8, 30, tzinfo=timezone.utc),
                            source_type=SourceType.DOCS,
                            trust_level=TrustLevel.INTERNAL_REPO,
                            license="MIT",
                        ),
                    )
                )
            second = SidraService(settings=settings, model=EchoModelAdapter())
            index = _Path(scratch) / "index.jsonl"
            records = sum(
                1 for line in index.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            live = len(list(second.store.documents()))
            mode_ok = index.stat().st_mode & 0o077 == 0
    except Exception as exc:  # noqa: BLE001 - an unmeasurable probe reports 0
        return 0.0, f"probe failed: {type(exc).__name__}: {exc}"

    if records != live:
        return 0.0, f"{records} record(s) on disk for {live} live document(s)"
    if not mode_ok:
        return 0.0, "compacted file is group/world readable"
    return 1.0, f"70 records compacted to {records}, permissions kept"


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
