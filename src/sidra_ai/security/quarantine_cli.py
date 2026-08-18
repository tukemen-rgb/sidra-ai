"""``sidra-quarantine`` - review and release quarantined content.

    sidra-quarantine list                 what is waiting, one line each
    sidra-quarantine show <id>            findings and reasons for one entry
    sidra-quarantine show <id> --content  also print the redacted content
    sidra-quarantine release <id> --operator NAME --reason "..."
    sidra-quarantine stats                counts by decision and category

Content is never printed unless asked for, and even then only the gate's
redacted copy - the original is not reachable from here. A tool that reveals
what the gate hid, in order to help you decide whether to unhide it, is just
the leak with extra steps.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sidra_ai.config.settings import get_settings
from sidra_ai.security.quarantine_review import (
    EntryNotFoundError,
    NotReleasableError,
    QuarantineReview,
)


def default_quarantine_path() -> Path:
    return Path(get_settings().data_dir) / "quarantine.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sidra-quarantine",
        description="Review and release content the security gate quarantined",
    )
    parser.add_argument(
        "--path", default=None, help="quarantine log (default: <SIDRA_DATA_DIR>/quarantine.jsonl)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="list entries")
    listing.add_argument(
        "--all", action="store_true", help="include released and non-releasable entries"
    )

    show = sub.add_parser("show", help="show one entry")
    show.add_argument("entry")
    show.add_argument(
        "--content",
        action="store_true",
        help="also print the gate's redacted content",
    )

    release = sub.add_parser("release", help="record a human approval")
    release.add_argument("entry")
    release.add_argument("--operator", required=True, help="who is approving")
    release.add_argument("--reason", required=True, help="why, at least 8 characters")

    sub.add_parser("stats", help="counts by decision and finding category")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.path) if args.path else default_quarantine_path()
    review = QuarantineReview(path)

    if not path.exists():
        print(f"no quarantine log at {path}", file=sys.stderr)
        return 1

    if args.command == "list":
        entries = review.entries() if args.all else review.pending()
        if not entries:
            print("nothing pending review" if not args.all else "no entries")
            return 0
        released = review.released_ids()
        for entry in entries:
            mark = "released" if entry.id in released else (
                "pending" if entry.releasable else "policy"
            )
            print(f"[{mark:8s}] {entry.summary()}")
        print(f"\n{len(entries)} entries. Use `show <id>` for detail.")
        return 0

    if args.command == "show":
        try:
            entry = review.get(args.entry)
        except EntryNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"id            : {entry.id}")
        print(f"recorded_at   : {entry.recorded_at}")
        print(f"decision      : {entry.decision}"
              f"{'' if entry.releasable else '  (policy refusal - not releasable)'}")
        print(f"repository    : {entry.repository or '(withheld)'}")
        print(f"source / type : {entry.source or '(withheld)'} / {entry.source_type}")
        print(f"original size : {entry.original_length} chars")
        print(f"retention     : {entry.content_retention}")
        print(f"released      : {'yes' if entry.id in review.released_ids() else 'no'}")
        print("\nreasons:")
        for reason in entry.reasons or ("(none recorded)",):
            print(f"  - {reason}")
        print("\nfindings:")
        for finding in entry.findings or ():
            print(
                f"  [{finding.get('severity', '?'):8s}] "
                f"{finding.get('category', '?')}:{finding.get('detector', '?')}"
            )
            print(f"      {finding.get('reason', '')}")
        if args.content:
            if entry.has_content:
                print("\nredacted content:")
                print(entry.raw.get("content", ""))
            else:
                print(f"\nno content retained (retention: {entry.content_retention})")
        return 0

    if args.command == "release":
        try:
            release = review.release(
                args.entry, operator=args.operator, reason=args.reason
            )
        except (EntryNotFoundError, NotReleasableError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"released {release.entry_id} by {release.operator} at {release.released_at}")
        print(f"  reason: {release.reason}")
        print(f"  recorded in {review.release_path}")
        print("\nThis records the approval only. Re-indexing is a separate,")
        print("deliberate step on the ingestion side.")
        return 0

    if args.command == "stats":
        stats = review.stats()
        print(f"total entries : {stats['total']}")
        print(f"  releasable  : {stats['releasable']}")
        print(f"  released    : {stats['released']}")
        print(f"  pending     : {stats['pending']}")
        print("\nby decision:")
        for key, count in sorted(stats["by_decision"].items()):
            print(f"  {key:12s} {count}")
        print("\nby finding category:")
        for key, count in sorted(stats["by_finding_category"].items(), key=lambda kv: -kv[1]):
            print(f"  {key:20s} {count}")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
