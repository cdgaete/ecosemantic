"""The tray's two threads, kept out of the Windows-only module so every host runs them: one polls
the state and draws it, one runs the actions a menu asked for, and neither ends on an error."""

from __future__ import annotations

import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from ecosemantic.tray.app import Tray, dispatched
from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.menu import Action

POLL_SECONDS = 2.0
WORKER_SECONDS = 5.0
TITLE_UNITS = 63
TEXT_UNITS = 255
TOOLTIP_UNITS = 127
ELLIPSIS = "…"


def units(text: str) -> int:
    """How many UTF-16 code units a text takes, which is what a Windows field counts: an astral
    character takes two, and a lone surrogate one."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def clipped(text: str, limit: int) -> str:
    """The text a Windows field keeps: no more than its limit of UTF-16 code units, the last of
    them an ellipsis, and text that fits left as it is."""
    if units(text) <= limit:
        return text
    head = text[:limit]
    while units(head) > limit - 1:
        head = head[:-1]
    return f"{head}{ELLIPSIS}"


@dataclass(kw_only=True)
class Loop:
    """The two threads a shown tray runs: the poll that computes and draws a state every two
    seconds, and the worker that runs one menu action at a time. Both carry a boundary — what
    either raises is written to the tray's log and told to the person, and the thread goes on."""

    tray: Tray
    draw: Callable[[EngineState], None]
    stop_icon: Callable[[], None]
    wait_seconds: float = POLL_SECONDS
    stopping: threading.Event = field(default_factory=threading.Event)
    actions: queue.Queue[Action | None] = field(default_factory=queue.Queue)
    reported: set[str] = field(default_factory=set)

    def asked(self, action: Action) -> None:
        """Ask for an action, which the worker runs in its turn."""
        self.actions.put(action)

    def worked(self) -> None:
        """Run each action asked for, one at a time, until a quit ends the tray."""
        while True:
            action = self.actions.get()
            if action is None:
                return
            try:
                dispatched(self.tray, action)
            except Exception as error:
                _reported(self.tray, error)
            if self.tray.quit_requested:
                self.stop_icon()
                return

    def polled(self) -> None:
        """Compute and draw the state every two seconds, until a quit ends the tray."""
        while not self.stopping.wait(self.wait_seconds):
            try:
                self.draw(self.tray.state())
            except Exception as error:
                reason = f"{type(error).__name__}: {error}"
                if reason not in self.reported:
                    self.reported.add(reason)
                    _reported(self.tray, error)
            if self.tray.quit_requested:
                self.stop_icon()
                return

    def stopped(self) -> None:
        """End both threads, the worker with a last, empty request."""
        self.stopping.set()
        self.actions.put(None)


def _reported(tray: Tray, error: BaseException) -> None:
    """Report one error from a boundary; a report that itself fails goes to standard error, which
    is the log or the console, so neither thread ends on it."""
    try:
        tray.report_error(error)
    except Exception as reporting:
        print(f"the tray could not report {error!r}: {reporting!r}", file=sys.stderr, flush=True)
