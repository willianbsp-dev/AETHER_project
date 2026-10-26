from machine_feira.automation import DesktopAutomation
from machine_feira.hyprland import HyprlandDispatcher
from machine_feira.types import Gesture, GestureEvent, Point


class _FakePyAutoGUI:
    FAILSAFE = False
    PAUSE = 0.0

    def __init__(self) -> None:
        self.moved_to: tuple[int, int] | None = None
        self.position_now = (500, 250)
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
        self.position_now = (x, y)

    def position(self) -> tuple[int, int]:
        return self.position_now

    def mouseDown(self) -> None:  # noqa: N802
        self.mouse_down_called = True

    def mouseUp(self) -> None:  # noqa: N802
        self.mouse_up_called = True

    def click(self, button: str = "left") -> None:
        self.clicks += 1
        if button == "right":
            self.right_clicks = getattr(self, "right_clicks", 0) + 1

    def scroll(self, amount: int) -> None:
        self.scrolled += amount

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)

    def press(self, key: str) -> None:
        self.pressed.append(key)

    def keyDown(self, key: str) -> None:  # noqa: N802
        self.pressed.append(f"down_{key}")

    def keyUp(self, key: str) -> None:  # noqa: N802
        self.pressed.append(f"up_{key}")


def test_ydotool_drag_uses_left_button_codes() -> None:
    automation, _, _ = _setup_automation()
    calls: list[tuple[str, ...]] = []
    automation._ydotool_run = lambda *args: calls.append(args) or True  # type: ignore[method-assign]
    automation.handle(GestureEvent(Gesture.PINCH, Point(0.5, 0.5)))
    automation.handle(GestureEvent(Gesture.NONE, Point(0.5, 0.5)))
    assert ("click", "0x40") in calls
    assert ("click", "0x80") in calls


class _FakeHyprland(HyprlandDispatcher):
    def __init__(self, available: bool = True) -> None:
        super().__init__()
        self._available_flag = available
        self.active_window: dict | None = {"fullscreen": 0, "title": "Test Window"}
        self.dispatched: list[str] = []

    def is_available(self) -> bool:
        return self._available_flag

    def get_active_window(self) -> dict | None:
        if not self._available_flag:
            return None
        return self.active_window

    def dispatch_raw(self, *args: str) -> bool:
        if not self._available_flag:
            return False
        cmd_str = " ".join(args).strip()
        self.dispatched.append(cmd_str)
        if "internal = 1" in cmd_str or "fullscreen 1" in cmd_str:
            if self.active_window:
                self.active_window["fullscreen"] = 1
        elif "internal = 0" in cmd_str or "fullscreen 0" in cmd_str:
            if self.active_window:
                self.active_window["fullscreen"] = 0
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
    # A posição do indicador já determina diretamente a posição da tela.
    automation.handle(GestureEvent(Gesture.NONE, Point(0.5, 0.5), cursor_enabled=True))
    assert fake_gui.moved_to == (499, 249)
    automation.handle(GestureEvent(Gesture.NONE, Point(0.6, 0.6), cursor_enabled=True))
    # A segunda posição é suavizada para não saltar com o tremor da câmera.
    assert fake_gui.moved_to == (521, 260)


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


def test_pinch_in_content_drags_without_super() -> None:
    automation, fake_gui, _ = _setup_automation()
    automation.handle(GestureEvent(Gesture.PINCH, Point(0.5, 0.5)))
    assert automation._dragging
    assert "down_super" not in fake_gui.pressed
    automation.handle(GestureEvent(Gesture.NONE, Point(0.5, 0.5)))
    assert fake_gui.mouse_up_called


def test_pinch_in_top_band_moves_window_with_super() -> None:
    automation, fake_gui, _ = _setup_automation()
    automation.handle(GestureEvent(Gesture.PINCH, Point(0.5, 0.10)))
    assert automation._dragging
    assert "down_super" in fake_gui.pressed
    automation.handle(GestureEvent(Gesture.NONE, Point(0.5, 0.10)))
    assert "up_super" in fake_gui.pressed


