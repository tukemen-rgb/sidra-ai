"""No Python source may carry an invalid escape sequence.

Found on the owner's PC (2026-09-20, Python 3.12): importing the ask page
printed ``SyntaxWarning: invalid escape sequence '\\d'`` because a JavaScript
regex had been pasted into a non-raw Python string. Python 3.12 only warns, a
future version refuses to import, and the CI container (3.11) said nothing -
so the warning could only ever be seen on the machine the product is for.

This compiles every module with every warning promoted to an error, so the
next pasted regex fails here instead of on the owner's screen. Every warning,
not only SyntaxWarning: on Python 3.11 (the CI container) an invalid escape is
still a DeprecationWarning, and a filter naming SyntaxWarning let the very
bug this test was written for pass on the first try.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "scripts").rglob("*.py"))


@pytest.mark.parametrize("module", MODULES, ids=lambda p: str(p.relative_to(ROOT)))
def test_module_compiles_without_syntax_warnings(module: Path) -> None:
    source = module.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compile(source, str(module), "exec")
