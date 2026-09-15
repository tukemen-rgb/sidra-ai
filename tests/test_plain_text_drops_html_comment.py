"""C-1860: plain_text drops an HTML comment instead of surfacing its content.

A sibling of C-1227 (link URL dropped) and C-1840 (image flattened). An HTML
comment 「<!-- ... -->」 is invisible in rendered Markdown, so its text - a PR
template instruction, a hidden note - must not surface in a flattened excerpt.
plain_text now removes the comment; the security gate's separate hidden-channel
detection of secrets/injection inside a comment is unchanged.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.plain_text_drops_html_comment import (
    evaluate_plain_text_drops_html_comment,
)


def test_plain_text_comment_eval_passes():
    result = evaluate_plain_text_drops_html_comment()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 21


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("本文 <!-- hidden --> の続き", "本文 の続き"),
        ("<!-- lead --> 表示される本文", "表示される本文"),
        ("見える本文 <!-- trailing note -->", "見える本文"),
        ("前\n<!-- multi\nline\ncomment -->\n後", "前 後"),
    ],
)
def test_comment_dropped_without_delimiter_or_content(raw, expected):
    got = plain_text(raw)
    assert got == expected
    assert "<!--" not in got and "-->" not in got


def test_secret_hidden_in_comment_not_surfaced():
    got = plain_text("設定 <!-- KEY=abc123secret --> 完了")
    assert got == "設定 完了"
    assert "KEY" not in got and "abc123secret" not in got


def test_angle_brackets_in_prose_are_not_a_comment():
    assert plain_text("型は List<String> を使う") == "型は List<String> を使う"


def test_link_flattening_still_works():
    assert plain_text("詳細は[管理画面](https://a/d)を参照") == "詳細は管理画面を参照"
