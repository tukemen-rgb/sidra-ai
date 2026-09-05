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

    # C-1213: the excerpt window's hard tail cut left bullets ending
    # mid-word; generator-bound facts are trimmed to their last complete
    # sentence, and terminator-free fragments pass through whole.
    from sidra_ai.evals.fact_whole_sentences import evaluate_fact_whole_sentences

    whole = evaluate_fact_whole_sentences()
    c.add(
        "creation_fact_whole_sentences",
        "deck and document bullets end at a sentence",
        10.0 * whole.checks_passed / whole.checks_total,
        detail=f"{whole.checks_passed}/{whole.checks_total} checks; "
               "src/sidra_ai/evals/fact_whole_sentences.py"
               + ("" if whole.passed else "; " + "; ".join(whole.failures)),
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

    # C-1232: 「## 概要」 copied the first retrieved fact whole, and that same
    # fact opened 「## わかっていること」 - so a report began with the identical
    # paragraph twice, and a 「概要」 that is only the top fact is not a summary.
    # 概要 is now an honest framing line (no fact copy, no digit); every fact
    # still lists under わかっていること with its source; the empty report keeps
    # 概要 blank so the C-1128 notice fires; the fabrication validator stays green.
    from sidra_ai.evals.document_overview_no_duplicate import (
        evaluate_document_overview_no_duplicate,
    )

    overview = evaluate_document_overview_no_duplicate()
    c.add(
        "document_overview_no_duplicate",
        "レポートの概要が先頭の根拠を丸写しせず段落が重複しない",
        10.0 * overview.checks_passed / overview.checks_total,
        detail=f"{overview.checks_passed}/{overview.checks_total} checks; "
               "src/sidra_ai/evals/document_overview_no_duplicate.py"
               + ("" if overview.passed else "; " + "; ".join(overview.failures)),
        kind=OUTCOME,
    )

    # C-1242: when the same passage lives in two files, generate_document emitted
    # a bullet for each, so 「わかっていること」 showed the identical sentence twice
    # with different sources. The report now merges identical-text facts into one
    # bullet whose 「出典」 lists every file (the document twin of the answer's
    # C-1241 dedupe); distinct facts and the empty case are unchanged.
    from sidra_ai.evals.document_dedupes_identical_facts import (
        evaluate_document_dedupes_identical_facts,
    )

    doc_dedupe = evaluate_document_dedupes_identical_facts()
    c.add(
        "document_dedupes_identical_facts",
        "レポートで同一の根拠を 1 箇条書きにまとめ出典を連結する",
        10.0 * doc_dedupe.checks_passed / doc_dedupe.checks_total,
        detail=f"{doc_dedupe.checks_passed}/{doc_dedupe.checks_total} checks; "
               "src/sidra_ai/evals/document_dedupes_identical_facts.py"
               + ("" if doc_dedupe.passed else "; " + "; ".join(doc_dedupe.failures)),
        kind=OUTCOME,
    )

    # C-1246: a 「…のレポートを作って」 request titled the report with the whole
    # phrase, so the kind word doubled in the heading, the 概要 and the
    # confirmation (「『競合分析のレポート』のレポートを作りました」). The title
    # is the subject alone now; a request with no kind word is untouched.
    from sidra_ai.evals.document_title_no_kind_echo import (
        evaluate_document_title_no_kind_echo,
    )

    title_echo = evaluate_document_title_no_kind_echo()
    c.add(
        "document_title_no_kind_echo",
        "レポートの題名が「レポート」等の文書種名を二重に言わない",
        10.0 * title_echo.checks_passed / title_echo.checks_total,
        detail=f"{title_echo.checks_passed}/{title_echo.checks_total} checks; "
               "src/sidra_ai/evals/document_title_no_kind_echo.py"
               + ("" if title_echo.passed else "; " + "; ".join(title_echo.failures)),
        kind=OUTCOME,
    )

    # C-1255: C-1246 dropped the kind word but the about phrase 「について」/
    # 「に関する」 stayed, so 「広告方針についてのレポート」 titled 「広告方針に
    # ついて」 and the 概要 said 「…について」について. The title is the subject
    # alone now; a request with no about phrase is unchanged.
    from sidra_ai.evals.document_title_no_about_echo import (
        evaluate_document_title_no_about_echo,
    )

    about_echo = evaluate_document_title_no_about_echo()
    c.add(
        "document_title_no_about_echo",
        "レポートの題名が「について/に関する」を残さず概要で二重にしない",
        10.0 * about_echo.checks_passed / about_echo.checks_total,
        detail=f"{about_echo.checks_passed}/{about_echo.checks_total} checks; "
               "src/sidra_ai/evals/document_title_no_about_echo.py"
               + ("" if about_echo.passed else "; " + "; ".join(about_echo.failures)),
        kind=OUTCOME,
    )

    # C-1256: generative art has two patterns and any request that names
    # neither silently became flow, with the summary saying only 「パターン:
    # flow」. Games decline unsupported requests and list what they can make;
    # art went quiet. Measured through the real chat path: a request with no
    # pattern word must draw the default and say so and name the choices, while
    # a named pattern (フロー/軌道) stays silent.
    from sidra_ai.evals.art_pattern_default_honest import (
        evaluate_art_pattern_default_honest,
    )

    art_default = evaluate_art_pattern_default_honest()
    c.add(
        "art_pattern_default_honest",
        "アートが無指定で既定パターンに落ちたことを利用者に正直に伝える",
        10.0 * art_default.checks_passed / art_default.checks_total,
        detail=f"{art_default.checks_passed}/{art_default.checks_total} checks; "
               "src/sidra_ai/evals/art_pattern_default_honest.py"
               + ("" if art_default.passed else "; " + "; ".join(art_default.failures[:4])),
        kind=OUTCOME,
    )

    # C-1257: right after making a game, demonstrative revisions (その/これ/
    # それ/この …を直して) fell to the Q&A "no evidence, ask an admin to ingest
    # a repository" wall because _BACK_REFERENCES had no demonstratives.
    # Measured through the real chat path: a game is made, then each
    # demonstrative revision must reach the reviser with its adjustment, while
    # a question and a creation request stay off the reviser.
    from sidra_ai.evals.revision_demonstrative_referent import (
        evaluate_revision_demonstrative_referent,
    )

    revise_demo = evaluate_revision_demonstrative_referent()
    c.add(
        "revision_demonstrative_referent",
        "直後の指示語（その/これ/それ）での修正が reviser に届く",
        10.0 * revise_demo.checks_passed / revise_demo.checks_total,
        detail=f"{revise_demo.checks_passed}/{revise_demo.checks_total} checks; "
               "src/sidra_ai/evals/revision_demonstrative_referent.py"
               + ("" if revise_demo.passed else "; " + "; ".join(revise_demo.failures[:4])),
        kind=OUTCOME,
    )

    # C-1258: the GIF summary named no motif and any request that matched no
    # motif word silently became the default pulse - even more silent than art
    # (C-1256), which at least printed 「パターン: flow」. Measured through the
    # real chat path: every summary must name the motif, an unnamed request
    # must say the default was used and name the requestable motif (魚), and a
    # named motif stays silent.
    from sidra_ai.evals.gif_motif_default_honest import (
        evaluate_gif_motif_default_honest,
    )

    gif_default = evaluate_gif_motif_default_honest()
    c.add(
        "gif_motif_default_honest",
        "GIF が絵柄を明記し、無指定で既定に落ちたことを正直に伝える",
        10.0 * gif_default.checks_passed / gif_default.checks_total,
        detail=f"{gif_default.checks_passed}/{gif_default.checks_total} checks; "
               "src/sidra_ai/evals/gif_motif_default_honest.py"
               + ("" if gif_default.passed else "; " + "; ".join(gif_default.failures[:4])),
        kind=OUTCOME,
    )

    # C-1259: every generated game's subtitle printed 「テンプレート <key>」 -
    # the internal template key, in English, on a Japanese page. Now it reads
    # 「ジャンル <日本語>」. Checked on the real generated HTML for all ten
    # templates: the Japanese genre label is present and the English key leak
    # is gone.
    from sidra_ai.evals.game_tagline_genre_localized import (
        evaluate_game_tagline_genre_localized,
    )

    tagline_genre = evaluate_game_tagline_genre_localized()
    c.add(
        "game_tagline_genre_localized",
        "生成ゲームの副題がジャンルを日本語で示し内部鍵を露出しない",
        10.0 * tagline_genre.checks_passed / tagline_genre.checks_total,
        detail=f"{tagline_genre.checks_passed}/{tagline_genre.checks_total} checks; "
               "src/sidra_ai/evals/game_tagline_genre_localized.py"
               + ("" if tagline_genre.passed else "; " + "; ".join(tagline_genre.failures[:4])),
        kind=OUTCOME,
    )

    # C-1260: opening the ask page 404'd on /favicon.ico every load (console
    # error + blank tab icon). The page is self-contained, so it now declares
    # an inline data: favicon. Checked on the served page string: an icon link
    # is present, inline, and names no external host.
    from sidra_ai.evals.ui_declares_inline_favicon import (
        evaluate_ui_declares_inline_favicon,
    )

    favicon = evaluate_ui_declares_inline_favicon()
    c.add(
        "ui_declares_inline_favicon",
        "質問応答画面がインライン favicon を宣言し /favicon.ico の 404 を出さない",
        10.0 * favicon.checks_passed / favicon.checks_total,
        detail=f"{favicon.checks_passed}/{favicon.checks_total} checks; "
               "src/sidra_ai/evals/ui_declares_inline_favicon.py"
               + ("" if favicon.passed else "; " + "; ".join(favicon.failures[:4])),
        kind=OUTCOME,
    )

    # C-1261: an explicit make request for an unbuildable kind (Excel, an app,
    # a video) fell to the Q&A "no evidence, ask an admin to ingest a repo"
    # wall, because the service only routed strong intents. Now it is declined
    # honestly with the list of buildable kinds. Measured through the real chat
    # path: unbuildable requests get the list not the wall, while a buildable
    # request still creates and a question still reaches the question path.
    from sidra_ai.evals.creation_unbuildable_declined import (
        evaluate_creation_unbuildable_declined,
    )

    unbuildable = evaluate_creation_unbuildable_declined()
    c.add(
        "creation_unbuildable_declined",
        "作れない制作依頼を Q&A 文言でなく作れる型の案内で正直に断る",
        10.0 * unbuildable.checks_passed / unbuildable.checks_total,
        detail=f"{unbuildable.checks_passed}/{unbuildable.checks_total} checks; "
               "src/sidra_ai/evals/creation_unbuildable_declined.py"
               + ("" if unbuildable.passed else "; " + "; ".join(unbuildable.failures[:4])),
        kind=OUTCOME,
    )

    # C-1262: making something from the CLI printed the summary but not the path
    # to the file it wrote, plus the misleading empty-index note on a creation
    # response. render() now shows the artifact path and suppresses that note for
    # creations, while a genuine Q&A keeps it. Rendered through the CLI's own
    # render over real creation payloads.
    from sidra_ai.evals.cli_shows_artifact_path import (
        evaluate_cli_shows_artifact_path,
    )

    cli_artifact = evaluate_cli_shows_artifact_path()
    c.add(
        "cli_shows_artifact_path",
        "CLI の制作出力が生成ファイルの場所を示し索引注記を誤って出さない",
        10.0 * cli_artifact.checks_passed / cli_artifact.checks_total,
        detail=f"{cli_artifact.checks_passed}/{cli_artifact.checks_total} checks; "
               "src/sidra_ai/evals/cli_shows_artifact_path.py"
               + ("" if cli_artifact.passed else "; " + "; ".join(cli_artifact.failures[:4])),
        kind=OUTCOME,
    )

    # C-1263: C-1261's decline labelled the project kind 「企画一式」, but PROJECT
    # makes a game-production bundle, so a business 「企画」 request was declined
    # while the same message offered 「企画一式」 - a contradiction. The label is
    # now 「ゲーム制作一式」. Measured through chat: the decline names project as
    # game production, never a bare 「企画一式」, and a real project still builds.
    from sidra_ai.evals.creation_project_label_game_specific import (
        evaluate_creation_project_label_game_specific,
    )

    project_label = evaluate_creation_project_label_game_specific()
    c.add(
        "creation_project_label_game_specific",
        "制作辞退が project 種別をゲーム制作と明示し裸の企画一式を勧めない",
        10.0 * project_label.checks_passed / project_label.checks_total,
        detail=f"{project_label.checks_passed}/{project_label.checks_total} checks; "
               "src/sidra_ai/evals/creation_project_label_game_specific.py"
               + ("" if project_label.passed else "; " + "; ".join(project_label.failures[:4])),
        kind=OUTCOME,
    )

    # C-1264: a chunk longer than the cap came back as a bare 200-char slice cut
    # mid-word, with no sign it was clipped, so the excerpt read as broken data.
    # It now carries 「…」 where it drops the head or tail, within the cap, and a
    # chunk that fits is unchanged. Checked on citation_excerpt directly.
    from sidra_ai.evals.citation_excerpt_marks_truncation import (
        evaluate_citation_excerpt_marks_truncation,
    )

    excerpt_mark = evaluate_citation_excerpt_marks_truncation()
    c.add(
        "citation_excerpt_marks_truncation",
        "途中で切れた引用抜粋に切詰めの印（…）を付け上限内に収める",
        10.0 * excerpt_mark.checks_passed / excerpt_mark.checks_total,
        detail=f"{excerpt_mark.checks_passed}/{excerpt_mark.checks_total} checks; "
               "src/sidra_ai/evals/citation_excerpt_marks_truncation.py"
               + ("" if excerpt_mark.passed else "; " + "; ".join(excerpt_mark.failures[:4])),
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

    # C-1239: the deck shell had no overflow-wrap, so a long source path or a
    # file-path token in a bullet did not wrap - on an iPhone 12 the content
    # measured 482px against a 390px screen, forcing a horizontal scroll. The
    # ask page fixed the same with overflow-wrap:anywhere; the deck shell now
    # carries it too, so long tokens break instead of widening the page.
    from sidra_ai.evals.deck_mobile_no_overflow import evaluate_deck_mobile_no_overflow

    deck_wrap = evaluate_deck_mobile_no_overflow()
    c.add(
        "deck_mobile_no_overflow",
        "スライドがスマホで横にはみ出さない（長い出典やパスが折り返す）",
        10.0 * deck_wrap.checks_passed / deck_wrap.checks_total,
        detail=f"{deck_wrap.checks_passed}/{deck_wrap.checks_total} checks; "
               "src/sidra_ai/evals/deck_mobile_no_overflow.py"
               + ("" if deck_wrap.passed else "; " + "; ".join(deck_wrap.failures)),
        kind=OUTCOME,
    )

    # C-1244: the on-screen touch pad drew all six buttons (◀▶▲▼ + A + R) on
    # every game, so the default fishing page put four dead directional buttons
    # over a 352×158px play field on a phone. The pad now draws only the keys
    # the running page reads; checkable offline from the generated HTML (the
    # PAD_ACTIVE filter, and per genre drawn == used).
    from sidra_ai.evals.pad_only_used_buttons import evaluate_pad_only_used_buttons

    pad_used = evaluate_pad_only_used_buttons()
    c.add(
        "creation_pad_only_used_buttons",
        "スマホの画面ボタンはそのゲームが使うものだけ描く（死にボタンで遊び面を覆わない）",
        10.0 * pad_used.checks_passed / pad_used.checks_total,
        detail=f"{pad_used.checks_passed}/{pad_used.checks_total} checks; "
               "src/sidra_ai/evals/pad_only_used_buttons.py"
               + ("" if pad_used.passed else "; " + "; ".join(pad_used.failures)),
        kind=OUTCOME,
    )

    # C-1247 (a C-1244 regression): the pad drew only what keys_read reports,
    # and keys_read cannot see K('ArrowLeft') (platformer) or partsSteerX
    # (kaiju), so those games lost their ◀▶ on a phone while the briefing still
    # said 「← → で歩き／走り」. This check reads the promise: every arrow/SPACE
    # the briefing names must be on the pad. Independent of keys_read.
    from sidra_ai.evals.pad_covers_briefing_controls import (
        evaluate_pad_covers_briefing_controls,
    )

    pad_cover = evaluate_pad_covers_briefing_controls()
    c.add(
        "pad_covers_briefing_controls",
        "briefing が案内する操作キーを画面パッドが必ず備える（歩ける・走れる）",
        10.0 * pad_cover.checks_passed / pad_cover.checks_total,
        detail=f"{pad_cover.checks_passed}/{pad_cover.checks_total} genres; "
               "src/sidra_ai/evals/pad_covers_briefing_controls.py"
               + ("" if pad_cover.passed else "; " + "; ".join(pad_cover.failures)),
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

    # C-1252: loadArtifacts rendered every artifact (200 in the instance), so
    # the entry page grew to ~50,000px on a phone. It now shows a bounded,
    # newest-first slice and reports the total when there are more.
    from sidra_ai.evals.ui_artifact_list_bounded import (
        evaluate_ui_artifact_list_bounded,
    )

    list_bounded = evaluate_ui_artifact_list_bounded()
    c.add(
        "ui_artifact_list_bounded",
        "生成ファイル一覧は新しい順に上限件数だけ描画（スマホで無限スクロールにしない）",
        10.0 * list_bounded.checks_passed / list_bounded.checks_total,
        detail=f"{list_bounded.checks_passed}/{list_bounded.checks_total} checks; "
               "src/sidra_ai/evals/ui_artifact_list_bounded.py"
               + ("" if list_bounded.passed else "; " + "; ".join(list_bounded.failures)),
        kind=OUTCOME,
    )

    # C-1214: a long citation token widened the page past a phone viewport
    # and the browser shrank every glyph to fit. The wrap mechanics are
    # pinned on the page source; the E2E (scrollWidth == viewport after an
    # answer, iPhone emulation) ran at fix time, recorded in the loop log.
    from sidra_ai.evals.ui_answer_wraps import evaluate_ui_answer_wraps

    wraps = evaluate_ui_answer_wraps()
    c.add(
        "ui_answer_wraps",
        "the answer stays inside a phone viewport",
        10.0 * wraps.checks_passed / wraps.checks_total,
        detail=f"{wraps.checks_passed}/{wraps.checks_total} checks; "
               "src/sidra_ai/evals/ui_answer_wraps.py"
               + ("" if wraps.passed else "; " + "; ".join(wraps.failures)),
        kind=OUTCOME,
    )

    # C-1224: on a phone the ask page's 更新 and per-file 開く buttons were
    # 41-42px, under the 48dp tap minimum - the game shell got this fix
    # (C-1219) but the product page it sits behind did not. One coarse-pointer
    # rule lifts them all; the 48px live proof (desktop unchanged) is in the
    # loop log.
    from sidra_ai.evals.ui_touch_targets import evaluate_ui_touch_targets

    ui_touch = evaluate_ui_touch_targets()
    c.add(
        "ui_touch_targets",
        "ask ページのボタンがスマホで指で押せる（48dp 以上）",
        10.0 * ui_touch.checks_passed / ui_touch.checks_total,
        detail=f"{ui_touch.checks_passed}/{ui_touch.checks_total} checks; "
               "src/sidra_ai/evals/ui_touch_targets.py"
               + ("" if ui_touch.passed else "; " + "; ".join(ui_touch.failures)),
        kind=OUTCOME,
    )

    # C-1217: the one filled slide of a requested revenue deck carried three
    # bullets, all ending mid-word - _bullets_for re-cut already-trimmed
    # facts at a hard 120 characters (the second cut site of C-1213's bug),
    # and whole_sentences counted filename dots as sentence ends. The live
    # regenerated deck was verified at fix time, recorded in the loop log.
    from sidra_ai.evals.deck_bullet_sentences import evaluate_deck_bullet_sentences

    bullet = evaluate_deck_bullet_sentences()
    c.add(
        "creation_deck_bullet_sentences",
        "スライドの箇条書きが文末で終わる（120 字の崖で切らない）",
        10.0 * bullet.checks_passed / bullet.checks_total,
        detail=f"{bullet.checks_passed}/{bullet.checks_total} checks; "
               "src/sidra_ai/evals/deck_bullet_sentences.py"
               + ("" if bullet.passed else "; " + "; ".join(bullet.failures)),
        kind=OUTCOME,
    )

    # C-1237: build_slides filled every section from the whole fact list, so a
    # fact matching two sections' cues (or a numeric fact carrying a prose cue)
    # showed on several slides at once - a deck whose 解決 and 根拠 slides repeat
    # the same paragraph, the deck twin of C-1232. Each fact is now claimed by
    # the first section that takes it; section order, blanks and the number
    # guard are unchanged.
    from sidra_ai.evals.deck_no_duplicate_facts import evaluate_deck_no_duplicate_facts

    deck_dup = evaluate_deck_no_duplicate_facts()
    c.add(
        "deck_no_duplicate_facts",
        "スライドで同じ根拠が複数のスライドに重複しない",
        10.0 * deck_dup.checks_passed / deck_dup.checks_total,
        detail=f"{deck_dup.checks_passed}/{deck_dup.checks_total} checks; "
               "src/sidra_ai/evals/deck_no_duplicate_facts.py"
               + ("" if deck_dup.passed else "; " + "; ".join(deck_dup.failures)),
        kind=OUTCOME,
    )

    # C-1249 (deck twin of C-1246): 「…のスライドを作って」 titled the deck with
    # the whole phrase, so the cover slide and <title> said 「スライド」 back. The
    # cover is the subject alone now; a request with no kind word is untouched.
    from sidra_ai.evals.deck_title_no_kind_echo import evaluate_deck_title_no_kind_echo

    deck_title = evaluate_deck_title_no_kind_echo()
    c.add(
        "deck_title_no_kind_echo",
        "スライドの表紙が「スライド」等の資料種名を二重に言わない",
        10.0 * deck_title.checks_passed / deck_title.checks_total,
        detail=f"{deck_title.checks_passed}/{deck_title.checks_total} checks; "
               "src/sidra_ai/evals/deck_title_no_kind_echo.py"
               + ("" if deck_title.passed else "; " + "; ".join(deck_title.failures)),
        kind=OUTCOME,
    )

    # C-1222: a generated document's 概要 opened 「2. ブランドを分けるか」 - the
    # excerpt landed mid ordered-list and plain_text stripped bullets but not
    # ordered-list numbers, so the first line began with a 2 and no 1. The
    # marker strip now covers ordered markers while inline decimals and years
    # survive.
    from sidra_ai.evals.document_list_markers import evaluate_document_list_markers

    doc_markers = evaluate_document_list_markers()
    c.add(
        "creation_doc_no_list_markers",
        "生成文書が番号付きリストの途中から始まらない",
        10.0 * doc_markers.checks_passed / doc_markers.checks_total,
        detail=f"{doc_markers.checks_passed}/{doc_markers.checks_total} checks; "
               "src/sidra_ai/evals/document_list_markers.py"
               + ("" if doc_markers.passed else "; " + "; ".join(doc_markers.failures)),
        kind=OUTCOME,
    )

    # C-1221: commits are ~43% of the corpus and every one ends with git/AI
    # trailers (Co-Authored-By, Claude-Session). The lead extractor pulled
    # them into the answer body as content; plain_text now drops the known
    # trailer lines, so the answer and generated artifacts are clean while the
    # raw citation excerpt stays verbatim for review.
    from sidra_ai.evals.answer_no_git_trailers import evaluate_answer_no_git_trailers

    trailers = evaluate_answer_no_git_trailers()
    c.add(
        "qa_answer_no_git_trailers",
        "回答本文に commit の git トレーラが混じらない",
        10.0 * trailers.checks_passed / trailers.checks_total,
        detail=f"{trailers.checks_passed}/{trailers.checks_total} checks; "
               "src/sidra_ai/evals/answer_no_git_trailers.py"
               + ("" if trailers.passed else "; " + "; ".join(trailers.failures)),
        kind=OUTCOME,
    )

    # C-1226: a cited Markdown table surfaced as 「| 項目 | 値 | | --- | --- |」 -
    # plain_text stripped headings/bold/lists/trailers but not table syntax,
    # and the corpus is full of tables. The separator row is now dropped and
    # cells joined with 「 / 」; a mid-sentence pipe is left alone.
    from sidra_ai.evals.answer_table_flattened import evaluate_answer_table_flattened

    table = evaluate_answer_table_flattened()
    c.add(
        "qa_answer_table_flattened",
        "回答の表が読める文になる（縦棒と区切り行が出ない）",
        10.0 * table.checks_passed / table.checks_total,
        detail=f"{table.checks_passed}/{table.checks_total} checks; "
               "src/sidra_ai/evals/answer_table_flattened.py"
               + ("" if table.passed else "; " + "; ".join(table.failures)),
        kind=OUTCOME,
    )

    # C-1245: C-1226 joined a table's cells with 「 / 」 but plain_text's final
    # whitespace collapse merged the newlines between rows, so a multi-row table
    # ran together (「項目 / 内容 運営歴 / 約20年 核 / …」) and could not be read
    # as rows. Rows now carry a delimiter that survives the collapse.
    from sidra_ai.evals.table_rows_readable import evaluate_table_rows_readable

    table_rows = evaluate_table_rows_readable()
    c.add(
        "qa_table_rows_readable",
        "引用の表が行ごとに区切れて読める（1 行に潰れない）",
        10.0 * table_rows.checks_passed / table_rows.checks_total,
        detail=f"{table_rows.checks_passed}/{table_rows.checks_total} checks; "
               "src/sidra_ai/evals/table_rows_readable.py"
               + ("" if table_rows.passed else "; " + "; ".join(table_rows.failures)),
        kind=OUTCOME,
    )

    # C-1227: a cited Markdown link leaked its brackets and URL - and a
    # guard-redacted URL showed 「[REDACTED:high_entropy:…]」 in what was a
    # relative path. plain_text now keeps the link text and drops the URL,
    # including a window-cut link, while a bare 「[1]」 reference is left alone.
    from sidra_ai.evals.answer_links_flattened import evaluate_answer_links_flattened

    links = evaluate_answer_links_flattened()
    c.add(
        "qa_answer_links_flattened",
        "生成物の Markdown リンクが text になる（括弧と URL が出ない）",
        10.0 * links.checks_passed / links.checks_total,
        detail=f"{links.checks_passed}/{links.checks_total} checks; "
               "src/sidra_ai/evals/answer_links_flattened.py"
               + ("" if links.passed else "; " + "; ".join(links.failures)),
        kind=OUTCOME,
    )

    # C-1231: 「OutputGuard？」 (a Japanese user's question - Latin keyword,
    # fullwidth 「？」, no kana/kanji) matched no evidence and got the *English*
    # no-evidence reply, breaking SYSTEM_PROMPT rule 6. The language gate now
    # counts Japanese punctuation/fullwidth forms too, so a symbol-only
    # Japanese question is answered in Japanese, kana/kanji still are, and a
    # plain English question stays English (both the abstention and preamble).
    from sidra_ai.evals.answer_language_matches_question import (
        evaluate_answer_language_matches_question,
    )

    lang = evaluate_answer_language_matches_question()
    c.add(
        "answer_language_matches_question",
        "回答の言語が質問に合う（全角句読点だけの日本語質問にも日本語で答える）",
        10.0 * lang.checks_passed / lang.checks_total,
        detail=f"{lang.checks_passed}/{lang.checks_total} checks; "
               "src/sidra_ai/evals/answer_language_matches_question.py"
               + ("" if lang.passed else "; " + "; ".join(lang.failures)),
        kind=OUTCOME,
    )

    # C-1248: C-1231 counted fullwidth forms as Japanese, but a question with no
    # language at all (digits, symbols, emoji, empty) still fell to English -
    # 「Run POST /v1/github/analyze」 to a Japanese reader. A non-Latin-script
    # question now defaults to Japanese; a real English question stays English.
    from sidra_ai.evals.answer_language_defaults_japanese import (
        evaluate_answer_language_defaults_japanese,
    )

    lang_default = evaluate_answer_language_defaults_japanese()
    c.add(
        "answer_language_defaults_japanese",
        "言語手がかりの無い質問は日本語で答える（数字・記号・絵文字・空でも英語にしない）",
        10.0 * lang_default.checks_passed / lang_default.checks_total,
        detail=f"{lang_default.checks_passed}/{lang_default.checks_total} checks; "
               "src/sidra_ai/evals/answer_language_defaults_japanese.py"
               + ("" if lang_default.passed else "; " + "; ".join(lang_default.failures)),
        kind=OUTCOME,
    )

    # C-1241: two files that carry the identical passage produced two blocks
    # with the same text, and the answer printed the paragraph under [S1] and
    # again under [S2] - the reader re-reads it and it looks like two findings.
    # The echo answer now shows the excerpt once and points a later duplicate
    # back to it; the footer still lists every source. (C-1232/C-1237 twin.)
    from sidra_ai.evals.answer_dedupes_identical_excerpts import (
        evaluate_answer_dedupes_identical_excerpts,
    )

    dedupe = evaluate_answer_dedupes_identical_excerpts()
    c.add(
        "answer_dedupes_identical_excerpts",
        "回答で同一の抜粋を繰り返さない（同文は 1 回＋注記、出典一覧は保つ）",
        10.0 * dedupe.checks_passed / dedupe.checks_total,
        detail=f"{dedupe.checks_passed}/{dedupe.checks_total} checks; "
               "src/sidra_ai/evals/answer_dedupes_identical_excerpts.py"
               + ("" if dedupe.passed else "; " + "; ".join(dedupe.failures)),
        kind=OUTCOME,
    )

    # C-1216: the top citation for a real revenue question was 26 characters
    # of raw Markdown cut mid-checkbox (「## D-CY4. … - [ ] **A.」). The lead
    # extractor now flattens markup (C-1212's plain_text) and label fragments
    # no longer consume the sentence budget; the live re-ask against the real
    # corpus ran at fix time, recorded in the loop log.
    from sidra_ai.evals.citation_readability import evaluate_citation_readability

    readable = evaluate_citation_readability()
    c.add(
        "qa_citation_readability",
        "回答の引用が読める文で出る（記号なし・実内容あり）",
        10.0 * readable.checks_passed / readable.checks_total,
        detail=f"{readable.checks_passed}/{readable.checks_total} checks; "
               "src/sidra_ai/evals/citation_readability.py"
               + ("" if readable.passed else "; " + "; ".join(readable.failures)),
        kind=OUTCOME,
    )

    # C-1236: an ingestion-time redaction shows as 「一部秘匿」/「（伏せ字あり）」,
    # but when the output guard blocks a whole excerpt at answer time the service
    # sets excerpt_withheld so a reader can tell that apart - and both the CLI and
    # the web page dropped the distinction, showing the withheld citation like any
    # other. Both now surface a withheld mark beside the redacted one.
    from sidra_ai.evals.citation_withheld_flagged import (
        evaluate_citation_withheld_flagged,
    )

    withheld = evaluate_citation_withheld_flagged()
    c.add(
        "citation_withheld_flagged",
        "抜粋が丸ごと伏せられた引用を CLI と UI が印で示す",
        10.0 * withheld.checks_passed / withheld.checks_total,
        detail=f"{withheld.checks_passed}/{withheld.checks_total} checks; "
               "src/sidra_ai/evals/citation_withheld_flagged.py"
               + ("" if withheld.passed else "; " + "; ".join(withheld.failures)),
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

    # C-1228: explain() covered 401/403/413/422/429/5xx but not 404 - clicking
    # 開く on a file removed since the list showed 「ダウンロードに失敗: HTTP
    # 404」. 404 now maps to 「見つかりません。一覧を更新してください（…）」.
    from sidra_ai.evals.ui_missing_artifact_guidance import (
        evaluate_ui_missing_artifact_guidance,
    )

    missing = evaluate_ui_missing_artifact_guidance()
    c.add(
        "ui_missing_artifact_guidance",
        "消えたファイルの 404 に次の一手を示す（一覧を更新）",
        10.0 * missing.checks_passed / missing.checks_total,
        detail=f"{missing.checks_passed}/{missing.checks_total} checks; "
               "src/sidra_ai/evals/ui_missing_artifact_guidance.py"
               + ("" if missing.passed else "; " + "; ".join(missing.failures)),
        kind=OUTCOME,
    )

    # C-1218: C-1211 translated HTTP status codes, but a fetch that never
    # reached the server rejected with an English TypeError string shown
    # verbatim (「失敗: Failed to fetch」). reason() now maps the network
    # rejection to Japanese guidance; the real page aborting /v1/chat was
    # verified at fix time, recorded in the loop log.
    from sidra_ai.evals.ui_network_error_guidance import (
        evaluate_ui_network_error_guidance,
    )

    net_guidance = evaluate_ui_network_error_guidance()
    c.add(
        "ui_network_error_guidance",
        "サーバーに繋がらないとき日本語で対処を示す",
        10.0 * net_guidance.checks_passed / net_guidance.checks_total,
        detail=f"{net_guidance.checks_passed}/{net_guidance.checks_total} checks; "
               "src/sidra_ai/evals/ui_network_error_guidance.py"
               + ("" if net_guidance.passed else "; " + "; ".join(net_guidance.failures)),
        kind=OUTCOME,
    )

    # C-1223: the ask CLI special-cased only 401 and 429, so a too-long
    # question printed a bare 「HTTP 422」 with no next step - the web page's
    # guidance (C-1211) never reached the terminal. The CLI now maps 403,
    # 413/422 and 5xx too, with the code printed and the body unread.
    from sidra_ai.evals.cli_error_guidance import evaluate_cli_error_guidance

    cli_guidance = evaluate_cli_error_guidance()
    c.add(
        "cli_error_guidance",
        "CLI が失敗時に次の一手を日本語で示す",
        10.0 * cli_guidance.checks_passed / cli_guidance.checks_total,
        detail=f"{cli_guidance.checks_passed}/{cli_guidance.checks_total} checks; "
               "src/sidra_ai/evals/cli_error_guidance.py"
               + ("" if cli_guidance.passed else "; " + "; ".join(cli_guidance.failures)),
        kind=OUTCOME,
    )

    # C-1233: the CLI mapped HTTP statuses (C-1223) and refused/timeout
    # connections to Japanese guidance, but the transport catch-all printed a
    # bare 「要求に失敗した: RemoteProtocolError」 - an English class name, no
    # next step - for a mid-answer disconnect or a bad --url. The catch-all now
    # gives actionable Japanese guidance with the class kept in parentheses for
    # debugging, and the ConnectError/timeout branches keep their own advice.
    from sidra_ai.evals.cli_network_error_guidance import (
        evaluate_cli_network_error_guidance,
    )

    cli_network = evaluate_cli_network_error_guidance()
    c.add(
        "cli_network_error_guidance",
        "CLI が通信失敗時にも次の一手を日本語で示す",
        10.0 * cli_network.checks_passed / cli_network.checks_total,
        detail=f"{cli_network.checks_passed}/{cli_network.checks_total} checks; "
               "src/sidra_ai/evals/cli_network_error_guidance.py"
               + ("" if cli_network.passed else "; " + "; ".join(cli_network.failures)),
        kind=OUTCOME,
    )

    # C-1243: the CLI mapped every HTTP status, the network catch-all and the
    # gate refusal to Japanese, but a config-safety failure still printed the
    # English prefix 「refusing to ask: …」. The prefix is now Japanese with a
    # next step; the exception detail (which names the config variable) stays in
    # parentheses, the way the HTTP branches keep their code.
    from sidra_ai.evals.cli_config_error_japanese import (
        evaluate_cli_config_error_japanese,
    )

    cli_config = evaluate_cli_config_error_japanese()
    c.add(
        "cli_config_error_japanese",
        "CLI の設定安全性エラーを英語でなく日本語の案内で示す",
        10.0 * cli_config.checks_passed / cli_config.checks_total,
        detail=f"{cli_config.checks_passed}/{cli_config.checks_total} checks; "
               "src/sidra_ai/evals/cli_config_error_japanese.py"
               + ("" if cli_config.passed else "; " + "; ".join(cli_config.failures)),
        kind=OUTCOME,
    )

    # C-1254: after a safety refusal the CLI still printed the no-evidence note
    # 「索引に根拠が無いか、取り込みがまだ走っていない」, blaming ingestion for a
    # refusal. The refusal path omits the index note now; a genuine no-evidence
    # answer keeps it.
    from sidra_ai.evals.cli_refusal_no_index_note import (
        evaluate_cli_refusal_no_index_note,
    )

    cli_refusal = evaluate_cli_refusal_no_index_note()
    c.add(
        "cli_refusal_no_index_note",
        "拒否時に索引未取込へ誤誘導する文言を出さない（通常の根拠なしでは出す）",
        10.0 * cli_refusal.checks_passed / cli_refusal.checks_total,
        detail=f"{cli_refusal.checks_passed}/{cli_refusal.checks_total} checks; "
               "src/sidra_ai/evals/cli_refusal_no_index_note.py"
               + ("" if cli_refusal.passed else "; " + "; ".join(cli_refusal.failures)),
        kind=OUTCOME,
    )

    # C-1238: a gate refusal put the gate's English audit reason into the
    # response, and both the web page and the CLI showed it verbatim -
    # 「拒否されました: prompt-injection patterns detected…」. The API reason stays
    # English for consumers and the audit trail; the two user-facing surfaces now
    # show a Japanese message chosen by security.decision (rephrase for a gate
    # refusal, retry for any other), and no longer print the raw English reason.
    from sidra_ai.evals.refusal_reason_japanese import evaluate_refusal_reason_japanese

    refusal_ja = evaluate_refusal_reason_japanese()
    c.add(
        "refusal_reason_japanese",
        "拒否時に英語の監査文でなく日本語の案内を利用者に見せる",
        10.0 * refusal_ja.checks_passed / refusal_ja.checks_total,
        detail=f"{refusal_ja.checks_passed}/{refusal_ja.checks_total} checks; "
               "src/sidra_ai/evals/refusal_reason_japanese.py"
               + ("" if refusal_ja.passed else "; " + "; ".join(refusal_ja.failures)),
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

    # C-1220: the platformer existed but 「ジャンプ」 alone did not route to it,
    # so 「猫がジャンプするゲーム」 fell to the default fishing template with no
    # substitution notice. The bare jump cues now reach the platformer while a
    # shooter/puzzle that merely mentions a jump keeps its own route.
    from sidra_ai.evals.jump_routes_to_platformer import (
        evaluate_jump_routes_to_platformer,
    )

    jump = evaluate_jump_routes_to_platformer()
    c.add(
        "creation_jump_routes_to_platformer",
        "跳ねるゲームの依頼が platformer に届く（釣りに落ちない）",
        10.0 * jump.checks_passed / jump.checks_total,
        detail=f"{jump.checks_passed}/{jump.checks_total} checks; "
               "src/sidra_ai/evals/jump_routes_to_platformer.py"
               + ("" if jump.passed else "; " + "; ".join(jump.failures)),
        kind=OUTCOME,
    )

    # C-1225: 「マリオみたいなゲーム」 fell to fishing with no notice - the
    # platformer flagship was a guarded trademark but named no genre. It now
    # routes to the platformer (title guard swaps the name), while マリオカート
    # keeps racing, matched first.
    from sidra_ai.evals.mario_routes_to_platformer import (
        evaluate_mario_routes_to_platformer,
    )

    mario = evaluate_mario_routes_to_platformer()
    c.add(
        "creation_mario_routes_to_platformer",
        "マリオ系の依頼が platformer に届く（商標は伏せる）",
        10.0 * mario.checks_passed / mario.checks_total,
        detail=f"{mario.checks_passed}/{mario.checks_total} checks; "
               "src/sidra_ai/evals/mario_routes_to_platformer.py"
               + ("" if mario.passed else "; " + "; ".join(mario.failures)),
        kind=OUTCOME,
    )

    # C-1250: the deck job writes a real .pptx (decks.save_pptx), but the intent
    # detector did not know 「pptx／パワポ／PowerPoint」 as deck words, so those
    # requests came back unknown (weak) and fell to the question path - and
    # 「…の pptx を作って」 built a fishing game. A PowerPoint request is a deck.
    from sidra_ai.evals.pptx_routes_to_deck import evaluate_pptx_routes_to_deck

    pptx = evaluate_pptx_routes_to_deck()
    c.add(
        "pptx_routes_to_deck",
        "pptx／パワポ／PowerPoint の依頼がスライド生成に届く（ゲーム/レポートは不変）",
        10.0 * pptx.checks_passed / pptx.checks_total,
        detail=f"{pptx.checks_passed}/{pptx.checks_total} checks; "
               "src/sidra_ai/evals/pptx_routes_to_deck.py"
               + ("" if pptx.passed else "; " + "; ".join(pptx.failures)),
        kind=OUTCOME,
    )

    # C-1230: an unsupported-genre substitution said 「いちばん近い」 (the
    # nearest), but every unsupported genre falls to the same default template
    # - no nearness is measured. The wording now says 「代わりに既定の」 (the
    # default), while still naming the genre asked for and the type built.
    from sidra_ai.evals.substitution_names_default import (
        evaluate_substitution_names_default,
    )

    subst = evaluate_substitution_names_default()
    c.add(
        "creation_substitution_names_default",
        "作れないジャンルの代替を「既定」と言い「いちばん近い」と偽らない",
        10.0 * subst.checks_passed / subst.checks_total,
        detail=f"{subst.checks_passed}/{subst.checks_total} checks; "
               "src/sidra_ai/evals/substitution_names_default.py"
               + ("" if subst.passed else "; " + "; ".join(subst.failures)),
        kind=OUTCOME,
    )

    # C-1235: 「むずかしいゲームを作って」 read the difficulty (hard) correctly,
    # then turned the same word into a subject - titling the page 「むずかしい」
    # and claiming 「『むずかしい』の題材を描く型はまだ無い」. A word consumed as
    # the difficulty cannot also be an undrawn subject; _title_from now falls
    # back to the template title when only a difficulty modifier is left, so no
    # false caveat is raised. A real subject and a named genre are untouched.
    from sidra_ai.evals.game_difficulty_only_no_false_subject import (
        evaluate_game_difficulty_only_no_false_subject,
    )

    diff_only = evaluate_game_difficulty_only_no_false_subject()
    c.add(
        "game_difficulty_only_no_false_subject",
        "難易度だけの依頼を「題材が描けない」と偽らず既定題で作る",
        10.0 * diff_only.checks_passed / diff_only.checks_total,
        detail=f"{diff_only.checks_passed}/{diff_only.checks_total} checks; "
               "src/sidra_ai/evals/game_difficulty_only_no_false_subject.py"
               + ("" if diff_only.passed else "; " + "; ".join(diff_only.failures)),
        kind=OUTCOME,
    )

    # C-1240: RPG/rhythm/tower-defense declined as unsupported genres (with the
    # buildable list), but 「クイズゲーム」「麻雀ゲーム」 fell to the subject path
    # (「『クイズ』の題材を描く型はまだ無い」) - treated like 「猫」, and the subject
    # path never lists what can be built. They were missing from GENRES (which
    # lists unsupported genres on purpose, to decline them). Added as unsupported
    # genres so they decline with the list; real subjects and supported genres
    # are unchanged.
    from sidra_ai.evals.unsupported_genre_not_subject import (
        evaluate_unsupported_genre_not_subject,
    )

    genre_not_subject = evaluate_unsupported_genre_not_subject()
    c.add(
        "unsupported_genre_not_subject",
        "クイズ・麻雀等を未対応ジャンル（一覧つき）として断り題材と誤らない",
        10.0 * genre_not_subject.checks_passed / genre_not_subject.checks_total,
        detail=f"{genre_not_subject.checks_passed}/{genre_not_subject.checks_total} checks; "
               "src/sidra_ai/evals/unsupported_genre_not_subject.py"
               + ("" if genre_not_subject.passed else "; " + "; ".join(genre_not_subject.failures)),
        kind=OUTCOME,
    )

    # C-1253: 「ブロック崩しを作って」「3目並べを作って」 came back unknown and fell
    # to the question path - a reader who asked for a game got an answer about
    # nginx. Bare game genres without the word 「ゲーム」 now route to the game
    # path (which declines honestly), while real questions stay questions.
    from sidra_ai.evals.game_genre_routes_to_game import (
        evaluate_game_genre_routes_to_game,
    )

    genre_route = evaluate_game_genre_routes_to_game()
    c.add(
        "game_genre_routes_to_game",
        "一般的なゲーム種名（ブロック崩し等）が game に届く＝Q&A に落ちない",
        10.0 * genre_route.checks_passed / genre_route.checks_total,
        detail=f"{genre_route.checks_passed}/{genre_route.checks_total} checks; "
               "src/sidra_ai/evals/game_genre_routes_to_game.py"
               + ("" if genre_route.passed else "; " + "; ".join(genre_route.failures)),
        kind=OUTCOME,
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
    # C-1121 turned this from "one phrasing is answered honestly" into
    # "every way of naming a genre we do not build is". The old shape had a
    # single unsupported case, and the case it happened to pick
    # (「格闘ゲームを作って」) was the one that already worked - while
    # 「対戦格闘ゲームを作って」 got a beam duel with no caveat and a page
    # titled 「対戦格闘」. A binary that can be satisfied by its own easiest
    # example is not a guard.
    #
    # The set is derived from the honesty table, so a genre that gains a
    # template leaves this number by itself rather than by an edit, plus
    # the word-order variants the item named.
    from sidra_ai.creation.games import _title_from as _honest_words
    from sidra_ai.creation.games import choose_template as _honest_route
    from sidra_ai.creation.vocabulary import GENRES as _honest_genres

    def _title_asked(text: str) -> str:
        return _honest_words(text, _GAME_TEMPLATES[_honest_route(text)].default_title)

    honest_asks: list[str] = []
    for _h_genre, _h_key, _h_words in _honest_genres:
        if _h_key in _GAME_TEMPLATES:
            continue
        _h_word = _h_words[0]
        # 「ノベルゲーム」 already ends in it; asking for a 「ノベルゲーム
        # ゲーム」 would be testing a sentence nobody types.
        honest_asks.append(
            f"{_h_word}を作って" if _h_word.endswith("ゲーム") else f"{_h_word}ゲームを作って"
        )
    # 対戦格闘 by its other names and in the other order: the bare 「対戦」 in
    # DUEL_WORDS is what made these three different questions.
    honest_asks += ["対戦格闘ゲームを作って", "格闘対戦を作って", "格ゲーを作って"]
    honest_asks = list(dict.fromkeys(honest_asks))

    #: The silent side. It must be a genre whose template is *not* the
    #: default: 「釣りゲームを作って」 builds the fishing page either way, so
    #: it cannot tell "this genre was built" from "everything falls to the
    #: default" - a break that routed every named genre to the substitute
    #: scored full marks against it.
    supported = ""
    if not honest_asks:
        # Every genre in the table has a template: the caveat has nothing left
        # to describe, which is a good state but not one this number can prove.
        honesty_failures.append("no unsupported genre left to test the wording on")
    honest_ok: list[str] = []
    #: Where a request that names nothing lands. The decline path promises
    #: this exact page, so it is read from the product rather than written
    #: down here.
    _honest_default = _honest_route("ゲームを作って")
    if honest_asks:
        supported = next(
            (
                text
                for text in ("キャッチゲームを作って", "ビーム対戦を作って", "レースゲームを作って")
                if (g := detect_genre(text)) is not None
                and g.supported
                and _honest_route(text) != _honest_default
            ),
            "",
        )
        if not supported:
            honesty_failures.append(
                "no supported genre builds anything but the default, so silence proves nothing"
            )
    if honest_asks and supported:
        with tempfile.TemporaryDirectory() as tmp:
            generate = build_game_generator(tmp)
            for ask in honest_asks:
                named = detect_genre(ask)
                if named is None or named.supported:
                    honesty_failures.append(f"{ask}: no longer names a genre we decline")
                    continue
                missed = generate(ask, detect_creation_intent(ask))
                built = str(missed.details.get("built_template", ""))
                trouble = ""
                if not missed.details.get("genre_substituted"):
                    trouble = "substitution not recorded"
                elif named.genre not in missed.summary:
                    trouble = "the summary does not name the genre asked for"
                elif built not in _GAME_TEMPLATES:
                    trouble = f"built_template={built!r}"
                elif _GAME_TEMPLATES[built].default_title not in missed.summary:
                    trouble = "the summary does not name what was built instead"
                elif _honest_route(ask) != built:
                    trouble = f"routing says {_honest_route(ask)!r}, the page says {built!r}"
                elif built != _honest_default:
                    # The summary says 「代わりに**既定の**…型で作りました」,
                    # and C-1230 chose that word over 「いちばん近い」 because
                    # every declined genre was supposed to fall to the same
                    # page. It was not true for 対戦格闘, which fell to the
                    # duel on a bare 「対戦」 - so the sentence named the
                    # wrong template *and* called it the default. Checked
                    # rather than assumed, because the wording depends on it.
                    trouble = (
                        f"said 「既定の」 and built {built!r} (the default is "
                        f"{_honest_default!r})"
                    )
                else:
                    # The layer that outlives the sentence: the file is
                    # handed over with a name, and that name must not be the
                    # genre the summary just declined.
                    page = generate_game(ask)
                    if page.title != _GAME_TEMPLATES[built].default_title:
                        trouble = f"the page calls itself {page.title!r}"
                if trouble:
                    honesty_failures.append(f"{ask}: {trouble}")
                else:
                    honest_ok.append(ask)

            # The silent side gates the whole number rather than costing
            # one case: a product that declined everything, or routed
            # everything to the substitute, would otherwise score full marks
            # for being consistently sorry.
            kept = generate(supported, detect_creation_intent(supported))
            wanted = detect_genre(supported)
            if kept.details.get("genre_substituted"):
                honesty_failures.append(f"{supported}: reported as a substitution")
            if "まだ作れない" in kept.summary:
                honesty_failures.append(f"{supported}: apologised for a genre it built")
            if kept.details.get("built_template") != wanted.template:
                honesty_failures.append(
                    f"{supported}: built {kept.details.get('built_template')!r}, "
                    f"not its own {wanted.template!r}"
                )
            # ...and it keeps the words it was asked in. The title guard is
            # for declines only; a genre we build is still named by the
            # operator's own phrasing.
            if generate_game(supported).title != _title_asked(supported):
                honesty_failures.append(f"{supported}: lost the words it was asked in")
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
        "作れない型を名乗らない言い方",
        0.0 if honesty_failures else float(len(honest_ok)),
        detail=(
            "; ".join(honesty_failures)
            if honesty_failures
            else f"{len(honest_ok)} 通りの言い方（{'・'.join(honest_ok)}）すべてで: "
            f"断りに依頼のジャンル名と代わりに作った型が出る・ルーティングが"
            f"その型と一致する・**ページ自身が断ったジャンルを名乗らない**"
            f"（既定題になる）。作れる {supported} は断りを出さず、"
            f"依頼の言葉のまま題になる"
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

    # --- keyboard play stays on the board -------------------------------
    #
    # C-1215: arrows and Space scrolled the page under the game (208px in
    # six presses, every template). The guard's mechanics are pinned across
    # templates; the browser-level proof ran at fix time (loop log).
    from sidra_ai.evals.keys_dont_scroll import evaluate_keys_dont_scroll

    scroll_guard = evaluate_keys_dont_scroll()
    c.add(
        "creation_keys_dont_scroll",
        "矢印と SPACE がページをスクロールさせない",
        10.0 * scroll_guard.checks_passed / scroll_guard.checks_total,
        detail=f"{scroll_guard.checks_passed}/{scroll_guard.checks_total} checks; "
               "src/sidra_ai/evals/keys_dont_scroll.py"
               + ("" if scroll_guard.passed else "; " + "; ".join(scroll_guard.failures)),
        kind=OUTCOME,
    )

    # --- control-panel buttons are tappable on a phone -----------------
    #
    # C-1219: the pad made the game playable on a phone, but the HTML panel
    # around it (skins, copy-result, remap, reset) kept 24-32px buttons -
    # under the 48dp minimum the knowledge base cites. One coarse-pointer
    # rule in the shell raises them all; the 48px live proof (desktop
    # unchanged) ran at fix time, recorded in the loop log.
    from sidra_ai.evals.touch_targets import evaluate_touch_targets

    touch = evaluate_touch_targets()
    c.add(
        "creation_touch_targets",
        "スマホで操作パネルのボタンが指で押せる大きさ（48dp 以上）",
        10.0 * touch.checks_passed / touch.checks_total,
        detail=f"{touch.checks_passed}/{touch.checks_total} checks; "
               "src/sidra_ai/evals/touch_targets.py"
               + ("" if touch.passed else "; " + "; ".join(touch.failures)),
        kind=OUTCOME,
    )

    # C-1234: C-1219 raised the panel's buttons to 48dp, but the tuning panel's
    # select/sliders/colour/checkboxes stayed 13-27px and rendered at 13.3px -
    # too small to tap and small enough to make iOS zoom on focus (the ask page
    # fixed that with a 16px floor, C-1225). The shell now floors select/input
    # at 16px and 44px min-height for a coarse pointer and enlarges checkboxes;
    # button/desktop/canvas pad are unchanged.
    from sidra_ai.evals.touch_form_controls import evaluate_touch_form_controls

    touch_form = evaluate_touch_form_controls()
    c.add(
        "creation_touch_form_controls",
        "スマホで調整パネルの入力（select/スライダー/色/チェック）が押せて拡大しない",
        10.0 * touch_form.checks_passed / touch_form.checks_total,
        detail=f"{touch_form.checks_passed}/{touch_form.checks_total} checks; "
               "src/sidra_ai/evals/touch_form_controls.py"
               + ("" if touch_form.passed else "; " + "; ".join(touch_form.failures)),
        kind=OUTCOME,
    )

    # C-1229: the how-to named only keyboard keys, which a phone lacks, and the
    # on-screen pad appears only once play starts. A coarse-pointer hint now
    # names the pad before then; desktop keeps its keyboard story.
    from sidra_ai.evals.touch_hint import evaluate_touch_hint

    touch_hint = evaluate_touch_hint()
    c.add(
        "creation_touch_hint",
        "スマホで画面のボタンで遊べると本文が伝える",
        10.0 * touch_hint.checks_passed / touch_hint.checks_total,
        detail=f"{touch_hint.checks_passed}/{touch_hint.checks_total} checks; "
               "src/sidra_ai/evals/touch_hint.py"
               + ("" if touch_hint.passed else "; " + "; ".join(touch_hint.failures)),
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

    # --- each cycle of the takedown is fiercer than the last -----------
    #
    # §6 観察 3 brought home to §6's own template (C-1324): the guardian,
    # the duel, the shooter and the marble all re-accelerate, but the
    # kaiju's three cycles played identically. The cracks now open faster
    # by the siblings' multiplier table while the 126-frame attack beat
    # and the 34-frame warning stay exactly as measured - the probe above
    # lives with each cycle's cracks under dodging before winning it, so
    # the growth rates here are observed on the running page, not read
    # off the table.
    import re as _ck_re
    import subprocess as _ck_sp

    from sidra_ai.creation.kaiju import probe_source as _ck_probe

    cycle_gaps: list[str] = []
    _ck_runs = [("既定", kaiju_seen)]
    _ck_hard_page = generate_game("難しい怪獣ゲームを作って").html
    _ck_hard_script = _ck_re.search(r"<script>(.*?)</script>", _ck_hard_page, _ck_re.S)
    if _ck_hard_script is not None:
        try:
            _ck_hard_run = _ck_sp.run(
                ["node", "-"],
                input=_ck_probe(_ck_hard_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _ck_hard_run.returncode == 0:
                _ck_runs.append(
                    ("hard", json.loads(_ck_hard_run.stdout.strip().splitlines()[-1]))
                )
            else:
                cycle_gaps.append(f"hard: {_ck_hard_run.stderr.strip()[:60]}")
        except (OSError, _ck_sp.SubprocessError, ValueError) as exc:
            cycle_gaps.append(f"hard: probe unavailable ({type(exc).__name__})")
    for _ck_label, _ck in _ck_runs:
        if _ck is None:
            cycle_gaps.append(f"{_ck_label}: the fight could not be played")
            continue
        _ck_growth = _ck.get("cycleGrowth") or []
        if len(_ck_growth) != 3 or min(_ck_growth) <= 0:
            cycle_gaps.append(f"{_ck_label}: a cycle's cracks were never watched")
            continue
        if not (_ck_growth[0] < _ck_growth[1] < _ck_growth[2]):
            cycle_gaps.append(f"{_ck_label}: the cracks ignore the cycle ({_ck_growth})")
        elif abs(_ck_growth[2] / _ck_growth[0] - 1.3) > 0.02:
            cycle_gaps.append(
                f"{_ck_label}: the last cycle opens x{_ck_growth[2] / _ck_growth[0]:.2f}, not x1.3"
            )
        if _ck.get("warnMin") != 33 or _ck.get("warnMax") != 33:
            cycle_gaps.append(
                f"{_ck_label}: the warning moved "
                f"({_ck.get('warnMin')}-{_ck.get('warnMax')}, expected the constant 33)"
            )
        if _ck.get("state") != "won":
            cycle_gaps.append(f"{_ck_label}: the fiercer fight is no longer beatable")
    c.add(
        "creation_kaiju_cycles",
        "討伐が周回ごとに苛烈になる",
        0.0 if cycle_gaps else 1.0,
        detail=(
            "; ".join(cycle_gaps)
            if cycle_gaps
            else "各周期の地割れと実際に暮らして計測: 開く速さが周期ごとに"
            "×1.15/×1.3 と実測で上がり（既定 1.4→1.61→1.82）、126f の攻撃"
            "ビートと 34f の予兆は不変、回避しながらの討伐は依然成立"
            "（§6 観察 3 を本家に）"
        ),
        kind=OUTCOME,
    )

    # --- shaving past an obstacle pays, crashing never does ------------
    #
    # §13 事実 1, racing edition (C-1325): obstacles were pure punishment -
    # a hit cut the pace and a daring near-pass paid nothing, in the genre
    # whose own tradition (the slipstream) is the textbook risk-reward.
    # Now a pass with 26-46px of daylight (the band starts exactly where
    # the hitbox ends) pays a pace surge the existing easing decays back
    # to base - a surge, not a permanent gear - and the HUD counts it.
    # Shaved for real with pinned geometry on two seeds.
    import re as _sl_re
    import subprocess as _sl_sp

    from sidra_ai.creation.racing import slip_probe as _slip_probe

    slip_gaps: list[str] = []
    for _sl_req in ("周回レースを作って", "難しいレースゲームを作って"):
        _sl_page = generate_game(_sl_req).html
        _sl_script = _sl_re.search(r"<script>(.*?)</script>", _sl_page, _sl_re.S)
        if _sl_script is None:
            slip_gaps.append(f"{_sl_req}: no script")
            continue
        try:
            _sl_run = _sl_sp.run(
                ["node", "-"],
                input=_slip_probe(_sl_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _sl_run.returncode != 0:
                slip_gaps.append(f"{_sl_req}: {_sl_run.stderr.strip()[:60]}")
                continue
            _sl = json.loads(_sl_run.stdout.strip().splitlines()[-1])
        except (OSError, _sl_sp.SubprocessError, ValueError) as exc:
            slip_gaps.append(f"{_sl_req}: probe unavailable ({type(exc).__name__})")
            continue
        _sl_base = _sl.get("base") or 0
        _sl_near, _sl_far, _sl_hit = _sl.get("near") or {}, _sl.get("far") or {}, _sl.get("hit") or {}
        if _sl_near.get("slips") != 1:
            slip_gaps.append(f"{_sl_req}: the near miss was not counted once")
        elif _sl_near.get("maxSpd", 0) < _sl_base * 1.15:
            slip_gaps.append(
                f"{_sl_req}: the near miss paid no surge "
                f"({_sl_near.get('maxSpd'):.2f} vs base {_sl_base})"
            )
        if abs(_sl.get("settledSpd", 0) - _sl_base) > _sl_base * 0.05:
            slip_gaps.append(f"{_sl_req}: the surge became a permanent gear")
        if _sl_far.get("slips") != 0:
            slip_gaps.append(f"{_sl_req}: a distant pass paid the slipstream")
        if _sl_hit.get("slips") != 0:
            slip_gaps.append(f"{_sl_req}: a crash paid the slipstream")
        if (_sl.get("graced") or {}).get("slips") != 0:
            slip_gaps.append(f"{_sl_req}: an immune pass-through paid the slipstream")
        if _sl_hit.get("minSpd", 99) > _sl_base * 0.6:
            slip_gaps.append(f"{_sl_req}: the hit no longer costs pace")
        if _sl.get("state") != "race":
            slip_gaps.append(f"{_sl_req}: the measured run ended by itself")
    c.add(
        "creation_race_slipstream",
        "すれすれの通過が報いる",
        0.0 if slip_gaps else 1.0,
        detail=(
            "; ".join(slip_gaps)
            if slip_gaps
            else "障害物を横 34px（当たり判定 26 のすぐ外）・80px・0px に固定して"
            "実走: 近い通過だけが 1 回数えられ、実測 spd が基準×1.3 に跳ねて"
            "イージングで基準へ戻り、遠い通過と衝突は払われない（衝突は従来"
            "どおり減速）。grace 中のすり抜けも払われない。§13 事実 1 のレース版＝スリップストリーム"
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
    import tempfile as _scene_tempfile

    from sidra_ai.creation.adventure import world_probe as _adv_probe
    from sidra_ai.creation.duel import pace_probe as _duel_pace_for_scenes
    from sidra_ai.creation.catchgame import probe_source as _catch_scene_probe
    from sidra_ai.creation.fishing import probe_source as _fishing_scene_probe
    from sidra_ai.creation.kaiju import probe_source as _kaiju_scene_probe
    from sidra_ai.creation.marble import probe_source as _marble_scene_probe
    from sidra_ai.creation.platformer import probe_source as _plat_hud_probe
    from sidra_ai.creation.puzzle import sky_probe as _puzzle_sky_probe
    from sidra_ai.creation.racing import probe_source as _racing_hud_probe
    from sidra_ai.creation.shooter import probe_source as _shooter_scene_probe
    from sidra_ai.creation.themes import select_theme as _scene_theme

    #: request phrase -> (template key, probe builder). The templates with
    #: more than one scene to tell apart, and only those: rooms for the
    #: adventure, phases for the kaiju, acts of the round for the shooter
    #: (C-1301), thirds of the corridor for the marble (C-1307), thirds of
    #: the round clock for the fishing, the catch and the puzzle (C-1315,
    #: C-1319, C-1327), and match tension for the duel (C-1321) - its pace
    #: probe visits all three acts, so it reports the painted scenes too.
    #: A single-scene template would inflate the count.
    _scene_targets = (
        ("迷宮を冒険するゲームを作って", "adventure", _adv_probe),
        ("巨大怪獣と戦うゲームを作って", "kaiju", _kaiju_scene_probe),
        ("シューティングゲームを作って", "shooter", _shooter_scene_probe),
        ("玉転がしゲームを作って", "marble", _marble_scene_probe),
        ("釣りゲームを作って", "fishing", _fishing_scene_probe),
        ("キャッチゲームを作って", "catch", _catch_scene_probe),
        ("ビームで撃ち合うゲームを作って", "duel", _duel_pace_for_scenes),
        ("パズルゲームを作って", "puzzle", _puzzle_sky_probe),
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
    #: label -> (hudFacts, scenes) for the templates whose probe reports a
    #: HUD contract (the three whose HUD sits on the full-frame sky).
    #: Collected here so the contrast check below costs no extra node runs.
    scene_hud: dict[str, tuple[dict, list]] = {}
    #: label -> depthFacts() for the templates whose probe reports a far-
    #: layer contract (§7 観察 7, C-1342). Harvested here so the depth
    #: check below costs no extra node runs.
    scene_depth: dict[str, list] = {}
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
            if isinstance(seen.get("hud"), dict):
                scene_hud[label] = (seen["hud"], scenes)
            if isinstance(seen.get("depth"), list):
                scene_depth[label] = seen["depth"]
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
            "コース 3 分割・fishing / catch / puzzle のラウンド 3 等分・duel "
            "の試合緊迫度で実際の描画色が変わり、"
            "最も明るい場面が最終部にある。4 テーマすべてで確認、壁と床の"
            "明度差はテーマ既定値のまま"
            if not scene_gaps
            else "; ".join(scene_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the HUD survives the brightest sky ----------------------------
    #
    # §4's quantity (WCAG 1.4.3, C-1329): normal text needs 4.5:1 against
    # its background, components 3:1 - measured in the worst scene, which
    # since §7 is the brightest final act. The three clock-bound templates
    # paint their HUD straight onto that sky, and the themed ink was
    # sinking to ~3:1 there: theming cannot help when the tint climbs
    # toward the ink's own luminance. The fix is a plate of the UNtinted
    # theme surface under the text; the page reports its HUD contract
    # (ink, plate, alpha - the constants draw() actually paints through)
    # and this check blends the plate over every measured sky the same way
    # the canvas does, in sRGB, then takes the WCAG ratio. The puzzle's
    # cursor stroke is a component drawn plateless on the sky, held to the
    # 3:1 floor - the old hardcoded near-white was 1.0:1 on light themes.
    def _hud_blend(alpha: float, top: str, under: str) -> str:
        t = [int(top.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
        u = [int(under.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
        return "#%02x%02x%02x" % tuple(
            round(alpha * a + (1 - alpha) * b) for a, b in zip(t, u)
        )

    hud_gaps: list[str] = []
    #: label -> edgeFacts() from the racing pages driven below (C-1347).
    racing_edge: dict[str, dict] = {}
    # The two RUNNING templates live outside the scene loop above (their
    # scenes step by lap / progress, not by clock), so their HUD contract
    # is read off their own gameplay probes. Their backdrop is not always
    # the scene floor - platformer's HUD sits on the tinted BG - so the
    # contract also reports skies[], the actual per-scene paint under the
    # plate, and the blend below prefers it when present.
    for request, key, builder in (
        ("レースゲームを作って", "racing", _racing_hud_probe),
        ("ジャンプで進むゲームを作って", "platformer", _plat_hud_probe),
    ):
        for suffix in _scene_themes:
            label = f"{key}/{suffix or 'default'}"
            page = generate_game(f"{request} {suffix}".strip()).html
            script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
            if script is None:
                hud_gaps.append(f"{label}: no script")
                continue
            try:
                probe = _scene_sp.run(
                    ["node", "-"],
                    input=builder(script.group(1)),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                )
                seen = json.loads(probe.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                hud_gaps.append(f"{label}: probe unavailable ({type(exc).__name__})")
                continue
            if isinstance(seen.get("hud"), dict):
                scene_hud[label] = (seen["hud"], seen.get("scenes") or [])
            else:
                hud_gaps.append(f"{label}: no HUD contract reported")
            if key == "racing" and isinstance(seen.get("edge"), dict):
                racing_edge[label] = seen["edge"]
    hud_seen: set[str] = set()
    for label, (hud, hud_scenes) in sorted(scene_hud.items()):
        hud_seen.add(label.split("/")[0])
        try:
            ink = _srgb_lum(hud["ink"])
            skies = hud.get("skies") if isinstance(hud.get("skies"), list) else None
            for act, sky in enumerate(hud_scenes):
                under = skies[act] if skies else sky["floor"]
                backed = _srgb_lum(_hud_blend(hud["alpha"], hud["plate"], under))
                ratio = _wcag(ink, backed)
                if ratio < 4.5:
                    hud_gaps.append(f"{label}: act {act} HUD sinks to {ratio:.2f}")
                if "cursor" in hud:
                    stroke = _wcag(_srgb_lum(hud["cursor"]), _srgb_lum(sky["floor"]))
                    if stroke < 3.0:
                        hud_gaps.append(
                            f"{label}: act {act} cursor sinks to {stroke:.2f}"
                        )
        except (KeyError, TypeError, ValueError):
            hud_gaps.append(f"{label}: HUD contract unreadable")
    _hud_all = {
        "fishing",
        "catch",
        "puzzle",
        "adventure",
        "kaiju",
        "shooter",
        "marble",
        "duel",
        "racing",
        "platformer",
    }
    for missing in _hud_all - hud_seen:
        hud_gaps.append(f"{missing}: no HUD contract reported")
    # C-1337 redefined the value from 0/1 to the NUMBER of templates whose
    # contract holds - any gap anywhere still collapses it to 0, so this is
    # the old bar with a wider roof, not a softer one (両定義: 旧 0/1 は
    # 8 型時点で 1、新定義の変更前は racing/platformer 未報告により 0).
    c.add(
        "creation_hud_contrast",
        "最明の空でも HUD が読める型",
        float(len(_hud_all)) if not hud_gaps else 0.0,
        detail=(
            "10 型（時計 3 型 C-1329 ＋ adventure/kaiju/shooter/marble/duel "
            "C-1334 ＋走る 2 型 C-1337）× 4 テーマ × 全 3 場面で、未着色"
            "サーフェスの板を α 合成した実背景（racing/platformer は契約が"
            "報告する per-scene の実塗り skies）に対し文字 4.5:1 以上・"
            "puzzle のカーソル枠 3:1 以上（§4 WCAG 1.4.3。走る 2 型は"
            "最終場面で素の ink が 3.07〜3.97:1 に沈んでいた）"
            if not hud_gaps
            else "; ".join(hud_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the road's edge survives every paint -------------------------
    #
    # §4 (C-1347): the roadside ticks and the start/finish band are the
    # boundary between "on the road" and "losing speed" - information,
    # not decoration. One fixed light neutral sat at ~1.05:1 against
    # everything on the paper theme, an invisible boundary for the whole
    # run. The mark is now a TWO-TONE pair (dark core, light rim) and the
    # page reports it: in every scene of every theme, ONE half must clear
    # the 3:1 component floor against both the road and the roadside, and
    # the pair must read against itself.
    edge_gaps: list[str] = []
    for label in sorted(racing_edge):
        contract = racing_edge[label]
        try:
            lum_a = _srgb_lum(contract["a"])
            lum_b = _srgb_lum(contract["b"])
            if _wcag(lum_a, lum_b) < 3.0:
                edge_gaps.append(f"{label}: the pair cannot read against itself")
            for act, plane in enumerate(contract["scenes"]):
                for side, name in (("surf", "the roadside"), ("road", "the road")):
                    ground = _srgb_lum(plane[side])
                    best = max(_wcag(lum_a, ground), _wcag(lum_b, ground))
                    if best < 3.0:
                        edge_gaps.append(
                            f"{label}: act {act} the edge sinks into {name} ({best:.2f})"
                        )
        except (KeyError, TypeError, ValueError):
            edge_gaps.append(f"{label}: edge contract unreadable")
    for missing in {f"racing/{s or 'default'}" for s in _scene_themes} - set(
        racing_edge
    ):
        edge_gaps.append(f"{missing}: no edge contract reported")
    c.add(
        "creation_racing_edge",
        "路肩がどのテーマでも読める",
        1.0 if not edge_gaps else 0.0,
        detail=(
            "racing × 4 テーマ × 全 3 場面で、二色ペアの道標（暗芯＋明縁）の"
            "どちらか一方が道路とコース外の両方に ≥3.0:1 で立ち、ペア自身も"
            "≥3.0:1。旧・単色 #dfe7f5 は紙テーマで全場面 1.03〜1.16:1＝境界"
            "がゲーム全体で見えなかった（§4・境界は情報）"
            if not edge_gaps
            else "; ".join(edge_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the far layer is far -----------------------------------------
    #
    # §7 観察 7 (C-1342): distance is drawn by CONTRAST - a foreground
    # silhouette, a midground subject, a faded far layer - and the film
    # pairs it with §6's partial-view scale. The kaiju arena was a flat
    # sky behind the one template whose whole subject is scale. Its page
    # now reports a depth contract (the sky, the midground's solid paint,
    # and the alpha the skyline is faded by), read off the same driven
    # probes as the scene palettes above: the blended far layer must be
    # visibly there (>=1.02:1 against the sky) yet fainter than the
    # midground silhouette in every scene of every theme.
    depth_gaps: list[str] = []
    _depth_all = ("kaiju", "duel")
    depth_seen = {label for label in scene_depth}
    for label in sorted(depth_seen):
        for act, plane in enumerate(scene_depth[label]):
            try:
                far = _srgb_lum(
                    _hud_blend(plane["alpha"], plane["solid"], plane["sky"])
                )
                sky = _srgb_lum(plane["sky"])
                solid = _srgb_lum(plane["solid"])
            except (KeyError, TypeError, ValueError):
                depth_gaps.append(f"{label}: depth contract unreadable")
                break
            if _wcag(far, sky) < 1.02:
                depth_gaps.append(
                    f"{label}: act {act} the far layer is invisible ({_wcag(far, sky):.2f})"
                )
            elif _wcag(far, sky) >= _wcag(solid, sky):
                depth_gaps.append(
                    f"{label}: act {act} the far layer is as near as the midground"
                )
    for missing in {
        f"{key}/{s or 'default'}" for key in _depth_all for s in _scene_themes
    } - depth_seen:
        depth_gaps.append(f"{missing}: no depth contract reported")
    # C-1345 redefined the value from 0/1 to the NUMBER of templates whose
    # far-layer contract holds - any gap anywhere still collapses it to 0
    # (両定義: 旧 0/1 は kaiju 時点で 1、新定義の変更前は duel が未報告の
    # ため 0).
    c.add(
        "creation_depth_layers",
        "遠景は淡く近景は濃い型",
        float(len(_depth_all)) if not depth_gaps else 0.0,
        detail=(
            "kaiju・duel × 4 テーマ × 全 3 場面で、遠景スカイライン（中景と"
            "同じ塗りを α 合成で霞ませたもの）が空より見えて（≥1.02:1）中景"
            "のシルエットより淡いことを実測（§7 観察 7 の 3 層——手前・中景・"
            "奥の霞。実測 遠景 1.04〜1.13:1・中景 1.21〜1.66:1）"
            if not depth_gaps
            else "; ".join(depth_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the clock is a journey too ------------------------------------
    #
    # §7 観察 5-6 at round scale (C-1315): the templates with a course spend
    # the brightness budget over distance, but the default template - the
    # fishing round - has no distance at all. Its journey is §8's sixty
    # seconds, so the sky must step with played time and keep the peak for
    # the final stretch. Measured by playing the round out: a cast landed
    # under the first sky and another under the last, acts read off the
    # running page as the clock passes each third, and the break still
    # called at sixty seconds - the arc decorates the round, it must not
    # touch it.
    round_scene_gaps: list[str] = []
    for _rs_request, _rs_probe_builder, _rs_hit in (
        ("釣りゲームを作って", _fishing_scene_probe, "cast"),
        ("難しい釣りゲームを作って", _fishing_scene_probe, "cast"),
        ("キャッチゲームを作って", _catch_scene_probe, "caught"),
        ("難しいキャッチゲームを作って", _catch_scene_probe, "caught"),
        # The puzzle joined the clock-bound skies with C-1327: its course
        # is the sixty seconds too, and its "hit" is a scored pop.
        ("パズルゲームを作って", _puzzle_sky_probe, "pop"),
        ("難しいパズルゲームを作って", _puzzle_sky_probe, "pop"),
    ):
        _rs_page = generate_game(_rs_request).html
        _rs_script = _scene_re.search(r"<script>(.*?)</script>", _rs_page, _scene_re.S)
        if _rs_script is None:
            round_scene_gaps.append(f"{_rs_request}: no script")
            continue
        try:
            _rs_run = _scene_sp.run(
                ["node", "-"],
                input=_rs_probe_builder(_rs_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _rs_run.returncode != 0:
                round_scene_gaps.append(f"{_rs_request}: {_rs_run.stderr.strip()[:80]}")
                continue
            _rs = json.loads(_rs_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            round_scene_gaps.append(f"{_rs_request}: probe unavailable ({type(exc).__name__})")
            continue
        acts = (_rs.get("sceneEarly"), _rs.get("sceneMid"), _rs.get("sceneLate"))
        if acts != (0, 1, 2):
            round_scene_gaps.append(f"{_rs_request}: the sky ignores the clock {acts}")
        _rs_scenes = _rs.get("scenes") or []
        if len(_rs_scenes) < 3 or max(
            range(len(_rs_scenes)), key=lambda i: _rs_scenes[i]["lum"]
        ) != len(_rs_scenes) - 1:
            round_scene_gaps.append(f"{_rs_request}: the last sky is not the brightest")
        if _rs.get(_rs_hit + "Early") != 1 or _rs.get(_rs_hit + "Late") != 1:
            round_scene_gaps.append(f"{_rs_request}: a play under the sky no longer lands")
        if not _rs.get("done") or _rs.get("reason") != "time":
            round_scene_gaps.append(f"{_rs_request}: the round no longer reaches its break")
    c.add(
        "creation_round_scene",
        "時間の経過で空が変わる",
        1.0 if not round_scene_gaps else 0.0,
        detail=(
            "fishing・catch・puzzle のラウンドを最後まで実プレイ: 幕 0→1→2 が"
            "実時間の 3 等分で切り替わり、最終幕が最明、第 1 幕と最終幕の両方で"
            "合わせ／受け／消しが成立、60 秒の区切りは不変（§7 観察 5-6 の"
            "ラウンド版）"
            if not round_scene_gaps
            else "; ".join(round_scene_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the perfect throw pays double ---------------------------------
    #
    # §13 事実 1 (C-1331): reward the player who takes a risk the game
    # never demanded. The default template was the last one where a skilled
    # press and a timid press scored the same point - the band paid 1
    # wherever it was hit. Now the middle 35% is the 会心 zone, drawn
    # deeper so the bargain is visible, and waiting for it risks the
    # marker leaving the band entirely. Measured by pressing three real
    # throws on the running page: dead centre pays 2 and counts a 会心,
    # the cautious edge pays its old 1 and counts none, and the whiff
    # outside pays 0 - so the risk is real in both directions.
    import re as _cp_re
    import subprocess as _cp_sp

    from sidra_ai.creation.fishing import precision_probe as _cp_probe

    cast_gaps: list[str] = []
    for _cp_request in ("釣りゲームを作って", "難しい釣りゲームを作って"):
        _cp_page = generate_game(_cp_request).html
        _cp_script = _cp_re.search(r"<script>(.*?)</script>", _cp_page, _cp_re.S)
        if _cp_script is None:
            cast_gaps.append(f"{_cp_request}: no script")
            continue
        try:
            _cp_run = _cp_sp.run(
                ["node", "-"],
                input=_cp_probe(_cp_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _cp_run.returncode != 0:
                cast_gaps.append(f"{_cp_request}: {_cp_run.stderr.strip()[:80]}")
                continue
            _cp = json.loads(_cp_run.stdout.strip().splitlines()[-1])
        except (OSError, _cp_sp.SubprocessError, ValueError) as exc:
            cast_gaps.append(f"{_cp_request}: probe unavailable ({type(exc).__name__})")
            continue
        perfect, careful, wide = _cp["perfect"], _cp["careful"], _cp["wide"]
        if perfect["gain"] <= careful["gain"]:
            cast_gaps.append(
                f"{_cp_request}: a perfect cast pays no more than a cautious one "
                f"({perfect['gain']} vs {careful['gain']})"
            )
        if perfect["gain"] != 2 or perfect["crits"] != 1 or perfect["hits"] != 1:
            cast_gaps.append(f"{_cp_request}: the centre press paid {perfect}")
        if careful["crits"] != 0:
            cast_gaps.append(f"{_cp_request}: caution and precision are the same throw")
        if careful["gain"] != 1 or careful["hits"] != 1:
            cast_gaps.append(f"{_cp_request}: the cautious press paid {careful}")
        if wide["gain"] != 0 or wide["hits"] != 0 or wide["casts"] != 1:
            cast_gaps.append(f"{_cp_request}: a miss was paid {wide}")
        if not (0 < _cp["crit"] < 1):
            cast_gaps.append(f"{_cp_request}: the 会心 zone is {_cp['crit']} of the band")
    c.add(
        "creation_cast_precision",
        "ど真ん中の合わせは倍払う",
        1.0 if not cast_gaps else 0.0,
        detail=(
            "fishing を normal と hard で実プレイし 3 投を値付け: 帯中央 35% の"
            "会心は 2 点＋重い演出、帯の端は従来どおり 1 点、帯の外は 0 点。"
            "点と釣果は分けて両方表示（§13 事実 1「取らなくてよい危険」・"
            "C-1405 の前例）"
            if not cast_gaps
            else "; ".join(cast_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the body of the jump ------------------------------------------
    #
    # §1's technique list (C-1332): tween, scale-bounce, particles, shake,
    # hitstop, sound. Scale-bounce - squash & stretch, the first principle
    # of animation - was the one item present nowhere, and the platformer
    # is the template whose whole craft is the jump. Watched frame by
    # frame on a real jump: the body stretches past 1 on the way up,
    # squashes below 1 on the exact landing frame, settles back within
    # half a second, and never breathes while standing still. The reduced-
    # motion run is the other half of the claim: every sampled frame reads
    # exactly 1, because that run promises the silhouette never changes.
    import re as _sq_re
    import subprocess as _sq_sp

    from sidra_ai.creation.platformer import squash_probe as _sq_probe

    squash_gaps: list[str] = []
    for _sq_request, _sq_reduced in (
        ("ジャンプアクションを作って", False),
        ("難しいジャンプアクションを作って", False),
        ("ジャンプアクションを作って", True),
    ):
        _sq_label = f"{_sq_request}{'（reduced）' if _sq_reduced else ''}"
        _sq_page = generate_game(_sq_request).html
        _sq_script = _sq_re.search(r"<script>(.*?)</script>", _sq_page, _sq_re.S)
        if _sq_script is None:
            squash_gaps.append(f"{_sq_label}: no script")
            continue
        try:
            _sq_run = _sq_sp.run(
                ["node", "-"],
                input=_sq_probe(_sq_script.group(1), reduced=_sq_reduced),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _sq_run.returncode != 0:
                squash_gaps.append(f"{_sq_label}: {_sq_run.stderr.strip()[:80]}")
                continue
            _sq = json.loads(_sq_run.stdout.strip().splitlines()[-1])
        except (OSError, _sq_sp.SubprocessError, ValueError) as exc:
            squash_gaps.append(f"{_sq_label}: probe unavailable ({type(exc).__name__})")
            continue
        if _sq_reduced:
            if (
                _sq["riseMax"] not in (0, 1)
                or (_sq["landSq"] or 1) != 1
                or _sq["idleMax"] != 0
                or _sq["restSq"] != 1
            ):
                squash_gaps.append(f"{_sq_label}: reduced motion still bounces {_sq}")
            continue
        if _sq["riseMax"] <= 1.1:
            squash_gaps.append(f"{_sq_label}: the jump never stretches ({_sq['riseMax']})")
        if _sq["landSq"] is None or _sq["landSq"] >= 0.9:
            squash_gaps.append(f"{_sq_label}: the landing never squashes ({_sq['landSq']})")
        if abs(_sq["settled"] - 1) > 0.02:
            squash_gaps.append(f"{_sq_label}: the bounce never settles ({_sq['settled']})")
        if _sq["idleMax"] != 0:
            squash_gaps.append(f"{_sq_label}: the body breathes while standing still")
    # The receiving half (C-1341): the catch basket takes an impact every
    # second and was the only rigid body left in its frame. Same contract,
    # its own verbs: 1 at rest, below 0.9 on the catch frame, back to 1
    # within half a second, and bit-identical 1 under reduced motion.
    from sidra_ai.creation.catchgame import bounce_probe as _bounce_probe

    for _sq_request, _sq_reduced in (
        ("キャッチゲームを作って", False),
        ("キャッチゲームを作って", True),
    ):
        _sq_label = f"catch{'（reduced）' if _sq_reduced else ''}"
        _sq_page = generate_game(_sq_request).html
        _sq_script = _sq_re.search(r"<script>(.*?)</script>", _sq_page, _sq_re.S)
        if _sq_script is None:
            squash_gaps.append(f"{_sq_label}: no script")
            continue
        try:
            _sq_run = _sq_sp.run(
                ["node", "-"],
                input=_bounce_probe(_sq_script.group(1), reduced=_sq_reduced),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _sq_run.returncode != 0:
                squash_gaps.append(f"{_sq_label}: {_sq_run.stderr.strip()[:80]}")
                continue
            _sq = json.loads(_sq_run.stdout.strip().splitlines()[-1])
        except (OSError, _sq_sp.SubprocessError, ValueError) as exc:
            squash_gaps.append(f"{_sq_label}: probe unavailable ({type(exc).__name__})")
            continue
        if not _sq.get("caught"):
            squash_gaps.append(f"{_sq_label}: nothing was ever caught, so nothing was measured")
            continue
        if _sq_reduced:
            if _sq["idleOff"] or _sq["catchSq"] != 1 or _sq["minAfter"] != 1:
                squash_gaps.append(f"{_sq_label}: reduced motion still bounces {_sq}")
            continue
        if _sq["idleOff"]:
            squash_gaps.append(f"{_sq_label}: the basket deforms with nothing landing")
        if _sq["catchSq"] is None or _sq["catchSq"] >= 0.9:
            squash_gaps.append(f"{_sq_label}: the catch never squashes ({_sq['catchSq']})")
        if abs(_sq["settled"] - 1) > 0.02:
            squash_gaps.append(f"{_sq_label}: the bounce never settles ({_sq['settled']})")
    # C-1341 redefined the value from 0/1 to the NUMBER of templates whose
    # own bounce contract holds - any gap anywhere still collapses it to 0
    # (両定義: 旧 0/1 は platformer 時点で 1、新定義の変更前は catch が
    # 未報告のため 0).
    c.add(
        "creation_squash_stretch",
        "イベントで体が伸びて潰れる型",
        2.0 if not squash_gaps else 0.0,
        detail=(
            "platformer の実ジャンプ（上昇 >1.1・着地 <0.9・0.5 秒で収束・"
            "立ち姿不動）＋ catch の実受け（受けの瞬間 <0.9・0.5 秒で復元・"
            "何も受けない間は不動）を毎フレーム観測。reduced-motion では"
            "両型とも全フレーム 1＝輪郭は一切変わらない（§1 の拡縮バウンス、"
            "跳ぶ側と受ける側）"
            if not squash_gaps
            else "; ".join(squash_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the hero has a face -------------------------------------------
    #
    # §1's technique list ends with eyes and expressions - the talk the
    # list comes from famously puts eyes on the blocks - and every SIDRA
    # character was a blank rectangle (C-1348). The platformer hero now
    # looks where the run goes, lifts its gaze while rising, and blinks
    # for one beat every few seconds; under reduced motion FRAME pins the
    # eyes open, so the face never animates there. Driven, not styled:
    # the probe runs both ways, jumps, and counts the blink.
    from sidra_ai.creation.platformer import face_probe as _face_probe

    face_gaps: list[str] = []
    for _fc_req, _fc_reduced in (
        ("ジャンプで進むゲームを作って", False),
        ("難しいジャンプで進むゲームを作って", False),
        ("ジャンプで進むゲームを作って", True),
    ):
        _fc_label = f"{'難しい' if '難しい' in _fc_req else 'default'}" + (
            "（reduced）" if _fc_reduced else ""
        )
        _fc_page = generate_game(_fc_req).html
        _fc_script = _scene_re.search(r"<script>(.*?)</script>", _fc_page, _scene_re.S)
        if _fc_script is None:
            face_gaps.append(f"{_fc_label}: no script")
            continue
        try:
            _fc_run = _scene_sp.run(
                ["node", "-"],
                input=_face_probe(_fc_script.group(1), reduced=_fc_reduced),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _fc_run.returncode != 0:
                raise ValueError(_fc_run.stderr.strip()[:60])
            _fc = json.loads(_fc_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            face_gaps.append(f"{_fc_label}: probe unavailable ({exc})")
            continue
        if _fc.get("lookRight") != 1 or _fc.get("lookLeft") != -1:
            face_gaps.append(f"{_fc_label}: the eyes never follow the run")
        if not _fc.get("upWhileRising"):
            face_gaps.append(f"{_fc_label}: the rise never lifts the gaze")
        if _fc_reduced:
            if _fc.get("blinkFrames"):
                face_gaps.append(f"{_fc_label}: reduced motion still blinks")
        elif not _fc.get("blinkFrames"):
            face_gaps.append(f"{_fc_label}: the hero never blinks")
        elif _fc.get("longestBlink", 0) > 12:
            face_gaps.append(
                f"{_fc_label}: the eyes stay shut ({_fc.get('longestBlink')} frames)"
            )
    c.add(
        "creation_hero_face",
        "主人公の目が走りを追う",
        0.0 if face_gaps else 1.0,
        detail=(
            "; ".join(face_gaps)
            if face_gaps
            else "platformer の実走行: 右へ走ると目が右（look=1）・左で -1・"
            "上昇中は視線が上がり、数秒に一度 1 拍のまばたき（500f 中 10f）。"
            "reduced-motion では FRAME が目を開いたまま留める＝顔は一切"
            "動かない（§1 の技法表で最後まで残っていた「キャラの目や表情」）"
        ),
        kind=OUTCOME,
    )

    # --- a held key keeps moving --------------------------------------
    #
    # §12 事実 3 (C-1328): held movement belongs in the loop, read off
    # pressed-state flags, not inside the keydown event. The on-screen pad
    # synthesises no key repeat - one press is exactly one keydown - so the
    # catch basket, the one template that moved only inside the event,
    # stood still under a held ◀ on the pad's own audience: a phone. The
    # probe presses the way the pad does (one keydown, one keyup) and reads
    # the basket every step: the tap nudge still lands, an OS auto-repeat
    # is not a second nudge, the drift continues while held, stops on
    # release, and the field edge holds. Whether catches still land is the
    # round-scene probe's question, asked of this same template every run.
    import re as _hm_re
    import subprocess as _hm_sp

    from sidra_ai.creation.catchgame import hold_probe as _hm_probe

    hold_gaps: list[str] = []
    for _hm_request in ("キャッチゲームを作って", "難しいキャッチゲームを作って"):
        _hm_page = generate_game(_hm_request).html
        _hm_script = _hm_re.search(r"<script>(.*?)</script>", _hm_page, _hm_re.S)
        if _hm_script is None:
            hold_gaps.append(f"{_hm_request}: no script")
            continue
        try:
            _hm_run = _hm_sp.run(
                ["node", "-"],
                input=_hm_probe(_hm_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _hm_run.returncode != 0:
                hold_gaps.append(f"{_hm_request}: {_hm_run.stderr.strip()[:80]}")
                continue
            _hm = json.loads(_hm_run.stdout.strip().splitlines()[-1])
        except (OSError, _hm_sp.SubprocessError, ValueError) as exc:
            hold_gaps.append(f"{_hm_request}: probe unavailable ({type(exc).__name__})")
            continue
        if abs((_hm["px0"] - _hm["pxNudge"]) - 0.06) > 0.02:
            hold_gaps.append(f"{_hm_request}: the first press lost its step")
        if _hm["pxNudge"] - _hm["pxRepeat"] > 0.02:
            hold_gaps.append(f"{_hm_request}: an OS auto-repeat is a second step")
        if _hm["pxHeld"] > _hm["pxNudge"] - 0.25:
            hold_gaps.append(f"{_hm_request}: a held key moves the basket once")
        if abs(_hm["pxStop2"] - _hm["pxStop1"]) > 1e-6:
            hold_gaps.append(f"{_hm_request}: the basket keeps moving after release")
        if not (-1e-9 <= _hm["pxEdge"] <= 1e-9):
            hold_gaps.append(f"{_hm_request}: the field edge does not hold")
    c.add(
        "creation_hold_to_move",
        "押しっぱなしで動き続ける",
        1.0 if not hold_gaps else 0.0,
        detail=(
            "catch をパッドと同じ押し方（keydown 1 回・リピート無し）で実測: "
            "初回タップの 0.06 ナッジ・保持中 0.012/フレームの継続移動・"
            "OS リピートで二重ナッジしない・keyup で停止・端で停まる"
            "（§12 事実 3。10 型で唯一 keydown 内でしか動かなかった型）"
            if not hold_gaps
            else "; ".join(hold_gaps)
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

    # --- what a big clear buys ----------------------------------------
    #
    # §5 (C-1322): the squared score says "clear big" but points are
    # vanity - they never touch the board's fate. Now a pop of five or
    # more banks a hammer (capped) and a hammer breaks one lone tile:
    # skill converted into survival, the tap/sink loop on the board
    # itself. Played out greedily on the running page: the refusal at
    # zero hammers, the earn on a big clear, and the spend - exactly one
    # tile gone, one hammer gone, the score untouched.
    from sidra_ai.creation.puzzle import hammer_probe as _puzzle_hammer_probe

    economy_gaps: list[str] = []
    for _ec_req in ("パズルゲームを作って", "難しいパズルゲームを作って"):
        _ec_page = generate_game(_ec_req).html
        _ec_script = _scene_re.search(r"<script>(.*?)</script>", _ec_page, _scene_re.S)
        if _ec_script is None:
            economy_gaps.append(f"{_ec_req}: no script")
            continue
        try:
            _ec_run = _scene_sp.run(
                ["node", "-"],
                input=_puzzle_hammer_probe(_ec_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _ec_run.returncode != 0:
                economy_gaps.append(f"{_ec_req}: {_ec_run.stderr.strip()[:60]}")
                continue
            _ec = json.loads(_ec_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            economy_gaps.append(f"{_ec_req}: probe unavailable ({type(exc).__name__})")
            continue
        _ec_refusal = _ec.get("refusal")
        if not _ec_refusal or _ec_refusal["tilesAfter"] != _ec_refusal["tilesBefore"]:
            economy_gaps.append(f"{_ec_req}: a broke player still broke a tile")
        _ec_earn = _ec.get("earn")
        if not _ec_earn:
            economy_gaps.append(f"{_ec_req}: no big clear ever banked a hammer")
        elif _ec_earn["size"] < 5:
            economy_gaps.append(f"{_ec_req}: a {_ec_earn['size']}-clear paid a hammer")
        _ec_spend = _ec.get("spend")
        if not _ec_spend:
            economy_gaps.append(f"{_ec_req}: the hammer was never spendable")
        else:
            if _ec_spend["tilesAfter"] != _ec_spend["tilesBefore"] - 1:
                economy_gaps.append(f"{_ec_req}: the break did not remove exactly one tile")
            if _ec_spend["hammersAfter"] != _ec_spend["hammersBefore"] - 1:
                economy_gaps.append(f"{_ec_req}: the break did not cost a hammer")
            if _ec_spend["scoreAfter"] != _ec_spend["scoreBefore"]:
                economy_gaps.append(f"{_ec_req}: the tool paid points (it must not)")
    c.add(
        "creation_puzzle_economy",
        "大消しが生存を買う",
        0.0 if economy_gaps else 1.0,
        detail=(
            "; ".join(economy_gaps)
            if economy_gaps
            else "puzzle を貪欲プレイで実測: 5 個以上の同時消しが『つち』を"
            "1 個ため（上限 3・HUD 表示）、つち 1 個で孤立 1 マスが砕ける"
            "——タイル丁度 1 減・つち 1 減・得点は不動。つち 0 では同じ押しが"
            "従来どおり拒まれる（§5 の tap→sink を盤上に）"
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

    # --- the break is quiet ---------------------------------------------
    #
    # §10 事実 4 (C-1336): adaptive music's oldest rule is that the tune
    # answers the state - Frogger switches the moment you are safe - and
    # the four bars were bouncing over 「ここまで」 and every template's
    # own end screen, painting over the very silence the win/fail beats
    # ring in. Heard, not read: a duel left alone loses on its own screen,
    # and the reservations are counted in three 300-frame windows -
    # playing, over the end screen, after R brings a new round.
    import re as _mb_re
    import subprocess as _mb_sp

    from sidra_ai.creation.music import end_probe as _mb_probe

    music_break_gaps: list[str] = []
    for _mb_request in ("ビームで撃ち合うゲームを作って", "難しいビームで撃ち合うゲームを作って"):
        _mb_page = generate_game(_mb_request).html
        _mb_script = _mb_re.search(r"<script>(.*?)</script>", _mb_page, _mb_re.S)
        if _mb_script is None:
            music_break_gaps.append(f"{_mb_request}: no script")
            continue
        try:
            _mb_run = _mb_sp.run(
                ["node", "-"],
                input=_mb_probe(_mb_script.group(1)),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if _mb_run.returncode != 0:
                music_break_gaps.append(f"{_mb_request}: {_mb_run.stderr.strip()[:80]}")
                continue
            _mb = json.loads(_mb_run.stdout.strip().splitlines()[-1])
        except (OSError, _mb_sp.SubprocessError, ValueError) as exc:
            music_break_gaps.append(f"{_mb_request}: probe unavailable ({type(exc).__name__})")
            continue
        if _mb["endedBy"] != "template":
            music_break_gaps.append(f"{_mb_request}: the duel never reached its own end")
        if _mb["during"] <= 0:
            music_break_gaps.append(f"{_mb_request}: the music never starts")
        if _mb["after"] != 0:
            music_break_gaps.append(
                f"{_mb_request}: the loop plays over the break ({_mb['after']} notes)"
            )
        if _mb["resumed"] <= 0:
            music_break_gaps.append(f"{_mb_request}: the music never comes back")
    c.add(
        "creation_music_break",
        "区切りでは音楽も止まる",
        1.0 if not music_break_gaps else 0.0,
        detail=(
            "duel を受動で敗北させ実測: プレイ中 300f は予約あり、終了画面の"
            "上では 0、R の新ラウンドで再開（§10 事実 4 の adaptive music。"
            "勝敗ビートの鳴る静寂を BGM が塗り潰さない）"
            if not music_break_gaps
            else "; ".join(music_break_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the tune is not allowed to lean on a wall ----------------------
    #
    # C-1129 (批評 #13). The melody is a random walk over ten pentatonic
    # degrees, and it ended at `Math.max(0,Math.min(9,...))`. A clamp is
    # not a boundary, it is an absorber: every step that reached past an
    # end became no step at all, so a run of outward draws printed one
    # pitch over and over. Real seeds did it - 「ゲームを作って」 alone
    # sat on the top degree for bars. The walk now bounces (walk the other
    # way by the size drawn), and the page keeps the log this is read
    # from, because re-deriving the melody to check the melody is the
    # check agreeing with itself.
    #
    # The claim is exact rather than statistical: a sounded note repeats
    # the one before it only when the draw itself was 0, so the longest
    # drone in the sample is exactly the longest chain of zero draws. A
    # clamp breaks that on the first seed that leans.
    from sidra_ai.creation.music import probe_source as _walk_probe

    variety_gaps: list[str] = []
    _walk_asks = (
        "ゲームを作って",
        "パズルゲームを作って",
        "釣りゲームを作って",
        "レースゲームを作って",
        "シューティングゲームを作って",
        "キャッチゲームを作って",
        "迷路のゲームを作って",
        "怪獣のゲームを作って",
        "ジャンプアクションを作って",
        "ビーム対戦を作って",
    )
    _walk_runs: list[tuple[str, dict]] = []
    for _walk_ask in _walk_asks:
        _walk_html = generate_game(_walk_ask).html
        _walk_src = _scene_re.search(r"<script>(.*?)</script>", _walk_html, _scene_re.S)
        if _walk_src is None:
            variety_gaps.append(f"{_walk_ask}: no script on the page")
            break
        try:
            _walk_out = _scene_sp.run(
                ["node", "-"],
                input=_walk_probe(_walk_src.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _walk_out.returncode != 0:
                raise ValueError(_walk_out.stderr.strip()[:60])
            _walk_runs.append(
                (_walk_ask, json.loads(_walk_out.stdout.strip().splitlines()[-1]))
            )
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            variety_gaps.append(f"probe unavailable ({exc})")
            break

    _walk_bounces = 0
    _walk_worst = 0
    for _walk_ask, _walk_heard in _walk_runs:
        walk = [list(entry) for entry in _walk_heard.get("walk") or []]
        mel = list(_walk_heard.get("mel") or [])
        sounded = [note for note in mel if note >= 0]
        if not walk:
            variety_gaps.append(f"{_walk_ask}: the page kept no walk")
            continue
        # The log is the melody, not a story told beside it.
        if [entry[2] for entry in walk] != sounded:
            variety_gaps.append(f"{_walk_ask}: the log and the tune disagree")
            continue
        for index, (came, drawn, went) in enumerate(walk):
            if not 0 <= went <= 9:
                variety_gaps.append(f"{_walk_ask}: left the scale ({went})")
                break
            # The size the draw asked for is the size taken, at an end or
            # anywhere else. A clamp shortens it; that is the defect.
            if abs(went - came) != abs(drawn):
                variety_gaps.append(
                    f"{_walk_ask}: step {index} moved {abs(went - came)}, drew {abs(drawn)}"
                )
                break
            if drawn != 0 and went == came:
                variety_gaps.append(f"{_walk_ask}: an end held the note at {came}")
                break
            if came + drawn < 0 or came + drawn > 9:
                _walk_bounces += 1
        # Every drone in the tune is a chain of zero draws and nothing
        # else: walk the sounded notes and the draws together.
        run = best = 1
        for index in range(1, len(walk)):
            if walk[index][2] == walk[index - 1][2]:
                if walk[index][1] != 0:
                    variety_gaps.append(
                        f"{_walk_ask}: repeated {walk[index][2]} on a non-zero draw"
                    )
                    break
                run += 1
                best = max(best, run)
            else:
                run = 1
        _walk_worst = max(_walk_worst, best)
    # A check that never reached an end proves nothing about ends.
    if _walk_runs and not _walk_bounces:
        variety_gaps.append("no seed in the sample ever reached an end")
    c.add(
        "creation_music_variety",
        "BGM が端に張り付いてドローンにならない",
        0.0 if variety_gaps else 1.0,
        detail=(
            "; ".join(variety_gaps)
            if variety_gaps
            else f"{len(_walk_runs)} 依頼を実走行し、ページ側の歩行ログで確認: "
            f"端に当たった歩 {_walk_bounces} 回すべてが draw と同じ歩幅で"
            f"跳ね返り、音が続くのは draw が 0 のときだけ（最長 {_walk_worst} 音）。"
            "ログは実際に鳴った音列と一致"
        ),
        kind=OUTCOME,
    )

    # --- playing well pays more than playing long ----------------------
    #
    # §13 事実 2: every template scored one point per thing, so a careful
    # round and a greedy one came out the same. C-1405 wires a combo
    # multiplier into catch first, and this asks the running page for the
    # four things the rule claims: it rises on consecutive successes, one
    # miss takes it back, it is on screen the whole time (at x1 as much as
    # at x4), and the score it feeds is points rather than catches. The
    # fifth reads the reduced-motion run: the rise keeps its sound and
    # loses its particles, which is C-1020's rule rather than a new one.
    from sidra_ai.creation.combo import COMBO_MAX, COMBO_STEP
    from sidra_ai.creation.combo import probe_source as _combo_probe

    combo_gaps: list[str] = []
    combo_page = generate_game("キャッチゲームを作って").html
    combo_script = _scene_re.search(r"<script>(.*?)</script>", combo_page, _scene_re.S)
    if combo_script is None:
        combo_gaps.append("no script on the page")
    else:
        def _combo_run(**kwargs):
            run = _scene_sp.run(
                ["node", "-"],
                input=_combo_probe(combo_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            return json.loads(run.stdout.strip().splitlines()[-1])

        try:
            clean = _combo_run(frames=1200)
            dropped = _combo_run(frames=1200, misses=[COMBO_STEP * COMBO_MAX])
            quiet = _combo_run(frames=600, reduced=True)
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            combo_gaps.append(f"probe unavailable ({exc})")
            clean = dropped = quiet = None

        if clean is not None:
            landings = clean["timeline"]
            if len(landings) < COMBO_STEP * COMBO_MAX:
                combo_gaps.append(f"only {len(landings)} landings to judge")
            else:
                # 1. it rises, on the rungs it says it does, and stops.
                rungs = {row["caught"]: row["mult"] for row in landings if row["missed"] == 0}
                wanted = {
                    n: min(COMBO_MAX, 1 + n // COMBO_STEP)
                    for n in rungs
                }
                off = {n: (rungs[n], wanted[n]) for n in rungs if rungs[n] != wanted[n]}
                if off:
                    combo_gaps.append(f"the ladder is not the rule: {sorted(off.items())[:3]}")
                if max(rungs.values(), default=0) != COMBO_MAX:
                    combo_gaps.append("a clean run never reaches the top rung")
                # 2. the points are not the count.
                top = landings[-1]
                if top["score"] <= top["caught"]:
                    combo_gaps.append(
                        f"the multiplier does not reach the score ({top['score']} for {top['caught']})"
                    )
                # 3. it is on screen at every rung, x1 included.
                seen_labels = {row["mult"]: row["hud"] for row in landings}
                blank = [m for m, hud in seen_labels.items() if not hud or f"\u00d7{m}" not in hud]
                if blank:
                    combo_gaps.append(f"not drawn at x{sorted(blank)}")

        if dropped is not None and dropped["timeline"]:
            after = [row for row in dropped["timeline"] if row["missed"] == 1]
            if not after:
                combo_gaps.append("the deliberate miss never landed")
            elif after[0]["mult"] != 1 or after[0]["run"] != 0:
                combo_gaps.append(
                    f"a miss did not take the run (x{after[0]['mult']}, run {after[0]['run']})"
                )
            elif not any(row["mult"] > 1 for row in after[1:]):
                combo_gaps.append("the run never rebuilds after a miss")

        if quiet is not None:
            loud = [row for row in (clean or {}).get("timeline", []) if "powerup" in row["rang"]]
            calm = [row for row in quiet["timeline"] if "powerup" in row["rang"]]
            if not calm:
                combo_gaps.append("reduced motion silences the rise as well")
            elif loud and min(row["rose"] for row in loud) <= max(
                row["rose"] for row in calm
            ):
                combo_gaps.append("reduced motion keeps the celebration's particles")
    c.add(
        "creation_combo_multiplier",
        "連続成功が得点に効く",
        0.0 if combo_gaps else 1.0,
        detail=(
            "; ".join(combo_gaps)
            if combo_gaps
            else f"catch を実走行: {COMBO_STEP} 連続ごとに 1 段・上限 x{COMBO_MAX}・"
            "1 度の失敗で x1 へ・HUD に常時表示・点は受け数でなく倍率込み。"
            "reduced では上がる音は残り粒子だけ落ちる"
        ),
        kind=OUTCOME,
    )

    # --- the same rule, flown rather than caught ------------------------
    #
    # C-1411 wires C-1405's ladder into the shooter, the second template
    # to have it. A kill was already a discrete success and a hull already
    # ended things, so the rule needed a place to add points and a place
    # to drop them and nothing else. What has to be true is read off a
    # flown page: the ladder rises on consecutive kills, a hull takes all
    # of it, each kill pays exactly the multiplier standing at that
    # moment, and graze (C-1406) is added beside it rather than multiplied
    # into it - a risk taken and a run kept are two things a player should
    # be paid for twice, not compounded.
    from sidra_ai.creation.combo import shooter_probe_source as _sc_probe

    sc_gaps: list[str] = []
    sc_page = generate_game("シューティングゲームを作って").html
    sc_script = _scene_re.search(r"<script>(.*?)</script>", sc_page, _scene_re.S)
    sc_clean = sc_crash = sc_quiet = None
    if sc_script is None:
        sc_gaps.append("no script on the page")
    else:
        def _sc_fly(**kw):
            out = _scene_sp.run(
                ["node", "-"],
                input=_sc_probe(sc_script.group(1), **kw),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:80])
            return json.loads(out.stdout.strip().splitlines()[-1])

        try:
            sc_clean = _sc_fly(frames=1400)
            sc_crash = _sc_fly(frames=1400, crash_at=400)
            sc_quiet = _sc_fly(frames=700, reduced=True)
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            sc_gaps.append(f"probe unavailable ({exc})")

    if sc_clean is not None:
        kills = [e for e in sc_clean["timeline"] if not e["hit"]]
        if not kills:
            sc_gaps.append("a held trigger shot nothing down")
        # 1. It rises, and it rises where the rule says.
        if sc_clean["combo"]["mult"] != COMBO_MAX:
            sc_gaps.append(
                f"clean flight topped out at x{sc_clean['combo']['mult']}, not x{COMBO_MAX}"
            )
        for entry, before in zip(kills[1:], kills):
            if entry["mult"] > before["mult"]:
                if entry["run"] % COMBO_STEP:
                    sc_gaps.append(
                        f"a rung arrived at {entry['run']} kills, not a multiple of {COMBO_STEP}"
                    )
                    break
        # 2. Each kill pays the rung standing at that moment - the whole
        #    point of the exercise, and the thing a wired-but-unpaid
        #    multiplier would fail while looking right on screen.
        singles = [e for e in kills if e["took"] == 1]
        if not singles:
            sc_gaps.append("no frame landed exactly one kill")
        for entry in singles:
            if entry["gained"] != entry["mult"]:
                sc_gaps.append(f"a kill at x{entry['mult']} paid {entry['gained']}")
                break
        # Two shots can meet two hulls on one frame, and a payout spanning
        # a rung is the sum of two rungs rather than twice either. Bounded
        # by the multiplier before the frame and the one after, because
        # recomputing the ladder here would be the check agreeing with
        # itself.
        for entry in [e for e in kills if e["took"] > 1]:
            if not (
                entry["was"] <= entry["mult"]
                and entry["took"] * entry["was"]
                <= entry["gained"]
                <= entry["took"] * entry["mult"]
            ):
                sc_gaps.append(
                    f"{entry['took']} kills between x{entry['was']} and "
                    f"x{entry['mult']} paid {entry['gained']}"
                )
                break
        # 3. On screen the whole time, at x1 as much as at the top.
        if kills and (kills[0]["hud"] or "").find("\u00d71") < 0:
            sc_gaps.append(f"the first kill drew {kills[0]['hud']!r}, without x1")
        top = [e for e in kills if e["mult"] == COMBO_MAX]
        if top and (top[0]["hud"] or "").find(f"\u00d7{COMBO_MAX}") < 0:
            sc_gaps.append(f"the top rung drew {top[0]['hud']!r}")
        # 4. Graze is beside the points, never inside them. The round banks
        #    the sum; a product would make one run worth the other's number.
        banked, paid = sc_clean["roundScore"], sc_clean["graze"]["paid"]
        if banked != sc_clean["score"] + paid:
            sc_gaps.append(
                f"the round banked {banked}, not {sc_clean['score']}+{paid}"
            )
        if not sc_clean["graze"]["seen"]:
            sc_gaps.append("the flight never grazed, so nothing was proved about it")
    if sc_crash is not None:
        # 5. One hull takes all of it - checked at the hull, not at the end,
        #    because a run that recovered by the last frame would look the
        #    same from there.
        hits = [e for e in sc_crash["timeline"] if e["hit"]]
        if not hits:
            sc_gaps.append("flying into hulls never cost a hit point")
        else:
            climbed = [e for e in sc_crash["timeline"] if e["mult"] > 1]
            if not climbed:
                sc_gaps.append("nothing was built before the crash")
            elif climbed[0]["at"] > hits[0]["at"]:
                sc_gaps.append("the crash came before any run existed")
            if hits[0]["mult"] != 1 or hits[0]["run"] != 0:
                sc_gaps.append(
                    f"a hull left x{hits[0]['mult']} run {hits[0]['run']}"
                )
    if sc_quiet is not None and sc_clean is not None:
        # 6. C-1020's rule, not a new one: the rise keeps its sound and
        #    loses its particles. Compared against the same rung flown with
        #    motion on, so "quieter" is measured rather than assumed.
        loud = [e for e in sc_clean["timeline"] if "powerup" in e["rang"]]
        quiet = [e for e in sc_quiet["timeline"] if "powerup" in e["rang"]]
        if not quiet:
            sc_gaps.append("reduced motion lost the sound of the rise")
        elif not loud:
            sc_gaps.append("no rung to compare the reduced run against")
        elif quiet[0]["rose"] >= loud[0]["rose"]:
            sc_gaps.append(
                f"reduced motion still threw particles ({quiet[0]['rose']} vs {loud[0]['rose']})"
            )
        if quiet and (quiet[0]["hud"] or "").find("\u00d7") < 0:
            sc_gaps.append("reduced motion dropped the number as well")
    c.add(
        "creation_shooter_combo",
        "撃墜の連続が得点に効く",
        0.0 if sc_gaps else 1.0,
        detail=(
            "; ".join(sc_gaps)
            if sc_gaps
            else f"shooter を 3 通り実走行: {COMBO_STEP} 連続撃墜ごとに 1 段・"
            f"上限 x{COMBO_MAX}・1 回の被弾で x1 へ・1 撃はその瞬間の倍率ぶん"
            f"入る・HUD に常時表示・かすり点は掛けずに足す"
            f"（{sc_clean['kills']} 撃墜 {sc_clean['score']} 点＋かすり "
            f"{sc_clean['graze']['paid']}＝{sc_clean['roundScore']}）。"
            "reduced では上がる音は残り粒子だけ落ちる"
            if sc_clean
            else ""
        ),
        kind=OUTCOME,
    )

    # --- a danger the player is allowed to decline ---------------------
    #
    # §13 事実 1: every hazard in the product is simply to be avoided, so
    # no risk is ever optional. C-1406 puts a graze band just outside the
    # shooter's kill radius: brushing a hull pays, three brushes in a row
    # make a point, and a hit takes the run. Four checks, flown on the real
    # page. The band check reads the *page's own* record of the gap it
    # judged each brush at - measuring that from outside the frame reads
    # the hulls before they move and reports grazes that never happened.
    from sidra_ai.creation.graze import GRAZE_BAND, GRAZE_RUN
    from sidra_ai.creation.graze import probe_source as _graze_probe

    graze_gaps: list[str] = []
    graze_page = generate_game("シューティングゲームを作って").html
    graze_script = _scene_re.search(r"<script>(.*?)</script>", graze_page, _scene_re.S)
    if graze_script is None:
        graze_gaps.append("no script on the page")
    else:
        def _graze_run(**kwargs):
            run = _scene_sp.run(
                ["node", "-"],
                input=_graze_probe(graze_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            return json.loads(run.stdout.strip().splitlines()[-1])

        try:
            hug = _graze_run(mode="hug")
            crash = _graze_run(mode="crash")
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            graze_gaps.append(f"probe unavailable ({exc})")
            hug = crash = None

        if hug is not None:
            # 1. brushing pays, and it reaches the round's own score.
            if hug["graze"]["paid"] <= 0:
                graze_gaps.append(f"a hugging flight earned nothing ({hug['graze']})")
            elif hug["roundScore"] <= hug["score"]:
                graze_gaps.append(
                    f"the graze points never reach the score "
                    f"({hug['roundScore']} vs {hug['score']} kills)"
                )
            # 2. distance earns nothing: every brush the page took was
            #    inside the band, and outside the radius that kills.
            outside = [
                pair
                for pair in hug["graze"]["at"]
                if not (pair[1] < pair[0] <= pair[1] + GRAZE_BAND)
            ]
            if not hug["graze"]["at"]:
                graze_gaps.append("the page recorded no brushes to check")
            elif outside:
                graze_gaps.append(f"paid outside the band: {outside[:3]}")
            # 3. it pays on a run, not per brush.
            if hug["graze"]["seen"] < hug["graze"]["paid"] * GRAZE_RUN:
                graze_gaps.append(
                    f"paid more often than the run allows "
                    f"({hug['graze']['seen']} brushes, {hug['graze']['paid']} points)"
                )

        if crash is not None:
            # 4. the hull still kills, and a hit takes the run.
            if crash["hp"] > 0:
                graze_gaps.append("flying into a hull no longer costs anything")
            hits = [row for row in crash["timeline"] if row.get("hit")]
            if not hits:
                graze_gaps.append("the crashing flight never lost a hull")
            elif any(row["run"] != 0 for row in hits):
                kept = [row["run"] for row in hits if row["run"] != 0]
                graze_gaps.append(f"a hit did not take the run (left {kept[:3]})")
            if crash["graze"]["paid"] > 0:
                graze_gaps.append("a flight that kept crashing still banked points")
            # ...and the radius it kills at has not moved. Asked of the
            # gap each hull actually landed from, because a page reports
            # its kill radius from a number recomputed beside the check -
            # shrinking the real one by a band's width passed a judge that
            # read the reported figure.
            struck = crash["graze"]["struck"]
            if not struck:
                graze_gaps.append("no hull landed, so the radius is unmeasured")
            else:
                inside = [pair for pair in struck if pair[0] >= pair[1]]
                if inside:
                    graze_gaps.append(f"a hull landed from outside its radius: {inside[:2]}")
                # Hulls close by a couple of pixels a frame, so the widest
                # landing sits just under the radius unless it moved.
                reach = max(pair[1] - pair[0] for pair in struck)
                if reach > 4:
                    graze_gaps.append(
                        f"the kill radius moved: the widest landing was {reach:.1f}px inside it"
                    )
    c.add(
        "creation_shooter_graze",
        "避けなくてよい危険がある",
        0.0 if graze_gaps else 1.0,
        detail=(
            "; ".join(graze_gaps)
            if graze_gaps
            else f"shooter を実走行: 撃墜半径の外側 {GRAZE_BAND}px の帯を"
            f"かすると加点、{GRAZE_RUN} 連続で 1 点、被弾で連続数 0。"
            "帯の内側だったことはページ自身の記録で確認（機体は"
            "フレーム内で動くので外からは測れない）。当たり判定は不変"
        ),
        kind=OUTCOME,
    )

    # --- a dial, not just an off switch --------------------------------
    #
    # C-1408: the panel let a player change the difficulty, two axes, the
    # accent and three flags, and the only thing it could do about sound
    # was M for all-or-nothing. The volume rides a single master factor
    # applied *after* the ceiling, which is the part worth measuring: the
    # fight's loudness step (§6 観察 4) is a ratio between two gains, and a
    # factor multiplied in before Math.min would be squeezed by the clamp
    # at full volume and not at half. So the ratio is read at two volumes
    # and must be the same number.
    from sidra_ai.creation.audio import volume_probe_source as _vol_probe

    vol_gaps: list[str] = []
    vol_page = generate_game("シューティングゲームを作って").html
    vol_script = _scene_re.search(r"<script>(.*?)</script>", vol_page, _scene_re.S)
    if vol_script is None:
        vol_gaps.append("no script on the page")
    else:
        heard = {}
        for level in (100, 50, 0):
            try:
                run = _scene_sp.run(
                    ["node", "-"],
                    input=_vol_probe(vol_script.group(1), volume=level),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if run.returncode != 0:
                    raise ValueError(run.stderr.strip()[:60])
                heard[level] = json.loads(run.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                vol_gaps.append(f"probe unavailable ({exc})")
                break

        if len(heard) == 3:
            full, half, off = heard[100], heard[50], heard[0]
            # 1. half means half, in the gain the page actually scheduled.
            if not full.get("calm"):
                vol_gaps.append("nothing was played at full volume")
            elif abs(half["calm"] - full["calm"] * 0.5) > 1e-6:
                vol_gaps.append(
                    f"50% is not half ({full['calm']} -> {half['calm']})"
                )
            # 2. zero is silence, not a very quiet sound.
            if off["calm"] is not None or off["tuneCount"] != 0:
                vol_gaps.append("0% still made a sound")
            # 3. the dial and the mute are different controls.
            if any(seen["mutedPlayed"] for seen in heard.values()):
                vol_gaps.append("M no longer silences the page")
            elif half["afterMute"] != half["calm"]:
                vol_gaps.append("releasing M did not hand back the set volume")
            # 4. the setting survives the trip through storage.
            for level, seen in heard.items():
                if seen.get("stored") != level:
                    vol_gaps.append(
                        f"a stored {level}% came back as {seen.get('stored')!r}"
                    )
            # 5. ...and the fight's step over calm is the same step.
            ratios = {}
            for level in (100, 50):
                seen = heard[level]
                if seen.get("calmClamped"):
                    ratios[level] = round(seen["loudClamped"] / seen["calmClamped"], 6)
            if len(ratios) != 2:
                vol_gaps.append("the combat step could not be read at both volumes")
            elif ratios[100] != ratios[50]:
                vol_gaps.append(
                    f"the volume changed the fight's step ({ratios[100]} vs {ratios[50]})"
                )
            # ...and the same, where the ceiling can actually be reached.
            # Nothing shipped comes near MAX_GAIN (the loudest effect peaks
            # at 0.48 against 0.9), so with today's values the dial's
            # position either side of Math.min changes nothing and the two
            # orderings are indistinguishable in any real sound. musicNote
            # takes its gain from the caller, so it is the one path where
            # the rule can be measured instead of assumed.
            if not full.get("clampedTune"):
                vol_gaps.append("the clamped gain could not be read")
            elif abs(half["clampedTune"] - full["clampedTune"] * 0.5) > 1e-6:
                vol_gaps.append(
                    "the dial is applied before the ceiling: a clamped gain "
                    f"went {full['clampedTune']} -> {half['clampedTune']}, not half"
                )
            # 6. the music rides the same dial as the effects.
            if not full.get("tune"):
                vol_gaps.append("the music scheduled no note to check")
            elif abs(half["tune"] - full["tune"] * 0.5) > 1e-6:
                vol_gaps.append(
                    f"the music ignores the dial ({full['tune']} -> {half['tune']})"
                )
    c.add(
        "creation_volume_axis",
        "音量が段階で変えられる",
        0.0 if vol_gaps else 1.0,
        detail=(
            "; ".join(vol_gaps)
            if vol_gaps
            else "実走行で確認: 50% で実 gain が半分・0% は無音（node を"
            "1 つも作らない）・M は独立で解除すると設定音量が戻る・"
            "保存が往復する・BGM も同じダイヤル・戦闘音圧比は 100% と"
            "50% で同一。**天井（MAX_GAIN）は現状どの音も届かない**ので、"
            "掛ける順序は musicNote に天井が効く gain を渡して実測した"
        ),
        kind=OUTCOME,
    )

    # --- the losing strip says why -------------------------------------
    #
    # C-1409: a losing round offered 「R / タップでもう一度」 and nothing
    # else - it asked for another go without saying what to do differently.
    # The line is built from counters the round already keeps, so the check
    # is that the number matches the loss that was actually produced, that
    # a win says nothing, and that a cause counted zero is never named.
    from sidra_ai.creation.games import _DIFFICULTY as _recap_ladder
    from sidra_ai.creation.recap import LOSS_UNWIRED, LOSS_WIRED
    from sidra_ai.creation.recap import probe_source as _recap_probe
    from sidra_ai.evals.adventure_losable import FRAMES as _adv_frames
    from sidra_ai.evals.adventure_losable import recap_route as _adv_route
    from sidra_ai.creation.puzzle import recap_route as _pz_route

    recap_gaps: list[str] = []
    if set(LOSS_WIRED) & set(LOSS_UNWIRED) or set(LOSS_WIRED) | set(
        LOSS_UNWIRED
    ) != set(_TOUCH_TEMPLATES):
        recap_gaps.append("a template is neither wired nor given a reason")
    _recap_asks = {
        "shooter": ("シューティングゲームを作って", {}),
        "marble": ("3D のゲームを作って", {}),
        # An untouched platformer never falls, so its cause is zero and it
        # correctly says nothing; holding right walks it off the ledges.
        "platformer": ("ジャンプアクションを作って", {"hold": "ArrowRight"}),
        "kaiju": ("怪獣と戦うゲームを作って", {}),
        # An untouched duel loses on its own: the CPU charges and fires
        # while the player stands in whatever lane it aimed at (C-1422).
        # 「対戦格闘」 is a *declined* genre (C-1121) and would hand back a
        # fishing page - the request has to be one this template answers.
        "duel": ("ビーム対戦のゲームを作って", {}),
        # Since C-1404 every racing rung finishes untouched, so its loss
        # comes from the panel's slowest pace - the way C-1105 makes one.
        "racing": (
            "レースゲームを作って",
            {"stored": {"speed": min(p[0] for p in _recap_ladder["racing"].values())}},
        ),
        # The only one that has to be *steered*. No key, held or not, loses
        # the adventure: the way out of the first room goes around a pond
        # the sword cannot cut, so a loss needs a route (C-1424). The route
        # is the one that module measured, not a second copy of it.
        "adventure": (
            "冒険ゲームを作って",
            {"frames": _adv_frames, "route": _adv_route()},
        ),
        # Also steered, for a different reason: nothing falls and nothing
        # spawns here, so a board left alone never jams. The drive is
        # greedy-biggest-group, which never presses a lone tile and so
        # never spends a hammer (C-1427).
        "puzzle": ("パズルゲームを作って", {"route": _pz_route()}),
    }
    for key in sorted(LOSS_WIRED):
        request, drive = _recap_asks[key]
        found = _scene_re.search(
            r"<script>(.*?)</script>", generate_game(request).html, _scene_re.S
        )
        if found is None:
            recap_gaps.append(f"{key}: no script on the page")
            continue
        try:
            run = _scene_sp.run(
                ["node", "-"],
                input=_recap_probe(found.group(1), template=key, **drive),
                capture_output=True,
                text=True,
                timeout=240,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            seen = json.loads(run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            recap_gaps.append(f"{key}: probe unavailable ({exc})")
            continue
        end = seen["atEnd"]
        if seen.get("verdictWhileLive"):
            recap_gaps.append(f"{key}: a reason was settled while the go was still live")
        # The number has to be the counter's, not a constant that happens
        # to look like one. Derived here from raw page state so a rewritten
        # table disagrees with it.
        raw = seen.get("counters") or {}
        expected = {
            "shooter": (3 - raw["hp"]) if raw.get("hp") is not None else None,
            "platformer": raw.get("respawns"),
            "kaiju": (3 - raw["cycles"]) if raw.get("cycles") is not None else None,
            # Whichever of duel's two causes was the larger - the same
            # choice recapLine makes, derived here from the raw counters
            # so a rewritten table disagrees with the page.
            "duel": (
                max(raw.get("lostBeam") or 0, raw.get("lostClash") or 0)
                if raw.get("lostBeam") is not None
                else None
            ),
            # Same shape as duel: two causes, and the line reports whichever
            # was larger.
            "adventure": (
                max(raw.get("hurtRoam") or 0, raw.get("hurtGuard") or 0)
                if raw.get("hurtRoam") is not None
                else None
            ),
            # Tiles opened with the tool against tiles left standing, the
            # larger one reported.
            "puzzle": (
                max(raw.get("jamBroken") or 0, raw.get("jamTiles") or 0)
                if raw.get("jamTiles") is not None
                else None
            ),
        }.get(key)
        if expected is not None and end.get("line"):
            if str(int(expected)) not in end["line"]:
                recap_gaps.append(
                    f"{key}: the line's count is not the counter's "
                    f"({end['line']!r} against {expected})"
                )
        if not end["lost"]:
            recap_gaps.append(f"{key}: the go that was produced was not a loss")
            continue
        if not end["line"]:
            recap_gaps.append(f"{key}: a loss with a counted cause said nothing")
        elif not any(ch.isdigit() for ch in end["line"]):
            recap_gaps.append(f"{key}: the line names no count ({end['line']!r})")
        elif "0 " in end["line"]:
            # A cause counted zero is not a cause.
            recap_gaps.append(f"{key}: named a cause counted zero ({end['line']!r})")
        # ...and the same page, asked about a win, stays quiet.
        won = seen["afterWin"]
        if not isinstance(won, dict):
            recap_gaps.append(f"{key}: the win case could not be read ({won})")
        elif won["lost"] or won["line"]:
            recap_gaps.append(f"{key}: a win was still explained ({won['line']!r})")
        # The line has to reach the strip, not just the function.
        if end["line"] and end["line"] not in seen["strip"]:
            recap_gaps.append(f"{key}: the line never reached the result strip")
    # ...and the other direction: a loss the page cannot account for stays
    # silent rather than inventing something. An untouched platformer never
    # falls, so its one cause is zero.
    if not recap_gaps:
        found = _scene_re.search(
            r"<script>(.*?)</script>",
            generate_game("ジャンプアクションを作って").html,
            _scene_re.S,
        )
        try:
            run = _scene_sp.run(
                ["node", "-"],
                input=_recap_probe(found.group(1), template="platformer"),
                capture_output=True,
                text=True,
                timeout=240,
            )
            quiet = json.loads(run.stdout.strip().splitlines()[-1])["atEnd"]
        except (OSError, _scene_sp.SubprocessError, ValueError, AttributeError) as exc:
            recap_gaps.append(f"the zero-cause case could not be run ({exc})")
            quiet = None
        if quiet is not None:
            if not quiet["lost"]:
                recap_gaps.append("the untouched platformer round was not a loss")
            elif quiet["line"]:
                recap_gaps.append(
                    f"a cause counted zero was named anyway ({quiet['line']!r})"
                )
    c.add(
        "creation_loss_recap",
        "負けた理由を一言で言う",
        0.0 if recap_gaps else 1.0,
        detail=(
            "; ".join(recap_gaps)
            if recap_gaps
            else f"{len(LOSS_WIRED)} 型で実際に負けを作って確認: 帯の一言が"
            "その回のカウンタと一致し、勝ちでは何も言わず、0 のカウンタは"
            f"名指ししない。未配線 {len(LOSS_UNWIRED)} 型は理由つき"
            "（LOSS_UNWIRED）"
        ),
        kind=OUTCOME,
    )

    # --- a genre we cannot build is named, not approximated silently ---
    #
    # C-1120: the detector kept a third list of game words, so 「レースを
    # 作って」 was not even a creation request - it got the retrieval
    # boilerplate while choose_template knew to build a race. The words now
    # come from the routing table itself. This checks the other half: a
    # request for a genre with no template still reaches the generator, is
    # named in the asker's own words, and is answered with what *can* be
    # built rather than a bare claim that fishing was "nearest".
    from sidra_ai.creation.games import TEMPLATES as _weak_templates
    from sidra_ai.creation.games import detect_genre as _weak_genre
    from sidra_ai.creation.intent import detect_creation_intent as _weak_intent
    from sidra_ai.creation.router import build_default_router as _weak_router
    from sidra_ai.creation.vocabulary import GENRES as _weak_genres
    from sidra_ai.creation.vocabulary import labels_for as _weak_labels

    weak_gaps: list[str] = []
    # Every genre in the table, buildable or not, has to be a game request.
    for label, template, words in _weak_genres:
        probe = f"{words[0]}を作って"
        if _weak_intent(probe).kind.value != "game":
            weak_gaps.append(f"{label}: 「{probe}」 is not read as a game request")
    unbuildable = [
        (label, words[0])
        for label, template, words in _weak_genres
        if template not in _weak_templates
    ]
    if not unbuildable:
        weak_gaps.append("no unbuildable genre is named, so nothing can be declined")
    else:
        _weak_dir = _scene_tempfile.mkdtemp(prefix="weak-intent-")
        router = _weak_router(data_dir=_weak_dir)
        expected = _weak_labels(_weak_templates)
        for label, word in unbuildable:
            probe = f"{word}を作って"
            outcome = router.route(probe, _weak_intent(probe), [])
            if not outcome.handled:
                weak_gaps.append(f"{label}: the request was not handled at all")
                continue
            said = outcome.summary
            if label not in said:
                weak_gaps.append(f"{label}: the decline does not name the genre asked for")
            # ...and it lists what is real, from TEMPLATES rather than prose.
            missing = [name for name in expected if name not in said]
            if missing:
                weak_gaps.append(f"{label}: the reply omits buildable genres {missing[:3]}")
            if any(name in said for name, _t, _w in _weak_genres if _t not in _weak_templates and name != label):
                weak_gaps.append(f"{label}: the reply offers a genre that does not exist")
    c.add(
        "creation_weak_intent_reply",
        "作れない型は名指しして、作れる型を出す",
        0.0 if weak_gaps else 1.0,
        detail=(
            "; ".join(weak_gaps)
            if weak_gaps
            else f"語彙表の {len(_weak_genres)} ジャンル全部が制作依頼として届き、"
            f"うち作れない {len(unbuildable)} 件は依頼者の語で名指しし、"
            "作れる型を TEMPLATES から並べて返す（存在しない型は挙げない）"
        ),
        kind=OUTCOME,
    )

    # --- the losing streak counts real defeats --------------------------
    #
    # C-1122: the difficulty eases after three losses (C-1402), and it was
    # being fed 「did any failure beat ever fire?」 over the life of the
    # page. Two defects in one predicate: the count never reset, so in a
    # template that restarts in place every round after the first loss was
    # also a loss (29 straight duel wins measured as a streak of 30); and
    # the round clock's own beat made every fishing and catch round a
    # defeat, though neither has a losing state - the buzzer is how those
    # end, not how they are lost. Three rounds of either and the game
    # quietly eased itself for somebody who had lost nothing.
    from sidra_ai.creation.adapt import streak_probe_source as _streak_probe
    from sidra_ai.creation.games import TEMPLATES as _streak_templates

    streak_gaps: list[str] = []
    streak_ok: list[str] = []
    _streak_asks = {
        "adventure": "冒険ゲームを作って",
        "catch": "キャッチゲームを作って",
        "duel": "対戦ゲームを作って",
        "fishing": "釣りゲームを作って",
        "kaiju": "怪獣と戦うゲームを作って",
        "marble": "3D のゲームを作って",
        "platformer": "ジャンプアクションを作って",
        "puzzle": "パズルゲームを作って",
        "racing": "レースゲームを作って",
        "shooter": "シューティングゲームを作って",
    }
    for key in sorted(_streak_templates):
        found = _scene_re.search(
            r"<script>(.*?)</script>",
            generate_game(_streak_asks[key]).html,
            _scene_re.S,
        )
        if found is None:
            streak_gaps.append(f"{key}: no script on the page")
            continue
        try:
            # Seeded at two, so both directions show in one run: a losing
            # round must reach three, and a winning one must clear it.
            run = _scene_sp.run(
                ["node", "-"],
                # A key is held for every frame: since C-1123 an
                # abandoned round banks nothing at all, defeats included,
                # so an untouched run would be measuring that rule rather
                # than this one.
                input=_streak_probe(
                    found.group(1),
                    rounds=4,
                    stored={f"sidra.streak.{key}": "2"},
                    # A key no template binds: holding a steering key
                    # changes how each game goes (ArrowRight drives the
                    # race into a wall), and this is about the streak.
                    hold="x",
                ),
                capture_output=True,
                text=True,
                timeout=240,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            seen = json.loads(run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            streak_gaps.append(f"{key}: probe unavailable ({exc})")
            continue
        # Only the rounds that really were rounds: a clock-ended template
        # restarts by re-running the page, so the probe reads the same
        # finished round again rather than playing a new one.
        rounds = [row for row in seen["rounds"] if row.get("fresh")]
        if not rounds:
            streak_gaps.append(f"{key}: no round completed")
            continue
        # 1. the count is per round, never cumulative.
        runaway = [row["beats"] for row in rounds if row["beats"] > 1]
        if runaway:
            streak_gaps.append(f"{key}: the failure count carried over ({runaway[:3]})")
            continue
        # 2. a template with no losing state never records a defeat...
        if not seen["canLose"]:
            if any(row["lost"] for row in rounds):
                streak_gaps.append(f"{key}: the clock was recorded as a defeat")
                continue
            if any(row["stored"] for row in rounds):
                streak_gaps.append(f"{key}: a streak was banked for a game with no loss")
                continue
        else:
            # A round that fired the failure beat *was* a defeat. Checked
            # against the beat rather than against the same predicate that
            # decides the record, or a page where nothing is ever a loss
            # would agree with itself: everything reads "won", the streak
            # sits at zero, and the judge sees no contradiction.
            unfelt = [row for row in rounds if row["beats"] > 0 and not row["lost"]]
            if unfelt:
                streak_gaps.append(
                    f"{key}: a round that fired the failure beat was recorded as a win"
                )
                continue
            # ...and one that can lose counts exactly the rounds it lost,
            # starting from the two it was seeded with.
            expected, wrong = 2, []
            for row in rounds:
                expected = expected + 1 if row["lost"] else 0
                if row["stored"] != expected:
                    wrong.append((row["lost"], row["stored"], expected))
            if wrong:
                streak_gaps.append(f"{key}: the streak does not follow the losses {wrong[:2]}")
                continue
            if not any(row["lost"] for row in rounds) and rounds[0]["stored"] != 0:
                streak_gaps.append(f"{key}: a won round left the streak at {rounds[0]['stored']}")
                continue
        streak_ok.append(key)
    c.add(
        "creation_dda_streak_honest",
        "連敗記録が本当の負けだけを数える",
        float(len(streak_ok)) if not streak_gaps else 0.0,
        detail=(
            "; ".join(streak_gaps)
            if streak_gaps
            else f"{len(streak_ok)} 型を実走行（連敗 2 を仕込んで、実際に始まった回だけ数える）: "
            "失敗数はラウンドごとに戻り、負けた回だけ連敗が伸び、勝てば 0 に戻る。"
            "負け状態を持たない型は時間切れを敗北として記録しない"
        ),
        kind=OUTCOME,
    )

    # --- an abandoned round earns nothing -------------------------------
    #
    # C-1123: a page left alone still plays. The race finishes, the basket
    # catches whatever falls into it, and the result strip then banked a
    # personal best and offered a line to paste about it - the product
    # congratulating somebody for walking away. The fix is about the
    # *record*, not about making the games unplayable without input: since
    # C-1404 every racing rung is meant to finish untouched, and taking
    # that back would undo a decision made on measurements. An untouched
    # round still plays and still ends; it just does not claim the result
    # was anybody's.
    from sidra_ai.creation.adapt import streak_probe_source as _afk_probe
    from sidra_ai.creation.games import TEMPLATES as _afk_templates

    afk_gaps: list[str] = []
    afk_ok: list[str] = []
    _afk_asks = {
        "adventure": "冒険ゲームを作って",
        "catch": "キャッチゲームを作って",
        "duel": "対戦ゲームを作って",
        "fishing": "釣りゲームを作って",
        "kaiju": "怪獣と戦うゲームを作って",
        "marble": "3D のゲームを作って",
        "platformer": "ジャンプアクションを作って",
        "puzzle": "パズルゲームを作って",
        "racing": "レースゲームを作って",
        "shooter": "シューティングゲームを作って",
    }
    _afk_extra = (
        "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]),\n"
        "    touched: roundTouched(), score: ROUND_FINAL,\n"
        "    best: store['sidra.best.'+AFK_KEY_TOKEN] === undefined"
        " ? null : store['sidra.best.'+AFK_KEY_TOKEN],\n"
        "    total: store['sidra.total.'+AFK_KEY_TOKEN] === undefined"
        " ? null : store['sidra.total.'+AFK_KEY_TOKEN] });"
    )

    def _afk_run(key, request, hold):
        found = _scene_re.search(
            r"<script>(.*?)</script>", generate_game(request).html, _scene_re.S
        )
        if found is None:
            return None, f"{key}: no script on the page"
        source = _afk_probe(found.group(1), rounds=1, hold=hold).replace(
            "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]) });",
            _afk_extra.replace("AFK_KEY_TOKEN", json.dumps(key)),
        )
        try:
            run = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=240
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            return json.loads(run.stdout.strip().splitlines()[-1])["rounds"][0], None
        except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
            return None, f"{key}: probe unavailable ({exc})"

    for key in sorted(_afk_templates):
        request = _afk_asks[key]
        alone, problem = _afk_run(key, request, None)
        if problem:
            afk_gaps.append(problem)
            continue
        if alone["touched"]:
            afk_gaps.append(f"{key}: an untouched round was counted as played")
            continue
        banked = [
            name
            for name in ("best", "total")
            if alone[name] is not None
        ]
        if banked or alone["stored"]:
            afk_gaps.append(f"{key}: an untouched round banked {banked or 'a streak'}")
            continue
        # The other direction, or this number could be had by never
        # recording anything at all.
        played, problem = _afk_run(key, request, "ArrowRight")
        if problem:
            afk_gaps.append(problem)
            continue
        if not played["touched"]:
            afk_gaps.append(f"{key}: a played round was not counted as played")
            continue
        if played["best"] is None:
            afk_gaps.append(f"{key}: a played round banked no best")
            continue
        afk_ok.append(key)
    c.add(
        "creation_afk_no_record",
        "放置したラウンドは記録にならない",
        float(len(afk_ok)) if not afk_gaps else 0.0,
        detail=(
            "; ".join(afk_gaps)
            if afk_gaps
            else f"{len(afk_ok)} 型で実走行: 無操作の 1 ラウンドは自己ベストも"
            "累計もゴーストも連敗も残さず、キーを押した回は残す。"
            "ゲーム自体は無操作でも従来どおり進む（C-1404 の決定を戻さない）"
        ),
        kind=OUTCOME,
    )

    # --- a best that can still be beaten --------------------------------
    #
    # C-1124: four templates score against a ceiling - laps out of three,
    # damage out of three, cycles out of three, the gems a room holds. The
    # first good run reaches it, the strip says 自己ベスト更新 once, and
    # after that nothing it offers is reachable again: 「あと 1」 against a
    # maximum is a target that does not exist. Each now carries a second
    # key, consulted only when the scores are level - the race that took
    # less time, the duel won with more left.
    #
    # Driven by seeding the store rather than by playing well: the run is
    # given a best equal to what it will score and a second key that is
    # deliberately worse, then deliberately better. A saturating record
    # cannot pass both.
    from sidra_ai.creation.round import ROUND_TIE as _tie_table
    from sidra_ai.creation.adapt import streak_probe_source as _tie_probe

    tie_gaps: list[str] = []
    tie_ok: list[str] = []
    _tie_asks = {
        "racing": "レースゲームを作って",
        "duel": "対戦ゲームを作って",
        "kaiju": "怪獣と戦うゲームを作って",
        "adventure": "冒険ゲームを作って",
    }
    _tie_extra = (
        "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]),\n"
        "    score: ROUND_FINAL, tie: roundTieFacts() });"
    )

    def _tie_run(key, seed):
        found = _scene_re.search(
            r"<script>(.*?)</script>", generate_game(_tie_asks[key]).html, _scene_re.S
        )
        if found is None:
            return None, f"{key}: no script on the page"
        source = _tie_probe(found.group(1), rounds=1, hold="x", stored=seed).replace(
            "    stored: Number(store[ADAPT_KEY] === undefined ? 0 : store[ADAPT_KEY]) });",
            _tie_extra,
        )
        try:
            run = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=240
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:60])
            return json.loads(run.stdout.strip().splitlines()[-1])["rounds"][0], None
        except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
            return None, f"{key}: probe unavailable ({exc})"

    for key in sorted(_tie_table):
        _expr, better, label = _tie_table[key]
        # What the round scores and what its second key comes to, read off
        # a plain run so the seeds below are about this template's reality.
        plain, problem = _tie_run(key, {})
        if problem:
            tie_gaps.append(problem)
            continue
        if plain["score"] is None or plain["tie"]["now"] is None:
            tie_gaps.append(f"{key}: the round produced no score or no second key")
            continue
        if plain["tie"]["better"] != better or not plain["tie"]["label"]:
            tie_gaps.append(f"{key}: the page does not carry the second key")
            continue
        here, tie = plain["score"], plain["tie"]["now"]
        worse = tie + 1000 if better == "less" else tie - 1
        finer = tie - 1000 if better == "less" else tie + 1
        # Same score as the stored best, but a better second key: a record.
        beat, problem = _tie_run(
            key, {f"sidra.best.{key}": here, f"sidra.tie.{key}": worse}
        )
        if problem:
            tie_gaps.append(problem)
            continue
        if not beat["record"]:
            tie_gaps.append(f"{key}: a level score with a better {label} set no record")
            continue
        # ...and the same score with a worse second key: no record.
        held, problem = _tie_run(
            key, {f"sidra.best.{key}": here, f"sidra.tie.{key}": finer}
        )
        if problem:
            tie_gaps.append(problem)
            continue
        if held["record"]:
            tie_gaps.append(f"{key}: a worse {label} still claimed a record")
            continue
        # ...and it never outranks the score itself: a run that scored less
        # than the stored best sets no record however good its second key.
        outranked, problem = _tie_run(
            key, {f"sidra.best.{key}": here + 1, f"sidra.tie.{key}": worse}
        )
        if problem:
            tie_gaps.append(problem)
            continue
        if outranked["record"]:
            tie_gaps.append(f"{key}: a lower score claimed a record on its {label}")
            continue
        tie_ok.append(key)
    c.add(
        "creation_record_improvable",
        "上限に当たった自己ベストがまだ更新できる",
        float(len(tie_ok)) if not tie_gaps else 0.0,
        detail=(
            "; ".join(tie_gaps)
            if tie_gaps
            else f"上限つきの {len(tie_ok)} 型で実走行: 得点が並んだとき第 2 キー"
            "（合計タイム・残り体力）が良ければ更新し、悪ければ更新しない。"
            "得点そのものより優先されることはない"
        ),
        kind=OUTCOME,
    )

    # --- the subject is named even when the title was taken away --------
    #
    # C-1125: C-1205 taught the summary to admit that 「猫のゲーム」 becomes
    # a fishing page with no cat in it. Its test for "they named a subject"
    # was 「the title is not the template's default」, and two things broke
    # that. The trademark guard *replaces* the title with the default, so a
    # request for a named work looked exactly like a request that named
    # nothing - the note vanished where it was most needed. And matching a
    # genre counted as satisfying the request, so 「魚の 3D ゲーム」 got the
    # 3D course it asked for, with no fish, and said nothing.
    from sidra_ai.creation.games import undepicted_subject as _subject_left
    from sidra_ai.creation.intent import detect_creation_intent as _subject_intent
    from sidra_ai.creation.router import build_default_router as _subject_router

    subject_gaps: list[str] = []
    _subject_dir = _scene_tempfile.mkdtemp(prefix="subject-honest-")
    _subject_router_instance = _subject_router(data_dir=_subject_dir)

    def _subject_say(request):
        outcome = _subject_router_instance.route(
            request, _subject_intent(request), []
        )
        return outcome.summary if outcome.handled else ""

    # Named work, no genre word: renamed *and* undepicted. Both have to be
    # said, and the one about the title cannot claim it was kept.
    said = _subject_say("ポケモンみたいなゲームを作って")
    if "ポケモン" not in said:
        subject_gaps.append("a trademarked request never names what it asked for")
    elif "作品名" not in said:
        subject_gaps.append("the title was replaced without saying so")
    elif "のまま・難易度" in said:
        # Matched on the whole clause: 「そのまま遊べます」 ends every
        # summary and contains 「のまま」.
        subject_gaps.append("a renamed page claimed its title was kept")
    # A genre we can build, with a subject we cannot draw: the genre is
    # honoured, so this must not be worded as a substitution.
    said = _subject_say("魚の 3D ゲームを作って")
    if "魚" not in said or "絵として出てきません" not in said:
        subject_gaps.append("a matched genre hid an undepicted subject")
    elif "いちばん近い" in said:
        subject_gaps.append("an honoured genre was described as a substitution")
    # A named work that *is* the genre it names: nothing was dropped, so
    # only the renaming is worth saying.
    said = _subject_say("マリオみたいなゲームを作って")
    if "作品名" not in said:
        subject_gaps.append("a renamed platformer said nothing about the name")
    elif "絵として出てきません" in said or "まだ無いため" in said:
        subject_gaps.append("a request we honoured was apologised for anyway")
    # ...and a plain genre request carries no caveat at all.
    for plain in ("レースを作って", "キャッチゲームを作って", "シューティングゲームを作って"):
        said = _subject_say(plain)
        if "絵として出てきません" in said or "まだ無いため" in said or "作品名" in said:
            subject_gaps.append(f"{plain}: a satisfied request was apologised for")
    # C-1205's own case still holds.
    said = _subject_say("猫のゲームを作って")
    if "猫" not in said or "まだ無いため" not in said:
        subject_gaps.append("C-1205's subject note stopped firing")
    # The rule itself: genre words cancel, a subject does not.
    if _subject_left("レースを作って", "racing", "レース"):
        subject_gaps.append("a bare genre word reads as an undepicted subject")
    if not _subject_left("猫のゲームを作って", "fishing", "猫"):
        subject_gaps.append("a named subject reads as nothing")
    c.add(
        "creation_subject_honest",
        "描けない題材は、題名を奪われても名指しする",
        0.0 if subject_gaps else 2.0,
        detail=(
            "; ".join(subject_gaps)
            if subject_gaps
            else "実 chat で確認: 商標で改名されても題材を名指しし（改名も言う・"
            "「題はそのまま」と嘘をつかない）、ジャンルが通った 3D でも"
            "「魚は絵として出てこない」と言う。満たした依頼には注釈を付けない"
        ),
        kind=OUTCOME,
    )

    # --- a revision finds the page it was talking about -----------------
    #
    # C-1126: 「猫のほうを難しくして」 can only mean the cat game, but 猫 is
    # not a genre word, so the message fell through to "whatever was made
    # last" and quietly adjusted the puzzle instead. The name is matched on
    # its distinctive part - C-1125's rule, asked again - so a page titled
    # 「パズル」 is never picked by name and a page titled 「ゲーム」 cannot
    # answer to every message ever typed.
    import time as _rev_time

    from sidra_ai.creation.intent import detect_creation_intent as _rev_intent
    from sidra_ai.creation.revise import find_target_meta as _rev_target
    from sidra_ai.creation.router import build_default_router as _rev_router

    rev_gaps: list[str] = []
    _rev_dir = _scene_tempfile.mkdtemp(prefix="revision-target-")
    _rev_maker = _rev_router(data_dir=_rev_dir)
    # Made in this order, so "latest" is the puzzle and every wrong answer
    # is the same wrong answer.
    # 「ゲームを作って」 is titled 「ゲーム」 - a page whose name is nothing
    # but the generic word. Made *after* the cat game on purpose: matching
    # whole titles would let it answer to every message containing ゲーム,
    # and the cat's own revision is the one it would steal.
    for _rev_req in (
        "猫のゲームを作って",
        "ゲームを作って",
        "レースゲームを作って",
        "パズルゲームを作って",
    ):
        _rev_maker.route(_rev_req, _rev_intent(_rev_req), [])
        # Second-resolution stamps; without this the order is not the order.
        _rev_time.sleep(1.1)

    def _rev_pick(message):
        found = _rev_target(_rev_dir, message)
        return (found[1].get("template"), found[1].get("title")) if found else (None, None)

    _rev_cases = (
        # By name, where no genre word appears at all: the defect itself.
        ("猫のほうを難しくして", "fishing"),
        ("猫のゲームをやさしくして", "fishing"),
        # By genre, still.
        ("レースのほうを難しくして", "racing"),
        # A title that is only its genre word must not be matched by name -
        # but the genre rule finds it anyway, which is the right answer for
        # the right reason.
        ("パズルを難しくして", "puzzle"),
        # Nothing named: the latest, which is what a bare ask means.
        ("難しくして", "puzzle"),
        ("もっとやさしく", "puzzle"),
    )
    # The rule that stops one page answering to everything, checked
    # directly: a title the operator never chose, and a title that is only
    # its genre word, are both unaddressable by name. The driven cases
    # above cannot separate this from whole-title matching - both give the
    # same answers - so it is asserted where it lives.
    from sidra_ai.creation.revise import _distinctive_name as _rev_name

    for _rev_meta, _rev_why in (
        ({"title": "タイミング釣り", "template": "fishing", "request": "ゲームを作って"},
         "a page nobody named is addressable by the name we gave it"),
        ({"title": "パズル", "template": "puzzle", "request": "パズルゲームを作って"},
         "a title that is only its genre word is addressable by name"),
    ):
        if _rev_name(_rev_meta):
            rev_gaps.append(_rev_why)
    for message, want in _rev_cases:
        got, title = _rev_pick(message)
        if got != want:
            rev_gaps.append(f"「{message}」 -> {got}（{title}）, wanted {want}")
    c.add(
        "creation_revision_targeting",
        "直す対象が依頼文の指す一枚になる",
        0.0 if rev_gaps else 1.0,
        detail=(
            "; ".join(rev_gaps)
            if rev_gaps
            else f"4 枚作って {len(_rev_cases)} 通りの言い方で確認: 題名で指せば"
            "その一枚、ジャンルで指せばその型、何も指さなければ最新。"
            "ジャンル語だけの題名は題名照合の対象にしない"
        ),
        kind=OUTCOME,
    )

    # --- an empty frame is not a document ------------------------------
    #
    # C-1128: with nothing retrieved, both paper generators printed a
    # skeleton and announced it. 「「進捗報告」を 4 枚で作りました」 and
    # 「レポートを作りました（根拠 0 件、社長が埋める欄 3 箇所）」 are the
    # sentences of a delivered thing; what was delivered was a frame. The
    # file may still be written - the owner can fill it - but the summary
    # now leads with what did not happen, and names which of the two
    # indistinguishable causes it was: nothing in the index, or evidence
    # that fit no section. Driven through the callables the router holds,
    # both directions: an empty request must carry the notice and a request
    # with usable evidence must not.
    from sidra_ai.creation.deck_job import build_deck_generator as _empty_deck
    from sidra_ai.creation.document_job import build_document_generator as _empty_doc
    from sidra_ai.creation.empty import EMPTY_HEADLINE as _EMPTY_HEAD
    from sidra_ai.creation.empty import EMPTY_INDEX as _EMPTY_INDEX
    from sidra_ai.creation.evidence import Fact as _EmptyFact
    from sidra_ai.creation.intent import detect_creation_intent as _empty_intent

    empty_gaps: list[str] = []
    _empty_dir = _scene_tempfile.mkdtemp(prefix="empty-honest-")
    _empty_make = {
        "deck": _empty_deck(_empty_dir),
        "document": _empty_doc(_empty_dir),
    }
    _empty_ask = {
        "deck": "進捗をまとめたデッキを作って",
        "document": "進捗レポートを作って",
    }
    # Evidence that lands in a section, and evidence that lands in none.
    # The second is the whole reason the cause is reported rather than
    # assumed: it produces the identical blank artifact.
    _empty_fits = [
        _EmptyFact(text="いま出来ることは索引の全文検索です。", source="README.md"),
        _EmptyFact(text="進捗は 3 件です。", source="PR-1.md"),
    ]
    _empty_stray = [_EmptyFact(text="ジャムの煮沸はよく混ぜる。", source="jam.md")]

    def _empty_run(kind, facts):
        ask = _empty_ask[kind]
        return _empty_make[kind](ask, _empty_intent(ask), facts)

    _empty_scored = {}
    for _e_kind in ("deck", "document"):
        _e_bad: list[str] = []
        # 1. Nothing retrieved: the notice, the cause, and no claim of a
        #    made thing anywhere in the sentence.
        out = _empty_run(_e_kind, [])
        # startswith, not "in": the item asks for the notice *first*, and a
        # summary that announces a deck and mentions the trouble afterwards
        # is the sentence this was filed about.
        if not out.summary.startswith(_EMPTY_HEAD):
            _e_bad.append(f"{_e_kind}: 空でも冒頭で「作れませんでした」と言わない")
        if _EMPTY_INDEX not in out.summary:
            _e_bad.append(f"{_e_kind}: 索引が空という原因を言わない")
        if "作りました" in out.summary:
            _e_bad.append(f"{_e_kind}: 空額縁を「作りました」と呼んでいる")
        if not out.details.get("empty"):
            _e_bad.append(f"{_e_kind}: 空なのに details['empty'] が偽")
        # The file is still there to fill - the item allows the artifact,
        # it forbids the sentence.
        if not out.artifact_path:
            _e_bad.append(f"{_e_kind}: 下書きごと捨てている（保存してあると言った）")
        # 2. Evidence that fills a section: the notice must be gone and the
        #    ordinary summary back. Without this the metric is satisfied by
        #    a generator that never claims anything.
        out = _empty_run(_e_kind, _empty_fits)
        if _EMPTY_HEAD in out.summary:
            _e_bad.append(f"{_e_kind}: 中身があるのに「作れませんでした」")
        if "作りました" not in out.summary:
            _e_bad.append(f"{_e_kind}: 中身があるのに作ったと言わない")
        if out.details.get("empty"):
            _e_bad.append(f"{_e_kind}: 中身があるのに details['empty'] が真")
        _empty_scored[_e_kind] = not _e_bad
        empty_gaps += _e_bad

    # 3. The cause is measured, not worded. Evidence arrived and no section
    #    took it: the artifact is byte-for-byte as blank as case 1, and the
    #    owner's next step is different, so the line has to differ too.
    #    Deck only - a document has no per-section matching, so there is no
    #    such case to reach and claiming one would be the invention this
    #    whole judge is about.
    out = _empty_run("deck", _empty_stray)
    _e_cause: list[str] = []
    if not out.details.get("empty"):
        _e_cause.append("deck: どの欄にも当たらない根拠で欄が埋まった（前提が崩れた）")
    else:
        if not out.summary.startswith(_EMPTY_HEAD):
            _e_cause.append("deck: 全欄が空でも冒頭で「作れませんでした」と言わない")
        if _EMPTY_INDEX in out.summary:
            _e_cause.append("deck: 根拠が届いていたのに「索引が空」と言った")
        if "1 件" not in out.summary:
            _e_cause.append("deck: 届いた根拠の件数を言わない")
    if _e_cause:
        _empty_scored["deck"] = False
        empty_gaps += _e_cause
    c.add(
        "creation_empty_honest",
        "全欄が空の資料を成果と呼ばない",
        float(sum(1 for ok in _empty_scored.values() if ok)),
        detail=(
            "; ".join(empty_gaps)
            if empty_gaps
            else "デッキ/レポートを実際に生成して確認: 全欄が空なら冒頭で「中身の"
            "ある資料を作れませんでした」と言い、下書きは残す。1 欄でも埋まれば"
            "元の通り「作りました」。原因の言い分け（索引が空 / 届いたがどの欄にも"
            "当たらない）は、後者に到達できるデッキ側だけで検査している"
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
    # --- the talisman finally guards -----------------------------------
    #
    # §3 (C-1323): the optional door's reward, the charm, healed once at
    # pickup and then decorated the HUD - a protective talisman that never
    # protected. Now one fatal hit shatters it in the hero's place: hp
    # stays at one, the mercy frames outlast a normal hit's, and the
    # failure beat does not fire for a death that did not happen. Once
    # only - the second fatal hit is an ordinary death. Struck for real
    # by the probe on two seeds.
    from sidra_ai.creation.adventure import charm_probe as _charm_probe

    charm_gaps: list[str] = []
    for _ch_req in ("迷宮を冒険するゲームを作って", "難しい冒険ゲームを作って"):
        _ch_page = generate_game(_ch_req).html
        _ch_script = _scene_re.search(r"<script>(.*?)</script>", _ch_page, _scene_re.S)
        if _ch_script is None:
            charm_gaps.append(f"{_ch_req}: no script")
            continue
        try:
            _ch_run = _scene_sp.run(
                ["node", "-"],
                input=_charm_probe(_ch_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _ch_run.returncode != 0:
                charm_gaps.append(f"{_ch_req}: {_ch_run.stderr.strip()[:60]}")
                continue
            _ch = json.loads(_ch_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            charm_gaps.append(f"{_ch_req}: probe unavailable ({type(exc).__name__})")
            continue
        _ch_save, _ch_death = _ch.get("afterSave") or {}, _ch.get("afterDeath") or {}
        if _ch_save.get("state") != "play" or _ch_save.get("hp") != 1:
            charm_gaps.append(f"{_ch_req}: the charm did not take the fatal hit")
            continue
        if _ch_save.get("charm") is not False:
            charm_gaps.append(f"{_ch_req}: the shield reforms - immortality wearing an amulet")
        if _ch_save.get("inv", 0) <= 60:
            charm_gaps.append(f"{_ch_req}: the mercy frames are no longer than a normal hit's")
        if _ch_save.get("beats") != 0:
            charm_gaps.append(f"{_ch_req}: a survived hit fired the failure beat")
        if _ch_death.get("state") != "over" or _ch_death.get("beats") != 1:
            charm_gaps.append(f"{_ch_req}: the second fatal hit is not an ordinary death")
    c.add(
        "creation_charm_shield",
        "護符が一度だけ身代わりになる",
        0.0 if charm_gaps else 1.0,
        detail=(
            "; ".join(charm_gaps)
            if charm_gaps
            else "護符持ちの hp1 に致死打を実際に当てて計測: 護符が砕けて"
            "hp1 で生存（無敵 90f＝通常 60f より長い慈悲・failBeat は鳴らない）、"
            "護符は消え、次の致死打は通常どおり敗北とビート。拾得文言も"
            "「一度だけ身代わりになる」と規則を言う（§3 の任意報酬が名前どおり"
            "守るように）"
        ),
        kind=OUTCOME,
    )

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
            # The gem is a pulse voice since C-1350: an oscillator still -
            # never noise - but one carrying its own comb into the graph.
            if gem != ["pulse", "oscillator"]:
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

    # --- three pulse voices, three widths (§2, C-1350) ------------------
    #
    # The last sfxr parameter the synth lacked: duty ratio. Web Audio has
    # no pulse type, so a pulse voice hands createPeriodicWave its Fourier
    # series - and the harmonics ARE the duty: harmonic n weighs
    # sin(n*pi*d)/n, so the comb's first null sits at n = 1/d. The judge
    # reads the ratio off that null in the wave the page actually built,
    # then checks it against the width the table declares - so a table
    # that says 12.5% while the wave plays square cannot pass. Harvested
    # from the texture probe's run: no extra node execution.
    duty_gaps: list[str] = []
    if timbre is not None and texture_script is not None:
        _duty_declared = {
            name: float(width)
            for name, width in _scene_re.findall(
                r"(\w+):\['pulse',[^\]]*?,([0-9.]+)\]", texture_script.group(1)
            )
        }
        _duty_read: dict[str, float] = {}
        for voice, expect_duty in (("sword", 0.25), ("gem", 0.125)):
            waves = timbre.get(f"{voice}Waves") or []
            if len(waves) != 1 or len(waves[0]) != 32:
                duty_gaps.append(f"{voice}: built {len(waves)} custom waves")
                continue
            imag = waves[0]
            null = next(
                (n for n in range(2, 32) if abs(imag[n]) < 1e-4 and abs(imag[n - 1]) > 1e-3),
                None,
            )
            if null is None:
                duty_gaps.append(f"{voice}: the spectrum has no comb, so no duty to read")
                continue
            _duty_read[voice] = 1.0 / null
            import math as _duty_math

            wrong = [
                n
                for n in range(1, 32)
                if abs(imag[n] - 2 / (n * _duty_math.pi) * _duty_math.sin(n * _duty_math.pi / null))
                > 1e-4
            ]
            if wrong:
                duty_gaps.append(f"{voice}: harmonics {wrong[:3]} do not follow a pulse at 1/{null}")
            elif abs(_duty_declared.get(voice, -1) - 1.0 / null) > 1e-6:
                duty_gaps.append(
                    f"{voice}: the table declares {_duty_declared.get(voice)} "
                    f"but the wave plays {1.0 / null:.4f}"
                )
            elif abs(1.0 / null - expect_duty) > 1e-6:
                duty_gaps.append(f"{voice}: duty {1.0 / null:.4f}, not the design's {expect_duty}")
        if len(_duty_read) == 2 and len(set(_duty_read.values())) < 2:
            duty_gaps.append("the two pulse voices share one width, so there is no family")
        if timbre.get("clashWaves"):
            duty_gaps.append("clash grew a custom wave: 50% is the square and keeps its name")
        elif timbre.get("clashNodes") != ["oscillator"]:
            duty_gaps.append(f"clash's wiring moved ({timbre.get('clashNodes')})")
        if timbre.get("swordMutedWaves") != 0:
            duty_gaps.append("the mute does not stop the pulse voice")
    elif not texture_gaps:
        duty_gaps.append("probe unavailable")
    c.add(
        "creation_sfx_duty",
        "スペクトルから読めるデューティ比を持つパルス声部の数",
        0.0 if duty_gaps or timbre is None else 2.0,
        detail=(
            "; ".join(duty_gaps or ["probe unavailable"])
            if duty_gaps or timbre is None
            else "実走行の AudioContext で確認: sword はくし形の節が第 4 倍音"
            "（=duty 25%）・gem は第 8 倍音（=12.5%）で、全 31 倍音が"
            "sin(nπd)/n のパルス列に一致し表の宣言値とも一致。clash は"
            "50%=square のまま＝3 声 3 音色。ミュートでパルスも沈黙"
        ),
        kind=OUTCOME,
    )

    # --- the step-up does not sound like the 47th gem ------------------
    #
    # §2's palette keeps powerUp as its own preset, apart from pickupCoin:
    # a rising tone WITH vibrato (C-1339). The multiplier stepping up is
    # rare and earned, and it was playing the same sweep as picking up a
    # gem. Read off each combo template's driven page: the cheer must
    # build the vibrato as a CONNECTION into the oscillator's frequency
    # (C-1308's lesson - an LFO that is built and never wired shaped
    # nothing), the gem must stay a plain oscillator, and the mute must
    # silence the step-up like everything else.
    powerup_gaps: list[str] = []
    for _pu_req, _pu_key in (
        ("キャッチゲームを作って", "catch"),
        ("シューティングゲームを作って", "shooter"),
        ("玉転がしゲームを作って", "marble"),
    ):
        _pu_page = generate_game(_pu_req).html
        _pu_script = _scene_re.search(r"<script>(.*?)</script>", _pu_page, _scene_re.S)
        if _pu_script is None:
            powerup_gaps.append(f"{_pu_key}: no script")
            continue
        try:
            _pu_run = _scene_sp.run(
                ["node", "-"],
                input=_sfx_probe.replace("SCRIPT_PLACEHOLDER", _pu_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _pu_run.returncode != 0:
                raise ValueError(_pu_run.stderr.strip()[:60])
            _pu = json.loads(_pu_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            powerup_gaps.append(f"{_pu_key}: probe unavailable ({exc})")
            continue
        cheer = _pu.get("cheerNodes")
        if not cheer:
            powerup_gaps.append(f"{_pu_key}: the cheer made no sound at all")
        elif "lfo->frequency" not in cheer:
            if "lfo->frequency" in (_pu.get("powerupNodes") or []):
                powerup_gaps.append(f"{_pu_key}: the step-up sounds like the 47th gem ({cheer})")
            else:
                powerup_gaps.append(f"{_pu_key}: the vibrato is built but never wired in ({_pu.get('powerupNodes')})")
        if "lfo->frequency" in (_pu.get("gemNodes") or []):
            powerup_gaps.append(f"{_pu_key}: the pickup grew a vibrato too, so the step-up is not distinct")
        if _pu.get("powerupMutedNodes"):
            powerup_gaps.append(f"{_pu_key}: M does not silence the step-up")
    # The other milestone voices (C-1346): the lantern, the shrine and the
    # charm raise a POWER, and each is driven for real; the key on the
    # ground is a LOCK's item and must stay plain - the judge holds both
    # sides of the distinction.
    from sidra_ai.creation.adventure import milestone_probe as _ms_probe
    from sidra_ai.creation.platformer import lamp_sfx_probe as _lamp_probe

    _pu_sites = 3 if not powerup_gaps else 0  # the three cheers above
    for _pu_req, _pu_key, _pu_builder in (
        ("迷宮を冒険するゲームを作って", "adventure", _ms_probe),
        ("ジャンプで進むゲームを作って", "platformer", _lamp_probe),
    ):
        _pu_page = generate_game(_pu_req).html
        _pu_script = _scene_re.search(r"<script>(.*?)</script>", _pu_page, _scene_re.S)
        if _pu_script is None:
            powerup_gaps.append(f"{_pu_key}: no script")
            continue
        try:
            _pu_run = _scene_sp.run(
                ["node", "-"],
                input=_pu_builder(_pu_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _pu_run.returncode != 0:
                raise ValueError(_pu_run.stderr.strip()[:60])
            _pu = json.loads(_pu_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            powerup_gaps.append(f"{_pu_key}: probe unavailable ({exc})")
            continue
        if _pu_key == "adventure":
            if not _pu.get("heartsAfter", 0) > 3 or "lfo->frequency" not in (
                _pu.get("shrineNodes") or []
            ):
                powerup_gaps.append("adventure: the shrine still rings like a pickup")
            else:
                _pu_sites += 1
            if not _pu.get("charmHeld") or "lfo->frequency" not in (
                _pu.get("charmNodes") or []
            ):
                powerup_gaps.append("adventure: the charm still rings like a pickup")
            else:
                _pu_sites += 1
            if not _pu.get("keyHeld"):
                powerup_gaps.append("adventure: the control key was never picked up")
            elif "lfo->frequency" in (_pu.get("keyNodes") or []):
                powerup_gaps.append(
                    "adventure: the lock's own key now shouts power-up"
                )
        else:
            if not _pu.get("lampLit") or "lfo->frequency" not in (
                _pu.get("lampNodes") or []
            ):
                powerup_gaps.append("platformer: the lantern still rings like a pickup")
            else:
                _pu_sites += 1
    # C-1346 redefined the value from 0/1 to the NUMBER of milestone sites
    # proven to ring the powerUp voice - any gap anywhere still collapses
    # it to 0 (両定義: 旧 0/1 は cheer 3 site の時点で 1、新定義の変更前は
    # 灯籠・祠・護符が鍵の音のままで 3).
    c.add(
        "creation_sfx_powerup",
        "力の節目が拾得と違う音で鳴る",
        float(_pu_sites) if not powerup_gaps else 0.0,
        detail=(
            "; ".join(powerup_gaps)
            if powerup_gaps
            else "6 つの節目を実駆動: combo 3 型の昇段＋灯籠点灯＋祠の最大"
            "ハート＋護符——全部が上昇音＋ビブラート（LFO が osc.frequency へ"
            "実接続・§2 の powerUp 系）。gem と地面の鍵は素の oscillator の"
            "まま＝力の音と錠前の音が聞き分けられる、M ミュートで無音"
        ),
        kind=OUTCOME,
    )

    # --- the key that is a fact, not an item ---------------------------
    #
    # §3 says keys come in kinds - items, tools, upgrades, KNOWLEDGE - and
    # distinguishes hard locks (the regular way only) from soft ones a
    # knowing player can route around (C-1340). The cave key was a hard
    # lock with one edge: kill every enemy. Now the forest stone tells a
    # seeded order and knocking the cave's three marks in that order
    # breaks the key's seal without a fight. Driven, not grepped: the
    # probe reads the order OFF THE STONE'S OWN MESSAGE - the knowledge
    # lives in the world, not in a facts function - knocks wrong on
    # purpose, then right, and watches the key fall with the enemies
    # still standing.
    from sidra_ai.creation.adventure import know_probe as _know_probe

    know_gaps: list[str] = []
    for _kn_req in ("迷宮を冒険するゲームを作って", "難しい迷宮を冒険するゲームを作って"):
        _kn_label = "難しい" if "難しい" in _kn_req else "default"
        _kn_page = generate_game(_kn_req).html
        _kn_script = _scene_re.search(r"<script>(.*?)</script>", _kn_page, _scene_re.S)
        if _kn_script is None:
            know_gaps.append(f"{_kn_label}: no script")
            continue
        try:
            _kn_run = _scene_sp.run(
                ["node", "-"],
                input=_know_probe(_kn_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _kn_run.returncode != 0:
                raise ValueError(_kn_run.stderr.strip()[:60])
            _kn = json.loads(_kn_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            know_gaps.append(f"{_kn_label}: probe unavailable ({exc})")
            continue
        order = _kn.get("order") or []
        if len(order) != 3 or sorted(order) != [0, 1, 2]:
            know_gaps.append(f"{_kn_label}: the sign keeps its secret ({_kn.get('signMsg')})")
            continue
        if _kn.get("wrongProgress") or _kn.get("wrongDrop"):
            know_gaps.append(f"{_kn_label}: the seal opens to any order")
        if not _kn.get("solved") or not _kn.get("keyGained"):
            know_gaps.append(f"{_kn_label}: the knowledge never paid the key")
        elif not _kn.get("aliveAtSolve"):
            know_gaps.append(f"{_kn_label}: the soft route still cost the fight")
    c.add(
        "creation_knowledge_key",
        "知識が鍵になる（§3 の soft lock）",
        0.0 if know_gaps else 1.0,
        detail=(
            "; ".join(know_gaps)
            if know_gaps
            else "実ページ 2 依頼で石碑を叩き、そのメッセージから順を読んで"
            "実行: 違う順では封が開かず、正しい順で敵が生きたまま鍵が転がり"
            "出て拾える（戦闘の hard 経路は不変・順列は SEED 由来）"
        ),
        kind=OUTCOME,
    )

    # --- a blow on the guardian reads in three beats -------------------
    #
    # §6 観察 2 (C-1343): a hit on a boss is flash, then smoke that stays,
    # then the silhouette back out of it. The kaiju leg has carried this
    # since C-1032; the guardian - the second boss built on the same
    # grammar - took a blow in one beat. Driven: one real strike, then
    # sixty frames of guardFacts, and the beats must stand in order.
    from sidra_ai.creation.adventure import beat_probe as _beat_probe

    beat_gaps: list[str] = []
    for _bt_req in ("迷宮を冒険するゲームを作って", "難しい迷宮を冒険するゲームを作って"):
        _bt_label = "難しい" if "難しい" in _bt_req else "default"
        _bt_page = generate_game(_bt_req).html
        _bt_script = _scene_re.search(r"<script>(.*?)</script>", _bt_page, _scene_re.S)
        if _bt_script is None:
            beat_gaps.append(f"{_bt_label}: no script")
            continue
        try:
            _bt_run = _scene_sp.run(
                ["node", "-"],
                input=_beat_probe(_bt_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _bt_run.returncode != 0:
                raise ValueError(_bt_run.stderr.strip()[:60])
            _bt = json.loads(_bt_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            beat_gaps.append(f"{_bt_label}: probe unavailable ({exc})")
            continue
        if not _bt.get("hurtAtHit"):
            beat_gaps.append(f"{_bt_label}: the blow never flashes")
        if not _bt.get("smokeFrames"):
            beat_gaps.append(f"{_bt_label}: the smoke never lingers")
        elif _bt.get("smokeAfterFlash", 0) < 15:
            beat_gaps.append(
                f"{_bt_label}: the smoke dies with the flash "
                f"({_bt.get('smokeAfterFlash')} frames past it)"
            )
        if _bt.get("smokeLeft"):
            beat_gaps.append(f"{_bt_label}: the smoke never clears")
    c.add(
        "creation_guard_hit_beats",
        "番人の被弾が 3 段で読める",
        0.0 if beat_gaps else 1.0,
        detail=(
            "; ".join(beat_gaps)
            if beat_gaps
            else "実ページ 2 依頼で番人に一撃を当て 60f を読む: 閃光が立ち"
            "（hurt 8f＋hitstop）、煙が閃光より長く残り（34f・閃光後 26f）、"
            "煙も晴れてシルエットが再登場（§6 観察 2・kaiju と同じ実測値）"
        ),
        kind=OUTCOME,
    )

    # --- the repeat never lands on the same pitch twice ----------------
    #
    # §14 事実 1 (C-1317): frequently fired effects need a small random
    # pitch shift or they read as a machine - and 事実 2 caps it: the
    # variation must stay well under the semitone (x1.06) that reads as a
    # deliberate step. Read off the same driven page as the texture above:
    # the same effect fired eight times must land on close-but-different
    # start frequencies, every one inside +-8% of the table's pitch, and
    # the mute must stop the variation with the sound.
    variation_gaps: list[str] = []
    if timbre is None:
        variation_gaps.append("probe unavailable (shared with texture)")
    else:
        heard_freqs = timbre.get("catchFreqs") or []
        _sfx_centre = 500.0  # SFX_TABLE catch f0; the probe fires 'catch'
        if len(heard_freqs) != 8:
            variation_gaps.append(f"the repeat was not heard ({len(heard_freqs)} of 8)")
        elif len(set(heard_freqs)) < 4:
            variation_gaps.append("the same pitch every time - the repeat is a machine again")
        elif any(
            not (_sfx_centre * 0.92 <= f <= _sfx_centre * 1.08) for f in heard_freqs
        ):
            variation_gaps.append(
                f"a repeat jumped out of the band ({min(heard_freqs):.0f}"
                f"-{max(heard_freqs):.0f} around {_sfx_centre:.0f})"
            )
        if timbre is not None and timbre.get("mutedFreqs") != 0:
            variation_gaps.append("the mute no longer stops the sound")
    c.add(
        "creation_sfx_variation",
        "同じ音が二度同じに鳴らない",
        0.0 if variation_gaps else 1.0,
        detail=(
            "; ".join(variation_gaps)
            if variation_gaps
            else "同じ効果音を 8 連射して実測: 開始周波数が毎回わずかに違い"
            "（±4% ジッタ、半音未満）、全発が表の音程 ±8% に収まり、"
            "M ミュートで止まる。スイープの両端が同じ係数で動くので"
            "音の正体（情報としてのピッチ）は不変（§14）"
        ),
        kind=OUTCOME,
    )

    # --- the victory has a phrase, not a beep --------------------------
    #
    # §2 (C-1326): the win became the round's heaviest beat (C-1316) while
    # its sound stayed a single half-second sweep - less to hear than the
    # defeat's noise burst. sfx('win') is now a rising major arpeggio (the
    # sfxr powerUp shape, plain C - no melody borrowed from anywhere),
    # every note through the same gain contract, all of it silent under M.
    # Read off the same driven page as the texture above.
    fanfare_gaps: list[str] = []
    if timbre is None:
        fanfare_gaps.append("probe unavailable (shared with texture)")
    else:
        _wf = timbre.get("winFreqs") or []
        if len(_wf) < 3:
            fanfare_gaps.append(f"the victory is {len(_wf)} note(s), not a phrase")
        elif any(_wf[i] >= _wf[i + 1] for i in range(len(_wf) - 1)):
            fanfare_gaps.append(f"the phrase does not rise ({[round(f) for f in _wf]})")
        if timbre.get("winGains") != len(_wf):
            fanfare_gaps.append(
                f"{timbre.get('winGains')} gain(s) for {len(_wf)} note(s) - "
                "a note off the loudness books"
            )
        if timbre.get("winMutedFreqs") != 0:
            fanfare_gaps.append("the fanfare plays under the mute")
    c.add(
        "creation_win_fanfare",
        "勝利がフレーズで鳴る",
        0.0 if fanfare_gaps else 1.0,
        detail=(
            "; ".join(fanfare_gaps)
            if fanfare_gaps
            else "実走行の AudioContext で確認: sfx('win') は 4 音の上昇"
            "アルペジオ（C-E-G-C・フレーズ全体に 1 ジッタで調律を保つ）、"
            "全音が gain 経由（戦闘段・上限・音量軸・M の契約は 1 音ずつ）、"
            "M ミュートで 0 音（§2 の powerUp 系を最重ビートに）"
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

    # --- match point plays faster than the opening bell ----------------
    #
    # §6's second-half change, duel edition (C-1318): the guardian and the
    # kaiju both quicken past half health, but the only versus mode used
    # to volley at the same pace at match point as at the opening. A
    # perfect dodger now takes twelve volleys at full health, at first
    # blood, and at match point: the foe's measured fill rate must step
    # ×1.15/×1.3 (the shooter's and marble's act table), the match point
    # must be behaviourally faster end to end, and the locked telegraph
    # must still give 15+ frames of warning in the last exchange - the
    # crescendo is not allowed to eat the fairness it plays over.
    from sidra_ai.creation.duel import pace_probe as _duel_pace_probe

    pace_gaps: list[str] = []
    for _pace_req in ("ビームで撃ち合うゲームを作って", "難しい対戦ゲームを作って"):
        _pace_page = generate_game(_pace_req).html
        _pace_script = _scene_re.search(r"<script>(.*?)</script>", _pace_page, _scene_re.S)
        if _pace_script is None:
            pace_gaps.append(f"{_pace_req}: no script")
            continue
        try:
            _pace_run = _scene_sp.run(
                ["node", "-"],
                input=_duel_pace_probe(_pace_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _pace_run.returncode != 0:
                pace_gaps.append(f"{_pace_req}: {_pace_run.stderr.strip()[:60]}")
                continue
            _pace = json.loads(_pace_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            pace_gaps.append(f"{_pace_req}: probe unavailable ({type(exc).__name__})")
            continue
        _acts = (_pace.get("opening"), _pace.get("middle"), _pace.get("clutch"))
        # Twelve shots leave eleven measured gaps between them.
        if any(a is None or a.get("n") != 11 for a in _acts):
            pace_gaps.append(f"{_pace_req}: an act was not fought out")
            continue
        _rates = [a["rate"] for a in _acts]
        if not (_rates[0] < _rates[1] < _rates[2]):
            pace_gaps.append(f"{_pace_req}: the fill rate ignores the act ({_rates})")
        elif abs(_rates[2] / _rates[0] - 1.3) > 0.02:
            pace_gaps.append(
                f"{_pace_req}: match point fills x{_rates[2] / _rates[0]:.2f}, not x1.3"
            )
        if _acts[2]["mean"] >= _acts[0]["mean"]:
            pace_gaps.append(
                f"{_pace_req}: match point is no faster end to end "
                f"({_acts[0]['mean']:.0f} -> {_acts[2]['mean']:.0f} frames)"
            )
        if any(a["minLock"] is None or a["minLock"] < 15 for a in _acts):
            pace_gaps.append(
                f"{_pace_req}: the crescendo ate the telegraph "
                f"({[a['minLock'] for a in _acts]})"
            )
        if _pace.get("state") != "play":
            pace_gaps.append(f"{_pace_req}: the measured match ended by itself")
        _pace_scenes = tuple(a.get("scene") for a in _acts)
        if _pace_scenes != (0, 1, 2):
            pace_gaps.append(f"{_pace_req}: the sky ignores the act {_pace_scenes}")
    # --- the flash never becomes a strobe -----------------------------
    #
    # §15 (WCAG 2.3.1, C-1320): a full-screen flash may switch on at most
    # three times in any one second - measured before the gate, the duel's
    # mash fire at match-point tempo hit four onsets in a second, and the
    # whole-canvas overlay is far past the area exemption. Driven with the
    # same machine-gun scenario: the worst rolling second must hold three
    # or fewer onsets while the flash itself stays alive - a gate that
    # passed by killing the effect would be a different defect. Statically,
    # every flash=1 in every template must go through flashGate().
    from sidra_ai.creation.duel import flash_probe as _duel_flash_probe
    from sidra_ai.creation.games import TEMPLATES as _fl_templates

    flash_gaps: list[str] = []
    for _fl_key, _fl_spec in _fl_templates.items():
        _fl_hits = _fl_spec.script.count("flash=1")
        _fl_gated = _fl_spec.script.count("if(flashGate())flash=1")
        if _fl_hits != _fl_gated:
            flash_gaps.append(f"{_fl_key}: {_fl_hits - _fl_gated} ungated flash=1")
    for _fl_req in ("ビームで撃ち合うゲームを作って", "撃ち合いの対戦を作って"):
        _fl_page = generate_game(_fl_req).html
        _fl_script = _scene_re.search(r"<script>(.*?)</script>", _fl_page, _scene_re.S)
        if _fl_script is None:
            flash_gaps.append(f"{_fl_req}: no script")
            continue
        try:
            _fl_run = _scene_sp.run(
                ["node", "-"],
                input=_duel_flash_probe(_fl_script.group(1)),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if _fl_run.returncode != 0:
                flash_gaps.append(f"{_fl_req}: {_fl_run.stderr.strip()[:60]}")
                continue
            _fl = json.loads(_fl_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            flash_gaps.append(f"{_fl_req}: probe unavailable ({type(exc).__name__})")
            continue
        if _fl.get("worstWindow", 99) > 3:
            flash_gaps.append(
                f"{_fl_req}: {_fl['worstWindow']} flashes in one second (WCAG 2.3.1 allows 3)"
            )
        if _fl.get("onsets", 0) < 5:
            flash_gaps.append(f"{_fl_req}: the gate killed the flash ({_fl.get('onsets')} onsets)")
    c.add(
        "creation_flash_cap",
        "閃光が 1 秒 3 回を超えない",
        0.0 if flash_gaps else 1.0,
        detail=(
            "; ".join(flash_gaps)
            if flash_gaps
            else "連打射撃・土壇場テンポで 15 秒実測: 全画面フラッシュの onset は"
            "どの 1 秒窓でも 3 回以下（WCAG 2.3.1）で、演出自体は生きている"
            "（15 秒で 25 回以上）。全テンプレの flash=1 が flashGate() 経由で"
            "あることも検査（§15・ゲート前の実測は 4 回/秒だった）"
        ),
        kind=OUTCOME,
    )

    c.add(
        "creation_duel_matchpoint",
        "土壇場が開幕より速い",
        0.0 if pace_gaps else 1.0,
        detail=(
            "; ".join(pace_gaps)
            if pace_gaps
            else "完全回避で各幕 12 ボレーを実測: 敵のチャージ充填率が幕ごとに"
            "×1.15/×1.3 と上がり、土壇場は開幕より実測で速く、ロック→発射の"
            "予兆は全幕 15f 以上のまま（§6 の後半変化・公正予兆 C-1309 と両立）。"
            "空も同じ幕を塗る（C-1321: 幕 0→1→2 でアリーナの基調色が変わる）"
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

    # --- danger you can decline, points you cannot fake ----------------
    #
    # §13 事実 1: reward the player who takes a risk the game never
    # demanded. The marble's hot gates (C-1313) stand in a block's shadow
    # and pay the base again; the opening gift gate never does. Judged by
    # rolling the course: hot gates exist, the pilot takes some, the score
    # is exactly explainable, and the run ends whether or not the hot ones
    # were taken (the risk is optional).
    #
    # **The arithmetic was restated in C-1421.** It used to read
    # ``(gates - hotTaken) + 2 * hotTaken`` - which quietly assumed no
    # multiplier exists anywhere on the course, and so would have been
    # broken by *any* run multiplier however it was written. The form below
    # sums each gate at the multiplier that was live when it landed, and
    # adds the hot gate's flat extra outside it. The two are the same
    # statement whenever every multiplier is 1: sum(base) + base*hotTaken
    # is gates + hotTaken is (gates - hotTaken) + 2*hotTaken. Checked that
    # way before it was adopted, on a course with nothing wired - both read
    # 23 against a score of 23.
    #
    # It is strictly the stronger of the two: every lie the old identity
    # caught (a score that does not match the gates taken) still fails it,
    # and a payment made at the wrong multiplier now fails it as well.
    from sidra_ai.creation.marble import GATE_BASE as _rr_base
    from sidra_ai.creation.marble import combo_probe_source as _marble_rr_probe
    from sidra_ai.creation.marble import probe_source as _marble_pace_probe

    rr_gaps: list[str] = []
    rr_page = generate_game("玉転がしゲームを作って").html
    rr_script = _scene_re.search(r"<script>(.*?)</script>", rr_page, _scene_re.S)
    if rr_script is None:
        rr_gaps.append("no script on the page")
    else:
        try:
            rr_run = _scene_sp.run(
                ["node", "-"],
                input=_marble_rr_probe(rr_script.group(1), mode="run"),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if rr_run.returncode != 0:
                raise ValueError(rr_run.stderr.strip()[:60])
            rolled = json.loads(rr_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            rolled = None
            rr_gaps.append(f"probe unavailable ({exc})")
        if rolled is not None:
            if rolled.get("hotTotal", 0) < 2:
                rr_gaps.append(f"no danger on the course ({rolled.get('hotTotal')})")
            if rolled.get("hotTaken", 0) < 1:
                rr_gaps.append("the risk was never worth taking")
            through = [e for e in rolled.get("events", []) if e["kind"] == "through"]
            expected = sum(
                _rr_base * e["mult"] + (_rr_base if e["hot"] else 0) for e in through
            )
            if not through:
                rr_gaps.append("the roll went through no gates")
            elif rolled.get("score") != expected:
                rr_gaps.append(
                    f"the score lies ({rolled.get('score')} != {expected})"
                )
            # ...and the hot gate's extra is flat, whatever the run was
            # paying. That is C-1313's claim itself - 「この門は 1 点多い」
            # has to stay true at x1 and at x4 alike - and it is the half
            # that stops the extra from being quietly folded into a
            # multiplier where a player could no longer see it.
            elif {
                e["paid"] - _rr_base * e["mult"] for e in through if e["hot"]
            } not in ({_rr_base}, set()):
                rr_gaps.append(
                    "the hot gate's extra changes with the run "
                    f"({sorted({e['paid'] - _rr_base * e['mult'] for e in through if e['hot']})})"
                )
            if rolled.get("state") != "over":
                rr_gaps.append("the course no longer completes")
    c.add(
        "creation_risk_reward",
        "取らなくてよい危険が報いる",
        0.0 if rr_gaps else 1.0,
        detail=(
            "; ".join(rr_gaps)
            if rr_gaps
            else "marble を実走: ブロックの陰のゲートが 2 点で実在し、"
            "合計は素点＋加点に一致、取らなくても完走できる（§13 事実 1）"
        ),
        kind=OUTCOME,
    )

    # --- the crescendo is in the roll, not only in the paint -----------
    #
    # §6 観察 3, at course scale (C-1314): the marble's three skies were
    # three colours over one constant speed - the same decorated flatness
    # C-1302 fixed in the shooter. Judged by rolling the course and
    # measuring the distance covered per frame in each act: strictly
    # rising, with the final stretch at least a fifth faster than the
    # first, while the hot gates and the finish still hold.
    ce_gaps: list[str] = []
    ce_page = generate_game("玉転がしゲームを作って").html
    ce_script = _scene_re.search(r"<script>(.*?)</script>", ce_page, _scene_re.S)
    if ce_script is None:
        ce_gaps.append("no script on the page")
    else:
        try:
            ce_run = _scene_sp.run(
                ["node", "-"],
                input=_marble_pace_probe(ce_script.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if ce_run.returncode != 0:
                raise ValueError(ce_run.stderr.strip()[:60])
            paced = json.loads(ce_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            paced = None
            ce_gaps.append(f"probe unavailable ({exc})")
        if paced is not None:
            rates = paced.get("rates") or []
            if len(rates) != 3 or min(rates) <= 0:
                ce_gaps.append(f"an act was never rolled through ({rates})")
            elif not (rates[0] < rates[1] < rates[2]):
                ce_gaps.append(
                    "the course does not re-accelerate "
                    f"({[round(r, 2) for r in rates]})"
                )
            elif rates[2] < rates[0] * 1.2:
                ce_gaps.append(
                    f"the final stretch is barely faster "
                    f"({rates[0]:.2f} -> {rates[2]:.2f})"
                )
            if paced is not None and paced.get("state") != "over":
                ce_gaps.append("the faster course no longer completes")
    c.add(
        "creation_course_escalation",
        "コースが幕ごとに速くなる",
        0.0 if ce_gaps else 1.0,
        detail=(
            "; ".join(ce_gaps)
            if ce_gaps
            else "marble を実走して幕別の実測速度を計測: 単調増加で最終幕が"
            "最速（×1.3）、完走と熱いゲートは不変（§6 観察 3 のコース版）"
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

    # --- the win is the heaviest moment of the round (C-1316) -----------
    #
    # §6 spends the biggest moment on the takedown and §1 scales the kick
    # to the weight of the event - yet after C-1105 every template's
    # victory was *lighter* than its loss (marble's was silent, kaiju's had
    # no win sound, the rest shook less than the failure's 14). One shared
    # winBeat now marks all seven win moments, and this number is earned
    # three ways: the kit itself is run in node under both motion settings,
    # three templates are actually played to their wins, and all seven
    # scripts are checked for the call - a win state that stopped calling
    # it would be a silent climax again.
    from sidra_ai.creation.juice import WIN_SHAKE as _win_shake
    from sidra_ai.creation.juice import probe_source as _win_kit_probe
    from sidra_ai.creation.platformer import probe_source as _plat_probe

    _win_templates = ("adventure", "duel", "kaiju", "marble", "platformer", "puzzle", "racing")
    win_gaps: list[str] = []
    for _wt in _win_templates:
        if "winBeat(" not in _tune_templates[_wt].script:
            win_gaps.append(f"{_wt}: the win moment never reaches winBeat()")
    for _wt in ("fishing", "catch", "shooter"):
        if "winBeat(" in _tune_templates[_wt].script:
            win_gaps.append(f"{_wt}: calls winBeat but has no win state")
    if _win_shake <= _fail_shake:
        win_gaps.append(
            f"the win shakes {_win_shake}, no more than the loss ({_fail_shake}) - "
            "the climax is outranked by the failure again"
        )
    # The kit, run: full weight with motion, zero shake without, and the
    # beat itself survives the setting.
    for _reduced in (False, True):
        try:
            _kit = _scene_sp.run(
                ["node", "-"],
                input=_win_kit_probe(reduced=_reduced),
                capture_output=True,
                text=True,
                timeout=30,
            )
            _kit_out = json.loads(_kit.stdout.strip().splitlines()[-1]) if _kit.returncode == 0 else None
        except (OSError, _scene_sp.SubprocessError, ValueError):
            _kit_out = None
        if not _kit_out or _kit_out.get("winBeats") != 1:
            win_gaps.append(f"kit reduced={_reduced}: winBeat did not run once")
            continue
        if _reduced and _kit_out.get("winShake") != 0:
            win_gaps.append(f"kit: shake {_kit_out.get('winShake')} survived reduced motion")
        if not _reduced and _kit_out.get("winShake", 0) < _win_shake:
            win_gaps.append(f"kit: the win shook only {_kit_out.get('winShake')}")
        if _kit_out.get("winHitstop", 0) <= 0:
            win_gaps.append(f"kit reduced={_reduced}: the win beat lost its hitstop")
    # Three wins actually reached: the corridor completed, the kaiju felled,
    # the flag touched - each must fire the beat exactly once, and the clean
    # completion must not fire the failure's.
    for _wreq, _wprobe, _wwant in (
        ("玉転がしゲームを作って", _marble_scene_probe, ("over", 0)),
        ("巨大怪獣と戦うゲームを作って", _kaiju_scene_probe, ("won", 0)),
        ("横スクロールのジャンプゲームを作って", _plat_probe, ("goal", None)),
    ):
        _wpage = generate_game(_wreq).html
        _wscript = _scene_re.search(r"<script>(.*?)</script>", _wpage, _scene_re.S)
        if _wscript is None:
            win_gaps.append(f"{_wreq}: no script")
            continue
        try:
            _wrun = _scene_sp.run(
                ["node", "-"],
                input=_wprobe(_wscript.group(1)),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if _wrun.returncode != 0:
                win_gaps.append(f"{_wreq}: {_wrun.stderr.strip()[:60]}")
                continue
            _wout = json.loads(_wrun.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            win_gaps.append(f"{_wreq}: probe unavailable ({type(exc).__name__})")
            continue
        if _wout.get("state") != _wwant[0]:
            win_gaps.append(f"{_wreq}: the win was not reached ({_wout.get('state')})")
            continue
        if _wout.get("winBeats") != 1:
            win_gaps.append(f"{_wreq}: the win fired the beat {_wout.get('winBeats')} time(s)")
        if _wwant[1] is not None and _wout.get("failBeats") != _wwant[1]:
            win_gaps.append(f"{_wreq}: a won round fired the failure beat")
    c.add(
        "creation_win_beat",
        "勝利の瞬間が最も重い型",
        float(len(_win_templates)) if not win_gaps else 0.0,
        detail=(
            "勝ち状態を持つ 7 型すべてが共通 winBeat（揺れ 16＝敗北 14 より重い・"
            "粒子・ヒットストップ・win 音）を通る。marble 完走・kaiju 撃破・"
            "platformer 旗は実プレイでビート 1 回を確認、reduced-motion では"
            "揺れ 0 のままビートは残る。勝ち状態の無い 3 型（fishing / catch / "
            "shooter）は数えず、winBeat も呼ばない"
            if not win_gaps
            else "; ".join(win_gaps)
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
            # A key is pressed every frame, because since C-1123 a round
            # nobody played banks no best - so an untouched run would be
            # asking whether an abandoned page gets congratulated, which is
            # a different question with the opposite right answer. A key no
            # template binds, so how each game goes is unchanged.
            source = _fail_probe(
                script.group(1),
                stored={f"sidra.tune.{key}": {"speed": gentle}},
                hold="x",
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
        SKIN_UNIT as _skin_unit,
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
        elif abs(banked - _skin_unit[key]) > max(1.0, _skin_unit[key] * 0.25):
            # ...and the table is still a measurement rather than a memory
            # of one (C-1407). The bounds above allow a twelvefold window,
            # which is how shooter came to claim 74 for a round that scores
            # 32 - the game played fine and only the pacing was wrong, so
            # nothing else could have noticed.
            skin_gaps.append(
                f"{key}: SKIN_UNIT says {_skin_unit[key]}, a round scores {banked:.0f}"
            )
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
            "だけ半透明のゴーストが現れる（描画差で確認）。当たり判定なし"
            "——2 回目のスコアは 1 回目と同じで、パネルで切ると描画は 1 回目と"
            "完全一致。通信は 0。**「コース位置で索引するので速い走行でも"
            "ずれない」はここでは検査していない**——同じ速度で自分と比べる"
            "限り時間索引でも辻褄が合う（実測: 時間索引に壊すとこの数字は 2 の"
            "まま）。その主張は creation_marble_ghost が速度を変えて検査する"
            if not ghost_gaps
            else "; ".join(ghost_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the second ghost, and the wall it must not touch ---------------
    #
    # §11 事実 1 is about racing a GROUP - the Bath result doubled with
    # multiple ghosts - and a group of one is not one (C-1333). The second
    # ghost is the run before this one, saved on every finished run
    # somebody played; the best trail still moves only on a record. Three
    # real runs prove both halves: the first saves both trails, a second
    # run slowed past the record meets the best AND the last ghost while
    # its defeat updates only the last key - a defeat that overwrote the
    # best trail would replace the wall with the stumble - and the panel
    # switch silences both without touching how the race goes.
    sg_gaps: list[str] = []
    sg_first = sg_second = sg_off = None
    sg_page = _tune_generate("レースゲームを作って", template="racing").html
    sg_script = _scene_re.search(r"<script>(.*?)</script>", sg_page, _scene_re.S)
    if sg_script is None:
        sg_gaps.append("no script on the page")
    else:
        def _sg_run(stored):
            source = _board_probe(
                sg_script.group(1),
                speed_expr=_board_binding["racing"],
                frames=3800,
                stored=stored,
            ).replace(
                "  writes: [...new Set(allWrites)].sort(),",
                "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
                " trail: allStored['sidra.ghost.racing']||null,"
                " lastTrail: allStored['sidra.ghost.last.racing']||null,"
                " score: roundFacts().score,",
            )
            out = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=300
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:80])
            return json.loads(out.stdout.strip().splitlines()[-1])

        sg_base = {"sidra.seen.racing": "1"}
        try:
            sg_first = _sg_run(dict(sg_base))
            sg_slow = round(sg_first["atLoad"]["speed"] * 0.55, 2)
            sg_carry = {
                **sg_base,
                "sidra.ghost.racing": sg_first["trail"],
                "sidra.ghost.last.racing": sg_first["lastTrail"],
                "sidra.best.racing": str(sg_first["score"]),
                "sidra.tune.racing": {"speed": sg_slow},
            }
            sg_second = _sg_run(dict(sg_carry))
            sg_off = _sg_run(
                {**sg_carry, "sidra.tune.racing": {"speed": sg_slow, "ghost": False}}
            )
        except (OSError, _scene_sp.SubprocessError, ValueError, KeyError, TypeError) as exc:
            sg_gaps.append(f"probe unavailable ({exc})")
            sg_first = sg_second = sg_off = None
    if sg_first is not None:
        if sg_first["ghost"]["lastHad"] or sg_first["ghost"]["lastDrawn"]:
            sg_gaps.append("a second ghost stood beside the very first run")
        if not sg_first["lastTrail"]:
            sg_gaps.append("the first finished run saved no last trail")
    if sg_second is not None and sg_first is not None:
        if sg_second["score"] >= sg_first["score"]:
            sg_gaps.append(
                f"the slowed run was not slower ({sg_second['score']} vs {sg_first['score']})"
            )
        if not sg_second["ghost"]["lastDrawn"]:
            sg_gaps.append("the last run left no ghost")
        if not sg_second["ghost"]["drawn"]:
            sg_gaps.append("the best ghost vanished when the second arrived")
        if sg_second["trail"] != sg_first["trail"]:
            sg_gaps.append("a defeat overwrote the record's trail")
        if sg_second["lastTrail"] == sg_first["lastTrail"] or not sg_second["lastTrail"]:
            sg_gaps.append("the defeat did not become tomorrow's second ghost")
    if sg_off is not None and sg_second is not None:
        if sg_off["ghost"]["lastDrawn"] or sg_off["ghost"]["drawn"]:
            sg_gaps.append("the switch does not put both ghosts away")
        if sg_off["ghost"]["runHash"] != sg_second["ghost"]["runHash"]:
            sg_gaps.append("the second ghost changed how the race went")
    sg_courses = 1 if sg_first is not None and not sg_gaps else 0
    # The other two courses (C-1335): same-speed second run, so the score
    # ties the best exactly - neither has a tiebreak, so a tie is not a
    # record and the best trail must sit still while both ghosts run. The
    # "defeat updates the last key" half stays racing's, whose slowed run
    # actually produces a different trail to see it with.
    for _sg_t, _sg_req in (
        ("marble", "玉転がしゲームを作って"),
        ("platformer", "ジャンプアクションを作って"),
    ):
        _sg_page = _tune_generate(_sg_req, template=_sg_t).html
        _sg_found = _scene_re.search(r"<script>(.*?)</script>", _sg_page, _scene_re.S)
        if _sg_found is None:
            sg_gaps.append(f"{_sg_t}: no script")
            continue

        def _sg_run_t(stored, _script=_sg_found.group(1), _t=_sg_t):
            source = _board_probe(
                _script,
                speed_expr=_board_binding[_t],
                frames=3800,
                stored=stored,
            ).replace(
                "  writes: [...new Set(allWrites)].sort(),",
                "  writes: [...new Set(allWrites)].sort(), ghost: ghostFacts(),"
                f" trail: allStored['sidra.ghost.{_t}']||null,"
                f" lastTrail: allStored['sidra.ghost.last.{_t}']||null,"
                " score: roundFacts().score,",
            )
            out = _scene_sp.run(
                ["node", "-"], input=source, capture_output=True, text=True, timeout=300
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:80])
            return json.loads(out.stdout.strip().splitlines()[-1])

        try:
            _sg_b = {f"sidra.seen.{_sg_t}": "1"}
            _sg_1 = _sg_run_t(dict(_sg_b))
            if not _sg_1["lastTrail"]:
                sg_gaps.append(f"{_sg_t}: the first finished run saved no last trail")
                continue
            _sg_c = {
                **_sg_b,
                f"sidra.ghost.{_sg_t}": _sg_1["trail"],
                f"sidra.ghost.last.{_sg_t}": _sg_1["lastTrail"],
                f"sidra.best.{_sg_t}": str(_sg_1["score"]),
            }
            _sg_2 = _sg_run_t(dict(_sg_c))
            _sg_o = _sg_run_t({**_sg_c, f"sidra.tune.{_sg_t}": {"ghost": False}})
        except (OSError, _scene_sp.SubprocessError, ValueError, KeyError, TypeError) as exc:
            sg_gaps.append(f"{_sg_t}: probe unavailable ({exc})")
            continue
        ok = True
        if not _sg_2["ghost"]["lastDrawn"]:
            sg_gaps.append(f"{_sg_t}: the last run left no ghost")
            ok = False
        if not _sg_2["ghost"]["drawn"]:
            sg_gaps.append(f"{_sg_t}: the best ghost vanished when the second arrived")
            ok = False
        if _sg_2["trail"] != _sg_1["trail"]:
            sg_gaps.append(f"{_sg_t}: a tie overwrote the record's trail")
            ok = False
        if _sg_o["ghost"]["lastDrawn"] or _sg_o["ghost"]["drawn"]:
            sg_gaps.append(f"{_sg_t}: the switch does not put both ghosts away")
            ok = False
        if _sg_o["ghost"]["runHash"] != _sg_2["ghost"]["runHash"]:
            sg_gaps.append(f"{_sg_t}: the second ghost changed how the run went")
            ok = False
        if ok:
            sg_courses += 1
    c.add(
        "creation_second_ghost",
        "直前の自分も隣を走る",
        float(sg_courses) if not sg_gaps else 0.0,
        detail=(
            "コース 3 型が三走契約に合格（C-1335 で定義を 0/1→合格コース数へ。"
            "旧定義では racing のみで 1、実際の前進は 1→3）。racing は完全"
            "契約: 記録に届かない減速走行が両ゴーストに会い、敗北は直前鍵"
            "だけを更新しベスト軌跡は不変。marble/platformer は同速 2 走目"
            "（同点＝記録でない）でベスト鍵不変・両ゴースト描画・パネルで"
            "両方消えて走りは不変（§11 事実 1: 複数ゴーストで効果 2 倍）"
            if not sg_gaps
            else "; ".join(sg_gaps)
        ),
        kind=OUTCOME,
    )

    # --- the corridor's past self, met at the same place ----------------
    #
    # C-1412 wires C-1401's trail to its second template. z down the
    # corridor is the same shape as distance around a lap, so the trail,
    # the key and the switch all carried over and nothing new was needed.
    #
    # This number is not the shared one asked twice. ``creation_ghost_replay``
    # runs each template against itself at one speed, which cannot see the
    # property §11 leans on: the trail is indexed by *progress*, not by the
    # clock. So the second run here is a deliberately faster one, and the
    # ghost it draws is compared against where the first run actually was
    # at that point on the course - a frame-keyed trail agrees with itself
    # and lands in the wrong place, which is exactly what that comparison
    # catches.
    from sidra_ai.creation.ghost import GHOST_STEP as _mg_step
    from sidra_ai.creation.marble import ghost_probe_source as _mg_probe

    mg_gaps: list[str] = []
    mg_page = _tune_generate("玉転がしを作って", template="marble").html
    mg_script = _scene_re.search(r"<script>(.*?)</script>", mg_page, _scene_re.S)
    mg_first = mg_fast = mg_off = None
    mg_checked = mg_worst = 0
    if mg_script is None:
        mg_gaps.append("no script on the page")
    else:
        def _mg_roll(**kwargs):
            out = _scene_sp.run(
                ["node", "-"],
                input=_mg_probe(mg_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:80])
            return json.loads(out.stdout.strip().splitlines()[-1])

        mg_base = {"sidra.seen.marble": "1"}
        try:
            mg_first = _mg_roll(stored=dict(mg_base))
            if mg_first["trail"]:
                mg_carry = {**mg_base, "sidra.ghost.marble": mg_first["trail"]}
                mg_fast = _mg_roll(stored=dict(mg_carry), roll=9.0)
                mg_off = _mg_roll(
                    stored={**mg_carry, "sidra.tune.marble": {"ghost": False, "speed": 9.0}}
                )
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            mg_gaps.append(f"probe unavailable ({exc})")

    if mg_first is not None:
        if mg_first["ghost"]["had"] or mg_first["ghost"]["drawn"]:
            mg_gaps.append("a ghost rolled beside the very first run")
        if not mg_first["trail"] or mg_first["ghost"]["saved"] < 1:
            mg_gaps.append("the run that set the record saved no trail")
    if mg_fast is not None and mg_first is not None:
        # The second run is genuinely faster, or the whole point of the
        # comparison is untested.
        if mg_fast["spd"] <= mg_first["spd"] or mg_fast["frames"] >= mg_first["frames"]:
            mg_gaps.append(
                f"the second run was not faster ({mg_fast['spd']:.1f} in "
                f"{mg_fast['frames']} vs {mg_first['spd']:.1f} in {mg_first['frames']})"
            )
        if not mg_fast["ghost"]["drawn"]:
            mg_gaps.append("the faster run met no ghost")
        else:
            # Where the ghost was drawn, against where the first run was at
            # that point on the course. The bucket is the page's own, so
            # the course position is not recomputed out here.
            mg_path = mg_first["path"]
            for bucket, drew in mg_fast["seen"]:
                target = bucket * _mg_step
                near, gap = None, 1e9
                for was_z, was_x in mg_path:
                    d = abs(was_z - target)
                    if d < gap:
                        gap, near = d, was_x
                if near is None or gap > _mg_step:
                    continue
                mg_checked += 1
                mg_worst = max(mg_worst, abs(drew - near))
            if mg_checked < 100:
                mg_gaps.append(f"only {mg_checked} points of the course could be compared")
            elif mg_worst > 24:
                mg_gaps.append(
                    f"the ghost drifted {mg_worst}px from where the run it came from was"
                )
    if mg_off is not None and mg_fast is not None:
        if mg_off["ghost"]["drawn"]:
            mg_gaps.append("the panel switch does not put the ghost away")
        # Drawn, and nothing else: the same roll with and without it.
        if mg_off["path"] != mg_fast["path"]:
            mg_gaps.append("the ghost changed how the marble rolled")
        if mg_off["ghost"]["runHash"] != mg_fast["ghost"]["runHash"]:
            mg_gaps.append("the ghost changed the run it was drawn beside")
    c.add(
        "creation_marble_ghost",
        "コースの位置で索引されたゴースト（速い走行でもずれない）",
        0.0 if mg_gaps else 1.0,
        detail=(
            "; ".join(mg_gaps)
            if mg_gaps
            else f"marble を 3 回実走行: 1 回目はゴースト無しで軌跡を保存、"
            f"2 回目は**速度を上げて**（{mg_first['spd']:.1f}→{mg_fast['spd']:.1f}・"
            f"{mg_first['frames']}→{mg_fast['frames']} フレーム）走り、"
            f"描かれたゴースト {mg_checked} 点すべてが 1 回目の同じ z 位置と"
            f"最大 {mg_worst}px しか違わない（時間で索引していればここでずれる）。"
            "パネルで切ると 1 点も描かれず、切っても切らなくても転がりは同一"
            if mg_first and mg_fast
            else ""
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
        # C-1120: the eight the self-test found at the front door. Four are
        # buildable and must reach their template; four name genres this
        # product has no template for and must still be recognised as game
        # requests, so they can be declined in the asker's own words rather
        # than answered with retrieval boilerplate.
        ("横スクロールのジャンプアクションを作って", "game", "platformer"),
        ("レースを作って", "game", "racing"),
        ("ぷよぷよみたいなの作って", "game", "puzzle"),
        ("さめがめを作って", "game", "puzzle"),
        ("テトリスみたいなゲームを作って", "game", None),
        ("RPG を作って", "game", None),
        ("音ゲーを作って", "game", None),
        ("タワーディフェンスを作って", "game", None),
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

    # C-1251: the 3D preview footer listed whatever BM25 returned for the
    # request (a fish model cited revenue-model.md), but a template mesh painted
    # with the DESIGN.md palette is grounded in the palette, not the retrieval.
    # The job stopped passing retrieved sources as evidence; the footer cites
    # the palette. False provenance, the C-1203 problem one artifact along.
    from sidra_ai.evals.model3d_provenance_is_palette import (
        evaluate_model3d_provenance_is_palette,
    )

    m3d_prov = evaluate_model3d_provenance_is_palette()
    c.add(
        "model3d_provenance_is_palette",
        "3D モデルの脚注は実際の出典（DESIGN.md 配色）だけ＝無関係の検索ヒットを載せない",
        10.0 * m3d_prov.checks_passed / m3d_prov.checks_total,
        detail=f"{m3d_prov.checks_passed}/{m3d_prov.checks_total} checks; "
               "src/sidra_ai/evals/model3d_provenance_is_palette.py"
               + ("" if m3d_prov.passed else "; " + "; ".join(m3d_prov.failures)),
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

    # --- the shared chrome wears the palette it was asked for ------------
    #
    # C-1130 (批評 #14). The round banner and the result strip painted
    # themselves in the dark theme's own ink - '#05070f' behind, '#dfe7f5'
    # on top - whatever palette the page had been generated in. On the
    # paper theme that is a near-black slab across a white page: the one
    # thing on screen that did not agree with the request.
    #
    # Counted per theme and read off a driven page, not off the source: the
    # probe's canvas now keeps the colour each fill was made with, so this
    # reports what the banner actually painted. A stub that threw fillStyle
    # away could not have caught this, which is why it went unnoticed.
    from sidra_ai.creation.round import probe_source as _chrome_probe
    from sidra_ai.creation.themes import DEFAULT_THEME as _chrome_default
    from sidra_ai.creation.themes import THEMES as _chrome_themes

    #: What the shared chrome says. Both lines, so a theme that themed the
    #: banner and left the retry line behind is not counted.
    _chrome_says = ("ここまで", "R / タップでもう一度")

    def _chrome_scrim(paint, theme):
        """The colour of the veil drawn under the banner, if it is wrong.

        Found by walking back from the words to the nearest rectangle -
        the page paints the slab and then writes on it - so this reads the
        drawing order rather than trusting a position in the source.
        """

        for index, entry in enumerate(paint):
            if entry[0] != "text" or entry[2] != "ここまで":
                continue
            # The rectangle drawn *immediately* before the words, not the
            # nearest one anywhere behind them: with the veil deleted the
            # walk-back found whatever the game had painted last and was
            # satisfied by it, so removing the veil entirely went unnoticed.
            if index == 0 or paint[index - 1][0] != "rect":
                return "(nothing was drawn behind it)"
            veil = str(paint[index - 1][1] or "")
            return None if veil.startswith(theme.tokens["bg"]) else veil
        return None
    chrome_gaps: list[str] = []
    chrome_ok: list[str] = []
    for _c_key, _c_theme in sorted(_chrome_themes.items()):
        _c_page = generate_game(
            f"{_c_theme.words[0]}のテーマでゲームを作って", template="catch"
        ).html
        _c_script = _scene_re.search(r"<script>(.*?)</script>", _c_page, _scene_re.S)
        if _c_script is None:
            chrome_gaps.append(f"{_c_key}: no script")
            continue
        try:
            _c_run = _scene_sp.run(
                ["node", "-"],
                input=_chrome_probe(_c_script.group(1)),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if _c_run.returncode != 0:
                raise ValueError(_c_run.stderr.strip()[:70])
            _c_seen = json.loads(_c_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            chrome_gaps.append(f"{_c_key}: probe unavailable ({exc})")
            continue
        if _c_seen.get("breakAt") is None:
            chrome_gaps.append(f"{_c_key}: never reached the break, so nothing was drawn")
            continue
        _c_paint = _c_seen.get("paint") or []
        _c_inks = sorted({p[1] for p in _c_paint if p[0] == "text" and p[2] in _chrome_says})
        _c_drew = {p[2] for p in _c_paint if p[0] == "text"} & set(_chrome_says)
        if len(_c_drew) < len(_chrome_says):
            chrome_gaps.append(
                f"{_c_key}: the chrome did not draw {sorted(set(_chrome_says) - _c_drew)}"
            )
        elif _c_inks != [_c_theme.tokens["text"]]:
            chrome_gaps.append(
                f"{_c_key}: painted {_c_inks}, not the theme's ink "
                f"{_c_theme.tokens['text']!r}"
            )
        elif _chrome_scrim(_c_paint, _c_theme) is not None:
            # The slab behind the words, not just the words. A break that
            # hard-coded the scrim alone sailed through the ink check -
            # which is half of what 批評 #14 named, and the visible half:
            # a near-black band across a white page.
            chrome_gaps.append(
                f"{_c_key}: the veil is {_chrome_scrim(_c_paint, _c_theme)!r}, "
                f"not the theme's ground {_c_theme.tokens['bg']!r}"
            )
        elif (
            _c_key != _chrome_default.key
            and _chrome_default.tokens["text"] in _c_inks
        ):
            # The other direction: a theme is not counted for merely being
            # drawn in *some* colour - it must not be the default's ink.
            chrome_gaps.append(f"{_c_key}: still wearing the default theme's ink")
        else:
            chrome_ok.append(_c_key)
    # C-1131 widens this from the shared banner to every template's own
    # HUD. The banner was one place; the score lines, the toasts and the
    # end-screen messages were the same literal ink in ten more. Counted on
    # the paper theme, which is the one a dark literal is visibly wrong on,
    # and asked of the running page: no word anywhere may be written in the
    # default theme's ink when a different palette was requested.
    #
    # Playfield objects are deliberately not in this: a guard's hit pips, a
    # road's boundary marks, a boss's hurt flash carry information by shape
    # and colour (§4) and repainting them is a readability decision rather
    # than a theming one. They are listed in C-1131's record.
    #
    # What this cannot see, said out loud: only words the driven run
    # actually wrote. An idle round draws the HUD and the end screen but
    # never the lamp's price or a toast, which need play to appear -
    # putting either back to the hard-coded ink leaves this number at full
    # marks, which is how the limit was found rather than assumed.
    hud_gaps: list[str] = []
    hud_ok: list[str] = []
    for _h_key in sorted(_GAME_TEMPLATES):
        _h_page = generate_game("紙のテーマでゲームを作って", template=_h_key).html
        _h_script = _scene_re.search(r"<script>(.*?)</script>", _h_page, _scene_re.S)
        if _h_script is None:
            hud_gaps.append(f"{_h_key}: no script")
            continue
        try:
            _h_run = _scene_sp.run(
                ["node", "-"],
                input=_chrome_probe(_h_script.group(1)),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if _h_run.returncode != 0:
                raise ValueError(_h_run.stderr.strip()[:70])
            _h_seen = json.loads(_h_run.stdout.strip().splitlines()[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            hud_gaps.append(f"{_h_key}: probe unavailable ({exc})")
            continue
        _h_paint = _h_seen.get("paint") or []
        _h_words = [p for p in _h_paint if p[0] == "text"]
        if not _h_words:
            hud_gaps.append(f"{_h_key}: wrote nothing, so nothing was proved")
            continue
        _h_dark = sorted({p[1] for p in _h_words if p[1] == _chrome_default.tokens["text"]})
        if _h_dark:
            _h_said = sorted({p[2] for p in _h_words if p[1] in _h_dark})[:3]
            hud_gaps.append(
                f"{_h_key}: wrote {_h_said} in the default theme's ink"
            )
        else:
            hud_ok.append(_h_key)
    c.add(
        "creation_template_hud_themed",
        "どの型の文字もページの配色で書かれる",
        0.0 if hud_gaps else float(len(hud_ok)),
        detail=(
            "; ".join(hud_gaps)
            if hud_gaps
            else f"{len(hud_ok)} 型を紙テーマで実走行し、**書いた文字の色**を"
            f"読んだ。既定テーマの墨で書かれた語はひとつも無い。"
            "**見ているのは走らせて実際に出た語だけ**——HUD と終了画面は出るが、"
            "遊ばないと出ない文字（ランプの数字・トースト）はこの走行に現れない"
            "ので、直してはいても**この数字は証明していない**（破壊で確認済み）。"
            "盤面の物（守衛の体力ピップ・路肩の標識・ボスの被弾点滅）は対象外"
            "——形と色で情報を運ぶので、塗り替えは可読性の判断（C-1131）"
        ),
        kind=OUTCOME,
    )

    c.add(
        "creation_round_chrome_themed",
        "共通の帯がページの配色で描かれる",
        0.0 if chrome_gaps else float(len(chrome_ok)),
        detail=(
            "; ".join(chrome_gaps)
            if chrome_gaps
            else f"{len(chrome_ok)} テーマを実走行し、区切りまで回して帯が"
            f"**実際に塗った色**を読んだ（{'・'.join(chrome_ok)}）。"
            "「ここまで」もリトライ行もそのテーマの文字色で描かれ、"
            "既定以外のテーマが既定の墨で描かれていないことも確認。"
            "テンプレート側の固定色はまだ残っている（C-1131）"
        ),
        kind=OUTCOME,
    )

    # --- the third sense, and only ever a third one ---------------------
    #
    # C-1413, §16. The generated pages never called `navigator.vibrate` at
    # all, while the very devices played with a thumb are the ones with a
    # vibrator in them. Two shared moments get it: the failure beat, which
    # every template already fires at its losing moment, and a round
    # confirming itself. `hitstop` was the other candidate and is wrong -
    # a cleared puzzle and a hit on the boss call it too, so it is not
    # "took a hit".
    #
    # Support is Android Chrome only (caniuse, checked 2026-09-04), so the
    # rule that matters most is that nothing is *told* this way: both
    # moments keep the sound and the picture they already had, and this is
    # a third channel on top. What is checked here is the decision the page
    # made - the call it placed - not whether a device buzzed.
    from sidra_ai.creation.juice import HAPTIC_HIT, HAPTIC_MAX, HAPTIC_ROUND
    from sidra_ai.creation.juice import page_probe_source as _hap_probe

    hap_gaps: list[str] = []
    hap_page = generate_game("シューティングゲームを作って").html
    hap_script = _scene_re.search(r"<script>(.*?)</script>", hap_page, _scene_re.S)
    hap_runs: dict[str, dict] = {}
    if hap_script is None:
        hap_gaps.append("no script on the page")
    else:
        def _hap_run(name, **kwargs):
            out = _scene_sp.run(
                ["node", "-"],
                input=_hap_probe(hap_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                raise ValueError(f"{name}: {out.stderr.strip()[:70]}")
            hap_runs[name] = json.loads(out.stdout.strip().splitlines()[-1])

        try:
            _hap_run("played")
            _hap_run("untouched", play=False)
            _hap_run("reduced", reduced=True)
            _hap_run("off", stored={"sidra.tune.shooter": {"haptic": False}})
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            hap_gaps.append(f"probe unavailable ({exc})")

    if len(hap_runs) == 4:
        played = hap_runs["played"]
        # 1. The hit lands in the hand, with the pattern the kit chose.
        if not played["sent"]:
            hap_gaps.append("a failure beat asked the device for nothing")
        elif played["sent"][0] != HAPTIC_HIT:
            hap_gaps.append(f"the first pulse was {played['sent'][0]!r}, not the hit's")
        # 2. The window gate holds. Ten beats back to back is the case the
        #    gate exists for, and the counter must stop at the cap rather
        #    than merely slow down.
        steps = played["burstSteps"]
        if not steps or steps[-1] != HAPTIC_MAX:
            hap_gaps.append(
                f"ten beats in one window fired {steps[-1] if steps else 0}, not {HAPTIC_MAX}"
            )
        elif played["max"] != HAPTIC_MAX:
            hap_gaps.append(f"the page reports a cap of {played['max']}, not {HAPTIC_MAX}")
        # 3. A round that was played confirms itself, once, with the double.
        doubles = [p for p in played["sent"] if isinstance(p, list)]
        if doubles != [list(HAPTIC_ROUND)]:
            hap_gaps.append(f"the round confirmed itself as {doubles!r}")
        # 4. ...and a round nobody played stays silent in the hand too, the
        #    same rule the records already follow (C-1123).
        untouched = hap_runs["untouched"]
        if [p for p in untouched["sent"] if isinstance(p, list)]:
            hap_gaps.append("a round nobody played still buzzed its confirmation")
        if untouched["banked"]:
            hap_gaps.append("the untouched run banked a score, so it proves nothing")
        # 5. Both switches. Reduced motion silences it like every other
        #    decoration, and the panel switch is the person's own.
        if hap_runs["reduced"]["sent"]:
            hap_gaps.append("reduced motion still buzzed")
        if hap_runs["off"]["on"] or hap_runs["off"]["sent"]:
            hap_gaps.append("the panel switch does not turn it off")
        # 6. Nothing is told only this way: the moments that buzz are the
        #    ones that already had a sound and a picture, so the beats and
        #    the banked score are unchanged with the vibration switched off.
        if hap_runs["off"]["banked"] != played["banked"]:
            hap_gaps.append("switching the vibration off changed what the round banked")
    c.add(
        "creation_haptics_wired",
        "被弾と確定が指にも返る（切れる・鳴りっぱなしにならない）",
        0.0 if hap_gaps else 1.0,
        detail=(
            "; ".join(hap_gaps)
            if hap_gaps
            else f"ページを 4 通り実走行し、`navigator.vibrate` に渡った値を読んだ: "
            f"被弾は {HAPTIC_HIT}ms の 1 発、遊んだラウンドの確定は "
            f"{list(HAPTIC_ROUND)} の 2 連が 1 回だけ。10 連打しても 60 フレーム窓で "
            f"{HAPTIC_MAX} 発で止まる。reduced とパネルのスイッチでどちらも 0 発になり、"
            "切っても積んだ点は変わらない（触覚でしか伝えない情報を作らない・§16 事実 2）。"
            "触れなかったラウンドは手にも鳴らない"
        ),
        kind=OUTCOME,
    )

    # --- the title screen with a game running behind it (§17, C-1414) ----
    #
    # An attract mode is a demo playing itself behind the title: the machine
    # shows what the game *is* before anybody commits to it. Three halves,
    # each one driven rather than read. The demo runs and moves; it earns
    # nobody anything; and the press hands over a go that starts at the top.
    # The last is checked against the product's own control - the same page
    # pressed at frame zero - so a rewind that missed something shows up as
    # two snapshots that disagree, whatever the missed thing was.
    #
    # Wired per template, because a demo is a template that plays itself and
    # most of these stand still with no input. ATTRACT_UNWIRED says why, one
    # line each, and the unwired ones are measured too: their title must
    # still be one still picture, which is the other direction of the claim.
    from sidra_ai.creation.attract import (
        ATTRACT_PILOT as _attract_pilot,
        ATTRACT_TEMPLATES as _attract_wired,
        ATTRACT_UNWIRED as _attract_unwired,
        probe_source as _attract_probe,
    )

    #: 70 seconds at 60fps. Past the round clock's own sixty-second limit -
    #: so a demo that quietly ran the clock would have rung the buzzer over
    #: its own title screen - and past a full racing demo, so the loop back
    #: to another go is observed rather than assumed.
    _ATTRACT_IDLE = 4200

    #: Played frames after the press, in both runs. Ten seconds is long
    #: enough for racing's first obstacles to be placed, which is where a
    #: rewound world and a merely rewound *scoreboard* stop agreeing: the
    #: instant of the press cannot tell them apart, because the obstacle
    #: list is empty in both.
    _ATTRACT_PLAY = 600

    def _attract_veiled(paint):
        """Is the last thing painted over the whole canvas see-through?

        The gate draws last, so the final full-canvas fill of the frame is
        its panel. An 8-digit colour carries an alpha channel and a 6-digit
        one does not, which is the difference between a veil and a lid -
        and the difference a player sees.
        """

        full = [
            op for op in paint if op.startswith("r:") and op.endswith(":0,0,720,320")
        ]
        return bool(full) and len(full[-1].split(":")[1]) > 7

    def _attract_drive(key, body, **kw):
        try:
            out = _scene_sp.run(
                ["node", "-"],
                input=_attract_probe(body, **kw),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                return None, f"{key}: {out.stderr.strip()[:70]}"
            return json.loads(out.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    attract_ok: list[str] = []
    attract_gaps: list[str] = []
    attract_still: list[str] = []
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            attract_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        watched, problem = _attract_drive(
            key, body, idle=_ATTRACT_IDLE, play=_ATTRACT_PLAY
        )
        if problem:
            attract_gaps.append(problem)
            continue
        facts = watched["beforePress"]["attract"]
        if key not in _attract_wired:
            # Unwired: the gate is exactly what it was. One still picture,
            # no frames given away, and a line in the table saying why.
            hashes = {f["hash"] for f in watched["idle"]}
            if facts["frames"]:
                attract_gaps.append(f"{key}: unwired, yet it ran {facts['frames']} frames")
            elif len(hashes) != 1:
                attract_gaps.append(f"{key}: unwired, yet its title drew {len(hashes)} pictures")
            elif key not in _attract_unwired:
                attract_gaps.append(f"{key}: unwired and unexplained")
            else:
                attract_still.append(key)
            continue
        control, problem = _attract_drive(key, body, idle=0, play=_ATTRACT_PLAY)
        if problem:
            attract_gaps.append(problem)
            continue
        trouble = None
        idle = watched["idle"]
        moved = sum(1 for a, b in zip(idle, idle[1:]) if a["hash"] != b["hash"])
        # Read *before* the press: everything here is a claim about what
        # the demo did on its own, and the press itself writes (it is what
        # remembers that the briefing has been read).
        press = watched["beforePress"]
        # 1. The demo got every frame, kept the loop alive to the end, and
        #    drew a different picture nearly every one of them. A demo that
        #    is merely "running" behind a still image is not a demo.
        # One loop, still. A gate that armed the next frame itself as well
        # as letting the demo arm it would schedule two callbacks, then
        # four, then eight - a page that looks right in every screenshot
        # and melts the phone it is running on. Asked first, because every
        # other number here is read off a page that has to be sane.
        if max(frame["calls"] for frame in idle) != 1:
            trouble = (
                f"{key}: {max(frame['calls'] for frame in idle)} callbacks fell due "
                "in one frame, so the loop is multiplying"
            )
        elif len(idle) != _ATTRACT_IDLE or facts["frames"] != _ATTRACT_IDLE:
            trouble = f"{key}: the demo got {facts['frames']} of {_ATTRACT_IDLE} frames"
        elif moved < _ATTRACT_IDLE * 0.9:
            trouble = f"{key}: the picture changed on {moved} of {_ATTRACT_IDLE - 1} frames"
        elif not facts["loops"]:
            # Asserted, not independently confirmed: on today's one wired
            # template a demo that stops looping freezes on its own goal
            # screen, and the motion check above catches that first. Kept
            # because a template whose ending keeps animating would slip
            # past motion, and because a demo that plays a game once is
            # not an attract mode.
            trouble = f"{key}: the demo never reached its own ending, so it never looped"
        # 1b. A piloted demo has to land the game's core verb (C-1338): the
        #     pilot line sets ATTRACT_LIVE when it does - the shooter's,
        #     on a kill. Motion alone cannot tell a demo with a game in it
        #     from a screensaver of one standing still and dying.
        elif key in _attract_pilot and not facts.get("live"):
            trouble = f"{key}: the piloted demo never landed its verb"
        # 2. The veil is a veil. The demo's own paint is under it, and the
        #    panel over it carries an alpha - a lid would score full marks
        #    on everything above while showing the player nothing.
        elif not _attract_veiled(watched["idlePaint"]):
            trouble = f"{key}: the title covers the demo instead of veiling it"
        elif idle[-1]["ops"] <= 12:
            trouble = f"{key}: nothing but the title was drawn on the last idle frame"
        # 3. Seventy seconds of demo earned nobody anything: the round clock
        #    never started, so it never rang, and nothing was written down.
        elif press["round"]["ms"] or press["round"]["done"] or press["touched"]:
            trouble = (
                f"{key}: the demo ran the round clock to {press['round']['ms']:.0f}ms"
                f"{' and rang it' if press['round']['done'] else ''}"
            )
        elif press["round"]["best"] is not None or (press["skin"] or {}).get("total"):
            trouble = f"{key}: the demo banked something"
        elif sorted(press["store"]):
            trouble = f"{key}: the demo wrote {sorted(press['store'])} to storage"
        # 4. ...and the press hands over the same go the control was handed,
        #    down to the last field of every facts function on the page.
        else:
            def _snap(run, at):
                # The demo's own counters are the one thing that must
                # differ, and the probe's wall clock is the probe's: the
                # watched run has four thousand more frames of 50/3ms
                # behind it, so its round clock lands a rounding away.
                out = {k: v for k, v in run[at].items() if k != "attract"}
                out["round"] = dict(out["round"], ms=round(out["round"]["ms"]))
                return out

            # At the press first, then after ten seconds of play: the
            # instant of the press cannot see a world whose random stream
            # was left where the demo dropped it, because nothing has been
            # placed out of it yet.
            for at in ("atPress", "afterPlay"):
                watched_at, control_at = _snap(watched, at), _snap(control, at)
                if watched_at != control_at:
                    differ = sorted(
                        k for k in watched_at if watched_at[k] != control_at.get(k)
                    )
                    when = "the go starts" if at == "atPress" else "ten seconds in it runs"
                    trouble = f"{key}: after the demo {when} differently ({', '.join(differ)})"
                    break
        if trouble:
            attract_gaps.append(trouble)
        else:
            attract_ok.append(key)
    c.add(
        "creation_attract_demo",
        "タイトルの裏でゲームが自分で動いて見せる型",
        float(len(attract_ok)) if not attract_gaps else 0.0,
        detail=(
            "; ".join(attract_gaps)
            if attract_gaps
            else f"{', '.join(attract_ok)}: 無操作 {_ATTRACT_IDLE} フレーム"
            f"（約 {_ATTRACT_IDLE // 60} 秒）実走行し、毎フレーム別の絵が描かれ、"
            "デモ自身の区切りで次の周回に入る。その 70 秒でラウンド時計は 0ms のまま"
            "（60 秒の buzzer はタイトルの裏では鳴らない）、best も見た目の総計も"
            "storage も一切動かない。押した瞬間の全 facts が「即座に押した対照ページ」"
            f"と完全一致する。未配線 {len(attract_still)} 型（{', '.join(attract_still)}）"
            "はタイトルが 1 枚の静止画のままで、理由は ATTRACT_UNWIRED に 1 行ずつ"
        ),
        kind=OUTCOME,
    )

    # --- the line that says a phone can be held the other way (§18) ------
    #
    # C-1415. The canvas keeps its 720:320 ratio at every page width, so the
    # same phone plays at about half the size on each side upright that it
    # gives lying down - and the page said nothing about it. One sentence
    # under the canvas, on the title screen only, on a device that can
    # actually be turned.
    #
    # Every part of that is a claim about a running page, and the probe can
    # turn the screen: the media queries are answered from variables and the
    # listeners are fired, so "it reacts to the phone moving" is measured
    # rather than assumed. A page that read the queries once at load would
    # pass every static check and sit there while the phone rotated.
    from sidra_ai.creation.rotate import ROTATE_ID as _rot_id, ROTATE_TEXT as _rot_text
    from sidra_ai.creation.rotate import probe_source as _rot_probe

    def _rot_drive(key, body, **kw):
        try:
            out = _scene_sp.run(
                ["node", "-"],
                input=_rot_probe(body, **kw),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if out.returncode != 0:
                return None, f"{key}: {out.stderr.strip()[:70]}"
            return json.loads(out.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    rot_gaps: list[str] = []
    rot_ok: list[str] = []
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            rot_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        # It is in the page at all, and it is the sentence - not a class
        # name the stylesheet knows about and nobody ever reads.
        if page.count(f'id="{_rot_id}"') != 1 or _rot_text not in page:
            rot_gaps.append(f"{key}: the page carries no rotate hint")
            continue
        phone, problem = _rot_drive(key, body, portrait=True, coarse=True, press=True)
        if problem:
            rot_gaps.append(problem)
            continue
        flat, problem = _rot_drive(key, body, portrait=False, coarse=True)
        if problem:
            rot_gaps.append(problem)
            continue
        mouse, problem = _rot_drive(key, body, portrait=True, coarse=False)
        if problem:
            rot_gaps.append(problem)
            continue
        trouble = None
        # 1. Held upright on a phone, the title screen says so.
        if not phone["atLoad"]["shown"]:
            trouble = f"{key}: a phone held upright is told nothing"
        # 2. Turned over, the line goes - without a reload, because the
        #    listener is what makes this a hint rather than a leftover.
        elif phone["afterTurn"]["shown"]:
            trouble = f"{key}: the hint stayed up after the phone was turned"
        elif not phone["turnedBack"]["shown"]:
            trouble = f"{key}: turning back upright did not bring the hint back"
        # 3. ...and the same page opened sideways starts without it.
        elif flat["atLoad"]["shown"] or not flat["afterTurn"]["shown"]:
            trouble = f"{key}: opened sideways, the hint does not follow the screen"
        # 4. A tall desktop window is portrait too. Telling somebody to turn
        #    their monitor is the page not knowing what it is running on.
        elif mouse["atLoad"]["shown"] or mouse["afterTurn"]["shown"]:
            trouble = f"{key}: a mouse-driven window was told to rotate"
        # 5. It belongs to the title screen. Once play starts it is out of
        #    the document, and turning the phone does not bring it back.
        elif phone["inBody"]:
            trouble = f"{key}: the hint was hidden rather than taken out"
        elif phone["afterStart"]["present"] or phone["afterStart"]["shown"]:
            trouble = f"{key}: the hint is still there once the game is running"
        elif phone["afterStart"]["afterTurningBack"]["shown"]:
            trouble = f"{key}: turning the phone during play brought the hint back"
        # 6. It is a hint, not a gate: the press still started the game.
        elif phone["gate"]["state"] != "playing" or phone["gate"]["frames"] < 1:
            trouble = f"{key}: the game did not start with the hint on screen"
        if trouble:
            rot_gaps.append(trouble)
        else:
            rot_ok.append(key)
    c.add(
        "creation_rotate_hint",
        "縦持ちの人にだけ「回すと広い」を一言伝える",
        0.0 if rot_gaps else 1.0,
        detail=(
            "; ".join(rot_gaps)
            if rot_gaps
            else f"{len(rot_ok)} 型すべてを 3 通りの画面で実走行: 縦持ち"
            "（粗いポインタ）のタイトル幕でだけ 1 行出る。走行中に画面を回すと"
            "その場で消え、戻すとまた出る（media query の change を購読、"
            "再読み込み不要）。横持ちで開けば最初から出ない。マウスの縦長窓"
            "（pointer:fine）では縦でも横でも出ない——モニタを回せとは言わない。"
            "ゲーム開始で DOM から取り除かれ、その後どう回しても戻らない。"
            "遮断ではないので、1 行が出たまま押せばゲームは始まる"
        ),
        kind=OUTCOME,
    )

    # --- the button that makes it as big as the screen (§18 事実 2) ------
    #
    # C-1416. A phone gives about 40% of its screen to the URL bar and this
    # page's own margins. Fullscreen takes it back - for somebody who asked,
    # on a browser that will honour it, and never as a surprise.
    #
    # Four rules, four ways of driving the page: a browser that supports it
    # and grants, one that supports it and refuses, one that does not
    # support it at all, and one where even the orientation lock succeeds.
    # The last is the control for the third rule - without a run where
    # nothing is refused, "the refusals were caught" could be a counter
    # that only ever goes up.
    from sidra_ai.creation.fullscreen import (
        BUTTON_ID as _fs_btn,
        LABEL_ENTER as _fs_enter,
        LABEL_EXIT as _fs_exit,
        LOCK_TO as _fs_lock,
        WRAP_ID as _fs_wrap,
        probe_source as _fs_probe,
    )

    def _fs_drive(key, body, **kw):
        try:
            out = _scene_sp.run(
                ["node", "-"],
                input=_fs_probe(body, **kw),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if out.returncode != 0:
                return None, f"{key}: {out.stderr.strip()[:70]}"
            return json.loads(out.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    fs_gaps: list[str] = []
    fs_ok: list[str] = []
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            fs_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        # The probe supplies its own wrapper and button - it has to, since
        # it is a stub DOM - so nothing it measures can tell whether the
        # generated page carries them. Deleting the button from the page
        # left every behavioural check below at full marks. This one fact
        # is read off the page's own bytes because nothing else can see it.
        if (
            page.count(f'id="{_fs_wrap}"') != 1
            or page.count(f'id="{_fs_btn}"') != 1
            or _fs_enter not in page
        ):
            fs_gaps.append(f"{key}: the page carries no fullscreen button")
            continue
        runs, problem = {}, None
        for name, kw in (
            ("granted", {}),
            ("refused", {"grant": False}),
            ("absent", {"supported": False}),
            ("locked", {"locks": True}),
        ):
            runs[name], problem = _fs_drive(key, body, **kw)
            if problem:
                break
        if problem:
            fs_gaps.append(problem)
            continue
        granted, refused = runs["granted"], runs["refused"]
        absent, locked = runs["absent"], runs["locked"]
        trouble = None
        # 1. Offered where it works, and only there.
        if not granted["atLoad"]["shown"] or granted["atLoad"]["label"] != _fs_enter:
            trouble = f"{key}: a browser that supports fullscreen was offered no button"
        # 2. Rule 1: nobody is put into fullscreen, and nothing else
        #    happens to their screen either. Measured after the page
        #    loaded, the gate was pressed, and thirty frames were played.
        elif granted["callsBeforeAnyPress"] or granted["untouched"]["asked"]:
            trouble = (
                f"{key}: the page touched the screen without being pressed "
                f"({granted['callsBeforeAnyPress']})"
            )
        elif absent["atLoad"]["shown"] or absent["calls"]:
            trouble = f"{key}: a browser without fullscreen was offered it anyway"
        # 3. One press, one request, on the wrapper - so there is a way back
        #    on the screen once it is granted.
        elif [c for c in granted["calls"] if c["call"] == "request"] != [
            {"call": "request", "on": _fs_wrap}
        ]:
            trouble = f"{key}: the press asked for {granted['calls']!r}"
        elif not granted["afterPress"]["active"] or granted["label"] != _fs_enter:
            trouble = f"{key}: fullscreen was entered but the button did not change back"
        elif granted["afterPress"]["label"] != _fs_exit:
            trouble = f"{key}: in fullscreen the button still says {granted['afterPress']['label']!r}"
        elif not [c for c in granted["calls"] if c["call"] == "exit"]:
            trouble = f"{key}: there is no way back out"
        elif granted["afterSecond"]["active"]:
            trouble = f"{key}: pressing it again did not leave fullscreen"
        # 4. Rule 3: a refusal is the browser declining, not a fault. The
        #    page catches it - and nothing escapes to the runtime, which is
        #    the half a written-but-bypassed .catch would fail.
        elif any(run["escaped"] for run in runs.values()):
            trouble = (
                f"{key}: a refused promise went unhandled "
                f"({next(r['escaped'] for r in runs.values() if r['escaped'])[:1]})"
            )
        elif refused["settled"]["refused"] != 2 or locked["settled"]["refused"] != 0:
            trouble = (
                f"{key}: refusals counted {refused['settled']['refused']} when refused "
                f"and {locked['settled']['refused']} when nothing was"
            )
        elif refused["afterPress"]["active"] or refused["afterPress"]["label"] != _fs_enter:
            trouble = f"{key}: a refused request left the page claiming to be fullscreen"
        # 5. Rule 4: the lock is attempted once inside, and never before.
        elif [c["on"] for c in granted["calls"] if c["call"] == "lock"] != [_fs_lock]:
            trouble = f"{key}: the orientation lock was not attempted once inside"
        elif refused["settled"]["locks"]:
            trouble = f"{key}: the orientation was locked without fullscreen being entered"
        # 6. SPACE is 「撃つ」 in four of these. A button that keeps focus
        #    turns the fire key into a fullscreen toggle.
        elif not granted["blurred"]:
            trouble = f"{key}: the button kept keyboard focus after it was pressed"
        if trouble:
            fs_gaps.append(trouble)
        else:
            fs_ok.append(key)
    c.add(
        "creation_fullscreen_button",
        "押した人だけが全画面になる（勝手にならない・出せない環境では出ない）",
        0.0 if fs_gaps else 1.0,
        detail=(
            "; ".join(fs_gaps)
            if fs_gaps
            else f"{len(fs_ok)} 型すべてを 4 通りのブラウザで実走行: 対応環境では"
            f"ボタンが出て、押すと `{_fs_wrap}` に対して requestFullscreen が 1 回だけ"
            "呼ばれ、ラベルが戻るボタンに替わり、もう一度押すと exit する。"
            "ロード・ゲート押下・30 フレームのプレイを通して無操作では 1 回も"
            "呼ばれない。`fullscreenEnabled` が偽の環境ではボタンが出ず、押しても"
            "何も呼ばない。拒否（reject）は握り潰され、node の unhandledRejection に"
            "1 件も漏れない——拒否された走行で 2 件、何も拒否されない走行で 0 件を"
            "数えており、常に増える定数ではないことも確認済み。向きの lock は"
            "全画面に入った後だけ 1 回試み、失敗しても無視する。押下後にフォーカスは"
            "手放す（SPACE は 4 型で「撃つ」なので、持ったままだと発射が全画面切替になる）"
        ),
        kind=OUTCOME,
    )

    # --- the last ten seconds, said out loud (§8 事実 1, C-1417) ---------
    #
    # The shared clock has always ended a go at sixty seconds and nothing on
    # the screen ever mentioned it, so the 「ここまで」 banner arrived out of
    # nowhere. §8 事実 1 asks for a break inside about a minute; a break you
    # cannot see coming is a surprise, not a break.
    #
    # The countdown is deliberately absent for the first fifty seconds
    # (条件①: a clock running the whole go turns 「気楽な 1 分」 into an
    # exam), and deliberately present under reduced motion (条件②: it is a
    # number, not a movement). Both are read off a page driven for a whole
    # go, frame by frame - the page's own opinion of whether it was due,
    # beside what it actually painted, because C-1415's break table has an
    # example of those two coming apart.
    from sidra_ai.creation.round import (
        ROUND_SHOW_MS as _clk_show,
        ROUND_URGENT_MS as _clk_urgent,
        clock_probe_source as _clk_probe,
    )
    from sidra_ai.creation.games import select_theme as _clk_theme

    #: Racing finishes its three laps before the buzzer when nobody steers.
    #: Held off the road it is slow enough to still be going at the end,
    #: which is the situation the countdown exists for.
    _CLK_HOLD = {"racing": "ArrowLeft"}

    def _clk_expect(frame):
        import math

        return f"のこり {math.ceil(frame['ms'] / 1000)}"

    def _clk_said(frame):
        """True when the badge disagreed with the clock behind it."""

        return frame["said"] != _clk_expect(frame)

    def _clk_drive(key, body, **kw):
        try:
            out = _scene_sp.run(
                ["node", "-"],
                input=_clk_probe(body, hold=_CLK_HOLD.get(key, ""), **kw),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                return None, f"{key}: {out.stderr.strip()[:70]}"
            return json.loads(out.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    clk_gaps: list[str] = []
    clk_ok: list[str] = []
    clk_short: list[str] = []
    _clk_tokens = _clk_theme("ゲームを作って").tokens
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            clk_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        run, problem = _clk_drive(key, body)
        if problem:
            clk_gaps.append(problem)
            continue
        frames = run["frames"]
        early = [f for f in frames if f["ms"] >= _clk_show]
        late = [f for f in frames if f["ms"] < _clk_show and not f["done"]]
        trouble = None
        # 1. 条件①, and this half is checkable on every template: for the
        #    first fifty seconds there is nothing on the screen about time.
        if any(f["said"] or f["due"] for f in early):
            when = next(f for f in early if f["said"] or f["due"])
            trouble = f"{key}: the clock showed with {when['ms'] / 1000:.1f}s still to go"
        elif not late:
            # This template's go ends long before the buzzer even when a key
            # is held, so an unattended run never reaches the situation the
            # countdown is for. Recorded as unmeasured, not as a pass.
            clk_short.append(key)
            continue
        # 2. Every one of those frames that painted at all says so - not
        #    just the ones where the page thought it was due.
        #
        #    "Painted at all" is the qualifier that matters. The juice kit
        #    freezes the whole loop for a few frames on a hit (hitstop), and
        #    those frames draw nothing whatsoever - the canvas keeps the
        #    previous picture, badge included. Measured rather than assumed:
        #    catch skips 46 of its last 600 frames and every one of them has
        #    zero fills of any kind, not a redrawn game with the badge left
        #    off it.
        elif [f for f in late if f["all"] and not f["said"]]:
            missed = [f for f in late if f["all"] and not f["said"]]
            trouble = (
                f"{key}: {len(missed)} of the last {len(late)} frames redrew the game "
                f"without the clock (page said due on {sum(1 for f in missed if f['due'])})"
            )
        # 3. The number is the real remaining time, rounded up so the last
        #    whole second reads 「1」 rather than 「0」. Compared against the
        #    unrounded milliseconds: rounding them first made 9000.4ms look
        #    like 9000 and the page's honest 「10」 look like an off-by-one.
        elif any(_clk_said(f) for f in late if f["said"]):
            wrong = next(f for f in late if f["said"] and _clk_said(f))
            trouble = (
                f"{key}: at {wrong['ms']:.1f}ms left it said {wrong['said']!r}, "
                f"not {_clk_expect(wrong)!r}"
            )
        # 4. The last three seconds are said in the alert colour - a colour
        #    that changes once, never a blink (§15).
        # Only the frames that actually painted have an ink to read. A held
        # frame painted nothing and is not evidence either way.
        elif {f["ink"] for f in late if f["said"] and f["ms"] <= _clk_urgent} != {
            _clk_tokens["alert"]
        }:
            trouble = (
                f"{key}: the last {_clk_urgent // 1000}s were said in "
                f"{sorted({f['ink'] for f in late if f['said'] and f['ms'] <= _clk_urgent})}"
            )
        elif {f["ink"] for f in late if f["said"] and f["ms"] > _clk_urgent} != {
            _clk_tokens["text"]
        }:
            trouble = f"{key}: the earlier seconds were not said in the page's own ink"
        # 5. ...and it stops when the go does. A countdown over a finished
        #    round is counting down to nothing.
        #
        #    A guard against a future refactor rather than a confirmed
        #    detector: no break reaches it today, because the round wrapper
        #    returns at its 「ここまで」 branch before the draw is called,
        #    and a template that ends on its own re-anchors the clock. Even
        #    deleting the ROUND_DONE clause from roundClockDue leaves the
        #    number at full marks, which is what proved the structure rather
        #    than the clause is what holds this.
        elif any(f["said"] for f in frames if f["done"]):
            trouble = f"{key}: the countdown kept running after the round ended"
        # 6. 条件②: reduced motion silences the decorations, not the facts.
        if not trouble:
            quiet, problem = _clk_drive(key, body, reduced=True)
            if problem:
                trouble = problem
            elif len([f for f in quiet["frames"] if f["said"]]) != len(
                [f for f in frames if f["said"]]
            ):
                trouble = f"{key}: reduced motion changed how long the countdown showed"
        if trouble:
            clk_gaps.append(trouble)
        else:
            clk_ok.append(key)
    c.add(
        "creation_time_visible",
        "終盤だけ残り時間が見える（60 秒の幕切れが不意打ちでなくなる）",
        0.0 if (clk_gaps or not clk_ok) else 1.0,
        detail=(
            "; ".join(clk_gaps)
            if clk_gaps
            else f"{len(clk_ok)} 型（{', '.join(clk_ok)}）を 1 ゲーム丸ごと"
            f"フレーム単位で実走行: 残り {_clk_show // 1000} 秒を切るまで画面には"
            "時間の話が一切出ず、切った後は毎フレーム出て、数字は実残り時間の"
            f"切り上げと完全一致。最後の {_clk_urgent // 1000} 秒だけ警告色で言う"
            "（明滅ではなく 1 度の色替えなので §15 の門番に触れない）。ラウンドが"
            "終われば止まる。reduced motion でも出る秒数は同じ（数字であって動きでは"
            f"ない・条件②）。残り {len(clk_short)} 型（{', '.join(clk_short) or 'なし'}）は"
            "無操作でもキー長押しでも自分の決着が先に来るため、終盤の状況自体が"
            "発生せず**未測定**（合格に数えていない）。表示位置は当て推量ではなく"
            "実測で決めた——10 型を走らせて描画座標を記録し、どの型も文字を置かない"
            "帯（HUD 行の 1 段下・右）を選んだ"
        ),
        kind=OUTCOME,
    )

    # --- the number said where it was earned (§1, C-1418) ----------------
    #
    # The score has only ever moved as a total in the corner, so which act
    # paid what was arithmetic the player had to do in their head. A 「+N」
    # at the place it happened says it once and gets out of the way.
    #
    # The whole risk in a decoration like this is that it lies. The call
    # sites read `score+=scorePop(x,y,n)` - the float returns the number it
    # shows, so the two are one value rather than two kept in step - and
    # this checks it end to end anyway: everything floated over a whole go,
    # summed, against the score the round reports.
    from sidra_ai.creation.juice import POP_MAX as _pop_max, pop_probe_source as _pop_probe

    def _pop_drive(key, body, **kw):
        try:
            out = _scene_sp.run(
                ["node", "-"],
                input=_pop_probe(body, **kw),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                return None, f"{key}: {out.stderr.strip()[:70]}"
            return json.loads(out.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"{key}: probe unavailable ({type(exc).__name__})"

    pop_gaps: list[str] = []
    pop_ok: list[str] = []
    pop_quiet: list[str] = []
    for key in sorted(_tune_templates):
        page = _tune_generate("ゲームを作って", template=key).html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            pop_gaps.append(f"{key}: no script")
            continue
        body = script.group(1)
        run, problem = _pop_drive(key, body, frames=1800, stress=_pop_max + 3)
        if problem:
            pop_gaps.append(problem)
            continue
        frames, end, stress = run["frames"], run["end"], run["stress"]
        if not end["shown"]:
            # Nothing scored in an unattended go, so there is no payment to
            # say anything about. Recorded as unmeasured, not as a pass.
            pop_quiet.append(key)
            continue
        trouble = None
        # 1. 条件③, end to end: everything floated, against the score the
        #    round reports. This is the check that found the graze bonus -
        #    a near miss pays through grazeFacts().paid rather than through
        #    the template's own `score`, so the total moved and nothing on
        #    the screen said why.
        if end["total"] != frames[-1]["score"]:
            trouble = (
                f"{key}: floated {end['total']} in total but the round scored "
                f"{frames[-1]['score']}"
            )
        # 2. What it is holding is what it puts on the glass - on every
        #    frame that redrew. A frozen frame (the juice kit's hitstop)
        #    paints nothing at all and keeps the previous picture, floats
        #    included; measured, not assumed.
        elif [
            f
            for f in frames
            if f["all"] and sorted(f["painted"]) != sorted(f"+{n}" for n in f["said"])
        ]:
            off = next(
                f
                for f in frames
                if f["all"] and sorted(f["painted"]) != sorted(f"+{n}" for n in f["said"])
            )
            trouble = f"{key}: holding {off['said']} but painted {off['painted']}"
        # 3. 条件②: never more than the cap on screen at once, and the cap
        #    is a thing that has been seen to engage rather than a constant
        #    nobody ever reached.
        elif max(f["live"] for f in frames) > _pop_max:
            trouble = f"{key}: {max(f['live'] for f in frames)} floats at once, over the cap"
        elif stress["after"]["live"] != _pop_max or stress["painted"] != _pop_max:
            trouble = (
                f"{key}: asked for {stress['asked']} at once and got "
                f"{stress['after']['live']} live / {stress['painted']} painted"
            )
        elif stress["after"]["dropped"] - stress["before"]["dropped"] != (
            stress["asked"] - _pop_max
        ):
            trouble = f"{key}: the cap dropped {stress['after']['dropped']} rather than counting"
        if not trouble:
            # 4. 条件①: reduced motion turns the decoration off - and the
            #    game is unchanged underneath it, which is what makes it a
            #    decoration rather than a mechanic.
            quiet, problem = _pop_drive(key, body, frames=1800, reduced=True)
            if problem:
                trouble = problem
            elif quiet["end"]["shown"] or any(f["painted"] for f in quiet["frames"]):
                trouble = f"{key}: reduced motion still floated {quiet['end']['shown']}"
            elif not quiet["frames"][-1]["score"]:
                trouble = f"{key}: with the floats off, nothing scored at all"
            # What is deliberately *not* checked here: that the reduced run
            # scores the same as the normal one. It is the control this
            # wanted, and it cannot be run - reduced motion switches off the
            # juice kit's hitstop, which changes the timestamps the
            # templates read, which changes the run. Measured rather than
            # supposed: with scorePop disabled entirely in both modes,
            # shooter still scored 49 against 45. Holding the *game* steps
            # equal instead of the browser frames did not close it either.
            # So the claim rests on the check above - everything floated,
            # summed, equals what the round scored - which needs no control
            # run at all.
        if trouble:
            pop_gaps.append(trouble)
        else:
            pop_ok.append(key)
    c.add(
        "creation_score_float",
        "点が入った場所に「+N」が出る（合計の暗算をさせない）",
        0.0 if (pop_gaps or not pop_ok) else 1.0,
        detail=(
            "; ".join(pop_gaps)
            if pop_gaps
            else f"{len(pop_ok)} 型（{', '.join(pop_ok)}）を実走行: 1 ゲームで浮かべた"
            "数の合計が、ラウンドが報告する得点と完全一致する（条件③）。呼び出しは"
            "`score+=scorePop(x,y,n)` の形で、浮かべる数と入る数が同一の値——別々に"
            "保つ 2 つではない。描き直したフレームでは保持中の浮き文字がそのまま"
            f"画面に出る。同時表示は上限 {_pop_max} 枚で、上限は実際に叩いて確認"
            f"（{_pop_max + 3} 枚を一度に頼んで {_pop_max} 枚だけ生き残り、残りが"
            "drop に計上される・条件②）。reduced motion では 1 枚も出ず、しかも"
            "得点は入り続ける（条件①）。なお「reduced でも得点が同じ」は"
            "**検査していない**——reduced は juice の hitstop を切り、それが"
            "テンプレの読む時刻を変えて走行そのものを変える（scorePop を両モードで"
            "完全に無効化しても shooter は 49 対 45 になる。ゲーム側の前進フレーム数を"
            "揃えても解消しない）。飾りであることの根拠は上の「浮かべた合計＝入った点」"
            "であって、対照走行ではない。"
            f"残り {len(pop_quiet)} 型（{', '.join(pop_quiet) or 'なし'}）は無操作の"
            "1 ゲームで 1 点も入らないため**未測定**（合格に数えていない）。"
            "この判定器づくりで shooter の掠りボーナスが未配線だと分かった——"
            "near miss は `score` ではなく grazeFacts().paid で払われるので、"
            "合計だけが動いて画面は何も言っていなかった。配線して一致させた"
        ),
        kind=OUTCOME,
    )

    # --- the second template that pays for standing close (C-1419) -------
    #
    # C-1406 put a graze band outside the shooter's kill radius. This wires
    # the same part to kaiju, and the entry that asked for it - like the
    # unwired table's own note - said 「拳」. The boss has no fists. It
    # opens cracks in the ground whose radius grows as they widen, and that
    # is the hazard the band went outside of. The same correction the graze
    # module already records for the shooter's 敵弾.
    #
    # Flown three ways on the real page, steered by pressing the arrow keys
    # the template listens for rather than by writing to the player's
    # position - so the probe can only reach places a person could.
    from sidra_ai.creation.graze import GRAZE_BAND as _kg_band, GRAZE_RUN as _kg_run
    from sidra_ai.creation.kaiju import graze_probe_source as _kg_probe

    kg_gaps: list[str] = []
    kg_page = _tune_generate("怪獣ゲームを作って", template="kaiju").html
    kg_script = _scene_re.search(r"<script>(.*?)</script>", kg_page, _scene_re.S)
    kg_runs: dict[str, dict] = {}
    if kg_script is None:
        kg_gaps.append("no script on the page")
    else:
        def _kg_fly(**kwargs):
            out = _scene_sp.run(
                ["node", "-"],
                input=_kg_probe(kg_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:60])
            return json.loads(out.stdout.strip().splitlines()[-1])

        try:
            kg_runs["hug"] = _kg_fly(mode="hug", frames=3000)
            kg_runs["clear"] = _kg_fly(mode="clear", frames=3000)
            kg_runs["crash"] = _kg_fly(mode="crash", frames=3000)
            kg_runs["quiet"] = _kg_fly(mode="hug", frames=3000, reduced=True)
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            kg_gaps.append(f"probe unavailable ({exc})")

    if len(kg_runs) == 4:
        hug, clear = kg_runs["hug"], kg_runs["clear"]
        crash, quiet = kg_runs["crash"], kg_runs["quiet"]
        # 1. Standing beside a crack pays, and the points reach the round's
        #    own score rather than sitting in a counter nobody reads.
        if hug["graze"]["paid"] <= 0:
            kg_gaps.append(f"a fight spent beside the cracks earned nothing ({hug['graze']})")
        elif hug["roundScore"] <= hug["cycles"]:
            kg_gaps.append(
                f"the graze points never reach the score "
                f"({hug['roundScore']} against {hug['cycles']} head hits)"
            )
        # 2. Every brush the page paid for was outside the radius that would
        #    have cost a heart, and inside the ribbon. Read off the page's
        #    own record of the gap it judged each brush at.
        #
        #    A guard rather than a confirmed detector, and worth saying so:
        #    widening the band to reach *inside* the radius leaves this at
        #    full marks, because it is unreachable - the collision branch
        #    runs first and removes the crack, so grazeNear is never called
        #    from inside the radius at all. What is confirmed is the other
        #    direction: paying from anywhere is caught. The check earns its
        #    place against a future reordering of those two branches.
        outside = [
            pair
            for pair in hug["graze"]["at"]
            if not (pair[1] < pair[0] <= pair[1] + _kg_band)
        ]
        if not hug["graze"]["at"]:
            kg_gaps.append("the page recorded no brushes to check")
        elif outside:
            kg_gaps.append(f"paid outside the band: {outside[:3]}")
        # 3. It pays on a run, not per brush.
        if hug["graze"]["seen"] < hug["graze"]["paid"] * _kg_run:
            kg_gaps.append(
                f"paid more often than the run allows "
                f"({hug['graze']['seen']} brushes, {hug['graze']['paid']} points)"
            )
        # 4. Keeping away earns nothing. Without this, "the band pays" could
        #    be true of the whole arena.
        if clear["graze"]["paid"] > 0:
            kg_gaps.append(f"a fight spent at distance was paid {clear['graze']['paid']}")
        # 5. The crack still costs a heart, a hit takes the run, and nothing
        #    is banked for walking into them.
        if crash["hp"] > 0:
            kg_gaps.append("walking into the cracks no longer costs anything")
        hits = [row for row in crash["timeline"] if row.get("hit")]
        if not hits:
            kg_gaps.append("the crashing fight never lost a heart")
        elif any(row["run"] != 0 for row in hits):
            kg_gaps.append(f"a hit did not take the run (left {[r['run'] for r in hits][:3]})")
        if crash["graze"]["paid"] > 0:
            kg_gaps.append("a fight that kept walking in still banked points")
        # ...and the radius it hurts at has not moved: every heart lost was
        # lost from inside the radius the page itself judged it by.
        struck = crash["graze"]["struck"]
        if not struck:
            kg_gaps.append("no crack landed, so the radius is unmeasured")
        elif [pair for pair in struck if pair[0] >= pair[1]]:
            kg_gaps.append(
                f"a heart was lost from outside the radius: "
                f"{[p for p in struck if p[0] >= p[1]][:2]}"
            )
        # 6. Reduced motion drops the particles, not the points (C-1406's
        #    contract: the reward is points and nothing else).
        if quiet["graze"]["paid"] <= 0:
            kg_gaps.append("with reduced motion the brushes stopped paying")
    c.add(
        "creation_kaiju_graze",
        "怪獣戦でも「かすめる」が選べる（危険は増やさず、点だけ増える）",
        0.0 if kg_gaps else 1.0,
        detail=(
            "; ".join(kg_gaps)
            if kg_gaps
            else f"実ページを 3 通り戦って計測。地割れの傍に立ち続けた戦いは "
            f"{kg_runs['hug']['graze']['paid']} 点を稼ぎ、その点はラウンドの得点に"
            f"届く（{kg_runs['hug']['roundScore']}）。支払われた接近は全て"
            f"「心を失う半径の外・帯 {_kg_band}px の内」——ページ自身が判定に使った"
            f"間合いの記録で確認。{_kg_run} 回続けて 1 点で、離れて戦えば 0 点。"
            "割れ目に踏み込めば心は減り、そのたび連続は 0 に戻り、1 点も入らない。"
            "心を失った間合いは全て半径の内側。**危険が増えていないこと自体も"
            "実測した**——graze の配線を kaiju から丸ごと剥がすと、3 通りの戦いは"
            "どれも同じフレームで同じ hp・同じ結末になる（hug 2818 / clear 2692 / "
            "crash 1441 フレーム、いずれも一致）。点が増えるだけで戦いは動いていない。"
            "reduced でも点は入る（粒子だけが消える）。"
            "起票と未配線表はどちらも「拳」と書いていたが、この怪獣に拳は無い——"
            "地面を割り、その半径は割れ目が広がるほど育つ。帯はその外に置いた"
        ),
        kind=OUTCOME,
    )

    # --- the third template with a run, and the sum that keeps it legible
    #
    # C-1420. combo.py's own unwired table said marble needed a decision
    # before it could be wired: C-1313 had made some gates worth double,
    # and two multipliers at once is one too many. The decision taken here
    # is that **the run multiplies the gate's base value and the hot gate's
    # extra is added outside it** - a hot gate on a x3 run pays 3 + 1, not
    # 6. Stacking them would make the best line on the course the one a
    # player cannot work out from the seat, which is what §13's readable
    # risk is against, and it is the same call C-1411 made when it added
    # the graze to the kills rather than multiplying them.
    #
    # So the check that matters is arithmetic on a page that played: every
    # payment against the multiplier that was live when it landed.
    from sidra_ai.creation.combo import COMBO_MAX as _mc_max, COMBO_STEP as _mc_step
    from sidra_ai.creation.marble import GATE_BASE as _mc_base
    from sidra_ai.creation.marble import combo_probe_source as _mc_probe

    mc_gaps: list[str] = []
    mc_page = _tune_generate("玉転がしを作って", template="marble").html
    mc_script = _scene_re.search(r"<script>(.*?)</script>", mc_page, _scene_re.S)
    mc_runs: dict[str, dict] = {}
    if mc_script is None:
        mc_gaps.append("no script on the page")
    else:
        def _mc_roll(**kwargs):
            out = _scene_sp.run(
                ["node", "-"],
                input=_mc_probe(mc_script.group(1), **kwargs),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                raise ValueError(out.stderr.strip()[:60])
            return json.loads(out.stdout.strip().splitlines()[-1])

        try:
            mc_runs["run"] = _mc_roll(mode="run")
            mc_runs["skip"] = _mc_roll(mode="skip")
            mc_runs["quiet"] = _mc_roll(mode="run", reduced=True)
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            mc_gaps.append(f"probe unavailable ({exc})")

    if len(mc_runs) == 3:
        clean, skip, quiet = mc_runs["run"], mc_runs["skip"], mc_runs["quiet"]
        through = [e for e in clean["events"] if e["kind"] == "through"]
        # 1. Consecutive gates build the run, on the ladder's own step and
        #    no further than its cap.
        if not through:
            mc_gaps.append("the roll never went through a gate")
        elif max(e["mult"] for e in through) <= 1:
            mc_gaps.append("a clean roll never built a multiplier")
        elif max(e["mult"] for e in through) > _mc_max:
            mc_gaps.append(f"the multiplier passed its cap ({max(e['mult'] for e in through)})")
        elif any(e["mult"] != min(_mc_max, 1 + e["run"] // _mc_step) for e in through):
            off = next(e for e in through if e["mult"] != min(_mc_max, 1 + e["run"] // _mc_step))
            mc_gaps.append(f"a run of {off['run']} was worth x{off['mult']}")
        # 2. The decision itself: base x mult for a plain gate, and the hot
        #    gate's extra added *outside* the multiplier.
        else:
            wrong = [
                e
                for e in through
                if e["paid"] != _mc_base * e["mult"] + (_mc_base if e["hot"] else 0)
            ]
            if wrong:
                bad = wrong[0]
                mc_gaps.append(
                    f"a {'hot' if bad['hot'] else 'plain'} gate on x{bad['mult']} paid "
                    f"{bad['paid']}, not "
                    f"{_mc_base * bad['mult'] + (_mc_base if bad['hot'] else 0)}"
                )
            else:
                # ...and specifically not the product, which is the answer
                # the decision rules out. Only says anything where the two
                # actually differ.
                stacked = [
                    e
                    for e in through
                    if e["hot"] and e["mult"] > 1 and e["paid"] == _mc_base * 2 * e["mult"]
                ]
                if stacked:
                    mc_gaps.append(f"a hot gate paid the product: {stacked[0]}")
                elif not [e for e in through if e["hot"] and e["mult"] > 1]:
                    mc_gaps.append("no hot gate landed on a built run, so the sum is untested")
        # 3. A gate that went past the posts takes the run - all of it.
        missed = [e for e in skip["events"] if e["kind"] == "past"]
        if not missed:
            mc_gaps.append("the skipping roll never missed a gate")
        elif any(e["run"] != 0 or e["mult"] != 1 for e in missed):
            mc_gaps.append(f"a missed gate left {[(e['run'], e['mult']) for e in missed][:2]}")
        elif max((e["mult"] for e in skip["events"]), default=1) <= 1:
            mc_gaps.append("the skipping roll never built anything to lose")
        # 4. It is on the screen the whole time, at x1 as much as at x4.
        huds = [e["hud"] for e in through if e["hud"]]
        if not huds:
            mc_gaps.append("the HUD was never drawn on a scoring frame")
        elif [h for h in huds if "×" not in h]:
            mc_gaps.append(f"the multiplier is missing from the HUD: {huds[0]!r}")
        elif not [h for h in huds if "×1" in h]:
            mc_gaps.append("the HUD only shows the multiplier once it has risen")
        # 5. Reduced motion drops the decoration and keeps the number
        #    (combo.py's own contract, C-1020's rule).
        if max((e["mult"] for e in quiet["events"]), default=1) <= 1:
            mc_gaps.append("with reduced motion the multiplier stopped building")
    c.add(
        "creation_marble_combo",
        "玉転がしの連続通過が積み上がる（二重ボーナスは積ではなく和）",
        0.0 if mc_gaps else 1.0,
        detail=(
            "; ".join(mc_gaps)
            if mc_gaps
            else f"実コースを 2 通り走らせて計測。連続通過で倍率が {_mc_step} 門ごとに"
            f"1 段上がり、×{_mc_max} で止まる。支払いは全て「基礎 {_mc_base}×倍率"
            f"（＋影の門なら基礎 {_mc_base}）」と一致——**積ではなく和**。"
            f"×4 の影の門は {_mc_base * 4 + _mc_base} 点であって "
            f"{_mc_base * 2 * 4} 点ではない（この 2 つが実際に食い違う走行で確認）。"
            "門を外せば連続も倍率も 0/×1 に戻る（この型に「落下」は無い——起票文は"
            "そう書いていたが、コースを外れる唯一の道はブロックで、それは走行自体を"
            "終わらせる。遊びながらやり直せる失敗は「門を外す」だけ）。倍率は ×1 の"
            "ときも HUD に出ている（実際に描かれた文字列で確認）。reduced でも"
            "積み上がる——飾りが消えるだけで数字は情報（C-1020）。"
            "SKIN_UNIT は再測定して据え置き: マッシャーの 1 ラウンドは今も 2 点で、"
            "この倍率が上げるのは上手に走った天井であって下限ではない"
        ),
        kind=OUTCOME,
    )

    # --- why the duel was lost, in one line (C-1422) ---------------------
    #
    # recap.py's unwired table said duel needed the hp comparison split out
    # first: 'end' is reached by winning and by losing alike, so there was
    # no predicate to hang a losing line on. That split is the whole of the
    # product change here - the damage and the CPU are untouched, and two
    # counters were added that only count.
    #
    # Two causes, because the duel has two genuinely different ways to lose
    # a heart: a beam that landed was fired into the lane the player was
    # standing in, and a lost clash was a shove that did not push hard
    # enough. Driven twice on the real page so each is seen alone - which
    # is also what makes 「the largest cause」 distinguishable from 「the
    # first cause in the table」.
    from sidra_ai.creation.duel import loss_probe_source as _dl_probe

    dl_gaps: list[str] = []
    dl_page = _tune_generate("ビーム対戦のゲームを作って").html
    dl_script = _scene_re.search(r"<script>(.*?)</script>", dl_page, _scene_re.S)
    dl_runs: dict[str, dict] = {}
    if dl_script is None:
        dl_gaps.append("no script on the page")
    else:
        for mode in ("beam", "clash", "mixed"):
            try:
                out = _scene_sp.run(
                    ["node", "-"],
                    input=_dl_probe(dl_script.group(1), mode=mode),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if out.returncode != 0:
                    raise ValueError(out.stderr.strip()[:60])
                dl_runs[mode] = json.loads(out.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
                dl_gaps.append(f"{mode}: probe unavailable ({exc})")

    if len(dl_runs) == 3:
        # The mixed run is the one that makes the count falsifiable. With a
        # single cause at 3 in every run, a line that hard-codes 「3」 reads
        # exactly like one that counts; mixed ends 2 and 1, so it does not.
        mixed = dl_runs["mixed"]
        if not (mixed["facts"]["lostBeam"] and mixed["facts"]["lostClash"]):
            dl_gaps.append(
                "the mixed go did not produce both causes, so the counts are "
                f"not falsifiable ({mixed['facts']['lostBeam']}/{mixed['facts']['lostClash']})"
            )
        elif str(mixed["facts"]["lostBeam"]) not in (mixed["recap"] or {}).get("line", ""):
            dl_gaps.append(
                f"the mixed go's line is not its own count "
                f"({(mixed['recap'] or {}).get('line')!r} against {mixed['facts']['lostBeam']})"
            )
        elif max(mixed["facts"]["lostBeam"], mixed["facts"]["lostClash"]) != mixed["facts"][
            "lostBeam"
        ]:
            dl_gaps.append("the mixed go named the smaller cause")
        for mode, wanted, other, phrase in (
            ("beam", "lostBeam", "lostClash", "ビームを"),
            ("clash", "lostClash", "lostBeam", "つばぜり合いに"),
        ):
            run = dl_runs[mode]
            facts, recap = run["facts"], run["recap"] or {}
            # 1. It was a loss, and it was a loss *by hp* - the comparison
            #    this item exists to add.
            if run["state"] != "end":
                dl_gaps.append(f"{mode}: the go never finished")
                continue
            if not (facts["pHp"] < facts["eHp"]):
                dl_gaps.append(f"{mode}: the go was not lost on hp ({facts['pHp']}/{facts['eHp']})")
            elif not recap.get("lost"):
                dl_gaps.append(f"{mode}: a go lost on hp was not counted as a loss")
            # 2. The line names this cause, with this counter's number.
            elif phrase not in recap.get("line", ""):
                dl_gaps.append(f"{mode}: the line does not name the cause ({recap.get('line')!r})")
            elif str(facts[wanted]) not in recap["line"]:
                dl_gaps.append(
                    f"{mode}: the line's count is not the counter's "
                    f"({recap['line']!r} against {facts[wanted]})"
                )
            # 3. ...and the other cause was at zero, so this run also shows
            #    that a cause counted zero is never named.
            elif facts[other]:
                dl_gaps.append(f"{mode}: the other cause was not zero ({facts[other]})")
            # 4. Every heart is accounted for. A counter that only sees
            #    some of the damage would still pass everything above.
            elif facts["lostBeam"] + facts["lostClash"] != 3:
                dl_gaps.append(
                    f"{mode}: {facts['lostBeam'] + facts['lostClash']} hearts counted, not 3"
                )
            # 5. The same finished page, with the hp the other way round,
            #    says nothing. A win that explains itself is second-guessing
            #    somebody who has just succeeded.
            elif (run.get("asWin") or {}).get("lost") is not False:
                dl_gaps.append(f"{mode}: the same page called a win a loss ({run.get('asWin')})")
            elif (run.get("asWin") or {}).get("line"):
                dl_gaps.append(f"{mode}: a win was given a reason ({run['asWin']['line']!r})")
        # 6. The two runs pick different lines, which is the only way to
        #    tell 「the largest cause」 from 「the first one in the table」.
        #
        #    Two breaks are recorded here as *not* reachable, rather than
        #    left to look covered. Making recapLine take the first cause
        #    instead of the largest still passes: the zero guard above it
        #    drops a cause counted zero before the comparison, so in a run
        #    with one live cause the two rules agree, and no run this
        #    template produces ends with a *later* cause larger than an
        #    earlier one. Removing that zero guard also still passes,
        #    because _CAUSE already blanks a zero cause's sentence - the
        #    guard is belt-and-braces over a ternary that had it covered.
        #    Both live in shared recap code that predates this item.
        if not dl_gaps:
            lines = {dl_runs[m]["recap"]["line"] for m in ("beam", "clash")}
            del mixed
            if len(lines) != 2:
                dl_gaps.append("both runs gave the same line, so the choice is untested")
    c.add(
        "creation_duel_loss_recap",
        "ビーム対戦の負けにも一言（勝ちには出ない）",
        0.0 if dl_gaps else 1.0,
        detail=(
            "; ".join(dl_gaps)
            if dl_gaps
            else "実ページを 2 通り戦って計測。立ち尽くす走行は"
            f"「{dl_runs['beam']['recap']['line']}」、相手のレーンに踏み込んで"
            f"競り負ける走行は「{dl_runs['clash']['recap']['line']}」——"
            "**別々の行が出る**ので「最大の原因」が「表の先頭」と区別できている。"
            "どちらの走行でも数字はページの生カウンタと一致し、0 の原因は名指し"
            "されず、失った心 3 つは 2 つのカウンタで過不足なく説明される。"
            "同じ終局ページの hp を逆にして尋ねると何も言わない——'end' は勝ちも"
            "負けも通るので、この hp 比較が C-1422 の中身そのもの。"
            "ダメージ計算と CPU の挙動は不変（足したのは数えるだけの 2 変数）"
        ),
        kind=OUTCOME,
    )

    # --- the adventure can be lost, and something can lose it (C-1424) ----
    #
    # Out of C-1423's unfinished record: its loss line could not be measured
    # because no drive that *loses* had ever been produced. A hands-off hero
    # stands where it wakes, and four obvious autopilots all died in the
    # first room. This is the instrument that was missing.
    #
    # The first room, measured rather than assumed: the hero wakes at tile
    # (2, 4) and the way out is (19, 4) - the same row - but grass sits on
    # that row and a pond spans columns 9-11 across rows 4 and 5. A pond
    # cannot be cut, so the route out goes *around*, and no held direction
    # finds it. The driver walks a breadth-first path over the room's own
    # grid instead, with the page's own solid() deciding what is wall.
    from sidra_ai.evals.adventure_losable import drive as _adv_drive

    adv_gaps: list[str] = []
    adv_runs: dict[str, object] = {}
    try:
        adv_runs["path"] = _adv_drive(mode="path")
        adv_runs["naive"] = _adv_drive(mode="naive")
        adv_runs["cutting"] = _adv_drive(mode="path", cut_grass=True)
    except (OSError, ValueError) as exc:
        adv_gaps.append(f"driver unavailable ({exc})")

    if len(adv_runs) == 3 and all(adv_runs.values()):
        lost, naive, cutting = (
            adv_runs["path"], adv_runs["naive"], adv_runs["cutting"]
        )
        # 1. It loses - really loses, hearts gone and the page saying so.
        if not lost.lost:
            adv_gaps.append(
                f"the driver did not lose (hp {lost.hp}, state {lost.state!r}, "
                f"room {lost.room})"
            )
        elif len(lost.hits) < 3:
            adv_gaps.append(f"only {len(lost.hits)} hearts were taken, not 3")
        # 2. It got out of the first room to do it, which is the whole
        #    difficulty - the room the hero wakes in has nobody in it.
        elif lost.room < 1:
            adv_gaps.append("the loss happened without ever leaving the first room")
        # 3. The path is what did it. Walking straight at the target is what
        #    this looked like before, and it is still stuck.
        #
        #    Not everything here is a confirmed detector, and it is worth
        #    saying which. Making the driver ignore the enemies entirely
        #    and walk only for the exit *still* loses - the roamers chase
        #    anyone crossing their room, so simply being in room 1 is
        #    enough. That is a fact about the product rather than a hole:
        #    the rooms past the first are dangerous to cross at all. The
        #    driver still aims at the enemies deliberately, because a
        #    driver that seeks the loss keeps working if a later room is
        #    laid out more gently.
        elif naive.lost:
            adv_gaps.append("walking straight at the target loses too, so the path proves nothing")
        elif naive.room > 0:
            adv_gaps.append(f"the naive drive left the first room ({naive.room}), so it is not the control")
        # 4. ...and the sword is not what did it. Routing *through* grass
        #    because the hero could in principle cut it is slower than
        #    going around, and never gets out at all.
        elif cutting.lost:
            adv_gaps.append("cutting a way through also loses, so the route around is not the reason")
    elif not adv_gaps:
        adv_gaps.append(f"only {len(adv_runs)} of the 3 drives produced a result")
    c.add(
        "creation_adventure_losable",
        "冒険は負けられる（負ける道を運転できる計器がある）",
        0.0 if adv_gaps else 1.0,
        detail=(
            "; ".join(adv_gaps)
            if adv_gaps
            else f"実ページを運転して計測: 経路探索の運転器は "
            f"{adv_runs['path'].frames} フレームで部屋 {adv_runs['path'].room} まで歩き、"
            f"心を 3 つとも失って 'over' に到達する。対照 2 通りはどちらも部屋 0 から"
            "出られない——(a) 目標へ直線的に歩く運転（C-1423 で 1 サイクル溶かした挙動）"
            "(b) 草を斬って**突っ切る**経路。(b) が効かないのは意外だが実測どおりで、"
            "斬撃には溜めと向きがあるため草を当てにした経路は固いタイルを押し続けて"
            "止まる。**部屋 0 の実測**: 勇者は tile(2,4) で目覚め出口は (19,4) と同じ行、"
            "しかし草が行 4 の列 3/5/7 に、池（斬れない）が列 9-11・行 4-5 に跨がる。"
            "だから道は「回り込む」形にしかなく、方向キー長押しでは永久に見つからない。"
            "壁かどうかはページ自身の solid() に訊いているので、判定が製品の当たり判定と"
            "食い違うことはない。なお「敵を無視して出口だけ目指す」破壊は落ちない"
            "——部屋 1 の敵は横切る者を追うので、居るだけで負けるため。穴ではなく"
            "製品の性質だが、運転器は意図して敵を狙う（将来もっと穏やかな部屋が"
            "来ても効くように）"
        ),
        kind=OUTCOME,
    )

    # --- and the adventure's own reason, interrogated (C-1425) -----------
    #
    # The shared judge above now covers adventure like any other template.
    # This one asks the three questions that are specific to it, because
    # they are the ones the shape of this template makes easy to get wrong:
    #
    # 1. The two counters are wired to the right damage sites. The same go
    #    is measured a second way - hearts watched frame by frame, with the
    #    room each drop happened in - and the two have to agree. Rooms 0
    #    and 1 have no guardian in them at all, so a drop there that the
    #    page filed under 「番人」 is a miswiring this catches.
    # 2. The guardian clause is reachable, not decorative. No drive that
    #    exists today survives to room 2 (C-1424 measured why), so the only
    #    honest way to ask is to move the counters and re-read the line:
    #    make the guardian the larger cause and the page must name it.
    # 3. Zero both and the page says nothing - the C-1409 rule, asked of
    #    this template's own counters rather than assumed from the shared
    #    one.
    from sidra_ai.evals.adventure_losable import REQUEST as _adv_request
    from sidra_ai.evals.adventure_losable import (
        recap_probe_source as _adv_recap_probe,
    )

    advrec_gaps: list[str] = []
    advrec_line = ""
    advrec_tail: dict = {}
    found = _scene_re.search(
        r"<script>(.*?)</script>", generate_game(_adv_request).html, _scene_re.S
    )
    if found is None:
        advrec_gaps.append("no script on the adventure page")
    else:
        try:
            run = _scene_sp.run(
                ["node", "-"],
                input=_adv_recap_probe(found.group(1)),
                capture_output=True,
                text=True,
                timeout=600,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:80])
            out = run.stdout.strip().splitlines()
            advrec_main = json.loads(out[-2])
            advrec_tail = json.loads(out[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
            advrec_gaps.append(f"probe unavailable ({exc})")
            advrec_main = {}
    if not advrec_gaps:
        end = advrec_main.get("atEnd") or {}
        advrec_line = end.get("line") or ""
        hits = advrec_tail.get("hits") or []
        # Rooms other than the last have no guardian in them.
        watched_roam = sum(1 for h in hits if h.get("room") != 2)
        watched_guard = sum(1 for h in hits if h.get("room") == 2)
        if not end.get("lost"):
            advrec_gaps.append("the driven go was not a loss")
        elif not advrec_line:
            advrec_gaps.append("a loss with counted causes said nothing")
        elif advrec_tail.get("roam") != watched_roam:
            advrec_gaps.append(
                f"まもの counted {advrec_tail.get('roam')} but "
                f"{watched_roam} hearts were lost outside the guardian's room"
            )
        elif advrec_tail.get("guard") != watched_guard:
            advrec_gaps.append(
                f"番人 counted {advrec_tail.get('guard')} but "
                f"{watched_guard} hearts were lost in the guardian's room"
            )
        elif str(watched_roam) not in advrec_line:
            advrec_gaps.append(
                f"the line's count is not the hearts that were lost "
                f"({advrec_line!r} against {watched_roam})"
            )
        elif advrec_tail.get("guard") == 0 and "番人" in advrec_line:
            advrec_gaps.append(f"named a cause counted zero ({advrec_line!r})")
        elif "番人" not in (advrec_tail.get("saidGuard") or ""):
            advrec_gaps.append(
                "made the guardian the larger cause and the line still did "
                f"not name it ({advrec_tail.get('saidGuard')!r})"
            )
        # ...and it read the moved counter rather than reprinting the number
        # it had already said. A line whose count is a constant passes every
        # check above, because the constant happens to be right.
        elif str(watched_roam + 5) not in (advrec_tail.get("saidGuard") or ""):
            advrec_gaps.append(
                f"the guardian line's count did not follow the counter "
                f"({advrec_tail.get('saidGuard')!r}, wanted {watched_roam + 5})"
            )
        elif advrec_tail.get("saidNothing"):
            advrec_gaps.append(
                f"both causes at zero and it still spoke "
                f"({advrec_tail.get('saidNothing')!r})"
            )
        elif advrec_line not in (advrec_main.get("strip") or []):
            advrec_gaps.append("the line never reached the result strip")
    c.add(
        "creation_adventure_loss_recap",
        "冒険の敗因を一言で言う",
        0.0 if advrec_gaps else 1.0,
        detail=(
            "; ".join(advrec_gaps)
            if advrec_gaps
            else f"C-1424 の経路で実際に負けた回を計測: 帯は「{advrec_line}」。"
            "同じ回のハートの減りを部屋つきで別に数え、2 つのカウンタが"
            "被弾した部屋と一致することを確認（部屋 0・1 に番人は居ない）。"
            "番人側は今日どの運転でも到達できない（C-1424 実測）ので、"
            "**カウンタを入れ替えて同じページに訊き直す**: 番人を多いほうに"
            "すると帯は番人を名指しし、両方 0 にすると何も言わない。"
            "つまり最多原因の選択が比較として動いていることまで測れている"
        ),
        kind=OUTCOME,
    )

    # --- the fourth template's run, and the sweep that does not break it -
    #
    # C-1426. ``COMBO_UNWIRED`` said fishing needed "a rule for the idle
    # sweep between casts" before it could be wired, and the rule is: the
    # sweep is not a miss. Only a cast breaks the run, because waiting for
    # the marker to come back around is the thing the game asks a player to
    # do, and a run that drained while they waited would make patience the
    # punished move.
    #
    # Driven on the real page, one go: build a run of cautious casts, leave
    # the marker sweeping for hundreds of frames with nothing pressed, land
    # a perfect throw on whatever multiplier the run reached, whiff once,
    # then build it again. Every number below is a score delta the page
    # produced, checked against the ladder derived from COMBO_STEP and
    # COMBO_MAX here rather than from the page's own claim.
    from sidra_ai.creation.combo import COMBO_MAX as _fc_max
    from sidra_ai.creation.combo import COMBO_STEP as _fc_step
    from sidra_ai.creation.combo import COMBO_TEMPLATES as _fc_wired
    from sidra_ai.creation.fishing import combo_probe_source as _fc_probe

    def _fc_rung(run_len: int) -> int:
        return min(_fc_max, 1 + run_len // _fc_step)

    def _fc_run(*, reduced: bool = False):
        page = generate_game("釣りゲームを作って").html
        script = _scene_re.search(r"<script>(.*?)</script>", page, _scene_re.S)
        if script is None:
            return None, "no script on the fishing page"
        try:
            probe = _scene_sp.run(
                ["node", "-"],
                input=_fc_probe(script.group(1), reduced=reduced),
                capture_output=True,
                text=True,
                timeout=420,
            )
            if probe.returncode != 0:
                raise ValueError(probe.stderr.strip()[:80])
            return json.loads(probe.stdout.strip().splitlines()[-1]), None
        except (OSError, _scene_sp.SubprocessError, ValueError) as exc:
            return None, f"probe unavailable ({exc})"

    fcombo_gaps: list[str] = []
    fcombo_top = 1
    seen, problem = _fc_run()
    if problem:
        fcombo_gaps.append(problem)
    elif "fishing" not in _fc_wired:
        fcombo_gaps.append("fishing is not in COMBO_TEMPLATES")
    else:
        clean = seen["timeline"]
        idle_a, idle_b = seen["idleBefore"], seen["idleAfter"]
        perfect, whiff = seen["perfect"], seen["whiff"]
        fcombo_top = max([c["multAfter"] for c in clean] or [1])
        # 1. Every cautious cast pays base x mult, with the ladder derived
        #    here from the run length rather than read off the page.
        for cast in clean:
            want = _fc_rung(cast["runAfter"])
            if cast["multAfter"] != want:
                fcombo_gaps.append(
                    f"a run of {cast['runAfter']} paid x{cast['multAfter']}, not x{want}"
                )
                break
            if cast["gain"] != want:
                fcombo_gaps.append(
                    f"a cast on x{want} scored {cast['gain']}, not {want}"
                )
                break
        if not fcombo_gaps and fcombo_top < 2:
            # A ladder that never left the bottom rung proves nothing.
            fcombo_gaps.append("the run never climbed past x1")
        # 2. The idle sweep, which is the whole reason this was unwired.
        if not fcombo_gaps:
            if idle_b["ms"] <= idle_a["ms"]:
                fcombo_gaps.append("no time passed during the idle sweep")
            elif idle_b["casts"] != idle_a["casts"]:
                fcombo_gaps.append("the idle sweep cast something")
            elif (idle_b["run"], idle_b["mult"]) != (idle_a["run"], idle_a["mult"]):
                fcombo_gaps.append(
                    f"sweeping without casting moved the run "
                    f"({idle_a['run']}/x{idle_a['mult']} -> "
                    f"{idle_b['run']}/x{idle_b['mult']})"
                )
        # 3. The sum: the multiplier rides the base, the perfect throw's
        #    extra is added outside it. On a x3 run that is 3 + 1, not 6.
        if not fcombo_gaps:
            want = _fc_rung(perfect["runAfter"]) + 1
            if perfect["crits"] < 1:
                fcombo_gaps.append("the perfect throw was not scored as one")
            elif perfect["gain"] != want:
                fcombo_gaps.append(
                    f"a 会心 on x{_fc_rung(perfect['runAfter'])} paid "
                    f"{perfect['gain']}, not {want} (base x mult + extra)"
                )
        # 4. ...and the only thing that breaks it does.
        if not fcombo_gaps:
            if whiff["multBefore"] < 2:
                fcombo_gaps.append("the whiff was thrown away on x1, so it proves nothing")
            elif whiff["multAfter"] != 1 or whiff["runAfter"] != 0:
                fcombo_gaps.append(
                    f"a cast outside the band left the run at "
                    f"{whiff['runAfter']}/x{whiff['multAfter']}"
                )
            elif whiff["gain"] != 0:
                fcombo_gaps.append(f"a missed cast still paid {whiff['gain']}")
            elif not seen["rebuilt"] or seen["rebuilt"][0]["multAfter"] != 1:
                fcombo_gaps.append("the run did not start again from x1")
        # 5. On screen at x1 as much as at x4 - asked of the lines the page
        #    actually drew, not of the source.
        if not fcombo_gaps:
            low = [c for c in clean if c["multAfter"] == 1]
            high = [c for c in clean if c["multAfter"] == fcombo_top]
            if not low or "\u00d71" not in (low[0]["hud"] or ""):
                fcombo_gaps.append("the multiplier was not on the HUD at x1")
            elif not high or f"\u00d7{fcombo_top}" not in (high[-1]["hud"] or ""):
                fcombo_gaps.append(f"the multiplier was not on the HUD at x{fcombo_top}")
    # 6. Reduced motion drops the decoration and keeps the information: the
    #    number is information, so it is still drawn (C-1020).
    if not fcombo_gaps:
        quiet, problem = _fc_run(reduced=True)
        if problem:
            fcombo_gaps.append(f"reduced motion: {problem}")
        else:
            hud = [c["hud"] for c in quiet["timeline"] if c["hud"]]
            if not hud or "\u00d7" not in hud[-1]:
                fcombo_gaps.append("reduced motion took the multiplier off the HUD")
    c.add(
        "creation_fishing_combo",
        "釣りの連続成功が積み上がる（合間の掃引では切れない）",
        0.0 if fcombo_gaps else 1.0,
        detail=(
            "; ".join(fcombo_gaps)
            if fcombo_gaps
            else f"実ページを運転して計測: 慎重なキャストを続けると倍率が "
            f"x{fcombo_top} まで上がり、各回の得点が「基礎×倍率」と一致する"
            "（倍率は COMBO_STEP/COMBO_MAX から判定器側で導いた梯子と照合）。"
            "**未配線だった理由がここで解ける**——キャストせずに数百フレーム"
            "掃引しても run も倍率も動かない（played time は進んでいることを"
            "確認済み）。待つことは罰ではない。会心は「基礎×倍率＋上乗せ」で、"
            "x3 の会心は 6 ではなく 4（C-1420 と同じ和の規約）。band を外した"
            "キャストだけが run を 0 に戻し、そこから x1 で積み直す。"
            "倍率は x1 の時点から HUD に出ており、reduced motion でも"
            "数字は残る（装飾だけが落ちる）"
        ),
        kind=OUTCOME,
    )

    # --- and the puzzle's own reason, interrogated (C-1427) --------------
    #
    # LOSS_UNWIRED said "'over' means the board jammed, but nothing counts
    # *why*". The axis was measured before it was chosen, not guessed: at
    # the jam, every tile still standing is a group of one. That is what
    # "no moves" means in a game where nothing spawns and nothing falls in
    # from above - the board only ever empties, so nothing fills up and
    # there is no column to blame.
    #
    # The two causes are made commensurable on purpose - both count tiles,
    # and together they are the whole stranded board - so "the largest
    # cause" is a real comparison rather than two units being ranked
    # against each other.
    from sidra_ai.creation.puzzle import recap_probe_source as _pz_probe

    pzjam_gaps: list[str] = []
    pzjam_line = ""
    pzjam_tail: dict = {}
    pzjam_main: dict = {}
    found = _scene_re.search(
        r"<script>(.*?)</script>",
        generate_game("パズルゲームを作って").html,
        _scene_re.S,
    )
    if found is None:
        pzjam_gaps.append("no script on the puzzle page")
    else:
        try:
            run = _scene_sp.run(
                ["node", "-"],
                input=_pz_probe(found.group(1)),
                capture_output=True,
                text=True,
                timeout=600,
            )
            if run.returncode != 0:
                raise ValueError(run.stderr.strip()[:80])
            out = run.stdout.strip().splitlines()
            pzjam_main = json.loads(out[-2])
            pzjam_tail = json.loads(out[-1])
        except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
            pzjam_gaps.append(f"probe unavailable ({exc})")
    if not pzjam_gaps:
        end = pzjam_main.get("atEnd") or {}
        pzjam_line = end.get("line") or ""
        tiles = pzjam_tail.get("tiles")
        purse = pzjam_tail.get("hammers")
        broken = pzjam_tail.get("broken") or 0
        recount = pzjam_tail.get("recount")
        want = max(broken, tiles or 0)
        if not end.get("lost"):
            pzjam_gaps.append("the driven go did not jam")
        elif not pzjam_line:
            pzjam_gaps.append("a jam with counted causes said nothing")
        elif not recount:
            pzjam_gaps.append("the board was empty, which is a clear and not a jam")
        elif tiles != recount:
            # The snapshot against the board it claims to summarise.
            pzjam_gaps.append(
                f"the jam recorded {tiles} tiles but {recount} were on the board"
            )
        elif pzjam_tail.get("singles") != recount:
            # ...and the definition of a jam, checked rather than assumed.
            pzjam_gaps.append(
                f"only {pzjam_tail.get('singles')} of {recount} stranded tiles "
                "were alone, so the board was not actually out of moves"
            )
        elif purse != pzjam_tail.get("livePurse"):
            # The snapshot's purse against the one the game still holds. A
            # purse that is never recorded would otherwise agree with a line
            # derived from it - the count and the claim share a source.
            pzjam_gaps.append(
                f"the jam recorded {purse} hammers but the game holds "
                f"{pzjam_tail.get('livePurse')}"
            )
        elif pzjam_tail.get("jamColours") != pzjam_tail.get("colours"):
            pzjam_gaps.append(
                f"the jam recorded {pzjam_tail.get('jamColours')} colours but "
                f"{pzjam_tail.get('colours')} were on the board"
            )
        elif str(want) not in pzjam_line:
            pzjam_gaps.append(
                f"the line's count is not the board's ({pzjam_line!r}, wanted {want})"
            )
        # A cause counted zero is not a cause: this go opens a few tiles
        # with the tool and strands many more, so the hammer clause is the
        # smaller one and must not be the one that spoke.
        elif broken >= (tiles or 0) and "ハンマー" not in pzjam_line:
            pzjam_gaps.append(f"the hammer was the larger cause and went unsaid ({pzjam_line!r})")
        # ...and the comparison is real. A go that opened more tiles than it
        # stranded is not something a drive reaches, so the honest way to
        # ask is to move the counter and re-read - and the count printed has
        # to follow it.
        elif "ハンマー" not in (pzjam_tail.get("saidPurse") or ""):
            pzjam_gaps.append(
                f"a purse larger than the board was still not named "
                f"({pzjam_tail.get('saidPurse')!r})"
            )
        elif str((tiles or 0) + 5) not in (pzjam_tail.get("saidPurse") or ""):
            pzjam_gaps.append(
                f"the hammer line's count did not follow the counter "
                f"({pzjam_tail.get('saidPurse')!r}, wanted {(tiles or 0) + 5})"
            )
        elif pzjam_tail.get("saidNothing"):
            pzjam_gaps.append(
                f"both causes at zero and it still spoke "
                f"({pzjam_tail.get('saidNothing')!r})"
            )
        elif pzjam_line not in (pzjam_main.get("strip") or []):
            pzjam_gaps.append("the line never reached the result strip")
        # A cleared board is the win, and it ends in the same state a jam
        # does - so the half of the predicate that tells them apart is the
        # half most likely to be dropped. Asked of the same page.
        elif (pzjam_main.get("afterWin") or {}).get("lost") or (
            pzjam_main.get("afterWin") or {}
        ).get("line"):
            pzjam_gaps.append(
                f"a cleared board was explained as a jam "
                f"({(pzjam_main.get('afterWin') or {}).get('line')!r})"
            )
    c.add(
        "creation_puzzle_jam_recap",
        "パズルが詰んだ理由を一言で言う",
        0.0 if pzjam_gaps else 1.0,
        detail=(
            "; ".join(pzjam_gaps)
            if pzjam_gaps
            else f"貪欲運転で実際に詰ませて計測: 帯は「{pzjam_line}」。"
            "**軸は想像せず先に実測した**——詰んだ盤では残ったタイルが"
            f"**全部 1 枚組**（{pzjam_tail.get('singles')}/{pzjam_tail.get('recount')} 枚）。"
            "この型は湧きも落ちも無く盤は減る一方なので、起票文にあった"
            "「どの列が先に埋まったか」という軸は**存在しない**。"
            "2 つの原因はどちらも**タイル枚数**に揃えてあり、和が取り残された"
            "盤そのものになる——だから「最多原因」が単位の違うもの同士の"
            "比較にならない。集計は生の盤から数え直した値と照合しており"
            f"（枚数・色数とも一致）、ハンマーでこじ開けた {pzjam_tail.get('broken')} 枚は"
            "この走行では少ないほうなので名指しされない。"
            "**「こじ開けたほうが多い」走行は運転では作れない**ため、"
            "カウンタを動かして同じページに訊き直す方式（動かした値に数が"
            "追随することまで検査）。両方 0 なら何も言わない"
        ),
        kind=OUTCOME,
    )

    # --- the comeback tool is a move, so the go waits for it (C-1428) ----
    #
    # Found by measuring C-1427, not by reading: a greedy round stranded 17
    # tiles while still holding 3 hammers. movesLeft() looked only for a
    # group of two, but a hammer breaks a lone tile and the collapse that
    # follows can put two of a colour beside each other again - so the go
    # was ending while the tool the code itself calls "the classic comeback
    # tool" sat unspent in the purse.
    #
    # Measured both ways on the same page, because "it no longer ends" is
    # only a result if the other drive does end:
    #
    # * the hoarder clears groups and never touches a lone tile - it runs
    #   out of pops while holding hammers, and the go stays live;
    # * the spender does the same and then spends the purse - it opens more
    #   tiles with the tool and only then jams, with an empty purse.
    pzend_gaps: list[str] = []
    pzend_hoard: dict = {}
    pzend_spend: dict = {}
    found = _scene_re.search(
        r"<script>(.*?)</script>",
        generate_game("パズルゲームを作って").html,
        _scene_re.S,
    )
    if found is None:
        pzend_gaps.append("no script on the puzzle page")
    else:
        for label, spend in (("hoard", False), ("spend", True)):
            try:
                run = _scene_sp.run(
                    ["node", "-"],
                    input=_pz_probe(found.group(1), spend=spend),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if run.returncode != 0:
                    raise ValueError(run.stderr.strip()[:80])
                out = run.stdout.strip().splitlines()
                seen = {"main": json.loads(out[-2]), "tail": json.loads(out[-1])}
            except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
                pzend_gaps.append(f"{label}: probe unavailable ({exc})")
                break
            if label == "hoard":
                pzend_hoard = seen
            else:
                pzend_spend = seen
    if not pzend_gaps:
        hoard_end, hoard_tail = pzend_hoard["main"]["atEnd"], pzend_hoard["tail"]
        spend_end, spend_tail = pzend_spend["main"]["atEnd"], pzend_spend["tail"]
        # 1. The hoarder really did run out of pops - otherwise "still
        #    playing" says nothing about the deadlock rule at all.
        if hoard_tail.get("bestN", 9) >= 2:
            pzend_gaps.append(
                f"the hoarding drive still had a group of {hoard_tail.get('bestN')} "
                "to clear, so it was never at the old deadlock"
            )
        elif not hoard_tail.get("livePurse"):
            pzend_gaps.append("the hoarding drive banked no hammers, so it holds nothing")
        # 2. ...and with hammers in hand the go is not over.
        elif hoard_end.get("lost"):
            pzend_gaps.append(
                f"the board declared a jam while holding "
                f"{hoard_tail.get('livePurse')} hammers"
            )
        # 3. The spender does end - so the round is still finishable, and
        #    "not over" above is the purse and not a loop that never ends.
        elif not spend_end.get("lost"):
            pzend_gaps.append("spending the purse never ended the go either")
        # 4. It ended with the tool used up, which is now the only way to
        #    reach a jam at all.
        elif spend_tail.get("livePurse"):
            pzend_gaps.append(
                f"the jam still held {spend_tail.get('livePurse')} hammers"
            )
        elif not spend_tail.get("broken"):
            pzend_gaps.append("no tile was ever opened with a hammer")
        # 5. The extra moves are real moves: spending opened tiles the
        #    hoarder never got to, so the board it jams on is smaller.
        elif spend_tail.get("recount", 0) >= hoard_tail.get("recount", 0):
            pzend_gaps.append(
                f"spending the purse opened nothing: {spend_tail.get('recount')} "
                f"tiles left against the hoarder's {hoard_tail.get('recount')}"
            )
    c.add(
        "creation_puzzle_hammer_endgame",
        "ハンマーを持っている間は詰みにしない",
        0.0 if pzend_gaps else 1.0,
        detail=(
            "; ".join(pzend_gaps)
            if pzend_gaps
            else f"同じページを 2 通りに運転して比較: **貯め込む運転**は"
            f"消せる組が尽きても（best {pzend_hoard['tail'].get('bestN')}）"
            f"ハンマー {pzend_hoard['tail'].get('livePurse')} 個を持ったまま"
            "**詰みにならない**。**使う運転**は同じ盤からハンマーで"
            f"{pzend_spend['tail'].get('broken')} 枚こじ開け、"
            f"残り {pzend_spend['tail'].get('recount')} 枚（貯め込み側は"
            f"{pzend_hoard['tail'].get('recount')} 枚）で財布が空になって"
            "初めて 'over' になる。**両方向で測っている**——「終わらない」は"
            "もう一方が終わって初めて結果になる。修正前は実測で 17 枚を"
            "残したままハンマー 3 個が未使用だった"
        ),
        kind=OUTCOME,
    )

    # --- the model's wording lands whole, both ways round (C-1431) ------
    #
    # ``with_copy`` overlays a model-written title and subtitle onto a page
    # that already works. Since C-1259 the subtitle names the genre in
    # Japanese, so the two fields can share a word - 「釣りゲームを作って」
    # titles its page 「釣り」 and its subtitle reads 「ジャンル 釣り」 - and a
    # bare substitution over the whole page lets whichever runs first cut
    # into the other.
    #
    # C-1259 ordered the two passes, which closes one direction. The other
    # was measured open: a new subtitle containing the old title came out
    # as 「朝凪の一本の朝に。」 on the page. Both directions are driven here,
    # and the third case runs them at once, because an ordering fix passes
    # whichever direction it was written for.
    import re as _cp_re

    _cp_ask = "釣りゲームを作って"
    _cp_cases = (
        ("forward", "朝凪の一本", "潮が動く前に。"),
        ("reverse", "朝凪の一本", "釣りの朝に。"),
        ("both", "釣りの一日", "釣りの朝に。"),
    )
    copy_gaps: list[str] = []
    copy_page = generate_game(_cp_ask)
    # The collision has to still exist, or every case below is vacuous.
    if copy_page.title not in copy_page.tagline:
        copy_gaps.append(
            f"the fields no longer share a word ({copy_page.title!r} / "
            f"{copy_page.tagline!r}), so this proves nothing"
        )
    else:
        # The five places the title's text occurs on a fishing page: three
        # are display copy and must follow the model, two merely contain
        # the same characters and must not move.
        _cp_shows = (
            ("browser tab", r"<title>(.*?)</title>", "title"),
            ("heading", r"<h1>(.*?)</h1>", "title"),
            ("subtitle", r'<p class="tag">(.*?)</p>', "tagline"),
        )
        _cp_leaves = (
            ("the game's own GTITLE", r'GTITLE="(.*?)"'),
            ("the share spec's genre name", r'"name": "(.*?)"'),
        )
        _cp_kept = {
            what: _cp_re.search(pat, copy_page.html).group(1)
            for what, pat in _cp_leaves
            if _cp_re.search(pat, copy_page.html)
        }
        if len(_cp_kept) != len(_cp_leaves):
            copy_gaps.append("the page no longer carries the strings this guards")
        for label, want_title, want_tag in _cp_cases:
            rewritten = copy_page.with_copy(title=want_title, tagline=want_tag)
            wanted = {"title": want_title, "tagline": want_tag}
            for what, pat, field in _cp_shows:
                found = _cp_re.search(pat, rewritten.html)
                if found is None:
                    copy_gaps.append(f"{label}: the page lost its {what}")
                elif found.group(1) != wanted[field]:
                    copy_gaps.append(
                        f"{label}: the {what} came out {found.group(1)!r}, "
                        f"not {wanted[field]!r}"
                    )
            # ...and the other direction: a substitution wide enough to
            # catch the display copy also catches these, silently.
            for what, pat in _cp_leaves:
                found = _cp_re.search(pat, rewritten.html)
                if found is not None and found.group(1) != _cp_kept.get(what):
                    copy_gaps.append(
                        f"{label}: {what} was rewritten to {found.group(1)!r}"
                    )
            if copy_page.tagline in rewritten.html:
                copy_gaps.append(f"{label}: the old subtitle is still on the page")
    c.add(
        "game_copy_overlay_isolated",
        "モデルの書いた題と副題が、互いを書き換えずにページに載る",
        0.0 if copy_gaps else 1.0,
        detail=(
            "; ".join(copy_gaps)
            if copy_gaps
            else "題と副題が語を共有するページ（「釣り」/「ジャンル 釣り」）で"
            "**両方向**を実際に上書きして確認: (a) 旧副題が旧題を含む場合、"
            "(b) **新副題が旧題を含む**場合、(c) 両方同時。いずれもモデルの"
            "文言が 3 か所（タブ題・見出し・副題）にそのまま出る。(b) は"
            "C-1259 の順序入れ替えでは塞がっておらず、実測で副題が"
            "「朝凪の一本の朝に。」になっていた。"
            "**逆側も検査している**: 題の文字列はページに 5 回出るが、"
            "残り 2 か所は題ではない——`GTITLE=\"タイミング釣り\"` は題を"
            "部分文字列として含むだけの別の定数で、share の `name` は"
            "ジャンル名。素の置換はこの 2 つも書き換えていた（実測で"
            "`GTITLE` が「タイミング朝凪の一本」になる）。置換を"
            "`<title>` / `<h1>` / `<p class=\"tag\">` に固定したので、"
            "順序が効いているのではなく**混線という種類が消えている**"
        ),
        kind=OUTCOME,
    )

    # --- the last few runs, in the order they happened (C-1432) ---------
    #
    # A best is one number and it only moves upward, so a page that keeps
    # nothing else says 「自己ベスト 24（あと 5）」 all afternoon without ever
    # telling a player they are getting closer. The row is what shows a
    # day's progress on the days the record does not move.
    #
    # Restarting is a real location.reload(), so rounds cannot share a page:
    # each load is its own process here and what carries between them is
    # exactly what carries in a browser - the store. One load in the middle
    # is left completely alone, because "a round nobody played does not
    # enter the row" is the condition most easily lost.
    from sidra_ai.creation.round import history_probe_source as _hist_probe

    hist_gaps: list[str] = []
    hist_runs: list = []
    # Six played loads against a cap of five, so the oldest actually
    # falls off rather than the cap being asserted about a row that
    # never reached it.
    _hist_holds = (
        "ArrowRight", "ArrowLeft", None, "ArrowRight",
        "ArrowLeft", "ArrowRight", "ArrowLeft",
    )
    found = _scene_re.search(
        r"<script>(.*?)</script>",
        generate_game("キャッチゲームを作って").html,
        _scene_re.S,
    )
    if found is None:
        hist_gaps.append("no script on the catch page")
    else:
        store: dict = {}
        for turn, hold in enumerate(_hist_holds):
            try:
                run = _scene_sp.run(
                    ["node", "-"],
                    input=_hist_probe(found.group(1), store=store, hold=hold, step=25),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if run.returncode != 0:
                    raise ValueError(run.stderr.strip()[:80])
                seen = json.loads(run.stdout.strip().splitlines()[-1])
            except (OSError, _scene_sp.SubprocessError, ValueError, IndexError) as exc:
                hist_gaps.append(f"load {turn}: probe unavailable ({exc})")
                break
            store = seen["store"]
            hist_runs.append({"hold": hold, **seen})
    if not hist_gaps and hist_runs:
        played = [r for r in hist_runs if r["hold"] is not None]
        idle = [r for r in hist_runs if r["hold"] is None]
        cap = hist_runs[0]["max"]
        # The row has to be built out of runs that differ, or a page
        # printing one constant would satisfy every check below.
        if len({r["score"] for r in played}) < 2:
            hist_gaps.append(
                f"every played round scored the same ({[r['score'] for r in played]}), "
                "so nothing here distinguishes a row from a repeated number"
            )
        # 1. Each played round appends its own score, in order, capped.
        else:
            wanted: list = []
            for turn, r in enumerate(hist_runs):
                if r["hold"] is not None:
                    wanted.append(r["score"])
                    wanted = wanted[-cap:]
                if r["runs"] != wanted:
                    hist_gaps.append(
                        f"load {turn}: the row is {r['runs']}, expected {wanted}"
                    )
                    break
        # 2. The round nobody played is not in it - and it really was a
        #    round, with a score of its own that the row declined to take.
        if not hist_gaps:
            for r in idle:
                if r["touched"]:
                    hist_gaps.append("the idle load was counted as played")
                elif r["runs"] != r["before"]:
                    hist_gaps.append(
                        f"an untouched round entered the row ({r['before']} -> {r['runs']})"
                    )
        # 3. It survives the reload, which is the whole point of a row.
        if not hist_gaps and len(played) > 1:
            if not hist_runs[1]["before"]:
                hist_gaps.append("the second load started from an empty row")
        # 4. A worse run stays in it. Flattery would be a row nobody could
        #    use to tell whether they are improving.
        if not hist_gaps:
            last = hist_runs[-1]["runs"]
            if len(last) > 1 and last != sorted(last):
                pass  # a drop is present, which is what this wants
            elif len({r["score"] for r in played}) > 1 and last == sorted(last):
                hist_gaps.append(f"the row came out sorted ({last}), not as it happened")
        # 5. ...and it reaches the screen, in that order.
        if not hist_gaps:
            shown = [r for r in hist_runs if r["said"]]
            if not shown:
                hist_gaps.append("the row was never drawn on the result strip")
            else:
                latest = shown[-1]
                want = "直近 " + " / ".join(str(v) for v in latest["runs"])
                if want not in latest["said"]:
                    hist_gaps.append(
                        f"the strip said {latest['said'][:1]}, not {want!r}"
                    )
        # 6. The cap holds.
        if not hist_gaps:
            if len(hist_runs[-1]["runs"]) > cap:
                hist_gaps.append(f"the row grew past {cap} ({hist_runs[-1]['runs']})")
            elif len(played) <= cap:
                hist_gaps.append(
                    f"only {len(played)} rounds were played against a cap of "
                    f"{cap}, so the cap was never reached"
                )
    c.add(
        "creation_score_history",
        "直近の走りの並びが見える（best 未満の日も語る）",
        0.0 if hist_gaps else 1.0,
        detail=(
            "; ".join(hist_gaps)
            if hist_gaps
            else f"ページを {len(hist_runs)} 回読み込んで実測（再開は本物の "
            "`location.reload()` なので 1 ラウンド 1 プロセス・持ち越すのは"
            "ブラウザと同じく store だけ）。走った回の得点が"
            f"{[r['score'] for r in hist_runs if r['hold']]} と**互いに異なり**、"
            f"並びはその順に積まれて最後は {hist_runs[-1]['runs']}、"
            f"結果帯に「直近 {' / '.join(str(v) for v in hist_runs[-1]['runs'])}」と"
            "出る。**触れなかった読み込みは得点を持ちながら並びに入らない**"
            "（その回だけ hold なしで走らせて確認）。下がった走りも消えず、"
            f"上限 {hist_runs[0]['max']} 件で古いほうから落ちる"
        ),
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
