# SIDRA AI v0.1 Integration Candidate

This branch is the only promotion target for SIDRA AI v0.1. It starts from Claude's current coordination/base commit and carries the verification gate that must pass on the exact commit promoted to `main`.

## Promotion rule

Do **not** merge this branch to `main` unless the exact current integration SHA has all required gates green:

1. full `python -m pytest`;
2. `sidra-evals`;
3. installed-distribution scan shows no blocked external LLM provider SDK;
4. existing read-only / localhost / no-paid-API safety regressions remain green;
5. no unresolved merge conflict or unverified lane update remains.

Any code, config, dependency, model-artifact, or workflow change after verification invalidates the earlier evidence and requires the gates to run again on the new SHA.

## Current base

- Claude coordination/base: `d856ba4390ff2cb95b46d93b9986da45671f15aa`
- `main` remains unchanged until the promotion rule is satisfied.

## Lane inputs observed for integration

These are source pins, not approvals. A lane must be refreshed to the current verified upstream/base and revalidated before it can enter this branch.

| Area | Current source SHA | Integration status |
| --- | --- | --- |
| L1 Retrieval / PR #10 | `a28e984ef44642f89f7be64c783046f40b0470b5` | Behind Claude base by one coordination commit; refresh + full verification required. |
| L3 Ingestion / PR #7 | `23f2251fad766ddeb39083c56fc2b0bae277e48b` | Includes L1 dependency; behind Claude base by one coordination commit; refresh + full verification required. |
| L4 Models / PR #8 | `e74b4c7787799fd1c88755e3be9a37f53c6284a9` | Claude base is an ancestor. Transformers is fail-closed/disabled pending local-artifact-only support. Full verification still required. |
| L2 Security / PR #9 | `acc0519e55161085022e03e2b41da03a3f60a834` | Behind Claude base by one coordination commit. Child PR #13 is not yet folded into the lane. |
| L2 PII child / PR #13 | `1746792b313286ef9e3f8f4f16a87519c7242f80` | A separate verification branch `cbb46bce552c0fa098c4da0ee19a59c9fca582c2` completed its Security verification workflow successfully; fold into L2 only after refresh/revalidation on the current base. |
| L5 API / PR #5 | `a8a3f8841f738800abc6778241da51c7f978adc0` | Stacked on Security `acc0519`; must follow the final verified L2 SHA. |
| API audit child / PR #14 | `f45a51a53eab54d6f3715ed3f847104412ded9b5` | Ahead of API #5; targeted logic checked, repository-wide verification still required before folding into L5. |
| L6 Evals / PR #12 | `13b23a1ab13a17e45191e6b30e13db39572c8acd` | Stacked on API `a8a3f884`; must follow final verified L2/L5 and then run full verification. |
| CI reference / PR #11 | `3577b7dc06fea6d012b596affa1ba2a1da2d8d68` | Prior CI proof only; not proof for the current multi-lane candidate. The integration branch has its own pinned-action gate. |

Open GitHub issues: none at the time this integration manifest was created.

## Integration order

Use dependency order, not PR number order:

1. refresh L1 to the current Claude base;
2. refresh L3 on the verified L1 result;
3. keep L4 on the current Claude base and verify it independently;
4. refresh L2 to the current Claude base, fold the verified intent of PR #13, then verify the exact resulting L2 SHA;
5. refresh L5 on that verified L2 SHA and fold PR #14 only after its API tests pass;
6. refresh L6 on the verified L5 SHA;
7. combine L1/L3 + L4 + L2/L5/L6 on this integration branch;
8. run the same-SHA integration gate;
9. only if every gate is green, promote that exact SHA to `main`.

Legacy PRs whose substantive work has been superseded by the lane integration PRs (`#1`, `#3`, `#4`, `#6`) are reference material and must not be independently promoted without a new conflict/coverage review.

## Runtime boundary for v0.1

- No paid/external LLM API fallback.
- Model inference remains local/loopback-only.
- GitHub ingestion is read-only.
- Safe read-only web research, when implemented, must use an allowlisted/SSRF-resistant fetch boundary and feed untrusted DATA through the Security Gate.
- Production publication, service-to-service production connection, external writes/sends, spending, secrets, and destructive operations remain outside this promotion approval.
