"""The twenty questions the owner would actually ask, in the repository.

On 2026-08-26 someone sat down as the owner of SIDRA STUDIO, wrote twenty
questions, ran them against the real five-repository index, and read every
result by hand. The tally survived in ``docs/OUTCOMES.md`` - 7 correct, 5
partial, 7 wrong, 1 unanswerable. **The questions did not.** So the number
could never be recomputed: nobody could tell whether a change to retrieval had
moved it, and two backlog items (C-1008, C-1009) were denominated in a figure
that had no way of being produced again.

This file exists so that never happens twice. It is not a reconstruction of
that set - those questions are gone, and guessing at them from the summary
would produce something that merely looks like the original. This is a new
set, and any number it produces starts a new series.

How it was written
------------------

The order matters more than the content, so it is on the record:

1. The twenty questions were written first, from the role - what an owner asks
   about their own business - and frozen before anything was searched for.
2. Only then was the corpus read, to find where each answer lives.
3. A question with no answer in the corpus was marked ``answer_marker=None``
   and reported as unanswerable. **No question was reworded to make it pass**,
   and no document was written so that one would.

Step 3 is the one that keeps this honest, and the count of unanswerable
questions is the visible evidence of it: a set chosen to score well would have
none. This one has one - nowhere in the five repositories does anyone write
down how many people the business needs.

What this set is not
--------------------

It is **not comparable to the 2026-08-26 figures**. Different questions, so a
7 here and a 7 there are not the same seven. The judge says so on its own
output rather than trusting anyone to remember.

It is also not a replacement for
:mod:`sidra_ai.evals.outcome_questions`. That set asks what an operator needs
while using the product. This one asks what the person paying for it needs to
know, which is a different corpus, a different vocabulary, and - as the
original measurement found - a much harder one.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The five repositories the questions may be answered from.
REPOSITORIES = (
    "tukemen-rgb/sidra-ai",
    "tukemen-rgb/site",
    "tukemen-rgb/creater-yard",
    "tukemen-rgb/Fg",
    "tukemen-rgb/marketing",
)


@dataclass(frozen=True)
class BossQuestion:
    """One owner question and, if the corpus has one, the answer's fingerprint.

    ``answer_marker`` is ``None`` when the five repositories do not contain the
    answer. That is a real state, not a gap to be filled: the honest report for
    such a question is "nobody has written this down", and a retriever cannot
    be marked wrong for failing to find it. The judge keeps these out of the
    denominator and names them, so the set cannot be quietly improved by
    deleting the questions it fails.

    ``topic`` is what the owner is asking about, not where the answer lives. It
    is here so a future reader can see the set covers the business rather than
    the parts of the business that happen to be documented.
    """

    name: str
    question: str
    topic: str
    answer_marker: str | None = None
    repository: str | None = None
    #: The answer lives in sidra-ai's own documents. Kept, because the owner
    #: does ask about the tool they paid for, but tallied separately: scoring
    #: our own prose is the inside number this whole set exists to escape.
    self_grounded: bool = False


BOSS_QUESTIONS: tuple[BossQuestion, ...] = (
    BossQuestion(
        name="targets-progress",
        question="今期の目標はどこまで達成できていますか",
        topic="KPI",
        answer_marker="投稿完了率",
        repository="tukemen-rgb/Fg",
    ),
    BossQuestion(
        name="competitors",
        question="競合はどこですか",
        topic="競合",
        answer_marker="ふりーむ！ — 最大の直接競合",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="how-we-earn",
        question="どうやって収益を出しますか",
        topic="収益",
        answer_marker="2 つの経済圏",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="what-it-costs",
        question="いくらお金がかかりますか",
        topic="費用",
        answer_marker="計測できていない指標は「未計測」と書く",
        repository="tukemen-rgb/Fg",
    ),
    BossQuestion(
        name="headcount",
        question="人はいま何人必要ですか",
        topic="体制",
        # Nowhere in the five repositories. Kept exactly as written, because
        # deleting the question would hide that the business has never
        # written this down - which is a more useful thing to learn than a
        # retrieval score.
        answer_marker=None,
    ),
    BossQuestion(
        name="next-90-days",
        question="これから 90 日で何をしますか",
        topic="計画",
        answer_marker="新規投稿10本、週次アクティブプレイヤー100人",
        repository="tukemen-rgb/Fg",
    ),
    BossQuestion(
        name="who-reviews-posts",
        question="投稿された作品は誰が審査しますか",
        topic="運営",
        answer_marker="通報だけでは公開は止まらない",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="personal-data",
        question="個人情報はどう扱っていますか",
        topic="個人情報",
        answer_marker="対応完了から 180 日後に削除",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="security-posture",
        question="セキュリティはどうなっていますか",
        topic="セキュリティ",
        answer_marker="The four invariants",
        repository="tukemen-rgb/sidra-ai",
        self_grounded=True,
    ),
    BossQuestion(
        name="how-many-users",
        question="利用者は何人いますか",
        topic="実績",
        answer_marker="投稿数・利用者数・PV はここに書けない",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="creator-acquisition",
        question="クリエイターはどうやって集めますか",
        topic="供給",
        answer_marker="最初に招く人",
        repository="tukemen-rgb/creater-yard",
    ),
    BossQuestion(
        name="churn",
        question="やめてしまう人はどれくらいいますか",
        topic="継続",
        answer_marker="離脱地点のたぐいの数字はどこにも無い",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="price",
        question="価格はいくらにしますか",
        topic="価格",
        answer_marker="スポンサー枠は月 30,000 円",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="terms-of-service",
        question="利用規約は誰が作りましたか",
        topic="法務",
        answer_marker="利用規約のページは無し",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="design-direction",
        question="デザインの方針は何ですか",
        topic="ブランド",
        answer_marker="GAMEYARD Design Principles",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="partners",
        question="提携先はどこですか",
        topic="提携",
        answer_marker="Creator を応援する Creator Partner",
        repository="tukemen-rgb/creater-yard",
    ),
    BossQuestion(
        name="when-we-launch",
        question="いつ公開しますか",
        topic="公開",
        # deploy/GO-LIVE.md is the fuller answer, but the ingestion pipeline
        # does not read deploy/, so scoring against it would measure a
        # document the product cannot see. The question stands as written;
        # the marker points at the answer that is actually in the index.
        answer_marker="本番反映は今夜、社長が本番サーバーで実行",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="quality-bar",
        question="品質の基準は何ですか",
        topic="品質",
        answer_marker="プレイ開始成功率",
        repository="tukemen-rgb/Fg",
    ),
    BossQuestion(
        name="incident-response",
        question="障害が起きたらどうしますか",
        topic="障害",
        answer_marker="ConoHa の Web コンソール",
        repository="tukemen-rgb/site",
    ),
    BossQuestion(
        name="where-data-lives",
        question="データはどこに保管していますか",
        topic="保管",
        answer_marker="バックアップの外部保管は既定で無効",
        repository="tukemen-rgb/site",
    ),
)


def grounded() -> tuple[BossQuestion, ...]:
    """The questions the corpus can answer - the scoring denominator."""

    return tuple(q for q in BOSS_QUESTIONS if q.answer_marker is not None)


def headline() -> tuple[BossQuestion, ...]:
    """Grounded questions about somebody else's repository.

    Same rule as the outcome set: sidra-ai answering a question out of its own
    documents is measured, but it is not what "can SIDRA answer the owner"
    means, so it never enters the headline.
    """

    return tuple(q for q in grounded() if not q.self_grounded)
