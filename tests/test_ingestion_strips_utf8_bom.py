"""C-1975: a UTF-8-with-BOM file survives ingestion instead of being quarantined.

The leading byte-order mark (U+FEFF) a Windows/Notepad UTF-8 file carries tripped
the ingestion gate's invisible_characters detector, quarantining the whole file.
decode_content now consumes a single leading BOM (utf-8-sig semantics); every
in-content invisible character still reaches the gate, so injection defense is
unchanged.
"""

from __future__ import annotations

import base64

from sidra_ai.evals.ingestion_strips_utf8_bom import evaluate_ingestion_strips_utf8_bom
from sidra_ai.ingestion.normalize import decode_content

_BOM = "﻿"
_TEXT = "# 見出し\n\n本文のテキストです。"


def _payload(data: bytes) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(data).decode("ascii")}


def test_eval_passes():
    result = evaluate_ingestion_strips_utf8_bom()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total


def test_leading_bom_is_stripped():
    assert decode_content(_payload((_BOM + _TEXT).encode("utf-8"))) == _TEXT


def test_plain_utf8_unchanged():
    assert decode_content(_payload(_TEXT.encode("utf-8"))) == _TEXT


def test_mid_content_feff_is_kept():
    # Only a leading BOM is an encoding marker; a U+FEFF elsewhere is content
    # (ZWNBSP) and must survive decode so the gate can still see it.
    out = decode_content(_payload((_TEXT + _BOM + "後書き").encode("utf-8")))
    assert _BOM in out


def test_only_one_leading_bom_consumed():
    # A doubled leading BOM keeps the second one (surgical: exactly one).
    out = decode_content(_payload((_BOM + _BOM + _TEXT).encode("utf-8")))
    assert out == _BOM + _TEXT


def test_binary_still_skipped():
    assert decode_content(_payload(bytes([0x89, 0x50, 0x4E, 0x47, 0x00]))) == ""
