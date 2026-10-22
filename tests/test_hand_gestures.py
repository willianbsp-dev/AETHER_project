import math
from dataclasses import dataclass
import pytest

from machine_feira.hand_gestures import (
    HandGestureRecognizer,
    INDEX_MCP,
    INDEX_PIP,
    INDEX_TIP,
    MIDDLE_MCP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_MCP,
    PINKY_PIP,
    PINKY_TIP,
    RING_MCP,
    RING_PIP,
    RING_TIP,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
)
from machine_feira.types import Gesture


@dataclass
class Landmark:
    x: float
    y: float
    z: float = 0.0


def create_hand(
    wrist: tuple[float, float] = (0.5, 0.8),
    thumb: tuple[float, float] = (0.35, 0.6),
    thumb_mcp: tuple[float, float] = (0.4, 0.7),
    index: tuple[float, float] = (0.45, 0.3),
    index_pip: tuple[float, float] = (0.45, 0.5),
    index_mcp: tuple[float, float] = (0.45, 0.65),
    middle: tuple[float, float] = (0.5, 0.28),
    middle_pip: tuple[float, float] = (0.5, 0.48),
    middle_mcp: tuple[float, float] = (0.5, 0.65),
    ring: tuple[float, float] = (0.55, 0.3),
    ring_pip: tuple[float, float] = (0.55, 0.5),
    ring_mcp: tuple[float, float] = (0.55, 0.65),
    pinky: tuple[float, float] = (0.6, 0.35),
    pinky_pip: tuple[float, float] = (0.6, 0.52),
    pinky_mcp: tuple[float, float] = (0.6, 0.68),
) -> list[Landmark]:
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    points[WRIST] = Landmark(*wrist)
    points[THUMB_MCP] = Landmark(*thumb_mcp)
    points[THUMB_TIP] = Landmark(*thumb)
    points[INDEX_MCP] = Landmark(*index_mcp)
    points[INDEX_PIP] = Landmark(*index_pip)
    points[INDEX_TIP] = Landmark(*index)
    points[MIDDLE_MCP] = Landmark(*middle_mcp)
    points[MIDDLE_PIP] = Landmark(*middle_pip)
    points[MIDDLE_TIP] = Landmark(*middle)
    points[RING_MCP] = Landmark(*ring_mcp)
    points[RING_PIP] = Landmark(*ring_pip)
    points[RING_TIP] = Landmark(*ring)
    points[PINKY_MCP] = Landmark(*pinky_mcp)
    points[PINKY_PIP] = Landmark(*pinky_pip)
    points[PINKY_TIP] = Landmark(*pinky)
    return points


def offset_hand(hand: list[Landmark], dx: float, dy: float) -> list[Landmark]:
    """Desloca todos os landmarks da mão por (dx, dy)."""
    return [Landmark(x=p.x + dx, y=p.y + dy, z=p.z) for p in hand]


def folded_other_fingers() -> dict:
    """Retorna posições dobradas para dedos médio, anelar e mínimo."""
    return {
        "middle": (0.5, 0.7),
        "middle_pip": (0.5, 0.55),
        "ring": (0.55, 0.7),
        "ring_pip": (0.55, 0.55),
        "pinky": (0.6, 0.7),
        "pinky_pip": (0.6, 0.55),
    }


def folded_ring_and_pinky() -> dict:
    """Mantém indicador e médio levantados para o modo de comandos."""
    return {
        "ring": (0.55, 0.7),
        "ring_pip": (0.55, 0.55),
        "pinky": (0.6, 0.7),
        "pinky_pip": (0.6, 0.55),
    }


def test_detects_pinch() -> None:
    recognizer = HandGestureRecognizer()
    # Polegar e indicador muito próximos
    hand = create_hand(
        thumb=(0.49, 0.45),
        index=(0.50, 0.45),
        **folded_other_fingers(),
    )
    event = recognizer.update(hand, now=1.0)
    assert event.gesture is Gesture.PINCH


def test_rejects_incomplete_landmarks() -> None:
    recognizer = HandGestureRecognizer()
    assert recognizer.update([Landmark(0.5, 0.5)] * 20, now=1.0).gesture is Gesture.NONE


def test_detects_scroll_with_index_and_middle_extended() -> None:
    recognizer = HandGestureRecognizer()
    resting_hand = create_hand(index=(0.45, 0.45), **folded_ring_and_pinky())
    recognizer.update(resting_hand, now=0.0)
    recognizer.update(resting_hand, now=1.05)
    # Mover o indicador para cima ao longo de frames
    detected = False
    for i in range(5):
        y_pos = 0.45 - (i * 0.03)
        hand = create_hand(
            index=(0.45, y_pos),
            index_pip=(0.45, y_pos + 0.15),
            index_mcp=(0.45, y_pos + 0.28),
            **folded_ring_and_pinky(),
        )
        ev = recognizer.update(hand, now=1.10 + i * 0.05)
        if ev.gesture is Gesture.SCROLL:
            detected = True
            assert ev.amount > 0  # Movimento para cima -> scroll positivo
            break

    assert detected


