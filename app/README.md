# ecosemantic

The command that runs EcoSemantic on a machine, and the Python API over the same workspace: `ecosemantic serve` runs the MCP server with the page beside it, `ecosemantic setup` installs a background database, `ecosemantic connect` writes a chatbot's configuration, and `import ecosemantic as es` opens a workspace from Python.

## Names it publishes

- `ecosemantic.cli` and `ecosemantic.console` — the command: `serve`, `setup`, `database`, `connect`, `doctor`, `init`, `export`, `import` and `compute`.
- `ecosemantic.local` — `build_context`, the local composition that binds the server's ports to their backends.
- `ecosemantic.serve` — the process: the listener and its handover, the MCP endpoint over stdio or HTTP, and the view mounted beside it.
- `ecosemantic.workspace` — the Python API: `open`, and the `Workspace`, `Database`, `ProductSystem` and `Process` handles, each method the tool of that name.
- `ecosemantic.installs` — the sources an install comes from, the process that carries one and the account handed to it.
- `ecosemantic.runs` — the launcher and the worker of a calculation that outlives its request.
- `ecosemantic.open`, `Workspace`, `Parameter`, `Case`, `Uncertainty`, `ExchangeOverride`, `ParameterOverride`, `DemandItem`, `BackgroundRef`, `ForegroundRef`, `ElementaryFlowRef`, `SystemRef` and `MonteCarloConfig` — the names `import ecosemantic as es` gives.

## Installing it

`uv tool install --python 3.12 ecosemantic` installs this distribution as a command, with a Python of its own; `uv tool install --python 3.12 "ecosemantic[mkl]"` adds the PARDISO solver, on Linux and Windows x86-64. `pip install ecosemantic` installs it into an environment of Python 3.12 or newer instead.

```bash
ecosemantic doctor
ecosemantic setup uslci
ecosemantic serve --transport http
```

## Telemetry

A server counts its starts and tool calls anonymously unless you turn that off: `ecosemantic telemetry off`, `ECOSEMANTIC_TELEMETRY=off` or `DO_NOT_TRACK=1`. The repository's `TELEMETRY.md` states exactly what is sent.

## What it depends on

The other five distributions at the same version, `ecosemantic-databases` with its `ecoinvent` extra, so a default install builds an ecoinvent release; and fastmcp, fastmcp-slim, pydantic, starlette and uvicorn. The `mkl` extra is `ecosemantic-engine`'s.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). The repository's README says how to install, connect a chatbot and start a first model: https://github.com/cdgaete/ecosemantic
