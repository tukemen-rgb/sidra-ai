"""Measure the security gate's decisions against real repository content.

Safety: this script never prints a detected value. It reports only the file
path, the detector label, the severity and the decision. That is the whole
point of the exercise - if measuring the leak detector leaked, the tool would
be the vulnerability.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.security.decisions import Decision, FindingCategory  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".py", ".ts", ".tsx", ".js", ".jsx",
                 ".json", ".yml", ".yaml", ".toml", ".html", ".css", ".sh", ""}
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "__pycache__",
             ".venv", "venv", ".pytest_cache", "coverage", ".sidra"}


def iter_documents(repo_root: Path, repository: str):
    """Yield (kind, path, content) for README, docs and source files."""

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not content.strip():
            continue
        rel = path.relative_to(repo_root).as_posix()
        kind = "readme" if rel.lower().startswith("readme") else (
            "docs" if rel.startswith("docs/") else "file"
        )
        yield kind, rel, content


def iter_commits(repo_root: Path, limit: int = 300):
    """Yield (kind, ref, message) for recent commit messages."""

    try:
        out = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%H%x00%s%n%b%x01"],
            cwd=repo_root, capture_output=True, text=True, timeout=120,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return
    for record in out.split("\x01"):
        if "\x00" not in record:
            continue
        sha, message = record.split("\x00", 1)
        sha = sha.strip()
        if sha and message.strip():
            yield "commit", f"commit/{sha[:12]}", message


def measure(repo_root: Path, repository: str, gate: SecurityGate) -> dict:
    decisions: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    detectors: Counter[str] = Counter()
    flagged: list[tuple[str, str, str, str, str]] = []
    total = 0

    sources = list(iter_documents(repo_root, repository)) + list(iter_commits(repo_root))
    for kind, ref, content in sources:
        total += 1
        result = gate.inspect(content, source="github", repository=repository)
        decisions[result.decision.value] += 1
        for finding in result.findings:
            categories[finding.category.value] += 1
            detectors[finding.detector] += 1
        if result.decision is not Decision.ALLOW:
            worst = sorted(
                result.findings,
                key=lambda f: {"critical": 3, "high": 2, "medium": 1, "low": 0}[
                    f.severity.value
                ],
                reverse=True,
            )
            label = worst[0].detector if worst else "?"
            cat = worst[0].category.value if worst else "?"
            sev = worst[0].severity.value if worst else "?"
            flagged.append((kind, ref, cat, label, sev))

    return {
        "repository": repository,
        "total": total,
        "decisions": decisions,
        "categories": categories,
        "detectors": detectors,
        "flagged": flagged,
    }


def main() -> int:
    targets = [(Path(a.split("=")[1]), a.split("=")[0]) for a in sys.argv[1:]]
    gate = SecurityGate(
        GatePolicy(),
        allowed_repositories=[repo for _, repo in targets],
    )

    grand = Counter()
    print(f"{'repository':28s} {'docs':>6s} {'allow':>7s} {'quar':>6s} {'block':>6s} {'flag%':>7s}")
    print("-" * 66)
    all_flagged = []
    for root, repo in targets:
        if not root.exists():
            print(f"{repo:28s} (未取得)")
            continue
        r = measure(root, repo, gate)
        d = r["decisions"]
        flag_rate = 100 * (d["quarantine"] + d["block"]) / r["total"] if r["total"] else 0
        print(f"{repo:28s} {r['total']:6d} {d['allow']:7d} {d['quarantine']:6d} "
              f"{d['block']:6d} {flag_rate:6.1f}%")
        grand.update(d)
        all_flagged.extend((repo, *f) for f in r["flagged"])
        grand.update({f"det:{k}": v for k, v in r["detectors"].items()})

    total_docs = grand["allow"] + grand["quarantine"] + grand["block"]
    if not total_docs:
        print("\n対象なし")
        return 1
    flagged_n = grand["quarantine"] + grand["block"]
    print("-" * 66)
    print(f"{'合計':28s} {total_docs:6d} {grand['allow']:7d} {grand['quarantine']:6d} "
          f"{grand['block']:6d} {100*flagged_n/total_docs:6.1f}%")

    print("\n=== 検知器別の発火回数（多い順） ===")
    dets = sorted(((k[4:], v) for k, v in grand.items() if k.startswith("det:")),
                  key=lambda x: -x[1])
    for name, count in dets[:20]:
        print(f"  {name:28s} {count:6d}")

    print(f"\n=== 索引から外れた文書 {len(all_flagged)} 件（値は非表示） ===")
    for repo, kind, ref, cat, label, sev in all_flagged[:60]:
        print(f"  [{sev:8s}] {cat:16s} {label:26s} {repo}:{ref}")
    if len(all_flagged) > 60:
        print(f"  ... 他 {len(all_flagged)-60} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
