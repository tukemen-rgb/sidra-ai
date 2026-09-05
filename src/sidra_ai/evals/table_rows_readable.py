"""Does a cited Markdown table keep its rows apart, or run them together?

C-1245: C-1226 flattened a table's cells with 「 / 」 and dropped the separator
row, but ``plain_text`` ends with ``" ".join(text.split())``, which collapses
the newlines *between* rows too. A multi-row table then reads as one run:
「項目 / 内容 運営歴 / 約20年 核 / 過去20年…」 - the 「 / 」 inside a row and the
space between rows look identical, so 「内容 運営歴」 reads as one cell and the
table cannot be parsed. Seen live in 「掲載作品数は何件か」's [S2] (the 夢現
comparison table in competitive-analysis.md).

The fix separates rows with a delimiter that survives the whitespace collapse,
so 「項目 / 内容」 and 「運営歴 / 約20年」 are visibly two rows. The checks drive
both ``plain_text`` and the echo model over a real multi-row table and confirm
the between-row run-ons are gone while the cells, the numbers and a non-table
pipe are untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A header row and two data rows. The between-row adjacencies below are the
#: run-ons a collapsed table produces.
_TABLE_BLOCK = (
    "集計。\n"
    "| 項目 | 値 |\n"
    "| --- | --- |\n"
    "| 収集ゲーム総数 | 21,907 件 |\n"
    "| 生成 HTML ページ数 | 25,581 |\n"
)

#: The two run-ons: header→row1 (「値 収集ゲーム総数」) and row1→row2
#: (「件 生成 HTML ページ数」). If either survives, the rows are not separated.
_RUN_ONS = ("値 収集ゲーム総数", "件 生成 HTML ページ数")


@dataclass(frozen=True)
class TableRowsReadableResult:
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
        GenerationRequest(system_prompt="", user_message="件数は", data_context=block)
    ).text


def evaluate_table_rows_readable() -> TableRowsReadableResult:
    from sidra_ai.creation.evidence import plain_text

    flat = plain_text(_TABLE_BLOCK)
    answer = _answer_over(_TABLE_BLOCK)

    checks = 0
    failures: list[str] = []

    # 1,2: the rows are separated by a boundary that is distinct from both the
    # space that joins prose and the 「 / 」 that joins a row's own cells -
    # otherwise a reader still cannot tell a row break from a cell break. Each
    # run-on is checked in both forms.
    for run in _RUN_ONS:
        if run not in flat and run.replace(" ", " / ", 1) not in flat:
            checks += 1
        else:
            failures.append(f"plain_text: rows not distinctly separated at 「{run}」")

    # 3: cells within a row are still joined so a row reads as one phrase.
    if "項目 / 値" in flat:
        checks += 1
    else:
        failures.append("plain_text: within-row cells not joined")

    # 4: every number - the reason someone asked - survives.
    if "21,907" in flat and "25,581" in flat:
        checks += 1
    else:
        failures.append("plain_text: a table number was lost")

    # 5,6: the same holds in the real answer the reader sees, not only in the
    # helper. The first run-on is the one a header/body table always has.
    if _RUN_ONS[0] not in answer:
        checks += 1
    else:
        failures.append("answer: header and first row run together")
    if "項目 / 値" in answer:
        checks += 1
    else:
        failures.append("answer: within-row cells not joined")

    # 7: a pipe that is not a table, and a plain sentence, are untouched - the
    # row delimiter is added only between table rows.
    if (
        plain_text("選択肢は a|b の形式") == "選択肢は a|b の形式"
        and plain_text("ふつうの文。") == "ふつうの文。"
    ):
        checks += 1
    else:
        failures.append("a non-table line was altered")

    return TableRowsReadableResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=7,
        failures=tuple(failures),
    )


__all__ = ["TableRowsReadableResult", "evaluate_table_rows_readable"]
