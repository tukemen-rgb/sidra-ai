"""Is a non-UTF-8 text document recovered, not dropped as if it were binary?

C-1780. ``decode_content`` decoded a base64 GitHub body as UTF-8 and, on
failure, returned ``""`` - the same value a binary file gives. ``readme_document``
and ``doc_document`` then dropped the document (``return None``). So a Shift-JIS
or EUC-JP README - readable text GitHub returned in full - vanished from the
corpus with a clean, complete-looking ingestion report, the one silent drop that
escaped this path's truncation-honesty discipline.

``decode_content`` now tells binary from non-UTF-8 text (a NUL byte marks binary)
and tries the known text encodings (UTF-8, then cp932, then EUC-JP, all strict)
before giving up, so a legacy Japanese document is indexed instead of discarded.

The checks drive ``decode_content`` and ``readme_document`` with synthetic
base64 payloads.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from sidra_ai.ingestion.normalize import decode_content, readme_document

_TEXT = "これは日本語のREADMEです。デプロイ手順を説明します。"


def _payload(data: bytes, *, encoding: str = "base64", path: str = "README.md") -> dict:
    return {
        "encoding": encoding,
        "content": base64.b64encode(data).decode("ascii"),
        "path": path,
    }


@dataclass(frozen=True)
class DecodeLegacyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ingestion_decodes_legacy_text_encodings() -> DecodeLegacyResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a Shift-JIS / cp932 document is recovered -------------------
    add(decode_content(_payload(_TEXT.encode("cp932"))) == _TEXT,
        "A: a cp932 (Shift-JIS) document was not recovered")
    # --- (B) an EUC-JP document is recovered ----------------------------
    add(decode_content(_payload(_TEXT.encode("euc_jp"))) == _TEXT,
        "B: a EUC-JP document was not recovered")
    # --- (C) a UTF-8 document still decodes (no regression) -------------
    add(decode_content(_payload(_TEXT.encode("utf-8"))) == _TEXT,
        "C: a UTF-8 document no longer decodes")
    # --- (D) a genuine binary file stays skipped (not mojibake'd) -------
    binary = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x00, 0x1A, 0x0A])
    add(decode_content(_payload(binary)) == "",
        "D: a binary file was wrongly decoded instead of skipped")
    # --- (E) readme_document keeps a cp932 doc (end to end) -------------
    doc = readme_document(_payload(_TEXT.encode("cp932")),
                          repository="o/r", commit_sha="c" * 40, license="MIT")
    add(doc is not None and doc.content == _TEXT,
        "E: a Shift-JIS README was dropped rather than indexed")
    # --- (F) a non-base64 payload returns its raw content --------------
    add(decode_content({"encoding": "utf-8", "content": "plain text"}) == "plain text",
        "F: a non-base64 payload no longer returns its raw content")

    total = 6
    return DecodeLegacyResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "DecodeLegacyResult",
    "evaluate_ingestion_decodes_legacy_text_encodings",
]
