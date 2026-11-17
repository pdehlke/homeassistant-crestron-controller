---
status: accepted
---

# A UI config flow for the link, a YAML file for the join map

Each processor link is a config entry created in Home Assistant's UI: a name, the processor's host,
the port, the panel slot's IP-ID, and the path of a join map file under `/config` (by default
`cip_panel/<name>.yaml`, created with a starter template if it does not exist). The flow registers
once to prove the address and IP-ID before saving, pressing nothing. Writes are switched on later in
the entry's options. The join map itself, which says which joins become which entities, is a YAML
file the user edits by hand, and changes take effect when the entry is reloaded, with no restart.

## Considered options

| Option | Why not |
| --- | --- |
| YAML only, in `configuration.yaml` (what the private integration did) | Every change to the integration's configuration needed a full Home Assistant restart, because there was no config entry to reload. No per-link options, so no safe place for the `allow_writes` switch. Repairs and diagnostics attach naturally to a config entry. The private integration could live with it because it served one house whose addresses were fixed; a public one cannot. |
| Everything in the UI, including the join map | A real join map runs to dozens or hundreds of entries with aliases, join ranges, subsystems and a never-write list. A form for that is a large build, hard to review, hard to diff, hard to back up, and hard to paste into an issue. The inventory CLI drafts YAML; a UI would make users retype it. |
| The join map stored inside the config entry, edited through an options flow as text | Hides the file from backups, version control and text editors, and still needs the same validation. Gains nothing over a file. |

## Consequences

The join map is validated by `parse()` in `cipcore/joinmap.py`, the same code `cip-panel check` runs,
so a map can be checked on a laptop before it reaches Home Assistant. A map that fails validation
raises `ConfigEntryError`, so the message appears on the integration's card instead of being retried
forever. An empty map is valid: the link still connects and shows its connectivity sensor, which
proves the connection before anything is mapped. The host, port and IP-ID belong to the config
entry and are changed with the entry's Reconfigure step, which re-probes the new settings and keeps
every entity and its history; the join map file is unaffected.
