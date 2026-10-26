# ecosemantic-core

The ports of EcoSemantic and the types they carry, the pure computations over a product system, the portable package a model travels in, the tables folder, the event bus, the drawing the page renders, and the two backends that serve the ports from installed database bundles and from a folder of product systems.

## Names it publishes

- `ecosemantic.ports` — the protocols every backend answers and the types they carry: `activity`, `calculation`, `graph`, `install`, `inventory`, `resolver`, `run`, `search`, `storage` and `types`.
- `ecosemantic.compute` — the pure computations, with no store behind them: `parameters`, `overrides`, `links`, `consequences`, `edits`, `results`, `render`, `montecarlo` and `accounts`.
- `ecosemantic.package` — the portable package a product system travels in, openLCA's JSON-LD among its forms, with the change log, the manifest, the gates and the compilation that reads it.
- `ecosemantic.tables` — a product system as a folder of text: a YAML model, CSV inputs and CSV results.
- `ecosemantic.events` — one bus per server process, fed by the storage every write goes through and by the watcher of each run.
- `ecosemantic.geometry`, `layout`, `routes`, `textmap` and `troubles` — the drawing, in the pixels the page renders it at: each card's rows, where a process sits, every arrow as an orthogonal route, the drawing as characters an agent reads, and what is wrong with it.
- `ecosemantic.quantity` and `scaling` — a quantity as the canvas writes it, and each card's exchanges scaled to one unit of the functional unit.
- `ecosemantic.backends.filesystem` — product systems, runs, installs and their records in a folder, and the watcher that announces what changes.
- `ecosemantic.backends.native` — the databases installed under one data directory: their registry entries, their catalogs and their compiled backgrounds, serving the search, inventory and calculation ports.

## What it depends on

`ecosemantic-engine` at the same version, and pydantic, olca-schema, asteval, duckdb, numpy, scipy, filelock, watchfiles and pyyaml.

## Installing it

`pip install ecosemantic` installs this distribution with the other five and the `ecosemantic` command. `pip install ecosemantic-core` installs it alone, for a backend or a tool that depends on the ports rather than on the server.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). The code is published from https://github.com/cdgaete/ecosemantic.
