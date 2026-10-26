from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.download import download
from ecosemantic.databases.ecoinvent.release import sha256
from ecosemantic.errors import Invalid, NotFound

MATRIX_EXPORT_FILES = (
    "A_public.csv",
    "B_public.csv",
    "C.csv",
    "ie_index.csv",
    "ee_index.csv",
    "LCIA_index.csv",
)


def write_matrix_export(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in MATRIX_EXPORT_FILES:
        (directory / name).write_bytes(b"x")


class FakeClient:
    matrix_paths: tuple[str, ...] = ("",)

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []

    def get_release(
        self, version: str, system_model: str, release_type: object, _extract: bool
    ) -> Path:
        self.calls.append(("release", version, system_model, str(release_type)))
        folder = self.root / str(release_type).split(".")[-1]
        folder.mkdir(parents=True, exist_ok=True)
        if "cumulative" in str(release_type):
            (folder / "Cut-off Cumulative LCIA v3.10.xlsx").write_bytes(b"x")
        if "matrix" in str(release_type):
            for relative in self.matrix_paths:
                write_matrix_export(folder / relative)
        return folder

    def list_extra_files(self, version: str) -> dict[str, object]:
        return {
            f"ecoinvent {version}_LCIA_implementation.7z": {},
            f"Database-Overview-for-ecoinvent-v{version}.xlsx": {},
            "Market Composition.xlsx": {},
        }

    def get_extra(self, version: str, filename: str) -> Path:
        self.calls.append(("extra", version, filename))
        if filename.endswith(".7z"):
            folder = self.root / "lcia"
            folder.mkdir(exist_ok=True)
            (folder / f"LCIA Implementation {version}.xlsx").write_bytes(b"x")
            return folder
        path = self.root / filename
        path.write_bytes(b"x")
        return path


class MissingExtraClient(FakeClient):
    def list_extra_files(self, version: str) -> dict[str, object]:
        listed = super().list_extra_files(version)
        del listed[f"Database-Overview-for-ecoinvent-v{version}.xlsx"]
        return listed


class TwoWorkbooksClient(FakeClient):
    def get_extra(self, version: str, filename: str) -> Path:
        folder = super().get_extra(version, filename)
        if filename.endswith(".7z"):
            (folder / f"LCIA Implementation {version} appendix.xlsx").write_bytes(b"x")
        return folder


class NestedMatrixClient(FakeClient):
    matrix_paths = ("universal_matrix_export",)


class TwoMatrixDirectoriesClient(FakeClient):
    matrix_paths = ("export_a", "export_b")


class EmptyMatrixClient(FakeClient):
    matrix_paths = ()


def test_download_fetches_the_five_files_a_build_reads(tmp_path: Path) -> None:
    release = download("3.10", "cutoff", FakeClient(tmp_path))
    assert release.lcia.name == "LCIA Implementation 3.10.xlsx"
    assert release.overview.name == "Database-Overview-for-ecoinvent-v3.10.xlsx"
    assert release.cumulative_lcia.name == "Cut-off Cumulative LCIA v3.10.xlsx"
    assert release.matrix.name == "matrix"
    assert (release.matrix / "A_public.csv").is_file()
    assert set(release.files()) == {"ecospold", "lcia", "matrix", "cumulative_lcia", "overview"}


def test_download_resolves_a_matrix_folder_nesting_its_files_one_level_deeper(
    tmp_path: Path,
) -> None:
    release = download("3.12", "cutoff", NestedMatrixClient(tmp_path))
    assert release.matrix.name == "universal_matrix_export"
    assert (release.matrix / "A_public.csv").is_file()


def test_download_refuses_a_matrix_folder_holding_two_export_directories(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="holds 2"):
        download("3.12", "cutoff", TwoMatrixDirectoriesClient(tmp_path))


def test_download_refuses_a_matrix_folder_holding_no_export(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="holds 0"):
        download("3.12", "cutoff", EmptyMatrixClient(tmp_path))


def test_download_names_an_extra_the_release_does_not_list(tmp_path: Path) -> None:
    with pytest.raises(NotFound, match="lists no"):
        download("3.10", "cutoff", MissingExtraClient(tmp_path))


def test_download_refuses_an_lcia_folder_holding_two_workbooks(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="not one"):
        download("3.10", "cutoff", TwoWorkbooksClient(tmp_path))


def test_sha256_of_a_file_is_the_hash_of_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "LCIA Implementation 3.10.xlsx"
    path.write_bytes(b"ecoinvent")
    assert sha256(path) == hashlib.sha256(b"ecoinvent").hexdigest()


def test_sha256_of_a_directory_covers_every_file_in_sorted_relative_path_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "MasterData").mkdir()
    (tmp_path / "MasterData" / "Units.xml").write_bytes(b"<units/>")
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "activity.spold").write_bytes(b"<spold/>")
    digest = sha256(tmp_path)
    assert (
        digest
        == hashlib.sha256(
            b"MasterData/Units.xml<units/>datasets/activity.spold<spold/>"
        ).hexdigest()
    )
    (tmp_path / "datasets" / "activity.spold").write_bytes(b"<tampered/>")
    assert sha256(tmp_path) != digest
