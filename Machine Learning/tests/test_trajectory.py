import math

from machine_feira.trajectory import CircleConfig, CircleTrajectoryRecognizer
from machine_feira.types import Gesture, Point


def test_detects_clockwise_circle() -> None:
    tracker = CircleTrajectoryRecognizer(CircleConfig(min_points=12, min_radius=0.03))
    center_x, center_y = 0.5, 0.5
    radius = 0.08

    # Gera trajetória em sentido horário (0 a 2*pi)
    total_steps = 20
    gesture = Gesture.NONE
    for i in range(total_steps):
        t = i / total_steps * 2 * math.pi
        x = center_x + radius * math.cos(t)
        y = center_y + radius * math.sin(t)
        now = 1.0 + (i * 0.04)
        tracker.add_point(Point(x, y), now)
        res = tracker.evaluate(now)
        if res != Gesture.NONE:
            gesture = res
            break

    assert gesture is Gesture.PAGE_FORWARD


def test_detects_counter_clockwise_circle() -> None:
    tracker = CircleTrajectoryRecognizer(CircleConfig(min_points=12, min_radius=0.03))
    center_x, center_y = 0.5, 0.5
    radius = 0.08

    # Gera trajetória em sentido anti-horário (0 a -2*pi)
    total_steps = 20
    gesture = Gesture.NONE
    for i in range(total_steps):
        t = -i / total_steps * 2 * math.pi
        x = center_x + radius * math.cos(t)
        y = center_y + radius * math.sin(t)
        now = 1.0 + (i * 0.04)
        tracker.add_point(Point(x, y), now)
        res = tracker.evaluate(now)
        if res != Gesture.NONE:
            gesture = res
            break

    assert gesture is Gesture.PAGE_BACK


def test_ignores_straight_line() -> None:
    tracker = CircleTrajectoryRecognizer(CircleConfig(min_points=12, min_radius=0.03))
    gesture = Gesture.NONE
    for i in range(20):
        now = 1.0 + (i * 0.04)
        tracker.add_point(Point(0.2 + i * 0.02, 0.5), now)
        res = tracker.evaluate(now)
        if res != Gesture.NONE:
            gesture = res

    assert gesture is Gesture.NONE

