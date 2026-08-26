from machine_feira.automation import DesktopAutomation
from machine_feira.hyprland import HyprlandDispatcher
from machine_feira.types import Gesture, GestureEvent, Point


class _FakePyAutoGUI:
    FAILSAFE = False
    PAUSE = 0.0

    def __init__(self) -> None:
        self.moved_to: tuple[int, int] | None = None
        self.mouse_down_called = False
        self.mouse_up_called = False
        self.clicks = 0
        self.scrolled: int = 0
        self.hotkeys: list[tuple[str, ...]] = []
        self.pressed: list[str] = []

    def size(self) -> tuple[int, int]:
        return (1000, 500)

    def moveTo(self, x: int, y: int, duration: float = 0) -> None:  # noqa: N802
        self.moved_to = (x, y)

    def mouseDown(self) -> None:  # noqa: N802
        self.mouse_down_called = True

    def mouseUp(self) -> None:  # noqa: N802
        self.mouse_up_called = True

    def click(self) -> None:
        self.clicks += 1

    def scroll(self, amount: int) -> None:
        self.scrolled += amount

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakeHyprland(HyprlandDispatcher):
    def __init__(self, available: bool = True) -> None:
        super().__init__()
        self._available_flag = available
        self.dispatched: list[str] = []

    def is_available(self) -> bool:
        return self._available_flag

    def dispatch_raw(self, *args: str) -> bool:
        if not self._available_flag:
            return False
        self.dispatched.append(" ".join(args).strip())
        return True

    def ensure_camera_unfocused(self, camera_title_keyword: str = "Machine Feira") -> None:
        pass


def _setup_automation(hyprland_available: bool = True) -> tuple[DesktopAutomation, _FakePyAutoGUI, _FakeHyprland]:
    fake_gui = _FakePyAutoGUI()
    fake_hypr = _FakeHyprland(available=hyprland_available)
    automation = DesktopAutomation(enabled=True, hyprland=fake_hypr)
    automation._pyautogui = fake_gui
    return automation, fake_gui, fake_hypr


def test_cursor_mapping() -> None:
    automation, fake_gui, _ = _setup_automation()
    automation.handle(GestureEvent(Gesture.NONE, Point(0.5, 0.5)))
    assert fake_gui.moved_to == (500, 250)


def test_drag_and_release() -> None:
    automation, fake_gui, _ = _setup_automation()
    # Inicia arrasto
    automation.handle(GestureEvent(Gesture.PINCH, Point(0.2, 0.2)))
    assert fake_gui.mouse_down_called
    assert automation._dragging

    # Solta arrasto
    automation.handle(GestureEvent(Gesture.NONE, Point(0.4, 0.4)))
    assert fake_gui.mouse_up_called
    assert not automation._dragging


def test_navigation_and_clicks() -> None:
    automation, fake_gui, _ = _setup_automation()

    automation.handle(GestureEvent(Gesture.DWELL_CLICK, Point(0.5, 0.5)))
    assert fake_gui.clicks == 1

    automation.handle(GestureEvent(Gesture.SCROLL, Point(0.5, 0.5), amount=10))
    assert fake_gui.scrolled == 10

    automation.handle(GestureEvent(Gesture.ZOOM_IN, Point(0.5, 0.5)))
    assert ("ctrl", "+") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.ZOOM_OUT, Point(0.5, 0.5)))
    assert ("ctrl", "-") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.PAGE_FORWARD, Point(0.5, 0.5)))
    assert ("alt", "right") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.PAGE_BACK, Point(0.5, 0.5)))
    assert ("alt", "left") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.CONFIRM, Point(0.5, 0.5)))
    assert "enter" in fake_gui.pressed


def test_voice_activation_callback() -> None:
    voice_triggered = []
    fake_gui = _FakePyAutoGUI()
    automation = DesktopAutomation(
        enabled=True,
        on_voice_activate=lambda: voice_triggered.append(True),
    )
    automation._pyautogui = fake_gui

    automation.handle(GestureEvent(Gesture.VOICE_ACTIVATE, Point(0.5, 0.5)))
    assert voice_triggered == [True]


def test_hyprland_window_and_workspace_actions() -> None:
    automation, _, fake_hypr = _setup_automation(hyprland_available=True)

    automation.handle(GestureEvent(Gesture.MAXIMIZE, Point(0.5, 0.5)))
    assert "hl.dsp.window.fullscreen_state({ internal = 1, client = 0 })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.RESTORE, Point(0.5, 0.5)))
    assert "hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.MINIMIZE, Point(0.5, 0.5)))
    assert "hl.dsp.window.move({ workspace = 'special:magic' })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.SWIPE_LEFT, Point(0.5, 0.5)))
    assert "hl.dsp.focus({ workspace = 'e-1' })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.SWIPE_RIGHT, Point(0.5, 0.5)))
    assert "hl.dsp.focus({ workspace = 'e+1' })" in fake_hypr.dispatched


def test_hyprland_fallback_when_unavailable() -> None:
    automation, fake_gui, _ = _setup_automation(hyprland_available=False)

    automation.handle(GestureEvent(Gesture.MAXIMIZE, Point(0.5, 0.5)))
    assert ("super", "f") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.MINIMIZE, Point(0.5, 0.5)))
    assert ("super", "d") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.SWIPE_LEFT, Point(0.5, 0.5)))
    assert ("super", "shift", "left") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.SWIPE_RIGHT, Point(0.5, 0.5)))
    assert ("super", "shift", "right") in fake_gui.hotkeys