"""One local file, and it works where it is carried (§9, C-1677).

§9's competitor survey puts export and lock-in among the market's three
standing complaints, and records SIDRA's answer: the artifact is one
local HTML the player owns, with nothing fetched and nothing sent.

Five scans in the collector look for ``fetch(`` and ``://`` today and
every one of them reads a single feature's preamble - the tuning panel's,
the daily seed's, the skins', the ghost's, the difficulty adjustment's.
A fragment each, and spelling at that. Nothing has ever looked at the
finished page, and nothing has ever run it anywhere but here.

Measured before fixed: no generated page carried a ``<link>`` of any
kind, so a saved file asked the browser for ``/favicon.ico`` on every
open - a 404 in the console and a blank tab, on the artifact a player
keeps and shows people. C-1260 fixed exactly that for SIDRA's own ask
page; the fix had never reached the product's output.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import carried_probe, generate_game

REQUESTS = {
    "adventure": "迷宮を冒険するゲームを作って",
    "duel": "ビームで撃ち合うゲームを作って",
    "puzzle": "パズルゲームを作って",
    "platformer": "ジャンプで進むゲームを作って",
    "catch": "落ちものをキャッチするゲームを作って",
}

NETWORK = (
    "fetch(", "XMLHttpRequest", "WebSocket", "EventSource",
    "sendBeacon", "navigator.geolocation", "import(",
)

ICON = re.compile(r"""<link[^>]*rel=["']icon["'][^>]*>""", re.I)


@pytest.fixture(scope="module")
def pages() -> dict[str, str]:
    return {key: generate_game(req).html for key, req in REQUESTS.items()}


def _drive(html: str, storage: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to carry the page somewhere else")
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=carried_probe(found.group(1), storage=storage),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_no_page_names_anything_outside_itself(pages: dict[str, str]) -> None:
    """Held with no exemption. The icon's SVG needs an ``xmlns``, whose
    name contains ``://`` while addressing nothing - encoding it as base64
    is what lets this contract be absolute instead of arguable."""

    for key, html in pages.items():
        assert "://" not in html, key
        far = [
            ref
            for ref in re.findall(r"""(?:src|href)\s*=\s*["']([^"']*)""", html)
            if not ref.startswith("data:")
        ]
        assert far == [], f"{key}: {far}"


def test_no_page_carries_a_way_to_reach_out(pages: dict[str, str]) -> None:
    for key, html in pages.items():
        for name in NETWORK:
            assert name not in html, f"{key}: {name}"


def test_every_page_declares_its_own_icon(pages: dict[str, str]) -> None:
    """The defect itself: without this the browser asks for
    /favicon.ico every time the saved file is opened."""

    for key, html in pages.items():
        tag = ICON.search(html)
        assert tag is not None, f"{key}: no icon declared"
        assert 'href="data:' in tag.group(0), f"{key}: {tag.group(0)[:60]}"


def test_the_icon_is_a_real_drawing_in_the_pages_own_colours(
    pages: dict[str, str],
) -> None:
    """An icon that decoded to nothing would satisfy the tag check and
    still leave the tab blank."""

    for key, html in pages.items():
        tag = ICON.search(html)
        assert tag is not None
        packed = tag.group(0).split("base64,")[1].rstrip('">')
        svg = base64.b64decode(packed).decode("utf-8")
        assert svg.startswith("<svg") and svg.endswith("</svg>"), key
        assert "xmlns=" in svg, f"{key}: a standalone SVG needs its namespace"
        assert svg.count("<rect") >= 2, key
        accent = re.search(r"a\{color:(#[0-9a-fA-F]{3,8})\}", html)
        assert accent is not None, f"{key}: the page has no accent to match"
        assert accent.group(1) in svg, f"{key}: the icon is not the page's colour"


def test_every_page_runs_with_the_network_taken_away(pages: dict[str, str]) -> None:
    for key, html in pages.items():
        seen = _drive(html, "keeps")
        assert seen["reached"] == [], f"{key}: reached for {seen['reached']}"
        assert seen["boom"] is None, f"{key}: {seen['boom']}"
        assert seen["frames"] == 600, f"{key}: {seen['frames']} frames"


def test_every_page_runs_where_nothing_can_be_stored(pages: dict[str, str]) -> None:
    """A private window, a blocked-cookies profile, a file opened straight
    from disk: ``localStorage`` exists and throws on every access. A page
    that only guards with ``typeof localStorage !== 'undefined'`` passes
    that guard and dies here."""

    for key, html in pages.items():
        seen = _drive(html, "refuses")
        assert seen["boom"] is None, f"{key}: {seen['boom']}"
        assert seen["frames"] == 600, f"{key}: {seen['frames']} frames"


def test_the_refusing_machine_really_refuses() -> None:
    """The probe's own contract. If the denial stopped throwing, the run
    above would pass for a page that never guards anything at all."""

    from sidra_ai.creation.games import carried_probe as build

    probe = build("try{localStorage.getItem('x')}catch(e){globalThis.CAUGHT=e.name}",
                  storage="refuses", frames=1)
    got = subprocess.run(
        ["node", "-"], input=probe + "\nconsole.log(globalThis.CAUGHT)",
        capture_output=True, text=True, timeout=60,
    )
    assert got.returncode == 0, got.stderr[:300]
    assert got.stdout.strip().splitlines()[-1] == "SecurityError", got.stdout[-200:]
