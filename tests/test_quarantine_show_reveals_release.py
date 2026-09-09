"""C-1611: `sidra-quarantine show` must reveal a release's who/why/when.

`release` records the operator, reason and timestamp, but the CLI never read
them back - `show` printed only 「released : yes」. It now shows the approving
operator, the reason, and the time for a released entry, and leaks nothing for
one that is still pending.
"""

from __future__ import annotations

import contextlib
import io
from datetime import datetime, timezone

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.quarantine_show_reveals_release import (
    evaluate_quarantine_show_reveals_release,
)
from sidra_ai.security import quarantine_cli
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate
from sidra_ai.security.quarantine_review import QuarantineReview

_TOKEN = "ghp_" + "5" * 36


def _prov(repo, path, stype):
    return Provenance(
        source="github", repository=repo, path=path, commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=stype,
        trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
    )


@pytest.fixture
def released(tmp_path):
    qpath = tmp_path / "quarantine.jsonl"
    store = QuarantineStore(qpath)
    gate = SecurityGate(GatePolicy(), allowed_repositories=("tukemen-rgb/site",),
                        quarantine_store=store)
    gate.screen_document(Document(
        content=f"deploy notes: token {_TOKEN} in CI",
        provenance=_prov("tukemen-rgb/site", "docs/deploy.md", SourceType.DOCS)))
    review = QuarantineReview(qpath)
    entry = review.entries()[0]
    review.release(entry.id, operator="reviewer-a", reason="a valid eight-plus reason")
    return qpath, entry.id, review.releases()[0]


def _show(qpath, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        quarantine_cli.main(["--path", str(qpath), *args])
    return buf.getvalue()


def test_eval_passes():
    result = evaluate_quarantine_show_reveals_release()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_show_reveals_operator_reason_and_time(released):
    qpath, entry_id, release = released
    out = _show(qpath, "show", entry_id)
    assert release.operator in out
    assert release.reason in out
    assert release.released_at in out


def test_release_for_returns_the_release(released):
    qpath, entry_id, release = released
    got = QuarantineReview(qpath).release_for(entry_id)
    assert got is not None
    assert got.operator == release.operator and got.reason == release.reason


def test_release_for_none_when_not_released(tmp_path):
    qpath = tmp_path / "quarantine.jsonl"
    store = QuarantineStore(qpath)
    gate = SecurityGate(GatePolicy(), allowed_repositories=("tukemen-rgb/site",),
                        quarantine_store=store)
    gate.screen_document(Document(
        content=f"token {_TOKEN}",
        provenance=_prov("tukemen-rgb/site", "d.md", SourceType.DOCS)))
    review = QuarantineReview(qpath)
    assert review.release_for(review.entries()[0].id) is None
    assert review.release_for("nonexistent") is None
