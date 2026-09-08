"""The runbooks are instructions for someone who cannot ask a question.

The owner follows these alone, on his own machine, after weeks away. A command
that has been renamed, a flag that was dropped, an environment variable that
became something else - each is an evening lost to a document that reads
perfectly and does not work. Nothing checked them until now; they currently
all pass, which is the right moment to pin that rather than the wrong one.

What is checked is only what the document tells him to *type*: environment
variables it names, scripts and modules it invokes, console commands it uses,
and the flags it passes to each. Prose is left alone on purpose - the coder
swap runbook describes a `scripts/check_code_generation.py` it explicitly
labels 「案。実装はしていない」, and a guard that could not tell a proposal from
an instruction would either fail on honest writing or be switched off.

The seam is the shape of the line: a reference is an instruction when it
follows ``py`` or ``python``, or is a console command in a code fence. That is
also the shape the owner's fingers follow.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: Documents whose commands a person is expected to run as written.
RUNBOOKS = (
    ROOT / "docs" / "RUNBOOK_FIRST_REAL_ANSWER.md",
    ROOT / "docs" / "RUNBOOK_CODER_MODEL_SWAP.md",
    ROOT / "docs" / "LOCAL_RUNTIME.md",
)

#: Commands that are not ours to verify. Their flags belong to somebody else.
FOREIGN = {"pip", "pytest", "venv", "ensurepip"}

#: `sidra-ai` is the package and the checkout directory, not a command.
NOT_A_COMMAND = {"sidra-ai"}

_INVOCATION = re.compile(
    r"(?:py|python|python3)\s+(scripts[\\/][A-Za-z0-9_]+\.py|-m\s+[A-Za-z0-9_.]+)([^\n`]*)"
)
_CONSOLE = re.compile(r"\bsidra-[a-z]+")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _console_scripts() -> dict[str, str]:
    data = tomllib.loads(_text(ROOT / "pyproject.toml"))
    return dict(data.get("project", {}).get("scripts", {}))


def _declared_flags(source_path: Path) -> set[str]:
    """Every ``--flag`` the file's argparse accepts.

    Read from the syntax tree rather than by pattern: ``add_argument`` is
    routinely split across lines, and a regex over ``add_argument("--`` missed
    ``sidra-api --check`` for exactly that reason while this was being written
    - which briefly looked like a broken runbook and was not.
    """

    flags: set[str] = set()
    tree = ast.parse(_text(source_path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (isinstance(function, ast.Attribute) and function.attr == "add_argument"):
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value.startswith("--"):
                    flags.add(argument.value)
    return flags


def _module_path(dotted: str) -> Path | None:
    candidate = ROOT / "src" / Path(*dotted.split("."))
    if candidate.with_suffix(".py").exists():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").exists():
        return candidate / "__init__.py"
    return None


def _invocations() -> list[tuple[Path, str, str]]:
    """(runbook, target, the rest of the command line) for each instruction."""

    found: list[tuple[Path, str, str]] = []
    for book in RUNBOOKS:
        for target, rest in _INVOCATION.findall(_text(book)):
            found.append((book, " ".join(target.split()), rest))
    return found


# --------------------------------------------------------------------------


def test_the_extractor_finds_the_commands_at_all() -> None:
    """Guard the guard: a regex that matches nothing passes everything."""

    invocations = _invocations()
    assert len(invocations) >= 8, (
        f"only {len(invocations)} commands found across {len(RUNBOOKS)} runbooks - "
        "the extractor is probably not matching what the documents contain"
    )
    targets = {target for _, target, _ in invocations}
    assert any(t.endswith(".py") for t in targets), "no script invocations found"
    assert any(t.startswith("-m ") for t in targets), "no module invocations found"


def test_every_environment_variable_named_is_one_the_code_reads() -> None:
    settings_source = _text(ROOT / "src" / "sidra_ai" / "config" / "settings.py")
    known = set(re.findall(r"""["'](SIDRA_[A-Z0-9_]+)["']""", settings_source))
    assert known, "no variables found in settings.py - this test is not reading it"

    for book in RUNBOOKS:
        named = set(re.findall(r"SIDRA_[A-Z0-9_]+", _text(book)))
        unknown = sorted(named - known)
        assert not unknown, (
            f"{book.name} tells the operator to set {unknown}, which "
            "config/settings.py does not read"
        )


def test_every_script_and_module_it_runs_exists() -> None:
    for book, target, _ in _invocations():
        if target.startswith("-m "):
            dotted = target[3:].strip()
            if dotted.split(".")[0] in FOREIGN:
                continue
            assert _module_path(dotted) is not None, (
                f"{book.name} runs `python -m {dotted}`, which is not in src/"
            )
        else:
            script = ROOT / target.replace("\\", "/")
            assert script.exists(), f"{book.name} runs {target}, which does not exist"


def test_every_console_command_it_names_is_installed() -> None:
    entry_points = _console_scripts()
    assert entry_points, "pyproject declares no console scripts"

    for book in RUNBOOKS:
        for name in sorted(set(_CONSOLE.findall(_text(book)))):
            if name in NOT_A_COMMAND:
                continue
            assert name in entry_points, (
                f"{book.name} uses `{name}`, which pyproject does not install"
            )


def test_every_flag_it_passes_is_one_that_command_accepts() -> None:
    """The quietest way a runbook rots: the command survives, the flag does not."""

    checked = 0
    for book, target, rest in _invocations():
        if target.startswith("-m "):
            dotted = target[3:].strip()
            if dotted.split(".")[0] in FOREIGN:
                continue
            source = _module_path(dotted)
        else:
            source = ROOT / target.replace("\\", "/")
        if source is None or not source.exists():
            continue  # named by another test
        used = set(re.findall(r"(--[a-z][a-z0-9-]*)", rest))
        if not used:
            continue
        declared = _declared_flags(source)
        checked += 1
        unknown = sorted(used - declared)
        assert not unknown, (
            f"{book.name} passes {unknown} to {target}, which accepts "
            f"{sorted(declared) or 'no flags'}"
        )
    assert checked, "no command in any runbook was passed a flag - check the regex"


def test_console_command_flags_are_checked_too() -> None:
    """`sidra-api --check` is in the acceptance criteria; it has to be real."""

    entry_points = _console_scripts()
    for book in RUNBOOKS:
        for line in _text(book).splitlines():
            stripped = line.strip().lstrip("> ").strip()
            match = re.match(r"^(sidra-[a-z]+)\s+(.*)$", stripped)
            if not match:
                continue
            name, rest = match.group(1), match.group(2)
            if name not in entry_points:
                continue  # named by the test above
            used = set(re.findall(r"(--[a-z][a-z0-9-]*)", rest))
            if not used:
                continue
            module = entry_points[name].split(":")[0]
            source = _module_path(module)
            assert source is not None, f"{name} points at {module}, which is not in src/"
            unknown = sorted(used - _declared_flags(source))
            assert not unknown, (
                f"{book.name} runs `{name} {' '.join(sorted(used))}`, but {name} "
                f"accepts {sorted(_declared_flags(source)) or 'no flags'}"
            )
