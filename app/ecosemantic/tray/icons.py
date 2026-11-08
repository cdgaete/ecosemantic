"""The picture the tray shows: the brand mark with a disc in its corner coloured by the engine's
state."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ecosemantic.tray.engine import EngineState

ICON = Path(__file__).with_name("icon-64.png")
DISC_PIXELS = 20
GREEN = (0x2E, 0x7D, 0x32)
AMBER = (0xF9, 0xA8, 0x25)
GREY = (0x75, 0x75, 0x75)
RED = (0xC6, 0x28, 0x28)


def colour_of(state: EngineState) -> tuple[int, int, int]:
    """The colour of the disc: red for an engine that failed, grey for one that stopped or a bridge
    that is off, green for a bridge that serves, and amber for everything on the way to serving —
    starting, connecting, offline, and signed out."""
    if state.kind == "failed":
        return RED
    if state.kind == "stopped":
        return GREY
    if state.kind == "starting":
        return AMBER
    if state.bridge == "connected":
        return GREEN
    if state.bridge == "off":
        return GREY
    return AMBER


def icon_image(state: EngineState) -> Image.Image:
    """The brand mark, 64 pixels square, with a 20-pixel disc in its lower right corner coloured by
    the state."""
    image = Image.open(ICON).convert("RGBA")
    drawing = ImageDraw.Draw(image)
    left = image.width - DISC_PIXELS
    top = image.height - DISC_PIXELS
    drawing.ellipse(
        (left, top, left + DISC_PIXELS - 1, top + DISC_PIXELS - 1),
        fill=colour_of(state),
    )
    return image
