"""Does the chunker avoid a redundant trailing chunk on a hard split?

C-1693. ``_split_long`` cuts an oversized paragraph in ``max_chars`` windows that
step by ``max_chars - overlap``. When the final window starts within ``overlap``
of the end, its slice is wholly inside the previous chunk's overlap region - a
redundant chunk, in the worst case a single character (a 2161-char paragraph at
1200/120 becomes ``[1200, 1081, 1]``). That degenerate chunk is indexed, can
surface as an unreadable one-character citation, and double-counts the overlap in
BM25's statistics. The split now stops before emitting a tail already contained
in the previous chunk, losing no content and keeping the overlap contract.

The checks drive the real ``_split_long`` and ``chunk_document``: no final chunk
is contained in its predecessor, every character is still covered, the overlap
between retained chunks is intact, and a legitimate tail is not dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

_MAX = 1200
_OVERLAP = 120
_DEGENERATE = (2161, 2200, 2280, 3241)


def _para(n: int) -> str:
    """A paragraph of ``n`` distinct characters, so each chunk's offset in the
    text is unambiguous (a homogeneous string would make every slice look like
    it starts at 0, defeating the coverage check)."""

    return "".join(chr(0x100 + i) for i in range(n))


def _covers_all(pieces: list[str], text: str) -> bool:
    """Every character of ``text`` appears in some chunk, in order."""

    # Reconstruct by walking chunks: each chunk is a contiguous slice; together
    # they must span [0, len(text)) with no gap. Find each chunk's start.
    covered = [False] * len(text)
    cursor = 0
    for piece in pieces:
        idx = text.find(piece, max(0, cursor - len(piece)))
        if idx < 0:
            idx = text.find(piece)
        if idx < 0:
            return False
        for i in range(idx, idx + len(piece)):
            covered[i] = True
        cursor = idx
    return all(covered)


@dataclass(frozen=True)
class ChunkerTailResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chunker_drops_redundant_overlap_tail() -> ChunkerTailResult:
    from sidra_ai.retrieval.chunker import _split_long, chunk_document
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def split(n: int) -> list[str]:
        return _split_long(_para(n), _MAX, _OVERLAP)

    # --- (A) no final chunk is wholly contained in the previous one ---
    bad = []
    for n in _DEGENERATE:
        p = split(n)
        if len(p) >= 2 and p[-1] in p[-2]:
            bad.append(f"{n}:{[len(x) for x in p]}")
    add(not bad, f"A: a redundant contained tail chunk was emitted ({bad})")

    # --- (B) content is fully preserved (no character dropped) ---
    lost = [n for n in _DEGENERATE if not _covers_all(split(n), _para(n))]
    add(not lost, f"B: content was lost for sizes {lost}")

    # --- (C) the overlap contract holds: consecutive full chunks share the
    #         overlap (a boundary-spanning region stays retrievable) ---
    p2400 = split(2400)
    full_pairs = [
        (a, b) for a, b in zip(p2400, p2400[1:]) if len(a) == _MAX
    ]
    overlap_ok = all(a[-_OVERLAP:] == b[:_OVERLAP] for a, b in full_pairs)
    add(bool(full_pairs) and overlap_ok, "C: the inter-chunk overlap was broken")

    # --- (D) a legitimate tail (longer than the overlap) is not dropped ---
    #         2400 -> [1200, 1200, 240]: the 240 tail is real content past the
    #         previous chunk's end, so it must stay.
    add(len(p2400) == 3 and _covers_all(p2400, _para(2400)),
        f"D: a legitimate tail was over-dropped (chunks={[len(x) for x in p2400]})")

    # --- (E) a paragraph within the cap is one chunk (unchanged) ---
    add(split(1000) == [_para(1000)], "E: a short paragraph was split")

    # --- (F) chunk_document emits no degenerate contained chunk ---
    prov = Provenance(
        source="github", repository="a/b", path="r.md", commit_sha="abc1234",
        timestamp=datetime.now(timezone.utc), source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO, license="mit",
    )
    contents = [c.content for c in chunk_document(Document(content=_para(2161), provenance=prov))]
    degenerate = [
        c for i, c in enumerate(contents)
        if any(i != j and c in other for j, other in enumerate(contents))
    ]
    add(not degenerate,
        f"F: chunk_document emitted a contained chunk (lens={[len(x) for x in contents]})")

    total = 6
    return ChunkerTailResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ChunkerTailResult", "evaluate_chunker_drops_redundant_overlap_tail"]
