"""One definition of "documentation", used by the product and the measurement.

The ingestion scope was written down twice: in ``list_docs_paths``, which
decides what SIDRA indexes, and in ``scripts/measure_outcomes.py``, which
decides what SIDRA's headline numbers are measured against. They disagreed -
the measurement walked every text file in every checkout, so 82% of the
corpus it scored was application source the product never fetches, and that
source outranked the documents carrying the answers.

These tests hold the two together, and hold the walk to a bounded shape.
"""

from __future__ import annotations

from typing import Any

import pytest

from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.github_client import GitHubReadOnlyClient
from sidra_ai.ingestion.scope import (
    DOCUMENTATION_ROOTS,
    DOCUMENTATION_SUFFIXES,
    is_documentation_path,
)

REPOSITORY = "tukemen-rgb/site"


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "readme.rst",
        "SPEC.md",
        "TODO.md",
        "CLAUDE.md",
        "docs/vision.md",
        "docs/research/case-studies.md",
        "docs/notes.txt",
    ],
)
def test_documentation_is_the_readme_root_docs_and_the_docs_tree(path: str) -> None:
    assert is_documentation_path(path)


@pytest.mark.parametrize(
    "path",
    [
        # Application source: the category that made the measured corpus 5.5x
        # the real one and pushed specifications out of the top five.
        "app/faq/page.tsx",
        "components/GamePlayer.tsx",
        "lib/game-faq.ts",
        "deploy/healthcheck.sh",
        "scripts/build.py",
        "data/articles/why-separate-origin.json",
        "package.json",
        "next.config.js",
        # A README that is not this repository's README.
        "vendor/untrusted/readme.md",
        # Documentation-shaped names outside the documentation roots.
        "app/notes.md",
        "src/sidra_ai/notes.txt",
        # Not documentation at all.
        "docs/diagram.png",
        "",
        "../secrets.md",
    ],
)
def test_everything_else_is_out_of_scope(path: str) -> None:
    assert not is_documentation_path(path)


def test_the_rule_is_case_and_separator_insensitive() -> None:
    """A checkout walked on any platform must answer as the API does."""

    assert is_documentation_path("DOCS\\Vision.MD")
    assert is_documentation_path("./docs/vision.md")
    assert not is_documentation_path("APP\\PAGE.TSX")


class _Tree:
    """A repository listing that records which directories were opened."""

    def __init__(self, contents: dict[str, list[dict[str, Any]]]) -> None:
        self.contents = contents
        self.opened: list[str] = []

    def __call__(self, repository: str, path: str, ref: str | None = None) -> Any:
        self.opened.append(path)
        return self.contents.get(path)


def _file(path: str) -> dict[str, Any]:
    return {"type": "file", "name": path.rsplit("/", 1)[-1], "path": path}


def _dir(path: str) -> dict[str, Any]:
    return {"type": "dir", "name": path.rsplit("/", 1)[-1], "path": path}


def _client(tmp_path, tree: _Tree) -> GitHubReadOnlyClient:
    settings = Settings(allowed_repositories=(REPOSITORY,), data_dir=str(tmp_path))
    client = GitHubReadOnlyClient(settings, transport=lambda *a, **k: None)
    client.get_contents = tree  # type: ignore[assignment]
    return client


def test_root_documentation_is_listed_without_descending_from_the_root(
    tmp_path,
) -> None:
    """The root gives up SPEC.md; it must not give up the whole repository.

    Listing the root is one extra request per ingestion and brings in the
    specification beside the README. Descending from it would walk ``app/``
    and ``node_modules/`` too, turning one ingestion into thousands of
    fetches - so the root is read flat and only ``docs/`` recurses.
    """

    tree = _Tree(
        {
            "": [
                _file("README.md"),
                _file("SPEC.md"),
                _file("package.json"),
                _dir("app"),
                _dir("node_modules"),
                _dir("docs"),
            ],
            "docs": [_file("docs/vision.md"), _dir("docs/research")],
            "docs/research": [_file("docs/research/case-studies.md")],
            "app": [_file("app/page.tsx"), _file("app/notes.md")],
            "node_modules": [_file("node_modules/left-pad/readme.md")],
        }
    )

    found = _client(tmp_path, tree).list_docs_paths(REPOSITORY)

    assert [entry["path"] for entry in found] == [
        "README.md",
        "SPEC.md",
        "docs/vision.md",
        "docs/research/case-studies.md",
    ]
    assert "app" not in tree.opened
    assert "node_modules" not in tree.opened
    assert tree.opened == ["", "docs", "docs/research"]


def test_the_item_limit_still_covers_root_documentation(tmp_path) -> None:
    """The bound is on the snapshot, so root files count against it too.

    Otherwise a repository could push the walk past its budget through files
    the limit never saw.
    """

    settings = Settings(
        allowed_repositories=(REPOSITORY,), data_dir=str(tmp_path), max_items_per_source=2
    )
    tree = _Tree({"": [_file(f"DOC{n}.md") for n in range(5)], "docs": []})
    client = GitHubReadOnlyClient(settings, transport=lambda *a, **k: None)
    client.get_contents = tree  # type: ignore[assignment]

    with pytest.raises(Exception, match="item limit"):
        client.list_docs_paths(REPOSITORY)


def test_every_listed_path_satisfies_the_shared_rule(tmp_path) -> None:
    """The API walk and the offline predicate must not drift apart.

    They are the two halves of the defect this module exists for: when the
    walk and the rule disagree, SIDRA's numbers describe a corpus it does
    not have.
    """

    tree = _Tree(
        {
            "": [_file("README.md"), _file("SPEC.md"), _file("yarn.lock"), _dir("docs")],
            "docs": [_file("docs/vision.md"), _file("docs/logo.svg")],
        }
    )

    found = _client(tmp_path, tree).list_docs_paths(REPOSITORY)

    assert found
    for entry in found:
        assert is_documentation_path(entry["path"]), entry["path"]


def test_the_suffix_and_root_constants_are_the_ones_the_walk_uses() -> None:
    """Pin the shared constants so a change has to be made deliberately."""

    assert DOCUMENTATION_SUFFIXES == (".md", ".markdown", ".txt", ".rst")
    assert DOCUMENTATION_ROOTS == ("docs",)
