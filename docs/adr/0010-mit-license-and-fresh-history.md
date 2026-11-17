---
status: accepted
---

# MIT licence, and a fresh git history

The project is released under the MIT licence, and its git history starts fresh with this
repository rather than carrying over the private repository's history.

## Licence

| Option | Outcome |
| --- | --- |
| Apache-2.0 | The recommendation going in, mainly for its explicit patent grant and its NOTICE convention for attribution. |
| MIT | Chosen by the owner. It is short, and it matches the licence of [klenae/python-cipclient](https://github.com/klenae/python-cipclient), whose work this project's wire format started from. The attribution that MIT requires is kept in `THIRD_PARTY_NOTICES.md`. Losing Apache-2.0's explicit patent grant was accepted. |

## History

The private repository's history is full of site details: addresses, IP-IDs, room and load names,
the alarm system's specifics, dates, and transcripts captured from a lived-in house. Rewriting that
history to remove them reliably would be slower and riskier than starting again, and a scrubbed
history that misses one commit leaks exactly what it was meant to hide.

The cost is that the reasoning behind the code is not in `git log`. It is in the documents instead:
these ADRs and the sanitised case studies under [docs/case-study/](../case-study/), which keep the
measurements and the rejected options without the site details.

No code from DosMan's original CresnetMon (Ms-PL), which inspired the private project's name and its
bus-monitoring origin, is included. See [disclaimer-and-credits.md](../about/disclaimer-and-credits.md).
