"""Appending one honest line per generation to a production's log.

A production log that only says "生成のたびに 1 行足す決まりです" is a rule
without a mechanism; nothing ever followed it. This module is the mechanism:
every scaffold run appends a machine-checkable record line saying **when it
ran, what it wrote, which evidence paths it used, and with which
parameters**. The line is what makes "この game.html はいつ・何から
作られたか" answerable a week later, when the chat that produced it is gone.

The record deliberately carries **paths, times and parameters only** - the
same rule the artifacts listing follows, and for the same reason. A record
that quoted a retrieved passage would copy indexed content into a file that
reads as metadata, and metadata is what people paste into issues and
screenshots without screening it. Every value written here is sanitised down
to one line with the field separator stripped, so a title (operator text)
cannot fake extra fields in its own record.

Parsing is the other half. ``read_records`` reads back what ``append_record``
wrote, and the product metric goes through it: a log format only a human can
check is a log whose regressions only a human can notice.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from dataclasses import dataclass
from html import escape
from datetime import datetime, timezone
from pathlib import Path

#: Serialises the read-modify-write both appenders do (C-1862).
#:
#: Both of them read the whole log, splice one line in, and write the whole
#: log back. With nothing holding that together, two threads read the same
#: text and the second write throws the first record away - and measured,
#: that is not a rare interleaving but the normal case: twelve threads
#: appending eight records each landed **11, 4, 7, 3 and 15 of 96** across
#: five runs. The visible symptom was a ``UnicodeDecodeError`` in 3 of those
#: 5 runs; the silent loss of ~90% of the records happened in 5 of 5. A
#: chat asking 「この game.html はいつ・何から作られたか」 is the whole point
#: of this module, and concurrently it was mostly answering "no record".
#:
#: One lock for the module rather than one per path: the critical section is
#: a small file read and write, two productions contending is not a real
#: workload, and a per-path table needs its own lock to be safe - complexity
#: bought with nothing.
#:
#: What it does **not** cover: another process. That is what the atomic
#: replace below is for - a reader in any process sees either the old file
#: or the new one, never a half-written one. Two *processes* appending at
#: once can still lose a record, and nothing here claims otherwise; v0.1
#: serves from one process.
_APPEND_LOCK = threading.Lock()


def _write_whole_file(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` in one step, or not at all.

    ``Path.write_text`` opens for writing, which truncates, and only then
    writes - so a reader arriving in that window gets a prefix, and a prefix
    that lands mid-character is the ``UnicodeDecodeError`` this was filed
    for (0x8f at position 185, and 0xa0/0x81 when reproduced). Writing a
    neighbouring temp file and renaming it over the target closes that: the
    rename is atomic, so no reader ever opens a partial log.
    """

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        # A failed write must not leave litter beside the log a person reads.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise

LOG_NAME = "production-log.md"

#: C-1830: where the same record goes for an artifact made on its own. Outside
#: ``artifacts/`` on purpose: a file inside it would be listed as an artifact
#: and change the count that ``/v1/artifacts`` reports as the true total.
STANDALONE_LOG_NAME = "creation-log.md"

#: The heading records live under. Appending under a heading rather than at
#: end-of-file keeps hand-written notes below it intact: the section is the
#: machine's, the rest of the document stays the operator's.
RECORDS_HEADING = "## 生成履歴"

#: C-1940: the same heading for a log written in English. A production log is
#: a file that is saved and forwarded, so it follows the same rule every reply
#: surface follows (C-1918..C-1938): the language of the request. Two headings
#: rather than one translated in place, because a log written last week under
#: the Japanese heading has to keep receiving records - ``append_record``
#: appends under whichever heading the file already carries.
RECORDS_HEADING_EN = "## Generation history"

#: One record. The separator is `` | `` (spaces included) and the sanitiser
#: strips bare ``|`` from every value, so field boundaries cannot be forged
#: by the text inside a field.
_LINE = re.compile(
    r"^- (?P<when>\S+) \| 作った物: (?P<made>.*?) \| 根拠: (?P<evidence>.*?)"
    r" \| パラメータ: (?P<parameters>.*)$"
)

#: The same record written in English (C-1940). Same separator, same fields,
#: same order - only the labels differ, so a reader of either file is reading
#: the same record.
_LINE_EN = re.compile(
    r"^- (?P<when>\S+) \| made: (?P<made>.*?) \| sources: (?P<evidence>.*?)"
    r" \| parameters: (?P<parameters>.*)$"
)

#: The empty-field marker. Written instead of an empty string so a record
#: with no evidence is visibly "none" rather than ambiguously blank.
_NONE = "なし"
_NONE_EN = "none"

#: Every record shape this module writes, as ``(pattern, empty-marker,
#: joiner)``. ``read_records`` walks this table rather than naming the
#: Japanese one and remembering to add the other: a second format that the
#: parser does not know about is a log that silently reads back as empty.
_RECORD_FORMATS = (
    (_LINE, _NONE, "、"),
    (_LINE_EN, _NONE_EN, ", "),
)


