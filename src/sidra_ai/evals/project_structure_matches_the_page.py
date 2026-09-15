"""Does structure.md describe the page that was actually shipped?

C-1848. The production document said 「現状の game.html は単一画面です。タイトル
画面もリザルト画面も無く、開いた瞬間に始まります」 and listed both screens under
「まだ無いもの」. Measured across all ten templates, every page has a briefing
start gate (C-1033), a result strip and an attract demo. The screen table had
two rows and no start screen at all.

``story.features``'s own docstring calls these documents "the specification
that is actually true of the shipped page", and the paragraph that was wrong
warns that describing a screen the page lacks turns the document into a wish.
The mirror - denying a screen the page has - costs a reader the same way: they
plan to build what is already built.

The rows are assembled from the modules that own the features, so the checks
here compare the document against the page rather than against a second list
that can go stale in the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation import attract, recap, startscreen
from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.story import (
    ProductionPlan,
    plan_for,
    screens,
    structure,
)


@dataclass(frozen=True)
class ProjectStructureResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _plan(template: str) -> ProductionPlan:
    # Through the product's own builder, so the plan carries the same numbers
    # the page ships with rather than ones invented here.
    plan = plan_for(f"{template}のゲームを作って")
    return ProductionPlan(template, plan.difficulty, plan.speed, plan.band)


def _document(template: str) -> str:
    return structure("題", (), _plan(template))


def evaluate_project_structure_matches_the_page() -> ProjectStructureResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) the start screen is in the table, for every template ----------
    missing = [
        template
        for template in sorted(TEMPLATES)
        if "開始（ブリーフィング）" not in _document(template)
    ]
    add(not missing, f"A: no start screen in the document for: {missing}")
    # --- (B) and the page really has one ----------------------------------
    #     Compared against the page, not against a list: at least one of the
    #     briefing's own lines is in the HTML. Not all of them - racing's first
    #     line carries a token that is substituted when the page is built.
    unbriefed = [
        template
        for template in sorted(TEMPLATES)
        if not any(
            line in generate_game(f"{template}のゲーム", template=template).html
            for line in startscreen.BRIEFINGS.get(template, ())
        )
    ]
    add(not unbriefed, f"B: these pages have no briefing after all: {unbriefed}")
    # --- (C) the document no longer calls the page single-screen ----------
    claims = [
        template
        for template in sorted(TEMPLATES)
        if "単一画面" in _document(template)
    ]
    add(not claims, f"C: still called single-screen: {claims}")
    # --- (D) and does not list the screens it has as missing --------------
    listed_missing = [
        template
        for template in sorted(TEMPLATES)
        if "タイトル画面（開始ボタン" in _document(template)
        or "リザルト画面（最終スコア" in _document(template)
    ]
    add(not listed_missing,
        f"D: screens that exist are still under 「まだ無いもの」: {listed_missing}")
    # --- (E) attract mode appears where the page has it -------------------
    wrong_attract = [
        template
        for template in sorted(TEMPLATES)
        if (template in attract.ATTRACT_TEMPLATES)
        != ("アトラクト" in _document(template))
    ]
    add(not wrong_attract, f"E: attract mode misreported for: {wrong_attract}")
    # --- (F) a losing result is described per template, not in general ----
    #     catch and fishing have no losing state (recap.LOSS_UNWIRED says so);
    #     the others end and name what ended them.
    wrong_loss = [
        template
        for template in sorted(TEMPLATES)
        if ("結果表示（負け）" in _document(template))
        != (template in recap.LOSS_WIRED)
    ]
    add(not wrong_loss, f"F: the losing state is misreported for: {wrong_loss}")
    # --- (G) what is genuinely missing is still said ----------------------
    #     Difficulty comes from the words of the request; no screen offers it.
    add(all("難易度選択" in _document(template) for template in sorted(TEMPLATES)),
        "G: the document stopped saying difficulty cannot be chosen on screen")
    # --- (H) and that claim is true of the page ---------------------------
    add(not any(
            "難易度" in line
            for lines in startscreen.BRIEFINGS.values()
            for line in lines
        ),
        "H: a briefing offers a difficulty choice, so the document is now wrong")
    # --- (I) the flow line and the table agree ----------------------------
    #     One source builds both; a document whose prose and table disagree is
    #     the failure this eval is about, one paragraph down.
    disagreed = []
    for template in sorted(TEMPLATES):
        document = _document(template)
        for name, _shows, _advance in screens(_plan(template)):
            if document.count(name) < 2:
                disagreed.append(f"{template}:{name}")
    add(not disagreed, f"I: flow and table disagree: {disagreed[:4]}")

    return ProjectStructureResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "ProjectStructureResult",
    "evaluate_project_structure_matches_the_page",
]
