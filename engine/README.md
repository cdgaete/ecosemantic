# ecosemantic-engine

The lowest distribution of the EcoSemantic core: the product-system vocabulary, the typed errors every other distribution raises, and the exact life cycle assessment computation over a compiled background.

## Names it publishes

- `ecosemantic.model` — the vocabulary a product system is made of: its entities, the refs that name what it reaches, the units the core knows, the structural validation a system passes before a calculation runs, the result-relevant projection a version hash names, and the summary an answer keeps of itself.
- `ecosemantic.errors` — the typed errors, `EcoSemanticError` and the refusals under it: a layer that cannot answer raises rather than approximates.
- `ecosemantic.engine` — the computation: `background` compiles a database into labelled memory-mapped arrays, `solver` makes the forward and adjoint solves from one factorisation, `calculation` reads scores, contributions, intensities, supply, inventory and paths from one solve, `foreground` gives a product system its columns over that background, `paths` walks the supply chain under one process, `montecarlo` takes each draw from the seed and the draw's index, `loops` judges the technosphere loops a draw is checked on, and `refine` refines a sparse solve.

## What it depends on

pydantic, numpy and scipy, and nimblend for the memory-mapped arrays a background is compiled into. The `mkl` extra adds pypardiso, on Linux x86-64 and Windows x86-64, where MKL publishes wheels.

## Installing it

`pip install ecosemantic` installs this distribution with the other five and the `ecosemantic` command. `pip install ecosemantic-engine` installs it alone, for code that builds on the vocabulary and the engine without a server; `pip install "ecosemantic-engine[mkl]"` adds the solver.

## Licence

PolyForm Noncommercial License 1.0.0, copyright Carlos Gaete-Morales: `LICENSE` and `NOTICE` in this distribution. Any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from him (cdgaete@gmail.com). EcoSemantic is his trademark, and the licence grants no right to use that name (`TRADEMARK.md` in the repository). The code is published from https://github.com/cdgaete/ecosemantic.
