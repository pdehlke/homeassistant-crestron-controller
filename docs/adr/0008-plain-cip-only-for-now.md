---
status: accepted
---

# Plain CIP only for now

Version 1 speaks plain CIP on TCP 41794 and nothing else. Authenticated or TLS-wrapped CIP (port
41796) is not supported. The reason is evidence: every processor this project has been tested
against accepted plain CIP with no authentication, and there was no processor available that
requires the secure variant, so any implementation would be written blind and shipped untested.
The config flow lets the user change the port, but the client sends the same unencrypted handshake
on any port.

## Considered options

| Option | Why not |
| --- | --- |
| Implement TLS and authentication from public descriptions | Nothing to test against. A security feature that has never connected to a real processor is worse than an honest "unsupported", because users would trust it. |
| Refuse to connect on any port other than 41794 | Some installations may forward or remap the port. Allowing a different port costs nothing. |

## Consequences

Systems that only allow the secure port are listed as unsupported in
[unsupported-systems.md](../troubleshooting/unsupported-systems.md). This project has not seen how
such a processor answers a plain handshake, so the config flow will show whichever generic
connection error results rather than a message that names the cause. The CLI's console commands
can answer a username and password prompt, but that path is also untested against a processor that
actually requires a login. Supporting either properly needs a contributor with such a processor and
a packet capture.
