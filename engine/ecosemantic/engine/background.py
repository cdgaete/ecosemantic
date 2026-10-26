"""A database compiled for calculation: its matrices as labelled arrays, its exchange rows with
their distributions, and the directory of numpy files it is saved as."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path

import nimblend as nb
import numpy as np

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import DISTRIBUTION_IDS, Method, Uncertainty
from ecosemantic.model.refs import Database

FORMAT = 1
_PARAMETERS = ("loc", "scale", "minimum", "maximum")


@dataclass(frozen=True)
class Rows:
    """Exchange rows by label, as a source states them: each row's row and column label, its
    amount, whether it enters the matrix negated, and its distribution."""

    rows: Sequence[str]
    columns: Sequence[str]
    amounts: Sequence[float]
    flipped: Sequence[bool]
    uncertainties: Sequence[Uncertainty | None]


@dataclass(frozen=True)
class Factors:
    """Characterisation factors by label: each one's category, its flow and its value."""

    categories: Sequence[str]
    flows: Sequence[str]
    values: Sequence[float]


@dataclass(frozen=True)
class Exchanges:
    """Exchange rows unsummed, at the positions of a background's coordinates: each row's row and
    column, its amount as stated, whether it enters the matrix negated, and its distribution:
    the type as `DISTRIBUTION_IDS` numbers it, 0 for none, and NaN for a parameter the type has
    not."""

    row: np.ndarray
    column: np.ndarray
    amount: np.ndarray
    flip: np.ndarray
    uncertainty_type: np.ndarray
    loc: np.ndarray
    scale: np.ndarray
    minimum: np.ndarray
    maximum: np.ndarray
    negative: np.ndarray

    @classmethod
    def of(
        cls,
        row: np.ndarray,
        column: np.ndarray,
        amounts: Sequence[float],
        flipped: Sequence[bool],
        uncertainties: Sequence[Uncertainty | None],
    ) -> Exchanges:
        """Rows at positions, with their distributions as columns."""
        n = len(amounts)
        kind = np.zeros(n, dtype=np.int8)
        parameters = {name: np.full(n, np.nan) for name in _PARAMETERS}
        negative = np.zeros(n, dtype=bool)
        for at, uncertainty in enumerate(uncertainties):
            if uncertainty is None:
                continue
            kind[at] = DISTRIBUTION_IDS[uncertainty.type]
            for name, value in uncertainty.params.items():
                if name == "negative":
                    negative[at] = bool(value)
                else:
                    parameters[name][at] = float(value)
        return cls(
            row=np.asarray(row, dtype=np.int32),
            column=np.asarray(column, dtype=np.int32),
            amount=np.asarray(amounts, dtype=np.float64),
            flip=np.asarray(flipped, dtype=bool),
            uncertainty_type=kind,
            negative=negative,
            **parameters,
        )


def _known(what: str, labels: np.ndarray, coordinate: np.ndarray) -> None:
    """Invalid when a row names a label the coordinate does not hold."""
    unknown = labels[~np.isin(labels, coordinate)]
    if unknown.size:
        raise Invalid(
            f"{unknown.size} {what} name a label the background does not hold, "
            f"the first {str(unknown[0])!r}"
        )


def _exchanges(rows: Rows, row: nb.StoredCoord, column: nb.StoredCoord) -> Exchanges:
    """The rows at the positions of two coordinates, their distributions as columns."""
    return Exchanges.of(
        row=row.to_position(np.asarray(rows.rows)),
        column=column.to_position(np.asarray(rows.columns)),
        amounts=rows.amounts,
        flipped=rows.flipped,
        uncertainties=rows.uncertainties,
    )


def _signed(rows: Rows) -> np.ndarray:
    """Each row's amount as it enters the matrix."""
    return np.where(np.asarray(rows.flipped, dtype=bool), -1.0, 1.0) * np.asarray(
        rows.amounts, dtype=np.float64
    )


