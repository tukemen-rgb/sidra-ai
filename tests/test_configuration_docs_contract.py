from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "src" / "sidra_ai" / "config" / "settings.py"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
SECURITY_DOC_PATH = ROOT / "docs" / "SECURITY.md"
ENV_ASSIGNMENT = re.compile(r"^(SIDRA_[A-Z0-9_]+)\s*=")
_ENV_HELPERS = {"_env_bool", "_env_int", "_env_list"}


def _literal_sidra_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if node.value.startswith("SIDRA_"):
            return node.value
    return None


def _settings_tree() -> ast.Module:
    return ast.parse(SETTINGS_PATH.read_text(encoding="utf-8"))


def _settings_environment_names() -> set[str]:
    """Collect environment names consumed by Settings without importing it."""

    tree = _settings_tree()
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue

        name = _literal_sidra_name(node.args[0])
        if name is None:
            continue

        if isinstance(node.func, ast.Name) and node.func.id in _ENV_HELPERS:
            names.add(name)
            continue

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
        ):
            names.add(name)
            continue

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            names.add(name)

    return names


def _settings_integer_constant(name: str) -> int:
    for node in _settings_tree().body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
            return node.value.value
    raise AssertionError(f"Settings constant {name} was not found as an integer literal")


def _documented_environment_names() -> set[str]:
    names: set[str] = set()
    for raw in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        candidate = raw.strip()
        if candidate.startswith("#"):
            candidate = candidate[1:].strip()
        match = ENV_ASSIGNMENT.match(candidate)
        if match:
            names.add(match.group(1))
    return names


def test_env_example_documents_every_settings_environment_input() -> None:
    consumed = _settings_environment_names()
    documented = _documented_environment_names()

    missing = sorted(consumed - documented)

    assert consumed, "Settings environment scan unexpectedly found no SIDRA_* inputs"
    assert not missing, (
        ".env.example is missing Settings environment inputs: " + ", ".join(missing)
    )


def test_env_example_documents_public_bind_token_floor() -> None:
    floor = _settings_integer_constant("MIN_PUBLIC_API_TOKEN_CHARS")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert f"at least {floor} visible ASCII characters" in env_example


def test_security_doc_describes_current_quarantine_retention_boundary() -> None:
    security_doc = SECURITY_DOC_PATH.read_text(encoding="utf-8")

    assert "`QUARANTINE` | kept out of the index" in security_doc
    assert "only sanitized review content plus minimized audit provenance" in security_doc
    assert "Uninspected\n`path`, `commit_sha`, `license`, `url`, `author`, and `extra` values" in security_doc
    assert "Finding evidence never carries raw surrounding text" in security_doc
    assert "PII and low-entropy/unknown secret classes are fingerprint-free" in security_doc
    assert "`QUARANTINE` | kept in full" not in security_doc
