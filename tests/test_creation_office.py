"""A format conversion is where a document quietly starts editing itself.

Two failures are guarded here. The first is the loud one: a writer that
reports success for a file it did not produce, or produced truncated. The
checker opens the package and reads its parts, because a zero-byte .docx and
a real one are the same line in a directory listing.

The second is the quiet one. The deck's blanks exist because a number was not
in the corpus, and a conversion is exactly the moment someone would "tidy"
them away. They have to survive into every format unchanged.
"""

from __future__ import annotations

import html
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.decks import BLANK, generate_deck  # noqa: E402
from sidra_ai.creation.office import (  # noqa: E402
    REQUIRED_PARTS,
    requested_formats,
    validate_office,
    write_docx,
    write_office,
    write_xlsx,
)


@pytest.fixture
def deck():
    return generate_deck("売上のデッキを作って", facts=[])


# ------------------------------------------------------- reading the ask


@pytest.mark.parametrize(
    "request_text,expected",
    [
        ("Word で資料を作って", ("docx",)),
        ("エクセルで出して", ("xlsx",)),
        ("パワポで作って", ("pptx",)),
        ("エクセルとパワポで", ("xlsx", "pptx")),
        ("デッキを作って", ()),
    ],
)
def test_the_named_formats_are_the_ones_detected(request_text, expected) -> None:
    assert requested_formats(request_text) == expected


def test_an_unnamed_format_is_not_guessed() -> None:
    """Silence is not a request for three files."""

    assert requested_formats("資料を作って") == ()


# ------------------------------------------------------------- it writes


@pytest.mark.parametrize("fmt", sorted(REQUIRED_PARTS))
def test_each_format_writes_a_package_that_opens(deck, tmp_path, fmt) -> None:
    results = write_office(deck, tmp_path, "deck")

    if not results[fmt]["written"]:
        pytest.skip(f"{fmt} writer unavailable: {results[fmt]['reason']}")
    assert results[fmt]["valid"], validate_office(results[fmt]["path"], fmt)


@pytest.mark.parametrize("fmt", sorted(REQUIRED_PARTS))
def test_every_required_part_is_present(deck, tmp_path, fmt) -> None:
    results = write_office(deck, tmp_path, "deck")
    if not results[fmt]["written"]:
        pytest.skip(f"{fmt} writer unavailable: {results[fmt]['reason']}")

    with zipfile.ZipFile(results[fmt]["path"]) as package:
        names = set(package.namelist())

    for part in REQUIRED_PARTS[fmt]:
        assert part in names


def test_each_format_is_reported_separately(deck, tmp_path) -> None:
    """Two installed and one missing is the likeliest real configuration."""

    results = write_office(deck, tmp_path, "deck")

    assert set(results) == {"docx", "xlsx", "pptx"}
    for fmt, result in results.items():
        assert set(result) == {"written", "reason", "path", "valid"}
        assert result["reason"], fmt


# ---------------------------------------------------------- the checker


def test_a_truncated_file_does_not_pass(tmp_path) -> None:
    """A zero-byte .docx and a real one look identical in a listing."""

    broken = tmp_path / "deck.docx"
    broken.write_bytes(b"")

    assert not validate_office(broken, "docx")["valid"]


def test_a_package_missing_its_defining_part_does_not_pass(tmp_path) -> None:
    partial = tmp_path / "deck.xlsx"
    with zipfile.ZipFile(partial, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")

    result = validate_office(partial, "xlsx")

    assert not result["valid"]
    assert any("xl/workbook.xml" in failure for failure in result["failures"])


def test_malformed_xml_inside_the_package_does_not_pass(tmp_path) -> None:
    bad = tmp_path / "deck.docx"
    with zipfile.ZipFile(bad, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<w:document><unclosed>")

    assert not validate_office(bad, "docx")["valid"]


def test_a_file_that_was_never_written_does_not_pass(tmp_path) -> None:
    assert not validate_office(tmp_path / "absent.docx", "docx")["valid"]


# ------------------------------------------------------- the blanks live


def test_the_blanks_survive_into_word(deck, tmp_path) -> None:
    """A conversion is not an occasion to fill a number nobody retrieved."""

    written, why = write_docx(deck, tmp_path / "deck.docx")
    if not written:
        pytest.skip(why)

    with zipfile.ZipFile(tmp_path / "deck.docx") as package:
        body = package.read("word/document.xml").decode("utf-8")

    assert BLANK in body


def test_the_blanks_survive_into_excel(deck, tmp_path) -> None:
    written, why = write_xlsx(deck, tmp_path / "deck.xlsx")
    if not written:
        pytest.skip(why)

    # Unescaped first: openpyxl writes CJK as numeric character references,
    # so a raw substring search would fail on a file that says exactly the
    # right thing.
    with zipfile.ZipFile(tmp_path / "deck.xlsx") as package:
        text = html.unescape(
            "".join(
                package.read(name).decode("utf-8")
                for name in package.namelist()
                if name.endswith(".xml")
            )
        )

    assert BLANK in text


def test_the_title_reaches_every_format(deck, tmp_path) -> None:
    results = write_office(deck, tmp_path, "deck")

    for fmt, result in results.items():
        if not result["written"]:
            continue
        with zipfile.ZipFile(result["path"]) as package:
            text = html.unescape(
                "".join(
                    package.read(name).decode("utf-8", "ignore")
                    for name in package.namelist()
                    if name.endswith(".xml")
                )
            )
        assert deck.title in text, fmt


# --------------------------------------------------- absence is reported


def test_a_missing_package_is_reported_not_raised(deck, tmp_path, monkeypatch) -> None:
    """An operator without the extra gets a reason, never a traceback."""

    monkeypatch.setitem(sys.modules, "docx", None)

    written, why = write_docx(deck, tmp_path / "deck.docx")

    assert not written
    assert "python-docx" in why


def test_the_extra_is_declared_in_pyproject() -> None:
    """These are optional by design; a hard dependency would be the bug."""

    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    creation = text.split("creation = ", 1)[1].split("\n", 1)[0]
    for package in ("python-docx", "openpyxl", "python-pptx"):
        assert package in creation
    dependencies = text.split("dependencies = ", 1)[1].split("]", 1)[0]
    for package in ("python-docx", "openpyxl", "python-pptx"):
        assert package not in dependencies
