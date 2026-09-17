"""Are the files a production set leaves behind in the language asked for?

C-1938 put the project's *reply* and its *title* into the language of the
request. The files were not touched, and the files are the artifact - this
loop keeps arguing that the thing which gets saved and forwarded matters
more than the sentence in the chat (C-1274 said the summary admitted what
the artifact did not; C-1283 said the same about the 3D preview).

Measured for 「make a game project about an owl」: of the lines that carry
any text, **90% of features.md, 94% of scenario.md, 95% of structure.md
and 66% of production-log.md are Japanese**. The reply says "Made a full
production set for “owl”" and the folder it points at is four Japanese
documents.

This does NOT report a pass. It counts the **English request's** files
that are actually in English - 0 of 4 today - so the gap is a number that
has to rise rather than a green light that would bless it.

The Japanese side is a GUARD, not part of the count. A single total over
both languages was the first shape of this judge and it was degenerate:
three different sabotages - the shared header turned English for
everyone, a file written empty, the threshold loosened until Japanese
counted as English - **all left the total unchanged at 4 of 8**, because
a loss on one side was paid for by a gain on the other. A number that
cannot move when the thing under it breaks is not a measurement. So the
Japanese documents must all still be Japanese, and if any of them is not,
the count is zero and the reason is named.

Why it is not simply fixed here, recorded so the next attempt starts from
the measurement rather than from the intention: the frame of each document
(headings, the provenance line, the explanatory paragraphs) is prose that
can be branched like every other surface in C-1929..C-1938. The CONTENT is
not. `TEMPLATES[...].how_to_play` is a Japanese sentence
(「動くマーカーが帯の中にある間に SPACE かクリック。」), and so are the
control labels, the screen names and the parameter labels that fill the
tables. Branching only the frame would ship a document whose headings are
English and whose rows are Japanese - the half-translated artifact that
sabotage D4 of C-1929 and D3/D4 of C-1932 exist to punish, and which I
have refused three times already. Doing it properly means the template
registry gains English for those fields, which is a change to the
product's own design vocabulary and belongs in its own item.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Japanese script. Punctuation is left out deliberately: a file may quote a
#: Japanese title, and a title is the operator's own word (C-1929).
_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: What share of a file's non-empty lines may carry Japanese before the file
#: counts as "not in English". Not zero: a file may legitimately quote a
#: Japanese title or a Japanese control name, and this is about the document,
#: not about a word in it.
JAPANESE_SHARE_LIMIT = 0.2

ENGLISH_ASK = "make a game project about an owl"
JAPANESE_ASK = "猫のゲームを企画から作って"

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


def evaluate_project_files_match_the_language_asked() -> ProjectFilesResult:
    failures: list[str] = []
    readings: list[str] = []
    english_right = 0
    japanese_held = True

    for request, wants_japanese in ((ENGLISH_ASK, False), (JAPANESE_ASK, True)):
        root = _write(request)
        for name in EXPECTED_FILES:
            path = root / name
            if not path.exists():
                # A file that was not written cannot be in any language. It
                # counts as neither, and on the Japanese side it breaks the
                # guard - a set that stopped writing a document is not a set
                # whose documents are in the right language.
                failures.append(f"「{request}」: {name} was not written at all")
                if wants_japanese:
                    japanese_held = False
                continue
            share = _japanese_share(path.read_text(encoding="utf-8"))
            japanese = share > JAPANESE_SHARE_LIMIT
            if wants_japanese:
                if not japanese:
                    japanese_held = False
                    failures.append(
                        f"「{request}」 {name}: only {share:.0%} of its lines are "
                        "Japanese - the side that already worked has moved"
                    )
            elif japanese:
                failures.append(
                    f"「{request}」 {name}: {share:.0%} of its lines are Japanese, "
                    "wanted an English one"
                )
            else:
                english_right += 1
            readings.append(f"{'JA' if wants_japanese else 'EN'} {name} {share:.0%}")

    return ProjectFilesResult(
        # Zero when the Japanese side has moved, so a gain on one side can
        # never pay for a loss on the other.
        files_in_the_right_language=english_right if japanese_held else 0,
        files_total=len(EXPECTED_FILES),
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )
