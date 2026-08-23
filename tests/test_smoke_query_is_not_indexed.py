"""The smoke question must not be written into a document SIDRA indexes.

``docs/`` is inside the ingestion scope, so a sentence written there is a
sentence in the corpus. On 2026-08-23 the C-413 record quoted GDP's smoke
question verbatim in ``docs/OUTCOMES.md``, and within the hour that file was
rank 1 for it - our own note about the measurement had become the best answer
to the thing being measured. The design document it was supposed to surface
dropped a place.

That is the same failure ``EXCLUDED_FROM_CORPUS`` exists for: a corpus
containing the answer key measures nothing and does it while printing a good
number. This test keeps the smoke question out of the index by checking the
documents the gate would actually admit - a document held in quarantine is
not in the corpus and cannot poison it, and if that ever changes this test
starts failing, which is exactly the warning wanted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_measure_outcomes():
    spec = importlib.util.spec_from_file_location(
        "measure_outcomes_smoke_under_test",
        REPO_ROOT / "scripts" / "measure_outcomes.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mo():
    return _load_measure_outcomes()


def test_the_smoke_question_is_not_in_any_indexed_document(mo) -> None:
    """Only this repository is checked: it is the one whose docs we write."""

    gate = mo.SecurityGate(
        mo.GatePolicy(), allowed_repositories=["tukemen-rgb/sidra-ai"]
    )

    leaked = []
    for rel_path, content in mo.iter_files(REPO_ROOT):
        if mo.DESIGN_SMOKE_QUERY not in content:
            continue
        result = gate.inspect(
            content, source="github", repository="tukemen-rgb/sidra-ai"
        )
        if result.decision is mo.Decision.ALLOW:
            leaked.append(rel_path)

    assert not leaked, (
        "the smoke question is written verbatim into a document SIDRA would "
        f"index, which makes that document its own best answer: {leaked}. "
        "Describe the question instead; scripts/measure_outcomes.py holds it."
    )


def test_the_question_still_exists_where_it_belongs(mo) -> None:
    """Keeping it out of the corpus must not mean losing it.

    The check above is satisfied trivially by deleting the question, so pin
    that it is still defined - and still the GDP wording, in Japanese, asking
    about both halves.
    """

    assert mo.DESIGN_SMOKE_QUERY.strip()
    assert "GAMEYARD" in mo.DESIGN_SMOKE_QUERY
    assert mo.DESIGN_SMOKE_QUERY.endswith("か")
