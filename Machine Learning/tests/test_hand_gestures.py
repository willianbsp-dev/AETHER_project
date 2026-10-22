import math

from dataclasses import dataclass



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

    return [Landmark(p.x + dx, p.y + dy, p.z) for p in hand]





def folded_other_fingers() -> dict:

    return {

        "middle": (0.5, 0.7),

        "middle_pip": (0.5, 0.55),

        "ring": (0.55, 0.7),

        "ring_pip": (0.55, 0.55),

        "pinky": (0.6, 0.7),

        "pinky_pip": (0.6, 0.55),

    }





def calibrate(recognizer: HandGestureRecognizer, hands, start: float = 0.0) -> float:

    """Conclui a calibração usando uma pose neutra, sem ativar o gesto testado."""

    if isinstance(hands, list):

        neutral_hands = [

            create_hand(wrist=(0.35, 0.80)),

            create_hand(wrist=(0.65, 0.80)),

        ][: len(hands)]

    else:

        neutral_hands = create_hand()



    for i in range(21):

        now = start + i * 0.11

        event = recognizer.update(neutral_hands, now=now)

        assert event.gesture is Gesture.NONE

    assert recognizer.calibrated

    return start + 21 * 0.11





def test_closed_fist_does_not_minimize() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        thumb=(0.48, 0.55),

        index=(0.45, 0.65),

        index_pip=(0.45, 0.55),

        middle=(0.5, 0.65),

        middle_pip=(0.5, 0.55),

        ring=(0.55, 0.65),

        ring_pip=(0.55, 0.55),

        pinky=(0.6, 0.68),

        pinky_pip=(0.6, 0.58),

    )

    now = calibrate(recognizer, hand)



    for i in range(8):

        event = recognizer.update(

            offset_hand(hand, 0.0, i * 0.035),

            now=now + i * 0.05,

        )

        assert event.gesture is not Gesture.MINIMIZE





def test_open_palm_down_does_not_minimize() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        wrist=(0.5, 0.5),

        thumb=(0.3, 0.3),

        index=(0.45, 0.2),

        middle=(0.5, 0.18),

        ring=(0.55, 0.2),

        pinky=(0.6, 0.25),

    )

    now = calibrate(recognizer, hand)



    for i in range(8):

        event = recognizer.update(

            offset_hand(hand, 0.0, i * 0.035),

            now=now + i * 0.05,

        )

        assert event.gesture is not Gesture.MINIMIZE





def test_detects_scroll_with_only_index_extended() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        index=(0.45, 0.42),

        index_pip=(0.45, 0.57),

        index_mcp=(0.45, 0.70),

        **folded_other_fingers(),

    )

    now = calibrate(recognizer, hand)



    detected = False

    for i in range(12):

        current = offset_hand(hand, 0.0, -i * 0.04)

        event = recognizer.update(current, now=now + i * 0.06)

        if event.gesture is Gesture.SCROLL:

            detected = True

            assert event.amount > 0

            break



    assert detected





def test_scroll_return_movement_does_not_trigger_second_scroll() -> None:
    recognizer = HandGestureRecognizer()
    hand = create_hand(
        index=(0.45, 0.42),
        index_pip=(0.45, 0.57),
        index_mcp=(0.45, 0.70),
        **folded_other_fingers(),
    )
    now = calibrate(recognizer, hand)

    scroll_detected = False
    last_position = 0.0
    frame = 0

    for i in range(12):
        last_position = -i * 0.04
        event = recognizer.update(
            offset_hand(hand, 0.0, last_position),
            now=now + frame * 0.06,
        )
        frame += 1
        if event.gesture is Gesture.SCROLL:
            scroll_detected = True
            break

    assert scroll_detected

    for i in range(1, 13):
        current = offset_hand(hand, 0.0, last_position + i * 0.04)
        event = recognizer.update(current, now=now + frame * 0.06)
        frame += 1
        assert event.gesture is not Gesture.SCROLL


def test_detects_dwell_click_with_index_only() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        index=(0.45, 0.35),

        index_pip=(0.45, 0.52),

        index_mcp=(0.45, 0.65),

        **folded_other_fingers(),

    )

    now = calibrate(recognizer, hand)



    recognizer.update(hand, now=now)

    ev_mid = recognizer.update(hand, now=now + 0.25)

    assert ev_mid.gesture is Gesture.NONE

    assert 0.4 <= ev_mid.dwell_progress <= 0.6



    ev_click = recognizer.update(hand, now=now + 0.55)

    assert ev_click.gesture is Gesture.DWELL_CLICK





