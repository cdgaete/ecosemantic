# Getting a database

A product system sits on one installed background database. EcoSemantic installs a database from a bundle: an openLCA JSON-LD zip, read and compiled once into the arrays and the search catalog the calculations use.

## From the page

The page's Databases editor (*Background databases* in its navigation) lists the installed databases and the sources one installs from, each saying what it needs. Pick a source, take a version, enter the account when the source asks for one, tick the box on the terms BAFU serves, and watch the install's steps; a refusal names its remedy. With no database installed, the page's welcome offers the same sources in place of the empty list of product systems. A database is served as soon as its install ends, by every server running on the data directory, with no restart.

The page opens itself when a chatbot starts the server. The agent in the chat gives you its address (`view_link`). An install the page posts runs the same steps `ecosemantic setup` runs, in a process of the server's own, so the server and the chatbot can restart while it carries on.

## From the command line

`ecosemantic setup` takes the same four sources, each named as the page names it, and installs into the data directory the server and the workspace read (`ecosemantic doctor` names it).

### USLCI

USLCI comes from the Federal LCA Commons, and needs nothing from you:

```bash
ecosemantic setup uslci              # the release the profile pins: 1.2026-09.0
ecosemantic setup uslci --version 1.2026-09.0 --replace
```

### BAFU

BAFU comes from openLCA Nexus. It needs a Nexus account, and it installs once you have read the release's terms and accepted them:

```powershell
$env:NEXUS_USERNAME = "..."
$env:NEXUS_PASSWORD = "..."
ecosemantic setup bafu --accept-terms
```

```bash
export NEXUS_USERNAME=... NEXUS_PASSWORD=...
ecosemantic setup bafu --accept-terms
```

`NEXUS_TOKEN` carries the token of an account with a second factor. Without `--accept-terms` the command answers the release's citation and licence file and installs nothing; read them, then install with it.

### ecoinvent, under your own licence

`ecosemantic setup ecoinvent` downloads the release's own files with your ecoinvent account, builds the bundle in a temporary directory, validates it against ecoinvent's published results, and installs it as `ecoinvent-<version>-<system model>`. It offers ecoinvent 3.10, 3.10.1, 3.11 and 3.12, cutoff system model:

```powershell
$env:EI_USERNAME = "..."
$env:EI_PASSWORD = "..."
ecosemantic setup ecoinvent 3.12
```

```bash
export EI_USERNAME=... EI_PASSWORD=...
ecosemantic setup ecoinvent 3.12
```

With neither variable set, the command asks for the account at a terminal and reads the password without echo. A run longer than a second reports its steps on standard error. A validation that does not pass refuses with its largest difference and installs nothing. The build sends nothing anywhere: a built bundle is yours to use under ecoinvent's licence, not to redistribute.

### An openLCA JSON-LD database

Any database openLCA exports as JSON-LD installs the same way:

```bash
ecosemantic setup openlca --package my-database.zip --name my-database --version 1
```

`setup` refuses a database with an input no dataset provides; `--drop-unlinked` installs it without those inputs and lists them in its answer. `--system-model` names the system model the database reports, `unit process` unless you say otherwise.

### The builder's own steps

`ecosemantic-databases`, which the default install carries, runs each step of an ecoinvent build on its own, for a person who wants the files:

```bash
ecosemantic-databases ecoinvent download 3.12 --system-model cutoff
ecosemantic-databases ecoinvent probe 3.12 --system-model cutoff
ecosemantic-databases ecoinvent build 3.12 --system-model cutoff --out builds
ecosemantic-databases ecoinvent validate 3.12 --system-model cutoff --bundle builds/ecoinvent-3.12-cutoff.zip
```

`setup ecoinvent` runs the same steps and installs what they build.

## Installed databases

`list_databases`, in the chat or as `ws.list_databases()` in Python, names what is installed. A product system records the build of its database by a fingerprint of the compiled arrays, so a colleague who installs the same build computes the same numbers, and a calculation over another build is refused until `rebase_database` moves the system onto it.
