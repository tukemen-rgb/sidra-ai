"""Judge the one number the offline instrument cannot hold: real ingestion.

``product_metrics.py`` has to run offline in seconds, so it can say whether
the refresher *runs* but not whether a run *produces an index*. Between
2026-08-23 and 2026-08-24 that gap hid the only thing that was broken: the
token could not read pulls or issues, every repository came back
``partial_fetch`` with ``indexed 0``, and not one number in either judge
moved. When the permission was added and the five repositories indexed 482
documents, ``--compare`` still printed NO MOVEMENT - the instrument had
nothing to say about the biggest change the product had seen in a week.

This script holds that number, on the same terms as the answerable judge:

* ``--save`` writes a snapshot, ``--compare`` reports movement against one;
* exit 0 moved, 1 nothing moved, 2 regressed (do not merge), and
  **3 cannot judge** - no token, or the network refused before GitHub was
  reached. An environment that cannot measure must say so instead of
  printing a zero that reads like a regression.

Two rules keep it honest.

**The corpus is not ours.** Four of the five repositories belong to other
people, and a document count rises when they write documents. Heads are
recorded beside the counts, and a run whose heads moved does not bank an
increase - otherwise "someone else pushed a file" becomes our progress.

**Fetches must stay complete.** ``indexed`` alone can look healthy while a
repository silently degrades to a partial fetch; the count of repositories
that fetched completely is a guard, and losing one is a regression even if
the document total happens to rise.

Usage::

    python scripts/check_ingestion_regression.py --save /tmp/ing-before.json
    python scripts/check_ingestion_regression.py --compare /tmp/ing-before.json

Needs ``SIDRA_GITHUB_TOKEN``. On a network that terminates TLS it also needs
``SIDRA_CA_BUNDLE`` naming that network's CA: the product transport sets
``trust_env=False`` on purpose, so the CA has to be named deliberately
rather than verification being switched off.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.config.settings import Settings  # noqa: E402

EXIT_MOVED = 0
EXIT_NO_MOVEMENT = 1
EXIT_REGRESSED = 2
EXIT_CANNOT_JUDGE = 3

# Pinned 2026-08-24 under the first real measurement (482 documents over the
# five repositories, all five complete). Floors sit below the measurement so
# ordinary churn in other people's repositories does not fail the build; they
# exist to catch the failure that actually happened - a permission or scope
# change that drops whole repositories to zero.
MIN_DOCUMENTS_INDEXED = 400
MIN_REPOSITORIES_INDEXED = 5

_OUTCOME_KEYS = ("github_documents_indexed", "github_repositories_indexed")
_GUARD_KEYS = ("github_complete_fetches",)


def _ingest_through_the_product(repositories: list[str]) -> dict:
    """Run the real ingestion path - the endpoint an operator would call.

    Measuring through ``POST /v1/github/analyze`` rather than calling the
    ingestion internals keeps this judging the program that ships: repository
    validation, the security gate and the store all sit in the path.
    """

    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/github/analyze", json={"repositories": repositories}
        )
    if response.status_code != 200:
        raise CannotJudge(
            f"the analyze endpoint answered {response.status_code}, so no "
            "ingestion happened"
        )
    return response.json()["ingestion"]


class CannotJudge(Exception):
    """The environment could not produce a measurement."""


def _snapshot(ingestion: dict) -> dict:
    """Reduce an analyze response to the numbers worth comparing."""

    repositories = ingestion.get("repositories", [])
    indexed = {
        repository["repository"]: int(repository.get("indexed", 0))
        for repository in repositories
    }
    complete = [
        repository
        for repository in repositories
        # An empty `skipped_reason` on a changed run means the whole
        # repository was fetched; `index_rehydrated` is the head-match skip,
        # which is a complete fetch that did not need repeating. Anything
        # else - `partial_fetch` above all - is not complete.
        if repository.get("skipped_reason", "") in ("", "index_rehydrated")
        and not repository.get("error", "")
    ]
    return {
        "github_documents_indexed": int(ingestion.get("total_indexed", 0)),
        "github_repositories_indexed": sum(1 for count in indexed.values() if count),
        "github_complete_fetches": len(complete),
        "documents_by_repository": indexed,
        # Attribution: if a head moved between --save and --compare, a rise in
        # the document count may belong to that push rather than to the change
        # under test. Twelve characters is enough to tell two commits apart
        # and short enough to read in a log.
        "corpus_heads": {
            repository["repository"]: str(repository.get("head_sha", ""))[:12]
            for repository in repositories
        },
        "repositories": sorted(indexed),
    }


def _floor_failures(snapshot: dict) -> list[str]:
    failures = []
    if snapshot["github_documents_indexed"] < MIN_DOCUMENTS_INDEXED:
        failures.append(
            f"documents {snapshot['github_documents_indexed']} < "
            f"{MIN_DOCUMENTS_INDEXED}"
        )
    if snapshot["github_repositories_indexed"] < MIN_REPOSITORIES_INDEXED:
        failures.append(
            f"repositories with an index "
            f"{snapshot['github_repositories_indexed']} < "
            f"{MIN_REPOSITORIES_INDEXED}"
        )
    return failures


def _compare(before: dict, now: dict) -> int:
    """Report movement with the same semantics as the other two judges."""

    if before.get("repositories") not in (None, now.get("repositories")):
        print(
            "repository scope changed between --save and --compare "
            f"({before.get('repositories')} -> {now.get('repositories')}): "
            "totals over different scopes are not comparable, so increases "
            "are NOT banked this run."
        )
        same_scope = False
    else:
        same_scope = True

    drifted = [
        f"{repository} {before.get('corpus_heads', {}).get(repository, '?')} "
        f"-> {head}"
        for repository, head in now.get("corpus_heads", {}).items()
        if before.get("corpus_heads", {}).get(repository) not in (None, head)
    ]
    if drifted:
        print("corpus moved between --save and --compare: " + "; ".join(drifted))
        print(
            "A document count rises when other people write documents, so "
            "increases are NOT banked this run. Re-run --save on the current "
            "heads if the change under test is supposed to move this number."
        )

    bankable = same_scope and not drifted

    moved: list[str] = []
    broken: list[str] = []
    for key in _OUTCOME_KEYS:
        old, new_value = before.get(key), now[key]
        if old is None:
            moved.append(f"{key} (newly measured) -> {new_value}")
        elif new_value > old:
            if bankable:
                moved.append(f"{key} {old} -> {new_value}")
        elif new_value < old:
            # A fall is reported whatever moved: if the corpus shrank the
            # number is still worth stopping for, and the printed drift says
            # where to look. Silence here is how a lost permission would ship.
            broken.append(f"{key} {old} -> {new_value}")
    for key in _GUARD_KEYS:
        old, new_value = before.get(key), now[key]
        if old is None:
            continue
        if new_value < old:
            broken.append(f"{key} {old} -> {new_value} (guard)")

    for line in broken:
        print(f"  WORSE  {line}")
    for line in moved:
        print(f"  BETTER {line}")
    print()
    if broken:
        print(f"REGRESSED: {len(broken)} number(s) moved the wrong way. Do not merge.")
        return EXIT_REGRESSED
    if not moved:
        print("NO MOVEMENT: no ingestion outcome changed.")
        return EXIT_NO_MOVEMENT
    print(f"MOVED: {len(moved)} outcome number(s).")
    for line in moved:
        print(f"LOOP_LOG: {line}")
    return EXIT_MOVED


def _report(snapshot: dict) -> None:
    print(f"documents indexed  : {snapshot['github_documents_indexed']}")
    print(f"repositories       : {snapshot['github_repositories_indexed']} with an index")
    print(f"complete fetches   : {snapshot['github_complete_fetches']}")
    for repository, count in sorted(snapshot["documents_by_repository"].items()):
        head = snapshot["corpus_heads"].get(repository, "")
        print(f"  {repository:<28} {count:>5}  {head}")


def main(
    argv: list[str] | None = None,
    ingest: Callable[[list[str]], dict] | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    save_path: Path | None = None
    compare_path: Path | None = None
    for flag in ("--save", "--compare"):
        if flag in arguments:
            index = arguments.index(flag)
            try:
                value = arguments[index + 1]
            except IndexError:
                print(f"{flag} needs a path", file=sys.stderr)
                return EXIT_REGRESSED
            del arguments[index : index + 2]
            if flag == "--save":
                save_path = Path(value)
            else:
                compare_path = Path(value)
    if save_path and compare_path:
        print("--save and --compare are exclusive", file=sys.stderr)
        return EXIT_REGRESSED
    if arguments:
        print(f"unexpected arguments: {arguments}", file=sys.stderr)
        return EXIT_REGRESSED

    settings = Settings.from_env()
    if not settings.github_token:
        print(
            "CANNOT JUDGE: SIDRA_GITHUB_TOKEN is not set, so nothing can be "
            "fetched. This is an environment gap, not a regression - the "
            "anonymous quota cannot index five repositories.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_JUDGE

    repositories = list(settings.allowed_repositories)
    ingest = ingest or _ingest_through_the_product
    try:
        ingestion = ingest(repositories)
    except CannotJudge as exc:
        print(f"CANNOT JUDGE: {exc}", file=sys.stderr)
        return EXIT_CANNOT_JUDGE
    except Exception as exc:  # noqa: BLE001 - any transport failure lands here
        print(f"CANNOT JUDGE: ingestion could not run: {exc}", file=sys.stderr)
        print(
            "If this is a TLS failure, name the network's CA in "
            "SIDRA_CA_BUNDLE. Do not disable verification.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_JUDGE

    snapshot = _snapshot(ingestion)
    _report(snapshot)

    errors = [
        f"{repository['repository']}: {repository['error']}"
        for repository in ingestion.get("repositories", [])
        if repository.get("error")
    ]
    # Every repository failing is the shape of a broken network or a revoked
    # token, not of a product regression. Some failing is a real finding and
    # falls through to the floors below.
    if errors and len(errors) == len(repositories):
        print("CANNOT JUDGE: every repository failed to fetch:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return EXIT_CANNOT_JUDGE
    for line in errors:
        print(f"  error: {line}")

    failures = _floor_failures(snapshot)
    if failures:
        print()
        print("BELOW FLOOR: " + "; ".join(failures), file=sys.stderr)
        print(
            "The floors are pinned under a real measurement. A drop this "
            "large is a lost permission or a lost repository, not churn.",
            file=sys.stderr,
        )
        return EXIT_REGRESSED

    if save_path:
        save_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nsaved: {save_path}")
        # A save is not a verdict. 0 here means "the measurement ran and the
        # floors held", which is what a caller taking a baseline wants to know.
        return EXIT_MOVED
    if compare_path:
        if not compare_path.exists():
            print(f"no snapshot at {compare_path}", file=sys.stderr)
            return EXIT_REGRESSED
        before = json.loads(compare_path.read_text(encoding="utf-8"))
        print()
        return _compare(before, snapshot)
    return EXIT_NO_MOVEMENT


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