@dataclass(frozen=True)
class GenerationRecord:
    """One parsed line of the 生成履歴 section."""

    when: str
    made: tuple[str, ...]
    evidence: tuple[str, ...]
    parameters: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "when": self.when,
            "made": list(self.made),
            "evidence": list(self.evidence),
            "parameters": dict(self.parameters),
        }


def _clean(value: object) -> str:
    """One value, one line, no separator characters.

    Newlines would end the record early and ``|`` would add fields to it;
    both come straight from operator text (titles, file names), so they are
    replaced rather than trusted. Length is capped for the same reason the
    audit log caps its fields: a log line an operator cannot read end to end
    is a log line nobody reads.

    HTML is escaped too (C-1486): a source label is the path of an indexed
    Issue/PR body (EXTERNAL trust), and this line is Markdown that a renderer
    permitting inline HTML would execute - the same neutralisation the report
    (C-1483) and the other stage files apply.
    """

    text = str(value)
    text = re.sub(r"[\r\n|]+", " ", text)
    text = " ".join(text.split())
    return escape(text[:200], quote=False)


def format_record(
    *,
    made: list[str],
    evidence: list[str],
    parameters: dict[str, object],
    now: datetime | None = None,
    in_japanese: bool = True,
) -> str:
    """Render one record line.

    Parameter values are scalars by contract (numbers, short strings); the
    caller passing anything else gets its ``str()`` sanitised like everything
    else rather than an error, because a record that raises is a record that
    silently stops being written.

    ``in_japanese=False`` writes the English form (C-1940). It defaults to
    Japanese so every existing caller keeps writing the line it wrote before:
    the language is the *request's*, and only the caller holding the request
    knows it.
    """

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    none = _NONE if in_japanese else _NONE_EN
    joiner = "、" if in_japanese else ", "
    made_part = joiner.join(_clean(name) for name in made) or none
    evidence_part = joiner.join(_clean(source) for source in evidence) or none
    parameter_part = (
        " ".join(f"{_clean(key)}={_clean(value)}" for key, value in parameters.items())
        or none
    )
    if in_japanese:
        return (
            f"- {stamp} | 作った物: {made_part} | 根拠: {evidence_part}"
            f" | パラメータ: {parameter_part}"
        )
    return (
        f"- {stamp} | made: {made_part} | sources: {evidence_part}"
        f" | parameters: {parameter_part}"
    )


def append_record(
    project_root: str | Path,
    *,
    made: list[str],
    evidence: list[str],
    parameters: dict[str, object],
    now: datetime | None = None,
    in_japanese: bool = True,
) -> Path:
    """Add one generation record to the project's ``production-log.md``.

    The log file must already exist: a run that did not write the LOG stage
    was asked for a partial project, and giving it a log file anyway would
    break "脚本だけ作って writes one file" - the property the scaffolder's
    tests pin hardest. Raising is honest; the caller decides whether the
    stage exists, this function only refuses to create files behind its back.
    """

    log_path = Path(project_root) / LOG_NAME
    if not log_path.is_file():
        raise FileNotFoundError(
            f"{log_path} does not exist; records are appended to the LOG stage, never created beside it"
        )

    line = format_record(
        made=made,
        evidence=evidence,
        parameters=parameters,
        now=now,
        in_japanese=in_japanese,
    )

    # Read and write under one lock (C-1862): the read decides what the
    # write contains, so a second thread reading between them writes the
    # first record away. Measured before the lock existed, that lost about
    # nine records in ten.
    with _APPEND_LOCK:
        text = log_path.read_text(encoding="utf-8")

        # C-1940: the heading the file *already carries* wins over the one
        # this run's language would choose. A log is appended to for as long
        # as the production lives, and a run in the other language must add
        # its line to the existing section rather than open a second one
        # further down - two 「生成履歴」 sections is a log nobody can read in
        # order, and ``read_records`` would still parse both, so nothing
        # would ever report it.
        heading = RECORDS_HEADING if in_japanese else RECORDS_HEADING_EN
        for candidate in (RECORDS_HEADING, RECORDS_HEADING_EN):
            if candidate in text:
                heading = candidate
                break

        if heading in text:
            # Insert at the end of the existing section - directly before the
            # next heading, or at end of file when the section is last - so
            # records stay chronological even if an operator wrote notes below.
            head, _, tail = text.partition(heading)
            next_heading = re.search(r"^#{1,6} ", tail, flags=re.M)
            if next_heading:
                cut = next_heading.start()
                section, rest = tail[:cut], tail[cut:]
            else:
                section, rest = tail, ""
            section = section.rstrip("\n") + "\n" + line + "\n\n"
            text = head + heading + section + rest
        else:
            text = text.rstrip("\n") + f"\n\n{heading}\n\n{line}\n"

        _write_whole_file(log_path, text)
    return log_path


