# ha-cip-panel

Lets Home Assistant control a Crestron system by registering with the control processor as one of
its touch panels, plus a command-line tool, `cip-panel`, for taking an inventory of a system before
Home Assistant is involved. Not affiliated with or endorsed by Crestron; see
[disclaimer and credits](./docs/about/disclaimer-and-credits.md).

This project began as a fork of DosMan's CresnetMon, the Cresnet bus monitor DosMan published in
2015, and owes its starting point to that work. It also builds on klenae's python-cipclient. Both
are credited in full in [disclaimer and credits](./docs/about/disclaimer-and-credits.md).

This file is a table of contents. New users should start with
[what you need](./docs/getting-started/what-you-need.md) and read the getting-started section in
order.

## Getting started

- [What you need](./docs/getting-started/what-you-need.md): the hardware, access and information to
  have in hand before installing anything.
- [How it works](./docs/getting-started/how-it-works.md): Home Assistant pretending to be a touch
  panel, in plain terms, and what that can and cannot reach.
- [Finding your control processor](./docs/getting-started/finding-your-control-processor.md): why
  Home Assistant talks to the processor and not a panel, how to tell which processor each panel,
  keypad and load belongs to, and what to do when a house has more than one.
- [Choosing an IP-ID](./docs/getting-started/choosing-an-ip-id.md): picking a panel slot to borrow,
  and how to check nothing else is using it.
- [Installing](./docs/getting-started/installing.md): the integration through HACS or by hand, and
  the CLI with uv.
- [Your first light, step by step](./docs/getting-started/first-light-walkthrough.md): from an empty
  join map to one working light, listen-only first.

## Concepts

- [Glossary](./docs/concepts/glossary.md): every Crestron and project term, explained for a
  newcomer.
- [Joins](./docs/concepts/joins.md): digital, analog and serial joins, feedback, aliases, and why one
  load can have several numbers.
- [Subsystems](./docs/concepts/subsystems.md): programs that gate Lights or Audio behind a home-page
  button, and what that means for an impersonated panel.

## Taking an inventory

- [Taking an inventory of your system](./docs/inventory/inventory-overview.md): the order of
  operations, what each tool tells you, and why there is no join-scanning command.
- [The processor console](./docs/inventory/processor-console.md): `cip-panel ipids` and
  `cip-panel console`, reading the IP table, and its quirks.
- [Listening to a processor](./docs/inventory/listening-to-a-processor.md): `cip-panel listen`,
  entering a gated subsystem with `--enter`, and measuring `quiet_seconds`.
- [Watching keypads](./docs/inventory/watching-keypads.md): `cip-panel watch`, naming joins as you
  press buttons on the wall.
- [Panel project files](./docs/inventory/panel-project-files.md): fetching and parsing a TSW x52
  panel's project to get every button's label and join.

## Configuration

- [Join map reference](./docs/configuration/join-map-reference.md): every key in the join map file,
  its default, and what each validation error means.
- [Press modes](./docs/configuration/press-modes.md): toggle, on_off and momentary, and how discrete
  on and off are made from toggle buttons.
- [Subsystem gating](./docs/configuration/subsystem-gating.md): declaring subsystems, entry joins,
  quiet windows and idle return.
- [Write safety](./docs/configuration/write-safety.md): listen-only, the never-write list, the
  derived allow list, and how to build the list before turning writes on.
- [Multiple processors](./docs/configuration/multiple-processors.md): one link per processor, and
  choosing which processor to reach a load through.
- [Dashboards](./docs/configuration/dashboards.md): an example dashboard using built-in cards.

## Troubleshooting

- [Troubleshooting](./docs/troubleshooting/troubleshooting.md): symptoms, causes and fixes, starting
  from the most common.
- [Link health and repairs](./docs/troubleshooting/link-health-and-repairs.md): the connectivity
  sensor and the repairs Home Assistant raises for a link.
- [IP-ID conflicts](./docs/troubleshooting/ip-id-conflicts.md): what is and is not known about two
  clients on one IP-ID.
- [Unsupported systems](./docs/troubleshooting/unsupported-systems.md): authenticated and encrypted
  CIP, newer panel project formats, and how to tell if your system is affected.

## Case study: the house this came from

