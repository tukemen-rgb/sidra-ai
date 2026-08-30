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
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.projects import scaffold_project, validate_project
from sidra_ai.creation.router import CreationOutcome


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
        if verdict["complete"]:
            summary = (
                f"「{project.title}」の制作一式を {project.slug} に作りました: {listing}。"
                + notice
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
