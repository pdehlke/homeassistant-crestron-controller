---
status: accepted
---

# Reading HTML5 panel projects

`crestron-controller panel parse` reads the `.ch5z` projects that TSW x60 and x70 panels run, as
well as the x52 `Environment.xml`
([issue #5](https://github.com/pdehlke/homeassistant-crestron-controller/issues/5)). Support is
experimental: no project taken from a real house has been read, and no join it reports has been
checked against a real processor. Every draft, summary and document that covers it says so.

## What it is built on

Nobody working on this project has an x60 or x70 panel. The format was learned instead from
Crestron's published npm packages, read from source, and from public projects found on GitHub:

- `@crestron/ch5-utilities` (`Ch5Archiver.js`) gives the archive layout: a zip holding one `.ch5`,
  itself a zip of the web project, and a manifest. That package is not open source, so its code
  is followed, never copied.
- `@crestron/ch5-crcomlib` 2.20.0 (Apache-2.0) ships metadata naming every join attribute of every
  component, with its kind and direction. `ch5_signals.py` is generated from it.
- Fourteen public repositories carry built `.ch5z` files and over forty carry Contract Editor
  contracts. Twelve builds were read: Construct projects with and without a contract, hand-written
  projects, a Construct project converted from VT Pro-e, and React and Vite builds. Two
  MIT-licensed ones, trimmed, are test fixtures; the rest were studied only.

## Decisions

- **Contract names resolve through `config/contract.cse2j`, and every contract signal is reported.**
  The contract is plain JSON: feedback as `states.<kind>.<smart object>.<join>` → name, presses as
  `events.<kind>.<name>` → `{joinId, smartObjectId}`. Signals no HTML attribute names are listed
  under `(contract only)`, so a widget the reader cannot follow still has its joins in the draft.
- **Lists are read from the contract, never from the template.** The contract lists every item's
  signals separately (`<list>.Items[<i>].<name>`). A numeric list template such as `1{{idx}}`,
  with no contract, is reported as unresolved.
- **Construct's shell (`app/template/`) is skipped.** Its signals (`logsbtn.clicked`,
  `selectedTheme`) stay inside the panel.
- **A project whose HTML has no joins and no contract is refused** with an explanation, since its
  joins are set from JavaScript.
- **`sendeventontouch` is a digital press**, added by hand: crcomlib 2.20's metadata omits it, but
  the 2.8 crcomlib bundled in Construct projects defines it on `ch5-button`, and Construct buttons
  use it.

## Considered options

| Option | Why not |
| --- | --- |
| Wait for a project from a real panel before building anything | Nobody on the project has one, and the public samples answered most of the open questions in #5, including the contract format. Building it experimental and labelled as such gives users with x60/x70 panels something to try and report on. |
| Hand-write the attribute-to-kind table | `receivestatevalue` is analog on a slider, digital on a toggle and serial on a text input. Crestron's metadata covers 405 attribute and component pairs; a hand-written table would get some wrong. |
| Expand numeric list templates (`1{{idx}}`) by assuming a 0- or 1-based index | Each list component substitutes its index differently, and nothing confirms which. A wrong guess would put a plausible join number on the wrong item. Reporting the template costs only a line. |
| Report Construct shell signals as unresolved | They would appear on every page of every Construct project and bury the names that matter. |
| Run the project's JavaScript to find joins in framework builds | That means running untrusted code from an archive, and needs a browser engine. Refusing with an explanation sends the user to `listen` and `watch`, which work for every panel. |
| Fetch `.ch5z` from the panel | Crestron's tools only upload, over SFTP, and nothing describes a download. `panel fetch` stays x52-only until someone tries it on a real panel. |
| Commit the two MIT samples whole | 9.7 MB and 21.9 MB, nearly all fonts and icons. Trimmed to the files the reader opens they are 236 KB and 9 KB. |

## Consequences

- A draft from a contract project is mostly `smart_object:` entries, which depend on SmartObject
  reading ([ADR 0012](./0012-smartobject-joins-are-their-own-namespace.md)), itself untested on
  real hardware.
- The CSV inventory gained a `smart_object` column, at the end so existing columns keep their
  positions.
- Page visibility joins in the samples were contract signals in per-page SmartObjects. Whether a
  real processor drives them that way is unknown.
- The first report from someone with a real x60/x70 project, ideally run alongside
  `crestron-controller watch`, would confirm or correct all of this.
