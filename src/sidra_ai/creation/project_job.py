"""The project scaffold as the router sees it.

Same split as the deck and the game: :mod:`sidra_ai.creation.projects` is a
library with no opinion about HTTP, and this file is the callable the router
holds.

The summary names the files that were written, in the directory they were
written to. That is the whole point of a project - one place holding the
production - and a summary that said "プロジェクトを作りました" without the
list would leave the operator guessing which of six stages they actually got.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.games import genre_fallback_note
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.projects import scaffold_project, validate_project
from sidra_ai.creation.router import CreationOutcome


def _genre_fallback_note(message: str, project) -> str:
    """Say the production's game fell back to the default template, when it did.

    C-1285: the standalone game path says 「代わりに既定の…型で作りました」 when a
    genre it has no template for lands on the default fishing page (game_job).
    The project bundles that same game.html and said nothing, so a request for
    an 「アクションゲームの制作一式」 read as a delivered action game. This carries
    the same admission into the project summary.

    Only the two cases the game path also treats as a substitution fire, so a
    genre we *do* build (釣り, シューティング) never draws a caveat: a recognised
    genre with no template, and a request that named no genre at all whose
    subject the default template does not draw.
    """

    note = genre_fallback_note(
        message, getattr(project, "game_template", ""), project.title
    )
    return f"なお{note}" if note else ""


def build_project_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        project = scaffold_project(message, data_dir, facts=list(retrieved or []))
        verdict = validate_project(project)

        listing = "、".join(project.files)
        notice = (
            "依頼にあった作品名は使えないためオリジナル版として名付けました。"
            if project.renamed
            else ""
        )
        genre_note = _genre_fallback_note(message, project)
        if verdict["complete"]:
            summary = (
                f"「{project.title}」の制作一式を {project.slug} に作りました: {listing}。"
                + notice
                + genre_note
            )
        else:
            # Reported, not hidden: an operator told "six files" who finds
            # five has no way to know which promise was the false one.
            summary = (
                f"「{project.title}」を {project.slug} に作りましたが、"
                f"書けなかったものがあります: {'、'.join(verdict['missing'])}"
            )

        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(project.root),
            details={
                "slug": project.slug,
                "stages": verdict["stages"],
                "files": verdict["files"],
                "missing": verdict["missing"],
                "whole_project": project.whole_project,
                "renamed": project.renamed,
                "evidence": list(project.evidence),
            },
        )

    return generate


__all__ = ["build_project_generator"]