class Background:
    """A database compiled for calculation. `technosphere` is over ("product", "activity"),
    `biosphere` over ("flow", "activity") and `characterization` over ("category", "flow").
    "product" and "activity" share one coordinate: one label per dataset, its native id."""

    def __init__(
        self,
        database: Database,
        methods: Sequence[Method],
        coords: dict[str, nb.StoredCoord],
        technosphere: nb.SparseArray,
        biosphere: nb.SparseArray,
        characterization: nb.SparseArray,
        exchanges: dict[str, Exchanges],
    ) -> None:
        self.database = database
        self.methods = tuple(methods)
        self.coords = coords
        self.technosphere = technosphere
        self.biosphere = biosphere
        self.characterization = characterization
        self.exchanges = exchanges
        self._category = {method.id: at for at, method in enumerate(self.methods)}

    @classmethod
    def compile(
        cls,
        database: Database,
        activities: Sequence[str],
        flows: Sequence[str],
        methods: Sequence[Method],
        technosphere: Rows,
        biosphere: Rows,
        factors: Factors,
    ) -> Background:
        """The background of these datasets, flows and methods. A dataset's rows at one
        coordinate, its production and its use of its own product, are added. Invalid for a row
        naming a label outside its coordinate."""
        activity_labels = np.array(sorted(activities))
        flow_labels = np.array(sorted(flows))
        category_labels = np.array([method.id for method in methods])
        _known("technosphere rows", np.asarray(technosphere.rows), activity_labels)
        _known("technosphere columns", np.asarray(technosphere.columns), activity_labels)
        _known("biosphere rows", np.asarray(biosphere.rows), flow_labels)
        _known("biosphere columns", np.asarray(biosphere.columns), activity_labels)
        _known("factor categories", np.asarray(factors.categories), category_labels)
        _known("factor flows", np.asarray(factors.flows), flow_labels)
        activity = nb.StoredCoord(activity_labels)
        coords = {
            "product": activity,
            "activity": activity,
            "flow": nb.StoredCoord(flow_labels),
            "category": nb.StoredCoord(category_labels),
        }
        return cls(
            database,
            methods,
            coords,
            nb.from_long(
                ("product", "activity"),
                coords,
                {
                    "product": np.asarray(technosphere.rows),
                    "activity": np.asarray(technosphere.columns),
                },
                _signed(technosphere),
                on_duplicate="sum",
            ),
            nb.from_long(
                ("flow", "activity"),
                coords,
                {"flow": np.asarray(biosphere.rows), "activity": np.asarray(biosphere.columns)},
                _signed(biosphere),
                on_duplicate="sum",
            ),
            nb.from_long(
                ("category", "flow"),
                coords,
                {"category": np.asarray(factors.categories), "flow": np.asarray(factors.flows)},
                np.asarray(factors.values, dtype=np.float64),
                on_duplicate="sum",
            ),
            {
                "technosphere": _exchanges(technosphere, activity, activity),
                "biosphere": _exchanges(biosphere, coords["flow"], activity),
            },
        )

    def treating(self) -> frozenset[str]:
        """The datasets whose production, net of their use of their own product, enters the
        matrix negative: the treatments, each taking in the waste its reference names, so a
        consumer sends it a negative amount. ecoinvent states such a reference as a negative
        output and openLCA as an input; both compile to a negative production."""
        rows = self.exchanges["technosphere"]
        own = np.asarray(rows.row) == np.asarray(rows.column)
        signed = np.where(np.asarray(rows.flip)[own], -1.0, 1.0) * np.asarray(rows.amount)[own]
        labels = self.coords["activity"].labels
        net = np.bincount(np.asarray(rows.column)[own], weights=signed, minlength=labels.size)
        return frozenset(str(label) for label in labels[net < 0])

    def position(self, dim: str, label: str) -> int | None:
        """The position of a label along "activity" or "flow", whose labels are sorted, or
        None."""
        labels = self.coords[dim].labels
        at = int(np.searchsorted(labels, label))
        return at if at < labels.size and labels[at] == label else None

    def positions(self, methods: Sequence[Method]) -> list[int]:
        """The position of each method's category, in the order given; NotFound naming every
        method the background does not hold."""
        missing = [method.spec for method in methods if method.id not in self._category]
        if missing:
            raise NotFound(f"{self.database.name!r} lacks methods {missing}")
        return [self._category[method.id] for method in methods]

    def arrays(self) -> dict[str, np.ndarray]:
        """Every array the background is saved as, by the name of its file: the label columns,
        each matrix's index and data, and each exchange column."""
        arrays: dict[str, np.ndarray] = {
            "activities": np.asarray(self.coords["activity"].labels),
            "flows": np.asarray(self.coords["flow"].labels),
            "categories": np.asarray(self.coords["category"].labels),
        }
        for name in ("technosphere", "biosphere", "characterization"):
            array: nb.SparseArray = getattr(self, name)
            arrays[f"{name}.index"] = np.asarray(array.index)
            arrays[f"{name}.data"] = np.asarray(array.data)
        for matrix, exchanges in self.exchanges.items():
            for field in fields(Exchanges):
                arrays[f"{matrix}.exchanges.{field.name}"] = np.asarray(
                    getattr(exchanges, field.name)
                )
        return arrays

    def fingerprint(self) -> str:
        """SHA-256 of the arrays in the order of their names, each as its name, its dtype, its
        shape and its bytes in C order, the category labels taken as each category's key less
        the database name, since a method id carries the name its database is installed under:
        what a calculation reads, apart from that name, background.json's other fields and the
        files' headers, so one build installed under any name, and every build holding the same
        numbers, shares it."""
        arrays = self.arrays()
        arrays["categories"] = np.asarray(
            [" > ".join(method.tuple[1:]) for method in self.methods], dtype=np.str_
        )
        digest = hashlib.sha256()
        for name, array in sorted(arrays.items()):
            values = np.ascontiguousarray(array)
            digest.update(f"{name}\0{values.dtype.str}\0{values.shape}\0".encode())
            digest.update(values.tobytes())
        return digest.hexdigest()

    def save(self, directory: Path) -> None:
        """Write the background into a new directory: one .npy file per array and label column,
        and background.json, written last, with the format, the database, the methods and the
        counts."""
        if directory.exists():
            raise Conflict(f"{directory} exists; save the background to a new directory")
        directory.mkdir(parents=True)
        arrays = self.arrays()
        for name, values in arrays.items():
            np.save(directory / f"{name}.npy", values, allow_pickle=False)
        manifest = {
            "format": FORMAT,
            "database": self.database.model_dump(mode="json"),
            "methods": [method.model_dump(mode="json") for method in self.methods],
            "counts": {name: int(values.shape[-1]) for name, values in arrays.items()},
        }
        (directory / "background.json").write_text(json.dumps(manifest, indent=1) + "\n")

    @classmethod
    def load(cls, directory: Path) -> Background:
        """The background saved in a directory, its arrays memory-mapped. NotFound for a
        directory holding none, Invalid for a format this engine does not read."""
        manifest_path = directory / "background.json"
        if not manifest_path.is_file():
            raise NotFound(f"{directory} holds no saved background")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("format") != FORMAT:
            raise Invalid(
                f"{directory} holds background format {manifest.get('format')!r}; "
                f"this engine reads format {FORMAT}"
            )

        def read(name: str) -> np.ndarray:
            return np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)

        activity = nb.StoredCoord(read("activities"))
        coords = {
            "product": activity,
            "activity": activity,
            "flow": nb.StoredCoord(read("flows")),
            "category": nb.StoredCoord(read("categories")),
        }
        dims = {
            "technosphere": ("product", "activity"),
            "biosphere": ("flow", "activity"),
            "characterization": ("category", "flow"),
        }
        arrays = {
            name: nb.SparseArray.from_canonical(
                read(f"{name}.index"), read(f"{name}.data"), coords, frame
            )
            for name, frame in dims.items()
        }
        exchanges = {
            matrix: Exchanges(
                **{f.name: read(f"{matrix}.exchanges.{f.name}") for f in fields(Exchanges)}
            )
            for matrix in ("technosphere", "biosphere")
        }
        return cls(
            Database.model_validate(manifest["database"]),
            [Method.model_validate(method) for method in manifest["methods"]],
            coords,
            arrays["technosphere"],
            arrays["biosphere"],
            arrays["characterization"],
            exchanges,
        )
