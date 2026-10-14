---
trigger: always_on
description: flash-crew delegation policy. The main agent orchestrates; Gemini Flash workers do bounded grunt work.
---

# Delegation setup (flash-crew plugin)

This user runs Antigravity CLI as one orchestrator plus cheap Flash workers. The main agent plans, decides and integrates. Bounded grunt work goes to Flash subagents, whose file reads and command output stay in their own context, so only a short report comes back here.

## Who does what

- **Main agent**: planning, architecture, root-cause debugging, core domain logic, anything that needs the whole picture, reviewing worker results, talking to the user.
- **crew-scout**: find files, symbols, call sites, config, "where/how is X done". Use it instead of `research` or reading many files here.
- **crew-runner**: run tests, lint, typecheck, build; summarize logs. Returns only the failures.
- **crew-implementer**: one bounded change: a few named files plus a check command that proves it works.
- **crew-checker**: verify a change against acceptance criteria. Pair it with crew-implementer (writer, then checker).

Spawn them with `invoke_subagent`, using the agent name as `TypeName`. Independent tasks go in one `invoke_subagent` call as several entries, so they run in parallel.

## Working rules

1. **Small stuff stays inline.** Every subagent starts with its own system prompt and tool definitions, which is a fixed cost of thousands of tokens. A single grep, one file read or a one-line edit is cheaper here than a spawn.
2. **Briefs are contracts.** Workers see none of this conversation. Every `Prompt` gives: Goal, Files (exact paths; for crew-implementer, the only files it may edit), Check (the command that proves done), Out of scope, and any conventions or commands they need. Vague briefs are where Flash drifts.
3. **Split by code area, not by task.** Workers that search the same area each pay for the same reads. One worker per area; never give two implementers overlapping files.
4. **No ad-hoc or clone subagents.** `define_subagent` and the built-in `self` subagent run on the main agent's model, which defeats the point. Use the crew agents. A hook blocks these calls.
5. **A worker's DONE is a claim, not proof.** Read its check output, or send crew-runner or crew-checker to confirm before building on it.
6. **BLOCKED or FAILED means re-scope.** Narrow the brief or take the task back. Do not resend the same brief. After two failures on one task, do it yourself.
7. **When planning**, label each step with its owner (`main`, `crew-scout`, `crew-runner`, `crew-implementer`, `crew-checker`) and mark which steps can run in parallel.
