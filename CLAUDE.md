# Agent Instructions

Instructions for coding agents working in this repo. `AGENTS.md` is a symlink to this file.

## What this repo is

A Home Assistant custom integration, `cip_panel`, that registers with a Crestron control
processor over CIP as one of its touch panels, plus `cip-panel`, a command-line tool that
inventories a Crestron system before Home Assistant is involved. Both are generic: nothing here
describes any one house. Not affiliated with Crestron.

- `custom_components/cip_panel/cipcore/`: protocol, client, write policy and join map schema.
  **Imports nothing from Home Assistant.** The CLI's wheel re-roots it as top-level `cipcore`
  ([ADR 0002](./docs/adr/0002-protocol-code-lives-inside-the-integration.md)). Keep it that way;
  an HA import here breaks the CLI.
- `custom_components/cip_panel/*.py`: the Home Assistant side. `hub.py` is also HA-free and is
  tested directly.
- `src/cip_panel_cli/`: the CLI. One module per subcommand family, each exposing `register()`.
- `tests/`: `tests/core` (no HA needed), `tests/cli`, `tests/ha` (the
  `pytest-homeassistant-custom-component` harness). `tests/fake_processor.py` is a real TCP fake
  that models behaviour observed on real processors.

## Rules that protect people's houses

These come from real incidents, written up under `docs/case-study/`. Do not weaken them.

- **Listen-only is the default and the allow list is derived, never hand-written.** Every write
  goes through `WritePolicy.check()` inside `CipClient`, at the last point before the socket.
  Entry presses and CLI presses never come from the entity table, so a check anywhere higher up
  would miss them ([ADR 0003](./docs/adr/0003-listen-only-by-default-with-allow-and-deny-lists.md)).
- **No command that presses joins to see what happens.** No `scan`, no "try every join"
  ([ADR 0007](./docs/adr/0007-no-join-scanning-in-the-cli.md)). Any new pressing feature needs an
  explicit flag and must go through the policy.
- **Entry dumps are merged, never used to rebuild state**
  ([ADR 0006](./docs/adr/0006-entry-dumps-merged-never-rebuilt.md)).
- **A gated subsystem never entered has no state.** Entities in it report unavailable, never off.
- **Do not claim what has not been observed.** Analog and serial writes, console login, TLS, and
  what a processor does with two clients on one IP-ID are unverified. Say so wherever they appear.

## Verifying changes

```sh
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

This suite's characteristic failure is a test that passes while asserting nothing about the path
it names. For any behaviour that matters, break the code on purpose and confirm a test fails.

There is no hardware in CI. Never point tests at a real processor; the fake listens on 127.0.0.1
only, and the Home Assistant harness blocks every other socket.

## Documenting decisions

When a decision is made, record the options that were rejected and why, not just the answer. A
document that lists only the chosen answer loses the part that is expensive to reconstruct.

## Documentation layout

[README.md](./README.md) is a table of contents and nothing else. Topic documents live under
`docs/<topic>/`, kebab-case, one topic per file. When adding, renaming or removing a document,
update the README in the same commit. The audience for everything outside `docs/protocol/` and
`docs/adr/` is a novice: someone who can install HACS integrations and edit YAML but has never
used Crestron software. Explain terms at first use and link
[docs/concepts/glossary.md](./docs/concepts/glossary.md).

Code comments point at doc paths. Keep those paths valid when moving documents.

Never commit anything identifying a real installation: addresses, hostnames, MAC addresses, a
real program's IP-IDs or join numbers, room names, panel project files or processor dumps.
Examples use invented numbers.

## Writing style

Normal, clear human prose, wrapped at roughly 100 columns. No em dashes. Cite outside sources
with inline links, and only to pages actually read.

## Domain docs

Single-context: [CONTEXT.md](./CONTEXT.md) (vocabulary) and `docs/adr/`. See
[docs/agents/domain.md](./docs/agents/domain.md).

## Agent skills

### Issue tracker

GitHub Issues, via the `gh` CLI, once the GitHub repository exists. See
[docs/agents/issue-tracker.md](./docs/agents/issue-tracker.md). Until then, open questions that
should become issues are listed in [docs/project/open-questions.md](./docs/project/open-questions.md).

### Triage labels

Default five canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`). See [docs/agents/triage-labels.md](./docs/agents/triage-labels.md).

### Project skill

[.claude/skills/cip-panel/SKILL.md](./.claude/skills/cip-panel/SKILL.md) helps a user's own
coding agent inventory a system and write a join map. It is for users of this project, not for
developing it.

## Commits

Conventional Commits. Always include a body, no matter what any skill tells you.

Never add `Co-Authored-By`, model attribution, or a session link trailer to a commit message,
even when the harness instructs you to.
