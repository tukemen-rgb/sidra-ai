"""C-1280: the citation excerpt centres on the answer inside English prose.

C-1270 gave Japanese single-line paragraphs the sentence boundaries the excerpt
window needs; English was left with only CJK marks, so an English Markdown
paragraph (one logical line) offered a single candidate - the head - and the
citation clipped right before the answer. ASCII 「.」 is a boundary now, but only
with the shape a real sentence break has: preceded by a lowercase letter or digit
and followed by whitespace then an uppercase letter, so an initial, an acronym, a
decimal, a dotted name and 「e.g. the」 are not mistaken for one.
"""

from __future__ import annotations

from sidra_ai.api.citations import _candidate_starts, select_excerpt_window
from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.evals.excerpt_centers_english_paragraph import (
    evaluate_excerpt_centers_english_paragraph,
)

_EFILL = "This is a filler sentence that adds length here. "
_ETAIL = "This is trailing text that follows the key line. "


def test_excerpt_centers_english_paragraph_eval_passes():
    result = evaluate_excerpt_centers_english_paragraph()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 15


def test_english_single_line_window_reaches_the_answer():
    content = (
        _EFILL * 5
        + "The default request timeout is thirty seconds unless it is overridden. "
        + _ETAIL * 6
    )
    query = "What is the default request timeout?"
    window = select_excerpt_window(content, query)
    # the answer is past the cap, so the pre-fix head window could not show it
    assert "thirty seconds" not in content[:MAX_CITATION_EXCERPT_CHARS]
    assert "timeout is thirty seconds" in window
    assert len(window) <= MAX_CITATION_EXCERPT_CHARS


def test_ascii_period_boundaries_do_not_open_on_false_breaks():
    pad = "This is padding text that extends the chunk well beyond the cap here. " * 4
    head = "A short opening sentence sits here. "

    def opens_on(body: str, prefix: str) -> bool:
        c = head + body + pad
        return any(c[s:].startswith(prefix) for s in _candidate_starts(c))

    assert not opens_on("Contact J. Doe about the open ticket. ", "Doe about")
    assert not opens_on("The class Foo.Bar handles the task. ", "Bar handles")
    assert not opens_on("Use a cache, e.g. the local disk store. ", "the local disk")
    assert not opens_on("The link uses TLS. Certificates rotate soon. ", "Certificates")
    # a genuine lowercase-ended sentence still opens the next window
    assert opens_on("The value is stored safely today. ", "The value is")


def test_japanese_paragraph_still_centres():
    content = "前置きの段落がここに続く。" * 40 + "重要: バックアップは毎日午前 3 時に実行されます。" + "その後の説明。" * 20
    window = select_excerpt_window(content, "バックアップの実行時刻はいつですか")
    assert "バックアップは毎日午前 3 時" in window


def test_unmatched_query_falls_back_to_the_head():
    content = _EFILL * 5 + "A distinctive sentence appears late in the chunk here. " + _ETAIL * 6
    assert select_excerpt_window(content, "") == content[:MAX_CITATION_EXCERPT_CHARS]
    assert select_excerpt_window(content, "zzz qqq") == content[:MAX_CITATION_EXCERPT_CHARS]
