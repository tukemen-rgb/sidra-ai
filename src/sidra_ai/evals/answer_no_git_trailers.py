"""Do commit-message git trailers stay out of the answer body?

C-1221: commits are nearly half the indexed corpus and every one ends with
git/AI trailers (Co-Authored-By, Claude-Session, ...). The echo lead
extractor pulled them in as content, so an answer about a commit ended
「…方針を維持。 Co-Authored-By: Claude … Claude-Session: https://…」 - git
plumbing shown as substance, exposing an authorship address and the shape
of a session URL. ``plain_text`` now drops the known trailer lines, so the
answer body and generated artifacts are clean while the raw citation
excerpt (which does not pass through ``plain_text``) stays verbatim for
review.

The checks drive the echo model over a data block whose content is a real
commit message with a trailer block, plus a content line that merely starts
with a colon-word, and confirm the trailer is gone while the content and the
colon-word line survive.
"""

from __future__ import annotations

from dataclasses import dataclass

# One body sentence, then the trailer block. The lead takes the first two
# informative sentences, so with the trailer present the second one *is* the
# trailer - the exact shape that put 「Co-Authored-By: …」 into the real answer
# for commit 40cbed2. Strip it and the lead is just the body sentence.
_COMMIT_BLOCK = (
    "AdSense は見送り、検索経由 500PV/日 で再検討と記録する方針を社長が"
    "決めたので広告収益はスポンサー枠とアフィリエイトで作る方針を維持する。\n"
    "\n"
    "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n"
    "Claude-Session: https://claude.ai/code/session_deadbeef\n"
    "Signed-off-by: Someone Else <someone@example.com>"
)


@dataclass(frozen=True)
class AnswerNoGitTrailersResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _answer_over(content: str) -> str:
    from sidra_ai.models.base import GenerationRequest
    from sidra_ai.models.echo import EchoModelAdapter

    block = (
        "<<<SIDRA_DATA_BLOCK S1>>>\n"
        "source: tukemen-rgb/site@40cbed2:commit/40cbed23a73d\n"
        "trust: retrieved-data\n"
        f"content:\n{content}\n"
        "<<<END_SIDRA_DATA_BLOCK S1>>>"
    )
    return EchoModelAdapter().generate(
        GenerationRequest(system_prompt="", user_message="AdSense の決定は", data_context=block)
    ).text


def evaluate_answer_no_git_trailers() -> AnswerNoGitTrailersResult:
    answer = _answer_over(_COMMIT_BLOCK)

    checks = 0
    failures: list[str] = []

    for token in ("Co-Authored-By", "Claude-Session", "Signed-off-by"):
        if token not in answer:
            checks += 1
        else:
            failures.append(f"answer still shows the {token} trailer")

    # The authorship address and the session-URL shape must not ride along.
    if "noreply@anthropic.com" not in answer:
        checks += 1
    else:
        failures.append("answer leaks the co-author address")

    # The substance is still there.
    if "スポンサー枠" in answer:
        checks += 1
    else:
        failures.append("trailer stripping took the content with it")

    # A content line that merely starts with a colon-word survives the strip
    # itself - checked at plain_text, since the two-sentence answer lead would
    # not reach a third line for its own reasons. The removal is an allowlist,
    # not a blanket 「Word: value」 rule.
    from sidra_ai.creation.evidence import plain_text

    flattened = plain_text("影響: 文書のみの変更。\nTODO: あとで見直す。")
    if "影響:" in flattened and "TODO:" in flattened:
        checks += 1
    else:
        failures.append("a content line starting with a colon-word was dropped")

    return AnswerNoGitTrailersResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
