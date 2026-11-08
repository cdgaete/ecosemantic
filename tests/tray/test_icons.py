from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.icons import icon_image

GREEN = (0x2E, 0x7D, 0x32)
AMBER = (0xF9, 0xA8, 0x25)
GREY = (0x75, 0x75, 0x75)
RED = (0xC6, 0x28, 0x28)
CENTRE = (54, 54)


def state(kind: str, bridge: str, *, bridge_on: bool = True) -> EngineState:
    """An engine state of this kind and bridge."""
    return EngineState(kind=kind, bridge=bridge, bridge_on=bridge_on, handle="ana")


CASES = {
    "connected": (state("running", "connected"), GREEN),
    "offline": (state("running", "offline"), AMBER),
    "connecting": (state("running", "connecting"), AMBER),
    "signed out": (state("running", "signed-out"), AMBER),
    "relay stopped": (state("running", "stopped"), AMBER),
    "bridge off": (state("running", "off", bridge_on=False), GREY),
    "starting": (state("starting", "connecting"), AMBER),
    "starting without the bridge": (state("starting", "off", bridge_on=False), AMBER),
    "stopped": (state("stopped", "off", bridge_on=False), GREY),
    "failed": (state("failed", "off", bridge_on=False), RED),
}


@pytest.mark.parametrize("name", CASES)
def test_every_state_has_its_icon(name: str) -> None:
    given, colour = CASES[name]
    image = icon_image(given)
    assert isinstance(image, Image.Image)
    assert image.size == (64, 64)
    seen = image.convert("RGB").getpixel(CENTRE)
    assert seen == colour, (name, seen)


def test_the_icon_is_the_brand_the_payload_carries() -> None:
    brand = Path(__file__).resolve().parents[2] / "app" / "ecosemantic" / "tray" / "icon-64.png"
    assert brand.is_file()
    assert Image.open(brand).size == (64, 64)
