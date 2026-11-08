# Provenance

The Python of this repository is written for it. What it takes from the frozen EcoSemantic system — nine private repositories under `github.com/kimeltech`, every commit in them Carlos Gaete-Morales's — is listed below: each source file, its commit, its destination and what changed. The page keeps its own record, `page/PROVENANCE.md`. Nothing is copied from openLCA or from Brightway.

## How the record was made

Two searches over the package's 143 Python source files outside `tests/` and against the frozen system's 523 Python files outside environments and caches:

- **Shared code.** Each file's lines, stripped of comments, imports, decorators and lines under twelve characters, cut into runs of four consecutive lines; a run present in both a package file and a frozen file is shared code. Seven pairs of files share a run, the largest two runs, and each is listed below.
- **Shared names.** Every function and class name of eight characters or more in the package's source outside `tests/` and `scripts/` (697) against the frozen system's (2,075). The 28 shared are the tool names of the MCP roster both systems serve, the four functions of the Monte Carlo summary and `evaluate`, listed below, and names a vocabulary shares without shared code: `__init__`, `database`, `download`, `lifespan`, `difference`, `get_version`, `read_log`, `unsubscribe_all`, `Activity`, `Exchange`, `ValidationReport`, `add_exchange`, `patch_exchange`, `_references`.

## Taken from the frozen system

| Source | Destination | Changed |
| ------ | ----------- | ------- |
| `ecosemantic_lca_workers/workers/mc_stats.py`, commit `362e0bd` | `core/ecosemantic/compute/montecarlo.py` | written again after its four functions' names and roles, `summarize_samples`, `worst_rel_se`, `should_stop` and `paired_delta`, and its constant `Z95`: the summary centred on the median with its distribution-free interval in place of the mean and its standard error, the stop rule judging the median's relative error, a variant's delta the median of paired differences, and pydantic results in place of dictionaries; no line is shared |
| `ecosemantic_lca_api/api/parameter_eval.py`, commit `b5ba246`, and its copy `ecosemantic_lca_workers/workers/parameter_eval.py`, commit `6258bf7` | `core/ecosemantic/compute/parameters.py`, `engine/ecosemantic/model/entities.py` | the role of `evaluate`, parameters materialised in dependency order and formulas evaluated over them with asteval, written again with `graphlib` in place of bw2parameters; the parameter-name pattern `^[a-z_][a-z0-9_]{0,63}$` kept as `NAME_RE` in `entities.py` |
| `ecosemantic_lca_api/api/versioning.py`, commit `2c800dc` | `engine/ecosemantic/model/canonical.py` | the design of the content hash, a SHA-256 over a canonical projection of the result-relevant fields of processes (`code`, `name`, `unit`, `location`, `reference_product`) and exchanges, written again over the product-system model and extended with parameters, cases, the reference process, uncertainty and the database's fingerprint |
| `ecosemantic_lca_api/api/models.py`, commit `075aee8`, and `ecosemantic_lca_workers/workers/uncertainty.py`, commit `84f155f` | `engine/ecosemantic/model/entities.py` | two tables of the uncertainty vocabulary both follow from stats_arrays' conventions: the parameter names each distribution takes (`loc`, `scale`, `minimum`, `maximum`, `negative`) and the distributions' numeric ids (lognormal 2, normal 3, uniform 4, triangular 5) |
| `ecosemantic_lca_api/api/biosphere_search.py`, commit `810e7db`; `ecosemantic_mcp/tools/server_tools.py`, commit `afe1feb`; `ecosemantic_backend/src/app/api/v1/lca.py`, commit `4f4147a` | `mcp/ecosemantic/mcp/discovery.py`, `core/ecosemantic/backends/native/search.py`, `app/ecosemantic/workspace/__init__.py` | the names of the elementary-flow search's filters, `compartment`, `sub_compartment`, `flow_type`, `unit`, passed by keyword with `limit` and `cursor` |
| `ecosemantic_mcp/tools/server_tools.py`, commit `afe1feb` | `mcp/ecosemantic/mcp/*.py`, `app/ecosemantic/workspace/__init__.py` | the names of the tools both servers register: `search_methods`, `create_exchange`, `update_exchange`, `delete_exchange`, `set_parameters`, `create_scenario`, `delete_scenario`, `rebase_scenario`; their arguments, answers and descriptions are written for this repository |

## Taken from EcoSemantic Desktop

`packages/ecosemantic-desktop`, commit `ed32299`, holds a payload build and a third-party notice for its own installer, which `scripts/payload.py` was designed against: `scripts/build-python.ts`, `scripts/payload-lock.ts`, `scripts/payload-requirements.py`, `scripts/third-party-notices.ts` and `scripts/compiled-licences.ts`. What it takes from them, by source:

| Source | Destination | Changed |
| ------ | ----------- | ------- |
| `scripts/third-party-notices.ts:11` | `scripts/payload.py`, `LICENCE_FILE` | the pattern body copied word for word, `^(?:licen[cs]e|copying)`, spelling Python's case-insensitivity `re.IGNORECASE` where TypeScript writes `iu` |
| `scripts/payload-requirements.py`, `header`, `declared`, `documents` and `gaps` | `scripts/payload.py`, `requirement_gaps` | written again over `packaging`, or the copy pip vendors, with every metadata field read by `email.parser` in place of hand-cut header lines; the walk from `ecosemantic[mkl,tray]` along each requirement's markers and extras, and the report that names every gap with the requirement that asks for it, are that file's |

The payload build itself is written for this repository: the interpreter asset, its hash and the wheel set come from `installer/python.json` and `uv.lock`, the seven core distributions from `dist/`, and the two folder budgets from `installer/budgets.json`, none of which the desktop app has.

| Source | Destination | Changed |
| ------ | ----------- | ------- |
| `resources/brand/icon-64.png`, commit `ed32299` | `app/ecosemantic/tray/icon-64.png` | copied unchanged: the tray draws the same mark as the desktop app, with a disc in its corner for the engine's state |
| `resources/brand/icon.ico`, commit `ed32299` | `installer/windows/icon.ico` | copied unchanged: the installer's own icon, and the uninstaller's |
