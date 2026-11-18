---
status: accepted
---

# CIP over TLS with a pinned certificate

Supersedes [ADR 0008](./0008-plain-cip-only-for-now.md) for the encrypted transport. Username and
password authentication (CIP packet types `0B` and `0C`) stays unsupported, for the reason 0008
gave: nobody has a working implementation or a capture of a real panel's handshake.

The integration and the CLI can speak CIP inside TLS, on port 41796 by default. The frames inside
the TLS stream are the same as plain CIP, so the change is confined to how the connection is opened
and configured ([issue #1](https://github.com/pdehlke/homeassistant-crestron-controller/issues/1)).
Processors present self-signed certificates that no authority vouches for, so the client does not
check the issuer. Instead the config flow records the SHA-256 fingerprint of the certificate the
processor presents when the entry is created, and every later connection refuses a processor whose
certificate has a different fingerprint. A refused connection raises a repair. Reconfiguring the
entry takes a fresh fingerprint, which is how a user accepts a certificate that changed for a known
reason, such as a replaced processor.

0008 rejected implementing TLS because nothing could test it. That is still true of real hardware:
this lands verified only against the test suite's fake processor, which serves TLS with a throwaway
self-signed certificate. What changed is that the encrypted transport is ordinary TLS, which the
fake can model faithfully, and that users with processors that require it otherwise had no path at
all. Every user-facing place that mentions TLS says it has not been verified on real hardware.

## Considered options

| Option | Why not |
| --- | --- |
| Encrypt without checking the certificate at all (`ssl.CERT_NONE` and nothing after), as the client cited in issue #1 does | Encryption with no assurance about who is on the other end. Anything that can answer at the processor's address gets the session, including every join Home Assistant writes. Pinning cost about half a day more. |
| Ship without checking now and add pinning later | Entries created in the meantime would have no pin, and adding one later means either pinning silently on the next connect, which proves nothing, or forcing every user through a reconfigure. Cheaper to get it right once. |
| Verify against a certificate authority, or let users supply a CA file | Processors ship self-signed certificates. Asking a novice to export a processor's certificate and install it as a CA is far beyond the audience this project writes for. |
| Pin silently on the first connection after setup rather than in the config flow | The config flow's probe is already the first successful connection, made while the user is watching. Pinning there ties the pin to a moment the user chose. |
| Keep the old pin through a reconfigure | Reconfigure is the only place a user can act on the certificate repair. If it kept the old pin, there would be no way to accept a legitimately new certificate short of deleting the entry and losing its entities. |
| Detect a plain client on a TLS port by sending something that makes a TLS server answer | It would send bytes that are not CIP to a processor that might be a plain one. Instead the client waits for the processor's register request, which every processor observed sends as soon as a client connects, and gives up after `greeting_timeout` (5 seconds by default) with an error that names TLS as the likely cause. |

## Older TLS versions are a per-link opt-in

Some home systems are old enough that their processors may not speak TLS 1.2. A link can turn on
`legacy_tls` ("Allow older encryption" in the config flow, `--legacy-tls` in the CLI), which lowers
the client's minimum to TLS 1.0 and sets OpenSSL's security level to 0. Both are needed: tested
against a fake that offers only TLS 1.0 or 1.1, lowering the minimum version alone still failed,
because OpenSSL 3 refuses those versions at its default security level. Level 0 also admits the
weak ciphers and SHA-1 certificates an old processor is likely to use. The client still negotiates
the newest version both ends support, and the certificate pin applies unchanged. Novice-facing
documentation is [encrypted CIP](../configuration/encrypted-cip.md).

| Option | Why not |
| --- | --- |
| Allow TLS 1.0 and 1.1 on every TLS link | Weakens every link to help a few. Most processors that offer TLS at all are likely to offer 1.2, though this is not verified. |
| Retry automatically with old TLS when a modern handshake fails | Falling back to weaker encryption without being asked is the classic downgrade pattern: anything that can make the first handshake fail gets the weaker one. It also hides from users that their link is using weaker encryption. |
| Lower only the minimum version, keeping OpenSSL's default security level | Does not work. The handshake still fails against a TLS 1.0 or 1.1 server. |
| Leave old processors unsupported | Plain CIP may already cover them, since a processor too old for TLS 1.2 may not offer encrypted CIP at all, but that is not verified. The opt-in costs little and is off by default. |

Whether TLS 1.0 and 1.1 are available at all depends on the OpenSSL that Python was built against.
They were available on the development machine (OpenSSL 3.5.5). Home Assistant's own builds were
not checked, and a build without them fails with the same TLS error whatever the setting says.

To make a failed handshake recognisable, the client opens the TCP connection first and then starts
TLS on it. Any failure during that second step is reported as a TLS error. Without the split, a
processor that could not agree a version reset the connection, which was reported as nothing
listening.

## Consequences

- Entries created before this change have no `tls` key and stay plain, with no migration.
- The CLI's `--tls` accepts any certificate and prints its fingerprint. It is an inventory tool run
  by the person standing next to the processor, so it reports rather than pins.
- Without `legacy_tls`, the client uses Python's default TLS settings, which on the Python this
  project runs on refuse anything older than TLS 1.2. Which TLS versions and ciphers real
  processors offer has not been observed. The CLI prints the version agreed so that reports from
  real hardware can settle it.
- A processor that legitimately rotates its certificate, for example on a firmware update, will
  stop the link until the user reconfigures. That is the intended trade.
- Real verification needs someone with a TLS-enabled processor to run
  `crestron-controller listen --tls` and report the result.
