from __future__ import annotations

from pathlib import Path

from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.tables.folder import write_folder
from ecosemantic.tables.reader import assemble
from tests.tables.test_folder import spaced


def test_a_folder_reassembles_into_the_document_it_was_rendered_from(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    assert content_hash(assemble(folder)) == content_hash(system)


def test_an_edited_value_reassembles_into_a_different_document(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        path.read_text().replace("fabric_mass,0.2,", "fabric_mass,0.25,"), encoding="utf-8"
    )
    assert content_hash(assemble(folder)) != content_hash(system)


def test_an_assembled_document_carries_the_hash_of_what_it_holds(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, spaced(product_system))
    assembled = assemble(folder)
    assert assembled.hash == content_hash(assembled)
