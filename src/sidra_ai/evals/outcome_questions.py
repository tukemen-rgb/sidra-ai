"""Real operator questions about the five allowlisted repositories.

Every other measurement in this repository scores SIDRA against material
SIDRA's authors wrote for the purpose of being scored: hand-built fixtures,
synthetic chunks, detector cases. Those answer "does the code do what we said
it does". They cannot answer "can SIDRA do its job", because nothing in them
came from outside.

These questions did. Each one is a question a SIDRA STUDIO operator could
actually ask, and each is answered by text that already exists in one of the
five repositories -- written by someone else, for another purpose, before this
file existed. ``answer_marker`` is a distinctive fragment of that text. A
question counts as answerable when the retriever surfaces a chunk containing
its marker; that is a claim about the corpus, not about our fixtures.

Adding a question is only legitimate if the answer already exists in the
corpus. Writing a document so that a question passes inverts the measurement:
the number stops describing the repositories and starts describing us.
``scripts/measure_outcomes.py`` therefore verifies every marker against the
checked-out corpus and fails if one is missing, so a question cannot quietly
become self-referential.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutcomeQuestion:
    """One operator question plus the evidence that answers it.

    ``tier`` separates two genuinely different asks:

    ``direct``
        The operator happens to use the document's own vocabulary. Retrieval
        is a lexical match and BM25 handles it.

    ``paraphrase``
        The operator asks in their own words, which is what people actually
        do. None of the question's content words appear near the answer, so
        a purely lexical retriever has nothing to match on.

    They are reported separately on purpose. A single blended figure would
    let a strong ``direct`` score hide the fact that SIDRA cannot follow an
    operator who phrases things their own way -- which is the failure mode
    that matters in use.
    """

    name: str
    question: str
    answer_marker: str
    repository: str
    tier: str = "direct"
    note: str = ""


# Ordered by repository so a gap in coverage is visible at a glance.
OUTCOME_QUESTIONS: tuple[OutcomeQuestion, ...] = (
    # --- tukemen-rgb/Fg (corporate strategy / KPI) --------------------
    OutcomeQuestion(
        name="north-star-metric",
        question="SIDRA STUDIO の北極星指標は何ですか",
        answer_marker="週次で遊ばれた投稿作品数",
        repository="tukemen-rgb/Fg",
    ),
    # The two questions below started as direct questions quoting their own
    # marker. The self-quote guard (test_question_does_not_contain_its_own_answer)
    # forced a rewording, and the rewording removed every content word the
    # marker has: measured overlap fell to inflection fragments only, with the
    # evidence at rank 9 and rank 150. A question whose vocabulary no longer
    # touches its answer is a paraphrase question in fact, whatever its label
    # says - and leaving the label wrong made the direct tier report a
    # retrieval failure that was actually a bookkeeping one.
    OutcomeQuestion(
        name="weekly-active-players-target",
        question="毎週どれだけの人に遊ばれることを目指していますか",
        answer_marker="週次アクティブプレイヤー",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="play-start-success-rate",
        question="ゲームが正しく起動する割合に目標値はありますか",
        answer_marker="プレイ開始成功率",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="perpetual-free-guardrail",
        question="永久無料や永年特典を提供してよいですか",
        answer_marker="永久無料・永年特典は将来原価を見積もれない限り提供しない",
        repository="tukemen-rgb/Fg",
    ),
    OutcomeQuestion(
        name="core-diagnosis",
        question="SIDRA STUDIO の最大の問題は開発力不足ですか",
        answer_marker="利用者のいる1つの事業へ経営資源が集中していない",
        repository="tukemen-rgb/Fg",
    ),
    OutcomeQuestion(
        name="gameyard-creatoryard-roles",
        question="次の90日で GAMEYARD と CreatorYard はそれぞれどんな役割ですか",
        answer_marker="CreatorYardを制作者の関係深化",
        repository="tukemen-rgb/Fg",
    ),
    OutcomeQuestion(
        name="positioning",
        question="大手ストアと正面から競争しますか",
        answer_marker="大手ストアとの正面競争は避けます",
        repository="tukemen-rgb/Fg",
    ),
    # --- tukemen-rgb/site (GAMEYARD) ----------------------------------
    OutcomeQuestion(
        name="paid-sales-policy",
        question="GAMEYARD で作品の有料販売はできますか",
        answer_marker="有料販売はしない",
        repository="tukemen-rgb/site",
    ),
    OutcomeQuestion(
        name="localization-policy",
        question="GAMEYARD を多言語化する予定はありますか",
        answer_marker="多言語化はしない",
        repository="tukemen-rgb/site",
    ),
    OutcomeQuestion(
        name="submission-fee",
        question="GAMEYARD への投稿に費用はかかりますか",
        answer_marker="投稿は無料",
        repository="tukemen-rgb/site",
    ),
    OutcomeQuestion(
        name="what-is-gameyard",
        question="GAMEYARD とはどういうサイトですか",
        answer_marker="ゲーム投稿サイト",
        repository="tukemen-rgb/site",
    ),

    # --- tukemen-rgb/creater-yard (CreatorYard) ------------------------
    OutcomeQuestion(
        name="cy-mvp-scope",
        question="CreatorYard の MVP にはどの機能が入りますか",
        answer_marker="MVP は Story のみ",
        repository="tukemen-rgb/creater-yard",
    ),
    OutcomeQuestion(
        name="cy-withdrawal-condition",
        question="CreatorYard の撤退条件はどう決まっていますか",
        answer_marker="書き手 10 人・Story 30 本",
        repository="tukemen-rgb/creater-yard",
    ),
    OutcomeQuestion(
        name="cy-payments",
        question="CreatorYard に決済や販売の機能はありますか",
        answer_marker="決済は持たない",
        repository="tukemen-rgb/creater-yard",
    ),
    OutcomeQuestion(
        name="cy-ranking-culture",
        question="CreatorYard でランキングや称号は導入しますか",
        answer_marker="数字を競争にしない",
        repository="tukemen-rgb/creater-yard",
    ),
    # --- tukemen-rgb/marketing -----------------------------------------
    OutcomeQuestion(
        name="mkt-what-is-this-repo",
        question="marketing リポジトリは何をする場所ですか",
        answer_marker="シドラスタジオのマーケティング戦略・営業資料をつくる",
        repository="tukemen-rgb/marketing",
    ),
    OutcomeQuestion(
        name="mkt-deliverables-location",
        question="完成した営業資料はどのディレクトリに置きますか",
        answer_marker="docs/deliverables",
        repository="tukemen-rgb/marketing",
    ),

    # --- paraphrased: the operator's words, not the document's ---------
    # Written by deliberately avoiding the vocabulary that surrounds each
    # answer, so a lexical retriever has nothing to latch onto. These are
    # expected to be harder, and a low score here is a real finding about
    # the product rather than a defect in the question.
    # GDP proposed three additions (#372 comment 5357238029). Only this one
    # could be added: the other two are answered by sidra-ai's own
    # docs/SECURITY.md, and
    # test_outcome_questions_are_not_answered_by_our_own_repository forbids
    # grounding a question in the one repository this project writes. Changing
    # that invariant is the CEO's call, so it is recorded in the backlog's
    # section E rather than decided here.
    OutcomeQuestion(
        name="para-ugc-safety-before-players",
        question="知らない人が投稿したゲームを、そのまま利用者に配ってしまいませんか",
        answer_marker="公開前に 8 段階の検査を必ず通す",
        repository="tukemen-rgb/site",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-monetise-works",
        question="制作者が自分の作品で稼ぐ手段はうちにありますか",
        answer_marker="有料販売はしない",
        repository="tukemen-rgb/site",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-overseas-users",
        question="海外のユーザーにも届けたいのですが対応していますか",
        answer_marker="多言語化はしない",
        repository="tukemen-rgb/site",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-cost-to-creator",
        question="作品を出すのに制作者側の金銭的な負担はありますか",
        answer_marker="投稿は無料",
        repository="tukemen-rgb/site",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-single-number",
        question="事業が伸びているかを1つの数字で見るなら何を見ますか",
        answer_marker="週次で遊ばれた投稿作品数",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-real-bottleneck",
        question="うちが伸び悩んでいる本当の理由は技術力ですか",
        answer_marker="利用者のいる1つの事業へ経営資源が集中していない",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-compete-with-steam",
        question="Steam や App Store と同じ土俵で勝負しますか",
        answer_marker="大手ストアとの正面競争は避けます",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-lifetime-perk",
        question="キャンペーンでずっと使える特典を付けてもいいですか",
        answer_marker="永久無料・永年特典は将来原価を見積もれない限り提供しない",
        repository="tukemen-rgb/Fg",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-cy-unfinished-work",
        question="まだ途中のゲームしか無いのですが載せて大丈夫ですか",
        answer_marker="完成度で人を落とさない",
        repository="tukemen-rgb/creater-yard",
        tier="paraphrase",
    ),
    OutcomeQuestion(
        name="para-cy-ai-disclosure",
        question="生成 AI で作った部分は黙っておいたほうがいいですか",
        answer_marker="隠さず書ける",
        repository="tukemen-rgb/creater-yard",
        tier="paraphrase",
    ),
)


def questions_by_repository() -> dict[str, tuple[OutcomeQuestion, ...]]:
    """Group the set so per-repository coverage can be reported."""

    grouped: dict[str, list[OutcomeQuestion]] = {}
    for question in OUTCOME_QUESTIONS:
        grouped.setdefault(question.repository, []).append(question)
    return {repo: tuple(items) for repo, items in grouped.items()}
