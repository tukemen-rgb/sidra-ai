"""The production log is written in the language the request was written in.

C-1940. A production set writes four documents, and until this item every
one of them was Japanese no matter what language the request was in - an
English 「make a game project about an owl」 got the reply in English
(C-1938) and a folder of four Japanese files. The reply is a sentence in a
chat; the folder is the artifact, and the artifact is what gets saved and
forwarded (C-1274, C-1283, C-1640).

Only the log is covered here, and that is the point of the item rather than
an omission in it: the three design documents are filled from the template
registry - ``how_to_play``, the control labels, the parameter names - which
holds those in Japanese alone, so branching their frame would ship a
document with English headings over Japanese rows. That is the
half-translated artifact C-1929's sabotage D4 exists to punish. The log is
the one file of the four whose text is entirely the scaffolder's own, so it
can be finished rather than half-done.

What the judge cannot see, and why these tests exist beside it:
``creation_project_files_match_the_language_asked`` measures the **share**
of a file's lines that carry Japanese, against a 20% limit that is there so
a quoted Japanese title does not condemn an English document. One Japanese
line in a sixteen-line log is 6% - under the limit. So the record line
going back to Japanese, or the parser losing the English format and reading
the log back as empty, are both invisible to that measurement. They are
pinned exactly here instead.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sidra_ai.creation.projects import scaffold_project
from sidra_ai.creation.records import (
    LOG_NAME,
    RECORDS_HEADING,
    RECORDS_HEADING_EN,
    append_record,
    read_records,
)

PINNED = datetime(2026, 9, 17, 20, 0, 0, tzinfo=timezone.utc)

ENGLISH_ASK = "make a game project about an owl"
JAPANESE_ASK = "猫のゲームを企画から作って"

#: Japanese script. Punctuation is deliberately not included: an English log
#: may legitimately quote a Japanese title, which is the operator's own word.
JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")


def _log(request: str, tmp_path) -> str:
    project = scaffold_project(request, tmp_path, now=PINNED)
    return (project.root / LOG_NAME).read_text(encoding="utf-8")


def test_an_english_request_gets_a_log_with_no_japanese_left_in_it(tmp_path):
    """Every line, not most of them.

    The title 「owl」 carries no Japanese, so for this request the strict
    answer is available and the loose one would only hide a missed line.
    """

    text = _log(ENGLISH_ASK, tmp_path)
    leftovers = [line for line in text.splitlines() if JAPANESE.search(line)]
    assert not leftovers, f"Japanese left in an English production log: {leftovers}"
    # Not merely "no Japanese" - a file that stopped being written would also
    # pass that. The log still has to be a log.
    assert RECORDS_HEADING_EN in text
    assert "## Made in this run" in text
    assert "game.html" in text


def test_a_japanese_request_still_gets_the_japanese_log(tmp_path):
    """The side that already worked has to stay where it was.

    Named separately from the English test because a single test over both
    languages is the degenerate shape C-1939 measured: a loss on one side
    paid for by a gain on the other, with the total never moving.
    """

    text = _log(JAPANESE_ASK, tmp_path)
    assert "制作記録" in text
    assert RECORDS_HEADING in text
    assert "作った物:" in text
    assert "## この回で作ったもの" in text


def test_the_english_record_line_reads_back(tmp_path):
    """A record only a Japanese parser can read is a record the log lost.

    ``read_records`` is what answers 「この game.html はいつ・何から作られたか」
    a week later; an English log whose lines no pattern matches answers
    "no record" while looking perfectly complete to a person.
    """

    project = scaffold_project(ENGLISH_ASK, tmp_path, now=PINNED)
    records = read_records(project.root)
    assert len(records) == 1
    record = records[0]
    assert record.when == "2026-09-17T20:00:00Z"
    assert "game.html" in record.made
    assert record.parameters.get("template")
    # The empty marker is the English one, and it is dropped on read rather
    # than coming back as a source called "none".
    assert record.evidence == ()


def test_a_later_run_appends_under_the_heading_the_file_already_has(tmp_path):
    """A log is appended to for as long as the production lives.

    A Japanese run against a log an English run opened must add its line to
    the section that is there. Opening a second 「生成履歴」 further down
    would still parse - both formats are read - so nothing would ever report
    it, and the file a person opens would have its history in two places.
    """

    project = scaffold_project(ENGLISH_ASK, tmp_path, now=PINNED)
    append_record(
        project.root,
        made=["scenario.md"],
        evidence=[],
        parameters={"template": "fishing"},
        now=PINNED,
    )
    text = (project.root / LOG_NAME).read_text(encoding="utf-8")
    assert text.count(RECORDS_HEADING_EN) == 1
    assert RECORDS_HEADING not in text
    assert len(read_records(project.root)) == 2
