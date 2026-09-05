"""When a citation excerpt is clipped, does it say so?

C-1264: a chunk longer than ``MAX_CITATION_EXCERPT_CHARS`` came back as a bare
200-character slice - 「…第8条 返金は購」 - cut mid-word with no sign it was
clipped, so the excerpt read as broken data. The answer body shows the whole
chunk; only the structured excerpt was silently truncated. It now carries a 「…」
where it drops the head or the tail of the chunk, stays within the cap, and a
chunk that fits is returned unchanged.

The checks call ``citation_excerpt`` directly (the documented, shared path) over
a long chunk (head at 0, tail clipped), a long chunk whose match is on a later
line (head clipped too), and a short chunk (nothing clipped).
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS

_ELLIPSIS = "…"


@dataclass(frozen=True)
class CitationExcerptTruncationResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_citation_excerpt_marks_truncation() -> CitationExcerptTruncationResult:
    from sidra_ai.api.citations import citation_excerpt
    from sidra_ai.security.output_guard import OutputGuard

    guard = OutputGuard()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A long single-line chunk: window opens at the head, tail is clipped.
    long_head = "返金方針について。" + "".join(
        f"第{i}条 返金は購入後 14 日以内に限り受け付ける。" for i in range(1, 14)
    )
    ex_head, _ = citation_excerpt(long_head, guard, query="返金")
    add(ex_head.endswith(_ELLIPSIS), f"tail-clipped excerpt has no 「…」: 「{ex_head[-16:]}」")
    add(not ex_head.startswith(_ELLIPSIS), "head was not clipped but a leading 「…」 was added")
    add(len(ex_head) <= MAX_CITATION_EXCERPT_CHARS,
        f"excerpt over the cap: {len(ex_head)}")

    # A long multi-line chunk whose only match is on a later line: the window
    # moves down, so the head is clipped too and must be marked.
    lines = ["冒頭の無関係な行です。" * 3]
    lines += [f"段落{i}: 一般的な説明が続きます。" * 2 for i in range(1, 12)]
    lines += ["ペンギンの飼育方法についてここで詳しく述べます。" * 3]
    lines += [f"末尾{i}: さらに説明が続きます。" * 2 for i in range(1, 12)]
    long_mid = "\n".join(lines)
    ex_mid, _ = citation_excerpt(long_mid, guard, query="ペンギン")
    add(ex_mid.startswith(_ELLIPSIS), f"head-clipped excerpt has no leading 「…」: 「{ex_mid[:16]}」")
    add(len(ex_mid) <= MAX_CITATION_EXCERPT_CHARS, f"mid excerpt over the cap: {len(ex_mid)}")

    # A short chunk fits: returned unchanged, no 「…」 added at either end.
    short = "料金プランは無料・スタンダード・プロの 3 種類です。"
    ex_short, _ = citation_excerpt(short, guard, query="料金")
    add(ex_short == short, f"a chunk that fits was altered: 「{ex_short}」")

    return CitationExcerptTruncationResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=6,
        failures=tuple(failures),
    )


__all__ = [
    "CitationExcerptTruncationResult",
    "evaluate_citation_excerpt_marks_truncation",
]
