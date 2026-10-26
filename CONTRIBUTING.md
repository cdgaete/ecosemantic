# Contributing to EcoSemantic

## What belongs here

EcoSemantic serves the individual practitioner: modelling, calculating, reviewing and exchanging product systems on their own machine, through a chatbot, the page, Python or the command line. What an organisation needs — teams, identities, roles, audit, reports to a standard, hosted operation — belongs to the platform Kimel Tech SpA sells and is not taken here.

## Signing off: the Developer Certificate of Origin

Every commit carries a `Signed-off-by` trailer with its author's name and email, as `git commit -s` writes it. The sign-off certifies the Developer Certificate of Origin, version 1.1, from https://developercertificate.org:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

A pull request's commits are checked by `scripts/signed_off.py`. There is no contributor licence agreement: a contribution is licensed under the Apache License, Version 2.0, the open source license the Developer Certificate of Origin refers to. The repository is distributed under the PolyForm Noncommercial License 1.0.0, and the Apache License lets Carlos Gaete-Morales distribute a contribution under those terms now and under the Apache License when the repository moves to it. The person who signs off a change answers for it, whether or not they wrote it with an AI assistant.

## Setting up

Python 3.12 or newer with uv, and Node 22.12 or newer with pnpm 10:

```bash
uv sync --all-packages
(cd page && pnpm install)
bash scripts/check.sh
(cd page && pnpm check && pnpm build)
```

## The house rules

- **No silent fallbacks.** A code path does the right thing or raises one of the typed errors in `engine/ecosemantic/errors/__init__.py`; it never substitutes a default and continues. No `try/except` around an internal call; a library's exception is translated where the library is called.
- **No comments in source.** A module's or a function's docstring states what it does and why a caller needs it, briefly. A test may carry a short comment.
- **Facts, not history.** Code, tests and documents state what is true now: no "used to", "no longer" or "previously".
- **Composition over duplication.** A package offers what it does through the names it publishes; a consumer that needs more extends that interface rather than writing it again. Below `mcp` nothing imports `backends`, and nothing the page stands on imports `view` (`tests/test_boundaries.py`).
- **Types.** Every signature is annotated; `X | None`, never `Optional[X]`; a closed vocabulary is one `Literal`; structured data that crosses a function boundary is a pydantic model or a frozen dataclass. `uv run ty check` passes.
- **Style.** `ruff format`, line length 100. A call with more than two arguments names them.
- **Tests.** A change in behaviour starts with a test that fails for the stated reason, and a test's name is the sentence it proves. No test reaches the network or licensed data: tests run on the synthetic fixture in `tests/fixture_data.py`.
- **The gate.** `bash scripts/check.sh` passes — ruff, ruff format, ty, vulture, and pytest under coverage at 95 % or above — with no `# noqa`, no `# type: ignore` and no skipped test.
- **No licensed data.** No ecoinvent dataset, identifier or score derived from one is committed.

## Pull requests

One concern a pull request, with the tests that pin it and the documents it changes. A vulnerability is reported privately, as `SECURITY.md` says; conduct follows `CODE_OF_CONDUCT.md`.
