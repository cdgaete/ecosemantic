from __future__ import annotations

from ecosemantic.mcp.treatments import treatments_of
from ecosemantic.model.refs import BackgroundRef
from tests.conftest import frame_system, widget_linking
from tests.fixture_data import CODES, FIXTURE_DB
from tests.memory_background import MemoryInventory


async def test_treatments_of_reads_the_system_and_its_links() -> None:
    frame = frame_system()
    glass = BackgroundRef(database=FIXTURE_DB, id=CODES["glass"])
    frame.process("frame").exchanges[1].input = glass
    widget = widget_linking(frame)
    # the widget sends elec and steel, the frame only glass; plastic is sent by neither
    inventory = MemoryInventory({CODES["elec"], CODES["glass"], CODES["plastic"]})
    found = await treatments_of(inventory, widget, {frame.id: frame})
    assert found == {BackgroundRef(database=FIXTURE_DB, id=CODES["elec"]), glass}
