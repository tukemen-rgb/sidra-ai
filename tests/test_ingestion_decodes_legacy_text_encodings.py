"""C-1780: a non-UTF-8 text document is recovered, not dropped as if binary.

decode_content returned "" for any base64 body that was not valid UTF-8 - the
same value binary files give - so a Shift-JIS/EUC-JP README vanished from the
corpus with no word in the ingestion report. It now tries the known text
encodings (UTF-8, cp932, EUC-JP, all strict) and only treats a NUL-bearing body
as binary.
"""

from __future__ import annotations

import base64

from sidra_ai.ingestion.normalize import decode_content, readme_document
from sidra_ai.evals.ingestion_decodes_legacy_text_encodings import (
    evaluate_ingestion_decodes_legacy_text_encodings,
)

_TEXT = "これは日本語のREADMEです。デプロイ手順を説明します。"


def _payload(data: bytes) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(data).decode("ascii"), "path": "README.md"}


def test_decode_legacy_eval_passes():
    result = evaluate_ingestion_decodes_legacy_text_encodings()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_shift_jis_and_euc_jp_are_recovered():
    assert decode_content(_payload(_TEXT.encode("cp932"))) == _TEXT
    assert decode_content(_payload(_TEXT.encode("euc_jp"))) == _TEXT


def test_utf8_still_decodes_and_binary_stays_skipped():
    assert decode_content(_payload(_TEXT.encode("utf-8"))) == _TEXT
    assert decode_content(_payload(bytes([0x89, 0x50, 0x4E, 0x47, 0x00, 0x1A]))) == ""


def test_a_shift_jis_readme_is_no_longer_dropped():
    doc = readme_document(_payload(_TEXT.encode("cp932")),
                          repository="o/r", commit_sha="c" * 40, license="MIT")
    assert doc is not None
    assert doc.content == _TEXT
