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

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG_NAME = "production-log.md"

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
    """

    text = str(value)
    text = re.sub(r"[\r\n|]+", " ", text)
    text = " ".join(text.split())
    return text[:200]


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

    text = log_path.read_text(encoding="utf-8")
    line = format_record(made=made, evidence=evidence, parameters=parameters, now=now)

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

    log_path.write_text(text, encoding="utf-8")
    return log_path


def read_records(project_root: str | Path) -> list[GenerationRecord]:
    """Every record line in the project's log, oldest first.

    A missing log is an empty list rather than an error: callers use this to
    ask "what does the record say", and "nothing" is the true answer for a
    partial project that never had a LOG stage.
    """

    log_path = Path(project_root) / LOG_NAME
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
            for pair in match.group("parameters").split(" "):
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
    "append_record",
    "format_record",
    "read_records",
]
