"""A finding is not a decision, and the report has to keep saying so.

The alarm that produced this measurement was a list of findings: an
``analyze`` run printed many ``email_role`` and ``high_entropy`` hits on
``site`` and it read as "the gate is eating the corpus". It was not,
because those severities do not refuse a document - but nothing in the
tooling said that out loud, so the only way to check was to go and count.

These tests pin the two properties that make the report answer the question
rather than restate the alarm: documents whose findings never changed a
decision are reported as indexed, and refused documents are reported without
their contents. The second matters more than it looks: a false-positive
investigation that pastes the true positives into a terminal has leaked
exactly what the gate exists to hold back.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "measure_quarantine_precision_under_test",
        REPO_ROOT / "scripts" / "measure_quarantine_precision.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mqp():
    return _load()


# A role address is LOW and does not refuse a document on its own. Built by
# concatenation so the file never carries a credential-shaped literal.
ROLE_ADDRESS = "support" + "@" + "example.com"
PERSON_ADDRESS = "private.person" + "@" + "example.com"


def _repo(tmp_path: Path, name: str, documents: dict[str, str]) -> Path:
    root = tmp_path / name
    (root / "docs").mkdir(parents=True)
    for rel, text in documents.items():
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_a_low_severity_finding_leaves_the_document_indexed(mqp, tmp_path) -> None:
    root = _repo(tmp_path, "quiet", {
        "docs/contact.md": f"# 連絡先\n\n問い合わせは {ROLE_ADDRESS} まで。\n",
    })

    report = mqp.measure([("other/quiet", root)])

    assert report["refused"] == 0
    assert report["reachability_rate"] == 1.0
    assert report["findings_on_indexed_documents"] >= 1, (
        "the finding fired but changed nothing; the report must show both"
    )


def test_a_refused_document_is_listed_with_labels_and_no_content(
    mqp, tmp_path
) -> None:
    secret = "私用の連絡先は " + PERSON_ADDRESS + " です。"
    root = _repo(tmp_path, "loud", {"docs/people.md": f"# 名簿\n\n{secret}\n"})

    report = mqp.measure([("other/loud", root)])

    assert report["refused"] == 1
    row = report["refused_documents"][0]
    assert row["path"] == "docs/people.md"
    assert row["decision"] in {"quarantine", "block"}
    assert any(label.startswith("email:") for label in row["detectors"])

    # Nothing anywhere in the report may carry the detected value.
    assert PERSON_ADDRESS not in repr(report)
    assert secret not in repr(report)


def test_reachability_counts_documents_rather_than_findings(mqp, tmp_path) -> None:
    """Ten role addresses in one file are one document, not ten problems.

    Counting findings would make a chatty document look like a corpus-wide
    collapse, which is precisely how the original alarm was misread.
    """

    many = "\n".join(f"- 窓口{i}: {ROLE_ADDRESS}" for i in range(10))
    root = _repo(tmp_path, "chatty", {
        "docs/desks.md": f"# 窓口一覧\n\n{many}\n",
        "docs/plain.md": "# 方針\n\nここには何も検出されるものが無い。\n",
    })

    report = mqp.measure([("other/chatty", root)])

    assert report["documents"] == 2
    assert report["refused"] == 0
    assert report["findings_on_indexed_documents"] >= 10
