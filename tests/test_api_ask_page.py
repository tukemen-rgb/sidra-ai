"""``GET /``: asking a question from a browser, with nothing installed.

The page is the smallest surface that could be called a UI, and each of the
tests below pins a way it could stop being usable or stop being safe without
anyone noticing:

* an asset moved to a CDN - the page still renders, and the button does
  nothing on the loopback-only machine it was written for;
* the auth boundary moving off the API along with the page (the shell is
  open by the owner's decision; what it talks to is not);
* CORS appearing, because a browser complained once;
* a retrieved document reaching the operator's browser as markup rather than
  as text.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.state import StateStore


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


@pytest.fixture
def api(service: SidraService, settings: Settings) -> TestClient:
    return TestClient(create_app(service, settings))


def test_the_page_is_served_as_html(api: TestClient) -> None:
    response = api.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_the_page_posts_to_the_existing_chat_endpoint(api: TestClient) -> None:
    """No new endpoint. What the page shows crossed the same guards."""

    body = api.get("/").text

    assert "/v1/chat" in body
    assert "<textarea" in body or "<input" in body


def test_the_page_fetches_nothing_off_this_host() -> None:
    """The reason this UI is hand-written rather than generated.

    A CDN script tag on a loopback-bound, CORS-free service produces a page
    that loads and a button that does nothing. Absolute ``src``/``href``
    targets are what that looks like in the markup, so they are refused
    here rather than discovered on an air-gapped machine.
    """

    external = [
        match.group(1)
        for match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", ASK_PAGE)
        if match.group(1).strip().lower().startswith(("http://", "https://", "//"))
    ]

    assert external == []


def test_the_shell_loads_without_a_token_but_the_api_still_needs_one(
    service: SidraService, settings: Settings, monkeypatch
) -> None:
    """The page is a constant shell; the auth boundary is on the API.

    Owner's decision 2026-09-20 ("7B"): with a token configured, a phone on
    the LAN could not open the page at all - navigation carries no
    ``Authorization`` header, so it got a 401 body and no form. The shell is
    now served like ``/health``. What must not move with it is the boundary
    itself: the routes the page talks to keep requiring the bearer token, and
    the page carries nothing worth protecting.
    """

    monkeypatch.setenv("SIDRA_API_TOKEN", "configured-token")
    api = TestClient(create_app(service, settings))

    page = api.get("/")
    assert page.status_code == 200
    assert "<form" in page.text
    # Nothing configuration- or index-shaped rides along with the shell.
    assert "configured-token" not in page.text
    assert page.text == ASK_PAGE

    # The API behind the page still needs the token.
    assert api.post("/v1/chat", json={"message": "x"}).status_code == 401
    assert api.get("/v1/index").status_code == 401
    assert api.get("/openapi.json").status_code == 401
    assert (
        api.get("/v1/index", headers={"Authorization": "Bearer configured-token"}).status_code
        == 200
    )


def test_serving_the_page_did_not_enable_cors(api: TestClient) -> None:
    """A browser on another origin still cannot reach this service.

    The page is same-origin with the API it posts to, so it needs no CORS,
    and adding any would hand every page the operator has open a way in.
    """

    response = api.get("/", headers={"Origin": "https://example.invalid"})

    assert "access-control-allow-origin" not in {
        name.lower() for name in response.headers
    }


def test_retrieved_content_is_inserted_as_text_not_markup() -> None:
    """Retrieved documents are DATA. That has to hold in the browser too.

    ``innerHTML`` on an answer or a citation would let a document this
    service indexed decide what runs in the operator's page. The page uses
    text nodes, and this test is what keeps a later edit from reaching for
    the shorter spelling.
    """

    assert "innerHTML" not in ASK_PAGE
    assert "outerHTML" not in ASK_PAGE
    assert "insertAdjacentHTML" not in ASK_PAGE
    assert "document.write" not in ASK_PAGE
    assert "textContent" in ASK_PAGE


def test_the_token_field_is_not_persisted_by_the_page() -> None:
    """The token goes into one header and nowhere that outlives the tab."""

    assert "localStorage" not in ASK_PAGE
    assert "sessionStorage" not in ASK_PAGE
    assert "document.cookie" not in ASK_PAGE
