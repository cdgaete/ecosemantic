# EcoSemantic

Life cycle assessment on your own machine, modelled by talking to an agent, from Python or from the command line. EcoSemantic installs a background database — ecoinvent built under your own licence, USLCI, BAFU, or any openLCA JSON-LD zip — and serves product systems over it: exact scores, contributions by process, flow and path, the inventory and Monte Carlo. A chatbot reaches it through an MCP server, a person watches and reviews the model on a page the server serves beside it, and `import ecosemantic as es` opens the same workspace from Python.

## Install

uv is the installer: one line on Windows, one on macOS and Linux, each as [uv's installation page](https://docs.astral.sh/uv/getting-started/installation/) gives it.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then the command, with a Python of its own, and the PARDISO solver where that solver publishes wheels:

```bash
uv tool install --python 3.12 ecosemantic
uv tool install --python 3.12 "ecosemantic[mkl]"   # PARDISO, on Linux and Windows x86-64
```

`--python 3.12` has uv use Python 3.12 or newer, downloading one when the machine holds only an older Python. `pip install ecosemantic` installs the six distributions with the ecoinvent dependencies into an environment of Python 3.12 or newer.

## Connect a chatbot, then restart it

```bash
ecosemantic init                          # every chatbot found
ecosemantic init --client claude-desktop  # or the ones you name
ecosemantic connect vscode --workspace path/to/project
```

`init` writes this server into the MCP configuration of each chatbot it finds — Claude Desktop or Cursor, where the platform keeps their configuration — and keeps every other server those files name. VS Code keeps a configuration per workspace, which `init` does not find, so `connect` writes that one. Restart the chatbot: it starts the server over standard input and output, and the server opens the EcoSemantic page in your browser. `ecosemantic doctor` reports what the install holds and lacks.

## A first database

The page's Databases editor lists the installed databases and the four sources a database installs from, each saying what it needs: an openLCA JSON-LD zip you hold; USLCI, which asks nothing of you; BAFU, which asks for an openLCA Nexus account and the release's terms; and ecoinvent, which downloads the release with your own account and builds it under your own licence. Pick a source, take a version, enter the account it asks for, and watch the install's steps. A database is served as soon as its install ends, by every server running on the data directory, with no restart.

A terminal installs the same four sources.

```bash
ecosemantic setup openlca --package my-database.zip --name my-database --version 1
ecosemantic setup uslci
ecosemantic setup bafu --accept-terms
ecosemantic setup ecoinvent 3.12
```

[Getting a database](docs/getting-a-database.md) says what each source needs, and what the builder's own steps are.

## A first model

Ask the agent, in the chat: *"On ecoinvent-3.12-cutoff, model one bicycle frame of 2 kg of low-alloyed steel tube, with 8 % scrap as a parameter; calculate its climate change score and show the contribution by process."* The agent reads the guide on building a model, calls the tools, and every write lands in the product system's change log. The model lands on the page as it is built, and the page takes your requests, which the agent answers.

## From Python

```python
import ecosemantic as es

with es.open() as ws:
    db = ws.database("ecoinvent-3.12-cutoff")
    steel = db.search_processes("market for steel, low-alloyed", location="GLO").items[0]
    method = next(
        hit
        for hit in db.search_methods("IPCC 2021 climate change fossil").items
        if hit.impact_method == "IPCC 2021" and hit.impact_category == "climate change: fossil"
    )

    frame = ws.create_product_system("bicycle frame", database=db)
    tube = frame.create_process(
        "tube", "frame tube drawing", unit="kilogram", reference_product="frame tube"
    )
    frame.update_product_system(reference_process="tube")
    tube.create_exchange(type="product", formula="2", input=steel)

    score = frame.calculate_impact(method_id=method.id).value.scores[0]
    print(score.value, score.unit)
```

`es.open()` takes the data and systems directories the server takes, and `es.open(data_dir=..., systems_dir=...)` names others. Each method answers what the tool of that name answers, as typed objects: `.value` holds the result, and a refusal raises the typed error from `ecosemantic.errors`.

## Documents

- [Quickstart: a chatbot](docs/quickstart-chat.md) — install, connect, a first database, a first model and its result.
- [Quickstart: Python](docs/quickstart-python.md) — `import ecosemantic as es`, from a workspace to a result, with the conventions a caller needs.
- [Getting a database](docs/getting-a-database.md) — the page and the command line, what each of the four sources needs, and the builder's own steps.
- [Building a model](mcp/ecosemantic/mcp/guides/building-a-model.md), [interpreting a result](mcp/ecosemantic/mcp/guides/interpreting-a-result.md) and [a sensitivity study](mcp/ecosemantic/mcp/guides/sensitivity-study.md) — the three guides the server serves as resources, so every chatbot reaches them.
- [Telemetry](TELEMETRY.md) — the anonymous counts of server starts and tool calls, exactly what is sent, and how to turn it off with `ecosemantic telemetry off`.
- [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [PROVENANCE.md](PROVENANCE.md).

## What this repository holds

Six distributions under one version, published together:

| Distribution | What it holds |
| ------------ | ------------- |
| `ecosemantic-engine` | `errors`, `model` and `engine`: the product-system vocabulary, its typed errors, and the exact computation with Monte Carlo |
| `ecosemantic-core` | the ports and the types they carry, the pure computations, the portable package, the tables folder, the event bus, the drawing, and the backends that serve the ports from installed bundles and a folder of product systems |
| `ecosemantic-mcp` | the MCP tools, the server that registers them, the run watcher, and the three guides |
| `ecosemantic-view` | the page's API and the built page |
| `ecosemantic-databases` | the ecoinvent builder with its release profiles, the USLCI and BAFU sources, the openLCA `.zolca` reader, and the `ecosemantic-databases` command |
| `ecosemantic` | `cli`, `console`, `local`, `installs`, `runs`, `serve` and `workspace`: the `ecosemantic` command and `import ecosemantic as es` |

`pip install ecosemantic` installs all six. The `ecoinvent` extra stays on `ecosemantic-databases` for a person who installs the builder alone, as `ecosemantic-databases[ecoinvent]`.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE`. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md`). The page bundles third-party software under its own licences, listed in the view's `ecosemantic/view/static/THIRD_PARTY_NOTICES.txt`; `PROVENANCE.md` and `page/PROVENANCE.md` record what the code takes from elsewhere. Contributions come under the Developer Certificate of Origin (`CONTRIBUTING.md`), vulnerabilities are reported privately (`SECURITY.md`), and the community keeps `CODE_OF_CONDUCT.md`.

The first version is published from https://github.com/cdgaete/ecosemantic.