#: The heading the standalone log opens with. A log a person opens has to say
#: what it is before its first line, and the records section below it is the
#: same one the production log uses, so one parser reads both.
_STANDALONE_HEADER = (
    "# 生成の記録\n\n"
    "SIDRA AI が単体で作った成果物の記録です。ファイル名・時刻・題・"
    "根拠に使った出典ラベル・パラメータだけを書きます"
    "（取得した文書の本文や、依頼の文そのものは書きません）。\n"
)

#: The same opening for a log a reader of English opens (C-1947). The
#: production log followed the request's language in C-1940; this one did
#: not, and this one is the common path - six generators go through it,
#: against the one that scaffolds a whole production. Somebody who asks
#: 「make a gif of an owl」 in English gets the gif and, beside it, a
#: Japanese file explaining what the folder is.
_STANDALONE_HEADER_EN = (
    "# Record of what was generated\n\n"
    "A record of the artifacts SIDRA AI made on their own. It carries the "
    "file name, the time, the title, the source labels used as evidence and "
    "the parameters - and nothing else (never the text of an indexed "
    "document, and never the wording of the request).\n"
)


def append_standalone_record(
    data_dir: str | Path,
    *,
    made: list[str],
    evidence: list[str],
    parameters: dict[str, object],
    now: datetime | None = None,
    in_japanese: bool = True,
) -> Path:
    """Add one record for an artifact that was made on its own.

    C-1830. The module above exists so that 「この game.html はいつ・何から
    作られたか」 has an answer a week later, and until now it had one only for
    a game made inside a whole production: ``append_record`` was called from
    one place. The ordinary request - the common path, six generators - wrote
    no record at all, and three games for 猫, 犬 and 忍者 came back as
    ``game-fishing-….html``, ``…-2.html`` and ``…-3.html``.

    **This one creates the file when it is missing, and that is the opposite
    of its sibling on purpose.** ``append_record`` refuses, because a project
    without a LOG stage was asked for a partial project and a log file
    appearing anyway would break that. Here there is no stage to respect: the
    log is the only record a standalone artifact gets, so refusing to create
    it would mean never writing one.

    Same line format, same 「生成履歴」 heading, so ``read_records`` reads both.
    """

    log_path = Path(data_dir) / STANDALONE_LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = format_record(
        made=made,
        evidence=evidence,
        parameters=parameters,
        now=now,
        in_japanese=in_japanese,
    )

    # Creating the file is inside the lock too (C-1862): two threads finding
    # it missing at once both wrote the header, and the second one wrote it
    # over whatever the first had already recorded.
    with _APPEND_LOCK:
        if not log_path.is_file():
            _write_whole_file(
                log_path,
                _STANDALONE_HEADER if in_japanese else _STANDALONE_HEADER_EN,
            )

        text = log_path.read_text(encoding="utf-8")
        # C-1947, the same rule the production log follows (C-1940): the
        # heading the file already carries wins. One log collects every
        # artifact this data directory ever made, so a request in the other
        # language must add its line to the section that is there rather
        # than open a second one further down.
        heading = RECORDS_HEADING if in_japanese else RECORDS_HEADING_EN
        for candidate in (RECORDS_HEADING, RECORDS_HEADING_EN):
            if candidate in text:
                heading = candidate
                break
        if heading in text:
            text = text.rstrip("\n") + "\n" + line + "\n"
        else:
            text = text.rstrip("\n") + f"\n\n{heading}\n\n{line}\n"
        _write_whole_file(log_path, text)
    return log_path


def read_records(
    project_root: str | Path, *, log_name: str = LOG_NAME
) -> list[GenerationRecord]:
    """Every record line in the project's log, oldest first.

    A missing log is an empty list rather than an error: callers use this to
    ask "what does the record say", and "nothing" is the true answer for a
    partial project that never had a LOG stage.
    """

    log_path = Path(project_root) / log_name
    if not log_path.is_file():
        return []

    records: list[GenerationRecord] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        for pattern, none, joiner in _RECORD_FORMATS:
            match = pattern.match(raw.strip())
            if match:
                break
        if not match:
            continue
        made = tuple(p for p in match.group("made").split(joiner) if p and p != none)
        evidence = tuple(
            p for p in match.group("evidence").split(joiner) if p and p != none
        )
        parameters: dict[str, str] = {}
        if match.group("parameters") != none:
            # C-1830: split before a key, not on every space. A value with a
            # space in it (an English title) used to drop everything after the
            # first word, silently and only on read-back - the line a person
            # reads was always complete.
            for pair in re.split(r" (?=[^ =]+=)", match.group("parameters")):
                key, sep, value = pair.partition("=")
                if sep:
                    parameters[key] = value
        records.append(
            GenerationRecord(
                when=match.group("when"),
                made=made,
                evidence=evidence,
                parameters=parameters,
            )
        )
    return records


__all__ = [
    "GenerationRecord",
    "LOG_NAME",
    "RECORDS_HEADING",
    "RECORDS_HEADING_EN",
    "STANDALONE_LOG_NAME",
    "append_record",
    "append_standalone_record",
    "format_record",
    "read_records",
]
