from machine_feira.automation import DesktopAutomation
from machine_feira.types import Gesture, GestureEvent, Point


class _FakePyAutoGUI:
    FAILSAFE = False
    PAUSE = 0.0

    def __init__(self) -> None:
        self.moved_to: tuple[int, int] | None = None
        self.mouse_down_called = False
        self.mouse_up_called = False
        self.clicks = 0
        self.scrolled = 0
        self.hotkeys: list[tuple[str, ...]] = []
        self.pressed: list[str] = []

    def size(self) -> tuple[int, int]:
        return (1000, 500)

    def moveTo(self, x: int, y: int, duration: float = 0) -> None:
        self.moved_to = (x, y)

    def mouseDown(self) -> None:
        self.mouse_down_called = True

    def mouseUp(self) -> None:
        self.mouse_up_called = True

    def click(self) -> None:
        self.clicks += 1

    def scroll(self, amount: int) -> None:
        self.scrolled += amount

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakeWindows:
    def __init__(self) -> None:
        self.maximize_called = False
        self.restore_called = False
        self.minimize_called = False
        self.workspace_next_called = False
        self.workspace_prev_called = False
        self.ensure_camera_unfocused_called = False

    def maximize(self) -> bool:
        self.maximize_called = True
        return True

    def restore(self) -> bool:
        self.restore_called = True
        return True

    def minimize(self) -> bool:
        self.minimize_called = True
        return True

    def workspace_next(self) -> bool:
        self.workspace_next_called = True
        return True

    def workspace_prev(self) -> bool:
        self.workspace_prev_called = True
        return True

    def ensure_camera_unfocused(self) -> None:
        self.ensure_camera_unfocused_called = True


def _setup_automation() -> tuple[
    DesktopAutomation,
    _FakePyAutoGUI,
    _FakeWindows,
]:
    fake_gui = _FakePyAutoGUI()
    fake_windows = _FakeWindows()

    automation = DesktopAutomation(
        enabled=True,
        windows=fake_windows,
    )

    automation._pyautogui = fake_gui

    return automation, fake_gui, fake_windows


def test_cursor_mapping() -> None:
    automation, fake_gui, _ = _setup_automation()

    automation.handle(
        GestureEvent(
            Gesture.NONE,
            Point(0.5, 0.5),
        )
    )

    assert fake_gui.moved_to == (500, 250)


def test_drag_and_release() -> None:
    automation, fake_gui, _ = _setup_automation()

    automation.handle(
        GestureEvent(
            Gesture.PINCH,
            Point(0.2, 0.2),
        )
    )

    assert fake_gui.mouse_down_called
    assert automation._dragging

    automation.handle(
        GestureEvent(
            Gesture.NONE,
            Point(0.4, 0.4),
        )
    )

    assert fake_gui.mouse_up_called
    assert not automation._dragging


def test_navigation_and_clicks() -> None:
    automation, fake_gui, _ = _setup_automation()

    automation.handle(
        GestureEvent(
            Gesture.DWELL_CLICK,
            Point(0.5, 0.5),
        )
    )

    assert fake_gui.clicks == 1

    automation.handle(
        GestureEvent(
            Gesture.SCROLL,
            Point(0.5, 0.5),
            amount=10,
        )
    )

    assert fake_gui.scrolled == 10

    automation.handle(
        GestureEvent(
            Gesture.ZOOM_IN,
            Point(0.5, 0.5),
        )
    )

    assert ("ctrl", "+") in fake_gui.hotkeys

    automation.handle(
        GestureEvent(
            Gesture.ZOOM_OUT,
            Point(0.5, 0.5),
        )
    )

    assert ("ctrl", "-") in fake_gui.hotkeys

    automation.handle(
        GestureEvent(
            Gesture.PAGE_FORWARD,
            Point(0.5, 0.5),
        )
    )

    assert ("alt", "right") in fake_gui.hotkeys

    automation.handle(
        GestureEvent(
            Gesture.PAGE_BACK,
            Point(0.5, 0.5),
        )
    )

    assert ("alt", "left") in fake_gui.hotkeys

    automation.handle(
        GestureEvent(
            Gesture.CONFIRM,
            Point(0.5, 0.5),
        )
    )

    assert "enter" in fake_gui.pressed


def test_voice_activation_callback() -> None:
    voice_triggered = []
    fake_gui = _FakePyAutoGUI()

    automation = DesktopAutomation(
        enabled=True,
        on_voice_activate=lambda: voice_triggered.append(True),
    )

    automation._pyautogui = fake_gui

    automation.handle(
        GestureEvent(
            Gesture.VOICE_ACTIVATE,
            Point(0.5, 0.5),
        )
    )

    assert voice_triggered == [True]


def test_windows_window_actions() -> None:
    automation, _, fake_windows = _setup_automation()

    automation.handle(
        GestureEvent(
            Gesture.MAXIMIZE,
            Point(0.5, 0.5),
        )
    )

    assert fake_windows.maximize_called

    automation.handle(
        GestureEvent(
            Gesture.RESTORE,
            Point(0.5, 0.5),
        )
    )

    assert fake_windows.restore_called

    automation.handle(
        GestureEvent(
            Gesture.MINIMIZE,
            Point(0.5, 0.5),
        )
    )

    assert fake_windows.minimize_called

    automation.handle(
        GestureEvent(
            Gesture.SWIPE_LEFT,
            Point(0.5, 0.5),
        )
    )

    assert fake_windows.workspace_prev_called

    automation.handle(
        GestureEvent(
            Gesture.SWIPE_RIGHT,
            Point(0.5, 0.5),
        )
    )

    assert fake_windows.workspace_next_called