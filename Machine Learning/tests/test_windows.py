from machine_feira import windows as windows_module
from machine_feira.windows import WindowsDispatcher


class _FakeGui:
    def __init__(self) -> None:
        self.hotkeys: list[tuple[str, ...]] = []

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)


def test_workspace_next_creates_when_current_is_last(monkeypatch) -> None:
    fake = _FakeGui()
    monkeypatch.setattr(windows_module, "_pyautogui", lambda: fake)
    dispatcher = WindowsDispatcher()
    monkeypatch.setattr(dispatcher, "ensure_camera_unfocused", lambda: None)
    ids = [b"a" * 16, b"b" * 16]
    monkeypatch.setattr(dispatcher, "virtual_desktop_ids", lambda: ids)
    monkeypatch.setattr(dispatcher, "current_virtual_desktop_id", lambda: ids[-1])
    created: list[bool] = []
    monkeypatch.setattr(dispatcher, "create_virtual_desktop", lambda: created.append(True) or True)

    assert dispatcher.workspace_next()
    assert created == [True]
    assert ("win", "ctrl", "right") not in fake.hotkeys


def test_workspace_next_switches_when_there_is_a_next_desktop(monkeypatch) -> None:
    fake = _FakeGui()
    monkeypatch.setattr(windows_module, "_pyautogui", lambda: fake)
    dispatcher = WindowsDispatcher()
    monkeypatch.setattr(dispatcher, "ensure_camera_unfocused", lambda: None)
    ids = [b"a" * 16, b"b" * 16]
    states = iter([ids[0], ids[1]])
    monkeypatch.setattr(dispatcher, "virtual_desktop_ids", lambda: ids)
    monkeypatch.setattr(dispatcher, "current_virtual_desktop_id", lambda: next(states, ids[1]))
    monkeypatch.setattr(windows_module.time, "sleep", lambda _s: None)
    created: list[bool] = []
    monkeypatch.setattr(dispatcher, "create_virtual_desktop", lambda: created.append(True) or True)

    assert dispatcher.workspace_next()
    assert ("win", "ctrl", "right") in fake.hotkeys
    assert not created


def test_workspace_prev_never_creates_desktop(monkeypatch) -> None:
    fake = _FakeGui()
    monkeypatch.setattr(windows_module, "_pyautogui", lambda: fake)
    dispatcher = WindowsDispatcher()
    monkeypatch.setattr(dispatcher, "ensure_camera_unfocused", lambda: None)

    assert dispatcher.workspace_prev()
    assert fake.hotkeys == [("win", "ctrl", "left")]
