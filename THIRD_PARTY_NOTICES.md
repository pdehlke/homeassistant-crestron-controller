# Third-party notices

## CresnetMon, by DosMan (acknowledgement)

CresnetMon was written by DosMan and published on CodePlex in April 2015 under the Microsoft
Public License (Ms-PL); a GitHub mirror is at
[StephenGenusa/CresnetMon](https://github.com/StephenGenusa/CresnetMon). The work that became this
project started as a fork of it. No CresnetMon code is included here, so no Ms-PL notice is
required; this entry is an acknowledgement of where the project came from. See
[disclaimer and credits](docs/about/disclaimer-and-credits.md).

## klenae/python-cipclient

The CIP wire format in `custom_components/crestron_controller/cipcore/protocol.py` was first worked out
from [klenae/python-cipclient](https://github.com/klenae/python-cipclient) and then
re-implemented. No code was copied verbatim, but the analog and serial write layouts follow
that project's byte layouts exactly, so its notice is reproduced here.

```
MIT License

Copyright (c) 2020 klenae

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## rellis-erigon/Crestron-CIP-HA

The join record walk in `custom_components/crestron_controller/cipcore/protocol.py`
(`iter_records()`) follows the record layout and the EXTENDED_DATA header documented in
[rellis-erigon/Crestron-CIP-HA](https://github.com/rellis-erigon/Crestron-CIP-HA)'s
`custom_components/crestron_cip/protocol.py` (`iter_records()` and `_scan_cresnet()`), and the
record types it accepts come from that project's list, as does the UTF-16 format bit that
`decode_serial()` reads. The SmartObject layout decoded by `smart_object_records()` follows that
project's `split_object_joins()`, and the one `smart_object_packet()` encodes follows its
`pack_smart_object()`, and the test fixtures in `tests/core/test_smart_objects.py` follow
the layout of frames it captured, with their text replaced. The code was re-implemented rather than copied, so its notice is
reproduced here.

```
MIT License

Copyright (c) 2026 rellis-erigon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Crestron @crestron/ch5-crcomlib

`src/crestron_controller_cli/ch5_signals.py`, the table of which join kind each CH5 component
attribute carries, is generated from the component metadata
(`build_bundles/generate-metadata/schema.json`) in
[@crestron/ch5-crcomlib](https://www.npmjs.com/package/@crestron/ch5-crcomlib) 2.20.0, which is
Copyright (C) 2022 to the present, Crestron Electronics, Inc., and licensed under the
[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0). The table was
reorganised into a default per attribute plus per-component exceptions, and a few entries were
added by hand, as that file says. No other crcomlib code is included.

## Crestron @crestron/ch5-utilities (format only)

The `.ch5z` archive layout that `src/crestron_controller_cli/ch5.py` reads was learned from
`build/archiver/Ch5Archiver.js` in
[@crestron/ch5-utilities](https://www.npmjs.com/package/@crestron/ch5-utilities). That package is
not open source; none of its code is included here, only the knowledge of the file layout it
writes.

## alvaroyurrita/Construct-Themes-Showcase (test fixture)

`tests/cli/fixtures/ch5/construct-themes-showcase-lightdark.ch5z` is the `LightDark.ch5z` build
from release v1.2.0 of
[alvaroyurrita/Construct-Themes-Showcase](https://github.com/alvaroyurrita/Construct-Themes-Showcase),
trimmed to its HTML, contract and project configuration files. Its manifest's checksum therefore
no longer matches its contents.

```
MIT License

Copyright (c) 2026 Alvaro Yurrita

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## markjervis/CwsDebug (test fixture)

`tests/cli/fixtures/ch5/cwsdebug-example.ch5z` is
`examples/CwsDebugExample/Construct/output/CwsDebugExample.ch5z` from
[markjervis/CwsDebug](https://github.com/markjervis/CwsDebug), trimmed the same way.

```
MIT License

Copyright (c) 2026 Mark Jervis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
