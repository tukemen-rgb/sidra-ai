"""Does the design document's scoring section describe THIS game?

C-1946. ``features.md`` opens by saying **「数値と操作は同じディレクトリの
game.html が実際に使うもの」** - the numbers and the controls are the ones
the page really uses. Its scoring section was one branch::

    "帯の中で…" if plan.template == "fishing" else "受けられたら 受け +1…"

so **nine of the ten templates were told they count 「受け」 and
「こぼし」**. Measured: the ``features.md`` of a racing production said so
while the page counts ``LAP`` and ``TOTAL``; kaiju's said so while the page
counts 周期. A document that merely said nothing would be empty. This one
made a claim, about the file next to it, and was wrong - after promising it
would not be.

**What this counts.** Templates whose scoring section survives three checks
at once, out of every template the registry has:

1. The sentence names what the page names. Each term of
   ``scoring_terms`` has to appear in the template's own ``script`` - the
   body the page runs, not a note beside it (C-1640) - **or** the body has
   to name the row of ``CANVAS_WORDS`` that carries it. Since C-1959 the
   words the canvas draws are injected once at the top of the page as
   ``CW`` instead of being written into each template, so a template that
   draws ``CW.caught`` draws 「受け」 just as surely as one with the literal
   in it. Checking the table alone would loosen this - every template would
   inherit every word - so it is the KEY THE TEMPLATE NAMES that counts.
2. The terms are actually in the Japanese sentence. A term list that
   drifted away from the sentence would let check 1 pass over words no
   reader ever sees. The **English** sentence is not checked term by
   term, and that is deliberate: the page's HUD prints Japanese, so
   requiring 「得点」 inside an English document would plant exactly the
   leftover that ``project_files_match_the_language_asked`` counts as a
   failure. Measured - the first draft of this item did require it, and
   took that number from 4 to 3. What is required instead is that no two
   templates share a sentence, in either language, which is the original
   defect stated as a rule rather than as a word list.
3. **No template borrows another's counters.** For each template, the
   terms that belong to other templates and not to it must not appear in
   its sentence. This is the original defect stated as a rule: racing may
   not say 「受け」, because 「受け」 is catch's word and racing's page has
   no such thing.

Ten templates are checked, not one. The judge for the documents' language
(``project_files_match_the_language_asked``) generates one production, and
one production is one template - C-1945 found that the hard way when a
Japanese row left in platformer's column moved no number at all. A defect
that lives per template has to be measured per template.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringResult:
    templates_that_describe_themselves: int
    templates_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_features_scoring_matches_the_page() -> ScoringResult:
    from sidra_ai.creation.canvaswords import CANVAS_WORDS
    from sidra_ai.creation.games import TEMPLATES
    from sidra_ai.creation.story import ProductionPlan, features, plan_for

    failures: list[str] = []
    readings: list[str] = []
    right = 0

    owned = {key: set(spec.scoring_terms) for key, spec in TEMPLATES.items()}

    for key in sorted(TEMPLATES):
        spec = TEMPLATES[key]
        page = spec.script
        # The words this template draws through the shared table: the row's
        # Japanese, for every row whose key its own body names (C-1959).
        through_table = {
            pair[0] for key, pair in CANVAS_WORDS.items() if f"CW.{key}" in page
        }
        problems: list[str] = []

        for term in spec.scoring_terms:
            if term not in page and term not in through_table:
                problems.append(f"「{term}」 is not in the page it describes")
            if term not in spec.scoring:
                problems.append(f"「{term}」 is claimed but not in the sentence")

        borrowed = sorted(
            term
            for other, terms in owned.items()
            if other != key
            for term in terms
            if term not in owned[key] and term in spec.scoring
        )
        if borrowed:
            problems.append(
                "says " + "、".join(f"「{t}」" for t in borrowed)
                + " - another template's counter"
            )

        # The English sentence cannot be checked term by term: the page's HUD
        # prints Japanese, and forcing 「得点」 into an English document is
        # exactly the leftover that `project_files_match_the_language_asked`
        # counts as a failure - measured, it took that number from 4 to 3
        # while this one was being written. So the English side is held to
        # what can be checked without contradicting that: it exists, it
        # reaches the document, and **it is not a copy of another template's
        # sentence** - which is the original defect stated for English.
        same_english = sorted(
            other
            for other, spec_other in TEMPLATES.items()
            if other != key and spec_other.scoring_en == spec.scoring_en
        )
        if same_english:
            problems.append(
                "its English sentence is word for word " + "、".join(same_english)
                + "'s"
            )
        same_japanese = sorted(
            other
            for other, spec_other in TEMPLATES.items()
            if other != key and spec_other.scoring == spec.scoring
        )
        if same_japanese:
            problems.append(
                "its sentence is word for word " + "、".join(same_japanese) + "'s"
            )

        # And the sentence has to reach the document a reader opens.
        base = plan_for(f"{key}のゲームを作って")
        plan = ProductionPlan(key, base.difficulty, base.speed, base.band)
        if spec.scoring not in features("題", (), plan):
            problems.append("the sentence never reaches features.md")
        if spec.scoring_en not in features("t", (), plan, in_japanese=False):
            problems.append("the English sentence never reaches features.md")

        if problems:
            failures.append(f"{key}: " + "; ".join(problems))
        else:
            right += 1
        readings.append(f"{key} {'ok' if not problems else 'WRONG'}")

    return ScoringResult(
        templates_that_describe_themselves=right,
        templates_total=len(TEMPLATES),
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = ["ScoringResult", "evaluate_features_scoring_matches_the_page"]
