"""Are the files a production set leaves behind in the language asked for?

C-1938 put the project's *reply* and its *title* into the language of the
request. The files were not touched, and the files are the artifact - this
loop keeps arguing that the thing which gets saved and forwarded matters
more than the sentence in the chat (C-1274 said the summary admitted what
the artifact did not; C-1283 said the same about the 3D preview).

Measured for 「make a game project about an owl」 when this was written:
of the lines that carry any text, **90% of features.md, 94% of
scenario.md, 95% of structure.md and 66% of production-log.md were
Japanese**. The reply said "Made a full production set for “owl”" and the
folder it pointed at was four Japanese documents. C-1940 finished
`production-log.md`; the other three are waiting on English in the
template registry and are still Japanese.

This does NOT report a pass. It counts the **English request's** files
that are actually in English, so the gap is a number that has to rise
rather than a green light that would bless it.

The Japanese side is a GUARD, not part of the count. A single total over
both languages was the first shape of this judge and it was degenerate:
three different sabotages - the shared header turned English for
everyone, a file written empty, the threshold loosened until Japanese
counted as English - **all left the total unchanged at 4 of 8**, because
a loss on one side was paid for by a gain on the other. A number that
cannot move when the thing under it breaks is not a measurement. So the
Japanese documents must all still be Japanese, and if any of them is not,
the count is zero and the reason is named.

C-1941 - **what this judge could not see, and why the ruler changed.**
C-1940 broke its own work seven ways and this judge noticed three. The
five it missed were all *partial*: one Japanese line back in the record,
three Japanese lines back in the front matter, the body of the document
deleted. The cause was the ruler: a **share** of the file's lines,
against a 20% limit. Sixteen lines of log means one to three Japanese
lines sit under the limit, and a document whose body was deleted keeps
its share because what remains is short. A judge that can only see a file
change language *wholesale* is exactly the instrument that would bless a
half-translated `features.md` at 19% - the artifact this loop has refused
four times (C-1929 D4, C-1932 D3/D4). So the share is gone, replaced by
three rules that a partial failure cannot slip through:

1. **No Japanese at all** on the English side. The share existed for a
   file that quotes a Japanese title; the English request does not, so
   the achievable answer is zero and anything above it is a leftover.
2. **The file is still the document.** Every stage file opens with
   ``# {title} — {stage}``, and all four agree on the title (the
   invariant C-1621 put there). A document written empty, or gutted down
   to the section a later append recreates, no longer opens with it. This
   is read off the product's own output rather than a hand-written list
   of headings a file "should" contain - a copied table is the one that
   goes stale (C-1848, C-1850).
3. **The same shape in both languages.** A file's Markdown headings are
   counted and must match its counterpart in the other language.
   Otherwise "translating" a section by **deleting** it passes rule 1
   perfectly: what is not there cannot be Japanese.

What it still cannot see, said plainly rather than left for the next
reader to discover: the two remaining sabotages of C-1940 broke the
**record format** - the English line stopped parsing, and a second
生成履歴 section was opened below the first. Those are not language
defects and this judge has no business claiming them; they are pinned in
``tests/test_project_log_language.py`` instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Japanese script. Punctuation is left out deliberately: a file may quote a
#: Japanese title, and a title is the operator's own word (C-1929).
_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Every Markdown heading, at any level.
_HEADING = re.compile(r"^#{1,6} ", re.M)

#: The line every stage file opens with: ``# {title} — {stage}``. The em dash
#: is the scaffolder's own separator (``_front_matter`` and ``story._header``
#: both write it), so this is the product's format, not a wish about it.
_TITLE_LINE = re.compile(r"^# (?P<title>.+?) — (?P<stage>.+)$")

ENGLISH_ASK = "make a game project about an owl"
JAPANESE_ASK = "猫のゲームを企画から作って"

#: What share of a file's non-empty lines must carry Japanese for the
#: **Japanese** side to still count as Japanese. This is the guard's ruler
#: only. The English side is not measured in shares any more (C-1941).
JAPANESE_SHARE_FLOOR = 0.2

#: The four documents a production set writes.
EXPECTED_FILES = ("scenario.md", "structure.md", "features.md", "production-log.md")


@dataclass(frozen=True)
class ProjectFilesResult:
    files_in_the_right_language: int
    files_total: int
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _write(request: str) -> Path:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.project_job import build_project_generator
    from sidra_ai.evals.scratch import scratch_dir

    generate = build_project_generator(scratch_dir("sidra-project-files-"))
    outcome = generate(request, detect_creation_intent(request))
    return Path(str(outcome.artifact_path))


def _japanese_share(text: str) -> float:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    return sum(1 for line in lines if _JAPANESE.search(line)) / len(lines)


def _japanese_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if _JAPANESE.search(line))


def _opening_title(text: str) -> str | None:
    """The title in the file's opening ``# {title} — {stage}`` line.

    ``None`` when the file does not open with one at all, which is what a
    document written empty looks like once a later append has put its own
    heading at the top.
    """

    for line in text.splitlines():
        if not line.strip():
            continue
        match = _TITLE_LINE.match(line.strip())
        return match.group("title") if match else None
    return None


def evaluate_project_files_match_the_language_asked() -> ProjectFilesResult:
    failures: list[str] = []
    readings: list[str] = []
    english_right = 0
    japanese_held = True

    # Both sets are written first, because rule 3 compares a file against the
    # same file in the other language and cannot judge one side alone.
    written: dict[bool, dict[str, str | None]] = {}
    for request, wants_japanese in ((ENGLISH_ASK, False), (JAPANESE_ASK, True)):
        root = _write(request)
        side: dict[str, str | None] = {}
        for name in EXPECTED_FILES:
            path = root / name
            side[name] = path.read_text(encoding="utf-8") if path.exists() else None
        written[wants_japanese] = side

    for wants_japanese, request in ((False, ENGLISH_ASK), (True, JAPANESE_ASK)):
        side = written[wants_japanese]
        other = written[not wants_japanese]
        tag = "JA" if wants_japanese else "EN"

        # Rule 2, second half: the four documents of one production have to
        # agree on whose production it is (C-1621). Read off the files, so a
        # file that lost its opening line is caught by the same check.
        titles = {name: _opening_title(text or "") for name, text in side.items()}
        agreed = {title for title in titles.values() if title}
        if len(agreed) > 1:
            failures.append(
                f"「{request}」: the four documents disagree about the title "
                f"({sorted(agreed)})"
            )
            if wants_japanese:
                japanese_held = False

        for name in EXPECTED_FILES:
            text = side[name]
            if text is None:
                # A file that was not written cannot be in any language. It
                # counts as neither, and on the Japanese side it breaks the
                # guard - a set that stopped writing a document is not a set
                # whose documents are in the right language.
                failures.append(f"「{request}」: {name} was not written at all")
                if wants_japanese:
                    japanese_held = False
                continue

            japanese_count = _japanese_lines(text)
            share = _japanese_share(text)
            headings = len(_HEADING.findall(text))
            counterpart = other.get(name)
            other_headings = (
                len(_HEADING.findall(counterpart)) if counterpart is not None else -1
            )
            readings.append(
                f"{tag} {name} {share:.0%} ja-lines={japanese_count} h={headings}"
            )

            # Rule 2: the file still opens as the document it is.
            if titles[name] is None:
                failures.append(
                    f"「{request}」 {name}: does not open with its "
                    "「# 題 — ステージ」 line - the document is gone, whatever "
                    "language the rest of it is in"
                )
                if wants_japanese:
                    japanese_held = False
                continue

            # Rule 3: the same document in the other language has the same
            # shape. Deleting a section is not translating it.
            if other_headings != headings:
                failures.append(
                    f"「{request}」 {name}: {headings} headings against "
                    f"{other_headings} in the other language - a section was "
                    "dropped rather than written"
                )
                if wants_japanese:
                    japanese_held = False
                continue

            if wants_japanese:
                # The guard keeps the share: a Japanese document is allowed
                # English in it (file names, parameter keys), and always had.
                if share <= JAPANESE_SHARE_FLOOR:
                    japanese_held = False
                    failures.append(
                        f"「{request}」 {name}: only {share:.0%} of its lines are "
                        "Japanese - the side that already worked has moved"
                    )
            elif japanese_count:
                # Rule 1: not a share. One line left behind is one line.
                failures.append(
                    f"「{request}」 {name}: {japanese_count} of its lines still "
                    f"carry Japanese ({share:.0%}), wanted an English one"
                )
            else:
                english_right += 1

    return ProjectFilesResult(
        # Zero when the Japanese side has moved, so a gain on one side can
        # never pay for a loss on the other.
        files_in_the_right_language=english_right if japanese_held else 0,
        files_total=len(EXPECTED_FILES),
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )
