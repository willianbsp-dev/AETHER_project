from unittest.mock import patch
import pytest

from machine_feira.hyprland import HyprlandDispatcher


def test_hyprland_minimize_moves_to_special_workspace():
    dispatcher = HyprlandDispatcher()
    with patch.object(dispatcher, "is_available", return_value=True), \
         patch.object(dispatcher, "dispatch_lua_or_legacy", return_value=True) as mock_dispatch:
        
        res = dispatcher.minimize()
        assert res is True
        mock_dispatch.assert_called_once_with(
            "hl.dsp.window.move({ workspace = 'special:minimized', follow = false })",
            "movetoworkspacesilent",
            "special:minimized",
        )


def test_hyprland_toggle_special_and_unminimize():
    dispatcher = HyprlandDispatcher()
    with patch.object(dispatcher, "is_available", return_value=True), \
         patch.object(dispatcher, "dispatch_lua_or_legacy", return_value=True) as mock_dispatch:
        
        assert dispatcher.toggle_special_minimized() is True
        assert dispatcher.unminimize_to_current() is True


def test_hyprland_restore_unminimizes_if_in_special():
    dispatcher = HyprlandDispatcher()
    with patch.object(dispatcher, "is_available", return_value=True), \
         patch.object(dispatcher, "get_active_window", return_value={"workspace": {"name": "special:minimized"}}), \
         patch.object(dispatcher, "is_special_workspace_open", return_value=True), \
         patch.object(dispatcher, "unminimize_to_current", return_value=True) as mock_unminimize, \
         patch.object(dispatcher, "toggle_special_minimized", return_value=True) as mock_toggle:
        
        res = dispatcher.restore()
        assert res is True
        mock_unminimize.assert_called_once()
        mock_toggle.assert_called_once()


def test_hyprland_restore_exits_fullscreen_if_fullscreen():
    dispatcher = HyprlandDispatcher()
    with patch.object(dispatcher, "is_available", return_value=True), \
         patch.object(dispatcher, "get_active_window", return_value={"fullscreen": 1, "workspace": {"name": "1"}}), \
         patch.object(dispatcher, "is_special_workspace_open", return_value=False), \
         patch.object(dispatcher, "dispatch_lua_or_legacy", return_value=True) as mock_dispatch:
        
        res = dispatcher.restore()
        assert res is True
        mock_dispatch.assert_called_once_with(
            "hl.dsp.window.fullscreen_state({ internal = 0, client = 0 })",
            "fullscreen",
            "0",
        )
