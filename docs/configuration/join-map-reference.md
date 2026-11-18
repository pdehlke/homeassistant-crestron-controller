# Join map reference

A join map is a YAML file, one per [link](../concepts/glossary.md#link), that says which
[joins](../concepts/joins.md) become which Home Assistant entities, which
[subsystems](../concepts/subsystems.md) exist, and which joins must never be written. This page
documents every key. It matches `custom_components/crestron_controller/cipcore/joinmap.py`, which is
the source of truth; `crestron-controller check` runs exactly the same validation as the
integration.

The file lives under your Home Assistant config folder, by default at
`crestron_controller/<name>.yaml`. Changes take effect when you reload the entry; no restart is
needed. Two complete examples ship with the repository:
[join-map-simple.yaml](../../examples/join-map-simple.yaml) for an ungated program and
[join-map-gated.yaml](../../examples/join-map-gated.yaml) for a gated one.

## General rules

- All join numbers are whole numbers from 1 to 32768, counted from 1 as Crestron join lists are.
  `true`, `false` and decimals are refused.
- Unknown keys are refused, at the top level, under `timing`, under `never_write` and on each
  entity, so a typo fails loudly. Two places are not checked this way; see
  [keys that are not checked](#keys-that-are-not-checked).
- Validation stops at the first problem and names it. Fix it and check again.
- An empty file is valid: no subsystems, nothing denied, no entities. The link still connects and
  shows its Link sensor.

## Top level

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `version` | integer | `1` | Schema version. Only `1` exists. |
| `subsystems` | mapping | none | Declares gated subsystems. Omit it entirely for an ungated program. See [subsystems](#subsystems). |
| `never_write` | mapping | nothing denied | Joins that must never be written. See [never_write](#never_write). |
| `timing` | mapping | measured defaults | Overrides for timeouts and windows. See [timing](#timing). |
| `entities` | list | empty | The entities to create. See [entities](#entities). |

## subsystems

Present only for a program that gates sections behind home-page buttons. Leave it out otherwise;
none of the subsystem machinery runs without it. Explained in
[subsystem gating](./subsystem-gating.md).

```yaml
subsystems:
  default: lights
  idle_return_seconds: 5
  repoll_after_entry: true
  entries:
    lights: {join: 40, quiet_seconds: 0.5}
    audio: {join: 41, quiet_seconds: 0.85}
```

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `entries` | mapping, required, at least one | none | One entry per subsystem. The key is the subsystem's name, used by entities' `subsystem:`. |
| `entries.<name>.join` | join, required | none | The digital entry join: the home-page button that enters this subsystem. |
| `entries.<name>.quiet_seconds` | number | `0.85` | How long the processor must be silent before this subsystem's entry dump counts as complete. Must be longer than the largest gap between two frames inside one dump. |
| `default` | subsystem name, required | none | The subsystem the slot enters on connect and returns to when idle. Entities with no `subsystem:` belong to it. |
| `idle_return_seconds` | number | `5.0` | How long the slot may sit idle in another subsystem before returning to the default. |
| `repoll_after_entry` | boolean | `true` | Re-send the update request after entering the default subsystem at bring-up, to fill in what the partial entry dump left out. Set `false` for a processor that never answers a second update request. |

Where the defaults came from, all measured on the system this was developed on:

- `quiet_seconds: 0.85` is twice the largest gap seen between two frames inside one entry dump on
  that processor's Audio subsystem (0.419 seconds). Its Lights subsystem's worst gap was 0.246
  seconds, so Lights used 0.5. The larger Audio gap reproduced on a second slot, so it was a
  property of the processor rather than of one panel. Measure your own with
  `crestron-controller listen --enter JOIN --allow-press`, which prints a suggested value.
- `idle_return_seconds: 5.0` was chosen to be longer than any single operation holds the slot, so a
  run of commands in another subsystem does not bounce back to the default between each one, and
  short enough that keypad changes in the default subsystem are not invisible for long.
- `repoll_after_entry: true`: a re-poll on that system returned the full state, 149 frames in about
  0.86 seconds, with an end marker. The second processor on the same system never answered a second
  update request, which is why the option exists.

## never_write

Joins Home Assistant must never write, whatever else the file says. Checked in the CIP client at the
last moment before bytes reach the network, and it wins over everything. See
[write safety](./write-safety.md).

```yaml
never_write:
  digital: ["200-219", 45]
  analog: []
  serial: []
```

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `digital` | list | empty | Digital joins never to write. |
| `analog` | list | empty | Analog joins never to write. |
| `serial` | list | empty | Serial joins never to write. |

Each list holds join numbers and `"low-high"` range strings, inclusive, in quotes so YAML reads them
as text. The lists apply to the whole link, across every subsystem: a join listed here is never
written in any subsystem. Reading a listed join is fine; it may appear in `also_reports`, a
`binary_sensor` or a `sensor`.

## timing

Overrides for the client's timeouts and windows, in seconds. Leave the whole section out unless you
have measured a reason to change something. Each value must be a positive number.

| Key | Default | What it controls | Where the default came from |
| --- | --- | --- | --- |
| `heartbeat_interval` | `15.0` | How often a heartbeat is sent to keep the session alive. | On the system this was developed on, the processor tolerated 149 seconds of total silence from a registered client without dropping it, so 15 is comfortable rather than marginal. |
| `sync_quiet_seconds` | `2.0` | After registering, how long a quiet link counts as "the registration dump is finished" when no end marker arrives. A slot with nothing to report might never send the marker. | Carried over from the private integration without a recorded measurement. For comparison, the slowest registration dump measured on that system took 0.964 seconds. |
| `press_hold_seconds` | `0.12` | How long a press holds a digital join high before releasing it. | The first live presses on that system used a 120 ms release, and the processor treated them as presses, with feedback staying high after the release. |
| `entry_min_seconds` | `0.9` | The shortest time an entry dump is collected, whatever the silence inside it. | On that system a Lights entry went quiet longer than the quiet threshold after its first frame, and the window closed 0.47 seconds in, on a dump whose last frame landed at about 0.53 seconds. Entry dumps arrive in bursts, so the window needs a floor. |
| `entry_timeout` | `3.0` | How long to wait for an entry dump before declaring the entry failed. | Entry dumps on that system landed in 0.514 to 0.529 seconds, and the slowest dump of any kind measured was the 0.964 second registration dump, so this is generous. |
| `repoll_timeout` | `5.0` | How long to wait for the end marker after a re-poll. On timeout, whatever arrived is still merged. | A re-poll on that system took about 0.86 seconds for 149 frames, three times running. |
| `bringup_retry_seconds` | `5.0` | The minimum time between bring-up attempts when an entry fails. | A rate limit, not a measurement: a failed entry produces no traffic, which would otherwise qualify the link for another attempt immediately. |
| `connect_timeout` | `10.0` | How long to wait for the TCP connection to the processor to open, including the TLS handshake on an encrypted link. | A chosen value, not a measurement. |
| `greeting_timeout` | `5.0` | How long to wait, once connected, for the processor's first message before giving up. | Every processor observed sends its register request as soon as a client connects. Silence usually means one end expects TLS and the other does not. |

The reconnect backoff is fixed and cannot be set here: 1, 2, 5, 10, then 30 seconds between
attempts, staying at 30. It starts again from 1 second after any session that reached synced, so a
link that was healthy and dropped once reconnects quickly. A
[case study](../case-study/lesson-backoff-that-never-reset.md) explains why that reset depends on
reaching synced and not merely on the session ending.

Two related values are fixed in the integration and also cannot be set: a light or switch waits 3
seconds for confirmation after a press, and makes at most 2 attempts.

## entities

A list. Each item is a mapping with a `type` and the keys that type allows.

### Keys every entity takes

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `type` | one of `light`, `switch`, `binary_sensor`, `button`, `sensor`, `number` | required | The Home Assistant platform. |
| `name` | text, required, not blank | required | The entity's name. Home Assistant shows it under the processor's device. |
| `id` | text of `a-z`, `0-9` and `_` | made from `name` | A stable identifier within this join map. It becomes part of the entity's unique ID, so changing it creates a new entity. Generated from the name by lowercasing and turning runs of other characters into `_`. Set it explicitly when two names would produce the same id, or when you want to rename an entity without losing its history. |
| `subsystem` | subsystem name | the default subsystem | Which subsystem's joins this entity reads and writes. Only allowed when the map declares `subsystems:`. |
| `icon` | text such as `mdi:lightbulb` | none | An icon override. |

### light and switch

A light and a switch take the same keys except `brightness`, which only a light takes. Which keys
are required depends on `press`. See [press modes](./press-modes.md) for how each mode behaves.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `press` | `toggle`, `on_off` or `momentary` | `toggle` | How the load is driven. |
| `feedback` | join | none | The digital join that reports the load's state. Required for `toggle` and `on_off`; not allowed for `momentary`. |
| `also_reports` | list of joins | empty | Other digital joins that report the same load, such as the same light on another panel page. A change on any of them updates the entity. Read only, never written. Not allowed for `momentary`. |
| `press_join` | join | same as `feedback` | `toggle` only: the join to press, when it differs from the feedback join. |
| `on_join` | join | none | `on_off`: the join pressed to turn on (required). `momentary`: the join pressed to turn on, and to turn off too when there is no `off_join` (required). |
| `off_join` | join | none | `on_off`: the join pressed to turn off (required). `momentary`: optional separate off join. |
| `brightness` | mapping | none | Light only. `{join: N, writable: false}`. `join` is the analog join carrying the level, 0 to 65535. `writable` defaults to `false`. |

About `brightness`: only `writable: true` makes the light dimmable in Home Assistant. Setting a
brightness then writes the level and nothing else; it does not also press the on join, because on a
toggle that could switch the light straight back off. Whether a level write turns the load on is up
to the program. Analog writes use an encoding no processor has yet been seen to accept in this
project; see [joins](../concepts/joins.md#analog-and-serial-writes). With `writable: false` the
light is on/off in Home Assistant and Home Assistant does not display the level; if you want to see
it, add a `sensor` on the same analog join.

### binary_sensor

A read-only digital join.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `join` | join, required | none | The digital join to read. |
| `device_class` | a Home Assistant binary sensor device class, such as `door` or `garage_door` | none | How Home Assistant presents it. Must be a class Home Assistant knows, or the entity fails to load. |

### button

A press and nothing else: a scene, a macro, an "all off".

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `join` | join, required | none | The digital join to press. |
| `hold_seconds` | number | `timing.press_hold_seconds` | How long to hold this press. Only change it if a program needs a longer press; remember that holding is not pressing. |

A button is available whenever its link is connected and synced, because it has nothing to read.

### sensor

A read-only analog or serial join. Exactly one of `analog` or `serial`.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `analog` | join | none | The analog join to read. |
| `serial` | join | none | The serial join to read; the value is the text. |
| `scale` | `raw` or `percent` | `raw` | Analog only. `percent` shows the value as a percentage of 65535, to one decimal place. Not allowed with `serial`. |
| `unit` | text | `%` when `scale: percent`, otherwise none | The unit of measurement. |
| `device_class` | a Home Assistant sensor device class | none | Must be a class Home Assistant knows. |

Serial sensors are available whenever the link is connected and synced, whatever subsystem they
name. On the system this was developed on, label serials arrived once per session rather than once
per subsystem entry, so they are not filed by subsystem.

### number

An analog join with a range, shown as a slider. Read-only unless `writable: true` and writes are on.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `analog` | join, required | none | The analog join. |
| `scale` | `raw` or `percent` | `raw` | `percent` maps 0 to 65535 onto 0 to 100. |
| `unit` | text | `%` when `scale: percent`, otherwise none | The unit of measurement. |
| `min` | number | `0` | Slider minimum. |
| `max` | number | `100` for `percent`, `65535` for `raw` | Slider maximum. |
| `step` | number | `1` | Slider step. |
| `writable` | boolean | `false` | Whether moving the slider writes the join. Same caveat as writable brightness. |

`min` and `max` must satisfy `0 <= min < max <= top`, where top is 100 for `percent` and 65535 for
`raw`.

## Rules across the whole map

- Every entity's `id` must be unique in the file.
- A join may be **read** by any number of entities. A binary sensor and a light on the same feedback
  join is fine.
- A join may be **written** by only one entity within one subsystem, because two entities pressing
  one toggle would each undo the other. The same join number written by two entities in two
  different subsystems is fine; it is a different signal in each.
- No two subsystems may share an entry join.
- No entry join may be on `never_write.digital`.
- No entity may write a join on the never-write list of the same kind.

## What Home Assistant may write

With writes on, the allow list is exactly:

- every subsystem's entry join (digital);
- for a light or switch, its `press_join`, `on_join` and `off_join` (digital), and its brightness
  join (analog) if `writable: true`;
- for a button, its `join` (digital);
- for a number with `writable: true`, its `analog` join.

Nothing else can be written. `crestron-controller check FILE` prints this list, and the never-write
list, in ranges.

## Validation errors

Each message starts with where the problem is: `join map`, a section such as `subsystems` or
`timing.entry_timeout`, or `entities[N] (id)` for the Nth entity (counted from 0) with its id or
name. Cross-entity errors start with the entity's id.

### File and top level

| Message | Meaning and fix |
| --- | --- |
| `join map: the file must be a YAML mapping` | The file is a list or a bare value. It must start with keys such as `version:`. |
| `join map: unknown top-level key(s): ...` | Only `version`, `subsystems`, `never_write`, `timing` and `entities` are allowed. Usually a typo or bad indentation. |
| `join map: version ... is not supported, use 1` | Set `version: 1`. |
| `join map <path> does not exist` | Shown by the integration when the configured file is missing. |
| `join map <path> is not valid YAML: ...` | A YAML syntax error; the detail gives the line. |
| `entities: must be a list` | Each entity must start with `- `. |

### subsystems

| Message | Meaning and fix |
| --- | --- |
| `subsystems: must be a mapping` | `subsystems:` must contain keys, not a list. |
| `subsystems: needs at least one entry under entries` | Add `entries:` with at least one subsystem, or delete `subsystems:` for an ungated program. |
| `subsystems.entries.<name>: needs a join` | Each entry needs `join: N`. |
| `subsystems.entries.<name>: join must be a whole number, got ...` / `... is outside 1-32768` | The entry join is not a valid join number. |
| `subsystems.entries.<name>: quiet_seconds must be a number, got ...` | Use a plain number of seconds. |
| `subsystems: two subsystems share an entry join` | Each subsystem needs its own entry join. |
| `subsystems.default: ... must name one of ...` | `default` is missing or misspelled. |
| `subsystems: idle_return_seconds must be a number, got ...` | Use a plain number of seconds. |

### never_write

| Message | Meaning and fix |
| --- | --- |
| `never_write: must be a mapping of digital/analog/serial lists` | Put the lists under `digital:`, `analog:` or `serial:`. |
| `never_write: unknown key(s): ...` | Only `digital`, `analog` and `serial`. |
| `never_write.<kind>: expected a list, got ...` | Write `[45]`, not `45`. |
| `never_write.<kind>: '...' is not a join or a 'low-high' range` | Ranges are quoted strings like `"200-219"`. |
| `never_write.<kind>: range '...' runs backwards` | Write the lower number first. |
| `never_write.<kind>: join must be a whole number, got ...` / `join N is outside 1-32768` | An item is not a valid join number. |

### timing

| Message | Meaning and fix |
| --- | --- |
| `timing: must be a mapping` | `timing:` must contain keys. |
| `timing: unknown key(s): ...` | Only the keys in [timing](#timing). `reconnect_backoff` is deliberately not settable. |
| `timing.<key>: must be a positive number of seconds` | Zero, negative and empty values are refused. |
| `timing: <key> must be a number, got ...` | Use a plain number. |

### Each entity

| Message | Meaning and fix |
| --- | --- |
| `entities[N]: each entity must be a mapping` | An item in the list is not a set of keys. Check indentation. |
| `...: type must be one of light, switch, binary_sensor, button, sensor, number` | Missing or misspelled `type`. |
| `...: unknown key(s) for a <type>: ...` | That key does not belong to this type. A common one: `join` on a light (lights use `feedback`). |
| `...: every entity needs a name` | Add a non-blank `name`. |
| `...: id '...' may use only a-z, 0-9 and _` | Fix the explicit `id`, or a name that produces nothing usable (one with no letters or digits). |
| `...: subsystem '...' is not one of ...` | The entity names a subsystem the map does not declare. |
| `...: names a subsystem, but the map declares none` | Remove `subsystem:`, or declare `subsystems:`. |
| `...: press must be one of toggle, on_off, momentary` | Misspelled `press`. |
| `...: press: toggle needs a feedback join, ...` | A toggle can only be made discrete by reading state first. Add `feedback`, or use `press: momentary` if there is no feedback. |
| `...: on_join/off_join need press: on_off or momentary` | You gave on or off joins to a toggle. Set `press`. |
| `...: press: on_off needs feedback, on_join and off_join` | All three are required. |
| `...: press_join is only for press: toggle` | Remove `press_join`, or use `toggle`. |
| `...: press: momentary needs on_join` | Add `on_join`. |
| `...: press: momentary is for joins with no feedback; ...` | You gave `feedback` or `also_reports` to a momentary entity. Use `toggle` or `on_off` instead. |
| `...: also_reports must be a list of joins` | Write `[34]`, not `34`. |
| `...: brightness must be a mapping with a join` | Write `brightness: {join: N}`. |
| `...: a binary_sensor needs a join` / `a button needs a join` | Add `join`. |
| `...: hold_seconds must be a number, got ...` | Use a plain number. |
| `...: a sensor needs exactly one of analog or serial` | Give one, not both and not neither. |
| `...: a number needs an analog join` | Add `analog`. |
| `...: scale must be raw or percent` | Misspelled `scale`. |
| `...: scale applies to analog joins only` | Remove `scale` from a serial sensor. |
| `...: min must be a number, got ...` (and `max`, `step`) | Use plain numbers. |
| `...: need 0 <= min < max <= 100` (or `65535`) | Fix the range. |
| `...: <key> must be a whole number, got ...` / `... is outside 1-32768` | A join key holds something that is not a valid join number. |

### Across entities

| Message | Meaning and fix |
| --- | --- |
| `entities[N]: id '...' is already used by entities[M]; give one of them an explicit id` | Two entities have the same id, often because two names slug the same. |
| `<id>: writes <kind> join N, which <other id> also writes` | Two entities in the same subsystem would write one join. Keep one; make the other a `binary_sensor` if you want to read it twice. |
| `subsystems.entries.<name>: entry join N is on the never-write list, so this subsystem could never be entered` | Remove it from `never_write`, or remove the subsystem. |
| `<id>: would write <kind> join N, which is on the never-write list. ...` | The entity would press a forbidden join. If the load has a safe alias elsewhere in the program, map that one as the join to press and keep the forbidden one in `also_reports`. |

### Errors from Home Assistant, not the schema

A `device_class` that Home Assistant does not recognise passes `crestron-controller check` but makes
that platform fail to load in Home Assistant, and the error appears in the log. Use the classes
listed in Home Assistant's documentation for binary sensors and sensors.

## Keys that are not checked

Two places accept unknown keys without complaint, so a typo there is silently ignored:

- inside a subsystem entry (`entries.<name>`), such as `quiet_second: 0.5`, which leaves the default
  in place;
- inside `brightness`, such as `writeable: true`, which leaves the light read-only.

`quiet_seconds` and `idle_return_seconds` are also not checked for being positive. Run
`crestron-controller check` and read its summary of subsystems to confirm the quiet values it will
use.
