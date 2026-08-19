#!/usr/bin/env python3
"""Measure what SIDRA can actually do against the real repositories.

Why this exists
---------------

Every number this project had before this script was an inside number. The
test suite scores our assertions against our code. ``verify_gate_recall.py``
scores our detectors against cases we wrote for them. The retrieval eval
scores the retriever against chunks we authored so they would be found. All
of them can pass while SIDRA answers nothing, because none of them asks a
question whose answer we did not also write.

This script asks that question. It ingests the five allowlisted repositories
as they actually are -- through the real gate and the real store -- and then
puts real operator questions to the real retriever. The headline number is
how many of those questions SIDRA can surface evidence for. It can go down
when someone tightens a detector, and that is the point: the safety numbers
and the product number are finally on the same page.

What it reports
---------------

``corpus``      documents found, and how many the gate admits (reachability).
``answerable``  questions whose evidence the retriever returns in the top-k.
``mrr``         mean reciprocal rank of the first chunk carrying the evidence.
``flag_rate``   share of the corpus quarantined or blocked.

Usage
-----

    python scripts/measure_outcomes.py \\
        tukemen-rgb/sidra-ai=. \\
        tukemen-rgb/site=/workspace/tukemen-rgb/site \\
        ...

Repositories that are not checked out are reported as missing rather than
silently dropped: a number measured over four repositories must not be
comparable-looking with one measured over five.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.documents import (  # noqa: E402
    Document,
    Provenance,
    SourceType,
    TrustLevel,
)
from sidra_ai.evals.outcome_questions import OUTCOME_QUESTIONS  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.decisions import Decision  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".py", ".ts", ".tsx", ".js", ".jsx",
                 ".json", ".yml", ".yaml", ".toml", ".html", ".css", ".sh"}
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "__pycache__",
             ".venv", "venv", ".pytest_cache", "coverage", ".sidra"}

TOP_K = 5


def head_sha(repo_root: Path) -> str:
    """Return the checked-out commit, or a synthetic one when git is absent.

    Provenance requires a 40-character sha. A corpus measured outside a git
    checkout is still worth measuring, so fall back rather than refuse.
    """

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=30,
        )
        sha = out.stdout.strip()
        if len(sha) == 40:
            return sha
    except (subprocess.SubprocessError, OSError):
        pass
    return "0" * 40


#: The question set states every ``answer_marker`` verbatim, so indexing it
#: hands the retriever the answer key. Measured against a checkout of this
#: repository alone, every question scored rank 1 - and the evidence chunk was
#: ``src/sidra_ai/evals/outcome_questions.py`` each time. The grounding check
#: passed for the same reason: it found the marker in the file that declares
#: it. A corpus that contains the answer key measures nothing, and it does so
#: while printing 100%.
EXCLUDED_FROM_CORPUS = ("src/sidra_ai/evals/outcome_questions.py",)


def iter_files(repo_root: Path):
    """Yield (relative_path, content) for readable text files.

    The answer key is skipped: see ``EXCLUDED_FROM_CORPUS``.
    """

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.relative_to(repo_root).as_posix() in EXCLUDED_FROM_CORPUS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not content.strip():
            continue
        yield path.relative_to(repo_root).as_posix(), content


def source_type_for(rel_path: str) -> SourceType:
    if rel_path.lower().startswith("readme"):
        return SourceType.README
    if rel_path.startswith("docs/"):
        return SourceType.DOCS
    return SourceType.DOCS


def ingest(
    targets: list[tuple[str, Path]],
    store: DocumentStore,
    gate: SecurityGate,
) -> dict:
    """Ingest each repository through the real gate; report what got in."""

    per_repo: dict[str, dict] = {}
    for repository, root in targets:
        sha = head_sha(root)
        counts = {"total": 0, "allow": 0, "quarantine": 0, "block": 0}
        for rel_path, content in iter_files(root):
            counts["total"] += 1
            provenance = Provenance(
                source="github",
                repository=repository,
                path=rel_path,
                commit_sha=sha,
                timestamp=datetime.now(timezone.utc),
                source_type=source_type_for(rel_path),
                trust_level=TrustLevel.INTERNAL_REPO,
                license="proprietary",
            )
            result = gate.inspect(
                content, source="github", repository=repository
            )
            if result.decision is Decision.ALLOW:
                counts["allow"] += 1
                store.add(
                    Document(
                        content=result.content,
                        provenance=provenance,
                        redacted=result.redacted,
                    ),
                    gate_result=result,
                )
            elif result.decision is Decision.QUARANTINE:
                counts["quarantine"] += 1
            else:
                counts["block"] += 1
        per_repo[repository] = counts
    return per_repo


def marker_present_in_corpus(
    marker: str, repository: str, targets: list[tuple[str, Path]]
) -> bool:
    """Check the marker exists on disk, before retrieval is even involved.

    Guards against a question drifting into self-reference: if someone adds
    a document so a question passes, this still returns True, but if a
    question is written with no basis in the corpus at all it fails loudly
    instead of scoring zero forever and looking like a retrieval problem.

    Only the question's own repository counts. Searching every target lets a
    question about one repository be grounded by a copy of its marker
    somewhere else - which is exactly how the answer key grounded all 18
    questions while none of the repositories they name was checked out.
    """

    for candidate, root in targets:
        if candidate != repository:
            continue
        for _rel_path, content in iter_files(root):
            if marker in content:
                return True
    return False


def measure_answerable(retriever: BM25Retriever, targets: list[tuple[str, Path]]) -> dict:
    """Ask each question and see whether the answering evidence comes back.

    Also computes a null: for each question, whether a marker belonging to a
    *different* repository turns up in the same result set. Retrieval over a
    corpus where every repository discusses the same business will surface
    plausible-looking neighbours for almost any query, so a raw hit rate can
    look excellent while measuring nothing. The gap between the two is the
    part that reflects retrieval rather than topic overlap, and the report
    prints them together so the headline can never be read without its null.

    The control deliberately draws from other repositories, not from adjacent
    questions: several questions here are answered by the same document, so a
    neighbour-based control scores near the real rate and hides the problem.
    """

    rows = []
    reciprocal_ranks: list[float] = []
    answered = 0
    control_hits = 0
    ungrounded: list[str] = []

    for question in OUTCOME_QUESTIONS:
        if not marker_present_in_corpus(
            question.answer_marker, question.repository, targets
        ):
            ungrounded.append(question.name)
            rows.append({
                "name": question.name,
                "repository": question.repository,
                "rank": None,
                "status": "ungrounded",
            })
            continue

        results = retriever.search(question.question, top_k=TOP_K)
        retrieved_text = " ".join(result.chunk.content for result in results)
        foreign = [
            other.answer_marker for other in OUTCOME_QUESTIONS
            if other.repository != question.repository
        ]
        if any(marker in retrieved_text for marker in foreign):
            control_hits += 1
        rank = None
        for position, result in enumerate(results, start=1):
            # The chunk has to come from the repository the question is about.
            # Without that condition a copy of the marker anywhere in the
            # corpus counts as the answer, which is how the answer key scored
            # rank 1 on every question it also defined.
            if result.chunk.provenance.repository != question.repository:
                continue
            if question.answer_marker in result.chunk.content:
                rank = position
                break
        if rank is None:
            rows.append({
                "name": question.name,
                "repository": question.repository,
                "rank": None,
                "status": "miss",
            })
            reciprocal_ranks.append(0.0)
        else:
            answered += 1
            reciprocal_ranks.append(1.0 / rank)
            rows.append({
                "name": question.name,
                "repository": question.repository,
                "rank": rank,
                "status": "hit",
            })

    scored = len(OUTCOME_QUESTIONS) - len(ungrounded)
    by_tier: dict[str, dict] = {}
    for question in OUTCOME_QUESTIONS:
        row = next(r for r in rows if r["name"] == question.name)
        if row["status"] == "ungrounded":
            continue
        bucket = by_tier.setdefault(question.tier, {"scored": 0, "answered": 0})
        bucket["scored"] += 1
        if row["status"] == "hit":
            bucket["answered"] += 1
    for bucket in by_tier.values():
        bucket["rate"] = bucket["answered"] / bucket["scored"] if bucket["scored"] else 0.0

    return {
        "questions": len(OUTCOME_QUESTIONS),
        "scored": scored,
        "answered": answered,
        "answerable_rate": (answered / scored) if scored else 0.0,
        "mrr": (sum(reciprocal_ranks) / len(reciprocal_ranks)) if reciprocal_ranks else 0.0,
        "by_tier": by_tier,
        "control_hits": control_hits,
        "control_rate": (control_hits / scored) if scored else 0.0,
        "discrimination": ((answered - control_hits) / scored) if scored else 0.0,
        "ungrounded": ungrounded,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", metavar="repo=path")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    targets: list[tuple[str, Path]] = []
    missing: list[str] = []
    for spec in args.targets:
        if "=" not in spec:
            print(f"bad target {spec!r}; expected repo=path", file=sys.stderr)
            return 2
        repository, raw_path = spec.split("=", 1)
        path = Path(raw_path)
        if not path.is_dir():
            missing.append(repository)
            continue
        targets.append((repository, path))

    if not targets:
        print("no repository was checked out; nothing measured", file=sys.stderr)
        return 2

    gate = SecurityGate(
        GatePolicy(), allowed_repositories=[repo for repo, _ in targets]
    )
    store = DocumentStore(gate)
    per_repo = ingest(targets, store, gate)
    retriever = BM25Retriever(store)
    answerable = measure_answerable(retriever, targets)

    total = sum(c["total"] for c in per_repo.values())
    allowed = sum(c["allow"] for c in per_repo.values())
    flagged = total - allowed
    report = {
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repositories_measured": [repo for repo, _ in targets],
        "repositories_missing": missing,
        "corpus": {
            "documents": total,
            "reachable": allowed,
            "reachability_rate": (allowed / total) if total else 0.0,
            "flag_rate": (flagged / total) if total else 0.0,
            "per_repository": per_repo,
        },
        "answerable": answerable,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not answerable["ungrounded"] else 1

    print(f"measured at {report['measured_at']}")
    if missing:
        print(f"NOT MEASURED (not checked out): {', '.join(missing)}")
    print()
    print(f"{'repository':28s} {'docs':>6s} {'reach':>6s} {'flag%':>7s}")
    print("-" * 50)
    for repository, counts in per_repo.items():
        rate = 100 * (counts["total"] - counts["allow"]) / counts["total"] if counts["total"] else 0
        print(f"{repository:28s} {counts['total']:6d} {counts['allow']:6d} {rate:6.1f}%")
    print("-" * 50)
    print(f"{'合計':28s} {total:6d} {allowed:6d} "
          f"{100 * flagged / total if total else 0:6.1f}%")
    print()
    print("--- 外の数字 ---")
    print(f"到達率        {100 * report['corpus']['reachability_rate']:.1f}%"
          f"  ({allowed}/{total} 文書が検索可能)")
    if not answerable["scored"]:
        # 0/0 must not render as 0.0%. A rate printed over an empty
        # denominator reads as "retrieval found nothing", when what actually
        # happened is that no question had a corpus to be answered from.
        print("回答可能率    測定不能  (採点できた問 0 問。下の未接地を見ること)")
    else:
        print(f"回答可能率    {100 * answerable['answerable_rate']:.1f}%"
              f"  ({answerable['answered']}/{answerable['scored']} 問で根拠を top-{TOP_K} に提示)")
    for tier in ("direct", "paraphrase"):
        bucket = answerable["by_tier"].get(tier)
        if bucket:
            label = "  うち直接語" if tier == "direct" else "  うち言い換え"
            print(f"{label:12s}  {100 * bucket['rate']:.1f}%"
                  f"  ({bucket['answered']}/{bucket['scored']})")
    if answerable["scored"]:
        print(f"MRR           {answerable['mrr']:.3f}")
        print(f"対照(無関係)  {100 * answerable['control_rate']:.1f}%"
              f"  ({answerable['control_hits']}/{answerable['scored']} 他リポジトリの根拠が紛れ込む)")
        print(f"識別力        {100 * answerable['discrimination']:+.1f} ポイント"
              f"  (回答可能率 - 対照。ここが 0 に近い数字は何も測っていない)")
    else:
        print("MRR           測定不能")
        print("対照(無関係)  測定不能")
        print("識別力        測定不能  (質問の対象リポジトリが 1 つも checkout されていない)")
    print()
    for row in answerable["rows"]:
        mark = {"hit": "OK  ", "miss": "MISS", "ungrounded": "??? "}[row["status"]]
        rank = f"rank {row['rank']}" if row["rank"] else "-"
        print(f"  {mark} {row['name']:32s} {row['repository']:24s} {rank}")

    if answerable["ungrounded"]:
        print("\nungrounded questions (no evidence in the corpus): "
              f"{', '.join(answerable['ungrounded'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
