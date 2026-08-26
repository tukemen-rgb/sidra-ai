"""Getting a generated file back without opening a hole to get it.

Three failures this file exists to prevent:

* the artifacts route becoming a file server for the whole disk - it joins a
  caller-supplied name to a path, which is where traversal lives;
* a listing that carries content - a generated deck is grounded in retrieved
  documents, so an excerpt in a listing is indexed DATA in a place that reads
  as metadata;
* an artifact rendered as a page in this origin, beside the field the
  operator types their token into.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.app import create_app  # noqa: E402
from sidra_ai.api.artifacts import (  # noqa: E402
    ArtifactNotFound,
    list_artifacts,
    read_artifact,
)
from sidra_ai.api.ui import ASK_PAGE  # noqa: E402


@pytest.fixture
def store(tmp_path):
    directory = tmp_path / "artifacts"
    directory.mkdir()
    (directory / "game-fishing-20260826T000000Z.html").write_text("<html>x</html>")
    return tmp_path


# --------------------------------------------------------------- listing


def test_a_missing_directory_lists_nothing_rather_than_failing(tmp_path) -> None:
    """Before the first creation there is no directory. That is not an error."""

    assert list_artifacts(tmp_path) == []


def test_the_listing_carries_name_size_and_time_only(store) -> None:
    entry = list_artifacts(store)[0].to_dict()

    assert set(entry) == {"name", "bytes", "modified"}
    assert "<html>" not in str(entry)


def test_a_symlink_is_not_listed(store, tmp_path) -> None:
    """The one way a listing could name a file outside the directory."""

    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    (store / "artifacts" / "link.html").symlink_to(outside)

    assert [a.name for a in list_artifacts(store)] == [
        "game-fishing-20260826T000000Z.html"
    ]


# ------------------------------------------------------------- traversal


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "..", "", "a/../b", "/etc/passwd", ".hidden", "x" * 200],
)
def test_names_that_are_not_artifacts_are_refused(store, name) -> None:
    with pytest.raises(ArtifactNotFound):
        read_artifact(store, name)


def test_a_symlink_with_an_ordinary_name_is_still_refused(store, tmp_path) -> None:
    """What the name pattern alone cannot catch."""

    outside = tmp_path / "secret.txt"
    outside.write_text("private")
    (store / "artifacts" / "ordinary.html").symlink_to(outside)

    with pytest.raises(ArtifactNotFound):
        read_artifact(store, "ordinary.html")


def test_a_real_artifact_reads_back(store) -> None:
    payload, name = read_artifact(store, "game-fishing-20260826T000000Z.html")

    assert payload == b"<html>x</html>"
    assert name == "game-fishing-20260826T000000Z.html"


# ------------------------------------------------------------------ HTTP


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SIDRA_DATA_DIR", str(tmp_path))
    from sidra_ai.api import service as service_module

    service_module.set_service(None)
    with TestClient(create_app()) as test_client:
        yield test_client
    service_module.set_service(None)


def test_making_something_then_listing_and_downloading_it(client) -> None:
    """The whole point of the page, end to end through the real app."""

    made = client.post("/v1/chat", json={"message": "釣りゲームを作って"})
    assert made.status_code == 200
    assert made.json()["creation"]["outcome"]["handled"]

    listing = client.get("/v1/artifacts")
    assert listing.status_code == 200
    names = [a["name"] for a in listing.json()["artifacts"]]
    assert names

    got = client.get(f"/v1/artifacts/{names[0]}")
    assert got.status_code == 200
    assert got.content


def test_an_artifact_leaves_as_a_download_not_a_page(client) -> None:
    """Rendered inline it would run in the origin holding the token."""

    client.post("/v1/chat", json={"message": "釣りゲームを作って"})
    name = client.get("/v1/artifacts").json()["artifacts"][0]["name"]

    got = client.get(f"/v1/artifacts/{name}")

    assert "attachment" in got.headers["content-disposition"]
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "text/html" not in got.headers["content-type"]


def test_a_missing_artifact_and_a_refused_name_look_identical(client) -> None:
    """Otherwise the difference maps the directory."""

    missing = client.get("/v1/artifacts/game-nothing-20260101T000000Z.html")
    refused = client.get("/v1/artifacts/..")

    assert missing.status_code == refused.status_code == 404


# -------------------------------------------------------------- the page


def test_the_page_says_you_can_just_ask_for_a_thing() -> None:
    assert "作って" in ASK_PAGE


def test_the_page_lists_and_downloads_through_the_authenticated_route() -> None:
    assert "/v1/artifacts" in ASK_PAGE
    assert "Authorization" in ASK_PAGE


def test_the_page_never_opens_an_artifact_in_this_origin() -> None:
    """A blob download; never an iframe or a same-origin tab."""

    assert "<iframe" not in ASK_PAGE
    assert "createObjectURL" in ASK_PAGE


def test_the_page_still_fetches_nothing_off_host() -> None:
    assert "http://" not in ASK_PAGE
    assert "https://" not in ASK_PAGE