def test_detects_thumbs_up_confirm() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        thumb=(0.35, 0.30),

        thumb_mcp=(0.35, 0.60),

        index=(0.45, 0.70),

        index_pip=(0.45, 0.55),

        **folded_other_fingers(),

    )

    now = calibrate(recognizer, hand)



    detected = False

    for i in range(4):

        event = recognizer.update(hand, now=now + i * 0.05)

        if event.gesture is Gesture.CONFIRM:

            detected = True

            break

    assert detected





def test_detects_pinch_with_all_other_fingers_extended() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        thumb=(0.49, 0.45),

        index=(0.50, 0.45),

        middle=(0.50, 0.25),

        ring=(0.55, 0.25),

        pinky=(0.60, 0.30),

    )

    now = calibrate(recognizer, hand)



    event = recognizer.update(hand, now=now)

    assert event.gesture is Gesture.PINCH





def test_detects_ok_sign_as_voice_activation() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        thumb=(0.49, 0.56),

        index=(0.50, 0.57),

        index_pip=(0.46, 0.50),

        index_mcp=(0.45, 0.65),

        middle=(0.50, 0.25),

        ring=(0.55, 0.25),

        pinky=(0.60, 0.30),

    )

    now = calibrate(recognizer, hand)



    detected = False

    for i in range(4):

        event = recognizer.update(hand, now=now + i * 0.05)

        if event.gesture is Gesture.VOICE_ACTIVATE:

            detected = True

            break

    assert detected





def test_detects_open_palm_swipe_left_and_right() -> None:

    base = create_hand(

        wrist=(0.5, 0.5),

        thumb=(0.3, 0.3),

        index=(0.45, 0.2),

        middle=(0.5, 0.18),

        ring=(0.55, 0.2),

        pinky=(0.6, 0.25),

    )



    left_recognizer = HandGestureRecognizer()

    now = calibrate(left_recognizer, base)

    detected_left = False

    for i in range(10):

        event = left_recognizer.update(

            offset_hand(base, -i * 0.025, 0.0),

            now=now + i * 0.04,

        )

        if event.gesture is Gesture.SWIPE_LEFT:

            detected_left = True

            break

    assert detected_left



    right_recognizer = HandGestureRecognizer()

    now = calibrate(right_recognizer, base)

    detected_right = False

    for i in range(10):

        event = right_recognizer.update(

            offset_hand(base, i * 0.025, 0.0),

            now=now + i * 0.04,

        )

        if event.gesture is Gesture.SWIPE_RIGHT:

            detected_right = True

            break

    assert detected_right





def test_detects_multiple_consecutive_swipes_with_same_hand() -> None:

    recognizer = HandGestureRecognizer()

    base = create_hand(

        wrist=(0.5, 0.5),

        thumb=(0.3, 0.3),

        index=(0.45, 0.2),

        middle=(0.5, 0.18),

        ring=(0.55, 0.2),

        pinky=(0.6, 0.25),

    )

    now = calibrate(recognizer, base)



    detected = []

    frame = 0



    # Primeiro movimento para a esquerda.

    for i in range(10):

        event = recognizer.update(

            offset_hand(base, -i * 0.025, 0.0),

            now=now + frame * 0.04,

        )

        frame += 1

        if event.gesture is Gesture.SWIPE_LEFT:

            detected.append(event.gesture)

            break



    # Espera o cooldown e volta para o centro.

    for _ in range(8):

        recognizer.update(base, now=now + frame * 0.04)

        frame += 1



    # Segundo movimento para a esquerda.

    for i in range(10):

        event = recognizer.update(

            offset_hand(base, -i * 0.025, 0.0),

            now=now + frame * 0.04,

        )

        frame += 1

        if event.gesture is Gesture.SWIPE_LEFT:

            detected.append(event.gesture)

            break



    assert detected.count(Gesture.SWIPE_LEFT) == 2





