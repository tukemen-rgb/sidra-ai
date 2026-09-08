"""A document nobody can retrieve is a document that is not in the product.

The operator asks in Japanese. Six of this repository's documents were written
entirely in English - and they were the most-referenced ones: SECURITY,
LOCAL_RUNTIME, ARCHITECTURE, README, INTEGRATION_V01, COLLABORATION. Neither
half of retrieval could reach them from a Japanese question, and the reason is
not something a better model fixes.

**Measured (C-1152).** Same document, same embedding model, one variable - the
language the question was asked in:

* asked in English, ``docs/SECURITY.md`` is rank **24** of 3,286 chunks;
* asked in Japanese, the same document is rank **2,676**.

Crossing languages costs 0.112 of cosine similarity. The entire corpus spans
0.116 from its best match to its worst. So the penalty for asking in the wrong
language is very nearly the whole range the score has to work with, and the
right document lands below the median regardless of what it says. Two controls
rule out the obvious alternative explanations: shortening the English passage
to a single on-point sentence does not help (rank 3,095 against 3,083), and the
same content written in Japanese ranks **1**. It is the language, not the
chunk, and not the model's grasp of the content.

The fix is that these documents carry a Japanese ``## 概要（日本語）`` summary
of their own sections. This test is what keeps the fix from decaying: a new
English-only document under ``docs/`` is invisible to the person the product is
for, and it should fail here rather than be discovered by them.

**The floor is a proxy, and here is what it is a proxy for.** What actually
makes retrieval work is BM25 finding Japanese terms in the document, which no
character count proves. What the count does rule out is the failure that
happened: a document with a stray Japanese word and nothing to match. The
measured distribution has no middle to argue about - the six failing documents
carried 0 to 42 Japanese letters and every other document carried 1,044 or
more, so 300 sits in an empty gap seven times wider than the largest failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import measure_outcomes  # noqa: E402

#: Below this a document has, at most, a stray word rather than a passage.
#: See the module docstring for the measured gap this sits inside.
MINIMUM_JAPANESE_LETTERS = 300

#: The heading the summaries carry, so a reviewer can find them and so the
#: failure message can name the remedy rather than only the symptom.
SUMMARY_HEADING = "## 概要（日本語）"


def japanese_letters(text: str) -> int:
    """Kana and CJK ideographs. Not a language detector - a presence check."""

    return sum(
        1
        for character in text
        for code in (ord(character),)
        if 0x3040 <= code <= 0x30FF or 0x4E00 <= code <= 0x9FFF
    )


def unreachable_documents(root: Path) -> tuple[list[str], int]:
    """The check itself, over whatever the corpus walker reads under ``root``.

    Factored out so the guard can be pointed at a fixture repository and shown
    to fail on the shape it exists for. A guard only ever exercised against a
    repository that already passes is a guard nobody has seen work.
    """

    thin: list[str] = []
    total = 0
    for path, content in measure_outcomes.iter_files(root):
        total += 1
        count = japanese_letters(content)
        if count < MINIMUM_JAPANESE_LETTERS:
            thin.append(f"{path} ({count} Japanese letters)")
    return thin, total


def test_every_ingested_document_carries_japanese() -> None:
    """Read through the corpus walker, so this measures what retrieval sees."""

    thin, total = unreachable_documents(ROOT)

    assert total > 0, "the corpus walker read nothing - the fixture is wrong"
    assert not thin, (
        "these documents cannot be retrieved from a Japanese question, which "
        "is the only kind this product is asked:\n  "
        + "\n  ".join(thin)
        + f"\n\nAdd a '{SUMMARY_HEADING}' section summarising the document's "
        "own sections. It is a summary, not a translation - the English body "
        "stays normative."
    )


def test_the_six_repaired_documents_carry_a_summary_section() -> None:
    """The count above can be satisfied by accident; the section cannot.

    These six are named rather than discovered because they are the ones the
    measurement was taken on. If one loses its summary, the number in this
    module's docstring stops describing the repository.
    """

    for relative in (
        "README.md",
        "docs/SECURITY.md",
        "docs/LOCAL_RUNTIME.md",
        "docs/ARCHITECTURE.md",
        "docs/INTEGRATION_V01.md",
        "docs/COLLABORATION.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert SUMMARY_HEADING in text, f"{relative} lost its Japanese summary"


_JAPANESE_BODY = (
    "# 脅威モデル\n\n"
    "SIDRA は第三者が書き込めるリポジトリを読む。課題の本文は攻撃者が書ける"
    "文章として扱う。想定する脅威はプロンプト注入と秘密の伝播である。\n" * 6
)
_ENGLISH_BODY = (
    "# Threat model\n\n"
    "SIDRA AI reads repositories that third parties can write to. An issue "
    "body is attacker-controllable text.\n" * 40
)


def _fixture_repository(root: Path, *documents: tuple[str, str]) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(_JAPANESE_BODY, encoding="utf-8")
    for name, content in documents:
        (root / "docs" / name).write_text(content, encoding="utf-8")


def test_the_guard_passes_a_repository_written_in_japanese(tmp_path) -> None:
    """The other half of the break: it must not fail on everything."""

    _fixture_repository(tmp_path, ("plan.md", _JAPANESE_BODY))

    thin, total = unreachable_documents(tmp_path)

    assert total == 2, f"the fixture was not read as expected: {total} files"
    assert not thin


def test_the_guard_rejects_an_english_only_document(tmp_path) -> None:
    """Break it on purpose: the guard must fail on the shape it exists for.

    Run against a fixture rather than the repository, so proving the guard
    bites does not require committing a document that breaks it.
    """

    _fixture_repository(tmp_path, ("threat.md", _ENGLISH_BODY))

    thin, total = unreachable_documents(tmp_path)

    assert total == 2
    assert len(thin) == 1 and "threat.md" in thin[0], thin


def test_a_stray_japanese_word_is_not_enough(tmp_path) -> None:
    """The exact shape that fooled a reader before this was measured.

    ``docs/ARCHITECTURE.md`` carried 9 Japanese letters and was unreachable
    all the same, so a floor of "at least one" would have passed the document
    this guard was written for.
    """

    _fixture_repository(tmp_path, ("architecture.md", _ENGLISH_BODY + "検索\n"))

    thin, _ = unreachable_documents(tmp_path)

    assert len(thin) == 1 and "architecture.md" in thin[0], thin
