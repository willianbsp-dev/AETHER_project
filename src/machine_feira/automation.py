"""Camada de automação desktop. Integra PyAutoGUI e comandos Hyprland."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Callable
from .hyprland import HyprlandDispatcher
from .types import Gesture, GestureEvent

logger = logging.getLogger(__name__)


# Gestos onde o cursor do mouse não deve ser reposicionado
NON_CURSOR_GESTURES = {
    Gesture.MAXIMIZE,
    Gesture.RESTORE,
    Gesture.MINIMIZE,
    Gesture.TOGGLE_MINIMIZED,
    Gesture.SWIPE_LEFT,
    Gesture.SWIPE_RIGHT,
    Gesture.VOICE_ACTIVATE,
    Gesture.PAUSE_TOGGLE,
    Gesture.VIRTUAL_KEYBOARD,
}

# Pequenos movimentos da mão não devem causar tremor no ponteiro, mas também não
# podem ser descartados completamente: a mão passa a funcionar como um trackpad.
CURSOR_DEADZONE = 0.0015
CURSOR_SENSITIVITY = 1.35


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
        self._last_cursor: tuple[float, float] | None = None
        self._screen_cursor: tuple[int, int] | None = None
        self.hyprland = hyprland or HyprlandDispatcher()
        self.on_voice_activate = on_voice_activate
        self.voice_hotkey = tuple(k for k in (voice_hotkey or ()) if k)
        self._paused = False

        if enabled:
            try:
                import pyautogui

                # O cursor pode naturalmente alcançar o canto durante o
                # controle relativo; o encerramento continua sendo feito por q.
                pyautogui.FAILSAFE = False
                pyautogui.PAUSE = 0.01
                self._pyautogui = pyautogui
            except Exception as err:
                # Em Wayland, PyAutoGUI pode não conseguir abrir o backend
                # X11. A aplicação continua executável em modo seguro e os
                # testes podem injetar um backend compatível.
                logger.warning("Automação gráfica indisponível: %s", err)

    def handle(self, event: GestureEvent) -> None:
        if not self.enabled or self._pyautogui is None:
            return

        if event.gesture is Gesture.PAUSE_TOGGLE:
            self._paused = not self._paused
            if self._paused:
                self.release()
            return
        if self._paused:
            return

        # 1. Movimentação contínua do cursor.
        # O primeiro quadro apenas cria a âncora; assim a câmera não faz o
        # ponteiro saltar para uma coordenada absoluta ao iniciar o controle.
        if event.gesture not in NON_CURSOR_GESTURES:
            self._move_cursor_relative(event)
        else:
            # Evita um salto quando uma ação discreta termina.
            self._last_cursor = (event.cursor.x, event.cursor.y)

        # 2. Arrastar Janela / Drag & Drop (Usa Super + Clique para compatibilidade total com Hyprland)
        if event.gesture is Gesture.PINCH:
            if not self._dragging:
                self.hyprland.ensure_camera_unfocused()
                self._send_key_down("super")
                self._pyautogui.mouseDown()
                self._dragging = True
        elif self._dragging:
            self._pyautogui.mouseUp()
            self._send_key_up("super")
            self._dragging = False

        # 3. Cliques e Interações no Desktop
        if event.gesture is Gesture.DWELL_CLICK:
            self.hyprland.ensure_camera_unfocused()
            self._pyautogui.click()
        elif event.gesture is Gesture.DOUBLE_CLICK:
            self.hyprland.ensure_camera_unfocused()
            self._pyautogui.click(button="right")
        elif event.gesture is Gesture.SCROLL:
            self.hyprland.ensure_camera_unfocused()
            self._pyautogui.scroll(event.amount)
        elif event.gesture is Gesture.ZOOM_IN:
            self._send_hotkey("ctrl", "+")
            self._send_hotkey("ctrl", "=")
        elif event.gesture is Gesture.ZOOM_OUT:
            self._send_hotkey("ctrl", "-")
        elif event.gesture is Gesture.PAGE_FORWARD:
            self._send_hotkey("alt", "right")
        elif event.gesture is Gesture.PAGE_BACK:
            self._send_hotkey("ctrl", "z")
        elif event.gesture is Gesture.UNDO:
            self._send_hotkey("ctrl", "z")
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
        elif event.gesture is Gesture.VIRTUAL_KEYBOARD:
            self._open_virtual_keyboard()

    def _send_key_down(self, key: str) -> None:
        if self._pyautogui is not None and hasattr(self._pyautogui, "keyDown"):
            self._pyautogui.keyDown(key)

    def _send_key_up(self, key: str) -> None:
        if self._pyautogui is not None and hasattr(self._pyautogui, "keyUp"):
            self._pyautogui.keyUp(key)

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
        else:
            try:
                import subprocess
                subprocess.Popen(
                    ["/home/will/.local/bin/aether-voice-toggle"],
                    start_new_session=True,
                )
            except OSError as err:
                logger.error("Não foi possível iniciar o ditado: %s", err)

    def _open_virtual_keyboard(self) -> None:
        """Abre um teclado virtual disponível no sistema hospedeiro."""
        command = next(
            (
                shutil.which(name)
                for name in ("wvkbd-mobintl", "wvkbd", "onboard")
                if shutil.which(name)
            ),
            None,
        )
        if command is None:
            logger.warning("Nenhum teclado virtual Wayland encontrado")
            return
        self.hyprland.ensure_camera_unfocused()
        subprocess.Popen([command], start_new_session=True)

    def release(self) -> None:
        if self.enabled and self._pyautogui:
            if self._dragging:
                self._pyautogui.mouseUp()
                self._send_key_up("super")
        self._dragging = False
        self._last_cursor = None

    def _move_cursor_relative(self, event: GestureEvent) -> None:
        """Move o ponteiro pela variação do dedo, como um trackpad virtual."""
        assert self._pyautogui is not None
        current = (event.cursor.x, event.cursor.y)
        previous = self._last_cursor
        self._last_cursor = current
        if previous is None:
            return

        dx = current[0] - previous[0]
        dy = current[1] - previous[1]
        if abs(dx) < CURSOR_DEADZONE and abs(dy) < CURSOR_DEADZONE:
            return

        width, height = self._pyautogui.size()
        if self._screen_cursor is None:
            try:
                screen_x, screen_y = self._pyautogui.position()
            except (AttributeError, OSError):
                # Fakes e backends sem leitura de posição começam no centro.
                screen_x, screen_y = width // 2, height // 2
        else:
            screen_x, screen_y = self._screen_cursor

        target_x = max(0, min(width - 1, int(screen_x + dx * width * CURSOR_SENSITIVITY)))
        target_y = max(0, min(height - 1, int(screen_y + dy * height * CURSOR_SENSITIVITY)))
        self._pyautogui.moveTo(target_x, target_y, duration=0)
        self._screen_cursor = (target_x, target_y)