def test_detects_two_hand_maximize_and_minimize() -> None:

    # Maximizar: começa fechado, sobe e abre.

    max_recognizer = HandGestureRecognizer()

    left = create_hand(wrist=(0.45, 0.55))

    right = create_hand(wrist=(0.55, 0.55))

    now = calibrate(max_recognizer, [left, right])



    detected_max = False

    for i in range(6):

        hand1 = offset_hand(left, -i * 0.03, -i * 0.025)

        hand2 = offset_hand(right, i * 0.03, -i * 0.025)

        event = max_recognizer.update(

            [hand1, hand2],

            now=now + i * 0.08,

        )

        if event.gesture is Gesture.MAXIMIZE:

            detected_max = True

            break

    assert detected_max



    # Minimizar: exatamente o inverso — começa aberto, desce e fecha.

    min_recognizer = HandGestureRecognizer()

    left = create_hand(wrist=(0.30, 0.45))

    right = create_hand(wrist=(0.70, 0.45))

    now = calibrate(min_recognizer, [left, right])



    detected_min = False

    for i in range(6):

        hand1 = offset_hand(left, i * 0.04, i * 0.025)

        hand2 = offset_hand(right, -i * 0.04, i * 0.025)

        event = min_recognizer.update(

            [hand1, hand2],

            now=now + i * 0.08,

        )

        if event.gesture is Gesture.MINIMIZE:

            detected_min = True

            break

    assert detected_min





def test_two_hands_stationary_do_not_fallback_to_confirm() -> None:

    recognizer = HandGestureRecognizer()

    hand1 = create_hand(

        thumb=(0.49, 0.56),

        index=(0.50, 0.57),

        index_pip=(0.46, 0.50),

        middle=(0.50, 0.25),

        ring=(0.55, 0.25),

        pinky=(0.60, 0.30),

    )

    hand2 = create_hand(wrist=(0.80, 0.60))

    now = calibrate(recognizer, [hand1, hand2])



    event = recognizer.update([hand1, hand2], now=now)

    assert event.gesture is not Gesture.CONFIRM





def test_circle_in_hand_recognizer_triggers_page_forward() -> None:

    recognizer = HandGestureRecognizer()

    center_x, center_y = 0.50, 0.35

    radius = 0.10

    steps = 32



    initial = create_hand(

        wrist=(0.5, 0.8),

        index_mcp=(0.45, 0.65),

        index_pip=(0.45, 0.50),

        index=(center_x + radius, center_y),

        **folded_other_fingers(),

    )

    now = calibrate(recognizer, initial)



    detected = False

    for i in range(steps):

        t = i / steps * 2 * math.pi

        x = center_x + radius * math.cos(t)

        y = center_y + radius * math.sin(t)

        hand = create_hand(

            wrist=(0.5, 0.8),

            index_mcp=(0.45, 0.65),

            index_pip=(0.45 + (x - center_x) * 0.4, 0.50 + (y - center_y) * 0.4),

            index=(x, y),

            **folded_other_fingers(),

        )

        event = recognizer.update(hand, now=now + i * 0.035)

        if event.gesture is Gesture.PAGE_FORWARD:

            detected = True

            break



    assert detected





def test_fist_does_not_trigger_pinch() -> None:

    recognizer = HandGestureRecognizer()

    hand = create_hand(

        thumb=(0.48, 0.55),

        index=(0.45, 0.65),

        index_pip=(0.45, 0.55),

        middle=(0.5, 0.65),

        middle_pip=(0.5, 0.55),

        ring=(0.55, 0.65),

        ring_pip=(0.55, 0.55),

        pinky=(0.6, 0.68),

        pinky_pip=(0.6, 0.58),

    )

    now = calibrate(recognizer, hand)



    for i in range(3):

        event = recognizer.update(hand, now=now + i * 0.05)

        assert event.gesture is not Gesture.PINCH





def _pinch_hand(wrist: tuple[float, float]) -> list[Landmark]:

    return create_hand(

        wrist=wrist,

        thumb=(wrist[0] - 0.01, wrist[1] - 0.05),

        index=(wrist[0], wrist[1] - 0.05),

        middle=(wrist[0], wrist[1] - 0.25),

        ring=(wrist[0] + 0.05, wrist[1] - 0.25),

        pinky=(wrist[0] + 0.10, wrist[1] - 0.20),

    )





def test_detects_zoom_with_one_open_hand_and_one_pinch_hand() -> None:

    recognizer = HandGestureRecognizer()

    open_hand = create_hand(wrist=(0.70, 0.55))

    pinch = _pinch_hand((0.30, 0.55))

    now = calibrate(recognizer, [pinch, open_hand])



    detected_in = False

    for i in range(5):

        current = _pinch_hand((0.30, 0.55 - i * 0.02))

        event = recognizer.update(

            [current, open_hand],

            now=now + i * 0.08,

        )

        if event.gesture is Gesture.ZOOM_IN:

            detected_in = True

            break

    assert detected_in



    recognizer = HandGestureRecognizer()

    pinch = _pinch_hand((0.30, 0.45))

    open_hand = create_hand(wrist=(0.70, 0.45))

    now = calibrate(recognizer, [pinch, open_hand])



    detected_out = False

    for i in range(5):

        current = _pinch_hand((0.30, 0.45 + i * 0.02))

        event = recognizer.update(

            [current, open_hand],

            now=now + i * 0.08,

        )

        if event.gesture is Gesture.ZOOM_OUT:

            detected_out = True

            break

    assert detected_out


