"""Does 「制作一式」 build the whole production, not one stage?

C-1462: 「制作一式」 is the project generator's own offered label and a PROJECT
intent word, but it was not in WHOLE_PROJECT_WORDS. So 「新機能ローンチのゲーム
制作一式を作って」 fell through to the stage matcher, where 「機能」 (inside 新機能,
the subject) matched the FEATURES cue and narrowed the full-set request to
features.md alone - while the summary still said 「制作一式を作りました」. 「制作一式」
now forces the whole production; 「アセット一式」 (a full set of assets) stays
narrowed to its own stage because the whole-project word is 「制作一式」, not bare
「一式」.

The checks read ``requested_stages`` for routing and a real router run for the
end-to-end file set.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectWholeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_project_production_set_is_whole() -> ProjectWholeResult:
    from sidra_ai.creation.projects import STAGE_ORDER, Stage, requested_stages

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 「制作一式」 forces the whole production even when the subject word collides
    # with a stage cue (新機能→機能=FEATURES, モデルルーム→モデル=ASSETS).
    for request in (
        "新機能ローンチのゲーム制作一式を作って",
        "ゲーム制作一式を作って",
        "モデルルーム管理ゲームの制作一式を作って",
    ):
        stages = requested_stages(request)
        add(stages == STAGE_ORDER,
            f"制作一式 did not build the whole production: {request!r} "
            f"-> {[s.name for s in stages]}")

    # A single-stage request is still narrowed, and 「アセット一式」 stays its own
    # stage (not the whole project).
    add(requested_stages("ゲームの脚本だけ作って") == (Stage.SCENARIO,),
        "a scenario-only request was widened")
    add(requested_stages("ゲームのアセット一式を作って") == (Stage.ASSETS,),
        "「アセット一式」 was widened to the whole project")

    # End to end: the router builds and lists the whole file set.
    import tempfile
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.router import build_default_router

    router = build_default_router(data_dir=tempfile.mkdtemp())
    req = "新機能ローンチのゲーム制作一式を作って"
    out = router.route(req, detect_creation_intent(req), [])
    details = out.details or {}
    add(details.get("whole_project") is True
        and len(details.get("files") or []) == len(STAGE_ORDER),
        f"the router did not build the whole production: "
        f"whole={details.get('whole_project')}, files={details.get('files')}")

    total = 6
    return ProjectWholeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ProjectWholeResult", "evaluate_project_production_set_is_whole"]
