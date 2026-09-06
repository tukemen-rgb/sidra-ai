"""Half a bold span must not reach the reader (C-1443).

Chunking cuts a document every ~1200 characters without regard for
markup, so a bold span that straddles a cut arrives at the flattener as
half a span - and the flattener only knew how to remove PAIRS. Measured
on this repo's own docs: 95 of the 940 chunks carrying ``**`` hold an odd
number of them, and every one used to show a raw ``**``.

The other half of the claim is that a ``**`` which is *content* survives.
Losing a real character out of quoted evidence is worse than showing a
marker, which is why the flattener leaves ambiguous asterisks alone - so
"delete every ``**``" is not a fix, it is a different bug.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.documents import Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.chunker import Document, chunk_document

DECORATION = [
    ("an opener whose closer was cut off", "これは **太字 のまま終わる"),
    ("a closer whose opener was cut off", "原因である。** → 次に取る者へ"),
    ("a marker hugging punctuation", "引き継ぎ**: build_default_router()"),
    ("a checkbox stub", "- [ ] **A. やること"),
]

CONTENT = [
    ("a marker standing between spaces", "③閉じない ** の残存（3/10）"),
    ("a path ending in a glob", "src/sidra_ai/security/** is not special"),
    ("a glob with text right after it", "docs/**<br>tests/"),
    ("a glob in the middle of a path", "パスは a/**/b です"),
    ("a glob leading a path", "**/health ではなく /v1/index に出した"),
]


@pytest.mark.parametrize("why,text", DECORATION, ids=[d[0] for d in DECORATION])
def test_half_a_bold_span_is_removed(why: str, text: str) -> None:
    assert "**" not in plain_text(text), why


@pytest.mark.parametrize("why,text", CONTENT, ids=[c[0] for c in CONTENT])
def test_a_marker_that_is_content_survives(why: str, text: str) -> None:
    """Each of these is a real line from the corpus, or its shape.

    The glob cases are not decoration. A first version of the rule
    guarded only the side *before* the stars, which kept every glob that
    has a slash in front and quietly ate 「docs/**<br>」, 「a/**/b」 and
    「**/health」 - and the check passed anyway until the leading-glob
    case was named, because every other glob it knew had a slash first.
    """

    assert "**" in plain_text(text), why


def test_a_balanced_span_still_loses_its_stars() -> None:
    assert plain_text("これは **太字** です。") == "これは 太字 です。"


def _chunks_of(path):
    prov = Provenance(
        source="git",
        repository="tukemen-rgb/sidra-ai",
        path=str(path),
        commit_sha="0" * 40,
        timestamp=datetime.now(timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="unknown",
    )
    text = path.read_text(encoding="utf-8", errors="ignore")
    return chunk_document(Document(content=text, provenance=prov))


def test_the_real_corpus_splits_spans_and_none_of_them_reach_the_reader() -> None:
    """Driven over the product's own chunker, not a hand-made fragment.

    The count is asserted to be non-zero first: a corpus that happened to
    split nothing would make everything below vacuous.
    """

    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    carrying = split = kept = 0
    offending = []
    for path in sorted((root / "docs").glob("*.md")):
        for chunk in _chunks_of(path):
            if "**" not in chunk.content:
                continue
            carrying += 1
            if chunk.content.count("**") % 2:
                split += 1
            flattened = plain_text(chunk.content)
            for spot in re.finditer(r"\*\*", flattened):
                after = flattened[spot.end() : spot.end() + 1]
                before = (
                    flattened[spot.start() - 1 : spot.start()] if spot.start() else ""
                )
                touching = (after and not after.isspace()) or (
                    before and not before.isspace()
                )
                if touching and before != "/" and after != "/":
                    offending.append(f"{path.name}#{chunk.index}: {flattened[max(0, spot.start() - 30):spot.start() + 10]!r}")
                else:
                    kept += 1

    assert carrying > 0, "no chunk in the corpus carries a bold marker at all"
    assert split > 0, "no chunk splits a bold span, so this proves nothing"
    assert not offending, offending[:3]
    assert kept > 0, "every ** was removed, including the ones that are content"
