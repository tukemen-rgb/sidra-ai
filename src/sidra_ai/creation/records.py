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

#: One record. The separator is `` | `` (spaces included) and the sanitiser
#: strips bare ``|`` from every value, so field boundaries cannot be forged
#: by the text inside a field.
_LINE = re.compile(
    r"^- (?P<when>\S+) \| 作った物: (?P<made>.*?) \| 根拠: (?P<evidence>.*?)"
    r" \| パラメータ: (?P<parameters>.*)$"
)

#: The empty-field marker. Written instead of an empty string so a record
#: with no evidence is visibly "none" rather than ambiguously blank.
_NONE = "なし"


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
) -> str:
    """Render one record line.

    Parameter values are scalars by contract (numbers, short strings); the
    caller passing anything else gets its ``str()`` sanitised like everything
    else rather than an error, because a record that raises is a record that
    silently stops being written.
    """

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    made_part = "、".join(_clean(name) for name in made) or _NONE
    evidence_part = "、".join(_clean(source) for source in evidence) or _NONE
    parameter_part = (
        " ".join(f"{_clean(key)}={_clean(value)}" for key, value in parameters.items())
        or _NONE
    )
    return f"- {stamp} | 作った物: {made_part} | 根拠: {evidence_part} | パラメータ: {parameter_part}"


def append_record(
    project_root: str | Path,
    *,
    made: list[str],
    evidence: list[str],
    parameters: dict[str, object],
    now: datetime | None = None,
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

    line = format_record(made=made, evidence=evidence, parameters=parameters, now=now)

    # Read and write under one lock (C-1862): the read decides what the
    # write contains, so a second thread reading between them writes the
    # first record away. Measured before the lock existed, that lost about
    # nine records in ten.
    with _APPEND_LOCK:
        text = log_path.read_text(encoding="utf-8")

        if RECORDS_HEADING in text:
            # Insert at the end of the existing section - directly before the
            # next heading, or at end of file when the section is last - so
            # records stay chronological even if an operator wrote notes below.
            head, _, tail = text.partition(RECORDS_HEADING)
            next_heading = re.search(r"^#{1,6} ", tail, flags=re.M)
            if next_heading:
                cut = next_heading.start()
                section, rest = tail[:cut], tail[cut:]
            else:
                section, rest = tail, ""
            section = section.rstrip("\n") + "\n" + line + "\n\n"
            text = head + RECORDS_HEADING + section + rest
        else:
            text = text.rstrip("\n") + f"\n\n{RECORDS_HEADING}\n\n{line}\n"

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


def append_standalone_record(
    data_dir: str | Path,
    *,
    made: list[str],
    evidence: list[str],
    parameters: dict[str, object],
    now: datetime | None = None,
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
    line = format_record(made=made, evidence=evidence, parameters=parameters, now=now)

    # Creating the file is inside the lock too (C-1862): two threads finding
    # it missing at once both wrote the header, and the second one wrote it
    # over whatever the first had already recorded.
    with _APPEND_LOCK:
        if not log_path.is_file():
            _write_whole_file(log_path, _STANDALONE_HEADER)

        text = log_path.read_text(encoding="utf-8")
        if RECORDS_HEADING in text:
            text = text.rstrip("\n") + "\n" + line + "\n"
        else:
            text = text.rstrip("\n") + f"\n\n{RECORDS_HEADING}\n\n{line}\n"
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
        match = _LINE.match(raw.strip())
        if not match:
            continue
        made = tuple(p for p in match.group("made").split("、") if p and p != _NONE)
        evidence = tuple(
            p for p in match.group("evidence").split("、") if p and p != _NONE
        )
        parameters: dict[str, str] = {}
        if match.group("parameters") != _NONE:
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
    "STANDALONE_LOG_NAME",
    "append_record",
    "append_standalone_record",
    "format_record",
    "read_records",
]
