"""Does a cited Markdown table read as prose, not a wall of bars?

C-1226: 「ページ数はいくつですか」 returned an answer whose top citation was
「実際に収集したデータ | 項目 | 値 | | --- | --- | | 収集ゲーム総数 |
21,907 件 | …」 - the README stats table, pipes and separator row and all.
``plain_text`` stripped headings, bold, lists and trailers but left table
syntax untouched, and the corpus is full of tables. The separator row is now
dropped and each row's cells are joined with 「 / 」, while a mid-sentence
「a|b」 (a pipe that is not a table) is left alone.

The checks drive the echo model over a data block whose content is a real
Markdown table and confirm the pipes and separator row are gone from the
answer while the numbers survive.
"""

from __future__ import annotations

from dataclasses import dataclass

_TABLE_BLOCK = (
    "実際に収集したデータ。\n"
    "| 項目 | 値 |\n"
    "| --- | --- |\n"
    "| 収集ゲーム総数 | 21,907 件 |\n"
    "| 生成 HTML ページ数 | 25,581 |\n"
)


@dataclass(frozen=True)
class AnswerTableFlattenedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _answer_over(content: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    block = (
        "<<<SIDRA_DATA_BLOCK S1>>>\n"
        "source: tukemen-rgb/site@0eedf95:README.md\n"
        "trust: retrieved-data\n"
        f"content:\n{content}\n"
        "<<<END_SIDRA_DATA_BLOCK S1>>>"
    )
    return EchoModelAdapter().generate(
        GenerationRequest(system_prompt="", user_message="ページ数は", data_context=block)
    ).text


def evaluate_answer_table_flattened() -> AnswerTableFlattenedResult:
    from sidra_ai.creation.evidence import plain_text

    answer = _answer_over(_TABLE_BLOCK)

    checks = 0
    failures: list[str] = []

    # The separator row must be gone entirely - not merely relabelled. Dropping
    # only the pipe-strip would flatten 「| --- | --- |」 into 「--- / ---」,
    # which is still noise, so the dashes must not survive either.
    if "---" not in answer and "| ---" not in answer:
        checks += 1
    else:
        failures.append("the table separator row is still shown")

    if "| 項目" not in answer and "項目 |" not in answer:
        checks += 1
    else:
        failures.append("table cells are still bounded by pipes")

    # The cells are still there, joined so they read as prose.
    if "項目 / 値" in answer:
        checks += 1
    else:
        failures.append("table cells were not joined into a readable phrase")

    # The numbers - the reason someone asked - survive.
    if "25,581" in answer:
        checks += 1
    else:
        failures.append("a table number was lost in flattening")

    # A pipe that is not a table stays put (checked at plain_text, since the
    # two-sentence lead would not reach a mid-body line for its own reasons).
    if plain_text("選択肢は a|b の形式") == "選択肢は a|b の形式":
        checks += 1
    else:
        failures.append("a mid-sentence pipe was mangled as a table")

    return AnswerTableFlattenedResult(
        passed=not failures, checks_passed=checks, checks_total=5,
        failures=tuple(failures),
    )
