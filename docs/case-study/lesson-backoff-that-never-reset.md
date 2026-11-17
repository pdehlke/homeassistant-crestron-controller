# Lesson: the reconnect backoff that could never step back down

The private integration reconnected after a dropped session with an escalating delay: 1, 2, 5, 10,
then 30 seconds. After a session that worked, it was supposed to start again from 1 second. It
never did. Once five drops had happened over the life of the process, every later reconnect waited
30 seconds, however long and healthy the sessions in between had been.

Nothing broke loudly. The cost showed up as slow recovery, and it was visible in a log for anyone
who knew what to look for. It is worth a page because the defect is a common one: a line of code
that reads like correct behaviour and cannot run.

## What the code said

The reconnect loop looked like this, simplified:

```python
attempt = 0
while running:
    try:
        await session()  # returns only if the loop is shutting down
        attempt = 0  # "a session that worked clears the escalation"
    except ConnectionError:
        log("connection lost")
    if not running:
        return
    await sleep(backoff[min(attempt, len(backoff) - 1)])
    attempt += 1
```

Read quickly, `attempt = 0` after a clean return means "a good session resets the backoff". But
`session()` had exactly one way to return without raising: its own loop condition going false,
which only happens at shutdown. Every real disconnect raised. So the reset only ran on the way out,
and the very next statement returned. It could never matter.

## How it showed up

During the [DHCP outage](post-mortem-dhcp-address-change.md), the integration retried a dead address
at a flat 33.1-second interval: the 30-second last step plus the time each failed connect took. Long
before that outage the escalation had already reached its ceiling, and it stayed there for the life
of the process.

## The fix in the private integration

The reset is keyed on whether the session reached **synced**, not on how it ended. Two details are
easy to get wrong:

- The synced flag has to be read before the connection is torn down, because teardown clears it.
  Reading it afterwards is the obvious way to write this and is silently wrong. A test pins the
  order.
- Synced is a high bar on purpose. Reaching it takes a registration, a full dump, a quiet window
  and, on a gated program, an entry press and that subsystem's own dump. A link that flaps cannot
  clear that bar, so it cannot win itself a reset on every cycle.

Measured against the integration driven through sync, drop and reconnect by a local fake processor:
before the fix, three sessions that each synced reconnected after 1, 2 and 5 seconds; after it, 1,
1 and 1. A link that never syncs still escalates 1, 2, 5, 10.

This was not verified by dropping the production link. There was no free slot to test on, and
forcing a real drop would have meant deliberately colliding with the bridge's own IP-ID, which was
not an experiment worth running on a house people live in.

## What this framework does about it

`CipClient._run()` in `custom_components/cip_panel/cipcore/client.py` carries the fixed logic,
including a comment at the exact line that captures `synced` before `_close()`. The steps are
`Timing.reconnect_backoff`, `(1.0, 2.0, 5.0, 10.0, 30.0)`; `_parse_timing()` in `joinmap.py`
leaves them out of the keys the join map's `timing:` section accepts, so they are not
configurable. A link that stays down long enough raises a repair whatever
the backoff is doing; see [link-health-and-repairs.md](../troubleshooting/link-health-and-repairs.md).

## What to check in your own code

- For every "reset" or "clear" statement in a loop, find every way control can reach it. If the
  only path is shutdown, it is dead code that looks alive.
- Prove a behaviour by mutation: delete the line, and confirm a test fails. If nothing fails, the
  test was passing for the wrong reason.
- Key recovery on a positive signal that the thing worked (here, synced), not on the absence of an
  exception.
- When a fake in a test overrides a method, check that the method still runs on the path the test
  claims to cover. A fake that hooks the wrong method stops testing and does not fail.