def test_scroll_has_distinct_up_and_down_directions() -> None:
    recognizer = HandGestureRecognizer()
    resting_hand = create_hand(index=(0.45, 0.45), **folded_ring_and_pinky())
    recognizer.update(resting_hand, now=0.0)
    recognizer.update(resting_hand, now=0.1)

    amounts: list[int] = []
    for i, y_pos in enumerate((0.42, 0.39, 0.36, 0.33)):
        hand = create_hand(
            index=(0.45, y_pos),
            index_pip=(0.45, y_pos + 0.15),
            index_mcp=(0.45, y_pos + 0.28),
            **folded_ring_and_pinky(),
        )
        event = recognizer.update(hand, now=0.2 + i * 0.08)
        if event.gesture is Gesture.SCROLL:
            amounts.append(event.amount)

    for i, y_pos in enumerate((0.36, 0.39, 0.42, 0.45, 0.48)):
        hand = create_hand(
            index=(0.45, y_pos),
            index_pip=(0.45, y_pos + 0.15),
            index_mcp=(0.45, y_pos + 0.28),
            **folded_ring_and_pinky(),
        )
        event = recognizer.update(hand, now=1.0 + i * 0.08)
        if event.gesture is Gesture.SCROLL:
            amounts.append(event.amount)

    assert any(amount > 0 for amount in amounts)
    assert any(amount < 0 for amount in amounts)


def test_detects_dwell_click() -> None:
    recognizer = HandGestureRecognizer()
    hand_pos = create_hand(index=(0.45, 0.35), **folded_ring_and_pinky())

    # Dois dedos levantados entram imediatamente no modo de comandos.
    ev_mode = recognizer.update(hand_pos, now=1.0)
    assert ev_mode.gesture is Gesture.NONE
    assert ev_mode.dwell_progress == 0.0
    assert ev_mode.gesture_mode


def test_detects_air_click_in_mouse_mode() -> None:
    recognizer = HandGestureRecognizer()
    positions = (0.35, 0.48, 0.25)
    events = []
    for i, y_pos in enumerate(positions):
        hand = create_hand(
            index=(0.45, y_pos),
            index_pip=(0.45, y_pos + 0.15),
            index_mcp=(0.45, y_pos + 0.28),
            **folded_other_fingers(),
        )
        events.append(recognizer.update(hand, now=1.0 + i * 0.05))

    assert any(event.gesture is Gesture.DWELL_CLICK for event in events)
    assert all(not event.gesture_mode for event in events)
    click_event = next(event for event in events if event.gesture is Gesture.DWELL_CLICK)
    assert not click_event.cursor_enabled


def test_detects_thumbs_up_confirm() -> None:
    recognizer = HandGestureRecognizer()
    # Todos os 4 dedos dobrados, polegar apontando para cima por 2+ frames
    hand = create_hand(
        thumb=(0.35, 0.3),
        thumb_mcp=(0.35, 0.6),
        index=(0.45, 0.7),
        index_pip=(0.45, 0.55),
        **folded_other_fingers(),
    )
    recognizer.update(hand, now=1.0)
    event = recognizer.update(hand, now=1.05)
    assert event.gesture is Gesture.CONFIRM

    # Manter a mão levantada não pode repetir o Enter a cada cooldown.
    for i in range(3, 12):
        event = recognizer.update(hand, now=1.05 + i * 0.40)
        assert event.gesture is Gesture.NONE

    # Só rearma depois que o gesto é realmente solto.
    recognizer.update(create_hand(), now=6.0)
    recognizer.update(hand, now=6.1)
    event = recognizer.update(hand, now=6.2)
    assert event.gesture is Gesture.CONFIRM


def test_detects_ok_sign_voice_activate() -> None:
    recognizer = HandGestureRecognizer()
    # Polegar e indicador em pinça, outros dedos estendidos por 2+ frames
    hand = create_hand(
        thumb=(0.49, 0.45),
        index=(0.50, 0.45),
        middle=(0.5, 0.25),
        ring=(0.55, 0.25),
        pinky=(0.6, 0.30),
    )
    recognizer.update(hand, now=1.0)
    event = recognizer.update(hand, now=1.05)
    assert event.gesture is Gesture.VOICE_ACTIVATE


