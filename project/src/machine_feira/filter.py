"""Filtros de suavização temporal para landmarks, cursor e distâncias."""

from __future__ import annotations

import math
from typing import Sequence
from .types import Point


class OneEuroFilter:
    """Filtro 1€ (One-Euro Filter) para cancelamento de ruído em tempo real com baixa latência.

    Em baixas velocidades (mão parada/apontando), aumenta a filtragem para eliminar
    tremores (jitter). Em altas velocidades (movimento rápido), reduz a filtragem para
    eliminar atraso (lag).
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    def filter(self, x: float, timestamp: float) -> float:
        if self._t_prev is None or self._x_prev is None:
            self._x_prev = x
            self._t_prev = timestamp
            self._dx_prev = 0.0
            return x

        dt = max(1e-4, timestamp - self._t_prev)
        self._t_prev = timestamp

        # Estima velocidade (derivada)
        dx = (x - self._x_prev) / dt
        edx = self._exponential_smoothing(dx, self._dx_prev, self._alpha(dt, self.d_cutoff))
        self._dx_prev = edx

        # Frequência de corte adaptativa
        cutoff = self.min_cutoff + self.beta * abs(edx)
        alpha = self._alpha(dt, cutoff)

        filtered = self._exponential_smoothing(x, self._x_prev, alpha)
        self._x_prev = filtered
        return filtered

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    @staticmethod
    def _exponential_smoothing(current: float, previous: float, alpha: float) -> float:
        return alpha * current + (1.0 - alpha) * previous


class PointFilter:
    """Filtra coordenadas 2D (x, y) de forma independente com OneEuroFilter."""

    def __init__(
        self,
        min_cutoff: float = 1.2,
        beta: float = 0.008,
        d_cutoff: float = 1.0,
    ) -> None:
        self.fx = OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self.fy = OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)

    def filter(self, point: Point, timestamp: float) -> Point:
        return Point(
            x=self.fx.filter(point.x, timestamp),
            y=self.fy.filter(point.y, timestamp),
            z=point.z,
        )

    def reset(self) -> None:
        self.fx.reset()
        self.fy.reset()

