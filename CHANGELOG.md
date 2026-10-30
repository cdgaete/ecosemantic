# Changelog

Each release names what it adds, changes and removes, newest first.

## 0.1.9

- An install downloads a release's files into `downloads` in the data directory, unless `LCA_DATA_INTERFACE_CACHE` names another folder, so they land under the root the person chose.
- lca-data-interface 0.1.2 is required, whose cache paths fit Windows.
- Commands other than `serve` start without loading the server.
- The telemetry collector's certificate is checked by the operating system's certificate verifier, and a send that fails is an INFO line, never a warning.

## 0.1.8

- A product system another server process is writing for the first time is announced to the page when its package is whole, never as deleted.

## 0.1.7

- Windows and macOS are tested on every change, beside Linux, at Python 3.12 and 3.14.
- Text is read and written as UTF-8 on every platform, so the tables a person opens on Windows carry their characters (e.g. `·`, accents).
- A database's fingerprint, and the digest of an ecoinvent release's files, are the same on every platform.
- Each install writes its build into its own directory and points the database at it, so a database installs again while a server on Windows serves it; the previous build's files are removed once nothing holds them.
- A data directory written by 0.1.6 opens without reinstalling: the first open moves each database into the new layout, keeping its fingerprint.
- After upgrading, restart every running EcoSemantic server: a server started before the upgrade starts its run and install workers from the upgraded files, which move the data directory into the new layout, and that server then lists no databases until it is restarted.

## 0.1.6

- The licence is the PolyForm Noncommercial License 1.0.0 in every distribution: any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from Carlos Gaete-Morales.

## 0.1.5

- A running server counts its starts and its agents' tool calls by name, under a random install identifier, and sends the totals every hour and when it stops to `https://telemetry.ecosemantic.com/v1/metrics`. It is on by default. `ecosemantic telemetry off`, `ECOSEMANTIC_TELEMETRY=off` or `DO_NOT_TRACK=1` turns it off, and then nothing is sent and no telemetry file is made. `TELEMETRY.md` states everything that is sent.
- `ecosemantic telemetry [on|off]` records the choice and shows it, with the install identifier and the endpoint; `ecosemantic init` and `ecosemantic doctor` say whether telemetry is on, what it counts and how to turn it off.
- A collector that cannot be reached, answers with an error or never answers does not delay a start or a tool call, and a stop waits for it at most 5 seconds.

## 0.1.0

The first release of the core, six distributions under one version:

- `ecosemantic-engine`: the product-system vocabulary, the typed errors, the exact solve over a memory-mapped background, contributions by process, flow and path, the inventory and plain Monte Carlo with a stop rule on the median.
- `ecosemantic-core`: the ports, the pure computations over a product system, the model package that openLCA opens, the tables folder, database bundles and the native backend that installs them with a fingerprint of their build.
- `ecosemantic-mcp`: forty-three tools for a chatbot, and three guides it reads as resources.
- `ecosemantic-view`: the page a person watches, reads results in and posts requests from.
- `ecosemantic-databases`: ecoinvent 3.10, 3.10.1, 3.11 and 3.12 cutoff built from the release's own files and validated against ecoinvent's published results.
- `ecosemantic`: the command — `serve`, `connect`, `doctor`, `setup`, `database`, `export`, `import`, `compute` — and `import ecosemantic as es`.
