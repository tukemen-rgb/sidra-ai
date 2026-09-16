"""Does an instruction that happens to name a feature still get carried out?

C-1878. The service answers questions about the page this conversation just
made (C-1866) by matching four feature cues - 共有 / 今日の挑戦 / 見た目 /
記録 - anywhere in the message. Those are ordinary words, the branch sits 240
lines in front of the revision branch, and it never asked whether the message
was a question. So:

* 「さっきのゲームの今日の挑戦をオフにして」 - already parsed into
  ``{'daily': 'off'}`` two lines earlier - came back as a description of the
  daily challenge, and nothing was changed;
* 「タイトルを『共有の記録』にして」 came back as a description of the copy
  button, and the rename never happened.

Five of the six phrasings measured on 2026-09-16 02:05 never reached the
reviser and wrote no version, while ``CHANGEABLE`` goes on promising that
今日の挑戦 is one of the things a revision can change. The only one that
worked was the one whose new title contained no feature word.

**Both directions are measured here, and the second is not decoration.** A
judge that only asked 「is the instruction carried out」 would be passed
outright by deleting the branch - and that branch is C-1866's fix for six
phrasings that used to be answered with 「対象リポジトリの取り込みを管理者に
依頼してください」. A judge that only asked 「is the question answered」 is the
product as it was this morning. The line between them is what this measures,
so it runs the real ``SidraService`` on both sides of it: the defect was
invisible to a check on ``detect_revision_intent``, which had the right answer
all along and was never consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.models.echo import EchoModelAdapter

#: The request every cell starts from.
MADE = "レースゲームを作って"

#: Instructions that carry a feature cue. ``expect`` is the adjustment the
#: detector reads, and ``版`` says whether a new version is due - 「今日の挑戦を
#: オフにして」 lands on the panel's own default, so the honest outcome is
#: 「変更なし」 from the REVISER, which is a different thing from never
#: reaching it.
INSTRUCTIONS: tuple[tuple[str, str, bool], ...] = (
    ("さっきのゲームの今日の挑戦をオフにして", "daily", False),
    ("さっきのゲームの日替わりをオンにして", "daily", True),
    ("さっきのゲームのタイトルを「共有の記録」にして", "title", True),
    ("さっきのゲームのタイトルを「今日の挑戦」にして", "title", True),
    ("さっきのゲームのタイトルを「見た目の記録」にして", "title", True),
    ("さっきのゲームのタイトルを「自己ベストの道」にして", "title", True),
)

#: Questions about the same features, which must keep C-1866's answer. The
#: word each one must find its way to is part of the cell: an answer that
#: merely refuses with the right code is not an answer.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("さっきのゲームの今日の挑戦ってなに", "今日の挑戦"),
    # 「共有」, not 「結果のコピー」: the share cues are 自慢/コピーし/共有/
    # シェア/…, so the noun form of the page's own button label reaches the
    # corpus wall instead - measured on 2026-09-16 and true before this item
    # touched anything, so it is filed rather than quietly fixed here.
    ("さっきのゲームの共有ってできるの", "結果をコピー"),
    ("さっきのゲームの自己ベストは残るの", "自己ベスト"),
    ("さっきのゲームの見た目は選べるの", "配色"),
)

_FEATURE_REFUSAL = "artifact_feature_question"


@dataclass(frozen=True)
class RevisionInstructionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    carried_out: int = 0
    answered: int = 0


class _Talk:
    """One service, one made game, and the history that points 「さっきの」 at it."""

    def __init__(self) -> None:
        # Through the shared helper, so the run cleans up after itself
        # (C-1770: judges reaching straight for mkdtemp left 30G in /tmp).
        self.dir = scratch_dir("sidra-revision-instruction-")
        self.service = SidraService(Settings(data_dir=self.dir), model=EchoModelAdapter())
        self.history: list[dict[str, str]] = []
        self.say(MADE)

    def say(self, message: str) -> dict:
        reply = self.service.chat(message, history=list(self.history))
        self.history.append({"role": "user", "content": message})
        self.history.append({"role": "assistant", "content": reply.get("answer", "")})
        return reply

    def pages(self) -> dict[str, Path]:
        """Written pages by name. The generator picks the sub-directory, so
        the path is kept rather than rebuilt from ``self.dir``."""

        return {p.name: p for p in Path(self.dir).rglob("game-*.html")}


def evaluate_revision_instruction_is_not_a_question() -> RevisionInstructionResult:
    checks = 0
    failures: list[str] = []
    carried_out = 0
    answered = 0

    for message, field, writes_version in INSTRUCTIONS:
        # A fresh conversation per instruction: a rename changes what
        # 「さっきのゲーム」 resolves to, so sharing one would measure the
        # order of this list as much as the product.
        talk = _Talk()
        before = talk.pages()
        reply = talk.say(message)
        label = message[len("さっきのゲームの") :]

        if reply.get("refusal") == _FEATURE_REFUSAL:
            failures.append(f"「{label}」: answered as a question about the page")
            continue
        checks += 1

        # The reviser ran and read the same field the detector did. Comparing
        # against the detector rather than a literal keeps this honest if the
        # vocabulary grows: the failure being measured is the instruction not
        # arriving, not a particular spelling.
        wanted = detect_revision_intent(message).adjustments
        got = (reply.get("creation") or {}).get("revision") or {}
        if got == wanted and field in got:
            checks += 1
            carried_out += 1
        else:
            failures.append(f"「{label}」: reviser got {got}, detector read {wanted}")

        after = talk.pages()
        made = {name: path for name, path in after.items() if name not in before}
        if bool(made) == writes_version:
            checks += 1
        else:
            failures.append(
                f"「{label}」: {'no new version' if writes_version else 'a version for nothing'}"
            )
        if writes_version and made and field == "title":
            title = wanted["title"]
            page = made[sorted(made)[-1]].read_text(encoding="utf-8")
            if f"<title>{title}</title>" in page:
                checks += 1
            else:
                failures.append(f"「{label}」: the new page is not titled {title}")

    # The other side of the line. Same four features, asked about rather than
    # changed - this is C-1866's own guarantee, kept where it can be seen
    # next to the fix that could have removed it.
    asking = _Talk()
    for message, word in QUESTIONS:
        reply = asking.service.chat(message, history=list(asking.history))
        label = message[len("さっきのゲームの") :]
        if reply.get("refusal") != _FEATURE_REFUSAL:
            failures.append(f"「{label}」: no longer answered as a feature question")
            continue
        checks += 1
        if word in reply.get("answer", ""):
            checks += 1
            answered += 1
        else:
            failures.append(f"「{label}」: the answer never says 「{word}」")

    return RevisionInstructionResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        carried_out=carried_out,
        answered=answered,
    )


__all__ = [
    "INSTRUCTIONS",
    "QUESTIONS",
    "RevisionInstructionResult",
    "evaluate_revision_instruction_is_not_a_question",
]
