"""Integração com o compositor Hyprland (com suporte a sintaxe Lua e Legada)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class HyprlandDispatcher:
    """Encapsula as chamadas ao hyprctl com suporte a Lua (Hyprland >= 0.56) e modo legado."""

    def __init__(self, hyprctl_bin: str = "hyprctl") -> None:
        self.hyprctl_bin = hyprctl_bin
        self._available: bool | None = None

    def is_available(self) -> bool:
        if self._available is None:
            self._available = shutil.which(self.hyprctl_bin) is not None
        return self._available

    def dispatch_raw(self, *args: str) -> bool:
        """Executa 'hyprctl dispatch ...' diretamente."""
        if not self.is_available():
            return False

        full_cmd = [self.hyprctl_bin, "dispatch", *args]
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=0.5,
            )
            return result.returncode == 0 and "error:" not in result.stdout
        except Exception as err:
            logger.warning("Falha ao executar hyprctl %s: %s", full_cmd, err)
            return False

    def dispatch_lua_or_legacy(self, lua_cmd: str, legacy_cmd: str, *legacy_args: str) -> bool:
        """Tenta primeiro a sintaxe Lua moderna; se falhar, tenta o comando legado."""
        # 1. Tenta formato Lua moderno
        if self.dispatch_raw(lua_cmd):
            return True
        # 2. Fallback para formato legado
        return self.dispatch_raw(legacy_cmd, *legacy_args)

    def maximize(self) -> bool:
        """Maximiza a janela ativa preservando a barra do Waybar (fullscreen 1 / internal=1)."""
        active = self.get_active_window()
        if active and active.get("fullscreen", 0) == 1:
            return True  # Já está maximizada com waybar visível

        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.fullscreen_state({ internal = 1, client = 0 })",
            "fullscreen",
            "1",
        )

    def restore(self) -> bool:
        """Restaura a janela ativa para o tamanho normal de volta do modo maximizado."""
        active = self.get_active_window()
        if active is None or active.get("fullscreen", 0) != 0:
            # Sai do modo maximizado/fullscreen
            return self.dispatch_lua_or_legacy(
                "hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })",
                "fullscreen",
                "0",
            )

        # Se não estiver em fullscreen, alterna estado flutuante
        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.float({ action = 'toggle' })",
            "togglefloating",
        )

    def minimize(self) -> bool:
        """Move a janela para o workspace especial (scratchpad)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.move({ workspace = 'special:magic' })",
            "movetoworkspacesilent",
            "special:minimized",
        )

    def workspace_next(self) -> bool:
        """Avança para o próximo workspace."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.focus({ workspace = 'e+1' })",
            "workspace",
            "e+1",
        )

    def workspace_prev(self) -> bool:
        """Retorna para o workspace anterior."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.focus({ workspace = 'e-1' })",
            "workspace",
            "e-1",
        )

    def get_active_window(self) -> dict | None:
        """Retorna as propriedades da janela ativa atual em formato de dicionário."""
        if not self.is_available():
            return None
        try:
            result = subprocess.run(
                [self.hyprctl_bin, "-j", "activewindow"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def ensure_camera_unfocused(self, camera_title_keyword: str = "Machine Feira") -> None:
        """Se a janela ativa for a câmera do OpenCV, passa o foco para a próxima janela."""
        active = self.get_active_window()
        if active and camera_title_keyword.lower() in active.get("title", "").lower():
            self.dispatch_raw("hl.dsp.window.cycle_next()")
