# Trading App — project pointer

The distilled architecture, phase layout, persistence map, feature flags, and
operational surface for this repo live in the Second Brain wiki:

```
/Users/mohan/Library/CloudStorage/OneDrive-Personal/Documents/knowledge/Second Brain/wiki/trading-app.md
```

**Read that page first** before answering questions about:

- Repo architecture, runtime, or the pipeline stages
- Phase F (market correspondent), G (universe + regime), H (crypto regime
  authority), or I (strategy observatory / research / governance)
- Persistence layout under `persist/`
- CryptoScheduler tasks and cadence
- Feature flags (`PHASE_*_ENABLED`, `CASH_ONLY_TRADING`, etc.)
- OpenClaw / ops_agent / Telegram surface

If the wiki page is missing context the user is asking about, do your normal
research (read code, run `git log`, etc.) and then **update the wiki page**
before stopping the turn. Append a row to `wiki/processing-log.md`. See
`~/.claude/CLAUDE.md` for the general read-before-research / update-when-learn
contract.

## Auto-sync on commit

Commits to `main` in this repo trigger a background `claude -p` invocation
(`.git/hooks/post-commit`) that reconciles the diff against `wiki/trading-app.md`
and `wiki/processing-log.md`. So if you only have project-internal questions
about a recent commit, the wiki is usually already current.

## Repo-specific reminders

- Use `python3`, not `python`, on this machine.
- `crypto_main.py` and `main.py` are the two daemons; `phase_f_main.py` is the
  reasoning daemon.
- The canonical trade ledger is `persist/{scope}/ledger/trades.jsonl` —
  fields are `entry_timestamp`, `exit_timestamp`, `net_pnl`, `strategy_name`
  (NOT `entry_time` / `realized_pnl` — that mismatch is a known bug in the
  Phase I-C governance code per the recent review).
- Don't write to `Second Brain/sources/` — that layer is user-only.
