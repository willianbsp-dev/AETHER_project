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


def test_detects_scroll_with_only_index_extended() -> None:
    recognizer = HandGestureRecognizer()
    # Mover o indicador para cima ao longo de frames
    detected = False
    for i in range(5):
        y_pos = 0.45 - (i * 0.03)
        hand = create_hand(
            index=(0.45, y_pos),
            index_pip=(0.45, y_pos + 0.15),
            index_mcp=(0.45, y_pos + 0.28),
            **folded_other_fingers(),
        )
        ev = recognizer.update(hand, now=1.0 + i * 0.05)
        if ev.gesture is Gesture.SCROLL:
            detected = True
            assert ev.amount > 0  # Movimento para cima -> scroll positivo
            break

    assert detected


def test_detects_dwell_click() -> None:
    recognizer = HandGestureRecognizer()
    hand_pos = create_hand(index=(0.45, 0.35), **folded_other_fingers())

    # Quadro inicial
    recognizer.update(hand_pos, now=1.0)
    # 0.25s depois (progresso em ~50%)
    ev_mid = recognizer.update(hand_pos, now=1.25)
    assert ev_mid.gesture is Gesture.NONE
    assert 0.4 <= ev_mid.dwell_progress <= 0.6

    # 0.55s depois (deve disparar DWELL_CLICK)
    ev_click = recognizer.update(hand_pos, now=1.55)
    assert ev_click.gesture is Gesture.DWELL_CLICK


def test_detects_thumbs_up_voice_activate() -> None:
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
    assert event.gesture is Gesture.VOICE_ACTIVATE


def test_detects_ok_sign_confirm() -> None:
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
    assert event.gesture is Gesture.CONFIRM


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
    assert ev.gesture is Gesture.CONFIRM


def test_circle_in_hand_recognizer_triggers_page_forward() -> None:
    recognizer = HandGestureRecognizer()
    center_x, center_y = 0.5, 0.3
    radius = 0.08
    steps = 20

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
            **folded_other_fingers(),
        )
        ev = recognizer.update(hand, now=1.0 + i * 0.04)
        if ev.gesture is Gesture.PAGE_FORWARD:
            detected = True
            break

    assert detected


def test_detects_zoom_in_and_out() -> None:
    recognizer = HandGestureRecognizer()
    # Posição inicial de pinça
    h1 = create_hand(thumb=(0.45, 0.45), index=(0.50, 0.45), **folded_other_fingers())
    recognizer.update(h1, now=1.0)

    # Afastar polegar do indicador para Zoom In
    detected_in = False
    for i in range(5):
        h = create_hand(thumb=(0.45 - i * 0.02, 0.45), index=(0.50 + i * 0.02, 0.45), **folded_other_fingers())
        ev = recognizer.update(h, now=1.05 + i * 0.05)
        if ev.gesture is Gesture.ZOOM_IN:
            detected_in = True
            break

    assert detected_in

    # Reset
    recognizer.update([], now=1.5)

    # Inicia aberto e aproxima para Zoom Out
    h_start = create_hand(thumb=(0.38, 0.45), index=(0.58, 0.45), **folded_other_fingers())
    recognizer.update(h_start, now=2.0)

    detected_out = False
    for i in range(5):
        h = create_hand(thumb=(0.38 + i * 0.02, 0.45), index=(0.58 - i * 0.02, 0.45), **folded_other_fingers())
        ev = recognizer.update(h, now=2.05 + i * 0.05)
        if ev.gesture is Gesture.ZOOM_OUT:
            detected_out = True
            break

    assert detected_out