def test_only_index_enabled_event_moves_cursor() -> None:
    automation, fake_gui, _ = _setup_automation()

    # Uma palma/ação discreta sem a marca do indicador isolado não pode mover
    # o ponteiro, mesmo que carregue uma coordenada de cursor.
    automation.handle(GestureEvent(Gesture.NONE, Point(0.2, 0.2)))
    automation.handle(GestureEvent(Gesture.NONE, Point(0.8, 0.8)))
    assert fake_gui.moved_to is None

    automation.handle(GestureEvent(Gesture.NONE, Point(0.2, 0.2), cursor_enabled=True))
    automation.handle(GestureEvent(Gesture.NONE, Point(0.3, 0.3), cursor_enabled=True))
    assert fake_gui.moved_to is not None


def test_navigation_and_clicks() -> None:
    automation, fake_gui, _ = _setup_automation()

    automation.handle(GestureEvent(Gesture.DWELL_CLICK, Point(0.5, 0.5)))
    assert fake_gui.clicks == 1

    automation.handle(GestureEvent(Gesture.DOUBLE_CLICK, Point(0.5, 0.5)))
    assert fake_gui.right_clicks == 1

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


def test_voice_hotkey_can_be_configured() -> None:
    automation, fake_gui, _ = _setup_automation()
    automation.handle(GestureEvent(Gesture.VOICE_ACTIVATE, Point(0.5, 0.5)))
    assert fake_gui.hotkeys == []

    automation.voice_hotkey = ("super", "alt", "v")
    automation.handle(GestureEvent(Gesture.VOICE_ACTIVATE, Point(0.5, 0.5)))
    assert ("super", "alt", "v") in fake_gui.hotkeys


def test_restore_toggles_floating_when_window_is_normal() -> None:
    automation, _, fake_hypr = _setup_automation()
    fake_hypr.active_window = {"fullscreen": 0, "title": "Test Window"}
    automation.handle(GestureEvent(Gesture.RESTORE, Point(0.5, 0.5)))
    assert "hl.dsp.window.float({ action = 'toggle' })" in fake_hypr.dispatched


def test_release_stops_drag() -> None:
    automation, fake_gui, _ = _setup_automation()
    automation.handle(GestureEvent(Gesture.PINCH, Point(0.2, 0.2)))
    assert automation._dragging
    automation.release()
    assert not automation._dragging
    assert fake_gui.mouse_up_called


def test_hyprland_window_and_workspace_actions() -> None:
    automation, _, fake_hypr = _setup_automation(hyprland_available=True)

    automation.handle(GestureEvent(Gesture.MAXIMIZE, Point(0.5, 0.5)))
    assert "hl.dsp.window.fullscreen_state({ internal = 1, client = 0, action = 'toggle' })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.RESTORE, Point(0.5, 0.5)))
    assert "hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.MINIMIZE, Point(0.5, 0.5)))
    assert "hl.dsp.window.move({ workspace = 'special:minimized', follow = false })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.SWIPE_LEFT, Point(0.5, 0.5)))
    assert "hl.dsp.focus({ workspace = 'r-1' })" in fake_hypr.dispatched

    automation.handle(GestureEvent(Gesture.SWIPE_RIGHT, Point(0.5, 0.5)))
    assert "hl.dsp.focus({ workspace = 'r+1' })" in fake_hypr.dispatched


def test_hyprland_fallback_when_unavailable() -> None:
    automation, fake_gui, _ = _setup_automation(hyprland_available=False)

    automation.handle(GestureEvent(Gesture.MAXIMIZE, Point(0.5, 0.5)))
    assert ("super", "f") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.RESTORE, Point(0.5, 0.5)))
    assert ("super", "v") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.MINIMIZE, Point(0.5, 0.5)))
    assert ("super", "shift", "m") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.SWIPE_LEFT, Point(0.5, 0.5)))
    assert ("super", "shift", "left") in fake_gui.hotkeys

    automation.handle(GestureEvent(Gesture.SWIPE_RIGHT, Point(0.5, 0.5)))
    assert ("super", "shift", "right") in fake_gui.hotkeys
