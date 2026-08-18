"""Fail-closed schema checks for the persisted GitHub ingestion cursor."""

from __future__ import annotations

import json

import pytest

from sidra_ai.ingestion.state import StateStore, StateStoreError


REPOSITORY = "tukemen-rgb/sidra-ai"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"version": 1},
        {"repositories": {}},
        {"version": 2, "repositories": {}},
        {"version": "1", "repositories": {}},
        {"version": True, "repositories": {}},
        {"version": 1, "repositories": None},
        {"version": 1, "repositories": []},
    ],
)
def test_ambiguous_persisted_schema_fails_closed_without_overwrite(
    tmp_path, payload
) -> None:
    """A damaged/future schema must never be interpreted as an empty cursor set."""

    path = tmp_path / "state.json"
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    path.write_text(serialized, encoding="utf-8")

    store = StateStore(path)
    with pytest.raises(StateStoreError, match="invalid schema"):
        store.mark_ingested(
            REPOSITORY,
            commit_sha="b" * 40,
            document_count=1,
        )

    assert path.read_text(encoding="utf-8") == serialized


def test_explicit_v1_empty_repository_map_remains_a_valid_first_run(tmp_path) -> None:
    """Only an explicit current-version empty map represents no persisted cursors."""

    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"version": 1, "repositories": {}}),
        encoding="utf-8",
    )

    state = StateStore(path).load()

    assert state.version == 1
    assert state.repositories == {}
