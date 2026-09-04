"""Does the answer show an identical excerpt once, not once per source?

C-1241: when two files carry the same passage (a TODO copied into a cycle
report), retrieval hands back two blocks with identical text and the answer
printed the paragraph under [S1] and again under [S2] - the reader reads it
twice and it reads as two independent findings. The echo answer now shows the
full excerpt once and points a later duplicate back to where it appeared, while
the footer still lists every source (both files do carry it).

The checks drive the echo backend with crafted DATA blocks - two identical, one
distinct - and confirm the excerpt appears once, the duplicate is noted, the
distinct block keeps its own text, the footer lists all three, and the note
follows the question's language.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerDedupeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _block(label: str, citation: str, content: str) -> str:
    return (
        f"<<<SIDRA_DATA_BLOCK {label}>>>\n"
        f"source: {citation}\n"
        "trust: DATA\n"
        "content:\n"
        f"{content}\n"
        f"<<<END_SIDRA_DATA_BLOCK {label}>>>"
    )


def _answer(question: str, blocks: list[str]) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    req = GenerationRequest(
        system_prompt="",
        user_message=question,
        data_context="\n".join(blocks),
    )
    return EchoModelAdapter().generate(req).text


def evaluate_answer_dedupes_identical_excerpts() -> AnswerDedupeResult:
    checks = 0
    failures: list[str] = []

    dup = "要判断の項目は人が決めるまで着手しない方針である。"
    distinct = "検査エンジンは 1 回で 1GB のメモリを使う。"
    blocks = [
        _block("S1", "repo@x:TODO.md", dup),
        _block("S2", "repo@x:cycle-report.md", dup),
        _block("S3", "repo@x:README.md", distinct),
    ]
    ans = _answer("outreach の方針は？", blocks)

    # 1: the duplicated excerpt text appears only once in the body.
    if ans.count(dup) == 1:
        checks += 1
    else:
        failures.append(f"the shared excerpt appears {ans.count(dup)}x (expected 1)")

    # 2: the second source points back to the first instead of repeating it.
    if "S1 と同じ内容" in ans:
        checks += 1
    else:
        failures.append("the duplicate source does not note it shares S1's text")

    # 3: the distinct excerpt is still shown in full.
    if distinct in ans:
        checks += 1
    else:
        failures.append("the distinct source lost its excerpt")

    # 4-6: the footer still lists every source (both duplicates and the distinct).
    footer = ans.rsplit("\n", 1)[-1]
    for label in ("[S1]", "[S2]", "[S3]"):
        if label in footer:
            checks += 1
        else:
            failures.append(f"footer missing {label}")

    # 7: an English question gets an English note, not the Japanese one.
    en = _answer("what is the policy", blocks)
    if "same text as S1" in en and "と同じ内容" not in en:
        checks += 1
    else:
        failures.append("the duplicate note does not follow the question's language")

    # 8: two DISTINCT excerpts are both shown (no false dedup).
    two_distinct = _answer(
        "検査エンジンは？",
        [
            _block("S1", "repo@x:a.md", distinct),
            _block("S2", "repo@x:b.md", "レート制限は 6 バーストに設定した。"),
        ],
    )
    if distinct in two_distinct and "レート制限は 6 バーストに設定した。" in two_distinct:
        checks += 1
    else:
        failures.append("distinct excerpts were wrongly collapsed")
    if "同じ内容" not in two_distinct:
        checks += 1
    else:
        failures.append("a same-text note fired for distinct excerpts")

    return AnswerDedupeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=9,
        failures=tuple(failures),
    )
