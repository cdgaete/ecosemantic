# ecosemantic-databases

The sources a background database installs from, each read from its own release files and written as an openLCA JSON-LD bundle the core installs: the ecoinvent builder with its release profiles, the USLCI source, the BAFU source, and the reader for an openLCA `.zolca` database.

## Names it publishes

- `ecosemantic.databases.ecoinvent` — the builder: a release's EcoSpold2 datasets, its MasterData and its LCIA implementation, read and nothing else; no Brightway, no bw2io. It downloads the release, probes what it holds against what a build reads, writes one openLCA JSON-LD bundle, and validates the bundle against ecoinvent's published results. `releases/` beside it holds one profile per validated release: file hashes, workbook layouts, the decisions the probe asked for, and the measured validation numbers.
- `ecosemantic.databases.uslci` — the USLCI source: the release the profile pins, downloaded from the Federal LCA Commons through `lca-data-interface`, with its profile, its two lists and its notices.
- `ecosemantic.databases.bafu` — the BAFU source: the release the profile pins, read through an openLCA Nexus session, with its profile and the terms an install accepts.
- `ecosemantic.databases.zolca` — the reader for an openLCA `.zolca` database.
- `ecosemantic.databases.profiles`, `lists`, `checks` and `scores` — the profiles a source pins, the lists a release is filed under, the checks a bundle passes and the scores it is validated against.
- The `ecosemantic-databases` command, over the `bafu`, `ecoinvent` and `uslci` groups.

## The command

`ecosemantic-databases` runs one step of an ecoinvent build on its own, for a person who wants the files; `setup ecoinvent` runs the same steps and installs what they build.

```bash
ecosemantic-databases ecoinvent download 3.12 --system-model cutoff
ecosemantic-databases ecoinvent probe 3.12 --system-model cutoff
ecosemantic-databases ecoinvent build 3.12 --system-model cutoff --out builds
ecosemantic-databases ecoinvent validate 3.12 --system-model cutoff --bundle builds/ecoinvent-3.12-cutoff.zip
```

`download` fetches the release's five files and prints each path with the SHA-256 of every file a build reads; `probe` lists what the release holds against what a build reads and the gaps between them; `build` writes `<dir>/ecoinvent-<version>-<model>.zip`; `validate` compiles the bundle for the engine and compares its scores with the matrix export and the cumulative LCIA workbook. `build` and `validate` read `releases/<version>-<model>.yaml` when the release has one, and take the default layout with `--no-profile`. `uslci` and `bafu` take the same four steps over their own releases.

## What it depends on

`ecosemantic-engine` and `ecosemantic-core` at the same version; `lca-data-interface` for the openLCA Nexus and Federal LCA Commons clients; and pydantic, olca-schema, pyyaml, numpy and scipy. The `ecoinvent` extra adds `ecoinvent_interface` and `python-calamine`.

## Credentials

`ecoinvent_interface` reads `EI_USERNAME` and `EI_PASSWORD` from the environment, and a download refuses with `Unavailable` when either is absent. The BAFU source reads `NEXUS_USERNAME` and `NEXUS_PASSWORD`, and `NEXUS_TOKEN` for an account with a second factor.

## Where the files live

Downloaded releases stay in `ecoinvent_interface`'s cache, `~/.local/share/EcoinventInterface/cache`, and built bundles go to the directory `build` takes. Neither is tracked. `releases/<version>-<model>.yaml` holds one profile per validated release, and no release data enters this distribution.

## Installing it

`pip install ecosemantic` installs this distribution with the other five, its `ecoinvent` extra included, and the `ecosemantic` command. `pip install "ecosemantic-databases[ecoinvent]"` installs the builder alone, with the dependencies an ecoinvent build needs.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). This distribution handles licensed data and credentials and carries no release data. The code is published from https://github.com/cdgaete/ecosemantic.