def test_detects_open_palm_minimize() -> None:
    recognizer = HandGestureRecognizer()
    base_hand = create_hand(
        wrist=(0.5, 0.5),
        thumb=(0.3, 0.3),
        index=(0.45, 0.2),
        middle=(0.5, 0.18),
        ring=(0.55, 0.2),
        pinky=(0.6, 0.25),
    )
    detected = False
    for i in range(6):
        hand = offset_hand(base_hand, dx=0.0, dy=i * 0.035)
        ev = recognizer.update(hand, now=1.0 + i * 0.05)
        if ev.gesture is Gesture.MINIMIZE:
            detected = True
            break

    assert detected


def test_detects_open_palm_swipe_left_and_right() -> None:
    recognizer = HandGestureRecognizer()
    base_hand = create_hand(
        wrist=(0.5, 0.5),
        thumb=(0.3, 0.3),
        index=(0.45, 0.2),
        middle=(0.5, 0.18),
        ring=(0.55, 0.2),
        pinky=(0.6, 0.25),
    )

    # Swipe para a esquerda
    detected_left = False
    for i in range(6):
        hand = offset_hand(base_hand, dx=-i * 0.035, dy=0.0)
        ev_left = recognizer.update(hand, now=1.0 + i * 0.05)
        if ev_left.gesture is Gesture.SWIPE_LEFT:
            detected_left = True
            break

    assert detected_left

    # Swipe para a direita após cooldown
    detected_right = False
    for i in range(6):
        hand = offset_hand(base_hand, dx=i * 0.035, dy=0.0)
        ev_right = recognizer.update(hand, now=2.0 + i * 0.05)
        if ev_right.gesture is Gesture.SWIPE_RIGHT:
            detected_right = True
            break

    assert detected_right


def test_detects_multiple_consecutive_swipes_with_same_hand() -> None:
    recognizer = HandGestureRecognizer()
    base_hand = create_hand(
        wrist=(0.4, 0.5),
        thumb=(0.2, 0.3),
        index=(0.35, 0.2),
        middle=(0.4, 0.18),
        ring=(0.45, 0.2),
        pinky=(0.5, 0.25),
    )

    # 1º Swipe para a direita
    first_detected = False
    for i in range(5):
        hand = offset_hand(base_hand, dx=i * 0.035, dy=0.0)
        ev = recognizer.update(hand, now=1.0 + i * 0.05)
        if ev.gesture is Gesture.SWIPE_RIGHT:
            first_detected = True
            break
    assert first_detected

    # 2º Swipe para a direita com a mesma mão após 0.45s
    second_detected = False
    for i in range(5):
        hand = offset_hand(base_hand, dx=i * 0.035, dy=0.0)
        ev = recognizer.update(hand, now=1.6 + i * 0.05)
        if ev.gesture is Gesture.SWIPE_RIGHT:
            second_detected = True
            break
    assert second_detected


def test_swipe_recoil_is_blocked() -> None:
    recognizer = HandGestureRecognizer()
    base_hand = create_hand(
        wrist=(0.4, 0.5),
        thumb=(0.2, 0.3),
        index=(0.35, 0.2),
        middle=(0.4, 0.18),
        ring=(0.45, 0.2),
        pinky=(0.5, 0.25),
    )

    # 1. Swipe para a direita
    for i in range(5):
        hand = offset_hand(base_hand, dx=i * 0.035, dy=0.0)
        recognizer.update(hand, now=1.0 + i * 0.05)

    # 2. Retorno imediato da mão para a esquerda (dentro de 0.8s) -> DEVE SER BLOQUEADO
    recoil_detected = False
    for i in range(5):
        hand = offset_hand(base_hand, dx=0.15 - (i * 0.035), dy=0.0)
        ev = recognizer.update(hand, now=1.3 + i * 0.05)
        if ev.gesture is Gesture.SWIPE_LEFT:
            recoil_detected = True
            break

    assert not recoil_detected


def test_detects_toggle_minimized_open_palm_up() -> None:
    recognizer = HandGestureRecognizer()
    base_hand = create_hand()
    detected = False
    for i in range(6):
        hand = offset_hand(base_hand, dx=0.0, dy=-i * 0.035)
        ev = recognizer.update(hand, now=1.0 + i * 0.05)
        if ev.gesture is Gesture.TOGGLE_MINIMIZED:
            detected = True
            break

    assert detected


def test_detects_two_hands_maximize_and_restore() -> None:
    recognizer = HandGestureRecognizer()

    # Duas mãos se afastando (MAXIMIZE)
    detected_max = False
    for i in range(6):
        hand1 = create_hand(wrist=(0.4 - i * 0.04, 0.6))
        hand2 = create_hand(wrist=(0.6 + i * 0.04, 0.6))
        ev_max = recognizer.update([hand1, hand2], now=1.0 + i * 0.06)
        if ev_max.gesture is Gesture.MAXIMIZE:
            detected_max = True
            break

    assert detected_max

    # Duas mãos se aproximando (RESTORE)
    detected_res = False
    for i in range(6):
        hand1 = create_hand(wrist=(0.2 + i * 0.04, 0.6))
        hand2 = create_hand(wrist=(0.8 - i * 0.04, 0.6))
        ev_res = recognizer.update([hand1, hand2], now=2.0 + i * 0.06)
        if ev_res.gesture is Gesture.RESTORE:
            detected_res = True
            break

    assert detected_res


