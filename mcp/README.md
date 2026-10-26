# ecosemantic-mcp

The MCP tools of EcoSemantic, each a plain function over the ports bound in `ServerContext`, and the server that registers them for a chatbot: search the installed databases, model a product system, and calculate its impacts, contributions, inventory and Monte Carlo runs.

## Names it publishes

- `ecosemantic.mcp.server` — the stdio server: what it is called, the tools it registers and the order it registers them in.
- The tool modules, each a set of module-level functions taking the `ServerContext`: `discovery` (what is installed), `modelling` (processes and exchanges), `linking` (what the stored systems' links hold), `parameters`, `calculation` (impacts, contributions, inventory), `tables`, `graph` (the drawing), `systems` (the stored systems and their log), `requests` (the request tools, and the answer every write tool returns), `installs`, `runs`, `treatments`, `envelopes` (the answer every tool returns) and `calls` (the tool call in progress, and what it hands the recorder).
- `ecosemantic.mcp.guides` — the three task guides served as resources: building a model, interpreting a result and a sensitivity study.
- `ecosemantic.mcp.panels` — the in-chat panels a host renders beside a tool's result.
- `ecosemantic.mcp.watcher` — the server's view of a run or an install in another process: poll the record, publish what changed, and settle one whose process is gone.

## What it depends on

`ecosemantic-engine` and `ecosemantic-core` at the same version, and fastmcp, fastmcp-slim, mcp and pydantic. It imports nothing from `ecosemantic.view`: the tools a page reads are the tools a chatbot calls.

## Installing it

`pip install ecosemantic` installs this distribution with the other five and the `ecosemantic` command that serves it. `pip install ecosemantic-mcp` installs it alone, for a host that registers the tools over its own transport.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). The code is published from https://github.com/cdgaete/ecosemantic.
