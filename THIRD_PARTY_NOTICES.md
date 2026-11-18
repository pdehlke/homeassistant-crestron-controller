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
