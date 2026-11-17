# Post-mortem: the light that came on whenever the bridge entered Lights

For a day, one light in the house kept switching itself on with nobody touching it. The private
integration was turning it on, without ever pressing its join. The processor's program ran a
[courtesy action](../concepts/glossary.md) whenever a panel slot entered the Lights subsystem: it
switched on a light in that panel's own room. The integration had borrowed that panel's slot, so it
inherited the courtesy, and it entered Lights often.

No code can stop a courtesy action, because it is the program's own logic. The only fix is the
choice of slot. That makes this the one failure in these case studies where the remedy is a
configuration decision you make before writing a line of YAML.

Background: [subsystems.md](../concepts/subsystems.md) and
[choosing-an-ip-id.md](../getting-started/choosing-an-ip-id.md).

## How it looked from outside

- One particular light came back on repeatedly through the day.
- The integration had already been changed that day to share its slot between Lights and audio
  (see [cursor-zone-audio.md](../patterns/cursor-zone-audio.md)), so the slot was entering Lights
  far more often than before: on every reconnect, every Home Assistant restart, and every return
  from audio.
- The working theory for most of the day was that the light's feedback join did not track the
  fixture. That was wrong. The join was right, and the house was doing what the join said.

## How it was diagnosed

The owner recognised it from years of living in the house: waking one particular wall panel from
standby always turned on a light in its room, and no other panel did that. If the program did the
same thing per slot, the bridge's borrowed slot would have a light of its own.

It was reproduced deliberately, starting with the light confirmed off at the fixture. Entering
audio and then Lights over CIP turned the light on about 1.1 seconds after the Lights entry press.
Three repeats from the on state left it on. So the entry switched the light on rather than toggling
it, and nothing in the integration ever pressed the light's own join.

Three candidate triggers were live, and each test ruled out less than it first appeared to:

| Test | Result | What it ruled out |
| --- | --- | --- |
| Register read-only on a different slot | Nothing turned on | Nothing: registering presses nothing, and that slot was not entering Lights. |
| Press that other panel's own Lights button by hand | Nothing turned on | Nothing about CIP: a finger on a real panel is not a CIP press. |
| Press audio entry, then Lights entry, over CIP, on the other slot | Nothing turned on | "Any CIP entry press does it." That left the slot itself. |

Matching slots to rooms finished it: the slot the bridge had borrowed belonged to a panel in a
room, and the light that came on was in that room. It is a courtesy: wake the panel, light its room.

## Root cause

A program behaviour, tied to the slot, older than the integration. Each panel slot's entry into
Lights ran logic that lit something in that panel's room. The bridge inherited the behaviour of the
real panel whose slot it was using.

## The fix

The bridge moved to a different slot, belonging to a panel whose Lights entry turned nothing on.
That panel was taken offline for the purpose. Nothing in the integration changed except the IP-ID.
Afterwards, bring-up turned nothing on, two full audio round trips turned nothing on, and a
lighting command still completed in 0.14 seconds.

Rejected alternatives:

| Option | Why not |
| --- | --- |
| Turn the light back off after every entry | A press per entry, and it fights a person who switched that light on deliberately. |
| Accept it and document it | A light comes on at every restart and every return from audio, forever. |
| Change the program | Correct at the source, and needs Crestron tooling plus the program source. |

## What this framework does about it

The framework cannot prevent a courtesy action, and does not pretend to. What it does:

- In [listen-only](../configuration/write-safety.md) mode, the default, no entry join is ever
  pressed, so no courtesy action can fire until you enable writes. `CipClient._bring_up()` in
  `custom_components/crestron_controller/cipcore/client.py` checks the policy before entering and
  logs that it cannot enter instead.
- Entry happens at bring-up after every connect, on demand before a write to another subsystem
  (`CipClient.async_enter()`), after an unconfirmed press (`Hub.async_set()` in `hub.py` calls
  `invalidate_subsystem()`), and on idle return (`Hub._idle_watch()`, governed by
  `idle_return_seconds`). Knowing where entries come from tells you how often a courtesy action
  would fire.
- The choice of slot is yours, and [choosing-an-ip-id.md](../getting-started/choosing-an-ip-id.md)
  includes testing a candidate slot for this before you commit to it.

## What to check on a different system

- Before enabling writes on a gated program, test the candidate slot. With someone watching the
  rooms, run `crestron-controller listen HOST --ipid 0x2A --enter JOIN --allow-press` (your own slot
  and the default subsystem's entry join) and see whether anything changes. Repeat from a state
  where any suspect light is off.
- Ask whoever lives with the system whether waking a particular panel does something. Habits like
  "that panel always turns the light by the door on" are evidence.
- A test that presses nothing, or a press made by hand at a real panel, does not test what the
  integration will do over CIP. Test the exact sequence the integration sends.
- If your program has no `subsystems:` at all, nothing is ever entered and this cannot happen.
