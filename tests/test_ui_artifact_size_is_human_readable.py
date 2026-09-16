"""C-1895: the entry page shows file sizes in units a person reads.

The generated-file listing printed the size as a raw byte count -
``a.bytes + " bytes"`` for a flat artifact and ``f.bytes + " bytes"`` for a file
inside a production - so a 107 KB animation read as ``109927 bytes``. A single
``formatBytes`` helper now renders B/KB/MB and both loops call it. The
behavioural proof (109927 -> "107 KB", 3201 -> "3.1 KB", 2411520 -> "2.3 MB" in
a real engine) ran at fix time and is recorded in the loop log.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_artifact_size_is_human_readable import (
    evaluate_ui_artifact_size_is_human_readable,
)


def test_ui_artifact_size_is_human_readable_eval_passes():
    result = evaluate_ui_artifact_size_is_human_readable()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_format_bytes_helper_scales_and_names_units():
    start = ASK_PAGE.find("function formatBytes(")
    assert start >= 0, "formatBytes helper not defined"
    body = ASK_PAGE[start : ASK_PAGE.find("\n  function ", start)]
    assert re.search(r"/=?\s*1024", body), "formatBytes does not divide by 1024"
    assert "KB" in body and "MB" in body


def test_both_listings_route_size_through_the_helper():
    assert re.search(r"formatBytes\(\s*a\.bytes\s*\)", ASK_PAGE)
    assert re.search(r"formatBytes\(\s*f\.bytes\s*\)", ASK_PAGE)


def test_raw_byte_concatenation_is_gone():
    assert 'a.bytes + " bytes' not in ASK_PAGE
    assert 'f.bytes + " bytes' not in ASK_PAGE
