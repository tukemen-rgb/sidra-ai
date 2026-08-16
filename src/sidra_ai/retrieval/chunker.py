"""Split documents into retrievable chunks without losing provenance.

Chunking is boundary-aware: markdown headings first, then paragraphs, then a
hard character split as a last resort. Every chunk inherits the parent
document's :class:`~sidra_ai.documents.Provenance` unchanged, so a citation
still points at a real commit and path.
"""

from __future__ import annotations

import re

from sidra_ai.documents import Chunk, Document

_HEADING = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 120


def _split_on_headings(text: str) -> list[str]:
    positions = [m.start() for m in _HEADING.finditer(text)]
    if not positions:
        return [text]
    if positions[0] != 0:
        positions.insert(0, 0)
    sections = []
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)
    return sections or [text]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}" if current else paragraph
            continue
        if current:
            pieces.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        # A single oversized paragraph: hard split with overlap so a sentence
        # spanning the boundary is still retrievable from one side.
        step = max_chars - overlap
        for start in range(0, len(paragraph), step):
            pieces.append(paragraph[start : start + max_chars])
        current = ""
    if current:
        pieces.append(current)
    return pieces or [text[:max_chars]]


def chunk_document(
    document: Document,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Split ``document`` into provenance-preserving chunks."""

    text = document.content.strip()
    if not text:
        return []

    pieces: list[str] = []
    for section in _split_on_headings(text):
        pieces.extend(_split_long(section, max_chars, overlap))

    return [
        Chunk(
            content=piece.strip(),
            provenance=document.provenance,
            document_id=document.doc_id,
            index=index,
            redacted=document.redacted,
        )
        for index, piece in enumerate(pieces)
        if piece.strip()
    ]
