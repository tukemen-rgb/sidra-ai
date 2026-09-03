"""Do chat answers quote evidence a reader can actually read?

C-1216: with the real corpus, 「GAMEYARDの収益はどうなっていますか」
returned as its *top* citation the 26 characters
``## D-CY4. 決済を持つか（Recipe 販売・Mentor 料金・サブスク） - [ ] **A.``
- raw Markdown decoration, cut mid-checkbox, zero actual content. The
echo lead extractor split on sentence terminators, so the heading label
(「D-CY4.」) and the checkbox stub (「A.」) each counted as a full
sentence and spent the whole excerpt budget before any content appeared.

The fix flattens the markup the way generated documents already do
(C-1212) and lets sub-sentence fragments ride along without consuming a
sentence slot. These checks run the echo model against a crafted
markdown-heavy block and a plain one; the live proof against the real
corpus ran at fix time and is recorded in the loop log.
"""

from __future__ import annotations

from dataclasses import dataclass

_MARKDOWN_BLOCK = (
    "## D-CY4. 決済を持つか（Recipe 販売・Mentor 料金・サブスク）\n"
    "- [ ] **A. 持たない**（無料のまま、収益はスポンサー枠と"
    "アフィリエイトで作る方針を維持する）\n"
    "- [ ] B. Recipe 販売だけ持つ。"
)

_PLAIN_BLOCK = (
    "First sentence long enough to count. "
    "Second sentence also long enough to count. "
    "Third must not appear in the lead."
)


@dataclass(frozen=True)
class CitationReadabilityResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _data_context() -> str:
    blocks = []
    for label, source, content in (
        ("S1", "tukemen-rgb/site@0eedf95:docs/creatoryard/CEO_REVIEW.md", _MARKDOWN_BLOCK),
        ("S2", "tukemen-rgb/site@0eedf95:docs/plain.md", _PLAIN_BLOCK),
    ):
        blocks.append(
            f"<<<SIDRA_DATA_BLOCK {label}>>>\n"
            f"source: {source}\n"
            "trust: retrieved-data\n"
            f"content:\n{content}\n"
            f"<<<END_SIDRA_DATA_BLOCK {label}>>>"
        )
    return "\n\n".join(blocks)


def evaluate_citation_readability() -> CitationReadabilityResult:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    answer = EchoModelAdapter().generate(
        GenerationRequest(
            system_prompt="",
            user_message="収益はどうなっていますか",
            data_context=_data_context(),
        )
    ).text

    checks = 0
    failures: list[str] = []

    for marker, description in (
        ("##", "heading hashes shown raw in the answer"),
        ("**", "bold stars shown raw in the answer"),
        ("- [ ]", "checkbox markers shown raw in the answer"),
    ):
        if marker not in answer:
            checks += 1
        else:
            failures.append(description)

    # The excerpt budget must reach actual content, not stop at the
    # heading label and the checkbox stub.
    if "収益はスポンサー枠" in answer:
        checks += 1
    else:
        failures.append("excerpt spent its budget on label fragments, no content shown")

    # Fragments ride along for context; dropping them would misquote the
    # source (the item id is what a reader greps for).
    if "D-CY4." in answer:
        checks += 1
    else:
        failures.append("heading label dropped from the quoted evidence")

    # Plain prose keeps the original two-sentence lead - no more, no less.
    if "Second sentence also long enough to count." in answer:
        checks += 1
    else:
        failures.append("plain lead lost its second sentence")
    if "Third must not appear" not in answer:
        checks += 1
    else:
        failures.append("plain lead overran the sentence budget")

    return CitationReadabilityResult(
        passed=not failures, checks_passed=checks, checks_total=7,
        failures=tuple(failures),
    )
