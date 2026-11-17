---
status: accepted
---

# Protocol code lives inside the integration

The CIP protocol, the session client, the write policy and the join map validator live in
`custom_components/cip_panel/cipcore/`, with zero Home Assistant imports. The integration imports
it as a subpackage. The `cip-panel` CLI is built from the same files: its wheel re-roots that
directory as a top-level `cipcore` package. There is one copy of the code, the CLI's `check` command
runs exactly the validation the integration runs, and a HACS install is self-contained.

## Considered options

| Option | Why not |
| --- | --- |
| Publish `cipcore` as its own package on PyPI and list it in the manifest's requirements | Two release processes kept in lockstep, a version pin that Home Assistant installs at runtime, and a break whenever the two drift. All for a library with exactly two consumers, both in this repository. |
| Copy the protocol code into the CLI | Two copies drift. The private project this grew out of learned this the hard way: four hand-copied versions of one safety guard across its scripts, two of which ended up with no guard at all, and a hard-coded address restated in several scripts, one of which went stale and silently disarmed a check. |
| Put the CLI inside the integration directory | The CLI is meant to run on a laptop before Home Assistant is involved, installed with `uv`. Making it depend on the integration's Home Assistant modules would drag Home Assistant in. |

## Consequences

`cipcore` must never import from Home Assistant. Anything Home Assistant-specific (entities,
repairs, config entries) lives one level up, in `hub.py` and the platform modules. Code inside
`cipcore` imports its siblings relatively, so it works under both package names.
