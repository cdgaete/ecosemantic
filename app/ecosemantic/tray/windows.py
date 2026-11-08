"""The tray on this machine: the shell, the clipboard, Windows' start-at-login value, a launcher
that ends what it starts when the tray ends, and the notification-area loop that shows it."""

from __future__ import annotations

import sys

if sys.platform != "win32":
    raise ImportError("ecosemantic.tray.windows runs on Windows only")

import ctypes
import os
import subprocess
import threading
import time
import winreg
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

import pystray

from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.tray.app import Tray
from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.home import APP, login_command
from ecosemantic.tray.icons import colour_of, icon_image
from ecosemantic.tray.loop import (
    POLL_SECONDS,
    TEXT_UNITS,
    TITLE_UNITS,
    TOOLTIP_UNITS,
    WORKER_SECONDS,
    Loop,
    clipped,
)
from ecosemantic.tray.menu import (
    Action,
    StartAtLogin,
    checked_of,
    clickable,
    menu_for,
    title,
)

CREATE_NO_WINDOW = 0x08000000
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
HWND_MESSAGE = wintypes.HWND(-3)
MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_SETFOREGROUND = 0x00010000
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_VALUE = APP
APPROVED_OFF = 0x03
CLIPBOARD_TRIES = 10
CLIPBOARD_PAUSE_SECONDS = 0.05
HOLD_SECONDS = 30.0

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class _IoCounters(ctypes.Structure):
    _fields_ = (
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    )


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def _declared() -> None:
    """Declare the argument and result types of every function this module calls, so a 64-bit handle
    is never truncated to 32 bits."""
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.CreateWindowExW.argtypes = (
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    )
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = (wintypes.HWND,)
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
    user32.MessageBoxW.restype = ctypes.c_int
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = wintypes.HANDLE


_declared()


def _failed(step: str, code: int | None = None) -> Unavailable:
    """What a failed Windows call is told as: the step and the error Windows keeps for it, which
    ctypes saves aside after each call when the library is opened with `use_last_error`."""
    return Unavailable(
        f"{step} failed: {ctypes.WinError(ctypes.get_last_error() if code is None else code)}"
    )


def _unnamed(step: str, error: OSError) -> Unavailable:
    """What a Windows call that raised is told as: the step and the error it carried."""
    return Unavailable(f"{step}: {error}")


def _contained(step: str, code: int, process: subprocess.Popen[bytes]) -> Unavailable:
    """The refusal of a process this tray could not put in its job: the step and the Windows error
    it left, and whether the process is still running outside the job."""
    if _killed(process):
        return _failed(step, code)
    return Unavailable(
        f"{_failed(step, code)}; the process {process.pid} may still run outside the job"
    )


def _killed(process: subprocess.Popen[bytes]) -> bool:
    """End a process this tray started and answer whether its end came within the wait."""
    process.kill()
    try:
        process.wait(timeout=HOLD_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return True


def _message_window() -> wintypes.HWND:
    """A window that receives messages and nothing else, which the clipboard needs: opened with no
    window, `SetClipboardData` fails."""
    window = user32.CreateWindowExW(
        0,
        "STATIC",
        None,
        0,
        0,
        0,
        0,
        0,
        HWND_MESSAGE,
        None,
        kernel32.GetModuleHandleW(None),
        None,
    )
    if not window:
        raise _failed("CreateWindowExW")
    return window


class Job:
    """A job object whose processes end when its last handle closes, which is when the tray ends for
    any reason at all."""

    def __init__(self) -> None:
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise _failed("CreateJobObjectW")
        self._handle = handle
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            raise _failed("SetInformationJobObject")

    def hold(self, process: subprocess.Popen[bytes]) -> None:
        """Put a process this tray started into the job, so Windows ends it when the tray does; one
        the job refuses is ended here, and a process whose end the wait runs out on is named, since
        it may still run outside the job."""
        handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, process.pid)
        if not handle:
            raise _contained("OpenProcess", ctypes.get_last_error(), process)
        try:
            if kernel32.AssignProcessToJobObject(self._handle, handle):
                return
            code = ctypes.get_last_error()
        finally:
            kernel32.CloseHandle(handle)
        raise _contained("AssignProcessToJobObject", code, process)


class WindowsLauncher:
    """Start a program with no window and its output appended to a log, inside one job object when
    the tray must end it with itself."""

    def __init__(self, *, job: Job | None = None) -> None:
        self._job = job if job is not None else Job()

    def start(self, command: list[str], log: Path, contained: bool) -> subprocess.Popen[bytes]:
        """Start the command with no window, its standard input nowhere and its output at the end of
        the log; one the tray must end with itself joins its job, and the bridge's commands do not,
        since a browser a sign-in opens is their child and must outlive the tray."""
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as written:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=written,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        if contained:
            self._job.hold(process)
        return process


