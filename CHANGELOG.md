# Changelog

Each release names what it adds, changes and removes, newest first.

## Unreleased

- `ecosemantic-relay`, a seventh distribution, holds the bridge's tunnel: the messages and frames of its one WebSocket, the bridge's discovery document and the Ed25519 proof a bridged request carries.
- `ecosemantic serve --bridge` serves the engine over HTTP, signs it in to `https://bridge.ecosemantic.com` when the machine holds no credential for it, and serves the bridge's tunnel beside the page, announcing `https://<handle>.bridge.ecosemantic.com` as the page's address and writing the connector's address and the tunnel's lines on stderr.
- `ecosemantic bridge sign-in` signs an engine in through the browser or `--device`, `ecosemantic bridge sign-out` revokes the grant, and `ecosemantic bridge status` says whether the engine is signed in and where its credential is kept, renewing nothing.
- `ecosemantic bridge status` answers on a machine without a credential store, naming the two sign-ins that need none.
- `ecosemantic bridge sign-out` refuses while an engine token gives the engine its sign-in, and answers that nothing was revoked when this systems directory holds no credential.
- `ecosemantic doctor` reports a bridge setting it cannot use, in its view section, and exits 0.
- `ecosemantic-databases` and `ecosemantic setup ecoinvent`: ecoinvent 3.13 cutoff, built from the release's own files and validated against ecoinvent's published results, its two Ecological Scarcity 2021 biotic resources categories against the release's matrix export.

## 0.1.12

- A release's validation and the scoring of every dataset in `ecosemantic-databases` refuse a dataset the compiled background lacks as `not_found`, naming it as `the import names background dataset '<code>', which '<database>' does not hold`, where they answered `invalid`.
- `ecosemantic compute` asks the store for a folder's treatments once and names the exchanges run backwards from that one answer in the impact, the contributions and the inventory it writes; `contribution_analysis` and `calculate_inventory` ask once per call.

## 0.1.11

- `list_sources` names `unit process` as the system model of `uslci` and `bafu`, so the page's form for either source shows it as the system model.
- An inventory's run folder, which `ecosemantic compute` writes into a table folder's `results` and the page's inventory download zips, records `floor` and `dropped` in its `schema.yaml`: the amount at or below which a residue is set aside, and how many were.
- A miss reads the same from every store and names a product system by its id: `no product system <id>`, `no version <hash> of product system <id>`, `no database '<name>' under <directory>; this store serves [...]`, `product system <id> is at <hash>, the write is based on <hash>` for a write on a stale base, and `<system> links <linked>, which has no reference process; set one with update_product_system`.
- `ecosemantic export` into a directory that does not exist is refused as `invalid`, naming the directory.
- `arrange_graph` takes `release_all`, which lets every held card go before the placements apply, and refuses it beside `release`; the page's *Reset layout* releases through it, a held code no process carries included.

## 0.1.10

- An install's summary names the inputs no dataset of the release provides as `cut_off`, the inputs the install cut off from the calculation, in place of `unlinked` and `dropped`; the catalog keeps each as an exchange with its reason, and the record keeps the rows in `cut_off.json` beside it.
- `install_database` refuses a database the server serves before anything is downloaded, unless `replace` is passed, where the refusal came after the download and the build.
- `drop_unlinked` is an `openlca` install's choice: a draft of another source that sets it is refused as `invalid`, and a draft's refusal reaches the caller as `invalid` with its reason.

## 0.1.9

- An install downloads a release's files into `downloads` in the data directory, unless `LCA_DATA_INTERFACE_CACHE` names another folder, so they land under the root the person chose.
- lca-data-interface 0.1.2 or later is required; its cache paths fit Windows.
- Importing the command line, and running `doctor`, `telemetry`, `init`, `connect`, `setup`, `database` or `import`, loads no FastMCP and no page; `compute` and `export` load FastMCP through the tool functions they call.
- The telemetry collector's certificate is checked by the operating system's certificate verifier, and a failed send is logged at INFO, below the warning level the server writes, so nothing is written.

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
