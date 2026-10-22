"""Integração da automação do AETHER com o Windows."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess


logger = logging.getLogger(__name__)


def _pyautogui():
    import pyautogui
    return pyautogui


user32 = ctypes.windll.user32 if os.name == "nt" else None
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

    def virtual_desktop_count(self) -> int:
        if os.name != "nt":
            return 1
        try:
            import winreg
            path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops\Desktops"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return winreg.QueryInfoKey(key)[0]
        except (OSError, ImportError):
            # Em algumas versões do Windows a chave pode não estar disponível.
            return 1

    def ensure_extra_virtual_desktop(self) -> bool:
        if self.virtual_desktop_count() > 1:
            return True
        try:
            self.ensure_camera_unfocused()
            _pyautogui().hotkey("win", "ctrl", "d")
            return True
        except Exception:
            logger.exception("Não foi possível criar uma área de trabalho virtual.")
            return False

    def workspace_next(self) -> bool:
        if not self.ensure_extra_virtual_desktop():
            return False
        try:
            self.ensure_camera_unfocused()
            _pyautogui().hotkey("win", "ctrl", "right")
            return True
        except Exception:
            logger.exception("Não foi possível mudar para a próxima área de trabalho.")
            return False

    def workspace_prev(self) -> bool:
        if not self.ensure_extra_virtual_desktop():
            return False
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
