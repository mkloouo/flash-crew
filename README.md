# flash-crew

The Antigravity CLI (`agy`) version of haiku-crew: one orchestrator thread, cheap Gemini Flash workers. It follows the same lessons from the r/ClaudeAI thread, adapted to how Antigravity works.

| Lesson | What the plugin does here |
| --- | --- |
| Small models hold up on **scoped** work and drift on open-ended work | Four `model: flash` workers with tight tool lists, strict contracts and fixed report formats |
| The main agent tends to delegate to **its own model** | A `PreToolUse` hook blocks `define_subagent`, the built-in `self` clone, and any file-defined agent left on `model: inherit` |
| Savings come from keeping reads in the worker's context and splitting by **code area** | An `always_on` rule with the delegation policy, loaded every turn |

## What's inside

```
flash-crew/
├── plugin.json              name + description (the schema allows nothing else)
├── rules/delegation.md      always_on delegation policy
├── agents/
│   ├── crew-scout.md        read-only search
│   ├── crew-runner.md       tests/lint/build, failures only
│   ├── crew-implementer.md  one bounded edit + check
│   └── crew-checker.md      verify against criteria
├── hooks.json               PreToolUse on invoke_subagent|define_subagent
├── hooks/agent_gate.py      the gate (uv script, standard library only)
├── gate.json                gate settings
└── pin_paths.py             pins absolute paths into the installed hooks.json
```

## Install

Needs Antigravity CLI and [`uv`](https://docs.astral.sh/uv/).

```bash
unzip flash-crew.zip
agy plugin install ./flash-crew
uv run ./flash-crew/pin_paths.py      # do this, see below
```

Restart `agy`, then check: `/plugin list` shows flash-crew, `/agents` lists the four `crew-*` agents, and `/hooks` shows `flash-crew-gate`.

**Why `pin_paths.py` matters.** In Antigravity, a hook that fails to start, crashes or times out **blocks** the tool call. The hook environment is also sanitized, so `uv` from `~/.local/bin` may not be on its PATH. Without pinning, a missing `uv` would block every subagent spawn with `pre-tool hook failed`. The script writes the absolute path of `uv` and of the gate into the installed copy of `hooks.json`. Re-run it after every reinstall or update.

**Smoke test** (inside `agy`):
1. `Use crew-scout to find where <something> is defined.` It should run and return a short report.
2. `Spawn the self subagent to list the files here.` It should be denied, and the agent should switch to a crew worker.
3. Check the log:
   ```bash
   tail -5 ~/.gemini/antigravity-cli/flash-crew-logs/delegations.jsonl
   ```
If nothing shows up in the log, the hook isn't firing. Check `/hooks` and re-run `pin_paths.py`.

## Picking the orchestrator: two quota pools

Antigravity tracks **two separate pools**, each with a 5-hour limit and a weekly limit:
- **Gemini pool**: Gemini 3.x Flash and Gemini 3.1 Pro.
- **Claude/GPT pool**: Claude Sonnet 5.5 and Opus 5.5, plus older models being retired on November 2, 2026.

Workers can only be `inherit`, `flash` or `pro`, so they always draw from the Gemini pool. That gives you two setups:

| Setup | Orchestrator (`/model`) | Workers | When |
| --- | --- | --- | --- |
| **Split pools** (recommended on paid plans) | Claude Opus 5.5 or Sonnet 5.5 | Flash | Planning burns the Claude pool and grunt work burns the Gemini pool, so neither runs dry as fast. Claude 5.5 needs Google AI Pro (not a trial) or Ultra |
| **All-Gemini** | Gemini 3.1 Pro | Flash | Free plan, or when the Claude pool is exhausted |

Community reports put Opus at several times Sonnet's quota cost per task (measured on the 4.6 models). If your Claude pool runs dry mid-week, try Sonnet 5.5 as orchestrator before giving up on the split.

## Stretching your quota

- **The weekly cap is hard.** On Pro and Ultra the 5-hour window refreshes, but once the weekly limit is hit, nothing refreshes until the reset. Google raised Gemini limits twice in May 2026, and users still report hitting the weekly cap after a few heavy sessions.
- **Every request carries a fixed overhead.** One user measured about 23k tokens of system prompt and tool definitions per request (CLI 1.0.0). That's why the policy keeps one-off reads inline and the workers have short tool lists.
- **Watch it as you go**: `/usage` shows what's left per pool, `/effort` lowers Flash thinking for routine work, and `/compact` trims context.
- **Set AI Credit Overages to "Never"** unless you want paid credits spent automatically once the baseline runs out.
- **API key fallback**: exporting `GEMINI_API_KEY` uses your Google AI Studio quota instead of the account pool (reported workaround).

## Tune it

- **gate.json**:
  - `blockDefineSubagent`: block ad-hoc agents made with `define_subagent`
  - `blockSelf`: block the built-in `self` clone
  - `allowInheritModel`: names of your own `inherit` agents to let through
- **Stronger checker**: change `crew-checker` to `model: pro` (Gemini 3.1 Pro). It costs more from the Gemini pool, but catches more.
- **Sandbox**: agents use the default `commandExecutionPolicy` (`sandbox`). If `crew-runner` can't run your tests because of the sandbox, add `commandExecutionPolicy: auto` to its frontmatter.

## Limits and unknowns

- **Effort can't be set per worker.** Antigravity's agent format has no effort field. Workers run Flash at the tier default, and `/effort` applies session-wide.
- **`flash` resolves to the current default Flash**, Gemini 3.8 Flash as of October 2026. The docs don't offer a way to pin a version.
- **Allowed spawns are auto-approved.** For calls it lets through, the gate returns `allow`, which skips the permission prompt for the spawn itself. The worker's own commands still go through your normal permissions.
- **Not tested inside agy.** The gate was tested against the documented hook payloads, not a live session. Plugin agent naming (`crew-scout` vs `flash-crew:crew-scout`) is handled both ways.
