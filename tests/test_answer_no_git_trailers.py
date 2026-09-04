"""C-1221: commit git trailers must not appear in the answer body.

Commits are nearly half the indexed corpus and every one ends with git/AI
trailers (Co-Authored-By, Claude-Session, ...). The echo lead extractor
pulled them in as content, so an answer about a commit ended
「…方針を維持。 Co-Authored-By: Claude …」. ``plain_text`` now drops the known
trailer lines while leaving content and the raw citation excerpt alone.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import plain_text
from sidra_ai.evals.answer_no_git_trailers import evaluate_answer_no_git_trailers


def test_answer_no_git_trailers_eval_passes():
    result = evaluate_answer_no_git_trailers()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_plain_text_drops_known_trailers():
    text = (
        "方針を維持する。\n"
        "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_x\n"
        "Signed-off-by: Someone <s@example.com>"
    )
    out = plain_text(text)
    assert out == "方針を維持する。"
    assert "noreply@anthropic.com" not in out


def test_plain_text_keeps_content_colon_lines():
    # An allowlist, not a blanket "Word: value" rule.
    assert plain_text("TODO: あとで直す") == "TODO: あとで直す"
    assert plain_text("影響: 文書のみ") == "影響: 文書のみ"
