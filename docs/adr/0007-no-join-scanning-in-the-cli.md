---
status: accepted
---

# The CLI has no join-scanning command

The `cip-panel` CLI helps a user find out what each join does by reading, never by pressing joins
in bulk. It can list the IP-IDs a processor expects (`ipids`), record everything a processor reports
to a slot (`listen`), show changes live while someone presses wall keypads and label them (`watch`),
and fetch and parse a touch panel's own project file, which names every page, button and join
(`panel fetch`, `panel parse`). The only press it can make is one join the user names explicitly,
with `--enter JOIN --allow-press`, to enter a gated subsystem; that press still passes the client's
write policy and the user's `--never-write` list. There is deliberately no command that presses a
range of joins to see what happens.

The reason is the alarm collision on the system this was developed on: a touch panel project that
used one block of join numbers for both a room's lighting buttons and an alarm keypad, including its
emergency buttons, and a lighting button later found to share its join with an alarm zone. A
scanner pressing unknown joins on that processor could have triggered an alarm, and on another
system it could open a gate or a garage door. See
[lesson-alarm-joins.md](../case-study/lesson-alarm-joins.md).

## Considered options

| Option | Why not |
| --- | --- |
| A scan command protected by the user's never-write list | A scan is what someone runs before they know which joins are dangerous. The deny list it would rely on is the thing the scan is meant to produce. |
| Scan only joins that look spare (unlabelled, unused on any page you have read) | "Looks spare" is a statement about the pages you have read. On the original system a join verified many times as a light was later found on an unread alarm page. |
| Scan, but only on processors without an alarm | The private project did exactly this once, on the one processor whose compiled program had been retrieved and searched and contained no alarm, security or access control at all. That was a judgement about one known program. A generic tool cannot make it for a stranger's system, and someone will run it on the wrong box. |
| Offer a scan behind a scary confirmation flag | Flags get copied from forum posts. The safe alternatives (panel project files, `watch` while pressing keypads by hand) cover the need. |

## Consequences

Inventory takes longer: fetching a TSW-752 project takes ten minutes or more, and labelling with
`watch` needs a person at the keypads. Systems whose panels use a project format `panel parse` does
not understand have to be mapped from `listen` and `watch` alone. Anyone who decides to scan their
own system can still write a script on `cipcore`; this project will not ship one.
