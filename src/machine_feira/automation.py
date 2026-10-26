"""Camada de automação desktop. Integra PyAutoGUI e comandos Hyprland."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable
from .hyprland import HyprlandDispatcher
from .types import Gesture, GestureEvent

logger = logging.getLogger(__name__)


# A imagem da câmera é um touchpad absoluto. A escala completa permite chegar
# às bordas esquerda e superior, que ficavam inacessíveis com uma margem fixa.
CURSOR_MARGIN = 0.0
CURSOR_SMOOTHING = 0.22
CURSOR_SCREEN_SCALE = 1.0
CURSOR_TOLERANCE = 0.006
# A pinça iniciada nos 18% superiores da imagem representa a barra de título;
# em qualquer outra área ela funciona como arrasto normal de conteúdo.
WINDOW_DRAG_BAND = 0.18


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
        self._window_dragging = False
        self._pyautogui = None
        self._last_cursor: tuple[float, float] | None = None
        self._screen_cursor: tuple[int, int] | None = None
        self._smoothed_pointer: tuple[float, float] | None = None
        # PyAutoGUI fala X11. Em Wayland, ydotool é o backend real de entrada;
        # ele será usado quando o daemon tiver criado o socket do usuário.
        self._ydotool = shutil.which("ydotool")
        self._ydotool_socket = Path(
            os.environ.get("YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket")
        )
        self._virtual_keyboard_process: subprocess.Popen[bytes] | None = None
        self._pointer_process: subprocess.Popen[bytes] | None = None
        self._last_pointer_injection = 0.0
        self.hyprland = hyprland or HyprlandDispatcher()
        self.hyprland.remember_current_target()
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
        # O reconhecedor só marca cursor_enabled para o indicador isolado. O
        # A posição 2D do indicador é convertida diretamente para a tela. A
        # bolinha de dwell é apenas clique e nunca bloqueia este movimento.
        if event.cursor_enabled:
            self._move_cursor_absolute(event)
        elif event.gesture is Gesture.PINCH and self._dragging:
            # Durante o arrasto, a pinça também acompanha a posição absoluta.
            self._move_cursor_absolute(event)
        else:
            # O próximo gesto de indicador começa a partir da posição atual da
            # mão, sem uma interpolação longa desde o gesto anterior.
            self._smoothed_pointer = None

        # 2. Pinça: arrasto de conteúdo ou movimento de janela.
        if event.gesture is Gesture.PINCH:
            if not self._dragging:
                self.hyprland.ensure_camera_unfocused()
                # O mesmo gesto ganha dois significados pelo ponto inicial:
                # faixa superior = janela; restante = elemento/site.
                self._window_dragging = event.cursor.y <= WINDOW_DRAG_BAND
                if self._window_dragging:
                    self._send_key_down("super")
                # 0x40 = botão esquerdo pressionado. 0x41 seria o direito e
                # acionaria o resize do Hyprland com Super.
                if not self._ydotool_run("click", "0x40"):
                    self._pyautogui.mouseDown()
                self._dragging = True
        elif self._dragging:
            # 0x80 = liberação do botão esquerdo.
            if not self._ydotool_run("click", "0x80"):
                self._pyautogui.mouseUp()
            if self._window_dragging:
                self._send_key_up("super")
            self._dragging = False
            self._window_dragging = False

        # 3. Cliques e Interações no Desktop
        if event.gesture is Gesture.DWELL_CLICK:
            self.hyprland.ensure_camera_unfocused()
            if not self._ydotool_run("click", "0xC0"):
                self._pyautogui.click()
        elif event.gesture is Gesture.DOUBLE_CLICK:
            self.hyprland.ensure_camera_unfocused()
            if not self._ydotool_run("click", "0xC1"):
                self._pyautogui.click(button="right")
        elif event.gesture is Gesture.SCROLL:
            self.hyprland.ensure_camera_unfocused()
            # Passos pequenos e assíncronos deixam o scroll contínuo sem
            # bloquear a câmera esperando um processo externo.
            # O sinal positivo do gesto de subir deve permanecer positivo no
            # ydotool; antes ele era invertido e o scroll ficava ao contrário.
            # Usar -y evita que o valor -1 seja interpretado como uma opção
            # do ydotool em vez de ser aceito como direção de descida.
            if not self._ydotool_background(
                "mousemove", "--wheel", "-x", "0", "-y", str(event.amount)
            ):
                self._pyautogui.scroll(event.amount)
        elif event.gesture is Gesture.ZOOM_IN:
            self._send_hotkey("ctrl", "+")
        elif event.gesture is Gesture.ZOOM_OUT:
            self._send_hotkey("ctrl", "-")
        elif event.gesture is Gesture.PAGE_FORWARD:
            self._send_hotkey("alt", "right")
        elif event.gesture is Gesture.PAGE_BACK:
            self._send_hotkey("alt", "left")
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
        if self._ydotool_run("key", f"{_LINUX_KEY_CODES.get(key, '')}:1"):
            return
        if self._pyautogui is not None and hasattr(self._pyautogui, "keyDown"):
            self._pyautogui.keyDown(key)

    def _send_key_up(self, key: str) -> None:
        if self._ydotool_run("key", f"{_LINUX_KEY_CODES.get(key, '')}:0"):
            return
        if self._pyautogui is not None and hasattr(self._pyautogui, "keyUp"):
            self._pyautogui.keyUp(key)

    def _send_hotkey(self, *keys: str) -> None:
        if self._pyautogui is None or not keys:
            return
        # Ctrl+Z no terminal é SIGTSTP: ele suspende o próprio processo do
        # AETHER. Se nenhuma janela gráfica foi encontrada na inicialização,
        # falhamos com segurança em vez de travar a aplicação novamente.
        if keys == ("ctrl", "z") and hasattr(self.hyprland, "has_target_window"):
            if not self.hyprland.has_target_window():
                logger.warning("Ctrl+Z ignorado: nenhuma janela gráfica segura foi encontrada")
                return
        self.hyprland.ensure_camera_unfocused()
        if self._ydotool_send_hotkey(keys):
            return
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
        """Alterna o wvkbd: um gesto abre, o mesmo gesto fecha."""
        if self._virtual_keyboard_process is not None and self._virtual_keyboard_process.poll() is None:
            self._virtual_keyboard_process.terminate()
            self._virtual_keyboard_process = None
            return

        # Também recolhe instâncias abertas antes desta execução do programa;
        # assim o gesto nunca acumula duas barras do wvkbd na tela.
        existing = subprocess.run(
            ["pgrep", "-x", "wvkbd-mobintl"], capture_output=True, text=True, check=False
        )
        if existing.returncode == 0:
            for pid in existing.stdout.split():
                if pid.isdigit():
                    subprocess.run(["kill", "-TERM", pid], check=False)
            return

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
        self._virtual_keyboard_process = subprocess.Popen([command], start_new_session=True)

    def release(self) -> None:
        if self.enabled and self._pyautogui:
            if self._dragging:
                if not self._ydotool_run("click", "0x80"):
                    self._pyautogui.mouseUp()
                self._send_key_up("super")
        self._dragging = False
        self._window_dragging = False
        self._last_cursor = None

    def _move_cursor_absolute(self, event: GestureEvent) -> None:
        """Converte a posição normalizada da câmera em posição absoluta da tela."""
        assert self._pyautogui is not None
        width, height = self._pyautogui.size()
        normalized_x = max(0.0, min(1.0, (event.cursor.x - CURSOR_MARGIN) / (1 - 2 * CURSOR_MARGIN)))
        normalized_y = max(0.0, min(1.0, (event.cursor.y - CURSOR_MARGIN) / (1 - 2 * CURSOR_MARGIN)))
        current = (normalized_x, normalized_y)
        if self._smoothed_pointer is None:
            self._smoothed_pointer = current
        else:
            old_x, old_y = self._smoothed_pointer
            # Descarta apenas tremores mínimos, sem criar um atraso de reação.
            if abs(normalized_x - old_x) < CURSOR_TOLERANCE and abs(normalized_y - old_y) < CURSOR_TOLERANCE:
                return
            self._smoothed_pointer = (
                old_x + (normalized_x - old_x) * CURSOR_SMOOTHING,
                old_y + (normalized_y - old_y) * CURSOR_SMOOTHING,
            )
        smooth_x, smooth_y = self._smoothed_pointer
        # Usa apenas 85% da tela para que pequenos tremores da mão não
        # atravessem grandes distâncias no desktop.
        target_x = max(0, min(width - 1, int((0.5 + (smooth_x - 0.5) * CURSOR_SCREEN_SCALE) * (width - 1))))
        target_y = max(0, min(height - 1, int((0.5 + (smooth_y - 0.5) * CURSOR_SCREEN_SCALE) * (height - 1))))
        moved_wayland = self._ydotool_move_absolute(target_x, target_y)
        if not moved_wayland:
            self._pyautogui.moveTo(target_x, target_y, duration=0)
        self._screen_cursor = (target_x, target_y)

    def _ydotool_run(self, *args: str) -> bool:
        """Executa uma ação Wayland somente se o daemon estiver disponível."""
        if not self._ydotool or not self._ydotool_socket.exists():
            return False
        try:
            result = subprocess.run(
                [self._ydotool, *args],
                env={**os.environ, "YDOTOOL_SOCKET": str(self._ydotool_socket)},
                capture_output=True,
                check=False,
                timeout=0.08,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _ydotool_background(self, *args: str) -> bool:
        """Executa uma ação do ydotool em segundo plano, sem travar a câmera.

        O gesto do indicador chega dezenas de vezes por segundo. Esperar um
        processo `ydotool` terminar em cada quadro fazia a webcam parar e
        podia deixar a tecla Super presa. Movimentos são limitados a 60 Hz e
        executados em segundo plano; cliques e atalhos continuam síncronos.
        """
        # Backends fakeados dos testes expõem `moved_to`; neles precisamos
        # deixar o movimento passar pelo método PyAutoGUI simulado.
        if hasattr(self._pyautogui, "moved_to"):
            return False
        if not self._ydotool or not self._ydotool_socket.exists():
            return False
        now = time.monotonic()
        if now - self._last_pointer_injection < 1.0 / 60.0:
            return True
        if self._pointer_process is not None and self._pointer_process.poll() is None:
            return True
        if not self._ydotool or not self._ydotool_socket.exists():
            return False
        now = time.monotonic()
        if now - self._last_pointer_injection < 1.0 / 60.0:
            return True
        if self._pointer_process is not None and self._pointer_process.poll() is None:
            return True
        try:
            self._pointer_process = subprocess.Popen(
                [self._ydotool, *args],
                env={**os.environ, "YDOTOOL_SOCKET": str(self._ydotool_socket)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._last_pointer_injection = now
            return True
        except OSError:
            return False

    def _ydotool_move_absolute(self, x: int, y: int) -> bool:
        """Move o ponteiro para uma coordenada absoluta sem esperar o processo."""
        # Backends fakeados dos testes expõem `moved_to`.
        if hasattr(self._pyautogui, "moved_to"):
            return False
        return self._ydotool_background("mousemove", "--absolute", str(x), str(y))

    def _ydotool_send_hotkey(self, keys: tuple[str, ...]) -> bool:
        """Envia teclas pelo Wayland, incluindo o Ctrl+Z do círculo anti-horário."""
        pressed: list[str] = []
        for key in keys:
            normalized = key.lower()
            code = _LINUX_KEY_CODES.get(normalized)
            if code is None:
                return False
            # '+' é Shift + '=' no teclado Linux; os demais são pressionados
            # juntos e liberados na ordem inversa.
            if normalized == "+":
                pressed.extend(("42:1", "13:1"))
            else:
                pressed.append(f"{code}:1")
        released = [item.replace(":1", ":0") for item in reversed(pressed)]
        return self._ydotool_run("key", *(pressed + released))


# Códigos Linux usados apenas para manter Super pressionado durante a pinça.
# Os demais atalhos continuam usando o backend de teclado já configurado.
_LINUX_KEY_CODES = {
    "super": 125,
    "ctrl": 29,
    "alt": 56,
    "z": 44,
    "left": 105,
    "right": 106,
    "+": 13,
    "-": 12,
}