def test_two_hands_stationary_falls_back_to_primary_hand() -> None:
    recognizer = HandGestureRecognizer()
    hand1 = create_hand(
        thumb=(0.49, 0.45),
        index=(0.50, 0.45),
        middle=(0.5, 0.25),
        ring=(0.55, 0.25),
        pinky=(0.6, 0.30),
    )
    hand2 = create_hand(wrist=(0.8, 0.6))

    recognizer.update([hand1, hand2], now=1.0)
    ev = recognizer.update([hand1, hand2], now=1.05)
    assert ev.gesture is Gesture.VOICE_ACTIVATE


def test_circle_in_hand_recognizer_triggers_page_forward() -> None:
    recognizer = HandGestureRecognizer()
    center_x, center_y = 0.5, 0.3
    radius = 0.08
    steps = 20

    # O círculo só é liberado após o indicador permanecer parado por 1 s.
    resting_hand = create_hand(index=(center_x, center_y), **folded_ring_and_pinky())
    recognizer.update(resting_hand, now=0.0)
    recognizer.update(resting_hand, now=1.05)

    detected = False
    for i in range(steps):
        t = i / steps * 2 * math.pi
        x = center_x + radius * math.cos(t)
        y = center_y + radius * math.sin(t)
        hand = create_hand(
            wrist=(0.5, 0.8),
            index_mcp=(0.45, 0.65),
            index_pip=(0.45 + (x - center_x) * 0.4, 0.5 + (y - center_y) * 0.4),
            index=(x, y),
            **folded_ring_and_pinky(),
        )
        ev = recognizer.update(hand, now=1.10 + i * 0.04)
        if ev.gesture is Gesture.PAGE_FORWARD:
            detected = True
            break

    assert detected


def test_detects_zoom_with_one_open_hand_and_one_dynamic_pinch() -> None:
    recognizer = HandGestureRecognizer()

    open_hand = create_hand(
        thumb=(0.25, 0.35),
        index=(0.35, 0.15),
        middle=(0.50, 0.12),
        ring=(0.62, 0.20),
        pinky=(0.70, 0.32),
    )

    # Mão em pinça começa mais fechada e se abre -> ZOOM_IN.
    detected_in = False
    for i in range(6):
        pinch_hand = create_hand(
            thumb=(0.42 - i * 0.012, 0.45),
            index=(0.46 + i * 0.012, 0.45),
            **folded_other_fingers(),
        )
        ev = recognizer.update([open_hand, pinch_hand], now=1.0 + i * 0.05)
        if ev.gesture is Gesture.ZOOM_IN:
            detected_in = True
            break

    assert detected_in

    recognizer.update([], now=1.5)

    # Mão em pinça começa mais aberta e fecha -> ZOOM_OUT.
    detected_out = False
    for i in range(6):
        pinch_hand = create_hand(
            thumb=(0.38 + i * 0.012, 0.45),
            index=(0.58 - i * 0.012, 0.45),
            **folded_other_fingers(),
        )
        ev = recognizer.update([open_hand, pinch_hand], now=2.0 + i * 0.05)
        if ev.gesture is Gesture.ZOOM_OUT:
            detected_out = True
            break

    assert detected_out

    # Uma única mão, mesmo fazendo a mesma abertura dinâmica da pinça, nunca deve gerar zoom.
    recognizer.update([], now=3.0)
    one_hand_events = []
    for i in range(6):
        hand = create_hand(
            thumb=(0.42 - i * 0.015, 0.45),
            index=(0.54 + i * 0.015, 0.45),
            **folded_other_fingers(),
        )
        one_hand_events.append(recognizer.update(hand, now=3.05 + i * 0.05).gesture)
    assert Gesture.ZOOM_IN not in one_hand_events
    assert Gesture.ZOOM_OUT not in one_hand_events


def test_closed_pinch_is_drag_not_zoom() -> None:
    recognizer = HandGestureRecognizer()
    hand = create_hand(
        thumb=(0.49, 0.45),
        index=(0.50, 0.45),
        **folded_other_fingers(),
    )
    events = [recognizer.update(hand, now=1.0 + i * 0.05).gesture for i in range(4)]
    assert Gesture.PINCH in events
    assert Gesture.ZOOM_IN not in events
    assert Gesture.ZOOM_OUT not in events
