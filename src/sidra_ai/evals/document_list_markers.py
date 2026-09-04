"""Does a generated document read as prose, not a mid-list fragment?

C-1222: 「収益方針をまとめた文書を作って」 produced a report whose 概要
opened 「2. ブランドを分けるか。 … 3. … 4. …」 - the excerpt window had
landed inside an ordered list in the source, and ``plain_text`` stripped
bullets (``- ``/``* ``) but not ordered-list numbers, so a document's very
first line began with a 2 and no 1. The list marker strip now covers
ordered markers too, while an inline decimal (「3.5 倍」) and a four-digit
year (「2024.」) are left alone.

The checks build a document through the public ``generate_document`` from a
fact whose text is a real ordered-list fragment, and confirm the numbers
are gone from the prose while the words and an inline decimal survive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidra_ai.creation.evidence import Fact, plain_text

_SRC = "tukemen-rgb/site docs/vision.md"

#: An ordered-list fragment as it arrives from an excerpt window that started
#: at item 2. ``plain_text`` runs on excerpts, so the fact text is already
#: flattened by the time the document generator sees it - mirror that here.
_FRAGMENT = plain_text(
    "2. ブランドを分けるか。\n"
    "分けるなら早いほうが安い（§6）\n"
    "3. 行動計測を入れるか。\n"
    "4. 決済を持つか。速度は 3.5 倍に伸びた。"
)


@dataclass(frozen=True)
class DocumentListMarkersResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_document_list_markers() -> DocumentListMarkersResult:
    from sidra_ai.creation.documents import generate_document

    doc = generate_document(
        "収益方針をまとめた文書を作って", facts=[Fact(text=_FRAGMENT, source=_SRC)]
    )
    md = doc.markdown
    overview = md.split("## 概要", 1)[1].split("##", 1)[0].strip()
    # C-1232 moved the fact's prose out of 概要 (which no longer copies the
    # first fact) and into 「わかっていること」, so the surviving-words check
    # reads it there now. The load-bearing check below is whole-document.
    known = md.split("## わかっていること", 1)[1].split("\n## ", 1)[0]

    checks = 0
    failures: list[str] = []

    if not re.match(r"^\d+[.)]", overview):
        checks += 1
    else:
        failures.append("the overview still opens with an ordered-list number")

    # No line in the body begins with an ordered-list marker.
    if not re.search(r"(?m)^\d+[.)][ \t]", md):
        checks += 1
    else:
        failures.append("a line still starts with an ordered-list marker")

    # The words survive - only the marker is removed.
    if "ブランドを分けるか" in known and "行動計測を入れるか" in known:
        checks += 1
    else:
        failures.append("stripping the markers took the list's words with it")

    # An inline decimal is content, not a marker.
    if "3.5" in md:
        checks += 1
    else:
        failures.append("an inline decimal was mangled")

    # plain_text keeps a four-digit year at a line start (only 1-3 digit
    # markers are list numbers).
    if plain_text("2024. 振り返り") == "2024. 振り返り":
        checks += 1
    else:
        failures.append("a four-digit year at a line start was stripped as a marker")

    return DocumentListMarkersResult(
        passed=not failures, checks_passed=checks, checks_total=5,
        failures=tuple(failures),
    )
