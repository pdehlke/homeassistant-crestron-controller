# Post-mortem: the subsystem latch a power cut cleared

For about four hours one morning, every light Home Assistant drove through one processor stopped
responding, while the wall keypads worked normally and the loads on a second processor kept
working from Home Assistant. Nothing in Home Assistant, the network or either processor was
broken. The processor's program required each panel slot to enter the Lights subsystem before it
would act on lighting joins, and the slot the integration had borrowed had been sitting inside
that subsystem for weeks without anyone knowing. A power cut restarted the program and cleared it.

This happened on the private, single-house integration this project was generalised from, on the
AADS link described in [two-processor-house.md](two-processor-house.md). Terms such as
[gated subsystem](../concepts/glossary.md) and [entry join](../concepts/glossary.md) are in the
glossary; [subsystems.md](../concepts/subsystems.md) explains the idea from the beginning.

## How it looked from outside

- Every wall keypad worked all morning.
- The loads on the second processor (the MC2E's XPanel slot, which has no subsystems) worked from
  Home Assistant.
- Every other load failed with the integration's own error for a press that was sent and never
  confirmed: pressed twice without the processor confirming the new state.
- The link's connectivity sensor read connected throughout. The session was up and registered.
- Every affected load read off, and none ever changed, even while keypads visibly switched the
  same lights.
- Restarting Home Assistant did not help. That fact turned out to matter most, because it ruled out
  anything a fresh process, socket or registration would fix.

## How it was diagnosed

Several plausible explanations survived a long way, and each was killed with a measurement rather
than an argument. All of these used read-only console commands or read-only registrations on
spare slots.

| Hypothesis | Killed by |
| --- | --- |
| The integration's socket was a zombie the processor no longer serviced | The console's `WHO` listed the session, with an uptime matching the last Home Assistant restart. |
| The processor was refusing connections from the Home Assistant host | A read-only registration from that same host, on a spare slot, was prompted, registered and received 149 frames in under a second. |
| The CIP server or the program was wedged | Read-only registrations on two other slots each registered in about 20 ms and got the full menu dump. The program-uptime command showed the program running. |
| The intersystem link between the two processors was down | `IPTABLE` on both processors showed it online. |
| The second processor had lost its dimmer modules | `REPORTCRESNET` listed every module and keypad online. |
| The program was in a bad state after booting before its network came up | A program reset from the console restarted it cleanly, and the fault survived unchanged. |
| Only one direction was broken | Home Assistant's history showed no feedback of any kind from that link since the outage began, across a morning of keypad use. |

Then a console trace on the processor (its `SDEBUG` facility, watching the slot and the
intersystem link at once) settled it. Home Assistant's presses arrived at the slot, both attempts,
high then low. Nothing left the processor in response: no traffic to the second processor, no
feedback to the slot. The same trace with a working load showed the intersystem link carrying
lighting state the whole time. The processor was receiving everything and acting on nothing: the
transport worked, and the program logic was declining to act.

The final test was a fresh read-only session on a spare slot that pressed the Lights button on the
panel project's home page. About twenty lighting joins arrived within a fifth of a second, having
been completely absent from the registration dump, and a load press that had been ignored four
times in the previous hour worked first time, on and off, with feedback.

A small operational note from the trace: on the system this was developed on, `SDEBUG` took the
slot's Ethernet ID in decimal, so the trace for hex IP-ID 2A would be addressed as 42. Asking for
the hex digits produced a "no device" error that was easy to mistake for a silent trace.

## Root cause

The program gated the whole lighting subsystem per slot, on the home-page entry button. A slot
that had not pressed it was sent the menu and nothing else, and every load press it sent was
silently dropped. The latch lived in the running program: not in non-volatile memory, and not on
the Home Assistant side.

The real panel on that slot had entered Lights before it was unplugged, and the program had run
continuously since, so the slot stayed latched. For about five weeks the integration never needed
to press the entry button and nobody knew the requirement existed. An earlier experiment had even
concluded that panel slots on this processor were not gated, because load presses worked without
any page selection. The test was accurate and the conclusion was wrong: the slot was already
inside the subsystem.

Everything else follows. The keypads are Cresnet devices on the other processor and never touch
this one. The second processor's XPanel slot has no gating. Restarting Home Assistant could not
restore state held in the processor. A program reset cleared the latch again. And the integration
reported every load off rather than unavailable, because from inside a CIP session a gated slot is
indistinguishable from a quiet house: the dump is empty either way.

## The fix in the private integration

Coming up became two phases on a link with an entry join: register, then press the entry join
when the registration dump ends, and call the session synced only once the subsystem's own dump
has landed. Entry happens per session, so every reconnect re-enters. A warning is logged when a
gated link reports no digital joins after entry, because this failure is silent by construction.

## What this framework does about it

- Gating is declared in the join map under `subsystems:`, with a `default` subsystem and an entry
  join for each. See [subsystem-gating.md](../configuration/subsystem-gating.md).
- `CipClient._bring_up()` in
  `custom_components/cip_panel/cipcore/client.py` enters the default subsystem after the
  registration dump, re-polls for full state, and only then sets `synced`. A fresh session starts
  with `current_subsystem` set to `None` (unknown), so a reconnect always re-enters.
- `CipClient.has_state_for()` makes an entity in a subsystem that has not been entered this session
  report unavailable through `Hub.available()` in `hub.py`, rather than off. Silence is not
  evidence.
- When a press goes unconfirmed, `Hub.async_set()` in `hub.py` calls
  `CipClient.invalidate_subsystem()`, so the retry presses the entry join again. If something
  clears the latch without dropping the session, the next command recovers it.
- In [listen-only](../configuration/write-safety.md) mode the entry press is a write and is refused,
  so entities in a gated subsystem stay unavailable. That is deliberate: nothing has been said
  about them.
- `cip-panel listen --enter JOIN --allow-press` shows the difference directly: listen without it
  and a gated program sends only its menu. See
  [listening-to-a-processor.md](../inventory/listening-to-a-processor.md).

## What to check on a different system

- If control breaks after a processor restart while physical panels keep working, suspect a gate
  before suspecting the network.
- Register read-only on a spare slot and compare the dump with what a real panel shows. A dump
  that holds only home-page joins means the program is gated.
- A connected, registered, quiet session proves nothing about whether the processor will act on
  it.
- A test that passes because of state left behind by a real panel is not evidence about a fresh
  slot. Repeat important tests after a program reset.