def test_paused_update_never_returns_none() -> None:
    recognizer = HandGestureRecognizer()
    hand = create_hand()
    now = calibrate(recognizer, hand)
    recognizer._paused = True

    event = recognizer.update(hand, now=now + 0.1)

    assert event is not None
    assert event.gesture is Gesture.NONE


def _pause_fist_v3(wrist_y: float = 0.80) -> list[Landmark]:
    dy = wrist_y - 0.80
    return create_hand(
        wrist=(0.50, 0.80 + dy),
        thumb=(0.48, 0.67 + dy),
        index=(0.45, 0.65 + dy),
        index_pip=(0.45, 0.58 + dy),
        index_mcp=(0.45, 0.65 + dy),
        middle=(0.50, 0.64 + dy),
        middle_pip=(0.50, 0.57 + dy),
        middle_mcp=(0.50, 0.65 + dy),
        ring=(0.55, 0.65 + dy),
        ring_pip=(0.55, 0.58 + dy),
        ring_mcp=(0.55, 0.65 + dy),
        pinky=(0.60, 0.67 + dy),
        pinky_pip=(0.60, 0.60 + dy),
        pinky_mcp=(0.60, 0.68 + dy),
    )


def test_pause_requires_compact_stationary_fist() -> None:
    recognizer = HandGestureRecognizer()
    now = calibrate(recognizer, create_hand())
    fist = _pause_fist_v3()

    recognizer.update(fist, now=now + 0.05)
    event = recognizer.update(fist, now=now + 1.00)
    assert event.gesture is Gesture.PAUSE_TOGGLE
    assert recognizer.paused


def test_lowering_hand_does_not_pause() -> None:
    recognizer = HandGestureRecognizer()
    now = calibrate(recognizer, create_hand())

    seen_pause = False
    for i in range(12):
        # Um punho que continua descendo: a intenção de pausa deve ser cancelada/reiniciada.
        hand = offset_hand(_pause_fist_v3(), 0.0, min(0.14, i * 0.018))
        event = recognizer.update(hand, now=now + 0.05 + i * 0.10)
        if event.gesture is Gesture.PAUSE_TOGGLE:
            seen_pause = True
            break
    assert not seen_pause
    assert not recognizer.paused


def test_pinch_hysteresis_keeps_drag_until_release_distance() -> None:
    recognizer = HandGestureRecognizer()
    base = create_hand(thumb=(0.48, 0.45), index=(0.50, 0.45))
    now = calibrate(recognizer, base)

    event = recognizer.update(base, now=now + 0.01)
    assert event.gesture is Gesture.PINCH

    # Entre start e release: deve continuar arrastando.
    middle_distance = create_hand(thumb=(0.42, 0.45), index=(0.50, 0.45))
    event = recognizer.update(middle_distance, now=now + 0.06)
    assert event.gesture is Gesture.PINCH

    released = create_hand(thumb=(0.36, 0.45), index=(0.50, 0.45))
    event = recognizer.update(released, now=now + 0.12)
    assert event.gesture is not Gesture.PINCH


def _typing_hand() -> list[Landmark]:
    return create_hand(
        thumb=(0.35, 0.60),
        index=(0.45, 0.55),
        index_pip=(0.45, 0.55),
        middle=(0.50, 0.54),
        middle_pip=(0.50, 0.54),
        ring=(0.55, 0.55),
        ring_pip=(0.55, 0.55),
        pinky=(0.60, 0.58),
        pinky_pip=(0.60, 0.58),
    )


def test_keyboard_pose_is_two_hands_simulating_typing() -> None:
    recognizer = HandGestureRecognizer()
    left = offset_hand(_typing_hand(), -0.16, 0.0)
    right = offset_hand(_typing_hand(), 0.16, 0.0)
    now = calibrate(recognizer, [left, right])

    detected = False
    for i in range(10):
        event = recognizer.update([left, right], now=now + 0.05 + i * 0.10)
        if event.gesture is Gesture.KEYBOARD_TOGGLE:
            detected = True
            break
    assert detected
