# Disclaimer and credits

## Not affiliated with Crestron

This project is not affiliated with, endorsed by, sponsored by or supported by Crestron Electronics,
Inc. Crestron, Cresnet, the names of Crestron products (such as AADS, MC2E, TSW-752 and XPanel) and
any other product names mentioned in this repository are trademarks of their respective owners. They
are used only to identify the equipment this software is compatible with.

## Where the protocol knowledge came from

Everything this project knows about CIP and the processor console came from published open-source
work and from observing traffic between equipment the author owns, in his own house, for the purpose
of making that equipment work with other software he also owns. The author did not have the source
code of the programs running on his own processors. Where a behaviour is described in these
documents, it was observed on one system, and the documents say so; other models, firmware versions
and programs may differ.

## Use at your own risk

This software sends commands to a control system that may operate lighting, audio, shades, locks,
gates, garage doors, alarms or other equipment. A press that reaches the wrong join can do something
you did not intend, and the meaning of a join depends entirely on how the program on your processor
was written. The integration starts listen-only and refuses joins you put on its never-write list,
but it cannot know which of your joins are dangerous. You are responsible for reading your own
system, maintaining that list, and deciding when to enable writes. Read
[write-safety.md](../configuration/write-safety.md) before you do.

Do not use this software to control life-safety equipment, and do not rely on it for any function
where a failure to act, or an unintended action, could cause injury or damage. It is provided under
the MIT licence, without warranty of any kind; see `LICENSE`.

## Credits

- **python-cipclient, by klenae.**
  [klenae/python-cipclient](https://github.com/klenae/python-cipclient), MIT licensed. Its CIP
  client was where this project's understanding of the wire format started, and the analog and
  serial write encodings here still come from it. This project's code is a separate
  re-implementation, checked against real processors; see
  [cip-wire-format.md](../protocol/cip-wire-format.md) and `THIRD_PARTY_NOTICES.md`.
- **Crestron-CIP-HA, by rellis-erigon.**
  [rellis-erigon/Crestron-CIP-HA](https://github.com/rellis-erigon/Crestron-CIP-HA), MIT licensed.
  Its notes on EXTENDED_DATA frames, and on frames that hold several join records, are where this
  project's handling of both comes from. That part has not been checked against a real processor
  here; see [cip-wire-format.md](../protocol/cip-wire-format.md) and `THIRD_PARTY_NOTICES.md`.
- **Construct-Themes-Showcase, by Alvaro Yurrita, and CwsDebug, by Mark Jervis.**
  [alvaroyurrita/Construct-Themes-Showcase](https://github.com/alvaroyurrita/Construct-Themes-Showcase)
  and [markjervis/CwsDebug](https://github.com/markjervis/CwsDebug), both MIT licensed. A trimmed
  copy of a sample `.ch5z` project from each is part of the tests for the experimental x60/x70
  panel project reader; see [panel project files](../inventory/panel-project-files.md) and
  `THIRD_PARTY_NOTICES.md`.
- **@crestron/ch5-crcomlib, by Crestron Electronics.**
  [@crestron/ch5-crcomlib](https://www.npmjs.com/package/@crestron/ch5-crcomlib), Apache License
  2.0. The table of which join kind each HTML5 panel component setting carries is generated from its
  component metadata. No other code from it is included; see `THIRD_PARTY_NOTICES.md`.
- **CresnetMon, by DosMan.** DosMan wrote CresnetMon, a Windows Forms monitor for the Cresnet
  RS-485 bus, and published it on CodePlex in April 2015 under the Microsoft Public License
  (Ms-PL). Stephen Genusa later mirrored it to GitHub as
  [StephenGenusa/CresnetMon](https://github.com/StephenGenusa/CresnetMon). This project exists
  because of it: the author's own work on his Crestron system began as a fork of that mirror, first
  as a Python port of DosMan's bus monitor, and the CIP panel emulation generalised here grew up in
  the same repository. DosMan's work showed that a Crestron system could be understood from the
  outside, by watching its own traffic, and that is the approach this project still takes. No code
  from CresnetMon is included in this repository, which is why it carries no Ms-PL notice, but the
  debt is real and is acknowledged here and in `THIRD_PARTY_NOTICES.md`.

## Author

Pete Ehlke.
