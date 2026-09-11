"""Does the chunker avoid splitting a code fence at its ``#`` comment lines?

C-1688. ``_split_on_headings`` found headings with ``^#{1,6}\\s+`` over the whole
document, blind to code fences. A fenced block of bash/python/yaml/Dockerfile
whose lines start with ``#`` (comments) was cut at every comment line, so a
README's setup steps were fragmented across chunks - ``npm install`` torn from
the sentence that introduces it, and the opening/closing fences orphaned. The
chunker now tracks ```````/``~~~`` fences and treats a ``#`` line
inside one as content, not a heading.

The checks drive the real ``chunk_document`` and confirm a fenced block stays in
one chunk, that real headings outside a fence still split (no regression), that
a heading after the fence closes splits again, and that malformed fences do not
crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _doc(content: str):
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel

    prov = Provenance(
        source="github", repository="acme/handbook", path="README.md",
        commit_sha="abc1234", timestamp=datetime.now(timezone.utc),
        source_type=SourceType.DOCS, trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    return Document(content=content, provenance=prov)


@dataclass(frozen=True)
class ChunkerFenceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chunker_ignores_headings_in_code_fences() -> ChunkerFenceResult:
    from sidra_ai.retrieval.chunker import chunk_document

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def texts(content: str) -> list[str]:
        return [c.content for c in chunk_document(_doc(content))]

    fenced = (
        "# 設定手順\n\n次のスクリプトを実行します。\n\n"
        "```bash\n# 依存をインストール\nnpm install\n# ビルド\nnpm run build\n```\n\n"
        "以上で完了です。"
    )

    # --- (A) the fenced block is not split at its `#` comment lines ---
    ch = texts(fenced)
    add(any("npm install" in c and "npm run build" in c for c in ch),
        f"A: the code fence was split at a `#` comment line (chunks={len(ch)})")

    # --- (B) real headings outside any fence still split (no regression) ---
    two = "# 見出しA\n\n本文あ\n\n# 見出しB\n\n本文い"
    ch_two = texts(two)
    add(any(c.startswith("# 見出しA") for c in ch_two)
        and any(c.startswith("# 見出しB") for c in ch_two)
        and len(ch_two) >= 2,
        f"B: real headings outside a fence stopped splitting (chunks={len(ch_two)})")

    # --- (C) a heading after the fence closes splits again (state resets) ---
    after = (
        "# 設定\n\n```bash\nnpm install\n```\n\n# 次の章\n\n本文"
    )
    ch_after = texts(after)
    add(any("次の章" in c and "npm install" not in c for c in ch_after),
        f"C: a heading after a closed fence did not split (chunks={len(ch_after)})")

    # --- (D) ~~~ fences are protected too (content on both sides of the
    #         comment must stay in one chunk) ---
    tilde = "# 手順\n\n~~~yaml\nsetting: enabled\n# コメント\nkey: value\n~~~\n\n完了"
    ch_tilde = texts(tilde)
    add(any("setting: enabled" in c and "key: value" in c for c in ch_tilde),
        f"D: a ~~~ fence was split at a `#` comment line (chunks={len(ch_tilde)})")

    # --- (E) a command stays with the sentence that introduces it ---
    add(any("次のスクリプトを実行します" in c and "npm install" in c for c in ch),
        "E: the command was torn from its introducing sentence")

    # --- (F) malformed fences (unclosed / repeated) do not crash ---
    crashed = None
    try:
        n1 = len(texts("# タイトル\n\n```bash\nnpm install\n(閉じ忘れ)"))
        n2 = len(texts("```\na\n```\n```\nb\n```"))
        ok = n1 >= 1 and n2 >= 1
    except Exception as exc:  # noqa: BLE001 - robustness check
        crashed = f"{type(exc).__name__}: {exc}"
        ok = False
    add(ok, f"F: a malformed fence crashed the chunker: {crashed}")

    total = 6
    return ChunkerFenceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ChunkerFenceResult",
    "evaluate_chunker_ignores_headings_in_code_fences",
]
