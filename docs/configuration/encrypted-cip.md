# Encrypted CIP

Most Crestron systems in homes let a touch panel talk to the
[control processor](../concepts/glossary.md#control-processor) without encryption. Crestron
Controller does the same by default, and if setup worked for you without changing anything, you can
stop reading here.

Some processors can be set to require encryption, which Crestron calls secure CIP. This page
explains how to turn encryption on, what Home Assistant does to make sure it is talking to your
processor, and what to do if your processor is too old for modern encryption.

> Encrypted CIP has so far been tested only against a simulated processor in this project's test
> suite, never against a real one. If you use it, an issue saying whether it worked, and on which
> processor, would help everyone. See [what to report](#what-to-report).

## Do I need it?

Probably not. You need encrypted CIP only if your processor refuses plain connections. The usual
sign is that setup says "Something answered on that port but did not speak CIP" when you leave
encryption off. Whoever installed your system can also tell you whether secure CIP was enabled.

Encryption keeps other devices on your network from reading or tampering with what Home Assistant
and the processor say to each other. On a home network you trust, plain CIP is what most systems
use.

## Turning it on

In the setup form (or Reconfigure, on the integration's menu, for an existing processor):

1. Turn on **Encrypted CIP (TLS)**. TLS is the name of the encryption standard; it is the same one
   your web browser uses for websites that start with `https`.
2. Leave **CIP port** blank. It then uses 41796, the usual port for encrypted CIP. Fill it in only
   if you know your processor uses a different one.
3. Leave **Allow older encryption** off for now. The section [older processors](#older-processors)
   explains when you need it.
4. Submit.

## How Home Assistant knows it is your processor

Encryption alone stops eavesdropping, but it does not prove who is on the other end. To cover that,
Home Assistant remembers your processor's certificate.

A certificate is the processor's digital ID card, which it shows every time something connects.
Each one has a fingerprint: a long string of letters and numbers, unique to that certificate. When
you submit the setup form, Home Assistant records the fingerprint. Every time it reconnects after
that, it checks the processor shows the same one, and refuses to connect if it does not.

If the fingerprint ever changes, you get a repair under Settings > Repairs called "the processor's
certificate has changed", and the link stays down until you act. A certificate can change for
ordinary reasons: the processor was replaced, reset to factory settings, or had its firmware
updated. If you know one of those happened, open Reconfigure on the integration's menu and save.
Home Assistant then remembers the new certificate. If none of them happened, find out what is
answering at the processor's address before you accept it, because it may not be your processor.

You do not need to copy or type the fingerprint anywhere. If you want to see it, the
`crestron-controller listen --tls` command prints it, and the integration's diagnostics download
includes it.

## Older processors

Encryption standards improve over time, and older versions are retired as weaknesses are found.
Home Assistant, like current web browsers, uses TLS 1.2 or newer by default. A processor made
before those versions were common may only know TLS 1.0 or 1.1, and the two sides then cannot agree
on how to encrypt. Setup reports this as "The encrypted connection could not be set up".

For those processors, turn on **Allow older encryption (TLS 1.0 and 1.1)**, together with
Encrypted CIP, and submit again. With it on:

- Home Assistant still uses modern encryption whenever the processor supports it. The older
  versions are used only when the processor offers nothing newer.
- The certificate check described above still applies, so Home Assistant still refuses a processor
  whose certificate has changed.
- The setting applies only to this one processor. Other processors and the rest of Home Assistant
  are unaffected.

The trade-off is that TLS 1.0 and 1.1 are weaker. Someone who could record the traffic on your
network would have an easier time decoding it than with TLS 1.2. Plain CIP, with no encryption at
all, is weaker still, so older encryption is a reasonable choice when it is the best your processor
can do. Only turn it on when you need it.

### If it still fails

Older encryption has to be built into the copy of Python that runs Home Assistant. Some builds
leave TLS 1.0 and 1.1 out entirely, and on those, no setting in this integration can bring them
back. If setup still says the encrypted connection could not be set up with older encryption on:

1. Check that the processor really requires encryption: turn Encrypted CIP off, leave the port
   blank, and try again.
2. If it does, run `crestron-controller listen 10.0.0.20 --ipid 0x2A --legacy-tls` (with your
   processor's address and IP-ID) from a computer. If that connects, the processor is fine and the
   Home Assistant installation is the one missing older encryption.

## The command-line tool

`crestron-controller listen` and `watch` take the same choices as the setup form:

| Option | Meaning |
| --- | --- |
| `--tls` | Use encrypted CIP. The port defaults to 41796. |
| `--legacy-tls` | Use encrypted CIP and also allow TLS 1.0 and 1.1. Implies `--tls`. |

Both print the TLS version the two sides agreed on and the certificate fingerprint before anything
else. The tool does not remember certificates; only the integration does.

## What to report

If you have a processor that requires encrypted CIP, please open an issue with:

- the processor model and firmware version, which `crestron-controller ipids` prints (see
  [inventory overview](../inventory/inventory-overview.md));
- the `TLS version:` line that `crestron-controller listen --tls` (or `--legacy-tls`) prints;
- whether the listen run went on to report joins.

Do not include the fingerprint, your processor's address or anything else that identifies your
house.

The reasoning behind these choices is in
[ADR 0011](../adr/0011-cip-over-tls-with-a-pinned-certificate.md).
