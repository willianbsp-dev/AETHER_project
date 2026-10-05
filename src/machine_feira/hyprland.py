"""Integração com o compositor Hyprland (Lua moderno e comandos legados)."""

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
            return result.returncode == 0 and "error:" not in result.stdout.lower()
        except Exception as err:
            logger.warning("Falha ao executar hyprctl %s: %s", full_cmd, err)
            return False

    def dispatch_lua_or_legacy(self, lua_cmd: str, legacy_cmd: str, *legacy_args: str) -> bool:
        """Tenta primeiro a sintaxe Lua moderna; se falhar, tenta o comando legado."""
        if self.dispatch_raw(lua_cmd):
            return True
        return self.dispatch_raw(legacy_cmd, *legacy_args)

    def maximize(self) -> bool:
        """Maximiza a janela ativa preservando a barra do Waybar (fullscreen interno)."""
        active = self.get_active_window()
        if active and active.get("fullscreen", 0) == 1:
            return True

        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.fullscreen_state({ internal = 1, client = 0, action = 'toggle' })",
            "fullscreen",
            "1",
        )

    def restore(self) -> bool:
        """Restaura a janela ativa:
        1. Se a gaveta 'special:minimized' estiver aberta ou a janela focada estiver nela -> Desminimiza para a área atual (Super + Alt + M / m+0).
        2. Se estiver em modo fullscreen -> Sai do modo fullscreen (fullscreen 0).
        3. Caso contrário -> Alterna modo flutuante (Super + V).
        """
        active = self.get_active_window()
        ws_name = ""
        if active and isinstance(active.get("workspace"), dict):
            ws_name = active["workspace"].get("name", "")

        # 1. Se estiver na gaveta special:minimized ou a gaveta estiver aberta
        if "minimized" in ws_name.lower() or self.is_special_workspace_open("minimized"):
            success = self.unminimize_to_current()
            if self.is_special_workspace_open("minimized"):
                self.toggle_special_minimized()
            return success

        # 2. Se estiver em fullscreen
        if active and active.get("fullscreen", 0) != 0:
            return self.dispatch_lua_or_legacy(
                "hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })",
                "fullscreen",
                "0",
            )

        # 3. Janela normal: alterna modo flutuante
        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.float({ action = 'toggle' })",
            "togglefloating",
        )

    def minimize(self) -> bool:
        """Adiciona a janela ativa ao workspace especial 'special:minimized' (Super + Shift + M)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.move({ workspace = 'special:minimized', follow = false })",
            "movetoworkspacesilent",
            "special:minimized",
        )

    def toggle_special_minimized(self) -> bool:
        """Alterna a exibição da gaveta de janelas minimizadas (Super + M)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.workspace.toggle_special('minimized')",
            "togglespecialworkspace",
            "minimized",
        )

    def unminimize_to_current(self) -> bool:
        """Tira a janela da gaveta especial e move para o workspace atual (Super + Alt + M / m+0)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.window.move({ workspace = 'm+0' })",
            "movetoworkspace",
            "m+0",
        )

    def workspace_next(self) -> bool:
        """Avança para o próximo workspace relativo (r+1)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.focus({ workspace = 'r+1' })",
            "workspace",
            "r+1",
        )

    def workspace_prev(self) -> bool:
        """Retorna para o workspace anterior relativo (r-1)."""
        return self.dispatch_lua_or_legacy(
            "hl.dsp.focus({ workspace = 'r-1' })",
            "workspace",
            "r-1",
        )

    def is_special_workspace_open(self, name: str = "minimized") -> bool:
        """Verifica se o workspace especial está visível em algum monitor ou focado."""
        if not self.is_available():
            return False
        try:
            # 1. Verifica no activeworkspace se a janela focada está no special
            act_res = subprocess.run(
                [self.hyprctl_bin, "-j", "activeworkspace"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.3,
            )
            if act_res.returncode == 0 and act_res.stdout.strip():
                act_ws = json.loads(act_res.stdout)
                if name.lower() in str(act_ws.get("name", "")).lower():
                    return True

            # 2. Verifica nos monitores se o specialWorkspace está ativo
            result = subprocess.run(
                [self.hyprctl_bin, "-j", "monitors"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.3,
            )
            if result.returncode == 0 and result.stdout.strip():
                monitors = json.loads(result.stdout)
                for mon in monitors:
                    special = mon.get("specialWorkspace", {})
                    spec_id = special.get("id", 0)
                    spec_name = str(special.get("name", "")).lower()
                    if spec_id != 0 and name.lower() in spec_name:
                        return True
        except Exception:
            pass
        return False

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
        """Garante que ações sejam enviadas para uma janela real, nunca à câmera."""
        active = self.get_active_window()
        if not active:
            return
        camera_keyword = camera_title_keyword.lower()
        active_text = " ".join(
            str(active.get(field, "")) for field in ("title", "class", "initialClass")
        ).lower()
        if camera_keyword not in active_text:
            return

        # O ciclo de foco pode voltar para a própria câmera. Primeiro procura
        # uma janela mapeada que não seja ela e foca pelo endereço Hyprland.
        try:
            result = subprocess.run(
                [self.hyprctl_bin, "-j", "clients"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.3,
            )
            clients = json.loads(result.stdout) if result.returncode == 0 else []
            for client in clients:
                client_text = " ".join(
                    str(client.get(field, "")) for field in ("title", "class", "initialClass")
                ).lower()
                address = client.get("address")
                if address and camera_keyword not in client_text and client.get("mapped", True):
                    if self.dispatch_raw("focuswindow", f"address:{address}"):
                        return
        except (OSError, ValueError, TypeError):
            pass

        if not self.dispatch_raw("hl.dsp.window.cycle_next()"):
            self.dispatch_raw("cyclenext")