def clipboard_text() -> str:
    """What this machine's clipboard holds as Unicode text, empty when it holds no text."""
    window = _message_window()
    try:
        _opened(window)
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise _failed("GlobalLock")
            try:
                return ctypes.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    finally:
        user32.DestroyWindow(window)


def copy_text(text: str) -> None:
    """Put text on this machine's clipboard as Unicode text, waiting out another program that holds
    the clipboard for a moment."""
    window = _message_window()
    try:
        _opened(window)
        try:
            if not user32.EmptyClipboard():
                raise _failed("EmptyClipboard")
            written = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(written)
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                raise _failed("GlobalAlloc")
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                code = ctypes.get_last_error()
                kernel32.GlobalFree(handle)
                raise _failed("GlobalLock", code)
            try:
                ctypes.memmove(pointer, written, size)
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                code = ctypes.get_last_error()
                kernel32.GlobalFree(handle)
                raise _failed("SetClipboardData", code)
        finally:
            user32.CloseClipboard()
    finally:
        user32.DestroyWindow(window)


def _opened(window: wintypes.HWND) -> None:
    """Open the clipboard with this window, trying again while another program holds it."""
    code = 0
    for _ in range(CLIPBOARD_TRIES):
        if user32.OpenClipboard(window):
            return
        code = ctypes.get_last_error()
        time.sleep(CLIPBOARD_PAUSE_SECONDS)
    raise _failed("OpenClipboard", code)


class WindowsPlatform:
    """This machine as the tray needs it: its notifications and refusals through the shell, its
    clipboard, Windows' start-at-login value under one value name, and the launcher that keeps the
    engine it starts in one job."""

    def __init__(
        self,
        *,
        value: str = RUN_VALUE,
        command: str | None = None,
        job: Job | None = None,
    ) -> None:
        self.launcher = WindowsLauncher(job=job)
        self.value = value
        self.command = command if command is not None else self.login_command()
        self._icon: pystray.Icon | None = None
        self._shown: pystray.Icon | None = None
        self._waiting: list[tuple[str, str]] = []
        self._waiting_lock = threading.Lock()

    @staticmethod
    def login_command() -> str:
        """The command Windows runs at login, from the `pythonw.exe` beside this interpreter."""
        return login_command(Path(sys.executable))

    def showing(self, icon: pystray.Icon) -> None:
        """Keep the icon notifications will go through, which the flush the tray's setup runs puts
        in place once the icon is visible."""
        with self._waiting_lock:
            self._shown = icon

    def flush(self) -> None:
        """Take the kept icon as the one notifications go through and show those that waited for
        it, which pystray drops while no icon is in the tray."""
        with self._waiting_lock:
            waiting, self._waiting = self._waiting, []
            self._icon = self._shown
            icon = self._icon
        if icon is None:
            return
        for heading, text in waiting:
            icon.notify(clipped(text, TEXT_UNITS), clipped(heading, TITLE_UNITS))

    def notify(self, *, title: str, text: str) -> None:
        """Show a notification, which waits for the icon while the tray has not drawn one yet."""
        with self._waiting_lock:
            icon = self._icon
            if icon is None:
                self._waiting.append((title, text))
                return
        icon.notify(clipped(text, TEXT_UNITS), clipped(title, TITLE_UNITS))

    def refuse(self, *, title: str, text: str) -> None:
        """Show a message the person has to dismiss, for a tray that will not start at all."""
        refuse(title, text)

    def open_url(self, url: str) -> None:
        """Open an address in this person's browser, naming the shell's refusal."""
        try:
            os.startfile(url)
        except OSError as error:
            raise Unavailable(f"the browser could not be opened: {error}") from error

    def open_folder(self, path: Path) -> None:
        """Open a folder in this person's file browser, naming the shell's refusal."""
        try:
            os.startfile(str(path))
        except OSError as error:
            raise Unavailable(f"the folder could not be opened: {error}") from error

    def copy(self, text: str) -> None:
        """Put text on this machine's clipboard."""
        copy_text(text)

    def start_at_login(self) -> StartAtLogin:
        """Whether this product starts at login, as its Run value says and as Windows' own switch in
        `StartupApproved` allows: a value Windows keeps none of counts as on, and a Run key it does
        not hold reads as off."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, self.value)
            approved = self._approved()
        except FileNotFoundError:
            return StartAtLogin(enabled=False)
        except OSError as error:
            raise _unnamed("the Run value could not be read", error) from error
        turned_off = approved is not None and approved[:1] == bytes([APPROVED_OFF])
        return StartAtLogin(enabled=not turned_off, turned_off_by_windows=turned_off)

    def set_start_at_login(self, enabled: bool) -> None:
        """Write or delete the Run value this product starts at login by, and never write Windows'
        own switch, which is the person's to set. Writing creates the key; deleting a value from a
        key Windows does not hold is done."""
        try:
            if enabled:
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.SetValueEx(key, self.value, 0, winreg.REG_SZ, self.command)
                return
        except OSError as error:
            raise _unnamed("the Run value could not be written", error) from error
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.value)
        except FileNotFoundError:
            return
        except OSError as error:
            raise _unnamed("the Run value could not be deleted", error) from error

    def _approved(self) -> bytes | None:
        """The binary value Windows' own switch keeps for this product, or none when it keeps
        none."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
                data, _ = winreg.QueryValueEx(key, self.value)
        except FileNotFoundError:
            return None
        return bytes(data)


