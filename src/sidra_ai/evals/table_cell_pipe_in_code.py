"""Does ``plain_text`` keep a table cell whole when it holds a pipe?

C-1867, a follow-through to C-1226/C-1865. ``_flatten_table_row`` split cells on
every 「|」 with ``str.split("|")``, so a pipe that a Markdown renderer never
treats as a column break split one cell into several and shifted the rest under
the wrong header:

* a pipe inside an inline-code span - 「| `ps aux | grep x` | 説明 |」, the shape a
  CLI-reference table takes - became three cells (「ps aux / grep x / 説明」)
  against a two-column header; and
* an escaped 「\\|」, also literal, split the same way.

``_flatten_table_row`` now splits with ``_split_table_cells``, which tracks
backtick spans and honours 「\\|」, so a code pipe stays inside its cell and the
row keeps its columns. The empty-cell fix (C-1865) is unaffected.

Tested on ``plain_text`` directly - the single flattener every surface shares.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import plain_text

#: (input, expected). A pipe inside inline code or escaped stays literal content
#: inside one cell; a blank cell still holds its slot (C-1865); an ordinary table
#: and a non-table pipe line are unchanged.
_CASES: tuple[tuple[str, str], ...] = (
    ("| `ps aux | grep x` | 説明 |", "ps aux | grep x / 説明；"),
    ("| コマンド | 説明 |\n|---|---|\n| `ps aux | grep x` | プロセス検索 |\n| `ls` | 一覧 |",
     "コマンド / 説明； ps aux | grep x / プロセス検索； ls / 一覧；"),
    ("| x \\| y | z |", "x | y / z；"),
    ("| A |  | 100 |", "A / / 100；"),
    ("| 項目 | 値 |\n|---|---|\n| 売上 | 1,234 |", "項目 / 値； 売上 / 1,234；"),
    ("パイプ | を含む | 文章だが表ではない", "パイプ | を含む | 文章だが表ではない"),
)


@dataclass(frozen=True)
class TableCellPipeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_table_cell_pipe_in_code() -> TableCellPipeResult:
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

    # Guards, phrased as the failure a reader hits: a code/escaped pipe must not
    # become a cell break.
    one = plain_text("| `ps aux | grep x` | 説明 |")
    add("ps aux / grep x" not in one, f"code pipe became a cell break: {one!r}")
    multi = plain_text(_CASES[1][0])
    add("ps aux / grep x /" not in multi, f"the CLI row re-columned: {multi!r}")
    esc = plain_text("| x \\| y | z |")
    add("x / y" not in esc, f"escaped pipe became a cell break: {esc!r}")

    total = len(_CASES) + 3
    return TableCellPipeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["TableCellPipeResult", "evaluate_table_cell_pipe_in_code"]
