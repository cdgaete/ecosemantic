# ecosemantic-view

The HTTP API of the EcoSemantic page and the page itself: where a person watches an agent build a product system, reads its change log and results, and posts requests the agent answers.

## Names it publishes

- `ecosemantic.view.app` — the view application: the token gate, the routes and the page.
- `ecosemantic.view.api` — the routes over the tools, each calling the tool the agent calls.
- `ecosemantic.view.stream` — the event streams: what happens to one product system, and what happens in the whole process, as it happens.
- `ecosemantic.view.credentials` — the page's credential routes, answering a peer on this machine only, since the page's token travels over plain HTTP.
- `ecosemantic.view.activity`, `installs`, `olca`, `tables` and `handling` — the activity routes and the trail of a log entry, the routes over the install tools, the openLCA hand-off, the table routes, and what every route handler shares: its error boundary and its uploads.
- The built page, under `ecosemantic/view/static/`: its HTML, its scripts and `THIRD_PARTY_NOTICES.txt`, which lists what the page bundles and under which licence.

The page's source is `page/`, a workspace of its own built with `pnpm build`, and the build writes that directory into this distribution's wheel and sdist.

## What it depends on

`ecosemantic-engine`, `ecosemantic-core` and `ecosemantic-mcp` at the same version, and fastmcp, fastmcp-slim, mcp, pydantic, starlette and sse-starlette.

## Installing it

`pip install ecosemantic` installs this distribution with the other five and the `ecosemantic` command that serves the page beside the MCP endpoint. `pip install ecosemantic-view` installs the API and the page alone, for a server of someone else's.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). The page bundles third-party software under its own licences, listed in `ecosemantic/view/static/THIRD_PARTY_NOTICES.txt`. The code is published from https://github.com/cdgaete/ecosemantic.
