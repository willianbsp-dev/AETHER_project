"""Integração da automação do AETHER com o Windows."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


def _pyautogui():
    import pyautogui
    return pyautogui


user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3


class WindowsDispatcher:
    """Controla janelas, teclado virtual e áreas de trabalho do Windows."""

    def __init__(self, camera_title_keyword: str = "Machine Feira") -> None:
        self.camera_title_keyword = camera_title_keyword

    def get_foreground_window(self) -> int:
        return int(user32.GetForegroundWindow()) if user32 is not None else 0

    def get_window_title(self, hwnd: int) -> str:
        if user32 is None or not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def is_available(self) -> bool:
        return user32 is not None

    def ensure_camera_unfocused(self) -> None:
        if user32 is None:
            return
        hwnd = self.get_foreground_window()
        title = self.get_window_title(hwnd)
        if self.camera_title_keyword.lower() in title.lower():
            try:
                _pyautogui().hotkey("alt", "tab")
                time.sleep(0.05)
            except Exception:
                logger.exception("Não foi possível retirar o foco da câmera.")

    def _active_window(self) -> int:
        self.ensure_camera_unfocused()
        return self.get_foreground_window()

    def maximize(self) -> bool:
        hwnd = self._active_window()
        if not hwnd or user32 is None:
            return False
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return True

    def restore(self) -> bool:
        hwnd = self._active_window()
        if not hwnd or user32 is None:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        return True

    def minimize(self) -> bool:
        hwnd = self._active_window()
        if not hwnd or user32 is None:
            return False
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return True

    def _session_id(self) -> int | None:
        if os.name != "nt" or kernel32 is None:
            return None
        try:
            session_id = ctypes.c_uint(0)
            process_id = kernel32.GetCurrentProcessId()
            if kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
                return int(session_id.value)
        except Exception:
            pass
        return None

    def _registry_paths(self) -> list[str]:
        paths = [r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"]
        session_id = self._session_id()
        if session_id is not None:
            paths.append(
                rf"Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo\{session_id}\VirtualDesktops"
            )
        return paths

    def _read_registry_binary(self, value_name: str) -> bytes | None:
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None

        for path in self._registry_paths():
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    value, value_type = winreg.QueryValueEx(key, value_name)
                    if value_type == winreg.REG_BINARY and isinstance(value, (bytes, bytearray)):
                        return bytes(value)
            except OSError:
                continue
        return None

    def virtual_desktop_ids(self) -> list[bytes]:
        raw = self._read_registry_binary("VirtualDesktopIDs")
        if not raw:
            return []
        return [raw[i : i + 16] for i in range(0, len(raw) - 15, 16)]

    def current_virtual_desktop_id(self) -> bytes | None:
        # Windows 11 normalmente guarda aqui; Windows 10 pode usar SessionInfo.
        paths = list(reversed(self._registry_paths()))
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None
        for path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    value, value_type = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
                    if value_type == winreg.REG_BINARY and isinstance(value, (bytes, bytearray)):
                        return bytes(value[:16])
            except OSError:
                continue
        ids = self.virtual_desktop_ids()
        return ids[0] if len(ids) == 1 else None

    def virtual_desktop_count(self) -> int:
        ids = self.virtual_desktop_ids()
        return max(1, len(ids))

    def current_virtual_desktop_index(self) -> int | None:
        ids = self.virtual_desktop_ids()
        current = self.current_virtual_desktop_id()
        if not ids or current is None:
            return None
        try:
            return ids.index(current)
        except ValueError:
            return None

    def create_virtual_desktop(self) -> bool:
        try:
            self.ensure_camera_unfocused()
            _pyautogui().hotkey("win", "ctrl", "d")
            return True
        except Exception:
            logger.exception("Não foi possível criar uma área de trabalho virtual.")
            return False

    def ensure_extra_virtual_desktop(self) -> bool:
        if self.virtual_desktop_count() > 1:
            return True
        return self.create_virtual_desktop()

    def workspace_next(self) -> bool:
        """Vai para a direita; se já estiver no último desktop, cria outro."""
        try:
            self.ensure_camera_unfocused()
            ids = self.virtual_desktop_ids()
            current = self.current_virtual_desktop_id()

            if ids and current in ids and ids.index(current) == len(ids) - 1:
                return self.create_virtual_desktop()

            if len(ids) <= 1 and current is None:
                return self.create_virtual_desktop()

            before = current
            _pyautogui().hotkey("win", "ctrl", "right")

            # Se o Windows não mudou de desktop, provavelmente estávamos no último.
            # O registro pode atualizar com pequeno atraso, então fazemos polling curto.
            if before is not None:
                for _ in range(10):
                    time.sleep(0.05)
                    after = self.current_virtual_desktop_id()
                    if after is not None and after != before:
                        return True
                return self.create_virtual_desktop()
            return True
        except Exception:
            logger.exception("Não foi possível mudar/criar a próxima área de trabalho.")
            return False

    def workspace_prev(self) -> bool:
        """Volta para a área anterior. Nunca cria desktop ao deslizar para a esquerda."""
        try:
            self.ensure_camera_unfocused()
            _pyautogui().hotkey("win", "ctrl", "left")
            return True
        except Exception:
            logger.exception("Não foi possível voltar para a área de trabalho anterior.")
            return False

    def toggle_virtual_keyboard(self) -> bool:
        """Abre/fecha o Teclado na Tela nativo do Windows."""
        try:
            self.ensure_camera_unfocused()
            _pyautogui().hotkey("win", "ctrl", "o")
            return True
        except Exception:
            try:
                subprocess.Popen(["osk.exe"], shell=False)
                return True
            except Exception:
                logger.exception("Não foi possível abrir o teclado virtual do Windows.")
                return False