def refuse(title: str, text: str) -> None:
    """Show a message the person has to dismiss, for a tray that will not start at all, which a
    platform that could not even be built still reaches."""
    if not user32.MessageBoxW(None, text, title, MB_OK | MB_ICONERROR | MB_SETFOREGROUND):
        raise _failed("MessageBoxW")


def menu(loop: Loop, state: EngineState, login: StartAtLogin) -> pystray.Menu:
    """The pystray menu one state offers, each item that acts asking for its action rather than
    running it: the tray's own thread never waits on the tray's lock."""
    return pystray.Menu(
        *[
            pystray.MenuItem(
                item.text,
                _asking(loop, item.action) if item.action is not None else None,
                checked=checked_of(item),
                enabled=clickable(item),
            )
            for item in menu_for(state, login)
        ]
    )


def _asking(loop: Loop, action: Action) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
    def chosen(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        loop.asked(action)

    return chosen


def session_handlers(tray: Tray) -> dict[int, Callable[[int, int], int]]:
    """Windows' end-of-session questions, answered so the tray blocks neither sign-out nor shutdown:
    the session may end, and the engine is asked to stop once with the tray, which its job ends
    anyway."""
    stopped = threading.Event()

    def endsession(wparam: int, _lparam: int) -> int:
        if wparam and not stopped.is_set():
            stopped.set()
            tray.engine.ask()
        return 0

    def queried(_wparam: int, _lparam: int) -> int:
        return 1

    return {WM_QUERYENDSESSION: queried, WM_ENDSESSION: endsession}


class Showing:
    """The tray as it is shown: the icon, the state last drawn, and the loop whose threads poll and
    act."""

    def __init__(
        self, tray: Tray, platform: WindowsPlatform, *, interval: float = POLL_SECONDS
    ) -> None:
        self.tray = tray
        self.platform = platform
        self.state = tray.state()
        self.login = platform.start_at_login()
        self.loop = Loop(
            tray=tray,
            draw=self.draw,
            stop_icon=lambda: None,
            wait_seconds=interval,
        )
        self.icon = pystray.Icon(
            APP, icon_image(self.state), clipped(title(self.state), TOOLTIP_UNITS)
        )
        self.loop.stop_icon = self.icon.stop
        platform.showing(self.icon)
        self.icon.menu = menu(self.loop, self.state, self.login)

    def draw(self, state: EngineState) -> None:
        """Draw a state just computed: the tooltip always, the icon when its colour changes, and the
        menu when what it offers does."""
        login = self.platform.start_at_login()
        self.icon.title = clipped(title(state), TOOLTIP_UNITS)
        if colour_of(state) != colour_of(self.state):
            self.icon.icon = icon_image(state)
        if state != self.state or login != self.login:
            self.icon.menu = menu(self.loop, state, login)
        self.state = state
        self.login = login

    def shown(self, icon: pystray.Icon) -> None:
        """The setup pystray calls once the loop runs: show the icon, then the notifications that
        waited for it."""
        icon.visible = True
        self.platform.flush()

    def run(self) -> None:
        """Show the icon until it stops, its poll and its worker beside it."""
        worked = threading.Thread(target=self.loop.worked, name="tray-actions", daemon=True)
        polled = threading.Thread(target=self.loop.polled, name="tray-state", daemon=True)
        worked.start()
        polled.start()
        try:
            self.icon.run(setup=self.shown)
        finally:
            self.loop.stopped()
            worked.join(timeout=WORKER_SECONDS)
            polled.join(timeout=self.loop.wait_seconds + WORKER_SECONDS)


def run_tray(tray: Tray) -> None:
    """Show the tray on this machine's notification area until quit runs: one thread polls the state
    every two seconds and draws it, another runs each menu action, and Windows may end the session
    with the tray."""
    platform = tray.platform
    if not isinstance(platform, WindowsPlatform):
        raise Invalid(f"the tray shows on a Windows platform, and this one is {platform!r}")
    showing = Showing(tray, platform)
    showing.icon._message_handlers.update(session_handlers(tray))
    showing.run()
