---
status: accepted
---

# Impersonate a touch panel over CIP

Home Assistant reaches a Crestron system by registering with the control processor over CIP as one
of the touch panels its program already defines, then reading and pressing that panel's joins. This
needs no change to the program, no Crestron software, no programmer and no new hardware, and it
inherits everything the program already does downstream of a panel press (on the system this was
developed on, that included keeping the wall keypad LEDs in step). The price is one panel slot: an
IP-ID whose real device is unplugged, never installed, or a software XPanel nobody uses.

## Considered options

These are the routes the owner of the original system actually evaluated, in roughly the order he
evaluated them.

| Option | Outcome |
| --- | --- |
| Hire a programmer to add an XSIG or EISC interface to the program, then use a community integration that speaks it | The first plan. Small in scope, since it is join mapping with no logic, but it needs Crestron tooling and the program source, and every later change to the map costs another paid visit. Panel impersonation reached the same joins with none of that. Still the right answer when a program has no panel slot that reaches what you need. |
| Cresnet bus injection: tap the RS-485 bus with a USB adapter and write frames to the dimmer modules directly ("Path B") | Transmission was proven: the processor logged the injected bytes and the bus roll call dipped while transmitting. But the dimmer modules ignored commands that arrived outside their slot in the bus master's poll cycle, a byte-perfect replay of the processor's own frames produced no light, and sustained injection made every module re-initialise. Parked and still open: it remains the only route that could one day remove the processors entirely. Out of scope for an integration anyone can install. |
| Replace the processor (or the whole system) outright | Removes the dependency, at the cost of hardware, rewiring and losing the program's logic. A strategy decision for an owner, not a software design. This project exists for people keeping their system. |
| A software XPanel slot rather than a physical panel's slot | Used where it works: on the original system one processor's XPanel slot reached exactly the loads that could not safely be reached elsewhere, with no panel sacrificed. But that slot reached a single room, because an XPanel's join map is whatever the programmer gave it. App slots on the other processor ran a different, gated project. A physical panel's slot reached the whole house, and the panel will hand over its own project file, which yields the whole join map by name without pressing anything. |
| Displace the intersystem link between two processors and use its joins | It carried whole-house joins, but it was occupied by the other processor, and taking it would have broken audio and other functions. |
| Connect and disconnect per command, from a script | Registration plus the state dump took about 1.1 seconds, so every light switch would gain a second of latency and the processor would see dozens of registrations an hour. The job is a long-lived session with heartbeats and state, which is a daemon, and a Home Assistant integration is a daemon with a lifecycle already. |

## Consequences

The project inherits the program's quirks as well as its features: gated subsystems, partial entry
dumps, courtesy actions on entry, join numbers reused across pages. Each has a case study under
[docs/case-study/](../case-study/). The program's join map is not published anywhere, so an
inventory step is unavoidable, and the CLI exists to make it safe.

Borrowing a slot is reversible: plug the panel back in and nothing else has changed. What a
processor does while two devices claim one IP-ID is not established by this project; see
[ip-id-conflicts.md](../troubleshooting/ip-id-conflicts.md).
