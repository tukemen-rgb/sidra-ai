"""C-1863: plain_text flattens a reference link and drops its URL definition.

A sibling of C-1227 (inline link), C-1840 (image) and C-1860 (HTML comment).
「[text][label]」 flattens to its text, and a 「[label]: https://…」 definition line
is dropped - scoped to a real URL target so a prose line like 「[INFO]: started」
is never removed.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.plain_text_flattens_reference_link import (
    evaluate_plain_text_flattens_reference_link,
)


def test_plain_text_reference_eval_passes():
    result = evaluate_plain_text_flattens_reference_link()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 18


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("詳しくは [仕様書][spec] を見よ。\n\n[spec]: https://example.com/spec", "詳しくは 仕様書 を見よ。"),
        ("See [the doc][1] and [guide][2].\n[1]: https://a.example/x\n[2]: https://b.example/y", "See the doc and guide."),
        ("collapsed [ref][] link", "collapsed ref link"),
    ],
)
def test_reference_link_flattened_without_bracket_or_url(raw, expected):
    got = plain_text(raw)
    assert got == expected
    assert "][" not in got and "https://" not in got


def test_prose_that_resembles_a_definition_is_kept():
    assert plain_text("[INFO]: started the server successfully") == "[INFO]: started the server successfully"
    assert plain_text("[注記]: 重要な話がある") == "[注記]: 重要な話がある"


def test_inline_link_and_shortcut_ref_unchanged():
    assert plain_text("詳細は[管理画面](https://a/d)を参照") == "詳細は管理画面を参照"
    assert plain_text("参照 [1] を見よ") == "参照 [1] を見よ"
