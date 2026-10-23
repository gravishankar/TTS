# AGENTS.md

The standing contract for all coding agents (Claude Code, Cursor, others) is
**[CLAUDE.md](CLAUDE.md)**. Read it before doing anything in this repository.

Requirements come from [docs/PRD.md](docs/PRD.md).

The most important rules, in brief (CLAUDE.md is authoritative):

- Cloud agents write code, tests and configs. Models, audio, inference and training run only on
  the user's local MacBook Pro M4 Max.
- Never commit audio, model weights, checkpoints, caches, credentials or private data.
- Never train on TEST or CHALLENGE, and never fine-tune before baseline evaluation.
- Never invent model APIs; verify them against authoritative source.
- Do not modify `agent-sdk-course/`.
