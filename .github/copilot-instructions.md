# Targeted validation

- Run only tests related to the change. Combine relevant unittest method, class or module selectors in one runner invocation; see [README](../README.en.md#tests).
- Do not run full test discovery for each development step. Use a separately agreed regression checkpoint, or escalate when targeted failures demonstrate a wider need.
- The parent agent owns validation. Subagents report required test selectors instead of running them unless explicitly assigned validation. Reuse successful results for unchanged code; do not repeat another agent's run.
- Report exact selectors, results and elapsed time. Do not claim unrun tests passed.
- Investigate failures in production code first. Change assertions only when requirements changed or evidence proves the test expectation wrong; never weaken coverage to obtain a pass.
- Database schema rejection tests protect the current schema contract; keep them even though old database migrations are unsupported.
- Tests modify global settings and must not run concurrently in one process. Use separate processes and isolated temporary storage if parallel execution is explicitly needed.
