# Security policy

## Supported versions

EcoSemantic is in its 0.x series. Security fixes go to the latest 0.x release.

## Reporting a vulnerability

Report a vulnerability privately, never in a public issue: through the repository's private vulnerability reporting, under *Security*, *Report a vulnerability*, or by email to support@ecosemantic.com. The maintainer acknowledges the report and agrees a disclosure date with you, and the fix ships as a release of the latest 0.x line that names the report.

## What the threat model names

- **The page served over HTTP.** `ecosemantic serve` binds the page to a port. On a loopback address it asks for no token; a bind that reaches a network is refused until the command says `--token` or `--no-token`, and under `--token` every request carries the workspace's token.
- **Formulas from third-party files.** A parameter's or an exchange's formula is evaluated by asteval, a restricted interpreter, whichever file it came from: an openLCA package, a table folder or a model package someone sent.
- **Archives a person uploads.** The openLCA return and the table return unpack a zip a person uploads. Each is refused past 100 MB, 1 GB unpacked or 100,000 entries before it is unpacked, and every entry stays inside its destination.
- **The stdio server is unauthenticated.** A chatbot that starts `ecosemantic serve` over stdio reaches every tool with the rights of the user running it.