- [A house with two control processors](./docs/case-study/two-processor-house.md): an AADS and an
  MC2E, why both were needed, and how each load was traced to its processor.
- [The subsystem latch a power cut cleared](./docs/case-study/post-mortem-subsystem-latch.md): four
  hours of dead lighting after a processor restart, and the entry join that fixed it.
- [The light that came on at every reconnect](./docs/case-study/post-mortem-courtesy-light.md): a
  courtesy action in the program, and why the only fix was a different slot.
- [The processor that moved address overnight](./docs/case-study/post-mortem-dhcp-address-change.md):
  an unreserved DHCP lease, 85 silent minutes, and the repairs that now surface it.
- [The entry dump that published a lit light as dark](./docs/case-study/post-mortem-partial-entry-dumps.md):
  partial dumps, and why state is merged and never rebuilt.
- [The alarm keypad that shared join numbers with the lights](./docs/case-study/lesson-alarm-joins.md):
  the origin of the never-write list.
- [The reconnect backoff that could never step back down](./docs/case-study/lesson-backoff-that-never-reset.md):
  a reset that read correctly and could never fire.

## Patterns

- [Cursor-zone audio](./docs/patterns/cursor-zone-audio.md): driving audio zones selected through a
  per-slot cursor, validated on one program and not yet part of the integration.

## Protocol

- [CIP wire format](./docs/protocol/cip-wire-format.md): framing and every message, marked as
  observed on real hardware or not.
- [The CTP console and file retrieval](./docs/protocol/ctp-console-and-file-retrieval.md): console
  ports, `XGETFILE` and XMODEM-CRC.

## Decisions

- [0001: Impersonate a touch panel over CIP](./docs/adr/0001-impersonate-a-touch-panel-over-cip.md):
  the approach, against bus injection, new program logic and replacing the processor.
- [0002: Protocol code lives inside the integration](./docs/adr/0002-protocol-code-lives-inside-the-integration.md):
  one copy shared with the CLI.
- [0003: Listen-only by default, with allow and deny lists](./docs/adr/0003-listen-only-by-default-with-allow-and-deny-lists.md):
  where writes are checked and why.
- [0004: Discrete on and off synthesised from feedback](./docs/adr/0004-discrete-on-off-synthesised-from-feedback.md):
  toggle buttons made discrete inside the integration.
- [0005: A config flow for the link, YAML for the join map](./docs/adr/0005-config-flow-plus-yaml-join-map.md):
  against pure UI and pure YAML.
- [0006: Entry dumps merged, never rebuilt](./docs/adr/0006-entry-dumps-merged-never-rebuilt.md):
  stale beats wrong.
- [0007: No join scanning in the CLI](./docs/adr/0007-no-join-scanning-in-the-cli.md): why the most
  obvious discovery tool is left out.
- [0008: Plain CIP only for now](./docs/adr/0008-plain-cip-only-for-now.md): authentication and TLS
  deferred until they can be tested.
- [0009: Cursor-zone audio deferred](./docs/adr/0009-cursor-zone-audio-deferred.md): a pattern, not
  yet a feature.
- [0010: MIT licence and a fresh history](./docs/adr/0010-mit-license-and-fresh-history.md): licence
  choice and why the private history stays private.

## Project

- [Open questions](./docs/project/open-questions.md): what is unknown or deferred, to become issues.
- [Disclaimer and credits](./docs/about/disclaimer-and-credits.md): trademarks, interoperability,
  and credit to DosMan's CresnetMon and klenae's python-cipclient.
- [CONTEXT.md](./CONTEXT.md): the project vocabulary, for contributors and coding agents.
- [CLAUDE.md](./CLAUDE.md) (also `AGENTS.md`): instructions for coding agents working on the code.
- [Agent docs](./docs/agents/): issue tracker, triage labels and domain-doc conventions.
- [The `cip-panel` agent skill](./.claude/skills/cip-panel/SKILL.md): helps your own coding agent
  inventory a system and write a join map, with safety rules built in.
- [Example join maps](./examples/): a simple ungated program and a gated one with a never-write list.
- [Third-party notices](./THIRD_PARTY_NOTICES.md) and [licence](./LICENSE) (MIT).
