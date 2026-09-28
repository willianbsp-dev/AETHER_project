"""Camada de automação desktop. Integra PyAutoGUI e comandos Hyprland."""

from __future__ import annotations

from typing import Callable
from .hyprland import HyprlandDispatcher
from .types import Gesture, GestureEvent

# Gestos onde o cursor do mouse não deve ser reposicionado
NON_CURSOR_GESTURES = {
    Gesture.MAXIMIZE,
    Gesture.RESTORE,
    Gesture.MINIMIZE,
    Gesture.TOGGLE_MINIMIZED,
    Gesture.SWIPE_LEFT,
    Gesture.SWIPE_RIGHT,
    Gesture.VOICE_ACTIVATE,
}


class DesktopAutomation:
    def __init__(
        self,
        enabled: bool = False,
        hyprland: HyprlandDispatcher | None = None,
        on_voice_activate: Callable[[], None] | None = None,
        voice_hotkey: tuple[str, ...] | None = None,
    ) -> None:
        self.enabled = enabled
        self._dragging = False
        self._pyautogui = None
        self._last_screen_pos: tuple[int, int] | None = None
        self.hyprland = hyprland or HyprlandDispatcher()
        self.on_voice_activate = on_voice_activate
        self.voice_hotkey = tuple(k for k in (voice_hotkey or ()) if k)

        if enabled:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.01
            self._pyautogui = pyautogui

    def handle(self, event: GestureEvent) -> None:
        if not self.enabled or self._pyautogui is None:
            return

        # 1. Movimentação do Cursor
        if event.gesture not in NON_CURSOR_GESTURES:
            cursor_x, cursor_y = self._screen_position(event)
            if self._last_screen_pos != (cursor_x, cursor_y):
                self._pyautogui.moveTo(cursor_x, cursor_y, duration=0)
                self._last_screen_pos = (cursor_x, cursor_y)

        # 2. Arrastar Janela / Drag & Drop (Usa Super + Clique para compatibilidade total com Hyprland)
        if event.gesture is Gesture.PINCH:
            if not self._dragging:
                self.hyprland.ensure_camera_unfocused()
                self._pyautogui.keyDown("super")
                self._pyautogui.mouseDown()
                self._dragging = True
        elif self._dragging:
            self._pyautogui.mouseUp()
            self._pyautogui.keyUp("super")
            self._dragging = False

        # 3. Cliques e Interações no Desktop
        if event.gesture is Gesture.DWELL_CLICK:
            self.hyprland.ensure_camera_unfocused()
            self._pyautogui.click()
        elif event.gesture is Gesture.SCROLL:
            self._pyautogui.scroll(event.amount)
        elif event.gesture is Gesture.ZOOM_IN:
            self._send_hotkey("ctrl", "+")
        elif event.gesture is Gesture.ZOOM_OUT:
            self._send_hotkey("ctrl", "-")
        elif event.gesture is Gesture.PAGE_FORWARD:
            self._send_hotkey("alt", "right")
        elif event.gesture is Gesture.PAGE_BACK:
            self._send_hotkey("alt", "left")
        elif event.gesture is Gesture.CONFIRM:
            # Se a gaveta de minimizadas estiver aberta, desminimiza; caso contrário, envia Enter
            if self.hyprland.is_special_workspace_open("minimized"):
                self.hyprland.restore()
            else:
                self._send_press("enter")
        elif event.gesture is Gesture.VOICE_ACTIVATE:
            self._trigger_voice()
        elif event.gesture is Gesture.MAXIMIZE:
            if not self.hyprland.maximize() and not self.hyprland.is_available():
                self._send_hotkey("super", "f")
        elif event.gesture is Gesture.RESTORE:
            if not self.hyprland.restore() and not self.hyprland.is_available():
                self._send_hotkey("super", "v")
        elif event.gesture is Gesture.MINIMIZE:
            if not self.hyprland.minimize() and not self.hyprland.is_available():
                self._send_hotkey("super", "shift", "m")
        elif event.gesture is Gesture.TOGGLE_MINIMIZED:
            if not self.hyprland.toggle_special_minimized() and not self.hyprland.is_available():
                self._send_hotkey("super", "m")
        elif event.gesture is Gesture.SWIPE_LEFT:
            if not self.hyprland.workspace_prev() and not self.hyprland.is_available():
                self._send_hotkey("super", "shift", "left")
        elif event.gesture is Gesture.SWIPE_RIGHT:
            if not self.hyprland.workspace_next() and not self.hyprland.is_available():
                self._send_hotkey("super", "shift", "right")

    def _send_hotkey(self, *keys: str) -> None:
        if self._pyautogui is None or not keys:
            return
        self.hyprland.ensure_camera_unfocused()
        self._pyautogui.hotkey(*keys)

    def _send_press(self, key: str) -> None:
        if self._pyautogui is None:
            return
        self.hyprland.ensure_camera_unfocused()
        self._pyautogui.press(key)

    def _trigger_voice(self) -> None:
        if self.on_voice_activate is not None:
            self.on_voice_activate()
            return
        if self.voice_hotkey:
            self._send_hotkey(*self.voice_hotkey)

    def release(self) -> None:
        if self.enabled and self._pyautogui:
            if self._dragging:
                self._pyautogui.mouseUp()
                self._pyautogui.keyUp("super")
        self._dragging = False
        self._last_screen_pos = None

    def _screen_position(self, event: GestureEvent) -> tuple[int, int]:
        assert self._pyautogui is not None
        width, height = self._pyautogui.size()
        clamped_x = max(0.0, min(1.0, event.cursor.x))
        clamped_y = max(0.0, min(1.0, event.cursor.y))
        x = min(width - 1, int(clamped_x * width))
        y = min(height - 1, int(clamped_y * height))
        return x, y
