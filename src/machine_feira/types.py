"""Tipos puros compartilhados entre reconhecimento e automação."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Gesture(Enum):
    NONE = auto()
    PINCH = auto()          # Mover Janela / Arrastar
    MAXIMIZE = auto()       # Maximizar (2 braços/mãos para os lados)
    RESTORE = auto()        # Restaurar/Flutuante (2 braços/mãos ao centro)
    MINIMIZE = auto()       # Minimizar (Palma aberta para baixo)
    SWIPE_LEFT = auto()     # Trocar Área de Trabalho para Esquerda
    SWIPE_RIGHT = auto()    # Trocar Área de Trabalho para Direita
    SCROLL = auto()         # Rolar Página (apenas indicador para cima/baixo)
    ZOOM_IN = auto()        # Zoom In (afastar polegar do indicador)
    ZOOM_OUT = auto()       # Zoom Out (juntar polegar ao indicador)
    PAGE_FORWARD = auto()   # Avançar Página (círculo horário no ar)
    PAGE_BACK = auto()      # Voltar Página (círculo anti-horário no ar)
    DWELL_CLICK = auto()    # Clicar em Links/Botões (indicador estável por 0.5s)
    VOICE_ACTIVATE = auto() # Ativar Voz/Digitação (joinha 👍)
    CONFIRM = auto()        # Confirmar/Enviar (OK 👌)


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

