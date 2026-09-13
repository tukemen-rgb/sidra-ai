"""C-1745: a game that is on disk must not be reported as absent.

The reviser picks its target from sidecars it can read, and both listings
behind the refusal skip a sidecar they cannot. Skipping is right for
choosing - a record we cannot read is a game we cannot rebuild - and wrong
for *saying what exists*: with every sidecar skipped the reply became
「修正できる生成済みゲームが見つかりません。先に「◯◯ゲームを作って」で
作成してください」 while the page sat in the same directory, openable and
playable. An operator who follows that advice ends up with a second copy
of a game they already had.

Both directions throughout. A reviser that always answered "the record
cannot be read" would pass every stranded case here and lie to everyone
whose directory is genuinely empty, so each of those is checked too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidra_ai.creation.revise import (
    build_game_reviser,
    detect_revision_intent,
    find_target_meta,
    save_meta,
    stranded_pages,
)

MESSAGE = "難しくして"
MAKE_ONE_FIRST = "先に「◯◯ゲームを作って」で作成してください"


def _page(root: Path, stem: str) -> Path:
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    page = root / "artifacts" / f"{stem}.html"
    page.write_text("<!doctype html><title>ある</title>", encoding="utf-8")
    return page


def _sidecar(page: Path, text: str) -> Path:
    path = page.with_name(page.stem + ".meta.json")
    path.write_text(text, encoding="utf-8")
    return path


def _answer(root: Path) -> str:
    return build_game_reviser(root)(MESSAGE, detect_revision_intent(MESSAGE)).summary


@pytest.mark.parametrize(
    "name,write",
    [
        (
            "unknown template",
            lambda page: save_meta(
                page,
                request="ゲームを作って",
                template="tetris",
                difficulty="normal",
                theme="dusk",
                title="ある",
            ),
        ),
        (
            "no template key",
            lambda page: _sidecar(
                page, json.dumps({"request": "ゲームを作って", "difficulty": "normal"})
            ),
        ),
        ("not json at all", lambda page: _sidecar(page, "{ぶつ切り")),
        ("a list, not an object", lambda page: _sidecar(page, '["ゲーム"]')),
    ],
)
def test_a_page_that_is_here_is_named_rather_than_denied(
    tmp_path: Path, name: str, write
) -> None:
    page = _page(tmp_path, "game-fishing-20260913T000000Z")
    write(page)

    said = _answer(tmp_path)

    assert page.name in said, f"{name}: the file is on disk and was not named"
    assert MAKE_ONE_FIRST not in said, (
        f"{name}: told to create a game that is already there - following that "
        "advice leaves two copies of one game"
    )


def test_an_empty_directory_still_sends_someone_to_the_generator(tmp_path: Path) -> None:
    """The other direction. Without it, "the record cannot be read" said to
    everyone would score full marks above."""

    (tmp_path / "artifacts").mkdir()

    said = _answer(tmp_path)

    assert MAKE_ONE_FIRST in said
    assert ".html" not in said, "named a file in a directory that holds none"


def test_no_artifacts_directory_at_all_says_the_same(tmp_path: Path) -> None:
    said = _answer(tmp_path)

    assert MAKE_ONE_FIRST in said
    assert ".html" not in said


def test_a_record_with_no_page_beside_it_is_not_named(tmp_path: Path) -> None:
    """Naming it would send an operator after a file that is not on disk."""

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "game-fishing-20260913T000000Z.meta.json").write_text(
        "{ぶつ切り", encoding="utf-8"
    )

    said = _answer(tmp_path)

    assert MAKE_ONE_FIRST in said
    assert ".meta.json" not in said
    assert stranded_pages(tmp_path) == []


def test_the_page_is_named_not_the_record(tmp_path: Path) -> None:
    """The page is what the operator can open. The sidecar is ours."""

    page = _page(tmp_path, "game-fishing-20260913T000000Z")
    _sidecar(page, "{ぶつ切り")

    stranded = stranded_pages(tmp_path)

    assert [path for path, _ in stranded] == [page]
    assert stranded[0][1]


def test_more_than_one_stranded_page_says_how_many(tmp_path: Path) -> None:
    """The subset honesty C-1727 established for the listing: a reply that
    names one of three and stops reads as "there is one"."""

    for stem in (
        "game-fishing-20260913T000000Z",
        "game-racing-20260913T000001Z",
        "game-puzzle-20260913T000002Z",
    ):
        _sidecar(_page(tmp_path, stem), "{ぶつ切り")

    said = _answer(tmp_path)

    assert "ほか 2 件" in said


def test_an_unknown_template_word_is_quoted_short(tmp_path: Path) -> None:
    """It comes from a file on this machine, and a refusal is not the place
    to print an arbitrary amount of it."""

    page = _page(tmp_path, "game-fishing-20260913T000000Z")
    _sidecar(
        page,
        json.dumps(
            {
                "request": "ゲームを作って",
                "template": "x" * 400,
                "difficulty": "normal",
            }
        ),
    )

    said = _answer(tmp_path)

    assert "x" * 24 in said
    assert "x" * 30 not in said


def test_a_readable_record_is_still_found(tmp_path: Path) -> None:
    """The new branch must not swallow the path that works."""

    page = _page(tmp_path, "game-fishing-20260913T000001Z")
    save_meta(
        page,
        request="釣りゲームを作って",
        template="fishing",
        difficulty="normal",
        theme="dusk",
        title="釣り",
    )

    found = find_target_meta(tmp_path, MESSAGE)

    assert found is not None
    assert found[0].name == page.stem + ".meta.json"
    assert stranded_pages(tmp_path) == []
