# Trading App — project pointer

This repo has **two parallel knowledge surfaces** that must both stay current.

### Surface 1 — `DOCUMENTATION.md` (in this repo)
*For external readers: collaborators, contractors, future hires.* Comprehensive
chronological journal at `/Users/mohan/Sandbox/trading_app/DOCUMENTATION.md`.
Long-form, factual, dated entries under "🔔 Latest Updates (Newest First)" plus
an "Implementation Status" table. ~4000 lines and growing.

### Surface 2 — Second Brain wiki (out of repo)
*For the user's personal analysis across future Claude sessions.* Distilled,
conceptual, one concept per file:
```
/Users/mohan/Library/CloudStorage/OneDrive-Personal/Documents/knowledge/Second Brain/wiki/
```
Main pages: `trading-app.md` (overview) plus topical sub-pages (`trading-app-phase-*.md`,
`trading-app-swing.md`, `trading-app-ml.md`, etc. as they get created).

### Read-before-research

**Read both surfaces first** before answering questions about repo architecture,
phases (A/B/C/D/E/F/G/H/I), pipeline stages, persistence layout, runtime, feature
flags, safety gates, or operational surface. The wiki is the distilled map;
DOCUMENTATION.md has the full history.

### Update-when-you-learn (the dual-write rule)

When you learn or change something durable about this app in a conversation,
update **BOTH** surfaces in the same turn before stopping:

1. **DOCUMENTATION.md** — append a new dated entry at the top of "🔔 Latest
   Updates" in the existing format. Update "Last updated:" at the file head.
   Add to "Implementation Status" table if it's a new component.
2. **Second Brain wiki** — update or create the relevant distilled page;
   append exactly one row to `wiki/processing-log.md`.
3. End your response with a 📚 block listing what you wrote to where (per the
   global `~/.claude/CLAUDE.md` directive).

Skip the surfaces only for genuinely ephemeral turns (typo fix, one-off lookup,
repeated command).

## Auto-sync on commit

Commits to `main` trigger a background `claude -p` invocation
(`.git/hooks/post-commit`) that reconciles the diff against BOTH surfaces:
prepends a dated entry to `DOCUMENTATION.md` (for external readers) AND
updates the Second Brain wiki + appends to `processing-log.md` (for user).
You'll see `[Second Brain + DOCUMENTATION.md] sync queued → /tmp/...` right
after the commit. Both surfaces should be current within ~60 seconds.

## Repo-specific reminders

- Use `python3`, not `python`, on this machine.
- `crypto_main.py` and `main.py` are the two daemons; `phase_f_main.py` is the
  reasoning daemon.
- The canonical trade ledger is `persist/{scope}/ledger/trades.jsonl` —
  fields are `entry_timestamp`, `exit_timestamp`, `net_pnl`, `strategy_name`
  (NOT `entry_time` / `realized_pnl` — that mismatch is a known bug in the
  Phase I-C governance code per the recent review).
- Don't write to `Second Brain/sources/` — that layer is user-only.
