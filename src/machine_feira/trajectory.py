"""Rastreamento de trajetória e detecção de gestos contínuos (círculos)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque

from .types import Gesture, Point


@dataclass(frozen=True)
class CircleConfig:
    min_radius: float = 0.025
    min_accumulated_angle: float = 3.8  # ~218 graus em radianos
    min_points: int = 8
    max_duration: float = 2.0
    min_duration: float = 0.20
    aspect_ratio_min: float = 0.25
    closure_threshold: float = 0.85


@dataclass
class _TimedPoint:
    x: float
    y: float
    time: float


class CircleTrajectoryRecognizer:
    """Detecta desenhos circulares no ar a partir da trajetória do dedo indicador."""

    def __init__(self, config: CircleConfig | None = None) -> None:
        self.config = config or CircleConfig()
        self._history: Deque[_TimedPoint] = deque(maxlen=80)

    def add_point(self, point: Point, timestamp: float) -> None:
        # Descarta pontos que excedam a janela de tempo máxima
        while self._history and (timestamp - self._history[0].time > self.config.max_duration):
            self._history.popleft()
        self._history.append(_TimedPoint(point.x, point.y, timestamp))

    def clear(self) -> None:
        self._history.clear()

    def get_trail(self) -> list[Point]:
        return [Point(p.x, p.y) for p in self._history]

    def evaluate(self, current_time: float) -> Gesture:
        """Avalia se a trajetória recente forma um círculo horário ou anti-horário."""
        if len(self._history) < self.config.min_points:
            return Gesture.NONE

        duration = current_time - self._history[0].time
        if duration < self.config.min_duration:
            return Gesture.NONE

        xs = [p.x for p in self._history]
        ys = [p.y for p in self._history]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y

        if width < self.config.min_radius or height < self.config.min_radius:
            return Gesture.NONE

        aspect = min(width, height) / max(1e-4, max(width, height))
        if aspect < self.config.aspect_ratio_min:
            return Gesture.NONE

        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        diameter = max(width, height)

        # Distância entre início e fim para verificar fechamento aproximado
        start = self._history[0]
        end = self._history[-1]
        closure_dist = math.hypot(end.x - start.x, end.y - start.y)
        if closure_dist > diameter * self.config.closure_threshold:
            return Gesture.NONE

        # Calcula o acúmulo de ângulos ao redor do centroide (cx, cy)
        total_angle = 0.0
        prev_angle: float | None = None

        for p in self._history:
            angle = math.atan2(p.y - cy, p.x - cx)
            if prev_angle is not None:
                diff = angle - prev_angle
                # Normaliza a diferença angular para [-pi, pi]
                while diff > math.pi:
                    diff -= 2 * math.pi
                while diff < -math.pi:
                    diff += 2 * math.pi
                total_angle += diff
            prev_angle = angle

        if total_angle >= self.config.min_accumulated_angle:
            self.clear()
            return Gesture.PAGE_FORWARD  # Horário -> Avançar
        elif total_angle <= -self.config.min_accumulated_angle:
            self.clear()
            return Gesture.PAGE_BACK     # Anti-horário -> Voltar

        return Gesture.NONE
