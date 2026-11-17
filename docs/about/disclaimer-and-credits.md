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

- [klenae/python-cipclient](https://github.com/klenae/python-cipclient), MIT licensed. Its CIP
  client was where this project's understanding of the wire format started, and the analog and
  serial write encodings here still come from it. This project's code is a separate
  re-implementation, checked against real processors; see
  [cip-wire-format.md](../protocol/cip-wire-format.md) and `THIRD_PARTY_NOTICES.md`.
- DosMan's original CresnetMon, a Cresnet bus monitor released under the Microsoft Public License
  (Ms-PL). It inspired the author's private project, which began as Cresnet bus monitoring and took
  its name before turning to CIP. No code from CresnetMon is included in this repository.

## Author

Pete Ehlke.
