"""Does ``plain_text`` keep an empty table cell so columns stay aligned?

C-1865, a follow-through to C-1226 (which flattens a Markdown table's cells with
「 / 」). ``_flatten_table_row`` dropped empty cells (「cell for cell in cells if
cell」), so a row with a blank interior cell lost it and every cell after it
shifted one column left. Measured: with the header 「名前 / 状態 / 値」, the row
「| A |  | 100 |」 flattened to 「A / 100」, so 100 - really the 値 - lines up under
状態, while the sibling row 「| B | 稼働 | 5 |」 kept all three. A flattened table
that silently re-columns one row is worse than a bar-walled one, because the
reader cannot see it happened.

``_flatten_table_row`` now keeps every cell, empty ones included, so the blank
holds its place; an all-empty row still collapses to nothing.

Tested on ``plain_text`` directly - the single flattener every surface shares.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import plain_text

#: (input, expected). The blank cell holds its slot (shown as an empty run
#: between 「 / 」 separators); an all-empty row is nothing; a table with no blank
#: cell is unchanged, and a non-table pipe line is left alone.
_CASES: tuple[tuple[str, str], ...] = (
    ("| A |  | 100 |", "A / / 100；"),
    ("| 名前 | 状態 | 値 |\n|---|---|---|\n| A |  | 100 |\n| B | 稼働 | 5 |",
     "名前 / 状態 / 値； A / / 100； B / 稼働 / 5；"),
    ("|  | 有 |", "/ 有；"),
    ("| Y |  |", "Y / ；"),
    ("|  |  |", ""),
    ("| 項目 | 値 |\n|---|---|\n| 売上 | 1,234 |", "項目 / 値； 売上 / 1,234；"),
    ("パイプ | を含む | 文章だが表ではない", "パイプ | を含む | 文章だが表ではない"),
)


@dataclass(frozen=True)
class TableEmptyCellResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_table_row_keeps_empty_cells() -> TableEmptyCellResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for raw, expected in _CASES:
        got = plain_text(raw)
        add(got == expected, f"plain_text({raw!r}) = {got!r} != {expected!r}")

    # Alignment guards, phrased as the failure a reader would actually hit.
    aligned = plain_text("| A |  | 100 |")
    add("A / / 100" in aligned, f"blank interior cell was dropped: {aligned!r}")
    multi = plain_text(_CASES[1][0])
    add("A / 100；" not in multi, f"the A row re-columned (100 under 状態): {multi!r}")
    add(multi.count("；") == 3, f"row count wrong (want 3 rows): {multi!r}")

    total = len(_CASES) + 3
    return TableEmptyCellResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["TableEmptyCellResult", "evaluate_table_row_keeps_empty_cells"]
