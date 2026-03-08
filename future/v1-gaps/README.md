# V1.0 Gap Implementation Plans

Implementation plans for features identified in `future/V1.0-GAPS.md`. All plans
are V1.0 scope (individual phases within plans may note post-1.0 deferrals).

## Plan Index

Plans are numbered by recommended implementation order (priority + dependencies).

| # | Plan | V1.0-GAPS Section | Priority |
|---|------|--------------------|----------|
| 01 | [Comptime Execution](gap01-comptime-execution.md) | Section 1 | High |
| 02 | [Linear Types](gap02-linear-types.md) | Section 2 | Medium |
| 03 | [Memory Regions](gap03-memory-regions.md) | Section 3 | Medium |
| 04 | [AI-Resistance Enforcement](gap04-ai-resistance-enforcement.md) | Section 4 | Medium |
| 05 | [Type System](gap05-type-system.md) | Section 9 | Medium |
| 06 | [Contracts & Verification](gap06-contracts-verification.md) | Section 10 | Low |
| 07 | [Optimizer Passes](gap07-optimizer-passes.md) | Section 5 | Low |
| 08 | [Runtime Tests](gap08-runtime-tests.md) | Section 11 | Medium |
| 09 | [CLI & Tooling](gap09-cli-tooling.md) | Section 13 | Low |
| 10 | [Concurrency](gap10-concurrency.md) | Section 6 | Low |
| 11 | [AI-Resistance Proposed](gap11-ai-resistance-proposed.md) | Section 7 | Low |

### Excluded from plans

- **Section 8** (Future AI-Resistance Research) — explicitly post-1.0, stays in `docs/ai-resistance.md`
- **Section 12** (Documentation claims) — folded into relevant gap plans' exit criteria

## Dependency Graph

```
gap01 (comptime)               — independent
gap02 (linear types)           — independent
gap03 (memory regions)         — soft dep on gap02 (ownership affects allocation)
gap04 (AI-resistance enforce)  — independent
gap05 (type system)            — independent
gap06 (contracts/verify)       — soft dep on gap05
gap07 (optimizer)              — soft dep on gap02 (copy elision uses move tracking)
gap08 (runtime tests)          — independent, parallelizable
gap09 (CLI tooling)            — independent
gap10 (concurrency)            — may dep on gap01, gap05
gap11 (AI-resistance proposed) — depends on gap04
```

Most plans are independent and can be worked in parallel. The main sequencing
constraints are:

- **gap03** benefits from gap02 decisions (ownership model affects region allocation);
  also requires escape analysis design (see `future/escape-analysis.md`)
- **gap06** uses type system features from gap05 (refinement analysis)
- **gap07** copy elision phase builds on gap02's move tracking infrastructure
- **gap10** may use comptime (gap01) and type system (gap05) infrastructure
- **gap11** builds on gap04's enforcement foundation

## Status Tracker

| # | Status | Notes |
|---|--------|-------|
| 01 | Not started | |
| 02 | Not started | |
| 03 | Not started | |
| 04 | Not started | |
| 05 | Not started | |
| 06 | Not started | |
| 07 | Not started | |
| 08 | Not started | |
| 09 | Not started | |
| 10 | Not started | |
| 11 | Not started | |
