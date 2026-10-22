"""Tipos compartilhados entre reconhecimento e automação."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Gesture(Enum):
    NONE = auto()
    CLICK_LEFT = auto()       # 1 clique no modo normal
    CLICK_RIGHT = auto()      # 2 cliques no modo normal
    PINCH = auto()            # Arrastar
    MAXIMIZE = auto()         # 2 mãos: juntas -> para cima e para fora
    RESTORE = auto()          # Mantido por compatibilidade
    MINIMIZE = auto()         # 2 mãos: afastadas -> para baixo e para dentro
    SWIPE_LEFT = auto()       # Área de trabalho anterior
    SWIPE_RIGHT = auto()      # Próxima área de trabalho
    SCROLL = auto()           # Scroll vertical com indicador
    ZOOM_IN = auto()          # Zoom in: mão em pinça sobe
    ZOOM_OUT = auto()         # Zoom out: mão em pinça desce
    PAGE_FORWARD = auto()     # Círculo horário
    PAGE_BACK = auto()        # Mantido por compatibilidade
    UNDO = auto()              # Círculo anti-horário -> Ctrl+Z
    DWELL_CLICK = auto()      # Recurso opcional de acessibilidade
    VOICE_ACTIVATE = auto()   # Mantido por compatibilidade
    CONFIRM = auto()          # Mantido por compatibilidade
    PAUSE_TOGGLE = auto()     # Punho mantido -> pausa/retoma
    KEYBOARD_TOGGLE = auto()  # Duas mãos em posição de digitação


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class GestureEvent:
    gesture: Gesture
    cursor: Point
    amount: int = 0
    dwell_progress: float = 0.0
    trail: list[Point] = field(default_factory=list)
